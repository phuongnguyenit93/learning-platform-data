# Gọi method không tham số và có tham số

SpEL cho phép gọi method trên đối tượng gốc, đối tượng lồng nhau, biến hoặc bean mà EvaluationContext cung cấp. Cú pháp gọi method có dấu ngoặc tròn sau tên method. Nếu method không nhận tham số, dùng cặp ngoặc rỗng; nếu method có tham số, đặt các đối số theo đúng thứ tự bên trong ngoặc.

Khả năng gọi method giúp biểu thức không chỉ đọc property mà còn sử dụng hành vi do object công khai. Tuy nhiên, method call có thể thực hiện logic phức tạp hoặc thay đổi trạng thái. Vì vậy, hãy hiểu cách SpEL phân giải method và chọn những method phù hợp để biểu thức dễ dự đoán, dễ kiểm soát.

## 1. Cú pháp gọi method cơ bản

Cú pháp tổng quát:

~~~text
methodName()
methodName(argument1)
methodName(argument1, argument2)
object.methodName()
object.methodName(argument1, argument2)
~~~

Dấu ngoặc là phần bắt buộc để thể hiện một lời gọi method. Không có tham số thì vẫn phải viết cặp ngoặc rỗng.

Ví dụ:

~~~text
name.toUpperCase()
name.substring(0, 3)
items.size()
items.get(0)
~~~

Các biểu thức trên lần lượt gọi method trên một chuỗi hoặc collection. Kết quả của method trở thành giá trị của biểu thức và có thể được dùng tiếp trong phép nối chuỗi, so sánh, tính toán hoặc lời gọi method khác.

Phân biệt property access với method invocation:

~~~text
customer.displayName
customer.getDisplayName()
~~~

Biểu thức thứ nhất truy cập property displayName thông qua property accessor. Biểu thức thứ hai gọi method getDisplayName() một cách tường minh. Cả hai có thể trả về cùng dữ liệu, nhưng cách viết thể hiện hai thao tác khác nhau.

## 2. Gọi method không tham số trên root object

Khi một EvaluationContext có root object, có thể gọi trực tiếp method của root object mà không cần viết tên biến hay tiền tố đặc biệt.

Giả sử có lớp Profile:

~~~java
public class Profile {

    private final String displayName;

    public Profile(String displayName) {
        this.displayName = displayName;
    }

