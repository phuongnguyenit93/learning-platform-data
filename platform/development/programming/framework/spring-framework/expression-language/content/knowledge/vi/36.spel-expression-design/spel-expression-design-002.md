# Đặt tên biến và root property để biểu thức SpEL tự giải thích

Một biểu thức Spring Expression Language (SpEL) thường ngắn, nhưng vẫn có thể khó hiểu nếu tên biến và property quá chung chung hoặc không phản ánh đúng ý nghĩa nghiệp vụ. Những tên như #x, #value, #data hay property status có thể đủ để parser chạy, nhưng người đọc phải lần ngược context và model mới biết dữ liệu đại diện cho điều gì.

Tên tốt giúp expression gần với một câu mô tả quy tắc. Ví dụ, #order.total >= #minimumOrderTotal dễ hiểu hơn #a >= #b. Tương tự, khi root object đã là OrderPolicyInput, property customerVerified hoặc orderTotal có thể làm rõ điều kiện mà không cần thêm nhiều chú thích.

Bài học này tập trung vào cách đặt tên biến và root property có ý nghĩa, cách phân biệt root object với variable, và cách thiết kế context để expression có thể tự giải thích mà vẫn ổn định, dễ kiểm thử và dễ bảo trì.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Đặt tên variable theo vai trò và ý nghĩa nghiệp vụ.
- Đặt tên root property rõ ràng, nhất quán với model Java.
- Phân biệt property của root object với variable có tiền tố #.
- Dùng #root và #this đúng ngữ cảnh.
- Chọn giữa root object và nhiều variable khi thiết kế EvaluationContext.
- Tránh tên quá ngắn, mơ hồ, trùng nghĩa hoặc phụ thuộc chi tiết triển khai.
- Đặt tên collection, Boolean, giá trị tiền tệ, thời gian và ngưỡng theo domain.
- Làm expression dễ đọc mà không cần chú thích dài.
- Giữ naming contract ổn định khi expression được lưu trong cấu hình hoặc database.

Bạn nên biết cách tạo SpelExpressionParser, Expression, EvaluationContext, root object, variable và JavaBean property.

## 2. Vì sao tên có ý nghĩa quan trọng?

SpEL expression thường được đọc bởi nhiều người: người viết policy, người bảo trì Java code, người debug production và người review thay đổi. Tên mơ hồ làm tăng chi phí hiểu và có thể khiến người đọc diễn giải sai quy tắc.

Ví dụ khó hiểu:

~~~text
#a > #b and #c
~~~

Người đọc không biết a là tổng đơn hàng hay hạn mức, b là ngưỡng nào, c là trạng thái gì.

Cách viết rõ hơn:

~~~text
#orderTotal >= #minimumOrderTotal and #customerVerified
~~~

Tên biến cho biết:

- orderTotal là tổng tiền của đơn hàng.
- minimumOrderTotal là ngưỡng tối thiểu.
- customerVerified là trạng thái xác minh khách hàng.

Expression lúc này thể hiện gần như trực tiếp một quy tắc nghiệp vụ.

Tên rõ ràng cũng giúp phát hiện lỗi khi review. Nếu một expression dùng #customerVerified để kiểm tra quyền truy cập, người đọc có thể nhận ra ngay rằng trạng thái xác minh khách hàng không đồng nghĩa với quyền truy cập.

## 3. Phân biệt root property và variable

SpEL có hai cách truy cập dữ liệu thường gặp:

- Property không có tiền tố được đọc trên root object hiện tại.
- Variable được truy cập bằng tiền tố # và được đăng ký trong EvaluationContext.

Ví dụ root object:

~~~java
public record OrderPolicyInput(
    BigDecimal orderTotal,
    boolean customerVerified
) {}
~~~

Expression dùng property của root object:

~~~text
orderTotal >= 100 and customerVerified
~~~

Đăng ký variable:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("minimumOrderTotal", new BigDecimal("100"));
~~~

Expression kết hợp root property và variable:

~~~text
orderTotal >= #minimumOrderTotal and customerVerified
~~~

Trong expression này, orderTotal và customerVerified thuộc root object; minimumOrderTotal là variable.

Có thể viết rõ root property bằng #root:

~~~text
#root.orderTotal >= #minimumOrderTotal
~~~

