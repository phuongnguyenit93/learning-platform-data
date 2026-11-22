# Chữ ký function, chuyển đổi kiểu và lỗi đánh giá

Trong SpEL, function là một method Java được đăng ký vào EvaluationContext để biểu thức có thể gọi bằng tên. Khi đăng ký, ứng dụng cung cấp một đối tượng Method, vì vậy chữ ký Java của method quyết định số lượng, thứ tự và kiểu tham số mà function nhận. Khi đánh giá, SpEL lấy các đối số từ biểu thức, thực hiện chuyển đổi kiểu nếu TypeConverter hỗ trợ, gọi method và sử dụng giá trị trả về làm kết quả của biểu thức.

Ba phần cần được hiểu riêng là chữ ký function, chuyển đổi dữ liệu và lỗi đánh giá. Một function có thể đăng ký thành công nhưng lời gọi vẫn thất bại vì đối số không tương thích, converter không xử lý được kiểu nguồn hoặc chính method ném exception. Phân biệt các giai đoạn này giúp chẩn đoán đúng nguyên nhân.

## 1. Function trong SpEL là gì?

Function là method Java được đưa vào EvaluationContext dưới một tên mà biểu thức có thể tham chiếu bằng tiền tố #.

Cú pháp gọi:

~~~text
#functionName()
#functionName(argument)
#functionName(argument1, argument2)
~~~

Tên function trong context không có dấu #. Dấu # chỉ xuất hiện trong biểu thức khi gọi function.

Ví dụ, một thư viện function:

~~~java
public class TextFunctions {

    public static String normalize(String value) {
        return value == null ? "" : value.trim().toLowerCase();
    }
}
~~~

Đăng ký và gọi:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Method normalizeMethod =
        TextFunctions.class.getMethod("normalize", String.class);

context.registerFunction("normalize", normalizeMethod);

Expression expression =
        parser.parseExpression("#normalize('  Spring  ')");

String result = expression.getValue(context, String.class);

System.out.println(result); // spring
~~~

SpEL không tự tìm mọi static method trên classpath theo tên function. Function chỉ có thể được gọi nếu ứng dụng đăng ký nó trong context đang dùng hoặc cung cấp cơ chế tương ứng.

## 2. Chữ ký Method xác định hợp đồng của function

Khi đăng ký function, ứng dụng cung cấp một đối tượng java.lang.reflect.Method. Method đó xác định:

- Tên và class khai báo method.
- Số lượng tham số.
- Thứ tự tham số.
- Kiểu Java của từng tham số.
- Kiểu trả về.
- Các exception mà phần triển khai có thể phát sinh.

Ví dụ:

~~~java
public class PriceFunctions {

    public static BigDecimal calculateTax(
            BigDecimal amount,
            BigDecimal rate) {

        return amount.multiply(rate);
    }
}
~~~

Đăng ký đúng chữ ký:

~~~java
Method taxMethod = PriceFunctions.class.getMethod(
        "calculateTax",
        BigDecimal.class,
        BigDecimal.class
);

context.registerFunction("calculateTax", taxMethod);
~~~

Biểu thức phải cung cấp hai đối số theo đúng thứ tự:

~~~text
#calculateTax(#amount, #taxRate)
~~~

Đối số thứ nhất được truyền cho amount, đối số thứ hai được truyền cho rate. Nếu đảo vị trí hoặc cung cấp sai số lượng tham số, việc gọi function có thể thất bại khi đánh giá.

Nên dùng kiểu tham số cụ thể, thể hiện đúng hợp đồng dữ liệu. Tránh khai báo tất cả tham số là Object chỉ để biểu thức dễ gọi hơn, vì điều đó chuyển nhiều lỗi kiểu sang bên trong method và làm hợp đồng khó kiểm tra.

## 3. Đăng ký Method bằng reflection

Có thể lấy Method bằng Class.getMethod hoặc Class.getDeclaredMethod. getMethod tìm method public, kể cả method kế thừa; getDeclaredMethod tìm method được khai báo trực tiếp trên class và có thể trả về method không public.

Ví dụ:

~~~java
Method method = TextFunctions.class.getMethod(
        "normalize",
        String.class
);

context.registerFunction("normalize", method);
~~~

Với function dùng trong ứng dụng, nên ưu tiên method public static có chữ ký rõ ràng. API đăng ký function nhận Method cụ thể, vì vậy method được chọn ngay khi cấu hình context.

Nếu class có nhiều overload cùng tên, hãy chọn đúng chữ ký khi lấy Method. SpEL không chọn overload của function chỉ dựa trên tên đăng ký như cách phân giải instance method thông thường; tên function gắn với Method đã đăng ký.

