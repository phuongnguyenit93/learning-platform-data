# Khởi tạo object với constructor arguments

Spring Expression Language (SpEL) cho phép tạo object Java ngay trong biểu thức bằng cú pháp **new**. Biểu thức có thể gọi constructor không tham số, constructor có đối số, constructor overload hoặc lồng một lời gọi constructor bên trong lời gọi khác. Các đối số được đánh giá trong EvaluationContext và có thể được chuyển đổi sang kiểu tham số thông qua TypeConverter khi cấu hình hỗ trợ.

Khả năng này hữu ích khi cần tạo một value object, một đối tượng dữ liệu nhỏ hoặc một argument để truyền vào method. Tuy nhiên, cần phân biệt việc tạo object bằng SpEL với việc Spring tạo bean trong ApplicationContext: constructor invocation không tự động thực hiện dependency injection, quản lý scope, lifecycle hay AOP của Spring.

## 1. Cú pháp khởi tạo object

### 1.1. Gọi constructor bằng new

Cú pháp tổng quát:

~~~java
new FullyQualifiedClassName(argument1, argument2, ...)
~~~

Ví dụ tạo String:

~~~java
new String('Spring Expression Language')
~~~

Ví dụ tạo một object miền:

~~~java
new com.example.domain.Customer('C-100', 'An')
~~~

SpEL tìm lớp theo tên kiểu, chọn constructor phù hợp với các đối số rồi gọi constructor đó khi biểu thức được đánh giá.

Không cần dùng **T(...)** trước tên lớp khi gọi constructor. **T(...)** dùng để tham chiếu một kiểu, thường nhằm truy cập thành viên static; **new ...(...)** dùng để tạo instance.

### 1.2. Constructor không tham số

Nếu lớp có constructor không tham số có thể truy cập, biểu thức có thể tạo object mà không truyền argument:

~~~java
new com.example.domain.SearchCriteria()
~~~

Ví dụ:

~~~java
public class SearchCriteria {

    private String keyword;

    public SearchCriteria() {
    }

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }
}
~~~

Biểu thức trên tạo một SearchCriteria mới. Các field sẽ nhận giá trị mặc định của Java hoặc giá trị mà constructor gán.

Việc tạo thành công phụ thuộc lớp có trên classpath, TypeLocator phân giải được tên lớp và constructor phù hợp có thể được gọi.

### 1.3. Constructor có đối số

Với constructor yêu cầu dữ liệu ban đầu, truyền các argument theo thứ tự khai báo:

~~~java
public class Customer {

    private final String code;
    private final String name;

    public Customer(String code, String name) {
        this.code = code;
        this.name = name;
    }

    public String getCode() {
        return code;
    }

    public String getName() {
        return name;
    }
}
~~~

Biểu thức:

~~~java
new com.example.domain.Customer('C-100', 'An')
~~~

Đối số thứ nhất được dùng cho code, đối số thứ hai cho name. Thứ tự và khả năng chuyển đổi phải phù hợp với một constructor có thể truy cập.

### 1.4. Kiểu kết quả

Constructor invocation trả về instance của lớp được tạo. Có thể nhận kết quả bằng kiểu cụ thể:

~~~java
Customer customer = parser
        .parseExpression(
                "new com.example.domain.Customer('C-100', 'An')"
        )
        .getValue(context, Customer.class);
~~~

Hoặc nhận dưới kiểu Object khi chưa biết trước kiểu kết quả:

~~~java
Object value = parser
        .parseExpression(
                "new com.example.domain.Customer('C-100', 'An')"
        )
        .getValue(context);
~~~

Nếu constructor trả về object đúng kiểu yêu cầu, không cần chuyển đổi kết quả. Tham số kiểu trong **getValue(context, Target.class)** là yêu cầu kiểu kết quả từ phía caller; nó khác với việc chuyển đổi các argument trước khi gọi constructor.

## 2. Phân giải tên lớp với TypeLocator

### 2.1. Tên lớp đầy đủ

