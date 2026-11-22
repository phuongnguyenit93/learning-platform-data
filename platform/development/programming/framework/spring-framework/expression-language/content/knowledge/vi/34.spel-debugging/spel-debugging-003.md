# Kiểm tra tên biến, bean và function đã đăng ký

Khi debug một biểu thức Spring Expression Language (SpEL), một lỗi thường gặp là biểu thức tham chiếu đến **variable**, **Spring bean** hoặc **function** chưa được đăng ký trong EvaluationContext đang được dùng để đánh giá. Cú pháp của ba loại tham chiếu này khác nhau, cơ chế cung cấp dữ liệu cũng khác nhau và chúng có thể tồn tại trong những context khác nhau.

Một biểu thức có thể parse thành công nhưng thất bại khi gọi getValue vì tên chưa được khai báo, tên bị viết sai chữ hoa/thường, bean resolver chưa được cấu hình hoặc function có chữ ký không phù hợp. Cách debug hiệu quả là xác định loại tham chiếu, kiểm tra đúng EvaluationContext tại thời điểm evaluate rồi xác minh tên và kiểu dữ liệu mà context thực sự cung cấp.

## Phân biệt variable, bean và function

Ba dạng tham chiếu phổ biến:

| Loại | Cú pháp trong SpEL | Cách đăng ký hoặc cung cấp |
|---|---|---|
| Variable | **#minimumPrice** | setVariable(name, value) |
| Bean | **@pricingService** | BeanResolver, thường là BeanFactoryResolver |
| Function | **#normalize(value)** | registerFunction(name, Method) |

Dấu mở đầu giúp xác định SpEL đang tìm gì:

- **#name** yêu cầu một variable trong EvaluationContext.
- **@name** yêu cầu một bean thông qua BeanResolver.
- **#name(...)** gọi một function đã đăng ký dưới tên đó.
- **name** không có dấu # thường là property của root object hiện tại, không phải variable.
- **#root** và **#this** là các biến đặc biệt do SpEL quản lý.

Không nên đổi qua lại các cú pháp này chỉ để thử khắc phục lỗi. Trước tiên, hãy xác định tên trong biểu thức đại diện cho dữ liệu, bean hay function.

## Kiểm tra variable

Ứng dụng đăng ký variable trên EvaluationContext. Với StandardEvaluationContext, có thể dùng **setVariable(...)**:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("minimumPrice", new BigDecimal("50.00"));
context.setVariable("enabled", true);
context.setVariable("region", "VN");
~~~

Trong biểu thức, tên variable phải có dấu #:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression(
                "#enabled and #region == 'VN' and #minimumPrice >= 50");

Boolean accepted =
        expression.getValue(context, Boolean.class);
~~~

Nếu viết **minimumPrice** thay vì **#minimumPrice**, SpEL sẽ tìm property trên root object hiện tại. Nếu root object không có property đó, biểu thức có thể phát sinh lỗi dù variable minimumPrice đã được đăng ký đúng.

Có thể đọc variable từ Java bằng **lookupVariable(...)**:

~~~java
Object minimumPrice =
        context.lookupVariable("minimumPrice");
~~~

Tên truyền vào lookupVariable không có dấu #. Đây là cách kiểm tra giá trị đã đăng ký trong chính context mà ứng dụng định dùng để evaluate.

### Kiểm tra đúng EvaluationContext

Variable thuộc về EvaluationContext, không thuộc về ExpressionParser và cũng không tự gắn vĩnh viễn vào Expression. Nếu ứng dụng parse expression rồi đánh giá bằng một context khác, các variable đã đặt trong context ban đầu sẽ không tự xuất hiện trong context mới.

~~~java
Expression expression =
        parser.parseExpression("#minimumPrice >= 50");

StandardEvaluationContext configuredContext =
        new StandardEvaluationContext();
configuredContext.setVariable(
        "minimumPrice",
        new BigDecimal("75.00"));

StandardEvaluationContext emptyContext =
        new StandardEvaluationContext();

// Đánh giá bằng configuredContext: variable đã được đăng ký.
Boolean first =
        expression.getValue(configuredContext, Boolean.class);

// Đánh giá bằng emptyContext: variable minimumPrice không có ở đây.
~~~

Khi debug, hãy kiểm tra object context được truyền vào đúng lời gọi getValue. Một lỗi thường gặp là khởi tạo variable trong một bean hoặc helper, nhưng ở nơi khác lại tạo context mới rồi đánh giá expression bằng context mới đó.

Nếu expression được cache hoặc tái sử dụng, điều đó không có nghĩa variable được cache theo expression. Mỗi lần đánh giá vẫn dùng root object và EvaluationContext được truyền vào lần gọi đó.