Nếu cần nhiều cách gọi, có thể đăng ký các tên function riêng hoặc tạo một wrapper method có chữ ký thống nhất để điều phối trong Java.

## 4. Gọi function không tham số và có tham số

Function không tham số được gọi với cặp ngoặc rỗng:

~~~text
#currentTimestamp()
#defaultLocale()
~~~

Function có một hoặc nhiều tham số đặt các đối số trong ngoặc:

~~~text
#normalize(#rawName)
#calculateTax(#amount, #rate)
#formatLabel('Order', #orderNumber)
~~~

Đối số có thể là literal, context variable, property của root object hoặc một biểu thức khác. SpEL đánh giá các đối số để lấy giá trị truyền vào method.

Ví dụ:

~~~java
context.setVariable("amount", new BigDecimal("250.00"));
context.setVariable("rate", new BigDecimal("0.08"));

Expression expression = parser.parseExpression(
        "#calculateTax(#amount, #rate)"
);

BigDecimal tax = expression.getValue(context, BigDecimal.class);
~~~

Hãy giữ thứ tự đối số nhất quán với chữ ký Java. Khi function có nhiều tham số cùng kiểu, lỗi đảo vị trí có thể không gây lỗi runtime nhưng vẫn tạo kết quả nghiệp vụ sai. Dùng tên biến có ý nghĩa và wrapper có tham số rõ ràng để giảm nhầm lẫn.

## 5. Function và instance method là hai cơ chế khác nhau

Function đã đăng ký được gọi qua #functionName(...). Instance method được gọi trên root object, biến object hoặc property object:

~~~text
#normalize(#rawText)
#customer.getDisplayName()
#order.calculateTotal()
~~~

Hai cú pháp có thể cùng gọi Java method nhưng cách phân giải khác nhau:

| Cách gọi | Nguồn method | Cách tham chiếu |
|---|---|---|
| Registered function | Method đã đăng ký trong context | #functionName(args) |
| Instance method | Object đích hiện tại hoặc object được truy cập | object.method(args) |
| Static method qua type reference | Class được phân giải bằng T(...) | T(com.example.Utility).method(args) |
| Spring bean method | Bean được phân giải qua BeanResolver | @beanName.method(args) |

Đăng ký function phù hợp khi muốn cung cấp một API nhỏ, ổn định cho biểu thức. Nếu method phụ thuộc trạng thái của một instance, hãy truyền object qua root/variable hoặc dùng bean resolver thay vì cố đăng ký instance method như một function tĩnh.

## 6. Tên function và context variables

Function được đăng ký bằng tên, ví dụ normalize. Trong biểu thức, tên đó được tham chiếu là #normalize.

Từ Spring Framework 6.1, function và variable dùng chung namespace trong EvaluationContext. Vì vậy, không nên đăng ký một function và một context variable với cùng tên rồi kỳ vọng cả hai cùng tồn tại độc lập. Việc đăng ký sau có thể thay thế binding trước đó.

Ví dụ tên dễ gây xung đột:

~~~java
context.registerFunction("format", formatMethod);
context.setVariable("format", "plain");
~~~

Hãy dùng quy ước tên tách biệt, chẳng hạn function theo động từ và biến theo danh từ:

~~~java
context.registerFunction("formatLabel", formatMethod);
context.setVariable("labelFormat", "plain");
~~~

Điều này giúp biểu thức dễ đọc và tránh lỗi khó nhận ra khi context được cấu hình ở nhiều nơi.

## 7. Chuyển đổi kiểu cho đối số function

Đối số trong biểu thức có thể có kiểu khác với kiểu tham số Java. SpEL dùng TypeConverter của EvaluationContext để chuyển đổi khi có converter phù hợp.

Ví dụ, function yêu cầu Integer nhưng biểu thức truyền vào một giá trị String:

~~~java
public class NumberFunctions {

    public static String describe(Integer value) {
        return "number=" + value;
    }
}
~~~

Khi conversion service được cấu hình có khả năng chuyển String sang Integer, lời gọi có thể sử dụng giá trị chuỗi phù hợp:

~~~text
#describeNumber('42')
~~~

Khả năng chuyển đổi phụ thuộc TypeConverter hiện tại và các converter được đăng ký. Không nên giả định mọi chuỗi đều có thể chuyển thành mọi kiểu hoặc dữ liệu sai định dạng sẽ tự được sửa.

