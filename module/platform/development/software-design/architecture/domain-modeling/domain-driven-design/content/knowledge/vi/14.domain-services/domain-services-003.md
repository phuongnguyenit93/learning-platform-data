# Đặt tên dịch vụ bằng hoạt động nghiệp vụ có ý nghĩa

Trong Domain-Driven Design (DDD), một số quy tắc nghiệp vụ không thuộc tự nhiên về một entity hoặc value object cụ thể. Chúng có thể liên quan đến nhiều đối tượng, thể hiện một phép tính hoặc một quyết định của miền, nhưng bản thân hoạt động đó vẫn có ý nghĩa nghiệp vụ rõ ràng. Khi ấy, nhóm có thể mô hình hóa hoạt động bằng **domain service (dịch vụ miền)**.

Một domain service tốt được đặt tên bằng ngôn ngữ mà chuyên gia nghiệp vụ và nhóm phát triển cùng hiểu. Tên cần cho biết dịch vụ thực hiện hoạt động gì, trên khái niệm nào và trong phạm vi nghiệp vụ nào. Những tên chung chung như `Helper`, `Manager`, `Processor` hoặc `BusinessService` không nói rõ ý định và thường che giấu trách nhiệm thực sự.

Đặt tên chính xác không chỉ giúp mã nguồn dễ đọc. Nó còn giúp nhóm nhận ra quy tắc nào đang được mô hình hóa, phân biệt domain service với application service và dịch vụ hạ tầng, đồng thời giữ cho thiết kế phản ánh ngôn ngữ chung của bounded context.

## 1. Domain service biểu diễn một hoạt động nghiệp vụ

Trong DDD, service là một thao tác có ý nghĩa được cung cấp như một hành vi riêng. Service thường không có danh tính và trạng thái vòng đời như entity. Một domain service thường không giữ trạng thái nghiệp vụ riêng giữa các lần gọi; nó nhận dữ liệu miền, thực hiện một quy tắc hoặc phép tính và trả về kết quả miền.

Ví dụ:

- Tính giá cuối cùng của một đơn hàng theo phân khúc khách hàng và chính sách khuyến mại.
- Đánh giá một hồ sơ có đủ điều kiện cấp tín dụng hay không.
- Tính phí vận chuyển dựa trên địa chỉ, khối lượng và phương thức giao hàng.
- Xác định tỷ giá quy đổi theo chính sách của miền tại một thời điểm.
- Phân bổ khoản thanh toán cho các hóa đơn theo quy tắc kế toán.

Những hoạt động này có thể liên quan đến nhiều khái niệm. Không có entity đơn lẻ nào sở hữu toàn bộ quy tắc một cách tự nhiên. Đặt hoạt động vào một domain service giúp mô hình diễn đạt rõ trách nhiệm thay vì buộc một entity phải biết quá nhiều về các đối tượng khác.

### 1.1. Domain service không phải nơi chứa mọi logic khó

Không nên tạo domain service chỉ vì một phương thức có nhiều dòng lệnh hoặc một entity đã có nhiều phương thức. Trước tiên hãy hỏi hành vi đó có thuộc về một entity hoặc value object nào không.

Ví dụ, việc một tài khoản kiểm tra số dư của chính nó trước khi rút tiền là hành vi tự nhiên của `Account`. Nếu tạo `AccountHelper.withdraw(account, amount)` để thay đổi số dư, nhóm đã đưa hành vi ra khỏi đối tượng sở hữu invariant và làm yếu đi khả năng bảo vệ trạng thái.

Ngược lại, việc xác định mức chiết khấu cho một đơn hàng dựa trên hồ sơ khách hàng, các dòng sản phẩm và chính sách khuyến mại có thể không thuộc riêng `Customer`, `Product` hay `Order`. Đây là ứng viên phù hợp cho một domain service hoặc một policy trong miền.

### 1.2. Service được nhận diện bằng hành vi

Entity được nhận diện bằng danh tính; value object được nhận diện bằng giá trị; domain service được nhận diện bằng hoạt động mà nó cung cấp. Vì vậy, tên domain service cần làm rõ hành vi hoặc quyết định nghiệp vụ, thay vì mô tả dữ liệu mà nó đang xử lý.

Tên `OrderPricingService` gợi ra hoạt động định giá đơn hàng. Tên `OrderDataProcessor` chỉ nói rằng có dữ liệu đơn hàng được xử lý, nhưng không cho biết quy tắc nào đang được áp dụng hoặc kết quả có ý nghĩa gì.

## 2. Vì sao tên dịch vụ cần gắn với ngôn ngữ nghiệp vụ?