Cách viết tường minh hữu ích khi expression có nhiều tầng collection hoặc nhiều ngữ cảnh hiện tại. Với biểu thức đơn giản, property root không tiền tố thường dễ đọc hơn.

## 4. Chọn root object hay nhiều variable?

Root object phù hợp khi các dữ liệu đầu vào tạo thành một đối tượng nghiệp vụ hoặc một DTO có schema rõ ràng.

Ví dụ:

~~~java
public record OrderPolicyInput(
    String orderStatus,
    BigDecimal orderTotal,
    boolean customerVerified,
    String customerTier
) {}
~~~

Expression:

~~~text
orderStatus == 'PAID'
    and orderTotal >= #minimumOrderTotal
    and customerVerified
~~~

Cách này gom các thuộc tính cùng thuộc một input vào một object.

Variables phù hợp khi expression cần kết hợp một số giá trị độc lập hoặc giá trị được cung cấp từ nhiều nguồn:

~~~java
context.setVariable("order", order);
context.setVariable("customer", customer);
context.setVariable("minimumOrderTotal", minimumOrderTotal);
context.setVariable("evaluationTime", evaluationTime);
~~~

Expression:

~~~text
#order.total >= #minimumOrderTotal
    and #customer.verified
    and #order.createdAt <= #evaluationTime
~~~

Không cần chuyển mọi giá trị thành variable. Nếu dữ liệu đã thuộc một DTO, giữ chúng thành root properties thường tạo cấu trúc dễ hiểu hơn. Nếu mỗi field được đăng ký rời rạc, người đọc phải kiểm tra nhiều lệnh setVariable mới hiểu đầy đủ input contract.

## 5. Quy tắc đặt tên variable

Tên variable nên mô tả ý nghĩa nghiệp vụ và vai trò của giá trị trong expression.

Các quy tắc hữu ích:

- Dùng camelCase nhất quán với Java.
- Ưu tiên danh từ có nghĩa cụ thể: orderTotal, customerTier, accountBalance.
- Dùng tên thể hiện ngưỡng: minimumOrderTotal, maximumRetryCount, allowedFailureRate.
- Dùng tên thể hiện thời điểm: evaluationTime, orderCreatedAt, expirationTime.
- Dùng tên thể hiện tập dữ liệu: eligibleRegions, blockedCustomerIds, approvedPaymentMethods.
- Dùng tên Boolean thể hiện trạng thái hoặc khả năng: customerVerified, hasAccess, canApprove, shouldRetry.
- Tránh tên một ký tự hoặc viết tắt nội bộ không phổ biến.
- Không đưa kiểu Java vào tên nếu không giúp hiểu domain, ví dụ stringName hoặc integerValue.
- Không đặt tên theo vị trí tạm thời như firstValue, secondValue nếu có thể dùng tên theo ý nghĩa.

Tên biến nên ổn định theo hợp đồng expression. Nếu expression được lưu trong database hoặc do quản trị viên cấu hình, đổi tên variable có thể làm các expression cũ không còn chạy.

## 6. Đặt tên Boolean rõ ràng

Boolean thường xuất hiện trong predicate và điều kiện. Tên cần cho biết chính xác trạng thái được kiểm tra.

Tên mơ hồ:

~~~text
#active
#valid
#allowed
~~~

Nếu context có nhiều loại đối tượng, các tên trên không cho biết active của cái gì hoặc ai đã cho phép điều gì.

Tên rõ hơn:

~~~text
#accountActive
#paymentMethodValid
#customerHasAccess
#orderCanBeCancelled
~~~

Với property Java, hãy giữ quy ước bean nhất quán. Ví dụ field boolean customerVerified có getter isCustomerVerified() và property name là customerVerified. Trong SpEL, truy cập property bằng customerVerified hoặc #customer.customerVerified tùy vị trí dữ liệu.

Tránh đặt một variable tên isCustomerVerified nếu model cũng có property customerVerified nhưng hai giá trị có nguồn khác nhau. Tên nên phản ánh nguồn và ý nghĩa của dữ liệu, không chỉ hình thức getter Java.

## 7. Đặt tên collection và phần tử

Tên collection nên dùng danh từ số nhiều hoặc tên tập hợp có nghĩa.

Ví dụ:

~~~text
#orders
#activeCustomers
#eligibleRegions
#blockedAccountIds
~~~

Trong selection và projection, predicate được đánh giá trên phần tử hiện tại. Có thể dùng #this để làm rõ:

~~~text
#orders.?[#this.status == 'PAID']
~~~

~~~text
#orders.![#this.orderNumber]
~~~

Khi collection có nhiều tầng, tên biến nên mô tả rõ từng tập hợp:

~~~text
#customers.![#this.orders.![orderNumber]]
~~~

Nếu expression phức tạp tới mức người đọc không biết #this đại diện object nào ở từng tầng, hãy chia logic thành các expression nhỏ hoặc chuẩn bị DTO trung gian có tên property rõ hơn.

Không dùng #items cho mọi loại collection khác nhau trong cùng một context. #orderItems, #approvedPayments và #shipmentEvents giúp người đọc nhận biết domain của dữ liệu.

## 8. Đặt tên root property theo domain

Root object thường là điểm bắt đầu của expression. Property của nó nên mô tả dữ liệu mà policy được phép đọc.

Ví dụ DTO:

~~~java
public record LoanEligibilityInput(
    BigDecimal requestedLoanAmount,
    BigDecimal annualIncome,
    int existingLoanCount,
    boolean identityVerified,
    String employmentType
) {}
~~~

Expression:

~~~text
identityVerified
    and requestedLoanAmount <= annualIncome * 3
    and existingLoanCount < 2
~~~

Các tên này có ý nghĩa cụ thể và phù hợp với domain cho vay.

Tránh property chung chung:

~~~java
public record Input(
    BigDecimal amount,
    BigDecimal value,
    boolean flag,
    String type
) {}
~~~

Với model như vậy, expression không thể tự giải thích ý nghĩa các field. Người đọc phải tìm code gọi để hiểu amount là khoản vay, thu nhập hay phí.

Root property cũng nên tránh nhúng quy tắc nghiệp vụ vào tên nếu quy tắc có thể thay đổi. Ví dụ eligibleForDiscount có thể phù hợp nếu đây là một kết quả đã được tính sẵn; nếu expression chính là nơi quyết định eligibility, tên input nên mô tả dữ liệu đầu vào như customerTier và orderTotal.

## 9. Phân biệt property root với variable cùng tên

Không nên đăng ký variable trùng tên với root property nếu hai giá trị có ý nghĩa khác nhau.

Ví dụ gây nhầm lẫn:

~~~java
context.setVariable("status", "APPROVED");
~~~

Trong khi root object cũng có property status.

Expression:

~~~text
status == 'APPROVED' and #status == 'APPROVED'
~~~

Người đọc phải biết status không tiền tố lấy từ root, còn #status lấy từ variable. Nếu hai nguồn không giống nhau, expression rất dễ bị hiểu sai.

Cách tốt hơn là đặt tên thể hiện nguồn:

~~~text
orderStatus == 'PAID'
    and #requiredApprovalStatus == 'APPROVED'
~~~

Nếu có thể, tránh trùng tên hoàn toàn giữa root properties và variables. Khi cần giữ tên giống nhau do contract hiện có, dùng #root.property hoặc #variable một cách tường minh.

## 10. Dùng #root và #this đúng mục đích

#root luôn tham chiếu root object của EvaluationContext. #this tham chiếu object hiện tại tại vị trí expression đang được đánh giá.

Ví dụ:

~~~text
#orders.?[#this.total >= #root.minimumOrderTotal]
~~~

Trong selection:

- #this là Order hiện tại đang được xét.
- #root là root object của context, ở ví dụ này có thể chứa minimumOrderTotal.
- #root.minimumOrderTotal đọc ngưỡng từ root object.

Nếu ngưỡng được đăng ký thành variable:

~~~text
#orders.?[#this.total >= #minimumOrderTotal]
~~~

Cách thứ hai tách ngưỡng thành variable. Cả hai cách đều có thể đúng; hãy chọn một mô hình nhất quán và làm rõ nguồn dữ liệu.

Không dùng #this thay cho tên domain khi biểu thức có thể viết dễ hiểu hơn bằng property trực tiếp. Trong predicate lồng nhau, #this rất hữu ích để xác định receiver hiện tại.

## 11. Đặt tên giá trị tiền tệ, ngưỡng và đơn vị

Các giá trị số thường gây hiểu nhầm nếu tên không thể hiện đơn vị hoặc vai trò.

Tên mơ hồ:

~~~text
#limit
#amount
#rate
#time
~~~

