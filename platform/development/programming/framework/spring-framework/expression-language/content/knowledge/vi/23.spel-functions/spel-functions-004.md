# Truyền tham số cho function

## Mục tiêu

Sau bài này, bạn có thể đăng ký một hàm Java để gọi từ Spring Expression Language (SpEL); truyền literal, biến, property của root object và kết quả biểu thức làm đối số; hiểu cách kiểu tham số được ghép với chữ ký phương thức; và xử lý giá trị null, lỗi gọi hàm hoặc dữ liệu không hợp lệ. Bạn cũng sẽ biết cách dùng function trong điều kiện, selection và projection, phân biệt function với method invocation và bean reference, đồng thời giới hạn những hàm được phép gọi.

## 1. Function trong SpEL là gì?

Function là một phương thức Java được đăng ký trong EvaluationContext để biểu thức SpEL có thể gọi bằng tên. Cú pháp gọi function có dấu thăng trước tên và truyền các đối số trong ngoặc đơn:

~~~text
#functionName(argument1, argument2)
~~~

Ví dụ:

~~~text
#normalize('  Spring  ')
~~~

Biểu thức gọi function có tên normalize và truyền một chuỗi làm đối số. Giá trị trả về của phương thức trở thành kết quả của phần biểu thức đó.

Function phù hợp khi cần tái sử dụng một phép xử lý Java trong nhiều biểu thức, chẳng hạn chuẩn hóa chuỗi, kiểm tra mã, tính ngưỡng hoặc chuyển đổi một giá trị. SpEL không tự tìm mọi phương thức Java theo tên function. Ứng dụng phải đăng ký một đối tượng Method để gắn tên function với phương thức được phép gọi.

## 2. Function khác method invocation như thế nào?

SpEL có thể gọi phương thức trên một đối tượng mà không cần đăng ký function:

~~~text
#customer.getDisplayName()
~~~

Đây là method invocation trên object được lưu trong biến customer.

Function có cú pháp riêng:

~~~text
#formatName(#customer)
~~~

Ở đây formatName là tên function đã đăng ký trong EvaluationContext. Đối số #customer được truyền vào phương thức Java tương ứng.

Có thể phân biệt ba dạng:

| Cú pháp | Ý nghĩa |
|---|---|
| #normalize(#value) | Gọi function đã đăng ký trong context |
| #customer.normalize() | Gọi method trên object customer |
| @customerService.normalize(#value) | Lấy bean qua BeanResolver rồi gọi method của bean |

Function không phải bean và cũng không phải property. Dấu # cho biết SpEL tra cứu function trong namespace biến của EvaluationContext; dấu @ dùng để tham chiếu bean qua BeanResolver.

## 3. Đăng ký function bằng Method

Function được đăng ký bằng một đối tượng java.lang.reflect.Method. Phương thức dùng làm function thông thường phải là static, vì SpEL gọi trực tiếp Method mà không cần một instance receiver.

Ví dụ lớp tiện ích:

~~~java
public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        if (value == null) {
            return null;
        }
        return value.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

Đăng ký function trong StandardEvaluationContext:

~~~java
Method normalizeMethod =
    TextFunctions.class.getMethod("normalize", String.class);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.registerFunction("normalize", normalizeMethod);
~~~

Sau khi đăng ký, biểu thức có thể gọi:

~~~text
#normalize('  SPRING  ')
~~~

Kết quả là chuỗi đã được loại bỏ khoảng trắng ở hai đầu và chuyển thành chữ thường.

Dùng getMethod(...) để lấy một public method theo đúng tên và kiểu tham số. Nếu dùng getDeclaredMethod(...), cần chú ý quyền truy cập của phương thức; ưu tiên public static method để hành vi dễ dự đoán và tránh phải mở quyền truy cập reflection không cần thiết.

## 4. Ví dụ Java hoàn chỉnh

Ví dụ sau đăng ký function normalize, truyền một biến vào biểu thức và nhận kết quả:

~~~java
import java.lang.reflect.Method;
import java.util.Locale;

import org.springframework.expression.Expression;
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;

public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        if (value == null) {
            return null;
        }
        return value.trim().toLowerCase(Locale.ROOT);
    }
}