Tên trong domain model là một phần của Ubiquitous Language (ngôn ngữ chung). Khi chuyên gia nói “đánh giá điều kiện tín dụng”, mã nguồn nên có một khái niệm dễ liên hệ với hoạt động đó. Nếu mã chỉ có `CustomerManager.check()`, người đọc phải mở implementation để đoán xem nó kiểm tra điều kiện mua chịu, trạng thái hồ sơ hay tính hợp lệ của dữ liệu.

Tên nghiệp vụ rõ ràng mang lại một số lợi ích:

- **Làm rõ ý định:** người đọc biết dịch vụ đang đưa ra quyết định hoặc thực hiện phép tính nào.
- **Giảm mơ hồ:** các hoạt động gần nhau như tính giá, áp dụng giảm giá và xác nhận giá có thể được phân biệt.
- **Hỗ trợ trao đổi:** chuyên gia nghiệp vụ có thể đọc tên trong sơ đồ hoặc mã và xác nhận nó có đúng thuật ngữ không.
- **Giới hạn trách nhiệm:** tên cụ thể giúp phát hiện một service đang làm quá nhiều việc không liên quan.
- **Dễ kiểm thử:** tên hoạt động gợi ra các tình huống nghiệp vụ và kết quả cần xác nhận.
- **Dễ thay đổi:** khi chính sách đổi, nhóm dễ tìm nơi mô hình hóa hành vi đó.

Một tên tốt không cần dài. Nó cần đủ cụ thể để người đọc hiểu đúng trách nhiệm trong bounded context hiện tại.

## 3. Cách đặt tên domain service

Không có một mẫu tên duy nhất bắt buộc cho mọi ngôn ngữ lập trình. Tuy nhiên, có thể dùng một số nguyên tắc để tạo tên nhất quán.

### 3.1. Bắt đầu từ động từ hoặc hoạt động nghiệp vụ

Hãy hỏi chuyên gia: “Dịch vụ này đang làm gì?”. Câu trả lời thường chứa động từ nghiệp vụ như:

- `calculate` — tính toán.
- `assess` — đánh giá.
- `allocate` — phân bổ.
- `authorize` — cấp phép hoặc chấp thuận.
- `determine` — xác định.
- `convert` — quy đổi.
- `reconcile` — đối soát.
- `quote` — đưa ra báo giá.
- `schedule` — lập lịch.
- `classify` — phân loại.

Chọn động từ phản ánh đúng ý nghĩa. Ví dụ, `assessCreditEligibility` diễn đạt việc đánh giá điều kiện tín dụng; `validateCustomer` quá rộng vì không nói rõ tiêu chí nào đang được kiểm tra.

### 3.2. Nêu rõ đối tượng hoặc kết quả của hoạt động

Động từ đơn lẻ thường chưa đủ. Tên cần cho biết hành động áp dụng lên khái niệm nào hoặc tạo ra kết quả gì.

| Tên mơ hồ | Tên diễn đạt hoạt động nghiệp vụ rõ hơn |
| --- | --- |
| `process()` | `calculateOrderPrice()` |
| `checkCustomer()` | `assessCreditEligibility()` |
| `handlePayment()` | `allocatePaymentToInvoices()` |
| `execute()` | `reconcileAccountBalance()` |
| `convert()` | `convertOrderCurrency()` |
| `manageShipping()` | `calculateShippingFee()` |

Tên được cải thiện giúp người đọc hiểu mục đích mà không cần biết chi tiết kỹ thuật bên trong.

### 3.3. Dùng thuật ngữ của bounded context

Một từ có thể có ý nghĩa khác nhau giữa các bounded context. Ví dụ, “khách hàng” trong bán hàng có thể là người mua, còn trong thanh toán có thể là chủ thể chịu nghĩa vụ trả tiền. Domain service phải sử dụng thuật ngữ của context mà nó thuộc về.

Nếu context thanh toán dùng khái niệm `PayerAccount`, tên `assessPayerCreditLimit` có thể phù hợp hơn `checkCustomer`. Nếu context bán hàng dùng `Buyer`, tên `calculateBuyerDiscount` có thể phản ánh đúng ngôn ngữ hơn.

Không nên đưa tên của một context khác vào service chỉ vì hai context cùng tham chiếu một người hoặc tổ chức ngoài đời. Nếu cần trao đổi, hãy dùng hợp đồng và mô hình chuyển đổi tại ranh giới.

### 3.4. Dùng hậu tố theo bản chất trách nhiệm

Hậu tố `Service` thường được dùng cho domain service, nhưng một số tên khác có thể diễn đạt chính xác hơn:

