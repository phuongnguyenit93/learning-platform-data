# Truyền literal, property và expression làm đối số khi gọi method trong SpEL

Khi gọi method bằng Spring Expression Language (SpEL), mỗi đối số trong dấu ngoặc đơn có thể là một literal, một property hoặc một biểu thức khác. SpEL đánh giá từng đối số để lấy giá trị runtime, sau đó dùng cơ chế method resolution để tìm method phù hợp trên target object. Hiểu rõ các dạng đối số và kiểu dữ liệu của chúng giúp viết lời gọi ngắn gọn, tránh lỗi chuyển đổi kiểu và giữ cho biểu thức dễ kiểm tra.

## 1. Cú pháp gọi method và danh sách đối số

Cú pháp cơ bản là tên method theo sau bởi danh sách đối số phân tách bằng dấu phẩy:

    methodName(argument1, argument2, ...)

Method có thể được gọi trên root object, trên một property của root object hoặc trên một biến trong EvaluationContext.

Ví dụ gọi method trên root object:

    calculateDiscount('VIP', total, quantity)

Nếu root object có method `calculateDiscount`, SpEL sẽ tìm và gọi method đó. Trong ví dụ này:

- `'VIP'` là literal chuỗi.
- `total` là property của root object.
- `quantity` cũng là property của root object.

Khi gọi method trên biến, dùng dấu `#` để tham chiếu biến:

    #pricingService.quote('EXPRESS', #order.total)

Ở đây `pricingService` và `order` là các biến được đăng ký trong EvaluationContext. Dấu `#` phân biệt biến với property được tra cứu trên root object.

Thứ tự các đối số trong biểu thức tương ứng với thứ tự tham số của method được chọn. Số lượng và kiểu đối số phải phù hợp với một method có thể gọi được trên target.

## 2. Truyền literal làm đối số

Literal là giá trị được viết trực tiếp trong biểu thức. Các loại thường dùng gồm:

| Loại literal | Ví dụ | Giá trị truyền vào |
|---|---|---|
| Chuỗi | `'EXPRESS'` | String |
| Số nguyên | `10` | Literal số nguyên |
| Số nguyên Long | `10L` | Long |
| Số thực | `19.95` | Double |
| Boolean | `true`, `false` | Boolean |
| Null | `null` | null |

Ví dụ:

    #shippingService.calculate('EXPRESS', 10, true)

Lời gọi này truyền ba giá trị trực tiếp: tên dịch vụ vận chuyển, số lượng và cờ ưu tiên. Literal phù hợp khi giá trị cố định, ngắn và có ý nghĩa rõ ngay tại vị trí gọi.

Có thể truyền literal chuỗi chứa dấu nháy đơn bằng cách escape theo cú pháp chuỗi của SpEL. Khi chuỗi dài hoặc cần xử lý dữ liệu đầu vào, nên đưa giá trị vào context dưới dạng biến để tránh làm biểu thức khó đọc.

Không nên nhầm literal với tên property. `'status'` là chuỗi có nội dung status, còn `status` là truy cập property tên status trên target hiện tại.

## 3. Truyền property của root object làm đối số

Khi EvaluationContext có root object, có thể dùng trực tiếp tên property trong biểu thức để lấy giá trị từ root object:

    applyDiscount('MEMBER', subtotal, customer.level)

Giả sử root object là Order và có các property `subtotal` và `customer`. SpEL đọc giá trị của chúng rồi truyền vào method `applyDiscount`.

Nếu root object được tham chiếu thông qua biến, cú pháp là:

    #order.applyDiscount('MEMBER', #order.subtotal, #order.customer.level)

Cả hai cách đều hợp lệ trong đúng context tương ứng. Dùng property không có dấu `#` khi muốn đọc từ root object; dùng `#variable` khi giá trị được đăng ký như một biến.

Property lồng nhau có thể truyền làm đối số:

    #notificationService.send(
        #order.customer.name,
        #order.customer.email
    )

Các đường dẫn property được đánh giá trong lúc thực thi biểu thức. Nếu một object trung gian là null, việc đọc property tiếp theo có thể gây lỗi đánh giá. Có thể dùng safe navigation khi null là trường hợp được chấp nhận:

    #notificationService.send(
        #order.customer?.email
    )

Khi safe navigation trả về null, method nhận đối số null nếu kiểu tham số cho phép. Tham số primitive như `int` hoặc `boolean` không thể nhận null; cần xử lý giá trị thiếu trước khi gọi method.

## 4. Truyền một expression làm đối số

Đối số không chỉ là một giá trị đã có sẵn. Có thể đặt một biểu thức tính toán bên trong danh sách đối số. SpEL đánh giá biểu thức con rồi truyền kết quả cho method.

Ví dụ dùng phép toán số học:

    #pricingService.quote(
        #order.subtotal,
        #order.quantity * #order.unitPrice
    )

Đối số thứ hai là kết quả của phép nhân `quantity * unitPrice`, không phải một chuỗi biểu thức được truyền nguyên văn cho method.

Có thể dùng biểu thức điều kiện:

    #shippingService.calculate(
        #order.weight,
        #order.priority ? 'EXPRESS' : 'STANDARD'
    )