Nếu conversion không thực hiện được, lỗi xuất hiện trong giai đoạn đánh giá function. Hãy kiểm tra kiểu runtime của đối số, kiểu tham số của Method và converter có hỗ trợ cặp kiểu nguồn/đích hay không.

## 8. Cấu hình ConversionService tùy chỉnh

StandardTypeConverter có thể dùng Spring ConversionService. Nếu ứng dụng có kiểu domain riêng, hãy đăng ký converter rồi gắn StandardTypeConverter vào EvaluationContext.

Ví dụ có kiểu CustomerId:

~~~java
public record CustomerId(String value) {
}

public class CustomerFunctions {

    public static String label(CustomerId id) {
        return "customer:" + id.value();
    }
}
~~~

Cấu hình chuyển String thành CustomerId:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerId.class,
        CustomerId::new
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

Method labelMethod = CustomerFunctions.class.getMethod(
        "label",
        CustomerId.class
);

context.registerFunction("customerLabel", labelMethod);
~~~

Biểu thức:

~~~text
#customerLabel('C-100')
~~~

Khi TypeConverter sử dụng ConversionService đã cấu hình, đối số String có thể được chuyển thành CustomerId trước khi gọi method.

Converter nên có quy tắc rõ ràng và kiểm tra dữ liệu đầu vào. Nếu chuỗi rỗng hoặc sai định dạng không thể tạo CustomerId hợp lệ, hãy phát sinh lỗi chuyển đổi có ý nghĩa để ứng dụng xử lý.

## 9. Chuyển đổi kiểu trả về

Function trả về kiểu do Java method khai báo. Nếu biểu thức được lấy bằng overload getValue có kiểu đích, SpEL có thể chuyển kết quả sang kiểu đích nếu TypeConverter hỗ trợ.

Ví dụ:

~~~java
Expression expression = parser.parseExpression(
        "#calculateCount('12')"
);

Integer count = expression.getValue(context, Integer.class);
~~~

Có hai điểm chuyển đổi cần phân biệt:

1. Chuyển đổi đối số trước khi gọi function để khớp kiểu tham số.
2. Chuyển đổi giá trị trả về sang kiểu mà code Java yêu cầu khi gọi getValue(context, TargetType.class).

Nếu function trả về BigDecimal nhưng code yêu cầu String, kết quả phụ thuộc converter có hỗ trợ chuyển đổi hay không. Việc yêu cầu kiểu trả về không thay đổi chữ ký Java của function và không làm method chạy với một kiểu khác.

Khi kiểu trả về là một phần của hợp đồng nghiệp vụ, nên khai báo kiểu Java phù hợp ngay trong function và chỉ dùng typed getValue để kiểm soát kiểu ở ranh giới nhận kết quả.

## 10. Conversion không phải validation

Conversion biến đổi giá trị từ kiểu nguồn sang kiểu đích. Validation kiểm tra giá trị có hợp lệ theo quy tắc nghiệp vụ hay không.

Ví dụ, chuỗi " -5 " có thể được chuyển thành Integer -5 thành công. Nhưng nếu function yêu cầu số lượng dương, giá trị đó vẫn không hợp lệ.

~~~java
public static int normalizeQuantity(Integer quantity) {
    if (quantity == null || quantity <= 0) {
        throw new IllegalArgumentException(
                "Quantity must be positive"
        );
    }
    return quantity;
}
~~~

Converter chỉ nên chịu trách nhiệm chuyển đổi kiểu. Quy tắc nghiệp vụ như số lượng dương, hạn mức, quyền truy cập hoặc trạng thái hợp lệ cần được kiểm tra ở function hoặc service phù hợp.

Không nên xem việc conversion thành công là bằng chứng dữ liệu đã hợp lệ. Tương tự, một function trả về đúng kiểu không đồng nghĩa với kết quả đáp ứng mọi invariant của domain.

## 11. Chữ ký overload và varargs

Một tên function đã đăng ký gắn với một Method cụ thể. Nếu class có nhiều overload:

~~~java
public static String describe(String value) {
    return "text";
}

public static String describe(Integer value) {
    return "number";
}
~~~

hãy chọn rõ overload khi đăng ký:

~~~java
Method textMethod = Functions.class.getMethod(
        "describe",
        String.class
);

context.registerFunction("describeText", textMethod);
~~~

Có thể đăng ký overload còn lại dưới tên khác:

~~~java
Method numberMethod = Functions.class.getMethod(
        "describe",
        Integer.class
);

context.registerFunction("describeNumber", numberMethod);
~~~