Tên cụ thể hơn:

~~~text
#maximumOrderTotal
#requestedLoanAmount
#discountRate
#evaluationTime
~~~

Nếu giá trị mang đơn vị, có thể thể hiện đơn vị trong tên khi điều đó giúp tránh nhầm lẫn:

~~~text
#timeoutMillis
#distanceMeters
#maximumFileSizeBytes
~~~

Với tiền tệ, nếu hệ thống có nhiều currency, chỉ đặt amount là chưa đủ. Có thể dùng requestedAmount và currencyCode, hoặc một Money value object có amount và currency rõ ràng.

Không dùng tên như priceUsd nếu giá trị thực tế có thể là currency khác. Tên sai khiến expression dễ được đọc đúng về cú pháp nhưng sai về nghiệp vụ.

## 12. Đặt tên thời gian rõ ràng

Thời gian thường có nhiều khái niệm khác nhau: thời điểm hiện tại, ngày tạo, hạn chót, thời điểm hết hạn hoặc ngày nghiệp vụ.

Nên dùng tên như:

~~~text
#evaluationTime
#orderCreatedAt
#paymentDueAt
#subscriptionExpiresAt
~~~

Tránh tên now nếu expression có nhiều mốc thời gian. #now có thể chấp nhận trong expression nhỏ, nhưng evaluationTime nói rõ đây là thời điểm được dùng để đánh giá policy.

Nếu dùng LocalDate, Instant hoặc ZonedDateTime, hãy giữ kiểu nhất quán và quy định timezone ở tầng Java. Không đặt tên property là date nếu nó thực sự là timestamp có timezone.

## 13. Đặt tên biến theo vai trò trong expression

Một giá trị có thể có nhiều vai trò. Hãy đặt tên theo cách expression sử dụng nó.

Ví dụ:

~~~text
#actualOrderTotal >= #minimumOrderTotal
~~~

Rõ hơn:

~~~text
#value >= #threshold
~~~

Nếu có nhiều loại ngưỡng:

~~~text
#actualOrderTotal >= #minimumOrderTotal
    and #actualOrderTotal <= #maximumOrderTotal
~~~

Cặp actual/minimum/maximum cho biết quan hệ giữa các giá trị.

Tương tự, khi so sánh thời gian:

~~~text
#paymentReceivedAt <= #paymentDueAt
~~~

Tên cho thấy đâu là thời điểm thực tế và đâu là hạn chót.

Tránh các cặp tên gần giống nhau nhưng không thể hiện vai trò, ví dụ #amount1 và #amount2. Nếu hai giá trị là subtotal và taxAmount, hãy dùng đúng tên domain đó.

## 14. Naming contract giữa Java và SpEL

Tên variable và property được dùng trong expression là một phần của hợp đồng giữa code Java và cấu hình SpEL.

Ví dụ Java:

~~~java
context.setVariable("minimumOrderTotal", minimumOrderTotal);
context.setVariable("evaluationTime", clock.instant());
~~~

Expression:

~~~text
#order.total >= #minimumOrderTotal
    and #order.createdAt <= #evaluationTime
~~~

Nếu Java đổi tên variable thành minimumTotal mà không cập nhật expression, runtime sẽ không tìm thấy tên cũ.

Để giảm rủi ro:

- Tập trung việc đăng ký variable trong một builder/factory của context.
- Dùng constant cho tên variable nếu nhiều nơi cùng tham chiếu.
- Có test cho các expression đã lưu.
- Version hóa policy nếu đổi naming contract.
- Không rename public variable chỉ để đồng nhất style mà không kiểm tra các expression phụ thuộc.
- Khi cần thay tên, hỗ trợ migration hoặc alias trong một giai đoạn chuyển tiếp có kiểm soát.

Ví dụ constant:

~~~java
public final class PolicyVariables {
    public static final String MINIMUM_ORDER_TOTAL =
        "minimumOrderTotal";

    private PolicyVariables() {}
}
~~~

Sau đó dùng cùng constant khi setVariable. Expression vẫn dùng tên không có dấu # trong API Java và thêm # khi tham chiếu trong source SpEL.

## 15. Tránh đưa chi tiết triển khai vào tên

Tên nên mô tả domain hơn là cách dữ liệu được lưu trữ hoặc truyền tới expression.

Tên kém bền vững:

~~~text
#redisOrderValue
#databaseCustomerRow
#requestParameter1
#dtoFieldX
~~~

Tên bền vững hơn:

~~~text
#order
#customer
#requestedRegion
~~~

Nếu nguồn dữ liệu thay đổi từ Redis sang database, expression không cần đổi chỉ vì implementation thay đổi.

Tương tự, tránh tên dựa trên thứ tự hoặc vị trí như firstArg, secondArg, col3. Tên theo ý nghĩa nghiệp vụ ít bị ảnh hưởng khi cấu trúc code thay đổi.

## 16. Giữ expression ngắn và tự giải thích

Tên tốt giúp expression dễ đọc, nhưng không nên cố nhồi toàn bộ nghiệp vụ vào một dòng dài.

Ví dụ:

~~~text
#customer.verified
    and #customer.account.active
    and #order.total >= #minimumOrderTotal
    and #order.region in #eligibleRegions
    and #evaluationTime < #policyExpiresAt
~~~

Các tên có ý nghĩa giúp đọc điều kiện theo từng dòng. Nếu expression vẫn có quá nhiều tầng lồng nhau, hãy tạo một DTO đầu vào có property được đặt tên theo domain hoặc tách policy thành các bước.

Có thể chuẩn bị property đã được tính trước nếu đó là dữ liệu đầu vào hợp lệ, ví dụ customerVerified hoặc accountActive. Tuy nhiên, không nên đặt tên một field như policyPassed nếu expression cần tự đánh giá chính policy đó; tên có thể khiến người đọc nghĩ kết quả đã được xác minh ở nơi khác.

## 17. Ví dụ trước và sau khi cải thiện tên

### Ví dụ 1: Điều kiện đơn hàng

Trước:

~~~text
#a > #b and #c
~~~

Sau:

~~~text
#orderTotal >= #minimumOrderTotal
    and #customerVerified
~~~

### Ví dụ 2: Điều kiện tài khoản

Trước:

~~~text
status == 'ACTIVE' and #flag
~~~

Sau:

~~~text
accountStatus == 'ACTIVE'
    and #accountHasNoOutstandingDebt
~~~

### Ví dụ 3: Thời hạn thanh toán

Trước:

~~~text
#d1 <= #d2
~~~

Sau:

~~~text
#paymentReceivedAt <= #paymentDueAt
~~~

### Ví dụ 4: Selection trên collection

Trước:

~~~text
#items.?[value > 0]
~~~

Sau:

~~~text
#orderLines.?[#this.quantity > 0]
~~~

Tên orderLines và quantity cho biết collection chứa gì và điều kiện đang kiểm tra thuộc tính nào.

## 18. Ví dụ thiết kế context có tên rõ ràng

Có thể gom dữ liệu vào một input DTO và chỉ đăng ký một số variable độc lập:

~~~java
public record OrderEvaluationInput(
    String orderStatus,
    BigDecimal orderTotal,
    boolean customerVerified,
    Instant orderCreatedAt
) {}

public StandardEvaluationContext createContext(
        OrderEvaluationInput input,
        BigDecimal minimumOrderTotal,
        Instant evaluationTime) {

    StandardEvaluationContext context =
        new StandardEvaluationContext(input);

    context.setVariable(
        "minimumOrderTotal",
        minimumOrderTotal
    );

    context.setVariable(
        "evaluationTime",
        evaluationTime
    );

    return context;
}
~~~

Expression:

~~~text
orderStatus == 'PAID'
    and orderTotal >= #minimumOrderTotal
    and customerVerified
    and orderCreatedAt <= #evaluationTime
~~~

Root properties thuộc OrderEvaluationInput. Variables là ngưỡng và thời điểm đánh giá được cung cấp riêng. Ranh giới này giúp người đọc biết dữ liệu nào mô tả đối tượng đang xét và dữ liệu nào là tham số của policy.

## 19. Kiểm thử naming contract

Tên rõ ràng vẫn cần được kiểm tra với context thực tế. Một expression có thể parse thành công nhưng thất bại nếu Java đăng ký sai tên variable hoặc DTO đổi property.

Test nên xác nhận:

- Tất cả variable được expression tham chiếu đều được đăng ký.
- Root property có đúng tên và accessor.
- Không có variable trùng tên root property ngoài chủ ý.
- Kiểu dữ liệu của từng tên phù hợp với expression.
- Các expression lưu trong database vẫn tương thích với naming contract hiện tại.
- Khi đổi tên, migration hoặc version policy được kiểm tra.