public class FunctionExample {

    public static void main(String[] args) throws Exception {
        Method method =
            TextFunctions.class.getMethod("normalize", String.class);

        StandardEvaluationContext context =
            new StandardEvaluationContext();

        context.registerFunction("normalize", method);
        context.setVariable("input", "  SPRING  ");

        ExpressionParser parser = new SpelExpressionParser();
        Expression expression =
            parser.parseExpression("#normalize(#input)");

        String result =
            expression.getValue(context, String.class);

        System.out.println(result); // spring
    }
}
~~~

Các bước chính:

1. Lấy đối tượng Method đại diện cho phương thức Java.
2. Đăng ký Method với tên function normalize.
3. Đưa dữ liệu đầu vào vào context bằng setVariable.
4. Phân tích biểu thức gọi function.
5. Đánh giá biểu thức và nhận giá trị trả về.

Expression có thể được parse một lần và đánh giá nhiều lần với các giá trị biến khác nhau. Mỗi lần đánh giá, function được gọi theo dữ liệu hiện có trong context.

## 5. Truyền literal làm tham số

Đối số có thể là literal được viết trực tiếp trong biểu thức:

~~~text
#normalize('  Hello World  ')
#isAllowed(18, 65)
#formatCode('vn', 42)
~~~

Literal chuỗi của SpEL thường đặt trong dấu nháy đơn. Literal số và boolean có thể viết trực tiếp theo cú pháp của ngôn ngữ.

Ví dụ function Java nhận hai số nguyên:

~~~java
public static boolean isWithinRange(
        int value, int minimum, int maximum) {
    return value >= minimum && value <= maximum;
}
~~~

Sau khi đăng ký Method tương ứng, có thể gọi:

~~~text
#isWithinRange(25, 18, 65)
~~~

Kết quả là true. Thứ tự đối số trong biểu thức phải tương ứng với thứ tự tham số của phương thức Java. Nếu đảo vị trí minimum và maximum, function vẫn có thể chạy nhưng kết quả không còn phản ánh quy tắc dự kiến.

## 6. Truyền biến trong EvaluationContext

Đối số function thường được lấy từ biến để có thể thay đổi dữ liệu mà không phải xây dựng lại chuỗi expression:

~~~text
#calculateDiscount(#subtotal, #discountRate)
~~~

Java đăng ký dữ liệu:

~~~java
context.setVariable("subtotal", new BigDecimal("250.00"));
context.setVariable("discountRate", new BigDecimal("0.10"));
~~~

Giả sử function có chữ ký:

~~~java
public static BigDecimal calculateDiscount(
        BigDecimal subtotal, BigDecimal rate) {
    return subtotal.multiply(rate);
}
~~~

Khi đánh giá, SpEL lấy hai biến, đánh giá từng đối số rồi truyền giá trị vào phương thức đã đăng ký.

Cách này giúp tách biểu thức khỏi dữ liệu đầu vào. Hãy cập nhật biến từ Java trước khi đánh giá; không nối dữ liệu người dùng trực tiếp vào chuỗi expression.

## 7. Truyền property của root object hoặc object trong biến

Đối số cũng có thể là property của root object:

~~~text
#formatCustomerName(name, email)
~~~

Nếu root object có các property name và email, SpEL đọc chúng rồi truyền vào function.

Có thể tham chiếu object đã đăng ký trong biến:

~~~text
#calculateTotal(#order.items, #order.taxRate)
~~~

Hoặc truyền một property cụ thể:

~~~text
#normalize(#customer.profile.displayName)
~~~

Tất cả đối số đều được đánh giá trước khi gọi function. Vì vậy, nếu một đường dẫn property trung gian là null, việc lấy đối số có thể thất bại trước khi phương thức Java được gọi.

Nếu dữ liệu lồng nhau có thể null, hãy dùng safe navigation ở từng mắt xích có thể null:

~~~text
#normalize(#customer?.profile?.displayName)
~~~

Function phải có hợp đồng xử lý null phù hợp với giá trị có thể nhận. Safe navigation bảo vệ việc truy cập property; nó không tự thay thế mọi lỗi bên trong function.