Tên lớp trong constructor expression được phân giải thông qua TypeLocator của EvaluationContext. Cách rõ ràng nhất là dùng tên đầy đủ gồm package và class:

~~~java
new com.example.domain.Customer('C-100', 'An')
~~~

Tên đầy đủ giúp tránh phụ thuộc vào import prefix và giảm khả năng trùng tên giữa các lớp.

### 2.2. Dùng import prefix với StandardTypeLocator

StandardTypeLocator hỗ trợ đăng ký package prefix để có thể viết tên lớp ngắn hơn:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("com.example.domain");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

Sau khi đăng ký package, có thể viết:

~~~java
new Customer('C-100', 'An')
~~~

Package **java.lang** được đăng ký mặc định trong StandardTypeLocator, nên có thể tham chiếu các lớp như String bằng tên ngắn.

Import prefix chỉ giúp phân giải tên ngắn. Nếu cần giới hạn những lớp được phép khởi tạo, không nên xem danh sách import của StandardTypeLocator là allowlist bảo mật. Tên lớp đầy đủ vẫn có thể được phân giải. Khi cần giới hạn thực sự, hãy dùng TypeLocator tùy chỉnh có kiểm tra allowlist.

### 2.3. Cấu hình ClassLoader

StandardTypeLocator có thể được tạo với một ClassLoader cụ thể:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator(applicationClassLoader);
~~~

Điều này hữu ích khi ứng dụng chạy trong môi trường có nhiều class loader, plugin hoặc module. ClassLoader phải nhìn thấy lớp cần khởi tạo.

Nếu lớp không nằm trong classpath hoặc ClassLoader được chọn không thể tải lớp, constructor expression sẽ thất bại khi đánh giá.

## 3. Đối số constructor là biểu thức SpEL

### 3.1. Dùng literal làm argument

Các literal thường dùng có thể truyền trực tiếp:

~~~java
new com.example.domain.Customer('C-100', 'An')
new java.math.BigDecimal('125.50')
new java.lang.String('hello')
~~~

Kiểu literal ảnh hưởng đến kiểu argument mà SpEL cung cấp cho quá trình phân giải constructor. Nếu constructor yêu cầu kiểu khác, TypeConverter có thể tham gia khi có chuyển đổi phù hợp.

### 3.2. Dùng property của root object

Đối số không cần là literal cố định. Có thể lấy dữ liệu từ root object:

~~~java
new com.example.domain.Customer(order.customerCode, order.customerName)
~~~

Khi đánh giá, SpEL đọc các property từ root object và truyền giá trị tương ứng vào constructor.

Nếu property trung gian có thể null, hãy kiểm tra trước hoặc dùng safe navigation ở vị trí phù hợp. Constructor có thể chấp nhận null cho kiểu tham chiếu, nhưng không thể nhận null cho tham số primitive.

### 3.3. Dùng biến trong EvaluationContext

Có thể truyền dữ liệu đã được ứng dụng chuẩn bị qua biến:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("customerCode", "C-100");
context.setVariable("customerName", "An");
~~~

Biểu thức:

~~~java
new com.example.domain.Customer(#customerCode, #customerName)
~~~

Biến được tham chiếu bằng dấu **#**. Cách này giúp tách dữ liệu khỏi chuỗi biểu thức, đặc biệt hữu ích khi dữ liệu đến từ request hoặc database.

Không nối trực tiếp giá trị người dùng vào source expression. Hãy giữ expression cố định và truyền giá trị qua biến context để dữ liệu không bị diễn giải lại như cú pháp SpEL.

### 3.4. Lồng constructor expression

Argument có thể là một constructor expression khác:

~~~java
new com.example.domain.Order(
    'O-100',
    new com.example.domain.Customer('C-100', 'An')
)
~~~

Ví dụ này tạo Customer trước để truyền làm argument cho constructor Order. Các biểu thức lồng nhau giúp mô tả object graph nhỏ ngay trong một expression.

Nếu cấu trúc có nhiều tầng hoặc nhiều object, nên tạo object trong Java rồi truyền object đã hoàn chỉnh vào context. Expression quá dài sẽ khó đọc, khó debug và khó kiểm soát chi phí.

## 4. Chuyển đổi kiểu của constructor arguments

### 4.1. TypeConverter tham gia như thế nào?

Constructor có chữ ký xác định kiểu tham số. Nếu argument trong expression có kiểu khác, SpEL có thể yêu cầu TypeConverter chuyển giá trị sang kiểu đích khi có converter phù hợp.

Ví dụ constructor:

~~~java
public class Customer {
    public Customer(Long id) {
        // Khởi tạo
    }
}
~~~

Expression truyền một String:

~~~java
new com.example.domain.Customer('42')
~~~

Nếu TypeConverter hỗ trợ String sang Long, argument có thể được chuyển thành giá trị Long trước khi constructor được gọi.

Khả năng chuyển đổi phụ thuộc TypeConverter và ConversionService đang được cấu hình. Không nên giả định mọi cặp kiểu đều tự chuyển đổi được.

### 4.2. StandardTypeConverter và ConversionService

StandardEvaluationContext sử dụng TypeConverter mặc định dựa trên cơ chế chuyển đổi của Spring. Ứng dụng có thể cung cấp ConversionService riêng:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);
~~~

Nếu cần chuyển String thành kiểu miền, đăng ký converter trên ConversionService:

~~~java
public record CustomerCode(String value) {
}
~~~

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

Constructor:

~~~java
public class Customer {
    public Customer(CustomerCode code) {
        // Khởi tạo
    }
}
~~~

Expression:

~~~java
new com.example.domain.Customer('C-100')
~~~

TypeConverter có thể dùng converter đã đăng ký để tạo CustomerCode trước khi gọi constructor.

Converter nên kiểm tra dữ liệu và từ chối giá trị không hợp lệ theo quy tắc miền. Việc chuyển đổi thành công về mặt kiểu Java không đảm bảo dữ liệu đúng nghiệp vụ.

### 4.3. Null và primitive

Tham số kiểu tham chiếu có thể nhận null nếu constructor và domain cho phép:

~~~java
new com.example.domain.Customer(null, 'An')
~~~

Ngược lại, tham số primitive như **int**, **long** hoặc **boolean** không thể nhận null. Nếu argument là null hoặc không chuyển đổi được sang primitive, lời gọi constructor sẽ thất bại.

Khi dữ liệu có thể thiếu, hãy quyết định rõ nên dùng wrapper như Integer hay kiểm tra bắt buộc trước khi tạo object. Không nên tự thay null bằng 0 hoặc false nếu nghiệp vụ chưa định nghĩa giá trị mặc định đó.

## 5. Constructor overload

### 5.1. Lớp có nhiều constructor

Java cho phép một lớp khai báo nhiều constructor cùng tên nhưng khác danh sách tham số:

~~~java
public class SearchCriteria {

    public SearchCriteria() {
    }

    public SearchCriteria(String keyword) {
    }

    public SearchCriteria(String keyword, int pageSize) {
    }
}
~~~

SpEL phải chọn constructor phù hợp với số lượng và kiểu argument:

~~~java
new com.example.domain.SearchCriteria()
~~~

~~~java
new com.example.domain.SearchCriteria('spring')
~~~

~~~java
new com.example.domain.SearchCriteria('spring', 20)
~~~

Mỗi biểu thức cung cấp số argument khác nhau và có thể dẫn đến constructor khác nhau.

### 5.2. Khi kiểu argument khác kiểu tham số

Quá trình phân giải constructor xem xét khả năng tương thích và chuyển đổi kiểu. Ví dụ, literal số có thể có kiểu khác với kiểu tham số constructor; TypeConverter có thể hỗ trợ chuyển đổi nếu phù hợp.

Không nên dựa vào suy đoán rằng constructor có kiểu gần giống literal nhất luôn được chọn trong mọi trường hợp. Nếu nhiều constructor có thể nhận argument sau chuyển đổi, kết quả phụ thuộc quy tắc phân giải của Spring và cấu hình converter.