### Kiểm tra tên variable

Tên variable cần nhất quán giữa nơi đăng ký và nơi tham chiếu:

~~~java
context.setVariable("customerId", "CUS-1024");
~~~

Biểu thức đúng:

~~~text
#customerId
~~~

Các tên **#customerID**, **#CustomerId** hoặc **#customer_id** là những tên khác. Không nên giả định tên variable tự động được chuẩn hóa chữ hoa/thường hoặc dấu gạch dưới.

Nên khai báo tên biến dưới dạng hằng số trong Java nếu cùng tên được dùng ở nhiều nơi:

~~~java
public final class SpelVariableNames {
    public static final String CUSTOMER_ID = "customerId";

    private SpelVariableNames() {
    }
}
~~~

~~~java
context.setVariable(
        SpelVariableNames.CUSTOMER_ID,
        customerId);
~~~

Cách này giảm lỗi đánh máy khi tạo context và khi duy trì các expression được lưu trong cấu hình.

### Variable null và variable chưa đăng ký

Một variable có thể được đăng ký với giá trị null:

~~~java
context.setVariable("middleName", null);
~~~

Giá trị null khác với một tên chưa được đăng ký, nhưng khi dùng **lookupVariable(...)**, cả hai tình huống đều có thể cho kết quả null. API này không cung cấp một phép containsVariable công khai để phân biệt chắc chắn hai trường hợp.

Nếu nghiệp vụ cần phân biệt variable chưa có với variable đã khai báo nhưng có giá trị null, hãy duy trì danh sách tên variable được phép hoặc metadata riêng ở lớp ứng dụng. Một lựa chọn khác là dùng kiểu wrapper thể hiện trạng thái có/không có giá trị thay vì dùng null cho nhiều ý nghĩa.

Khi variable có thể null, biểu thức cần xử lý null trước khi truy cập property hoặc gọi method trên giá trị đó.

## Kiểm tra bean reference

Bean reference trong SpEL dùng dấu **@**:

~~~text
@pricingService
~~~

Cú pháp này yêu cầu EvaluationContext có **BeanResolver** để tìm bean theo tên. Chỉ tạo StandardEvaluationContext không tự động làm cho mọi Spring bean có thể được truy cập bằng @.

Với ứng dụng Spring, có thể cấu hình **BeanFactoryResolver**:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setBeanResolver(
        new BeanFactoryResolver(applicationContext));
~~~

Sau khi cấu hình, biểu thức có thể tham chiếu bean:

~~~java
Expression expression =
        parser.parseExpression("@pricingService");
~~~

Hoặc gọi method trên bean nếu method invocation được hỗ trợ:

~~~java
Expression expression =
        parser.parseExpression(
                "@pricingService.calculate(#order)");
~~~

Khi bean reference thất bại, hãy kiểm tra cả hai điều kiện: bean có tồn tại trong BeanFactory hay không và EvaluationContext có BeanResolver phù hợp hay không.

### Kiểm tra tên bean

Tên trong biểu thức phải khớp với tên bean hoặc alias đã đăng ký trong container. Ví dụ:

~~~java
@Component("pricingService")
public class PricingService {
    // ...
}
~~~

Biểu thức tham chiếu:

~~~text
@pricingService
~~~

Nếu bean được đăng ký bằng tên **priceService**, biểu thức @pricingService sẽ không tìm thấy bean đó trừ khi pricingService là alias hợp lệ.

Có thể kiểm tra tên ở phía ứng dụng bằng BeanFactory hoặc ApplicationContext:

~~~java
boolean exists =
        applicationContext.containsBean("pricingService");
~~~

Nếu bean không tồn tại, hãy kiểm tra component scan, profile, conditional configuration, tên bean được khai báo trong @Bean và alias. Cũng cần kiểm tra đúng ApplicationContext nếu ứng dụng có parent context hoặc nhiều context con.

Không nên gọi getBean chỉ để dò tên nếu việc lấy bean có thể khởi tạo một singleton lazy hoặc kích hoạt logic khởi tạo có side effect. containsBean phù hợp hơn cho bước kiểm tra tồn tại cơ bản; việc xác minh bean thực tế cần được thực hiện trong môi trường kiểm thử phù hợp.

### Kiểm tra BeanResolver của context

Một ứng dụng có thể có bean trong ApplicationContext nhưng vẫn không truy cập được bằng cú pháp @ nếu context đánh giá SpEL không có BeanResolver.

Khi tự tạo StandardEvaluationContext, cấu hình rõ ràng:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

context.setBeanResolver(
        new BeanFactoryResolver(applicationContext));
