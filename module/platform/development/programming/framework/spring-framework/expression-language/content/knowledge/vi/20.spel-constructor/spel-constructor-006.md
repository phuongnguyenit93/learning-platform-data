# Kiểu không có constructor phù hợp trong SpEL

Spring Expression Language (SpEL) có thể tạo object mới bằng toán tử **new**. Khi đánh giá expression, SpEL phải tìm một constructor của kiểu được yêu cầu và xác định constructor đó có thể nhận các đối số đang truyền hay không.

Ví dụ:

~~~text
new com.example.Invoice('INV-001', 125.50)
~~~

Expression chỉ hoạt động nếu kiểu Invoice có constructor phù hợp với hai đối số này, hoặc SpEL có thể chuyển đổi các đối số sang kiểu mà constructor yêu cầu. Nếu không có constructor tương thích, quá trình đánh giá thất bại.

Lỗi “không có constructor phù hợp” thường xuất hiện khi số lượng đối số sai, kiểu đối số không tương thích, giá trị không thể chuyển đổi hoặc kiểu chỉ có constructor khác với cách expression đang gọi. Cần phân biệt lỗi này với trường hợp SpEL không tìm thấy class hoặc EvaluationContext không cho phép constructor expression.

## 1. Cú pháp gọi constructor

SpEL dùng từ khóa **new** để tạo object:

~~~text
new fully.qualified.Type(argument1, argument2, ...)
~~~

Với kiểu trong package **java.lang**, có thể bỏ tên package:

~~~text
new String('Spring')
new Integer(42)
~~~

Với kiểu thuộc package khác, dùng tên đầy đủ:

~~~text
new java.math.BigDecimal('125.50')
new java.util.ArrayList()
new com.example.Invoice('INV-001', 125.50)
~~~

Ví dụ trong Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

BigDecimal amount = parser
        .parseExpression("new java.math.BigDecimal('125.50')")
        .getValue(BigDecimal.class);
~~~

SpEL phân tích expression, tìm kiểu BigDecimal, chọn constructor nhận String và tạo object mới. Kết quả trả về là một instance BigDecimal.

Constructor invocation có thể xuất hiện bên trong một expression lớn hơn:

~~~text
new com.example.Customer('CUS-001', 'Linh').displayName
~~~

Hoặc truyền object mới tạo vào một method:

~~~text
@invoiceService.create(new com.example.InvoiceDraft('INV-001'))
~~~

Trong trường hợp này, constructor của InvoiceDraft phải phù hợp với đối số INV-001; sau đó object được truyền vào method create của bean invoiceService.

## 2. SpEL tìm constructor phù hợp như thế nào?

SpEL sử dụng **ConstructorResolver** để tìm constructor có thể xử lý kiểu và các đối số được truyền vào. Với EvaluationContext tiêu chuẩn, Spring cung cấp **ReflectiveConstructorResolver**, implementation dùng Java reflection để tìm constructor trên class.

Quá trình lựa chọn có thể xét các dạng tương thích:

1. **Exact match:** kiểu đối số trùng với kiểu tham số constructor.
2. **Inexact match:** kiểu đối số là subtype có thể truyền vào kiểu tham số constructor.
3. **Match qua chuyển đổi:** đối số có thể được chuyển sang kiểu tham số bằng TypeConverter được đăng ký trong EvaluationContext.

Có thể hiểu rằng SpEL không chỉ đếm số đối số. Nó còn phải xác định kiểu của từng đối số và kiểm tra khả năng truyền các giá trị đó vào constructor.

Ví dụ:

~~~java
public class CustomerKey {

    private final String value;

    public CustomerKey(String value) {
        this.value = value;
    }
}
~~~

Expression sau phù hợp với constructor:

~~~text
new com.example.CustomerKey('CUS-001')
~~~

Nhưng expression sau không phù hợp vì constructor không nhận hai đối số:

~~~text
new com.example.CustomerKey('CUS-001', 'VIP')
~~~

Class tồn tại và expression có cú pháp hợp lệ, nhưng không có constructor nhận đúng số lượng và kiểu đối số như yêu cầu.