Để tránh mơ hồ:

- Thiết kế số lượng overload vừa phải.
- Tránh nhiều constructor có kiểu tham số dễ chuyển đổi qua lại.
- Dùng kiểu argument rõ ràng khi có thể.
- Kiểm thử từng trường hợp với phiên bản Spring thực tế.
- Cân nhắc static factory method có tên riêng khi các cách khởi tạo mang ý nghĩa khác nhau.

### 5.3. Constructor varargs

Java cũng cho phép constructor có tham số varargs:

~~~java
public class TagSet {

    private final String[] tags;

    public TagSet(String... tags) {
        this.tags = tags;
    }
}
~~~

Có thể viết expression truyền nhiều argument:

~~~java
new com.example.domain.TagSet('java', 'spring', 'spel')
~~~

Việc phân giải constructor varargs và chuyển đổi từng phần tử cần được kiểm thử với phiên bản Spring và TypeConverter mà ứng dụng sử dụng. Khi có nhiều overload varargs, khả năng mơ hồ tăng lên; nên giữ API khởi tạo đơn giản và rõ kiểu.

## 6. Constructor invocation khác Spring bean creation

### 6.1. Object được tạo trực tiếp

Biểu thức:

~~~java
new com.example.domain.Customer('C-100', 'An')
~~~

gọi constructor Java để tạo một instance mới. Object này không tự động được đăng ký vào ApplicationContext.

Do đó, nó không tự nhận:

- Dependency injection từ Spring.
- Bean lifecycle callbacks như một Spring bean thông thường.
- Bean scope do container quản lý.
- AOP proxy hoặc các interceptor được cấu hình qua Spring.
- Các post-processor áp dụng trong quy trình tạo bean của container.

Nếu constructor cần một dependency, expression phải truyền dependency đó như một argument nếu thiết kế cho phép; SpEL không tự động autowire dependency vào object vừa tạo.

### 6.2. Khi nào nên dùng constructor expression?

Constructor expression phù hợp với:

- Value object nhỏ, bất biến.
- DTO hoặc object dữ liệu đơn giản.
- Argument tạm thời cho một method.
- Kiểu miền có constructor rõ ràng và ít tác dụng phụ.

Ví dụ:

~~~java
new com.example.domain.Money('125.50', 'VND')
~~~

### 6.3. Khi nào nên dùng Spring bean?

Nếu object cần dependency injection, lifecycle, scope, proxy hoặc cấu hình container, hãy để Spring tạo và quản lý object đó. Khi expression cần gọi một bean, hãy dùng bean reference với BeanResolver được cấu hình và giới hạn phù hợp.

Không dùng **new** để cố tạo một service Spring phức tạp. Việc gọi constructor trực tiếp có thể tạo object thiếu dependency hoặc bỏ qua các cơ chế mà ứng dụng trông đợi từ container.

## 7. ConstructorResolver và quyền truy cập

### 7.1. Cơ chế phân giải constructor

EvaluationContext có ConstructorResolver để tìm constructor phù hợp. StandardEvaluationContext mặc định sử dụng resolver dựa trên reflection của Spring.

Quy trình tổng quát:

1. TypeLocator phân giải tên lớp thành Class.
2. ConstructorResolver tìm constructor có thể nhận các argument.
3. TypeConverter hỗ trợ chuyển đổi argument khi cần.
4. ConstructorExecutor thực thi constructor và trả về instance.

TypeLocator, ConstructorResolver và TypeConverter có trách nhiệm khác nhau. Nếu tên lớp không phân giải được, kiểm tra TypeLocator. Nếu không có constructor phù hợp, kiểm tra chữ ký và quyền truy cập constructor. Nếu argument sai kiểu, kiểm tra TypeConverter.

### 7.2. Constructor cần có khả năng truy cập

Nên dùng constructor public cho các kiểu được khởi tạo từ expression. Constructor private hoặc package-private có thể không được resolver mặc định truy cập theo cách mong muốn; không nên dựa vào khả năng truy cập reflection vượt quyền của ứng dụng.