~~~

Nếu expression được đánh giá bởi một integration của Spring, integration đó có thể tự tạo EvaluationContext và cung cấp BeanResolver hoặc một cơ chế truy cập khác. Không nên giả định context do annotation tạo ra giống với context mà ứng dụng tự tạo.

Khi debug, cần tìm đúng nơi tạo context cho expression đó và kiểm tra resolver được gắn ở đó. Thêm BeanResolver vào một context không được dùng trong getValue sẽ không giải quyết được lỗi.

### Bean name khác với variable name

Hai cú pháp có thể cùng chứa một từ nhưng tìm ở hai nơi khác nhau:

~~~java
context.setVariable("pricingService", service);
~~~

- **#pricingService** đọc variable được đăng ký trong context.
- **@pricingService** tìm bean qua BeanResolver.

Đăng ký variable không tạo bean. Đăng ký bean trong Spring cũng không tự tạo variable cùng tên. Nếu biểu thức dùng sai dấu mở đầu, SpEL sẽ tìm sai loại đối tượng.

## Kiểm tra function đã đăng ký

Function trong SpEL được tham chiếu bằng dấu # và theo sau là danh sách đối số:

~~~text
#normalize('  Spring  ')
~~~

Khác với variable đơn thuần, function có dấu ngoặc gọi và được đăng ký bằng một Method Java. StandardEvaluationContext cung cấp **registerFunction(name, method)**.

Ví dụ, định nghĩa function tĩnh:

~~~java
public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase();
    }
}
~~~

Đăng ký method:

~~~java
Method normalizeMethod =
        TextFunctions.class.getMethod(
                "normalize",
                String.class);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.registerFunction(
        "normalize",
        normalizeMethod);
~~~

Sau đó gọi trong expression:

~~~java
Expression expression =
        parser.parseExpression("#normalize('  Spring  ')");

String result =
        expression.getValue(context, String.class);
~~~

Kết quả là **spring**. Tên truyền vào registerFunction không có dấu #; dấu # chỉ được dùng trong biểu thức.

### Kiểm tra method dùng để đăng ký

Khi function không gọi được, hãy xác minh:

- Method lấy được từ đúng class.
- Tên method trong registerFunction khớp với tên trong expression.
- Chữ ký method nhận đúng số lượng và kiểu đối số.
- Method phù hợp với cơ chế function invocation, thông thường là public static.
- Method không bị overload gây nhầm lẫn khi lấy Method bằng reflection.
- Context được truyền vào getValue chính là context đã đăng ký function.

Nên lấy Method bằng getMethod với kiểu tham số cụ thể:

~~~java
Method method =
        TextFunctions.class.getMethod(
                "normalize",
                String.class);
~~~

Cách này xác định rõ overload cần đăng ký. Nếu class có nhiều method cùng tên nhưng khác tham số, không nên tìm method chỉ bằng tên rồi chọn phần tử đầu tiên trong danh sách reflection.

### Phân biệt function và method của object

Function được gọi theo tên đã đăng ký:

~~~text
#normalize(#input)
~~~

Method của object được gọi trên một target:

~~~text
#customer.getName()
~~~

Function không phải Spring bean và không được tham chiếu bằng @. Nó cũng không tự động xuất hiện chỉ vì class Java có static method. Ứng dụng phải đăng ký Method vào EvaluationContext trước khi expression gọi function.

Nếu muốn gọi một method của Spring service, hãy dùng bean reference và method invocation khi context cho phép, hoặc gọi service từ Java rồi truyền kết quả vào context. Không cần đăng ký cùng một service method như function nếu bean reference đã đáp ứng use case.

### Function và variable dùng cùng dấu #

Variable và function đều dùng dấu #, nên cần phân biệt hình thức tham chiếu:

- **#threshold** đọc giá trị variable.
- **#normalize(value)** gọi function.
- **#root** và **#this** là biến đặc biệt của SpEL.

Tránh đăng ký một tên vừa làm variable vừa làm function. Tên trùng nhau làm biểu thức khó hiểu và có thể gây xung đột trong cơ chế lưu trữ variable/function của context. Dùng quy ước tên riêng, ví dụ variable là danh từ và function là động từ.

## Kiểm tra trong đúng loại EvaluationContext

Không phải mọi EvaluationContext đều hỗ trợ cùng khả năng:

| Khả năng | StandardEvaluationContext | SimpleEvaluationContext |
|---|---|---|
| Root object và property access | Có, có thể cấu hình | Có, trong phạm vi builder/accessor |
| Variable | Có | Có trong các cấu hình được hỗ trợ |
| Bean reference | Có nếu gắn BeanResolver | Không hỗ trợ bean reference |
| Type reference T(...) | Có với TypeLocator | Không hỗ trợ |
| Constructor invocation | Có với ConstructorResolver | Không hỗ trợ |
| Method invocation | Có theo resolver được cấu hình | Không bật mặc định; có thể giới hạn qua builder phù hợp |
| Function registration | Hỗ trợ qua StandardEvaluationContext | Không cung cấp đầy đủ khả năng như StandardEvaluationContext |

Nếu expression dùng @bean hoặc function nhưng context thực tế là một context giới hạn, hãy kiểm tra khả năng của loại context đó trước khi tìm lỗi ở tên. Có thể phải chuyển phần xử lý ra Java hoặc dùng StandardEvaluationContext với các resolver được giới hạn rõ ràng.

## Phân biệt lỗi parse và lỗi evaluation

Tên variable, bean hoặc function thường được tra cứu khi expression được đánh giá. Vì vậy, chuỗi có thể parse thành công nhưng thất bại ở getValue.

Hai giai đoạn cần phân biệt:

- **ParseException:** chuỗi không đúng cú pháp SpEL, ví dụ thiếu dấu ngoặc hoặc viết sai cấu trúc lời gọi.
- **EvaluationException:** biểu thức đúng cú pháp nhưng tên không tồn tại trong context, resolver không được cấu hình hoặc lời gọi không thể thực hiện với dữ liệu hiện tại.

Ví dụ:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("#normalize(#name)");
} catch (ParseException ex) {
    throw new IllegalArgumentException(
            "Invalid SpEL syntax", ex);
}