## 3. Những nguyên nhân phổ biến khiến không có constructor phù hợp

### 3.1. Sai số lượng đối số

Constructor được khai báo với một số lượng tham số nhất định. Nếu expression truyền thiếu hoặc thừa đối số, resolver không tìm được chữ ký phù hợp.

Ví dụ class:

~~~java
public class Money {

    public Money(BigDecimal amount, Currency currency) {
        // ...
    }
}
~~~

Expression sai:

~~~text
new com.example.Money()
~~~

Expression đúng:

~~~text
new com.example.Money(
    new java.math.BigDecimal('100.00'),
    T(java.util.Currency).getInstance('VND')
)
~~~

Money không có constructor không tham số. Muốn tạo object, phải truyền đủ amount và currency theo chữ ký đã khai báo.

### 3.2. Kiểu đối số không tương thích

Giả sử class có constructor:

~~~java
public class UserId {

    public UserId(UUID value) {
        // ...
    }
}
~~~

Expression truyền String:

~~~text
new com.example.UserId('8f14e45f-ea4d-4f9a-8a2d-123456789abc')
~~~

SpEL chỉ gọi được constructor nếu TypeConverter có thể chuyển String thành UUID trong context đó. Không nên giả định mọi cặp kiểu Java đều có converter mặc định.

Một cách rõ ràng hơn là tạo UUID trước bằng method phù hợp rồi truyền kết quả vào constructor:

~~~text
new com.example.UserId(
    T(java.util.UUID).fromString('8f14e45f-ea4d-4f9a-8a2d-123456789abc')
)
~~~

Khi expression dùng các kiểu hoặc converter đặc thù, cần kiểm tra khả năng chuyển đổi thực tế của EvaluationContext.

### 3.3. Chọn nhầm overload

Một class có thể khai báo nhiều constructor:

~~~java
public class ReportRequest {

    public ReportRequest(String reportId) {
        // ...
    }

    public ReportRequest(String reportId, boolean includeDetails) {
        // ...
    }

    public ReportRequest(String reportId, Locale locale) {
        // ...
    }
}
~~~

Các expression hợp lệ theo những chữ ký tương ứng:

~~~text
new com.example.ReportRequest('RPT-01')
new com.example.ReportRequest('RPT-01', true)
new com.example.ReportRequest(
    'RPT-01',
    T(java.util.Locale).US
)
~~~

Nếu truyền sai số lượng hoặc một giá trị có kiểu không tương thích với overload mong muốn, SpEL không thể gọi constructor đó. Khi có nhiều overload, hãy viết expression với đối số có kiểu rõ ràng để tránh phụ thuộc vào chuyển đổi không cần thiết.

### 3.4. Kiểu tham số là interface hoặc superclass

Một constructor có thể nhận interface hoặc superclass, trong khi expression truyền một implementation cụ thể. Trường hợp này có thể là inexact match nếu kiểu đối số có thể gán cho kiểu tham số.

Ví dụ:

~~~java
public class NotificationJob {

    public NotificationJob(List<String> recipients) {
        // ...
    }
}
~~~

Một ArrayList có thể được truyền vào constructor nhận List:

~~~text
new com.example.NotificationJob(new java.util.ArrayList())
~~~

Ngược lại, nếu constructor yêu cầu một implementation cụ thể nhưng expression tạo ra một kiểu không tương thích, SpEL không thể tự thay thế bằng một object khác.

### 3.5. Constructor chỉ có tham số, nhưng expression gọi constructor rỗng

Java không tự sinh constructor không tham số nếu class đã khai báo constructor khác.

~~~java
public class SearchFilter {

    public SearchFilter(String keyword) {
        // ...
    }
}
~~~

Expression:

~~~text
new com.example.SearchFilter()
~~~

không hợp lệ vì SearchFilter không có constructor rỗng. Cách đúng là truyền keyword:

~~~text
new com.example.SearchFilter('spring')
~~~

Nếu ứng dụng thực sự cần tạo object rỗng, hãy cung cấp constructor không tham số có chủ đích hoặc dùng một factory method phù hợp. Không nên thêm constructor rỗng chỉ để làm expression chạy nếu nó tạo ra trạng thái object không hợp lệ.