    public String greeting() {
        return "Xin chào " + displayName;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

Có thể phân tích và đánh giá lời gọi greeting():

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile("Lan");

EvaluationContext context =
        new StandardEvaluationContext(profile);

Expression expression = parser.parseExpression("greeting()");

String message = expression.getValue(context, String.class);

System.out.println(message); // Xin chào Lan
~~~

Trong ví dụ này, profile là root object. Khi SpEL gặp greeting(), method resolver tìm method phù hợp trên root object và gọi nó. Không cần viết profile.greeting() vì chính profile đã là đối tượng gốc của context.

Nếu context được tạo mà không có root object, lời gọi method không có đối tượng đích sẽ không thể phân giải theo cách trên. Khi đó cần đặt root object hoặc gọi method thông qua một biến, property hay bean đã được cung cấp.

## 3. Gọi method có một hoặc nhiều tham số

Đối số được viết trong cặp ngoặc, phân tách bằng dấu phẩy. SpEL hỗ trợ truyền literal, biến, property hoặc kết quả của một biểu thức khác làm tham số.

Giả sử Profile có thêm method:

~~~java
public String greet(String name) {
    return "Xin chào " + name;
}

public String formatName(String prefix, String suffix) {
    return prefix + displayName + suffix;
}
~~~

Có thể gọi như sau:

~~~java
Expression greet = parser.parseExpression("greet('Minh')");
String first = greet.getValue(context, String.class);

Expression format = parser.parseExpression(
        "formatName('Mr. ', ' Nguyen')"
);
String second = format.getValue(context, String.class);
~~~

Trong SpEL, string literal được đặt trong dấu nháy đơn. Literal số có thể viết trực tiếp không cần dấu nháy; Boolean dùng true hoặc false; giá trị null dùng null.

Ví dụ:

~~~text
calculate(10, 20)
setEnabled(true)
findByCode('SP-100')
combine('Spring', 6)
~~~

Số lượng và thứ tự đối số phải phù hợp với method được chọn. Nếu method yêu cầu hai tham số thì lời gọi phải cung cấp hai đối số, trừ trường hợp method có khai báo varargs hoặc có một overload khác phù hợp.

## 4. Truyền biến làm đối số

Không cần nhúng dữ liệu động vào chuỗi biểu thức. Có thể đặt giá trị vào EvaluationContext dưới dạng biến rồi tham chiếu bằng tiền tố #.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Profile profile = new Profile("Lan");
StandardEvaluationContext context =
        new StandardEvaluationContext(profile);

context.setVariable("targetName", "Minh");

Expression expression =
        parser.parseExpression("greet(#targetName)");

String message = expression.getValue(context, String.class);
~~~

Biến #targetName được lấy từ context và truyền làm đối số cho greet(String). Cách này hữu ích khi biểu thức được lưu trong cấu hình nhưng giá trị thực tế thay đổi theo request hoặc theo dữ liệu nghiệp vụ.

Có thể truyền nhiều biến:

~~~java
context.setVariable("prefix", "Hello ");
context.setVariable("suffix", "!");

Expression expression = parser.parseExpression(
        "formatName(#prefix, #suffix)"
);
~~~

Hãy dùng tên biến có ý nghĩa và thống nhất giữa nơi cấu hình biến với nơi viết biểu thức. Nếu biến chưa được đăng ký hoặc tên bị sai, SpEL không thể phân giải đối số tương ứng.

## 5. Đối số có thể là một biểu thức khác

Mỗi đối số không chỉ là literal hoặc biến đơn giản. Nó có thể là một biểu thức tính toán hoặc truy cập property.

~~~text
calculate(price * quantity)
format(customer.firstName + ' ' + customer.lastName)
substring(0, name.length())
~~~

Ví dụ trong Java:

~~~java
Expression expression = parser.parseExpression(
        "calculate(#unitPrice * #quantity)"
);

context.setVariable("unitPrice", 19.5);
context.setVariable("quantity", 3);

Object result = expression.getValue(context);
~~~

SpEL đánh giá biểu thức đối số để lấy giá trị, sau đó dùng giá trị đó khi phân giải và gọi method. Nếu đối số chứa lời gọi method khác, lời gọi bên trong cần được đánh giá trước để tạo ra đối số cho lời gọi bên ngoài.

Với biểu thức nhiều tầng, hãy dùng khoảng trắng và xuống dòng trong chuỗi Java để người đọc nhận ra ranh giới từng đối số. Nếu logic tính đối số quá dài, nên chuẩn bị giá trị trong Java hoặc một biến context trước khi đánh giá.

## 6. Gọi method trên object lồng nhau

Nếu root object chứa các object con, có thể gọi method trên object con qua đường dẫn property:

~~~text
customer.getDisplayName()
customer.address.format()
order.calculateTotal()
order.customer.isActive()
~~~

Ví dụ:

~~~java
Expression expression = parser.parseExpression(
        "customer.getDisplayName()"
);

String name = expression.getValue(context, String.class);
~~~

SpEL trước tiên truy cập property customer trên root object, sau đó gọi getDisplayName() trên object được trả về. Mỗi mắt xích trong đường dẫn phải tồn tại và có thể truy cập.

Nếu customer là null, việc tiếp tục gọi method trên nó có thể phát sinh lỗi khi đánh giá. Hãy kiểm tra dữ liệu trước, thiết kế object graph có trạng thái rõ ràng hoặc dùng cơ chế null-safe phù hợp với phiên bản Spring đang sử dụng. Không nên dựa vào việc một object tình cờ không null trong dữ liệu mẫu.

## 7. Gọi method trên biến

Biến trong EvaluationContext có thể chứa object, không chỉ chứa chuỗi hoặc số. Khi biến là object, có thể gọi method của object đó qua cú pháp #variable.method(...).

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("text", "Spring Expression Language");

Expression expression = parser.parseExpression(
        "#text.toUpperCase()"
);

String result = expression.getValue(context, String.class);
~~~

Có thể gọi method có tham số trên cùng biến:

~~~text
#text.substring(0, 6)
#text.replace('Expression', 'EL')
~~~

Cách này hữu ích khi root object không nên chứa mọi dữ liệu đầu vào. Ứng dụng có thể đưa từng object cần thiết vào context dưới tên biến cụ thể, giúp biểu thức thể hiện rõ dữ liệu mà nó sử dụng.

## 8. Gọi static method

SpEL hỗ trợ gọi static method thông qua type reference T(...). Sau tên kiểu là dấu chấm và tên method, tiếp theo là các đối số nếu có.

~~~text
T(java.lang.Math).abs(-10)
T(java.lang.Math).max(12, 30)
T(java.lang.String).valueOf(123)
~~~

Ví dụ:

~~~java
Expression expression = parser.parseExpression(
        "T(java.lang.Math).max(12, 30)"
);

Integer result = expression.getValue(Integer.class);
~~~

T(...) yêu cầu SpEL phân giải được kiểu thông qua TypeLocator của EvaluationContext. Static method không được gọi trên root object vì nó thuộc về class, không phải instance.

Chỉ dùng static method cần thiết và có hành vi dễ hiểu. Nếu biểu thức không đáng tin cậy, khả năng tham chiếu kiểu và gọi static method cần được giới hạn bằng cấu hình context phù hợp.

## 9. Gọi method của Spring bean

Trong một ứng dụng Spring, biểu thức có thể gọi method trên bean bằng cú pháp @beanName.method(...), nếu EvaluationContext có BeanResolver tương ứng.

Ví dụ về cú pháp:

~~~text
@pricingService.calculateTotal(#order)
@featureFlags.isEnabled('new-checkout')
~~~

Với context tự tạo, có thể kết nối BeanFactory bằng BeanFactoryResolver:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setBeanResolver(
        new BeanFactoryResolver(beanFactory)
);
~~~

Sau khi cấu hình, biểu thức có thể phân giải bean theo tên. Việc bean đã tồn tại trong Spring container không có nghĩa mọi EvaluationContext đều tự động có thể truy cập bean đó. Khả năng này phụ thuộc resolver mà context được cấp.

Gọi bean từ SpEL có thể mở rộng phạm vi hành động của biểu thức vì bean có thể truy cập repository, dịch vụ hoặc hệ thống bên ngoài. Chỉ công khai bean và method thực sự cần cho use case; tránh biến expression thành một cách gọi tùy ý toàn bộ application service.

## 10. MethodResolver và cách chọn method phù hợp

Khi gặp lời gọi method, SpEL cần xác định method nào trên đối tượng đích phù hợp với tên method và các đối số. Công việc này được thực hiện thông qua MethodResolver của EvaluationContext.

StandardEvaluationContext mặc định có cơ chế phân giải method dựa trên reflection. Vì vậy, method công khai phù hợp trên object có thể được gọi nếu method resolver và kiểu đối số cho phép.

Ví dụ có hai overload:

~~~java
public String describe(String value) {
    return "text: " + value;
}

public String describe(Integer value) {
    return "number: " + value;
}
~~~

Các lời gọi có đối số kiểu chuỗi và số có thể chọn overload tương ứng:

~~~text
describe('42')
describe(42)
~~~

Việc chọn overload phụ thuộc kiểu thực tế của đối số và khả năng chuyển đổi kiểu. Nếu đối số là null hoặc có nhiều overload tương thích, kết quả phân giải có thể không rõ ràng hoặc không chọn được method như mong đợi.

Khi gặp lỗi overload:

1. Kiểm tra kiểu runtime của từng đối số.
2. Kiểm tra số lượng và thứ tự tham số.
3. Xem method có overload cùng tên hay không.
4. Kiểm tra TypeConverter nếu cần chuyển đổi kiểu.
5. Dùng tên method riêng biệt hoặc biến có kiểu rõ ràng nếu overload gây mơ hồ.

Đừng dựa vào việc một chuỗi số như '42' luôn được tự động hiểu là Integer. Trong SpEL, string literal vẫn là String cho đến khi cơ chế chuyển đổi phù hợp được áp dụng.

## 11. Method có varargs và tham số null

Java method có thể khai báo varargs, ví dụ:

~~~java
public String join(String separator, String... values) {
    return String.join(separator, values);
}
~~~

Khi gọi từ SpEL, cần cung cấp các đối số phù hợp với signature và khả năng phân giải method của phiên bản Spring đang dùng. Với varargs, hãy kiểm tra lời gọi trên đúng phiên bản ứng dụng thay vì giả định mọi cách truyền mảng hoặc danh sách đều được chuyển đổi giống nhau.

Tham số null cũng cần chú ý:

~~~text
findByCode(null)
~~~

Nếu có nhiều overload nhận các kiểu tham chiếu khác nhau, null không cho biết rõ overload nào được mong muốn. Hãy dùng method có tên riêng, truyền một biến có kiểu rõ ràng hoặc chuẩn hóa dữ liệu trước khi gọi.

## 12. SimpleEvaluationContext và giới hạn gọi method

StandardEvaluationContext hỗ trợ method invocation theo cấu hình mặc định rộng hơn. SimpleEvaluationContext được thiết kế cho một tập con SpEL hạn chế và không bật instance method invocation mặc định.

Nếu use case thực sự cần gọi instance method trong SimpleEvaluationContext, builder có thể bật rõ ràng bằng withInstanceMethods():

~~~java
EvaluationContext context =
        SimpleEvaluationContext
                .forReadOnlyDataBinding()
                .withInstanceMethods()
                .build();
~~~

Hãy chỉ bật khả năng này khi method invocation là yêu cầu rõ ràng. Context hạn chế không tự biến mọi method trên object thành an toàn; root object và các accessor vẫn cần được chọn cẩn thận.

Nếu chỉ cần đọc property để lọc hoặc hiển thị, hãy giữ context chỉ đọc và không bật method invocation. Nếu cần gọi method, hãy cung cấp object có API nhỏ, ổn định và không có side effect ngoài dự kiến.

## 13. Method call có thể tạo side effect

Gọi method không chỉ trả về một giá trị. Method có thể cập nhật object, ghi log, truy vấn database, gửi request hoặc thay đổi trạng thái hệ thống.

Ví dụ:

~~~text
account.withdraw(100)
notificationService.send(message)
repository.deleteById(#id)
~~~

Các biểu thức này có thể thực hiện hành động thay đổi trạng thái nếu context cho phép gọi method tương ứng. Vì vậy, không nên xem SpEL như một ngôn ngữ chỉ đọc.

Đặc biệt, khi biểu thức được đánh giá nhiều lần, method có side effect có thể bị gọi nhiều lần. Một biểu thức được dùng trong nhiều request hoặc trong một template có thể gây ra hành vi lặp lại nếu không kiểm soát lifecycle.

Nguyên tắc thực tế:

- Ưu tiên method thuần, chỉ tính toán và trả về kết quả.
- Không đưa repository hoặc service ghi dữ liệu vào context nếu không cần.
- Không đặt gửi email, thanh toán hoặc cập nhật trạng thái trong biểu thức cấu hình có thể được đánh giá lặp.
- Giữ quyền method ở mức tối thiểu bằng root object và resolver được chọn.
- Thực hiện hành động nghiệp vụ quan trọng trong Java/service flow, nơi có thể quản lý transaction, authorization và xử lý lỗi rõ ràng.

## 14. Kiểm tra lỗi khi gọi method

Một lời gọi method có thể thất bại ở nhiều bước khác nhau:

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Method không được tìm thấy | Sai tên hoặc method không thể truy cập | Kiểm tra tên, visibility và object đích |
| Sai số lượng đối số | Số tham số không khớp signature | Đối chiếu lời gọi với method Java |
| Không chọn được overload | Kiểu đối số mơ hồ hoặc null | Kiểm tra kiểu runtime và overload |
| Không chuyển được đối số | Không có converter phù hợp | Kiểm tra TypeConverter và kiểu tham số |
| Không gọi được method trên property con | Object trung gian null hoặc property không truy cập được | Kiểm tra từng mắt xích trong đường dẫn |
| Bean reference không hoạt động | Context chưa có BeanResolver | Kiểm tra cấu hình BeanFactoryResolver |
| Static method không phân giải được | TypeLocator không tìm thấy class | Kiểm tra tên class và TypeLocator |
| SimpleEvaluationContext từ chối method | Instance method invocation chưa được bật | Chỉ bật withInstanceMethods khi cần |

Khi debug, hãy tách việc parse khỏi việc evaluate. Parser có thể chấp nhận cú pháp gọi method nhưng đến khi getValue mới phát hiện không phân giải được method hoặc không chuyển được đối số.

## 15. Ghi nhớ

Method không tham số được gọi bằng tên method và cặp ngoặc rỗng, ví dụ greeting(). Method có tham số nhận các đối số theo thứ tự, ví dụ greet('Lan') hoặc calculate(#price, #quantity). Method có thể được gọi trên root object, object lồng nhau, biến hoặc bean được context cung cấp. Static method được gọi thông qua type reference T(...).

MethodResolver quyết định method nào phù hợp; TypeConverter có thể tham gia chuyển đổi đối số. StandardEvaluationContext hỗ trợ method invocation rộng hơn, trong khi SimpleEvaluationContext chỉ bật instance method khi được cấu hình rõ ràng. Hãy kiểm soát object và method được công khai, ưu tiên method thuần, và giữ các side effect quan trọng trong Java/service layer.