## 8. Truyền kết quả của biểu thức làm đối số

Đối số không bị giới hạn ở literal hoặc biến đơn giản. Có thể truyền kết quả của một biểu thức khác:

~~~text
#calculateTax(#order.total * #taxRate)
~~~

~~~text
#formatName(#firstName + ' ' + #lastName)
~~~

~~~text
#isEligible(#customer.age, #customer.orders.size())
~~~

SpEL đánh giá các biểu thức đối số, sau đó gọi function với các giá trị đã tính. Có thể lồng function nếu kiểu trả về của function bên trong tương thích với tham số của function bên ngoài:

~~~text
#formatCode(#normalize(#rawCode))
~~~

Trong ví dụ này, normalize chạy trước; kết quả của nó được truyền vào formatCode.

Biểu thức lồng giúp tái sử dụng xử lý, nhưng không nên lồng quá sâu đến mức khó xác định kiểu dữ liệu hoặc thứ tự gọi. Nếu có nhiều bước biến đổi, hãy đặt kết quả trung gian trong Java hoặc tạo một phương thức nghiệp vụ có tên mô tả rõ ý nghĩa.

## 9. Nhiều tham số và kiểu dữ liệu

Số lượng và thứ tự đối số phải phù hợp với chữ ký Method được đăng ký.

Ví dụ:

~~~java
public static String formatAmount(
        BigDecimal amount, String currency, int scale) {
    return amount.setScale(scale, RoundingMode.HALF_UP)
        + " " + currency;
}
~~~

Biểu thức:

~~~text
#formatAmount(#amount, #currency, #scale)
~~~

Các giá trị được truyền theo thứ tự amount, currency và scale.

Một số điểm cần chú ý:

- Số lượng đối số phải phù hợp với phương thức.
- Kiểu dữ liệu cần tương thích với kiểu tham số.
- Kiểu primitive như int không thể nhận null.
- Kiểu tham chiếu như String hoặc BigDecimal có thể nhận null nếu phương thức cho phép.
- Giá trị trả về có kiểu do phương thức Java quyết định.

SpEL có cơ chế TypeConverter trong EvaluationContext để chuyển đổi một số giá trị đối số khi cần. Không nên dựa vào chuyển đổi ngầm để che giấu dữ liệu sai định dạng. Với số tiền hoặc dữ liệu cần độ chính xác, hãy truyền đúng kiểu như BigDecimal ngay từ đầu.

## 10. Chọn đúng Method khi có overload

Java cho phép nhiều phương thức cùng tên nhưng khác danh sách tham số:

~~~java
public static String format(int value) { ... }

public static String format(BigDecimal value) { ... }
~~~

Khi đăng ký function, ứng dụng đăng ký một đối tượng Method cụ thể:

~~~java
Method method =
    FormatFunctions.class.getMethod("format", BigDecimal.class);

context.registerFunction("formatAmount", method);
~~~

Tên function trong SpEL là formatAmount, còn Method được chọn rõ là overload nhận BigDecimal.

SpEL không tự đăng ký toàn bộ overload của một tên Java. Việc chọn Method diễn ra khi ứng dụng lấy Method để đăng ký. Nếu cần nhiều dạng đầu vào, có thể đăng ký các function với tên riêng hoặc viết một phương thức wrapper nhận một kiểu dữ liệu thống nhất rồi xử lý phân nhánh trong Java.

Cách đăng ký rõ ràng giúp tránh việc một biểu thức gọi nhầm overload hoặc thay đổi hành vi khi lớp Java được bổ sung một phương thức cùng tên.

## 11. Đăng ký function bằng setVariable và registerFunction

Function được lưu trong namespace biến của EvaluationContext. Ở các phiên bản Spring cũ, có thể đăng ký Method bằng setVariable:

~~~java
context.setVariable("normalize", normalizeMethod);
~~~

Sau đó gọi bằng:

~~~text
#normalize(' Spring ')
~~~

Từ Spring Framework 6.1, StandardEvaluationContext cung cấp registerFunction(name, method) để diễn đạt rõ ý định đăng ký function:

~~~java
context.registerFunction("normalize", normalizeMethod);
~~~

Nên ưu tiên registerFunction khi phiên bản Spring đang dùng hỗ trợ phương thức này. Với dự án cũ hơn, kiểm tra API của đúng phiên bản; cách setVariable với giá trị là Method là cách đăng ký function truyền thống.

Function và variable dùng chung namespace. Nếu đăng ký function normalize rồi gọi setVariable("normalize", "text"), giá trị variable có thể thay thế Method đã đăng ký. Khi đó biểu thức #normalize(...) không còn tìm thấy Method để gọi.

Hãy tránh dùng cùng một tên cho function và biến. Đặt tên có ý nghĩa theo vai trò, chẳng hạn normalizeText cho function và inputText cho biến.

## 12. Function trả về giá trị và cách sử dụng kết quả

Function có thể trả về chuỗi, số, boolean, object hoặc collection. Giá trị trả về có thể được dùng như một phần của biểu thức lớn hơn.

Ví dụ function trả về boolean:

~~~text
#isBusinessDay(#eventDate) and #order.total > 0
~~~

Ví dụ function trả về chuỗi:

~~~text
#normalize(#customer.name).toUpperCase()
~~~

Ví dụ function trả về BigDecimal:

~~~text
#calculateNetAmount(#grossAmount, #taxAmount) >= #minimumAmount
~~~

Nếu function trả về null, phần biểu thức nhận kết quả đó cũng có thể là null. Truy cập tiếp property hoặc gọi method trên kết quả null có thể phát sinh lỗi. Hãy xác định rõ function có thể trả null hay không và dùng safe navigation hoặc điều kiện phù hợp.

Function dùng trong biểu thức thường nên trả về giá trị có ý nghĩa. Phương thức void không cung cấp kết quả hữu ích cho các phép tính tiếp theo; nếu cần thực hiện hành động, hãy cân nhắc gọi một service qua cơ chế được kiểm soát ở tầng ứng dụng thay vì dùng function tính toán.

## 13. Dùng function trong selection và projection

Function có thể được gọi trong điều kiện selection hoặc biểu thức projection.

Ví dụ lọc các mã hợp lệ:

~~~text
#codes.?[#isValidCode(#this)]
~~~

Function isValidCode được gọi cho từng phần tử của collection.

Ví dụ chuẩn hóa tên trong projection:

~~~text
#customers.![#normalize(#this.name)]
~~~

Mỗi khách hàng được chuyển thành một chuỗi tên đã chuẩn hóa.

Có thể kết hợp cả hai:

~~~text
#orders.?[#isEligibleOrder(#this, #minimumTotal)].![#toSummary(#this)]
~~~

Selection gọi isEligibleOrder trên từng đơn hàng; projection gọi toSummary trên từng đơn hàng đã được chọn.

Hãy nhớ function có thể được gọi nhiều lần trong một lần đánh giá collection. Với N phần tử, function trong selection có thể chạy tới N lần; function trong projection chạy theo số phần tử đi qua projection. Không nên đặt truy vấn mạng, ghi file hoặc thao tác nặng trong function được gọi lặp theo từng phần tử.

## 14. Function có tác dụng phụ và vấn đề hiệu năng

Function là mã Java thực sự. Khi được gọi, phương thức có thể thay đổi trạng thái, đọc/ghi dữ liệu hoặc giao tiếp với hệ thống bên ngoài.

Đối với function được dùng trong biểu thức điều kiện hoặc collection operation, nên ưu tiên phương thức thuần (pure function):

- Cùng đầu vào cho cùng kết quả.
- Không thay đổi trạng thái dùng chung.
- Không ghi file hoặc gửi thông điệp.
- Không mở kết nối hoặc giữ tài nguyên.
- Không phụ thuộc vào thứ tự gọi ngoài hợp đồng đã định.

Một function có tác dụng phụ có thể bị gọi nhiều lần khi expression được đánh giá lại hoặc khi nằm trong selection/projection. Điều này có thể khiến một biểu thức trông như phép lọc đơn giản nhưng thực tế tạo nhiều giao dịch hoặc hành động ngoài ý muốn.