Đối với method varargs, cần chú ý cách Java reflection biểu diễn tham số cuối dưới dạng array và cách SpEL chuẩn bị đối số. Hãy thử lời gọi với số lượng đối số thực tế trên phiên bản Spring đang chạy. Nếu biểu thức được nhiều nhóm cấu hình, một wrapper method có tham số cố định thường dễ hiểu và ổn định hơn.

## 12. Lỗi parse và lỗi evaluate xảy ra ở hai giai đoạn

SpEL có hai giai đoạn chính:

- Parse: phân tích chuỗi biểu thức và tạo Expression.
- Evaluate: chạy Expression với EvaluationContext và dữ liệu cụ thể.

Lỗi cú pháp thường xuất hiện trong giai đoạn parse dưới dạng ParseException. Ví dụ thiếu dấu ngoặc, dấu nháy hoặc viết sai cấu trúc lời gọi function.

Lỗi trong giai đoạn evaluate thường xuất hiện dưới dạng EvaluationException hoặc lớp con như SpelEvaluationException. Ví dụ function chưa được đăng ký, sai đối số, không chuyển đổi được kiểu hoặc method ném exception.

Ví dụ xử lý riêng hai giai đoạn:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(
            "#calculateTax(#amount, #rate)"
    );
} catch (ParseException ex) {
    // Biểu thức sai cú pháp
    throw ex;
}

try {
    BigDecimal result = expression.getValue(
            context,
            BigDecimal.class
    );
} catch (EvaluationException ex) {
    // Lỗi khi phân giải hoặc chạy biểu thức
    throw ex;
}
~~~

Tách hai giai đoạn giúp xác định lỗi nằm ở chuỗi biểu thức hay ở dữ liệu/context tại thời điểm chạy. Trong ứng dụng thực tế, có thể parse một lần và tái sử dụng Expression cho nhiều lượt đánh giá.

## 13. Các nguyên nhân lỗi đánh giá thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Function không được tìm thấy | Tên chưa đăng ký hoặc context đang dùng khác context cấu hình | Kiểm tra tên đăng ký và context truyền vào getValue |
| Không tìm được Method khi khởi tạo | Sai tên hoặc danh sách kiểu tham số khi dùng reflection | Kiểm tra getMethod/getDeclaredMethod |
| Sai số lượng đối số | Expression không khớp chữ ký Method | Đối chiếu số tham số và thứ tự đối số |
| Đối số không tương thích | TypeConverter không có converter phù hợp | Kiểm tra kiểu runtime và kiểu tham số |
| Chuyển đổi thất bại | Giá trị nguồn sai định dạng hoặc converter từ chối | Kiểm tra dữ liệu đầu vào và nguyên nhân conversion |
| Kết quả không đúng kiểu mong muốn | Return type không tương thích với kiểu getValue yêu cầu | Kiểm tra chữ ký trả về và converter |
| Function ném exception | Lỗi trong logic của method | Kiểm tra cause gốc của lỗi đánh giá |
| Function biến mất sau khi đăng ký | Tên bị trùng với context variable | Dùng tên function và variable riêng biệt |
| Lỗi chỉ xuất hiện ở một request | Context hoặc biến đầu vào khác nhau giữa các lượt | Kiểm tra root object, variables và TypeConverter |

Thông báo lỗi cụ thể và mã lỗi có thể khác theo phiên bản Spring và đường thực thi. Hãy dựa vào loại exception, cause và dữ liệu đầu vào thực tế thay vì phụ thuộc vào toàn bộ chuỗi thông báo.

## 14. Chẩn đoán lỗi function có hệ thống

Khi function không chạy như mong đợi, hãy kiểm tra theo thứ tự:

1. Xác nhận chuỗi biểu thức parse thành công.
2. Xác nhận đúng EvaluationContext được truyền vào getValue.
3. Xác nhận function đã đăng ký dưới đúng tên, không có dấu # ở tên đăng ký.
4. Xác nhận Method lấy được đúng class, tên và kiểu tham số.
5. Kiểm tra số lượng, thứ tự và kiểu runtime của đối số.
6. Kiểm tra TypeConverter và ConversionService nếu cần chuyển kiểu.
7. Nếu method đã chạy nhưng thất bại, xem cause gốc để tìm lỗi trong function.
8. Kiểm tra kiểu trả về và kiểu đích của getValue.

Có thể ghi log tên expression hoặc mã rule, loại exception và nguyên nhân gốc. Tránh ghi toàn bộ dữ liệu nhạy cảm trong context hoặc giá trị đối số vào log.