try {
    String result =
            expression.getValue(context, String.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot resolve or invoke the expression reference", ex);
}
~~~

Nếu lỗi nằm ở function, kiểm tra tên đăng ký và Method. Nếu lỗi nằm ở bean, kiểm tra BeanResolver và tên bean. Nếu lỗi nằm ở variable, kiểm tra setVariable và context được truyền vào. Không nên sửa cú pháp khi nguyên nhân thực tế là thiếu registration.

## Quy trình debug có hệ thống

Khi một expression báo không tìm thấy variable, bean hoặc function, có thể kiểm tra theo thứ tự:

1. **Xác định cú pháp tham chiếu.** Dấu # là variable/function; dấu @ là bean; tên không có dấu # thường là property của root object.
2. **Xác định context thực tế.** Tìm nơi tạo EvaluationContext và object được truyền vào getValue.
3. **Kiểm tra registration.** Với variable, dùng lookupVariable; với bean, kiểm tra BeanFactory và BeanResolver; với function, kiểm tra Method được registerFunction.
4. **So khớp tên chính xác.** Kiểm tra chữ hoa/thường, alias, prefix và lỗi đánh máy.
5. **Kiểm tra kiểu dữ liệu.** Xác nhận số lượng và kiểu đối số của function/method, kiểu root object và kiểu property.
6. **Kiểm tra resolver.** Xác nhận context có PropertyAccessor, MethodResolver hoặc BeanResolver phù hợp.
7. **Tách parse và evaluation.** Ghi nhận lỗi ở đúng giai đoạn.
8. **Tạo ví dụ tối thiểu.** Dùng một context nhỏ, một expression và một bộ dữ liệu cố định để tái hiện.

Một ví dụ kiểm tra variable:

~~~java
Object value =
        context.lookupVariable("minimumPrice");

if (value == null) {
    // Kiểm tra thêm metadata ứng dụng nếu null có thể là giá trị hợp lệ.
}
~~~

Một ví dụ kiểm tra bean:

~~~java
if (!applicationContext.containsBean("pricingService")) {
    throw new IllegalStateException(
            "Required bean is not registered");
}
~~~

Một ví dụ kiểm tra function:

~~~java
Method method =
        TextFunctions.class.getMethod(
                "normalize",
                String.class);

context.registerFunction("normalize", method);
~~~

Các bước trên phải chạy trên chính context hoặc cấu hình tạo ra context được dùng để đánh giá. Kiểm tra một context test khác không chứng minh context production đã được cấu hình giống vậy.

## Kiểm thử registration bằng JUnit

Nên có test nhỏ chứng minh variable, bean và function được cung cấp đúng:

~~~java
@Test
void evaluatesVariableAndFunction() throws Exception {
    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable("name", "Spring");

    Method normalize =
            TextFunctions.class.getMethod(
                    "normalize",
                    String.class);

    context.registerFunction("normalize", normalize);

    Expression expression =
            new SpelExpressionParser()
                    .parseExpression("#normalize(#name)");

    String result =
            expression.getValue(context, String.class);

    assertEquals("spring", result);
}
~~~

Với bean reference, test cần cấu hình BeanResolver hoặc dùng context do Spring tạo trong integration test:

~~~java
context.setBeanResolver(
        new BeanFactoryResolver(applicationContext));
~~~

Sau đó đánh giá expression dùng @beanName và xác nhận bean đúng được gọi. Có thể dùng bean giả hoặc spy để kiểm tra số lần gọi và đối số.

Ngoài test thành công, hãy test các trường hợp sai tên, thiếu registration, sai kiểu đối số và context không hỗ trợ capability. Test cần xác nhận lỗi được báo ở giai đoạn phù hợp và không có bean hoặc function ngoài dự kiến bị gọi.

## Kiểm tra context của annotation và Spring integration

Khi SpEL được dùng trong annotation hoặc một module Spring, framework có thể tạo EvaluationContext riêng và tự cung cấp một số biến, bean resolver hoặc root object. Những giá trị này không nhất thiết giống context mà ứng dụng tự tạo bằng new StandardEvaluationContext().

Ví dụ, Spring Cache có thể cung cấp thông tin phương thức và tham số cho biểu thức key. Spring Security có thể cung cấp root object và các biến theo ngữ cảnh bảo mật. Không nên giả định tên biến của một integration sẽ tồn tại trong integration khác.

Nếu lỗi chỉ xảy ra trong annotation:

- Xác định integration nào đang đánh giá expression.
- Tra cứu root object và biến mà integration đó cung cấp.
- Kiểm tra tên tham số có được phát hiện đúng hay không.
- Xác nhận bean/function có được integration expose hay cần cấu hình riêng.
- Tạo integration test chạy qua chính annotation hoặc interceptor thay vì chỉ test parser độc lập.

Một StandardEvaluationContext tự tạo không mô phỏng đầy đủ context mà module Spring cụ thể tạo ra.

## Logging và chẩn đoán mà không lộ dữ liệu nhạy cảm

Khi debug, nên ghi nhận:

- Mã hoặc tên rule.
- Loại tham chiếu bị lỗi: variable, bean, function hay root property.
- Tên tham chiếu đã chuẩn hóa theo chính sách logging.
- Loại EvaluationContext đang sử dụng.
- Giai đoạn lỗi: parse hay evaluation.
- Kiểu root object và kiểu đối số cần thiết, nếu không nhạy cảm.

Tránh ghi toàn bộ giá trị variable, object hoặc đối số function nếu chúng có thể chứa token, thông tin cá nhân hoặc dữ liệu nghiệp vụ nhạy cảm. Với lỗi do người dùng nhập expression, không trả stack trace hoặc tên class nội bộ cho người dùng cuối.

## Checklist ngắn

- Dùng # cho variable/function, @ cho bean và tên property trực tiếp cho root object.
- Đăng ký variable trên đúng EvaluationContext bằng setVariable.
- Dùng lookupVariable để kiểm tra variable; nhớ rằng null không phân biệt được chưa đăng ký với đã đăng ký null.
- Cấu hình BeanResolver, chẳng hạn BeanFactoryResolver, trước khi dùng @beanName trong context tự tạo.
- Kiểm tra tên bean hoặc alias trong đúng ApplicationContext.
- Đăng ký function bằng Method phù hợp qua registerFunction.
- Kiểm tra chữ ký, số lượng và kiểu đối số của function.
- Tránh trùng tên variable và function.
- Kiểm tra khả năng của SimpleEvaluationContext hay StandardEvaluationContext thực tế.
- Phân biệt ParseException với EvaluationException.
- Kiểm tra context được truyền vào getValue, không chỉ context đã cấu hình ở nơi khác.
- Test cả registration thành công và trường hợp thiếu/sai tên.

## Kết luận

Để debug tên variable, bean và function trong SpEL, trước hết phải phân biệt đúng cú pháp: **#variable**, **@beanName** và **#function(arguments)**. Variable được đặt bằng setVariable trên EvaluationContext; bean cần BeanResolver để tra cứu trong Spring container; function cần một Method được đăng ký bằng registerFunction.

Một expression parse thành công vẫn có thể lỗi khi evaluate nếu context không chứa tên cần thiết hoặc không hỗ trợ loại tham chiếu đó. Hãy kiểm tra đúng context được truyền vào getValue, xác minh tên và kiểu đối số, tách lỗi parse với lỗi evaluation và viết test trên chính cấu hình context của ứng dụng. Cách kiểm tra theo từng loại tham chiếu sẽ giúp tìm nguyên nhân nhanh mà không phải mở rộng quyền truy cập một cách không cần thiết.