### 3.6. Constructor có visibility hoặc kiểu không thể khởi tạo

Constructor phải có thể được cơ chế reflection của SpEL truy cập trong môi trường chạy. Một constructor private hoặc bị giới hạn bởi module/security có thể không được resolver mặc định gọi như mong đợi.

Ngoài ra, interface và abstract class không thể được tạo instance trực tiếp bằng constructor thông thường:

~~~text
new com.example.PaymentProcessor()
~~~

Nếu PaymentProcessor là interface, expression không thể tạo một instance cụ thể từ interface đó. Hãy dùng một implementation có thể khởi tạo hoặc tham chiếu bean do Spring quản lý.

### 3.7. Đối số null và constructor overload

Giá trị null không thể truyền vào tham số primitive như int hoặc boolean. Nếu class có nhiều overload nhận các kiểu reference khác nhau, null cũng có thể khiến việc xác định overload mong muốn trở nên không rõ ràng.

Ví dụ:

~~~java
public class SearchFilter {

    public SearchFilter(String keyword) {
        // ...
    }

    public SearchFilter(Locale locale) {
        // ...
    }
}
~~~

Expression:

~~~text
new com.example.SearchFilter(null)
~~~

không thể hiện rõ constructor nào là mục tiêu. Hãy tránh truyền null khi có nhiều overload reference; dùng một giá trị có kiểu rõ ràng hoặc gọi factory method có tên mô tả ý định.

## 4. Varargs và mảng trong constructor

SpEL hỗ trợ constructor có tham số varargs.

Ví dụ:

~~~java
public class AccessRule {

    public AccessRule(String name, String... roles) {
        // ...
    }
}
~~~

Có thể truyền các đối số varargs:

~~~text
new com.example.AccessRule('invoice-read', 'ADMIN', 'AUDITOR')
~~~

Khi expression có nhiều đối số hơn số tham số cố định, resolver có thể xem xét constructor varargs nếu các giá trị phù hợp với kiểu phần tử của mảng varargs.

SpEL cũng hỗ trợ cú pháp tạo array:

~~~text
new int[] {1, 2, 3, 4}
new String[] {'A', 'B', 'C'}
new int[5]
new int[3][4]
~~~

Array construction là một dạng constructor expression riêng. Khi dùng, hãy phân biệt tạo array với gọi constructor của class thông thường.

## 5. Chuyển đổi kiểu có thể giúp tìm constructor phù hợp

SpEL mặc định sử dụng Spring ConversionService thông qua TypeConverter của EvaluationContext. ConversionService có các converter phổ biến và có thể được mở rộng bằng converter riêng.

Ví dụ, constructor nhận BigDecimal:

~~~java
public class InvoiceAmount {

    public InvoiceAmount(BigDecimal amount) {
        // ...
    }
}
~~~

Expression có thể dùng một String để tạo BigDecimal bên trong:

~~~text
new com.example.InvoiceAmount(
    new java.math.BigDecimal('125.50')
)
~~~

Cách này làm kiểu đối số trở nên rõ ràng trước khi gọi constructor.

Không nên dựa vào giả định rằng SpEL sẽ tự chuyển mọi String thành mọi kiểu domain. Việc chuyển đổi phụ thuộc converter được đăng ký và kiểu dữ liệu đích. Nếu không có converter phù hợp hoặc converter ném lỗi, constructor invocation vẫn thất bại.

### 5.1. Đăng ký converter tùy chỉnh

Nếu ứng dụng có quy tắc chuyển đổi riêng, có thể đăng ký Converter với ConversionService rồi cung cấp service đó qua TypeConverter của EvaluationContext.

Ví dụ converter:

~~~java
public class StringToUserIdConverter
        implements Converter<String, UserId> {

    @Override
    public UserId convert(String source) {
        return new UserId(UUID.fromString(source));
    }
}
~~~

Khi converter được đăng ký trong ConversionService được context sử dụng, SpEL có thể chuyển String sang UserId khi tìm constructor cần kiểu UserId.

Cần phân biệt hai việc:

- **ConstructorResolver** tìm constructor có thể nhận các kiểu đối số.
- **TypeConverter** chuyển đổi giá trị khi cần để phù hợp với tham số.

Converter không tạo ra một constructor còn thiếu. Nó chỉ có thể giúp một constructor hiện có trở nên tương thích với đối số.

## 6. Type resolution khác với constructor resolution

Trước khi tìm constructor, SpEL phải xác định được kiểu được gọi sau từ khóa new. Đây là hai bước riêng biệt:

1. **Type resolution:** TypeLocator tìm class theo tên trong expression.
2. **Constructor resolution:** ConstructorResolver tìm constructor trên class đó có thể nhận các đối số.

Ví dụ:

~~~text
new com.example.CustomerKey('CUS-001')
~~~

Nếu class CustomerKey không nằm trên classpath hoặc classloader không nhìn thấy class, SpEL không thể resolve type. Đây không phải lỗi “class có nhưng không có constructor phù hợp”.

Với kiểu ngoài java.lang, nên dùng tên class đầy đủ để tránh phụ thuộc vào import hoặc cấu hình TypeLocator:

~~~text
new java.math.BigDecimal('10.00')
~~~

Nếu ứng dụng dùng classloader riêng hoặc module boundary, cần bảo đảm TypeLocator có thể nhìn thấy class cần tạo. Khi tên class được resolve thành công nhưng không có constructor phù hợp với đối số, lúc đó mới là vấn đề constructor resolution.

## 7. EvaluationContext có cho phép constructor expression không?

Khả năng của expression phụ thuộc vào EvaluationContext.

- **StandardEvaluationContext** cung cấp đầy đủ các chiến lược đánh giá SpEL và mặc định dùng cơ chế reflection để resolve constructor.
- **SimpleEvaluationContext** được thiết kế cho một tập tính năng giới hạn và loại trừ constructor invocation, type reference và bean reference.

Vì vậy, nếu expression chứa:

~~~text
new com.example.CustomerKey('CUS-001')
~~~

nhưng được đánh giá trong SimpleEvaluationContext, lỗi có thể xuất phát từ việc context không hỗ trợ constructor expression. Không nên chẩn đoán nhầm đây là do CustomerKey thiếu constructor.

Nếu cần tạo object bằng SpEL, hãy dùng EvaluationContext có hỗ trợ tính năng này và chỉ mở quyền cần thiết cho nguồn expression đang xử lý.

## 8. Constructor expression có tạo Spring bean không?

Không. Toán tử **new** gọi constructor Java để tạo object trực tiếp. Object được tạo không tự động trở thành bean do Spring container quản lý.

Ví dụ:

~~~text
new com.example.InvoiceDraft('INV-001')
~~~

Expression tạo một instance InvoiceDraft. Spring không tự động thực hiện quá trình đăng ký bean, quản lý scope, dependency injection, lifecycle callback hoặc tạo proxy cho instance này.

Nếu muốn sử dụng một bean đã được Spring quản lý, hãy tham chiếu bean qua cú pháp **@beanName** tại context có BeanResolver:

~~~text
@invoiceFactory.createDraft('INV-001')
~~~

Hai cách có mục đích khác nhau:

| Cách viết | Cơ chế | Khi nào dùng |
| --- | --- | --- |
| **new com.example.InvoiceDraft(...)** | Gọi constructor trực tiếp | Tạo object giá trị hoặc object ngắn hạn |
| **@invoiceFactory.createDraft(...)** | Gọi method trên Spring bean | Cần factory, dependency hoặc quy tắc tạo object do Spring quản lý |
| **@invoiceDraft** | Resolve bean đã đăng ký | Dùng instance bean do container cung cấp |

Nếu constructor cần nhiều dependency, có quy tắc khởi tạo phức tạp hoặc object phải được Spring quản lý, hãy ưu tiên factory bean hoặc service Java thay vì nhồi quá nhiều logic vào constructor expression.

## 9. Phân biệt các nhóm lỗi khi tạo object

Khi expression dùng new thất bại, hãy xác định lỗi nằm ở giai đoạn nào:

| Nhóm lỗi | Dấu hiệu | Hướng xử lý |
| --- | --- | --- |
| Parse error | Cú pháp new, dấu ngoặc hoặc danh sách đối số không hợp lệ | Sửa cú pháp expression |
| Type resolution error | Không tìm thấy class theo tên | Kiểm tra tên đầy đủ, classpath và TypeLocator/classloader |
| Constructor not found | Class đã được resolve nhưng không có constructor nhận được các đối số | Kiểm tra số lượng, kiểu và overload |
| Conversion error | Cần chuyển đổi đối số nhưng không có converter hoặc chuyển đổi thất bại | Chuẩn hóa kiểu hoặc đăng ký converter phù hợp |
| Access/invocation error | Constructor không thể truy cập hoặc chính constructor ném exception | Kiểm tra visibility, module access và lỗi trong constructor |
| Context restriction | EvaluationContext không hỗ trợ constructor expression | Dùng context có tính năng phù hợp hoặc chuyển việc tạo object sang Java |

Các lỗi đánh giá của SpEL thường được bọc trong hệ exception của Spring Expression. Hãy đọc thông báo gốc và kiểm tra class name, argument types cùng vị trí expression để xác định đúng nguyên nhân. Không nên chỉ sửa số lượng đối số khi vấn đề thực tế là class không resolve được hoặc converter không hoạt động.

## 10. Cách chẩn đoán “không có constructor phù hợp”

Khi gặp lỗi, có thể kiểm tra theo trình tự sau:

1. **Xác nhận class tồn tại:** class có nằm trên runtime classpath và tên trong expression đúng không?
2. **Dùng tên đầy đủ:** với class ngoài java.lang, viết fully qualified class name.
3. **Liệt kê constructor thực tế:** xem constructor nào được khai báo, số lượng tham số và kiểu từng tham số.
4. **So sánh đối số:** xác định kiểu SpEL nhận được từ literal, variable hoặc nested expression.
5. **Kiểm tra chuyển đổi:** nếu hai kiểu khác nhau, xác định ConversionService có converter phù hợp không.
6. **Kiểm tra overload:** nếu có nhiều constructor, làm rõ kiểu đối số để chọn đúng overload.
7. **Kiểm tra EvaluationContext:** context có hỗ trợ constructor expression và có ConstructorResolver phù hợp không?
8. **Kiểm tra khả năng truy cập:** constructor có thể được reflection gọi trong runtime/module hiện tại không?
9. **Kiểm tra thân constructor:** nếu constructor được gọi nhưng ném exception, sửa nguyên nhân trong code khởi tạo.

Một ví dụ minh họa:

~~~java
public class Money {

    private final BigDecimal amount;

    public Money(BigDecimal amount) {
        this.amount = amount;
    }
}
~~~

Expression dễ hiểu và có kiểu đối số rõ ràng:

~~~text
new com.example.Money(
    new java.math.BigDecimal('99.90')
)
~~~

Nếu viết:

~~~text
new com.example.Money('99.90')
~~~

kết quả phụ thuộc khả năng chuyển String sang BigDecimal của TypeConverter trong EvaluationContext. Việc tạo BigDecimal rõ ràng bên trong expression làm cho chữ ký constructor được thể hiện trực tiếp và giảm phụ thuộc vào conversion ngầm.

## 11. Khi cần quy tắc tạo object đặc biệt: ConstructorResolver hoặc factory

Nếu ứng dụng cần cách tạo object không theo constructor reflection thông thường, SpEL cho phép mở rộng bằng **ConstructorResolver**.

Một ConstructorResolver có nhiệm vụ tìm constructor phù hợp trong EvaluationContext và trả về ConstructorExecutor để thực hiện lời gọi. Implementation mặc định là ReflectiveConstructorResolver.

Có thể đăng ký resolver tùy chỉnh trong StandardEvaluationContext khi cần:

- Chỉ cho phép tạo một số kiểu được liệt kê.
- Ánh xạ một tên kiểu logic sang một cách tạo object riêng.
- Hỗ trợ cơ chế khởi tạo đặc thù của ứng dụng.
- Giới hạn hoặc kiểm soát tập constructor có thể được expression gọi.