Không nên bắt mọi Throwable rồi trả về null, vì cách đó che giấu lỗi lập trình, lỗi chuyển đổi và lỗi nghiệp vụ. Hãy bắt các exception phù hợp tại ranh giới xử lý và chuyển thành thông báo có ý nghĩa cho caller.

## 15. An toàn khi cung cấp function cho biểu thức

Đăng ký function làm tăng khả năng mà biểu thức có thể thực hiện. Nếu function có thể ghi database, gửi email, thanh toán hoặc gọi API, một expression có thể kích hoạt hành động đó khi được đánh giá.

Một số nguyên tắc:

- Chỉ đăng ký function thực sự cần thiết cho use case.
- Ưu tiên function thuần, không thay đổi trạng thái và không thực hiện I/O.
- Dùng tên thể hiện hành vi và chữ ký tham số rõ ràng.
- Kiểm tra dữ liệu trong function; không dựa vào conversion để thay thế validation.
- Không đăng ký repository hoặc service rộng quyền dưới dạng function tiện dụng.
- Giữ EvaluationContext riêng cho từng lượt đánh giá khi variables hoặc root object thay đổi.
- Không xem việc ẩn tên function là cơ chế authorization.

Nếu biểu thức do người dùng hoặc nguồn không tin cậy cung cấp, cần kiểm soát cả function, MethodResolver, PropertyAccessor, TypeLocator và BeanResolver. Chỉ đăng ký một số function an toàn là một phần của giới hạn quyền, nhưng vẫn cần giới hạn các đường truy cập khác trong context.

## 16. Ví dụ hoàn chỉnh: function, conversion và xử lý lỗi

Ví dụ sau đăng ký function tính phí từ hai tham số BigDecimal, dùng context variable và lấy kết quả theo kiểu cụ thể:

~~~java
public class BillingFunctions {

    public static BigDecimal calculateFee(
            BigDecimal amount,
            BigDecimal rate) {

        if (amount == null || rate == null) {
            throw new IllegalArgumentException(
                    "Amount and rate are required"
            );
        }

        if (amount.signum() < 0 || rate.signum() < 0) {
            throw new IllegalArgumentException(
                    "Amount and rate must be non-negative"
            );
        }

        return amount.multiply(rate);
    }
}
~~~

Cấu hình và đánh giá:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Method feeMethod = BillingFunctions.class.getMethod(
        "calculateFee",
        BigDecimal.class,
        BigDecimal.class
);

context.registerFunction("calculateFee", feeMethod);

context.setVariable("amount", new BigDecimal("250.00"));
context.setVariable("rate", new BigDecimal("0.08"));

Expression expression = parser.parseExpression(
        "#calculateFee(#amount, #rate)"
);

try {
    BigDecimal fee = expression.getValue(
            context,
            BigDecimal.class
    );

    System.out.println(fee); // 20.0000
} catch (EvaluationException ex) {
    // Ghi nhận lỗi đánh giá và xử lý theo chính sách ứng dụng
}
~~~

Chữ ký Method xác định hai tham số BigDecimal. Các biến context cung cấp giá trị cho lời gọi. Function kiểm tra invariant nghiệp vụ rồi trả về BigDecimal. Typed getValue yêu cầu kết quả BigDecimal; nếu function đã trả đúng kiểu thì không cần chuyển đổi kết quả.

Trong ứng dụng thực tế, cần quyết định scale và RoundingMode cho phép tính tiền ở tầng nghiệp vụ. Ví dụ trên minh họa chữ ký và luồng đánh giá, không tự định nghĩa chính sách làm tròn cho mọi loại phí.

## 17. Ghi nhớ

Function SpEL là Method Java được đăng ký vào EvaluationContext và gọi bằng cú pháp #functionName(args). Method đã chọn quyết định số lượng, thứ tự, kiểu tham số và kiểu trả về. Với overload, hãy chọn rõ Method khi đăng ký hoặc cung cấp tên function riêng.

TypeConverter có thể chuyển đổi đối số để phù hợp chữ ký và chuyển kết quả sang kiểu mà getValue yêu cầu, nếu converter hỗ trợ. StandardTypeConverter có thể sử dụng ConversionService tùy chỉnh. Conversion chỉ đổi kiểu; validation nghiệp vụ vẫn phải được thực hiện riêng.

ParseException chỉ ra lỗi phân tích biểu thức; EvaluationException và SpelEvaluationException thường chỉ ra lỗi trong lúc đánh giá, phân giải function, chuyển đổi hoặc chạy method. Hãy tách parse khỏi evaluate, kiểm tra context và chữ ký Method, xem cause gốc khi function thất bại, và chỉ cung cấp những function có phạm vi quyền phù hợp.