Nếu cần gọi service, truy vấn dữ liệu hoặc thực hiện thao tác có thể thất bại, hãy đặt việc đó trong service Java và truyền kết quả đã chuẩn bị vào context. Đo chi phí thực tế nếu function thực hiện phép tính tốn CPU.

## 15. Xử lý null và lỗi khi truyền tham số

Lỗi có thể xảy ra trước hoặc trong lúc gọi function:

- Biến đầu vào chưa được đăng ký.
- Root object hoặc property trung gian là null.
- Số lượng đối số không phù hợp với Method.
- Kiểu đối số không thể chuyển đổi sang kiểu tham số.
- Đối số null được truyền vào tham số primitive.
- Function ném exception khi xử lý dữ liệu.
- Method không thể truy cập theo quyền reflection hiện tại.

Ví dụ function nhận String:

~~~java
public static String normalize(String value) {
    if (value == null) {
        return null;
    }
    return value.trim();
}
~~~

Phương thức này chủ động xử lý null. Nếu function không chấp nhận null, hãy kiểm tra trước khi gọi:

~~~text
#input != null and #isValidCode(#input)
~~~

Với lỗi đánh giá, ứng dụng nên bắt EvaluationException tại ranh giới gọi expression và ghi nhận nguyên nhân gốc. Không nên bắt mọi lỗi rồi trả về true hoặc một giá trị mặc định tùy tiện, vì như vậy có thể biến dữ liệu sai thành kết quả nghiệp vụ hợp lệ.

## 16. Phân biệt function với bean và method resolver

Function là một Method được đăng ký trực tiếp trong context. Bean reference lấy object từ Spring container, còn method resolver quyết định cách gọi method trên object.

| Cơ chế | Đăng ký hoặc cấu hình | Cách gọi |
|---|---|---|
| Function | Method được đăng ký vào context | #functionName(args) |
| Bean reference | BeanResolver kết nối với BeanFactory | @beanName.method(args) |
| Method invocation | Object có thể truy cập trong expression | #object.method(args) hoặc rootProperty.method(args) |

Function thường phù hợp với một phép xử lý tĩnh, ngắn và có đầu vào/đầu ra rõ ràng. Bean phù hợp với collaborator có dependency, lifecycle hoặc trạng thái do Spring quản lý. Method invocation phù hợp khi thao tác thuộc về chính object dữ liệu đang được đánh giá.

Không nên đăng ký một service instance như function bằng cách truyền Method instance method. Function reference được thiết kế để gọi Method đã đăng ký theo cơ chế function; hãy dùng static method hoặc tham chiếu bean nếu cần gọi method trên instance do Spring quản lý.

## 17. Giới hạn quyền gọi function

Đăng ký một function đồng nghĩa với việc cho phép expression gọi mã Java tương ứng. Nếu expression đến từ người dùng hoặc nguồn không đáng tin cậy, việc đăng ký quá nhiều function có thể mở rộng quyền vượt nhu cầu.

Hãy áp dụng các nguyên tắc:

1. Chỉ đăng ký function thật sự cần cho bài toán.
2. Dùng lớp tiện ích có các public static method nhỏ, dễ kiểm tra.
3. Không đăng ký method có khả năng thực thi lệnh hệ thống, đọc bí mật hoặc thay đổi dữ liệu nếu không có yêu cầu và kiểm soát riêng.
4. Kiểm tra kiểu, kích thước và nội dung của đối số.
5. Không dùng function để thay thế authorization hoặc validation ở tầng service.
6. Dùng EvaluationContext phù hợp và không chia sẻ context có thể thay đổi giữa các request nếu có nguy cơ rò rỉ dữ liệu.

Nếu cần cung cấp function cho expression không đáng tin cậy, hãy tạo một context riêng chỉ chứa các function trong allowlist. Tránh đưa object hoặc function có quyền rộng vào context chỉ vì tiện lợi.

## 18. Ví dụ tổng hợp: function kiểm tra hạn mức

Giả sử ứng dụng cần kiểm tra tổng tiền của đơn hàng nằm trong giới hạn:

~~~java
public final class OrderFunctions {

    private OrderFunctions() {
    }