Toán tử điều kiện chọn một trong hai chuỗi dựa trên giá trị của property `priority`, sau đó truyền chuỗi được chọn vào method.

Một method call khác cũng có thể là đối số:

    #reportService.createSummary(
        #order,
        #order.items.size()
    )

Ở đây `#order.items.size()` là một lời gọi method lồng nhau. Kết quả số lượng phần tử được truyền vào method `createSummary`.

Khi biểu thức con dài, nên tách nó ra thành biến trong Java hoặc định dạng biểu thức nhiều dòng. Điều này giúp kiểm tra từng giá trị trung gian và tránh một lời gọi method quá khó đọc.

## 5. Kết hợp literal, property và expression trong một lời gọi

Có thể kết hợp nhiều loại đối số trong cùng một method call. Ví dụ, dịch vụ báo giá nhận loại khách hàng, giá trị đơn hàng, số lượng và mức giảm được tính từ dữ liệu:

    #pricingService.quote(
        'MEMBER',
        #order.subtotal,
        #order.items.size(),
        #order.subtotal * #discountRate
    )

Giả sử các biến `pricingService`, `order` và `discountRate` đã được đăng ký trong context. Lời gọi gồm:

1. Literal chuỗi `'MEMBER'`.
2. Property `#order.subtotal`.
3. Expression `#order.items.size()`.
4. Expression số học `#order.subtotal * #discountRate`.

Ví dụ Java minh họa cách chuẩn bị context:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("pricingService", pricingService);
    context.setVariable("order", order);
    context.setVariable("discountRate", new BigDecimal("0.05"));

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "#pricingService.quote(" +
            "'MEMBER', " +
            "#order.subtotal, " +
            "#order.items.size(), " +
            "#order.subtotal * #discountRate)"
    );

    Object quote = expression.getValue(context);

Cách này giữ dữ liệu nghiệp vụ trong Java object và chỉ mô tả cách kết hợp chúng trong SpEL. Nếu biểu thức được dùng nhiều lần, có thể parse Expression một lần rồi đánh giá với context phù hợp cho từng lần gọi.

## 6. Kiểu đối số và chuyển đổi khi gọi method

Method được khai báo với kiểu tham số cụ thể. SpEL phải tìm một method phù hợp với số lượng và kiểu của các đối số đã đánh giá.

Ví dụ, method:

    BigDecimal quote(String tier, BigDecimal amount)

cần một String và một BigDecimal. Nếu đối số thứ hai là một giá trị có kiểu tương thích, SpEL có thể chọn method đó. Khi cần, cơ chế chuyển đổi kiểu của EvaluationContext có thể chuyển đổi đối số sang kiểu tham số mà method yêu cầu.

StandardEvaluationContext mặc định dùng ReflectiveMethodResolver để phân giải method dựa trên reflection. Việc chọn method và chuyển đổi đối số phụ thuộc vào resolver cùng TypeConverter được cấu hình trong context.

Ví dụ, nếu method nhận Long, hãy truyền một giá trị Long rõ ràng khi có thể:

    #counterService.setLimit(100L)

Nếu giá trị nguồn là String, không nên dựa vào giả định rằng mọi chuỗi đều tự động chuyển thành kiểu số trong mọi context. Hãy parse và xác thực dữ liệu trước, hoặc cấu hình converter phù hợp và kiểm tra lỗi chuyển đổi.

Chuyển đổi kiểu không đồng nghĩa với validation nghiệp vụ. Một chuỗi có thể chuyển thành Integer thành công nhưng vẫn nằm ngoài giới hạn mà method chấp nhận. Method hoặc tầng ứng dụng vẫn cần kiểm tra các quy tắc liên quan.

## 7. Method overload và đối số có kiểu mơ hồ

Một class có thể khai báo nhiều method cùng tên nhưng khác kiểu tham số:

    String format(Integer value)
    String format(Long value)
    String format(String value)

Khi SpEL gọi method overload, ReflectiveMethodResolver cần chọn method phù hợp với các kiểu đối số thực tế. Nếu nhiều overload có thể nhận đối số sau chuyển đổi, lựa chọn có thể không khớp với ý định nghiệp vụ hoặc không phân giải được.

Để tránh mơ hồ:

- Chuẩn bị biến có kiểu cụ thể trong Java trước khi đánh giá.
- Dùng hậu tố literal như `L`, `F` hoặc `D` khi muốn chỉ rõ kiểu số.
- Chuyển đổi String sang kiểu đích một cách tường minh trước lời gọi.
- Tránh overload quá nhiều method cùng tên nếu chúng thường được gọi từ biểu thức động.
- Kiểm tra kiểu runtime của đối số và method thực tế được gọi trong các bài test.

Ví dụ, thay vì truyền một literal số nguyên khi method cần Long, có thể dùng:

    #counterService.setLimit(100L)

Hoặc chuẩn bị biến:

    context.setVariable("limit", Long.valueOf(100));
    #counterService.setLimit(#limit)

Cách thứ hai hữu ích khi giá trị được lấy từ nguồn dữ liệu bên ngoài hoặc cần kiểm tra trước khi gọi.