| Hậu tố hoặc dạng tên | Khi phù hợp | Ví dụ |
| --- | --- | --- |
| `...Service` | Một hoạt động miền có ý nghĩa, có thể kết hợp nhiều khái niệm | `OrderPricingService` |
| `...Policy` | Một chính sách quyết định điều gì được phép hoặc điều kiện nào áp dụng | `CreditApprovalPolicy` |
| `...Calculator` | Một phép tính có đầu vào và kết quả rõ | `ShippingFeeCalculator` |
| `...Allocator` | Phân bổ một nguồn lực hoặc khoản tiền theo quy tắc | `PaymentAllocator` |
| `...Specification` | Một điều kiện nghiệp vụ có thể đánh giá trên đối tượng | `EligibleForDiscountSpecification` |
| `...Resolver` | Xác định hoặc chọn một kết quả theo quy tắc | `ApplicableTaxRateResolver` |

Đây là gợi ý về ngữ nghĩa, không phải quy định đặt tên cứng. Một `Policy` hoặc `Specification` có thể được mô hình hóa như một đối tượng riêng thay vì service thông thường. Hãy chọn tên theo cách chuyên gia mô tả trách nhiệm và cách nhóm muốn biểu diễn nó.

### 3.5. Tên lớp và tên phương thức cần bổ sung cho nhau

Tên lớp nên thể hiện phạm vi trách nhiệm; tên phương thức thể hiện hành động cụ thể. Tránh lặp từ không cần thiết hoặc để cả hai tên đều chung chung.

Ví dụ:

```java
public final class OrderPricingService {
    public PriceQuote calculateQuote(OrderPricingInput input) {
        // Áp dụng quy tắc định giá của miền.
    }
}
```

Tên `OrderPricingService` cho biết nhóm quy tắc mà service phụ trách. Phương thức `calculateQuote` nêu rõ hoạt động được yêu cầu và kết quả trả về.

Nếu service chỉ có một hoạt động duy nhất, tên phương thức vẫn nên đủ rõ khi được đọc trong ngữ cảnh sử dụng: `pricingService.calculateQuote(input)` dễ hiểu hơn `pricingService.execute(input)`.

## 4. Phân biệt domain service với application service

Đây là điểm quan trọng vì cả hai đều có thể mang hậu tố `Service`, nhưng phục vụ các mục đích khác nhau.

**Domain service** biểu diễn quy tắc hoặc hoạt động thuộc miền nghiệp vụ. Nó dùng ngôn ngữ domain, làm việc với khái niệm miền và không nên phụ thuộc vào giao thức hoặc framework cụ thể.

**Application service** điều phối một use case. Nó tải dữ liệu cần thiết qua repository, gọi hành vi trên entity hoặc domain service, quản lý transaction theo ranh giới ứng dụng và phối hợp các bước cần thiết. Application service không nên trở thành nơi chứa các quy tắc miền chỉ vì nó thuận tiện để viết.

| Tiêu chí | Domain service | Application service |
| --- | --- | --- |
| Trọng tâm | Quy tắc hoặc hoạt động nghiệp vụ | Điều phối một use case |
| Ngôn ngữ | Thuật ngữ miền và hành vi nghiệp vụ | Command, query, use case và luồng ứng dụng |
| Công việc điển hình | Tính giá, đánh giá điều kiện, phân bổ khoản thanh toán | Tải aggregate, gọi domain behavior, lưu kết quả, phát thông báo |
| Trạng thái | Thường không giữ trạng thái nghiệp vụ riêng | Thường không giữ trạng thái giữa các request |
| Persistence | Không nên tự quản lý vòng đời lưu trữ của aggregate | Thường dùng repository qua các abstraction |
| Ví dụ tên | `OrderPricingService`, `CreditApprovalPolicy` | `PlaceOrderService`, `ApproveCreditApplicationUseCase` |

Ví dụ, `OrderPricingService` tính báo giá theo chính sách miền. `PlaceOrderService` tải thông tin khách và sản phẩm, gọi dịch vụ định giá, tạo aggregate `Order`, lưu đơn và điều phối các bước của use case.

Không nên gọi một lớp là `OrderService` nếu nó vừa tính giá, vừa lưu database, vừa gửi email, vừa gọi cổng thanh toán. Tên rộng như vậy thường che giấu việc nhiều trách nhiệm đang bị trộn lẫn.

## 5. Phân biệt domain service với dịch vụ hạ tầng

Một service trong hệ thống không nhất thiết là domain service. Dịch vụ hạ tầng cung cấp khả năng kỹ thuật như gửi email, đọc đồng hồ hệ thống, lưu file hoặc gọi API bên ngoài.

Ví dụ:

- `EmailSender` gửi email qua SMTP hoặc nhà cung cấp.
- `SystemClock` cung cấp thời gian hiện tại.
- `PaymentGatewayClient` gọi API thanh toán.
- `FileStorage` lưu và tải tệp.

Các thành phần này có thể được ứng dụng sử dụng thông qua port và adapter. Chúng không tự động trở thành domain service chỉ vì được inject vào một lớp trong domain.

Hãy phân biệt:

| Tên | Bản chất | Vị trí thường gặp |
| --- | --- | --- |
| `CreditEligibilityPolicy` | Quy tắc xác định khách có đủ điều kiện tín dụng | Domain model |
| `ApproveCreditApplicationService` | Điều phối use case phê duyệt hồ sơ | Application layer |
| `CreditBureauClient` | Gọi dịch vụ dữ liệu tín dụng bên ngoài | Infrastructure adapter |
| `SystemClock` | Cung cấp thời gian từ hệ thống | Infrastructure adapter qua clock port |

Nếu quy tắc tín dụng cần dữ liệu từ một dịch vụ bên ngoài, application service có thể lấy dữ liệu qua output port rồi truyền dữ liệu đã được diễn giải vào domain service. Cách tổ chức cụ thể phụ thuộc vào nơi sở hữu quy tắc và độ ổn định của thông tin.

## 6. Khi nào nên tạo domain service?

Một hoạt động có thể phù hợp với domain service khi các điều kiện sau xuất hiện:

1. Hoạt động có ý nghĩa nghiệp vụ rõ và chuyên gia có thể diễn đạt bằng một thuật ngữ.
2. Quy tắc không thuộc tự nhiên về một entity hoặc value object cụ thể.
3. Hoạt động có thể liên quan đến nhiều khái niệm miền hoặc thể hiện một phép tính/quyết định độc lập.
4. Đặt hành vi vào service giúp giữ trách nhiệm của entity rõ ràng mà không làm mất khả năng bảo vệ invariant.

Ví dụ, tính giá một đơn có thể cần hồ sơ khách hàng, các dòng hàng, chính sách giá và chương trình khuyến mại. Không nên buộc `Customer` phải biết cách định giá mọi sản phẩm hoặc buộc `Product` phải biết toàn bộ thông tin đơn hàng. `OrderPricingService` có thể biểu diễn hoạt động này.

Ngược lại, nếu hành vi chỉ thay đổi trạng thái nội bộ của một entity và phụ thuộc vào invariant của chính entity đó, hãy đặt hành vi trên entity. Ví dụ `order.cancel(reason)` thường tự nhiên hơn `OrderCancellationService.cancel(order, reason)` nếu việc hủy là hành vi của chính đơn hàng.

## 7. Ví dụ: định giá đơn hàng bằng domain service

Giả sử chính sách bán hàng quy định giá cuối cùng phụ thuộc vào:

- Phân khúc của người mua.
- Các sản phẩm và số lượng trong đơn.
- Bảng giá có hiệu lực tại ngày đặt hàng.
- Khuyến mại áp dụng cho từng dòng hoặc toàn đơn.
- Giới hạn giảm giá tối đa theo chính sách.

Không có entity nào trong số `Buyer`, `Product` hay `Order` sở hữu toàn bộ quy tắc này một cách tự nhiên. Nhóm có thể định nghĩa `OrderPricingService` để tính một `PriceQuote`.

```java
public record BuyerPricingProfile(
        BuyerId buyerId,
        BuyerSegment segment
) {}

public record PricedOrderLine(
        ProductId productId,
        int quantity,
        Money listPrice
) {}

public record OrderPricingInput(
        BuyerPricingProfile buyer,
        List<PricedOrderLine> lines,
        PricingDate pricingDate,
        PromotionCode promotionCode
) {}

public record PriceQuote(
        Money subtotal,
        Money discount,
        Money total
) {}

public final class OrderPricingService {
    public PriceQuote calculateQuote(OrderPricingInput input) {
        // 1. Kiểm tra dữ liệu miền cần cho định giá.
        // 2. Tính subtotal theo các dòng hàng.
        // 3. Áp dụng chính sách theo phân khúc người mua.
        // 4. Kiểm tra điều kiện và giới hạn khuyến mại.
        // 5. Trả về PriceQuote theo tiền tệ và quy tắc làm tròn.
        throw new UnsupportedOperationException("Illustrative example");
    }
}
```

Các kiểu `BuyerPricingProfile`, `PricedOrderLine`, `PricingDate`, `PromotionCode`, `Money` và `PriceQuote` là kiểu miền hoặc dữ liệu đầu vào/đầu ra được định nghĩa theo ngôn ngữ của context. Đoạn mã cố ý để phần tính toán ở dạng chú thích vì công thức thực tế phụ thuộc chính sách của từng doanh nghiệp.

Tên `OrderPricingService.calculateQuote` cho biết rõ dịch vụ làm gì và tạo ra kết quả nào. Nếu chỉ đặt tên là `PricingHelper.execute`, người đọc không biết đó là tính báo giá, tính thuế, áp dụng chiết khấu hay cập nhật bảng giá.

### 7.1. Application service điều phối domain service

Application service chịu trách nhiệm tải thông tin cần thiết và lưu kết quả của use case:

```java
public final class PlaceOrderService {
    private final BuyerRepository buyers;
    private final ProductCatalog products;
    private final OrderRepository orders;
    private final OrderPricingService pricingService;

    public PlaceOrderService(
            BuyerRepository buyers,
            ProductCatalog products,
            OrderRepository orders,
            OrderPricingService pricingService
    ) {
        this.buyers = buyers;
        this.products = products;
        this.orders = orders;
        this.pricingService = pricingService;
    }

    public OrderId place(PlaceOrderCommand command) {
        BuyerPricingProfile buyer = buyers.getPricingProfile(command.buyerId());
        List<PricedOrderLine> lines = products.getPricingLines(command.lines());

        PriceQuote quote = pricingService.calculateQuote(
                new OrderPricingInput(
                        buyer,
                        lines,
                        command.pricingDate(),
                        command.promotionCode()
                )
        );

        Order order = Order.create(command.buyerId(), lines, quote);
        orders.save(order);
        return order.id();
    }
}
```

Ví dụ cho thấy ranh giới trách nhiệm: application service điều phối dữ liệu và use case; domain service thực hiện quy tắc định giá; aggregate `Order` quản lý trạng thái và bất biến của đơn; repository lưu aggregate. Trong một hệ thống thật, nhóm cần xác định snapshot giá, transaction, tồn kho, thanh toán và các bước phối hợp khác.

## 8. Ví dụ: đánh giá điều kiện tín dụng

Giả sử một doanh nghiệp cho khách hàng mua chịu. Quyết định cấp tín dụng phụ thuộc vào hạn mức còn lại, tổng nghĩa vụ hiện tại, nhóm rủi ro và chính sách theo loại hợp đồng. Đây có thể là một quy tắc không thuộc riêng một entity.

Tên `CreditApprovalPolicy` hoặc `CreditEligibilityService` cho biết rõ đây là hoạt động đánh giá điều kiện tín dụng. Phương thức có thể là `assess(...)` và trả về một kết quả miền:

```java
public record CreditAssessment(
        boolean eligible,
        Money availableLimit,
        CreditDecisionReason reason
) {}

public final class CreditApprovalPolicy {
    public CreditAssessment assess(
            CreditProfile profile,
            Money requestedAmount,
            CreditPolicyTerms terms
    ) {
        // Đánh giá hạn mức, nghĩa vụ hiện tại và điều kiện chính sách.
        throw new UnsupportedOperationException("Illustrative example");
    }
}
```

Kết quả `CreditAssessment` diễn đạt quyết định theo ngôn ngữ miền. Nó hữu ích hơn một boolean đơn giản nếu nghiệp vụ cần giải thích lý do từ chối, hạn mức còn lại hoặc điều kiện cần bổ sung.

Nếu quyết định tín dụng cần gọi một tổ chức đánh giá tín dụng bên ngoài, application service có thể lấy kết quả qua port, sau đó truyền dữ liệu cần thiết vào policy. `CreditApprovalPolicy` không nên tự tạo HTTP request hoặc biết endpoint của nhà cung cấp.

## 9. Đặt tên phương thức và kiểu dữ liệu kết quả

Tên lớp tốt vẫn chưa đủ nếu phương thức có tên mơ hồ hoặc trả về kiểu dữ liệu không thể hiện ý nghĩa nghiệp vụ.

### 9.1. Dùng động từ đúng với quyết định

Một số động từ có vẻ gần nghĩa nhưng thể hiện mức cam kết khác nhau:

- `assess` đánh giá điều kiện và đưa ra nhận định.
- `approve` chấp thuận một yêu cầu theo thẩm quyền.
- `authorize` cấp quyền hoặc cho phép một hành động.
- `calculate` tính ra một giá trị.
- `quote` đưa ra một báo giá có thể có thời hạn hoặc điều kiện.
- `allocate` phân bổ một nguồn lực hoặc khoản tiền.
- `reconcile` đối chiếu và xử lý chênh lệch.

Ví dụ, `assessCreditEligibility()` có thể trả về kết quả đánh giá. `approveCredit()` thể hiện quyết định chấp thuận. Nếu service chỉ tính toán và chưa có quyền ra quyết định cuối cùng, không nên đặt tên là `approve`.

### 9.2. Trả về kiểu miền thay vì kiểu kỹ thuật chung chung

Nếu dịch vụ định giá trả về `double`, người gọi phải tự đoán tiền tệ, độ chính xác, chiết khấu và thuế đã được tính hay chưa. Một kiểu `PriceQuote` hoặc `Money` có thể thể hiện rõ hơn ý nghĩa của kết quả.

Tương tự, đánh giá tín dụng có thể trả về `CreditAssessment` thay vì `boolean`, nếu người dùng nghiệp vụ cần biết lý do và điều kiện. Một dịch vụ phân bổ thanh toán có thể trả về `PaymentAllocationResult` thay vì `Map<String, BigDecimal>` nếu kết quả có quy tắc và ý nghĩa riêng.