Ví dụ:

~~~java
@Test
void evaluatesUsingNamedPolicyInputs() {
    OrderEvaluationInput input =
        new OrderEvaluationInput(
            "PAID",
            new BigDecimal("150.00"),
            true,
            Instant.parse("2026-01-01T10:00:00Z")
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext(input);

    context.setVariable(
        "minimumOrderTotal",
        new BigDecimal("100.00")
    );

    context.setVariable(
        "evaluationTime",
        Instant.parse("2026-01-02T10:00:00Z")
    );

    Expression expression = parser.parseExpression(
        "orderStatus == 'PAID' " +
        "and orderTotal >= #minimumOrderTotal " +
        "and customerVerified"
    );

    assertThat(expression.getValue(context, Boolean.class))
        .isTrue();
}
~~~

Test này xác nhận tên root property và variable trong expression khớp với context được tạo từ Java. Nếu expression được lưu ngoài source code, nên có bộ test chạy trên các policy đã publish.

## 20. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Variable không tìm thấy | Tên trong setVariable khác tên sau dấu # | Dùng naming contract chung và test context |
| Expression đọc nhầm dữ liệu | Root property và variable trùng tên | Đổi tên theo nguồn hoặc dùng #root.property tường minh |
| Expression khó hiểu | Tên như x, value, data hoặc flag | Đổi sang tên mô tả domain và vai trò |
| Boolean bị hiểu sai | Tên không cho biết trạng thái của đối tượng nào | Dùng customerVerified, accountActive, canApprove |
| Collection khó đọc | Dùng items cho nhiều loại tập hợp | Dùng orders, paymentMethods, shipmentEvents |
| Đổi tên Java làm policy cũ lỗi | Expression lưu ngoài source phụ thuộc tên cũ | Version hóa và migration naming contract |
| Root property không được đọc | Getter hoặc property name không khớp | Kiểm tra JavaBean accessor và DTO |
| #this gây nhầm trong nested selection | Có nhiều tầng collection | Dùng #this tường minh ở từng tầng hoặc tách expression |
| Tên chứa chi tiết hạ tầng | Expression phụ thuộc Redis/DB/request field | Đổi sang tên domain ổn định |
| Expression quá dài dù tên rõ | Quá nhiều điều kiện và tầng lồng nhau | Chia policy hoặc tạo DTO trung gian |

## 21. Checklist đặt tên trước khi đưa expression vào runtime

- [ ] Variable có mô tả ý nghĩa nghiệp vụ thay vì tên tạm không?
- [ ] Root property có phản ánh đúng domain và kiểu dữ liệu không?
- [ ] Đã phân biệt root property không tiền tố với variable có tiền tố # chưa?
- [ ] Tên Boolean có cho biết trạng thái hoặc quyền của đối tượng nào không?
- [ ] Tên collection có cho biết loại phần tử không?
- [ ] Giá trị tiền tệ, ngưỡng, thời gian và đơn vị có tên rõ ràng không?
- [ ] Có tránh tên một ký tự, viết tắt khó hiểu và tên theo vị trí không?
- [ ] Có tránh trùng tên giữa root property và variable không?
- [ ] #root và #this có được dùng rõ ràng trong expression lồng nhau không?
- [ ] Tên có ổn định khi implementation hoặc nguồn dữ liệu thay đổi không?
- [ ] Java context builder có dùng cùng naming contract với expression không?
- [ ] Đã test mọi variable và root property được tham chiếu chưa?
- [ ] Policy đã lưu có version hoặc migration khi naming contract thay đổi không?

## 22. Kết luận

Tên variable và root property là một phần của thiết kế expression, không chỉ là chi tiết trình bày. Dùng tên theo domain và vai trò giúp SpEL gần với một câu mô tả quy tắc: orderTotal, minimumOrderTotal, customerVerified và evaluationTime dễ hiểu hơn x, value hoặc flag. Hãy phân biệt property của root object với variable có tiền tố #, dùng #root và #this đúng ngữ cảnh, tránh trùng tên và giữ naming contract ổn định giữa Java với các expression đã lưu. Khi expression vẫn khó đọc, hãy cải thiện DTO hoặc chia logic thành các bước nhỏ thay vì kéo dài một biểu thức duy nhất.