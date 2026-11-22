# Không che giấu tác dụng phụ trong expression

Spring Expression Language (SpEL) cho phép đọc property, tính toán, gọi method, gọi function, tham chiếu bean và thậm chí gán giá trị. Vì vậy, một expression có thể làm nhiều việc hơn việc tạo ra một giá trị: nó có thể thay đổi trạng thái object, ghi dữ liệu hoặc kích hoạt hành động bên ngoài.

Trong thiết kế tốt, expression nên thể hiện rõ mục đích khai báo: đọc dữ liệu, kiểm tra điều kiện hoặc tính ra một kết quả. Các hành động có tác dụng phụ như lưu database, gửi email, trừ tiền, phát message hoặc cập nhật trạng thái nên được đặt trong service Java với luồng thực thi rõ ràng.

Không nên giấu hành động có tác dụng phụ trong một expression trông giống phép tính đơn giản. Expression có thể được đánh giá nhiều lần, chạy trên từng phần tử collection, được gọi trong annotation hoặc được thực thi lại khi có lỗi ở compiled mode. Nếu người đọc không nhận ra một method đang thay đổi trạng thái, ứng dụng rất dễ phát sinh hành động trùng lặp hoặc khó truy vết.

## 1. Side effect là gì?

Một phép tính được xem là có tác dụng phụ khi ngoài việc trả về kết quả, nó còn thay đổi trạng thái hoặc tạo tác động quan sát được bên ngoài lần tính toán đó.

Ví dụ các side effect thường gặp:

- Thay đổi field hoặc property của object.
- Ghi hoặc xóa dữ liệu trong database.
- Gửi email, SMS, webhook hoặc message lên broker.
- Thực hiện thanh toán, hoàn tiền hoặc cập nhật số dư.
- Ghi file, gọi API hoặc thay đổi hệ thống bên ngoài.
- Thay đổi trạng thái dùng chung, cache hoặc biến static.
- Phát event hoặc tạo audit record.

Một method có thể trả về boolean hoặc String nhưng vẫn tạo side effect. Kiểu trả về không cho biết method có thuần hay không.

Ví dụ:

~~~java
boolean isEligible(Order order) {
    auditService.recordEligibilityCheck(order.getId());
    return order.getTotal().compareTo(limit) >= 0;
}
~~~

Tên isEligible nghe như một phép kiểm tra chỉ đọc, nhưng method còn ghi audit record. Nếu expression gọi method này nhiều lần, audit record có thể được tạo nhiều lần.

Hãy xem xét hành vi thực tế của method và getter, không chỉ dựa vào tên gọi hoặc kiểu trả về.

## 2. Expression nên thể hiện phép đọc và phép tính

Một expression thuần thường có các đặc điểm:

- Đọc dữ liệu từ root object hoặc variables.
- Thực hiện phép so sánh, tính toán hoặc chuyển đổi không thay đổi trạng thái bên ngoài.
- Trả về cùng kết quả khi đầu vào không đổi.
- Không phụ thuộc vào thứ tự gọi trước đó hoặc trạng thái ẩn.
- Có thể đánh giá lại mà không tạo thêm hành động.

Ví dụ:

~~~text
#order.total >= #minimumTotal
~~~

Expression chỉ đọc total và so sánh với minimumTotal.

Một ví dụ tính toán:

~~~text
#order.subtotal * (1 + #taxRate)
~~~

Nếu các property được đọc không gây side effect, expression chỉ tạo ra giá trị mới.

Ngược lại, expression sau có thể thay đổi trạng thái:

~~~text
#order.status = 'APPROVED'
~~~

Hoặc:

~~~text
@paymentService.charge(#order.account, #order.total)
~~~

Hai expression này thực hiện hành động. Chúng cần được nhận diện là command hoặc thao tác thay đổi trạng thái, không nên đặt lẫn vào một biểu thức chỉ nhằm hiển thị hoặc kiểm tra điều kiện.

## 3. Method invocation có thể tạo side effect

SpEL cho phép gọi method trên object:

~~~text
#order.calculateTotal()
~~~

hoặc gọi method trên Spring bean:

~~~text
@orderService.approve(#order)
~~~

SpEL không tự phân biệt method thuần với method có side effect. Nó gọi method theo khả năng truy cập được cấu hình trong EvaluationContext.

Method thuần có thể phù hợp:

~~~java
public BigDecimal calculateTax(BigDecimal subtotal, BigDecimal rate) {
    return subtotal.multiply(rate);
}
~~~

Method có tác dụng phụ:

~~~java
public void approve(Order order) {
    order.setStatus(OrderStatus.APPROVED);
    orderRepository.save(order);
    eventPublisher.publishEvent(new OrderApproved(order.getId()));
}
~~~

Nếu cần đánh giá một điều kiện, hãy dùng method chỉ đọc như canApprove(order). Sau khi điều kiện được xác nhận, gọi approve(order) từ service hoặc application workflow.

Không nên dùng method có side effect trong key, condition, message template hoặc một expression có thể được đánh giá lại mà người gọi không nhận ra.

## 4. Getter cũng có thể có side effect

Property access trong SpEL thường đi qua PropertyAccessor và có thể gọi getter Java. Một getter không nhất thiết là thao tác đọc thuần.

Ví dụ:

~~~java
public Customer getCustomer() {
    accessCounter++;
    return customerRepository.load(customerId);
}
~~~

Expression:

~~~text
#order.customer.name
~~~

có thể gọi getCustomer() trong lúc truy cập property. Nếu getter truy vấn repository hoặc thay đổi accessCounter, việc đọc property đã tạo tác động.

Các trường hợp cần chú ý:

- Getter kích hoạt lazy loading của ORM.
- Getter truy vấn database hoặc gọi API.
- Getter cập nhật cache hoặc trạng thái nội bộ.
- Getter ghi log/audit theo từng lần gọi.
- Getter tính toán đắt tiền hoặc có kết quả thay đổi theo thời gian.

Hãy giữ getter đơn giản và dự đoán được. Đặt truy vấn, cập nhật và phối hợp hệ thống trong method service có tên thể hiện rõ hành động.

Nếu expression cần dữ liệu đã được tải, hãy chuẩn bị DTO hoặc view model trong Java rồi truyền vào EvaluationContext.

## 5. Function được đăng ký cũng không tự động là pure

SpEL cho phép đăng ký Java Method thành function:

~~~java
context.registerFunction("normalizeCode", normalizeMethod);
~~~

Expression gọi function bằng cú pháp:

~~~text
#normalizeCode(#rawCode)
~~~

Function thường phù hợp với các phép biến đổi thuần như chuẩn hóa chuỗi, kiểm tra định dạng hoặc tính toán. Tuy nhiên, việc đăng ký dưới dạng function không bảo đảm method không có side effect.

Ví dụ function không nên dùng trong expression có thể đánh giá lặp lại:

~~~java
public static boolean sendReminder(Order order) {
    mailClient.send(order.getCustomerEmail(), "Reminder");
    return true;
}
~~~

Expression:

~~~text
#sendReminder(#order)
~~~

Tên function và kiểu trả về boolean không làm hành động gửi email trở thành an toàn khi evaluate nhiều lần.

Chỉ đăng ký các function có hành vi phù hợp với mục đích expression. Nếu cần hành động, hãy gọi một service method tại điểm điều phối rõ ràng.

## 6. Bean reference không làm method trở nên an toàn

Bean reference dùng cú pháp:

~~~text
@beanName
~~~

Ví dụ:

~~~text
@pricingService.calculate(#order)
~~~

Bean được Spring quản lý có thể chứa repository, client hoặc các dependency có side effect. Việc method được gọi qua bean reference không thay đổi ngữ nghĩa của method và không tự tạo transaction boundary cho expression.

Nếu bean được trả về là Spring proxy, method invocation có thể đi qua proxy theo cấu hình của ứng dụng. Nhưng SpEL không tự mở transaction, không bảo đảm retry an toàn và không quản lý workflow nghiệp vụ.

Hãy chỉ gọi bean method trong expression khi method có hành vi phù hợp, thường là phép đọc hoặc tính toán. Đặt các lệnh ghi và hành động bên ngoài expression.

## 7. Assignment là một side effect rõ ràng

SpEL hỗ trợ assignment trong các context cho phép ghi:

~~~text
#customer.name = 'Linh'
~~~

Hoặc gán property của root object:

~~~text
status = 'APPROVED'
~~~

Assignment thay đổi object được đánh giá. Đây là side effect trực tiếp và có thể ảnh hưởng đến những đoạn expression tiếp theo hoặc các thành phần khác đang giữ cùng reference.

Một số context giới hạn khả năng ghi, chẳng hạn SimpleEvaluationContext được cấu hình read-only. Tuy nhiên, việc dùng context read-only không bảo đảm mọi method được gọi đều thuần; method hoặc getter vẫn có thể tạo side effect riêng.

Nếu mục tiêu là cập nhật object theo dữ liệu đầu vào, hãy cân nhắc thực hiện bằng Java setter hoặc mapper trong một bước có tên rõ ràng. Dùng SpEL assignment khi data binding là mục tiêu được dự kiến và phạm vi ghi được kiểm soát.

## 8. Selection và projection có thể gọi logic nhiều lần

SpEL có các operator collection:

- **Selection** .?[...] lọc phần tử theo điều kiện.
- **Projection** .![...] biến đổi từng phần tử thành kết quả mới.

Ví dụ:

~~~text
#orders.?[total >= #minimumTotal]
~~~

Điều kiện được đánh giá trên từng phần tử được kiểm tra.

Projection:

~~~text
#orders.![#formatter.format(#this)]
~~~

Expression trong projection được đánh giá cho từng phần tử.

Nếu method bên trong điều kiện hoặc projection có side effect, nó có thể được gọi nhiều lần:

~~~text
#orders.?[@auditService.recordAndCheck(#this)]
~~~

Với một collection có N phần tử, method có thể được gọi đến N lần trong một lần evaluate. Nếu expression được đánh giá thêm lần nữa, số lần gọi có thể tăng tiếp.

Không nên dùng selection/projection để gửi thông báo, ghi audit, lưu dữ liệu hoặc thay đổi trạng thái. Hãy dùng chúng cho lọc và biến đổi giá trị; thực hiện hành động bằng vòng lặp/service Java khi đã xác định rõ phần tử và chính sách xử lý.

## 9. Short-circuit và nhánh điều kiện

Một số operator logic của SpEL có hành vi short-circuit. Với and, nếu vế trái là false thì vế phải không cần được đánh giá. Với or, nếu vế trái là true thì vế phải không cần được đánh giá. Toán tử ternary chỉ đánh giá nhánh được chọn.

Ví dụ:

~~~text
#order != null and #order.total > #minimumTotal
~~~

Nếu order là null, vế phải không được đánh giá.

Tuy nhiên, không nên dựa vào short-circuit để giấu side effect trong một nhánh:

~~~text
#shouldNotify and @notificationService.send(#order)
~~~

Khi shouldNotify là true, method gửi thông báo được gọi. Khi điều kiện thay đổi hoặc expression được evaluate lại, hành động có thể được gọi lần nữa.

Điều kiện logic nên chỉ đọc dữ liệu. Hãy đặt hành động sau khi điều kiện được tính trong Java:

~~~java
if (expression.getValue(context, Boolean.class)) {
    notificationService.send(order);
}
~~~

Cách này làm rõ thời điểm gửi thông báo và giúp áp dụng transaction, retry hoặc idempotency theo chính sách của ứng dụng.

## 10. Một expression có thể được đánh giá nhiều lần

Parse Expression một lần không có nghĩa kết quả chỉ được tính một lần.

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("#order.total > #minimumTotal");

Boolean first = expression.getValue(context, Boolean.class);
Boolean second = expression.getValue(context, Boolean.class);
~~~

Hai lời gọi getValue() là hai lần đánh giá riêng. Nếu expression gọi method có side effect, method đó có thể được gọi trong cả hai lần.

Expression cũng có thể được gọi nhiều lần bởi:

- Nhiều request hoặc nhiều message.
- Vòng lặp trong application code.
- Framework integration point.
- Cơ chế kiểm tra condition, key hoặc metadata.
- Logic retry ở tầng ứng dụng.
- Việc tạo lại giá trị hiển thị hoặc log.

Không nên giả định framework chỉ evaluate expression một lần nếu hợp đồng API không cam kết điều đó. Hãy thiết kế expression sao cho việc đánh giá lại không làm thay đổi trạng thái.

## 11. Annotation và integration point cũng có thể đánh giá expression

SpEL xuất hiện trong nhiều annotation và integration point của Spring, chẳng hạn @Value, @Cacheable, @PreAuthorize hoặc các cấu hình khác.

Expression trong các vị trí này thường được dùng để đọc tham số, tạo key, xác định condition hoặc kiểm tra quyền. Nếu nhúng hành động vào đó, hành động có thể được gọi vào thời điểm framework đánh giá expression, có thể khác với thời điểm người đọc source code dự đoán.

Ví dụ không nên dùng trong cache key:

~~~java
@Cacheable(
    cacheNames = "orders",
    key = "@auditService.recordAndReturnKey(#orderId)"
)
public Order findOrder(String orderId) {
    // ...
}
~~~

Việc tạo cache key có thể gọi method ghi audit. Key computation nên là phép tính thuần và xác định.

Tương tự, expression dùng trong security condition nên chỉ kiểm tra quyền. Không đặt thao tác cập nhật hoặc gửi thông báo trong @PreAuthorize.

## 12. MIXED compiler mode và nguy cơ chạy lại side effect

SpEL compiler có các mode OFF, IMMEDIATE và MIXED. Trong MIXED mode, nếu compiled evaluation thất bại, SpEL có thể quay về interpreter và đánh giá lại expression.

Điều này có thể gây rủi ro nếu compiled expression đã thực hiện một phần hành động trước khi lỗi xảy ra.

Ví dụ expression:

~~~text
@paymentService.charge(#account, #amount) + #payload.value
~~~

Giả sử lời gọi charge đã thực hiện giao dịch, sau đó phần truy cập payload.value thất bại trong compiled form. Khi MIXED quay về interpreter và đánh giá lại, method charge có thể được gọi lần nữa.

Vì vậy:

- Không đặt side effect trong expression dùng MIXED mode.
- Ưu tiên expression chỉ đọc và tính toán.
- Nếu phải gọi hành động, hãy thực hiện ngoài expression tại một điểm điều phối rõ ràng.
- Không dựa vào việc đổi sang IMMEDIATE như biện pháp thay thế cho thiết kế idempotent; lỗi vẫn có thể xảy ra sau khi hành động đã bắt đầu.
- Kiểm tra cấu hình compiler của parser hoặc integration point đang dùng.

Chi tiết compiler và fallback phụ thuộc phiên bản Spring. Hãy đối chiếu tài liệu của phiên bản ứng dụng khi chọn mode.

## 13. Tách decision khỏi command

Một cách thiết kế dễ hiểu là tách hai bước:

1. **Decision:** expression chỉ trả lời có nên thực hiện hành động hay không.
2. **Command:** Java service thực hiện hành động sau khi quyết định được xác nhận.

Ví dụ:

~~~java
Expression canApprove =
        parser.parseExpression(
                "#order.total <= #approvalLimit"
                + " and #order.customer.active"
        );

boolean approvedByRule = Boolean.TRUE.equals(
        canApprove.getValue(context, Boolean.class)
);

if (approvedByRule) {
    approvalService.approve(order);
}
~~~

Expression chỉ đánh giá quy tắc. Service approve thực hiện cập nhật trạng thái, lưu database và phát event theo transaction hoặc workflow của ứng dụng.

Cách tách này giúp:

- Người đọc thấy rõ đâu là điều kiện, đâu là hành động.
- Test expression không cần gọi database hoặc hệ thống bên ngoài.
- Test service có thể xác minh transaction, event và side effect riêng.
- Có thể thay đổi rule mà không thay đổi quy trình thực thi command.

## 14. Dùng function thuần và formatter cho các phép biến đổi

Nếu cần tái sử dụng logic trong expression, ưu tiên function hoặc bean method có tính thuần:

~~~java
public static String normalizeCode(String value) {
    return value == null ? null : value.trim().toUpperCase(Locale.ROOT);
}
~~~

Expression:

~~~text
#normalizeCode(#rawCode) == #expectedCode
~~~

Formatter cũng có thể phù hợp nếu chỉ chuyển đổi một giá trị thành chuỗi:

~~~text
@priceFormatter.format(#order.total, #locale)
~~~

Tuy nhiên, cần xác nhận formatter không ghi dữ liệu hoặc gọi hệ thống ngoài. Một method tên format vẫn có thể có side effect nếu implementation làm nhiều việc hơn dự kiến.

Đặt tên method phản ánh hành vi thực tế. Nếu method thay đổi trạng thái, dùng động từ thể hiện hành động như approve, send, charge hoặc persist và gọi nó ở tầng service.

## 15. Idempotency và xử lý retry cho hành động

Có những workflow buộc phải retry, ví dụ gửi message hoặc gọi payment gateway. Trong trường hợp đó, không nên dựa vào SpEL expression để quản lý retry.

Hãy đặt idempotency ở service hoặc integration layer:

~~~java
paymentService.charge(
        account,
        amount,
        idempotencyKey
);
~~~

Service dùng idempotency key để nhận diện cùng một yêu cầu nghiệp vụ và ngăn giao dịch bị thực hiện nhiều lần theo hợp đồng của payment provider hoặc cơ chế lưu trạng thái nội bộ.

Các nguyên tắc:

- Tạo idempotency key ổn định cho cùng một command nghiệp vụ.
- Lưu trạng thái xử lý và kết quả theo chính sách của hệ thống.
- Phân biệt lỗi trước khi gửi request với lỗi không rõ kết quả sau khi gửi.
- Không tự động retry một thao tác không idempotent nếu chưa biết lần trước đã thành công hay chưa.
- Dùng outbox hoặc cơ chế phát event tin cậy khi cần đồng bộ database và message broker.

SpEL nên quyết định điều kiện hoặc tạo dữ liệu cần thiết. Service chuyên trách mới là nơi quản lý retry, transaction và idempotency.

## 16. Side effect và transaction boundary

Gọi method trên bean từ SpEL không tự động tạo transaction boundary. Transaction phụ thuộc vào cấu hình Spring transaction và cách method được gọi qua proxy.

Nếu bean reference trả về một Spring proxy, lời gọi có thể đi qua transaction interceptor theo cấu hình. Nhưng không nên suy luận rằng mọi expression đều chạy trong transaction chỉ vì method đích có @Transactional.

Hãy kiểm tra:

- Bean được resolve có phải proxy phù hợp không.
- Method được gọi có nằm trong transaction boundary dự kiến không.
- Lỗi có được propagate để transaction rollback không.
- Side effect bên ngoài database có được phối hợp với transaction không.
- Retry có thể thực hiện lại hành động sau khi transaction đã commit hoặc rollback không.

Đối với thao tác nghiệp vụ, gọi service trực tiếp từ application service thường làm transaction boundary rõ hơn so với nhúng lời gọi vào expression.

## 17. Kiểm thử side effect

Một bài test cần xác nhận không chỉ giá trị trả về mà còn số lần hành động được gọi.

Ví dụ với Mockito:

~~~java
@Test
void decisionExpressionDoesNotSendNotification() {
    NotificationService notificationService =
            mock(NotificationService.class);

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("order", order);
    context.setVariable("minimumTotal", new BigDecimal("100.00"));

    Expression expression = parser.parseExpression(
            "#order.total >= #minimumTotal"
    );

    Boolean result = expression.getValue(context, Boolean.class);

    assertEquals(Boolean.TRUE, result);
    verifyNoInteractions(notificationService);
}
~~~

Nếu expression cần gọi một method chỉ đọc, có thể verify method đó được gọi với số lần dự kiến. Nếu expression có collection operation, hãy xác nhận số lần method được gọi tương ứng với số phần tử và số lần evaluate.

Với command service, test riêng:

~~~java
@Test
void approvesOrderOnlyWhenRulePasses() {
    when(ruleEvaluator.canApprove(order)).thenReturn(true);

    applicationService.process(order);

    verify(approvalService, times(1)).approve(order);
}
~~~

Các tình huống nên kiểm tra:

- Gọi getValue() một lần và nhiều lần.
- Collection rỗng, một phần tử và nhiều phần tử.
- Điều kiện short-circuit và nhánh ternary.
- Method ném exception trước hoặc sau khi thay đổi trạng thái.
- Retry ở application layer.
- MIXED compiler mode nếu expression được dùng trong mode này.
- Idempotency khi command được gửi lại.

Dùng mock hoặc fake cho email, payment, broker và repository để test không thực hiện tác động production thật.

## 18. Cách nhận diện side effect bị che giấu

Khi đọc một expression hoặc method mà expression gọi, hãy tự hỏi:

1. Property access có gọi getter truy vấn dữ liệu hoặc thay đổi trạng thái không?
2. Method có ghi database, phát event hoặc gọi API không?
3. Function đã đăng ký có thực sự thuần không?
4. Bean reference đang gọi một query method hay command method?
5. Expression có được dùng trong selection/projection và do đó chạy trên nhiều phần tử không?
6. Framework có thể đánh giá expression nhiều lần không?
7. Có retry hoặc compiler fallback nào có thể chạy lại một phần expression không?
8. Kết quả có phụ thuộc vào thời gian, random, trạng thái dùng chung hoặc thứ tự gọi không?
9. Nếu expression thất bại giữa chừng, hành động nào đã xảy ra?
10. Có thể tách decision và command thành hai bước rõ ràng không?

Tên method, comment hoặc kiểu trả về không đủ để kết luận. Cần xem implementation và các dependency mà method sử dụng.

## 19. Những lỗi thiết kế thường gặp

- **Gọi command trong condition:** condition được đánh giá lại có thể lặp hành động.
- **Gửi email trong projection:** mỗi phần tử có thể kích hoạt một email.
- **Ghi audit trong getter:** property access lặp lại có thể tạo nhiều record.
- **Cập nhật trạng thái bằng assignment ẩn:** người đọc tưởng expression chỉ tính giá trị.
- **Dùng bean reference để điều phối workflow:** expression che giấu transaction và thứ tự hành động.
- **Đặt hành động trong cache key:** việc tính key có thể phát sinh side effect.
- **Dùng function có tên như phép kiểm tra nhưng thực tế ghi dữ liệu:** tên gây hiểu nhầm về hành vi.
- **Dựa vào short-circuit để kiểm soát command:** thay đổi điều kiện có thể làm hành động bắt đầu.
- **Cho rằng parse một lần nghĩa là evaluate một lần:** mỗi getValue() vẫn thực thi lại expression.
- **Bỏ qua MIXED fallback:** compiled failure có thể khiến một phần expression được chạy lại.
- **Không có idempotency cho command có retry:** một yêu cầu có thể tạo nhiều tác động.

## 20. Ghi nhớ nhanh

- SpEL có thể gọi method, function, bean và setter; các thao tác này có thể tạo side effect.
- Getter cũng có thể truy vấn database, kích hoạt lazy loading hoặc thay đổi trạng thái.
- Ưu tiên expression thuần để đọc dữ liệu, kiểm tra điều kiện và tính toán.
- Không đặt thanh toán, gửi thông báo, ghi database hoặc phát event trong expression dùng cho condition, key, template hoặc collection operation.
- Selection và projection có thể đánh giá expression cho từng phần tử.
- Một Expression đã parse có thể được evaluate nhiều lần; parse một lần không có nghĩa chạy một lần.
- Short-circuit và ternary chỉ điều khiển nhánh được đánh giá, không bảo đảm hành động bên trong nhánh sẽ chỉ chạy một lần.
- Assignment trong SpEL có thể thay đổi object nếu context cho phép ghi.
- MIXED compiler mode có thể quay về interpreter sau compiled failure và làm một phần expression được đánh giá lại.
- Tách decision expression khỏi command service.
- Để transaction, retry và idempotency trong application/service layer.
- Kiểm thử cả giá trị trả về lẫn số lần side effect xảy ra.

## 21. Tài liệu tham khảo chính thức

- [Spring Framework — SpEL Evaluation and EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework — Method Invocation](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework — Variables and Functions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework — Collection Selection and Projection](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/collection-selection.html)
- [Spring Framework — SpEL Compilation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