### 9.3. Tránh tên phụ thuộc vào cách triển khai

Tên như `JpaPricingService`, `SqlDiscountProcessor` hoặc `HttpCreditManager` mô tả công nghệ thay vì hoạt động nghiệp vụ. Những tên này phù hợp hơn với adapter hoặc infrastructure component nếu chúng thật sự phản ánh implementation.

Domain service nên giữ tên ổn định khi nhóm đổi database, framework hoặc giao thức. Nếu tên phải thay đổi chỉ vì thay thư viện, có thể trách nhiệm đang bị đặt nhầm tầng.

## 10. Tránh các tên dịch vụ chung chung

Một số tên thường xuất hiện khi nhóm chưa làm rõ trách nhiệm:

| Tên nên tránh nếu không có định nghĩa rõ | Vấn đề | Câu hỏi để cải thiện |
| --- | --- | --- |
| `Helper` | Không diễn đạt hoạt động hoặc phạm vi | Nó hỗ trợ quyết định nghiệp vụ nào? |
| `Manager` | Có thể bao gồm mọi loại thao tác | Nó quản lý vòng đời nào và có quyền quyết định gì? |
| `Processor` | Không nói rõ đầu vào được xử lý thành kết quả nào | Quy trình nghiệp vụ cụ thể là gì? |
| `Handler` | Có thể chỉ mô tả cơ chế nhận sự kiện | Nó xử lý command hay thực hiện quy tắc miền nào? |
| `CommonService` | Trách nhiệm quá rộng, thường gom logic không liên quan | Những hoạt động nào thực sự thuộc cùng một khái niệm? |
| `BusinessService` | Không phân biệt được domain service với application service | Quy tắc miền cụ thể nào được biểu diễn? |
| `DataService` | Tập trung vào dữ liệu thay vì hành vi | Dữ liệu được dùng để thực hiện hoạt động nào? |
| `execute()` hoặc `process()` | Phương thức không nói rõ ý định | Người dùng nghiệp vụ sẽ gọi hành động đó là gì? |

Những từ như `Manager`, `Processor` hoặc `Handler` không bị cấm tuyệt đối. Chúng có thể phù hợp trong một số ngữ cảnh kỹ thuật hoặc khi tổ chức đã định nghĩa trách nhiệm cụ thể. Vấn đề là không dùng chúng để thay thế việc tìm ra tên nghiệp vụ.

## 11. Giữ domain service tập trung và không trạng thái

Domain service thường không giữ trạng thái nghiệp vụ thay đổi qua các lần gọi. Dữ liệu cần cho một hoạt động được truyền qua tham số hoặc được cung cấp bởi một abstraction phù hợp. Kết quả được trả về dưới dạng kiểu miền hoặc được phản ánh vào các đối tượng miền theo quy tắc.

Một số dấu hiệu cho thấy service đang có quá nhiều trách nhiệm:

- Có nhiều nhóm phương thức không liên quan như định giá, gửi email và lưu hồ sơ.
- Giữ nhiều thuộc tính mutable theo từng khách hàng hoặc từng đơn hàng.
- Có tên chung chung nhưng implementation chứa nhiều quy tắc khác nhau.
- Tự tải và lưu nhiều aggregate, gọi API ngoài và quản lý toàn bộ transaction.
- Trả về kiểu dữ liệu kỹ thuật khiến caller phải diễn giải lại ý nghĩa nghiệp vụ.

Khi gặp các dấu hiệu này, hãy xem xét tách quy tắc miền, use case và tích hợp kỹ thuật về đúng trách nhiệm.

### 11.1. Service có thể phụ thuộc vào abstraction, nhưng cần đúng tầng

Một số quy tắc miền cần thông tin không có sẵn trong các entity đầu vào, ví dụ tỷ giá có hiệu lực tại thời điểm giao dịch hoặc lịch làm việc của một vùng. Nhóm cần xác định thông tin đó thuộc về mô hình miền hay là dữ liệu được lấy từ một hệ thống ngoài.

Application layer có thể truy vấn dữ liệu qua repository hoặc output port rồi truyền một snapshot miền vào domain service. Trong trường hợp phù hợp, domain service cũng có thể sử dụng một interface thể hiện khái niệm miền như `ExchangeRateProvider`, miễn là hợp đồng không phụ thuộc HTTP, SDK hoặc database cụ thể.

Không nên để domain service tự mở kết nối database, gọi REST client cụ thể hoặc gửi email. Những chi tiết đó thuộc adapter và application orchestration.

## 12. Quy trình đặt tên domain service

Khi phát hiện một hoạt động có thể cần domain service, nhóm có thể thực hiện các bước sau.

### Bước 1: Mô tả hoạt động bằng câu nghiệp vụ