Nếu lớp không có constructor phù hợp hoặc constructor không thể được gọi trong môi trường hiện tại, SpEL sẽ phát sinh lỗi khi evaluate.

### 7.3. ClassLoader và module

Trong ứng dụng có module hoặc class loader riêng, lớp có thể tồn tại nhưng không được ClassLoader của TypeLocator nhìn thấy. Quyền truy cập reflection cũng có thể bị giới hạn bởi module system hoặc cấu hình runtime.

Hãy kiểm tra classpath, ClassLoader và khả năng truy cập constructor trong môi trường triển khai thực tế, không chỉ trong IDE.

## 8. Kết hợp constructor với method và collection

Constructor expression có thể được dùng làm argument cho một method:

~~~java
#orderService.create(
    new com.example.domain.Customer('C-100', 'An')
)
~~~

Có thể tạo object rồi gọi method của object đó trong cùng biểu thức:

~~~java
new com.example.domain.Money('100.00', 'VND').amount
~~~

Cũng có thể tạo collection chứa object mới:

~~~java
{
    new com.example.domain.Customer('C-100', 'An'),
    new com.example.domain.Customer('C-200', 'Binh')
}
~~~

Những biểu thức này hữu ích cho dữ liệu nhỏ và có cấu trúc đơn giản. Nếu danh sách dài hoặc object graph phức tạp, nên chuẩn bị trong Java để dễ validate, kiểm thử và quản lý vòng đời.

Constructor expression tạo instance mới khi được đánh giá. Nếu expression được đánh giá nhiều lần, constructor có thể được gọi nhiều lần. Không nên giả định object được cache hoặc dùng chung giữa các lần evaluate.

## 9. Lỗi thường gặp khi khởi tạo object

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy type | Tên lớp sai hoặc TypeLocator không phân giải được | Dùng tên đầy đủ hoặc đăng ký import prefix |
| Không tìm thấy constructor | Sai số argument hoặc không có chữ ký phù hợp | Kiểm tra constructor và thứ tự tham số |
| Constructor không truy cập được | Visibility hoặc giới hạn reflection/module | Dùng constructor public và kiểm tra runtime |
| Argument không chuyển được | TypeConverter thiếu converter phù hợp | Cấu hình ConversionService hoặc sửa kiểu đầu vào |
| Null truyền vào primitive | Primitive không nhận null | Dùng wrapper hoặc validate trước |
| Chọn overload ngoài dự kiến | Nhiều constructor tương thích sau chuyển đổi | Giảm overload, làm rõ kiểu argument |
| Constructor ném exception | Validation hoặc logic khởi tạo thất bại | Xử lý lỗi ở tầng Java và giữ nguyên nguyên nhân |
| Object thiếu dependency | Nhầm constructor invocation với Spring bean creation | Để container tạo bean hoặc truyền dependency rõ ràng |
| Biểu thức lồng nhau khó đọc | Object graph được tạo trực tiếp quá phức tạp | Chuẩn bị object trong Java rồi đưa vào context |

Parse thành công chỉ cho biết cấu trúc biểu thức hợp lệ. Việc tìm lớp, chọn constructor, chuyển đổi argument và chạy constructor diễn ra khi đánh giá, nên các lỗi này thường xuất hiện ở giai đoạn evaluate.

## 10. Giới hạn bảo mật khi cho phép constructor expression

Constructor expression có thể khởi tạo lớp mà TypeLocator phân giải được. Nếu người dùng không tin cậy có thể kiểm soát expression và context cho phép tham chiếu type rộng, họ có thể yêu cầu tạo object ngoài dự kiến.

Một số nguyên tắc:

- Không đánh giá expression không tin cậy bằng StandardEvaluationContext có quyền rộng.
- Nếu cần giới hạn lớp, dùng TypeLocator tùy chỉnh có allowlist thực sự.
- Không cho phép người dùng tự cung cấp tên lớp rồi ghép trực tiếp vào source expression.
- Chỉ cung cấp root object và biến cần thiết.
- Hạn chế constructor của lớp có tác dụng phụ, truy cập hệ thống hoặc cấp phát tài nguyên lớn.
- Kiểm soát số lượng object và kích thước dữ liệu đầu vào.
- Cân nhắc SimpleEvaluationContext khi chỉ cần tập tính năng SpEL giới hạn; context này không cung cấp constructor reference như StandardEvaluationContext.
- Không xem allowlist TypeLocator là ranh giới bảo mật duy nhất nếu context còn cho phép gọi method hoặc truy cập bean rộng.

Constructor có thể thực hiện bất kỳ logic nào mà code của nó được viết để thực hiện. Vì vậy, ưu tiên constructor nhẹ, xác định và không có I/O hoặc tác dụng phụ ngoài dự kiến.

## 11. Ví dụ hoàn chỉnh

Giả sử có value object CustomerCode và Customer:

~~~java
public record CustomerCode(String value) {
    public CustomerCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer code is required"
            );
        }
    }
}

public record Customer(
        CustomerCode code,
        String name
) {
}
~~~

Cấu hình TypeLocator và TypeConverter:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("com.example.domain");

context.setTypeLocator(typeLocator);
context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

context.setVariable("customerName", "An");
context.setVariable("customerCode", "C-100");
~~~

Tạo object bằng constructor expression:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Customer customer = parser
        .parseExpression(
                "new Customer(#customerCode, #customerName)"
        )
        .getValue(context, Customer.class);
~~~

SpEL phân giải lớp Customer qua import prefix, đánh giá hai biến, chuyển customerCode từ String sang CustomerCode thông qua ConversionService rồi gọi constructor phù hợp.

Trong thực tế, class và record phải nằm trong package đã đăng ký và được ClassLoader nhìn thấy. Nếu dùng tên đầy đủ, có thể bỏ bước đăng ký import.

## 12. Kiểm thử constructor expression

Nên kiểm thử riêng các trường hợp hợp lệ và lỗi:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Customer customer = parser
        .parseExpression(
                "new com.example.domain.Customer(" +
                "new com.example.domain.CustomerCode('C-100'), 'An')"
        )
        .getValue(context, Customer.class);

assertEquals("C-100", customer.code().value());
assertEquals("An", customer.name());
~~~

Ngoài trường hợp thành công, hãy kiểm thử:

- Constructor không tham số.
- Constructor có một và nhiều argument.
- Các overload có cùng tên lớp.
- Argument null cho kiểu tham chiếu và primitive.
- Chuyển đổi String sang kiểu miền.
- Dữ liệu constructor không hợp lệ.
- Constructor ném exception.
- Tên lớp không được TypeLocator phân giải.
- Constructor không có quyền truy cập phù hợp.
- Biểu thức lồng constructor và method.
- Expression được đánh giá nhiều lần để xác nhận mỗi lần tạo instance mới theo thiết kế.

Với converter tùy chỉnh, kiểm thử cả giá trị hợp lệ, chuỗi rỗng, null và dữ liệu sai định dạng. Không chỉ kiểm tra object được tạo; hãy xác nhận các invariant của domain sau constructor.

## 13. Tổng kết

SpEL tạo object Java bằng cú pháp **new FullyQualifiedClassName(arguments)**. TypeLocator phân giải tên lớp, ConstructorResolver chọn constructor, TypeConverter chuyển argument khi cần và constructor tạo instance trong lúc evaluate.

Hãy dùng tên lớp đầy đủ hoặc import prefix rõ ràng, thiết kế constructor public với chữ ký đơn giản, kiểm soát overload và kiểm thử chuyển đổi argument. Nhớ rằng object được tạo trực tiếp không phải Spring bean và không tự nhận dependency injection, lifecycle hay AOP.

Với biểu thức do người dùng kiểm soát, hãy giới hạn lớp được phép khởi tạo, dữ liệu và chi phí constructor. Nếu cần một service do Spring quản lý, hãy để container tạo bean và chỉ cung cấp cho expression một API hẹp, có quyền truy cập được kiểm soát.