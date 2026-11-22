# Đăng ký hàm Java vào EvaluationContext

Spring Expression Language (SpEL) cho phép gọi các hàm Java từ expression bằng cách đăng ký một đối tượng **java.lang.reflect.Method** vào **EvaluationContext**. Sau khi đăng ký, expression gọi hàm bằng cú pháp **#functionName(arguments)**.

Cơ chế này hữu ích khi nhiều expression cần dùng chung một phép xử lý nhỏ, chẳng hạn chuẩn hóa chuỗi, kiểm tra mã, tính toán hoặc áp dụng một quy tắc đơn giản. Thay vì viết lại logic trong từng expression, ứng dụng đưa method Java vào context một lần rồi gọi lại bằng tên hàm.

Ví dụ:

~~~text
#normalizeCode(#rawCode)
~~~

Expression gọi function normalizeCode đã đăng ký trong context và truyền giá trị của variable rawCode làm đối số.

## 1. Function trong SpEL là gì?

Một function của SpEL là một method Java được đăng ký với một tên để expression có thể gọi. Tên function do ứng dụng chọn, không nhất thiết trùng với tên method Java.

Ví dụ method Java:

~~~java
public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        return value == null
                ? null
                : value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

Method Java có tên normalize. Khi đăng ký method này với tên normalizeCode, expression gọi:

~~~text
#normalizeCode(' spring ')
~~~

Kết quả là chuỗi SPRING.

Cú pháp gọi function:

~~~text
#functionName(argument1, argument2, ...)
~~~

Dấu # cho biết tên đang được tra cứu trong namespace variable/function của EvaluationContext. Dấu ngoặc tròn truyền các đối số cho method.

Function có thể trả về bất kỳ kiểu Java nào mà SpEL có thể nhận và sử dụng: String, boolean, số, enum, domain object, collection hoặc null. Kết quả trả về có thể tiếp tục được dùng trong phép toán, điều kiện, truy cập property hoặc lời gọi method khác.

## 2. Đăng ký Method bằng StandardEvaluationContext

Cách thông dụng là lấy Method bằng reflection rồi gọi **registerFunction()** trên StandardEvaluationContext.

Ví dụ hoàn chỉnh:

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
        return value == null
                ? null
                : value.trim().toUpperCase(Locale.ROOT);
    }
}

class FunctionExample {

    public static void main(String[] args) throws NoSuchMethodException {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        Method normalizeMethod = TextFunctions.class
                .getMethod("normalize", String.class);

        context.registerFunction("normalizeCode", normalizeMethod);
        context.setVariable("rawCode", " spring ");

        ExpressionParser parser = new SpelExpressionParser();

        Expression expression =
                parser.parseExpression("#normalizeCode(#rawCode)");

        String result = expression.getValue(context, String.class);

        System.out.println(result); // SPRING
    }
}
~~~

Các bước chính:

1. Tạo StandardEvaluationContext.
2. Lấy đối tượng Method đại diện cho method Java cần đăng ký.
3. Gọi registerFunction() với tên function và Method.
4. Đăng ký các variable mà expression cần dùng.
5. Parse expression có cú pháp #functionName(...).
6. Đánh giá expression bằng chính context đã đăng ký function.

Function được đăng ký trên context cụ thể. Chỉ những expression được đánh giá bằng context đó mới nhìn thấy function này.

## 3. Method dùng làm function nên có chữ ký như thế nào?

Function được đăng ký bằng một đối tượng Method, vì vậy cần chọn chính xác method và chữ ký mong muốn.

### 3.1. Dùng static method

Nên đăng ký một **public static method**. Function invocation không truyền một instance Java làm receiver cho method; method được gọi như một hàm tiện ích độc lập.

Ví dụ phù hợp:

~~~java
public static boolean isValidCode(String value) {
    return value != null && value.matches("[A-Z]{3}-[0-9]{4}");
}
~~~

Đăng ký:

~~~java
Method method = CodeFunctions.class
        .getMethod("isValidCode", String.class);

context.registerFunction("validCode", method);
~~~

Gọi trong SpEL:

~~~text
#validCode(#code)
~~~