Yêu cầu chuyên gia hoàn thành câu: “Trong quy trình này, chúng ta cần ...”. Ví dụ: “Chúng ta cần đánh giá khách hàng có đủ điều kiện mua chịu hay không”. Câu trả lời giúp tìm động từ và kết quả thực tế.

### Bước 2: Xác định khái niệm và quy tắc liên quan

Liệt kê entity, value object, policy và dữ liệu miền tham gia. Làm rõ điều kiện, đầu vào, đầu ra và trường hợp ngoại lệ. Không bắt đầu bằng tên lớp kỹ thuật.

### Bước 3: Kiểm tra hành vi có thuộc entity/value object không

Hỏi đối tượng nào sở hữu trạng thái và invariant đang bị thay đổi. Nếu hành vi tự nhiên thuộc một entity, hãy ưu tiên đặt phương thức trên entity đó. Nếu hoạt động liên quan nhiều khái niệm hoặc không có chủ thể tự nhiên, cân nhắc domain service.

### Bước 4: Chọn động từ phản ánh đúng ý nghĩa

Phân biệt tính toán, đánh giá, phê duyệt, phân bổ, đối soát hoặc quy đổi. Động từ phải thể hiện đúng mức cam kết và quyền quyết định của hoạt động.

### Bước 5: Nêu rõ phạm vi trong tên

Thêm khái niệm hoặc context cần thiết để tên không bị hiểu rộng. Ví dụ `ShippingFeeCalculator` rõ hơn `FeeCalculator` nếu hệ thống còn có phí thanh toán, phí lưu kho và phí dịch vụ khác.

### Bước 6: Chọn hậu tố phù hợp

Chọn `Service`, `Policy`, `Calculator`, `Allocator` hoặc tên khác dựa trên bản chất trách nhiệm. Không thêm hậu tố chỉ vì thói quen nếu nó làm tên khó hiểu.

### Bước 7: Kiểm tra tên với chuyên gia và trong câu gọi

Đọc tên trong một câu tự nhiên: “Đánh giá điều kiện tín dụng”, “Tính báo giá đơn hàng”, “Phân bổ khoản thanh toán”. Sau đó đọc trong mã: `creditApprovalPolicy.assess(...)`. Nếu chuyên gia hiểu đúng ý nghĩa và nhóm phát triển dùng tên tự nhiên, tên có cơ sở tốt.

### Bước 8: Kiểm tra phạm vi trách nhiệm sau khi triển khai

Nếu service ngày càng chứa các hoạt động khác nhau, hãy xem lại tên và ranh giới. Tên tốt cần tiếp tục phản ánh đúng trách nhiệm sau khi mô hình phát triển.

## 13. Bảng ví dụ tên trước và sau khi làm rõ

| Tình huống nghiệp vụ | Tên chưa rõ | Tên gợi ý | Ý nghĩa |
| --- | --- | --- | --- |
| Tính giá theo khách hàng và khuyến mại | `OrderHelper` | `OrderPricingService` | Tính báo giá theo chính sách định giá |
| Đánh giá khả năng mua chịu | `CustomerChecker` | `CreditEligibilityPolicy` | Đánh giá điều kiện tín dụng |
| Tính chi phí giao hàng | `ShippingManager` | `ShippingFeeCalculator` | Tính phí theo điều kiện vận chuyển |
| Phân bổ khoản thu cho nhiều hóa đơn | `PaymentProcessor` | `PaymentAllocator` | Phân bổ tiền theo quy tắc thanh toán |
| Đối chiếu số dư sổ cái và tài khoản | `AccountHelper` | `AccountReconciliationService` | Phát hiện và xử lý chênh lệch theo chính sách |
| Chọn mức thuế áp dụng | `TaxService` | `ApplicableTaxRateResolver` | Xác định mức thuế phù hợp với giao dịch |
| Quy đổi tiền tệ | `CurrencyManager` | `MoneyExchangeService` | Quy đổi theo tỷ giá và thời điểm xác định |

Các tên gợi ý cần được đối chiếu với ngôn ngữ thật của từng bounded context. Một doanh nghiệp có thể dùng “phí giao hàng”, “cước vận chuyển” hoặc “chi phí logistics” với những định nghĩa khác nhau. Không nên chuẩn hóa tên chỉ dựa trên ví dụ trong tài liệu.

## 14. Những sai lầm thường gặp