## 8. Đối số null và dữ liệu thiếu

Literal `null` hoặc một property trả về null đều có thể được dùng làm đối số nếu method chấp nhận giá trị null:

    #profileService.updateNickname(#user.nickname)

Nếu `nickname` là null và method nhận String, lời gọi có thể tiếp tục với đối số null. Nhưng nếu method nhận kiểu primitive, chẳng hạn `int`, null không thể chuyển thành giá trị hợp lệ.

Khi có nhiều overload nhận các kiểu tham chiếu khác nhau, null có thể khiến việc chọn method trở nên mơ hồ. Hãy chuẩn hóa giá trị hoặc gọi một method có chữ ký rõ ràng thay vì dựa vào lựa chọn overload trong trường hợp null.

Có thể dùng safe navigation để tránh lỗi khi một property trung gian không tồn tại:

    #profileService.updateEmail(#user.contact?.email)

Safe navigation chỉ xử lý đường dẫn truy cập null theo cú pháp được hỗ trợ. Nó không tự tạo giá trị thay thế và không bảo đảm method đích chấp nhận null. Nếu cần giá trị mặc định, hãy dùng toán tử điều kiện hoặc chuẩn bị biến trong Java.

## 9. Đối số varargs và danh sách tham số

Method Java có thể khai báo tham số varargs, ví dụ:

    void notifyUsers(String subject, String... recipients)

SpEL có thể gọi method varargs khi resolver tìm được chữ ký phù hợp. Khi biểu thức có nhiều đối số cuối, cần kiểm tra cách chúng khớp với mảng varargs và kiểu phần tử. Với lời gọi phức tạp, truyền sẵn một mảng hoặc collection có kiểu phù hợp từ Java có thể rõ ràng hơn.

Không nên nhầm một collection được truyền như một đối số với nhiều đối số riêng biệt. Ví dụ:

    #reportService.export(#order.items)

truyền một collection làm một đối số; còn:

    #reportService.notify('Ready', 'a@example.com', 'b@example.com')

là lời gọi có nhiều đối số cuối, có thể khớp với method varargs tương ứng.

Nếu method nhận một mảng, hãy kiểm tra kiểu mảng và kiểu phần tử. Nếu method nhận List, truyền collection phù hợp thay vì giả định SpEL tự chuyển mọi collection sang array hoặc ngược lại.

## 10. Debug và kiểm thử lời gọi method

Khi một lời gọi không hoạt động, nên kiểm tra theo thứ tự:

1. Target object có null không?
2. Tên method có đúng và method có thể truy cập trong context không?
3. Số lượng đối số có khớp với chữ ký method không?
4. Kiểu runtime của từng đối số là gì?
5. Có overload nào cạnh tranh hoặc gây mơ hồ không?
6. TypeConverter có hỗ trợ chuyển đổi cần thiết không?
7. Một property hoặc expression con có trả về null hoặc ném lỗi không?

Có thể kiểm tra kiểu của đối số trước khi đánh giá biểu thức:

    Object amount = context.lookupVariable("amount");

    System.out.println(amount);
    System.out.println(amount == null
            ? "null"
            : amount.getClass().getName());

Nên viết test riêng cho các trường hợp literal, property, expression lồng nhau, null, kiểu số khác nhau và overload. Với method có side effect, test cần xác nhận cả kết quả trả về lẫn thay đổi trên object hoặc service giả lập.

## 11. Giới hạn quyền khi gọi method qua SpEL

Method invocation có thể thực hiện logic nghiệp vụ, truy cập dữ liệu hoặc thay đổi trạng thái. Nếu biểu thức đến từ người dùng hoặc cấu hình không hoàn toàn tin cậy, hãy giới hạn những object và method có thể được truy cập.

SimpleEvaluationContext không bật instance method invocation mặc định; ứng dụng phải cấu hình rõ nếu cần khả năng này. StandardEvaluationContext cung cấp nhiều khả năng reflection hơn, vì vậy không nên đưa một service nhạy cảm vào context rồi cho phép biểu thức tùy ý gọi mọi method công khai.

Chỉ đưa vào context các service cần thiết cho use case. Ưu tiên các method có mục đích hẹp, tham số rõ ràng và ít side effect. Xác thực dữ liệu đầu vào trong Java hoặc trong tầng nghiệp vụ trước khi thực hiện thao tác quan trọng.

## 12. Ghi nhớ

Đối số method trong SpEL có thể là literal, property hoặc một expression được đánh giá tại thời điểm gọi. Dùng property trực tiếp khi lấy dữ liệu từ root object, và dùng `#variable` khi lấy dữ liệu từ EvaluationContext. Method resolver chọn method phù hợp với số lượng và kiểu đối số; TypeConverter có thể hỗ trợ chuyển đổi khi cần. Với overload, null, varargs hoặc dữ liệu đầu vào động, hãy làm rõ kiểu đối số và kiểm thử chữ ký method thực tế. Khi biểu thức có thể gọi service hoặc thay đổi trạng thái, hãy giới hạn context và chỉ cho phép những method mà use case cần.