Nếu cần gọi method instance có dependency, trạng thái hoặc cấu hình được inject, hãy cân nhắc gọi method trên Spring bean bằng bean reference, ví dụ @codePolicy.isValid(#code). Bean method phù hợp hơn khi logic cần các dependency do Spring quản lý.

### 3.2. Chọn đúng overload

Java cho phép overload method, nhưng registerFunction() nhận một đối tượng Method cụ thể. Vì vậy, hãy chọn rõ overload bằng tên method và danh sách kiểu tham số:

~~~java
Method method = NumberFunctions.class
        .getMethod("round", BigDecimal.class, int.class);

context.registerFunction("roundAmount", method);
~~~

Expression:

~~~text
#roundAmount(#amount, 2)
~~~

Method được đăng ký là overload nhận BigDecimal và int. Không nên kỳ vọng SpEL tự khám phá mọi overload Java chỉ vì chúng có cùng tên.

Nếu cần nhiều dạng gọi, có thể đăng ký các function name riêng cho từng chữ ký hoặc viết một method facade nhận một kiểu đầu vào thống nhất rồi tự xử lý trong Java.

### 3.3. Đối số và giá trị trả về

Số lượng và kiểu đối số trong expression phải tương thích với chữ ký method đã đăng ký.

Ví dụ method:

~~~java
public static BigDecimal addTax(
        BigDecimal amount,
        BigDecimal taxRate) {
    return amount.multiply(BigDecimal.ONE.add(taxRate));
}
~~~

Expression:

~~~text
#addTax(#subtotal, #taxRate)
~~~

Kết quả là BigDecimal và có thể tiếp tục được dùng:

~~~text
#addTax(#subtotal, #taxRate).setScale(2)
~~~

Nếu số lượng đối số không đúng, kiểu không tương thích hoặc việc chuyển đổi thất bại, expression có thể ném lỗi khi đánh giá. Hãy giữ kiểu dữ liệu của variable và tham số method rõ ràng để tránh phụ thuộc vào chuyển đổi không cần thiết.

## 4. Dùng function ở nhiều phần của expression

Sau khi đăng ký, function có thể được gọi ở bất kỳ phần nào của expression mà vị trí đó chấp nhận một giá trị hoặc một điều kiện.

Ví dụ:

~~~text
#isValidCode(#code)
    and #normalizeCode(#code) == #expectedCode
~~~

Cả hai function dùng cùng variable code. Một function kiểm tra tính hợp lệ; function còn lại chuẩn hóa giá trị để so sánh.

Function cũng có thể xuất hiện trong nhánh ternary:

~~~text
#isPremium(#customer)
    ? #calculateDiscount(#order, #customer)
    : 0
~~~

Hoặc được truyền làm đối số cho một bean method:

~~~text
@auditService.record(#formatAuditMessage(#event))
~~~

Trong trường hợp này, SpEL gọi function formatAuditMessage trước, rồi truyền kết quả vào method record của bean auditService. Bean reference vẫn cần BeanResolver trong EvaluationContext.

### 4.1. Dùng function trong selection

Giả sử đã đăng ký function isEligible nhận một Order và trả về boolean:

~~~java
public static boolean isEligible(Order order) {
    return order != null
            && order.getTotal().compareTo(new BigDecimal("100.00")) >= 0;
}
~~~

Expression:

~~~text
#orders.?[#isEligible(#this)]
~~~

Selection gọi function cho từng phần tử và chỉ giữ lại những Order mà function trả về true.

### 4.2. Dùng function trong projection

Nếu có function formatOrder nhận một Order và trả về String:

~~~text
#orders.![#formatOrder(#this)]
~~~

Projection tạo danh sách chuỗi từ collection Order. #this là phần tử hiện tại của collection; function nhận phần tử đó làm đối số.

Có thể kết hợp selection và projection:

~~~text
#orders.?[#isEligible(#this)].![#formatOrder(#this)]
~~~

Đầu tiên lọc collection bằng isEligible, sau đó chuyển từng Order còn lại thành chuỗi bằng formatOrder.

## 5. Function và variable dùng chung namespace

Function được gọi bằng ký hiệu # giống variable, nhưng cách sử dụng khác nhau:

- **#minimumTotal** đọc một giá trị variable.
- **#normalizeCode(#rawCode)** gọi function và truyền đối số.
- **#currentUser.name** đọc property của object được lưu trong variable currentUser.

Trong StandardEvaluationContext, tên function và tên variable dùng chung namespace. Vì vậy, tránh đăng ký function và variable có cùng tên. Một lần setVariable() có thể thay đổi giá trị đang được tra cứu dưới tên đó, và việc đăng ký function cũng có thể ghi đè entry cùng tên.

Ví dụ nên tránh:

~~~java
context.registerFunction("normalize", normalizeMethod);
context.setVariable("normalize", "UPPER");
~~~

Sau khi dùng cùng tên cho variable, expression #normalize(...) không còn được phân giải như function đã đăng ký.

Hãy dùng quy ước tên rõ ràng, ví dụ:

- Function: normalizeCode, isEligible, calculateTax.
- Variable: rawCode, currentUser, taxRate, orders.

### 5.1. Đăng ký Method bằng setVariable()

Ngoài registerFunction(), StandardEvaluationContext còn cho phép đăng ký một Method bằng setVariable():

~~~java
context.setVariable("normalizeCode", normalizeMethod);
~~~

Khi giá trị được đăng ký là Method, SpEL có thể gọi nó như function:

~~~text
#normalizeCode(#rawCode)
~~~

Tuy nhiên, registerFunction() thể hiện rõ ý định đăng ký function hơn và nên được ưu tiên khi API phiên bản Spring đang dùng hỗ trợ phương thức này. Dù dùng cách nào, tên vẫn nằm trong namespace chung với variable.

## 6. Function khác gì bean method và static method call?

Có ba cách thường gặp để gọi logic Java từ SpEL:

| Cách gọi | Ví dụ | Cơ chế |
| --- | --- | --- |
| Registered function | **#normalizeCode(#value)** | Method được đăng ký vào EvaluationContext |
| Spring bean method | **@textPolicy.normalize(#value)** | BeanResolver tìm bean rồi gọi instance method |
| Static method qua type reference | **T(com.example.TextFunctions).normalize(#value)** | TypeLocator tìm class rồi gọi static method |

### 6.1. Khi nào dùng registered function?

Dùng function khi cần một method tiện ích tĩnh, nhỏ, không phụ thuộc vào instance hoặc dependency injection. Tên function có thể ngắn gọn và được giới hạn rõ trong EvaluationContext.

Ví dụ: chuẩn hóa chuỗi, kiểm tra định dạng, tính toán thuần hoặc chuyển đổi một giá trị.

### 6.2. Khi nào dùng bean method?

Dùng bean method khi logic cần dependency do Spring quản lý, cấu hình, trạng thái hoặc phối hợp với repository/service khác:

~~~text
@permissionService.canRead(#document, #currentUser)
~~~

Bean reference cần BeanResolver. Đổi lại, method có thể là instance method và sử dụng dependency đã được inject.

### 6.3. Khi nào dùng T()?

SpEL hỗ trợ type reference bằng toán tử T():

~~~text
T(java.lang.Math).max(#left, #right)
~~~

Cách này phù hợp khi muốn gọi trực tiếp một static method công khai của class. Không cần đăng ký Method thành function, nhưng expression phải tham chiếu type qua TypeLocator và EvaluationContext phải cho phép type reference.

Registered function tạo một alias rõ ràng trong context; T() thể hiện trực tiếp class và method được gọi. Hãy chọn cách phù hợp với độ rõ ràng và phạm vi quyền truy cập mong muốn.

## 7. Function có thể nhận những kiểu đối số nào?

Function nhận các đối số theo chữ ký của Java Method được đăng ký. Các đối số trong expression có thể là literal, variable, property, kết quả của function khác hoặc kết quả của một phép tính.

Ví dụ method:

~~~java
public static BigDecimal calculateFee(
        BigDecimal amount,
        BigDecimal rate,
        boolean priority) {

    BigDecimal fee = amount.multiply(rate);

    return priority
            ? fee.add(new BigDecimal("10.00"))
            : fee;
}
~~~

Expression:

~~~text
#calculateFee(#amount, #feeRate, #priority)
~~~

Có thể truyền literal:

~~~text
#calculateFee(#amount, 0.02, true)
~~~

Hoặc dùng kết quả của function khác làm đối số:

~~~text
#calculateFee(#normalizeAmount(#rawAmount), #feeRate, #priority)
~~~

### 7.1. Chuyển đổi kiểu đối số

SpEL có thể sử dụng TypeConverter của EvaluationContext trong quá trình gọi method. Khả năng chuyển đổi phụ thuộc ConversionService và converter được cấu hình. Không nên giả định mọi chuỗi đều tự động chuyển được sang mọi kiểu domain.

Nếu một function nhận BigDecimal, cách rõ ràng là cung cấp BigDecimal từ variable hoặc tạo nó tường minh:

~~~text
#calculateFee(new java.math.BigDecimal('100.00'), #feeRate, false)
~~~

Nếu việc chuyển đổi là quy tắc riêng của ứng dụng, hãy đăng ký converter phù hợp hoặc thực hiện chuyển đổi trong Java trước khi đưa dữ liệu vào context.

### 7.2. Varargs

Method Java có thể dùng varargs nếu chữ ký được đăng ký hỗ trợ:

~~~java
public static String joinCodes(String separator, String... codes) {
    return String.join(separator, codes);
}
~~~

Expression có thể truyền các đối số tương ứng:

~~~text
#joinCodes('-', 'A1', 'B2', 'C3')
~~~

Khi dùng varargs, hãy bảo đảm số lượng và kiểu đối số khớp với tham số cố định cùng kiểu phần tử của mảng varargs.

## 8. Function trả về null hoặc ném exception

Nếu method trả về null, kết quả function trong SpEL cũng là null. Có thể xử lý kết quả đó bằng toán tử Elvis:

~~~text
#displayName(#user) ?: 'Anonymous'
~~~

Nếu method ném exception, quá trình đánh giá expression thất bại và Spring Expression thường bọc lỗi gốc trong exception của SpEL. Hãy xử lý lỗi nghiệp vụ trong Java method nếu có thể khôi phục một cách có ý nghĩa; đừng dùng function để che giấu mọi lỗi bằng một giá trị mặc định chung.

Function nên xác định rõ hợp đồng với đầu vào null:

~~~java
public static String safeUpper(String value) {
    return value == null ? null : value.toUpperCase(Locale.ROOT);
}
~~~

Với method khác, null có thể là dữ liệu không hợp lệ và cần ném IllegalArgumentException hoặc một exception domain cụ thể. Điều quan trọng là hành vi phải rõ ràng và nhất quán với nơi expression được sử dụng.

## 9. Phạm vi và vòng đời của function

Function được đăng ký trên một EvaluationContext, không phải đăng ký global cho mọi SpEL parser trong JVM.

Ví dụ:

~~~java
StandardEvaluationContext firstContext =
        new StandardEvaluationContext();

firstContext.registerFunction("normalizeCode", normalizeMethod);

StandardEvaluationContext secondContext =
        new StandardEvaluationContext();
~~~

Expression được đánh giá bằng firstContext có thể gọi #normalizeCode(...). Nếu đánh giá cùng expression bằng secondContext, function không tự xuất hiện ở đó; cần đăng ký lại.

Một Expression đã parse có thể được tái sử dụng với nhiều context khác nhau. Expression giữ cấu trúc đã parse, còn các function và variable được phân giải từ EvaluationContext truyền vào mỗi lần getValue().

Một pattern hữu ích là tạo context cho mỗi đơn vị xử lý:

~~~java
StandardEvaluationContext createContext(String rawCode)
        throws NoSuchMethodException {

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Method normalizeMethod = TextFunctions.class
            .getMethod("normalize", String.class);

    context.registerFunction("normalizeCode", normalizeMethod);
    context.setVariable("rawCode", rawCode);

    return context;
}
~~~

Nếu function registration giống nhau trong nhiều context, có thể đặt việc lấy Method và đăng ký vào một factory/helper để tránh lặp code. Không nên dùng chung một context mutable cho nhiều request đồng thời nếu các request cần variable khác nhau.

## 10. Kiểm thử function đã đăng ký

Có thể dùng JUnit để xác nhận function được đăng ký và gọi đúng:

~~~java
class SpelFunctionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void invokesRegisteredStaticMethod() throws Exception {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        Method normalizeMethod = TextFunctions.class
                .getMethod("normalize", String.class);

        context.registerFunction("normalizeCode", normalizeMethod);
        context.setVariable("rawCode", " spring ");

        String result = parser
                .parseExpression("#normalizeCode(#rawCode)")
                .getValue(context, String.class);

        assertEquals("SPRING", result);
    }

    @Test
    void usesFunctionResultInAnotherExpression() throws Exception {
        StandardEvaluationContext context =
                new StandardEvaluationContext();

        Method normalizeMethod = TextFunctions.class
                .getMethod("normalize", String.class);

        context.registerFunction("normalizeCode", normalizeMethod);
        context.setVariable("rawCode", " spring ");

        Boolean result = parser
                .parseExpression(
                    "#normalizeCode(#rawCode) == 'SPRING'"
                )
                .getValue(context, Boolean.class);

        assertEquals(Boolean.TRUE, result);
    }
}
~~~

Các test nên bao gồm:

- Function được đăng ký với tên mong muốn.
- Đối số đúng kiểu và đúng số lượng.
- Kết quả có kiểu và giá trị như mong đợi.
- Đầu vào null hoặc dữ liệu biên theo hợp đồng method.
- Function được gọi trong selection, projection hoặc biểu thức logic nếu ứng dụng dùng các trường hợp đó.
- Context mới chưa đăng ký function và hành vi khi tên function không tồn tại.

Nếu function được dùng trong @Value, @Cacheable hoặc Method Security, hãy kiểm thử cả integration point thực tế để xác nhận context mà Spring tạo có các function/variable cần thiết. Không nên giả định annotation tự động nhận function đã đăng ký trong một StandardEvaluationContext hoàn toàn độc lập.

## 11. Bảo mật khi đăng ký function

Function cho phép expression gọi code Java. Vì vậy, method được đăng ký là một phần của bề mặt quyền truy cập mà expression có thể sử dụng.

Một số nguyên tắc thực tế:

1. Chỉ đăng ký function mà expression thực sự cần.
2. Ưu tiên method thuần, có kết quả xác định và không tạo side effect.
3. Không đăng ký method có thể xóa dữ liệu, thực hiện thanh toán, thay đổi quyền, truy cập bí mật hoặc gọi hệ thống bên ngoài nếu expression không hoàn toàn đáng tin cậy.
4. Không đánh giá SpEL tùy ý do người dùng gửi với một StandardEvaluationContext chứa các function có quyền rộng.
5. Kiểm tra kiểu và giá trị đầu vào trong Java method; không dựa hoàn toàn vào expression để xác thực.
6. Tách context theo phạm vi xử lý để tránh rò rỉ variable hoặc trạng thái giữa các request.
7. Nếu cần logic phụ thuộc service hoặc quyền truy cập phức tạp, cân nhắc một facade bean có API giới hạn thay vì đăng ký nhiều static utility method.

StandardEvaluationContext cung cấp nhiều khả năng của SpEL. Việc chỉ đăng ký một function không tự biến toàn bộ expression thành sandbox. Hãy giới hạn nguồn expression và các tính năng mà context cho phép.

## 12. Những lỗi thường gặp

1. **Quên đăng ký function:** expression gọi #normalizeCode(...) nhưng context chưa đăng ký tên này.
2. **Dùng sai cú pháp:** function được gọi bằng #name(args), không phải @name(args).
3. **Đăng ký nhầm Method overload:** getMethod() phải nhận đúng danh sách kiểu tham số.
4. **Dùng method instance như function:** function registration không cung cấp receiver object; hãy dùng static method hoặc gọi bean instance method qua @beanName.
5. **Sai số lượng hoặc kiểu đối số:** expression phải tương thích với chữ ký Method đã đăng ký.
6. **Trùng tên variable và function:** chúng dùng chung namespace trong StandardEvaluationContext.
7. **Đăng ký vào context khác:** function chỉ có trong context đã đăng ký nó.
8. **Giả định function là bean:** function không được Spring container quản lý và không có dependency injection tự động.
9. **Không xử lý null hoặc exception:** lỗi từ method có thể làm toàn bộ expression thất bại.
10. **Đăng ký function có quyền quá rộng:** expression không tin cậy có thể gọi method đã được mở ra cho nó.

## 13. Ghi nhớ nhanh

- Đăng ký function bằng **StandardEvaluationContext.registerFunction(name, method)**.
- Method được đăng ký là một đối tượng **java.lang.reflect.Method**.
- Ưu tiên **public static method**, vì function invocation không truyền instance receiver.
- Gọi function trong SpEL bằng **#functionName(arguments)**.
- Tên function có thể khác tên method Java.
- Chọn đúng overload khi lấy Method bằng reflection.
- Function có thể nhận literal, variable, property hoặc kết quả của expression khác.
- Giá trị trả về có thể tiếp tục được dùng trong điều kiện, phép toán, selection và projection.
- Function và variable dùng chung namespace; tránh đặt cùng tên.
- Function thuộc EvaluationContext đã đăng ký; context mới cần đăng ký lại.
- Dùng bean reference cho instance method cần dependency injection; dùng T() khi muốn gọi trực tiếp static method qua type reference.
- Chỉ đăng ký các method cần thiết và không đánh giá expression không tin cậy bằng context có quyền quá rộng.

## 14. Tài liệu tham khảo chính thức

- [Spring Framework — Functions in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/functions.html)
- [Spring Framework — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [EvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [Spring Framework — Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