Tuy nhiên, nếu chỉ cần tạo một object domain thông thường, hãy ưu tiên constructor Java rõ ràng và các converter chuẩn. Nếu object cần nhiều dependency, validation hoặc logic khởi tạo, factory bean/service thường dễ đọc hơn resolver tùy chỉnh.

Ví dụ dùng factory:

~~~java
@Component
public class InvoiceDraftFactory {

    public InvoiceDraft create(String invoiceId, Customer customer) {
        // Kiểm tra và tạo InvoiceDraft theo quy tắc ứng dụng
        return new InvoiceDraft(invoiceId, customer);
    }
}
~~~

Expression:

~~~text
@invoiceDraftFactory.create(#invoiceId, #customer)
~~~

Cách này dùng bean factory do Spring quản lý và cho phép gom validation hoặc logic khởi tạo vào một method Java có thể kiểm thử độc lập.

## 12. Kiểm thử constructor expression

Có thể viết test nhỏ để xác nhận constructor phù hợp được gọi:

~~~java
class ConstructorExpressionTest {

    private final ExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void createsMoneyUsingMatchingConstructor() {
        Money money = parser
                .parseExpression(
                    "new com.example.Money(" +
                    "new java.math.BigDecimal('99.90')"
                    + ")"
                )
                .getValue(Money.class);

        assertEquals(new BigDecimal("99.90"), money.getAmount());
    }

    @Test
    void reportsFailureWhenNoMatchingConstructorExists() {
        assertThrows(EvaluationException.class, () ->
                parser.parseExpression(
                    "new com.example.Money('unexpected', 10)"
                ).getValue(Money.class)
        );
    }
}
~~~

Test đầu xác nhận expression dùng đúng constructor. Test thứ hai minh họa trường hợp không có constructor nhận hai đối số String và Integer như expression cung cấp.

Trong dự án thực tế, nên kiểm tra cả:

- Constructor không tham số và constructor có tham số.
- Overload có kiểu tham số khác nhau.
- Giá trị cần chuyển đổi.
- Constructor varargs.
- Kiểu không thể khởi tạo hoặc constructor không truy cập được.
- Context bị giới hạn không cho phép constructor expression.

Nếu constructor chứa logic nghiệp vụ, hãy kiểm thử logic đó trực tiếp bằng unit test Java. SpEL test chỉ xác nhận expression có thể phân giải và gọi constructor đúng cách.

## 13. Ghi nhớ nhanh

- SpEL tạo object bằng cú pháp **new fully.qualified.Type(arguments)**.
- Với kiểu thuộc java.lang, có thể bỏ package; các kiểu khác nên dùng tên đầy đủ.
- SpEL hỗ trợ varargs và cú pháp tạo array.
- ConstructorResolver tìm constructor theo kiểu và số lượng đối số.
- ReflectiveConstructorResolver xét exact match, subtype-compatible match và khả năng chuyển đổi qua TypeConverter.
- Không có constructor rỗng nếu class đã khai báo constructor khác mà không tự cung cấp constructor không tham số.
- Constructor expression có thể thất bại vì sai arity, kiểu không tương thích, chuyển đổi thất bại hoặc constructor không truy cập được.
- Type resolution và constructor resolution là hai bước riêng biệt.
- SimpleEvaluationContext loại trừ constructor invocation; StandardEvaluationContext cung cấp đầy đủ tính năng hơn.
- **new** tạo object Java trực tiếp, không tạo Spring-managed bean.
- Dùng factory bean/service khi việc tạo object cần dependency, validation hoặc lifecycle do Spring quản lý.
- Khi gặp lỗi, kiểm tra class, constructor signatures, argument types, converter, resolver và EvaluationContext theo thứ tự.

## 14. Tài liệu tham khảo chính thức

- [Spring Framework — Constructor Expressions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html)
- [Spring Framework — EvaluationContext and Type Conversion](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [ReflectiveConstructorResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/ReflectiveConstructorResolver.html)
- [ConstructorResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ConstructorResolver.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