    public static boolean isWithinLimit(
            BigDecimal amount,
            BigDecimal minimum,
            BigDecimal maximum) {

        if (amount == null || minimum == null || maximum == null) {
            return false;
        }

        return amount.compareTo(minimum) >= 0
            && amount.compareTo(maximum) <= 0;
    }
}
~~~

Đăng ký và gọi function:

~~~java
Method method = OrderFunctions.class.getMethod(
    "isWithinLimit",
    BigDecimal.class,
    BigDecimal.class,
    BigDecimal.class
);

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.registerFunction("isWithinLimit", method);

context.setVariable("minimum", new BigDecimal("100.00"));
context.setVariable("maximum", new BigDecimal("500.00"));

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "#isWithinLimit(total, #minimum, #maximum)"
);

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

Trong biểu thức:

- total là property của root object order.
- #minimum và #maximum là biến trong EvaluationContext.
- #isWithinLimit(...) là function đã đăng ký.

Phương thức Java chịu trách nhiệm kiểm tra null và so sánh BigDecimal. Biểu thức chỉ kết nối các giá trị đầu vào với quy tắc được đóng gói trong function.

## 19. Kiểm thử function và đối số

Khi kiểm thử một function được dùng trong SpEL, hãy xác nhận:

| Trường hợp | Điều cần kiểm tra |
|---|---|
| Literal hợp lệ | Đối số được truyền đúng |
| Variable | Giá trị mới nhất trong context được sử dụng |
| Root property | Đúng property của đối tượng gốc được truyền |
| Nhiều đối số | Đúng số lượng và thứ tự |
| Kiểu tương thích | Method được gọi với kiểu phù hợp |
| Kiểu cần chuyển đổi | TypeConverter xử lý theo cấu hình |
| Đối số null | Function xử lý đúng hợp đồng |
| Biến chưa đăng ký | Lỗi hoặc giá trị thiếu được phát hiện |
| Function trả null | Biểu thức phía sau xử lý null |
| Function ném exception | Lỗi được báo tại ranh giới đánh giá |
| Overload | Đúng Method đã đăng ký được gọi |
| Selection/projection | Số lần gọi tương ứng phần tử được xử lý |
| Trùng tên variable/function | Namespace không bị ghi đè ngoài ý muốn |
| Function có tác dụng phụ | Không tạo hành động lặp ngoài dự kiến |

Có thể kiểm thử phương thức Java trực tiếp và kiểm thử tích hợp qua SpEL. Kiểm thử trực tiếp xác nhận logic của function; kiểm thử tích hợp xác nhận việc đăng ký Method, phân giải tên, đánh giá đối số và chuyển đổi kiểu.

## 20. Ghi nhớ

Function trong SpEL là Method Java được đăng ký trong EvaluationContext và được gọi bằng cú pháp #functionName(arguments). Function thông thường dùng static method; ứng dụng lấy đối tượng Method rồi đăng ký với tên function. Từ Spring Framework 6.1, nên dùng StandardEvaluationContext.registerFunction; ở phiên bản cũ hơn có thể đăng ký Method qua setVariable.

Đối số có thể là literal, variable, property của root object hoặc kết quả biểu thức khác. Thứ tự và kiểu đối số phải phù hợp với Method đã đăng ký. Function có thể trả về giá trị được dùng trong điều kiện hoặc biểu thức lớn hơn; null và exception cần được xử lý theo hợp đồng rõ ràng.

Function và variable dùng chung namespace, vì vậy tránh đặt cùng tên. Function khác bean reference và method invocation trên object. Function có thể chạy nhiều lần trong selection/projection hoặc khi expression được đánh giá lại, nên ưu tiên phương thức thuần, nhanh và không có tác dụng phụ.

Chỉ đăng ký những function cần thiết, kiểm tra đối số và giới hạn quyền gọi khi expression đến từ nguồn không đáng tin cậy. Với service có dependency, lifecycle hoặc tác dụng phụ, hãy cân nhắc dùng bean hoặc xử lý trong Java thay vì biến nó thành function tĩnh.

## Tài liệu tham khảo

- [Spring Framework Reference — Functions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/functions.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [EvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)