| Sai lầm | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| Đặt tên `Helper`, `Manager` hoặc `Processor` mà không có phạm vi rõ | Người đọc không biết service thực hiện quy tắc nào | Dùng động từ nghiệp vụ và khái niệm cụ thể |
| Tạo domain service cho mọi phương thức phức tạp | Hành vi bị tách khỏi entity đang sở hữu invariant | Kiểm tra trách nhiệm của entity và value object trước |
| Dùng tên theo công nghệ như `JpaOrderService` cho domain logic | Mô hình bị gắn với implementation | Dùng thuật ngữ nghiệp vụ; để tên công nghệ ở adapter |
| Đặt logic use case vào domain service | Domain service trở thành nơi điều phối persistence, transaction và thông báo | Chuyển điều phối lên application service |
| Để domain service gửi email hoặc gọi HTTP trực tiếp | Quy tắc miền phụ thuộc hạ tầng và khó kiểm thử | Dùng output port và adapter ở ranh giới |
| Dùng động từ không phản ánh quyền quyết định | Tên gây hiểu sai mức cam kết, ví dụ `approve` khi chỉ mới `assess` | Xác nhận ý nghĩa với chuyên gia nghiệp vụ |
| Trả về kiểu kỹ thuật không có ngữ nghĩa | Caller phải tự suy đoán và tái tạo quy tắc | Dùng value object hoặc result type của miền |
| Gom nhiều hoạt động không liên quan vào một service | Trách nhiệm phình to và khó thay đổi | Tách theo hoạt động và quy tắc nghiệp vụ |
| Dùng thuật ngữ của context khác | Mô hình nội bộ mất tính nhất quán | Đặt tên theo Ubiquitous Language của context sở hữu |

## 15. Nguyên tắc thực hành

Khi đặt tên domain service, nhóm nên ghi nhớ:

- **Bắt đầu từ hoạt động nghiệp vụ.** Hỏi chuyên gia dịch vụ đang làm gì và tạo ra quyết định hoặc kết quả nào.
- **Dùng động từ có nghĩa chính xác.** Phân biệt `assess`, `approve`, `authorize`, `calculate`, `allocate` và các hành động gần nghĩa.
- **Nêu rõ khái niệm liên quan.** Tên cần đủ cụ thể để không nhầm với dịch vụ khác trong cùng bounded context.
- **Dùng Ubiquitous Language.** Thuật ngữ phải được chuyên gia nghiệp vụ hiểu và nhóm phát triển dùng nhất quán.
- **Ưu tiên hành vi trên entity khi phù hợp.** Không tách hành vi ra service nếu entity hoặc value object tự nhiên sở hữu quy tắc.
- **Giữ domain service tập trung.** Một service nên có trách nhiệm nghiệp vụ rõ, thường không giữ trạng thái riêng giữa các lần gọi.
- **Phân biệt các tầng service.** Domain service giữ quy tắc miền; application service điều phối use case; infrastructure service thực hiện khả năng kỹ thuật.
- **Dùng kiểu miền cho đầu vào và đầu ra.** Kết quả nên diễn đạt ý nghĩa nghiệp vụ, không buộc caller tự suy luận từ kiểu dữ liệu chung.
- **Tránh tên phụ thuộc implementation.** Công nghệ có thể thay đổi mà tên hoạt động miền vẫn giữ nguyên.
- **Kiểm tra tên trong câu gọi và với chuyên gia.** Tên cần tự nhiên trong trao đổi và rõ ràng khi đọc mã nguồn.

Tên domain service tốt mô tả một hoạt động mà tổ chức thực sự thực hiện. Khi tên dùng đúng động từ, đúng khái niệm và đúng phạm vi bounded context, nó giúp người đọc hiểu ý định của mô hình mà không phải lần theo chi tiết triển khai. Việc đặt tên cũng là một cách kiểm tra thiết kế: nếu nhóm không thể diễn đạt service bằng một hoạt động nghiệp vụ rõ ràng, có thể trách nhiệm của nó chưa được xác định đúng.

## 16. Câu hỏi tự kiểm tra

1. Domain service biểu diễn loại hành vi nào và vì sao nó thường không có danh tính riêng như entity?
2. Vì sao không nên tạo domain service chỉ vì một phương thức có nhiều dòng lệnh?
3. Hãy phân biệt `OrderPricingService` với `OrderDataProcessor` về mức độ thể hiện ý nghĩa nghiệp vụ.
4. Khi nào nên đặt hành vi trên entity hoặc value object thay vì tạo domain service?
5. Phân biệt domain service, application service và infrastructure service bằng ví dụ cụ thể.
6. Vì sao `assessCreditEligibility` có thể chính xác hơn `approveCredit` trong một bước chỉ đánh giá điều kiện?
7. Hậu tố `Service`, `Policy`, `Calculator`, `Allocator` và `Resolver` gợi ý những loại trách nhiệm nào?
8. Vì sao domain service nên dùng thuật ngữ của bounded context sở hữu nó?
9. Khi domain service cần dữ liệu từ hệ thống bên ngoài, nhóm nên tổ chức việc lấy dữ liệu và chuyển đổi ở đâu?
10. Hãy chọn một hoạt động nghiệp vụ, viết câu mô tả cho chuyên gia, đề xuất tên class và method, kiểu kết quả, rồi giải thích vì sao hoạt động đó thuộc domain service.
