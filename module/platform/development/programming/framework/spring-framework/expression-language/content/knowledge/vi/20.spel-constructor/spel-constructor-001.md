# Toán tử new trong SpEL

## 1. Toán tử new dùng để làm gì?

Spring Expression Language (SpEL) có thể tạo object ngay trong biểu thức bằng toán tử new. Cú pháp này cho phép gọi constructor của một class và nhận về instance mới.

Ví dụ:

    new String('Hello')
    new java.util.Date()
    new com.example.Customer('Lan', 30)

Khi expression được đánh giá, SpEL tìm kiểu được chỉ định, giải quyết constructor phù hợp, đánh giá các đối số rồi tạo object.

Toán tử new hữu ích khi cần tạo một giá trị hoặc object trung gian ngay trong expression, chẳng hạn truyền object mới vào method, tạo một collection đặc biệt hoặc xây dựng tham số cho một phép tính.

Tuy nhiên, new chỉ tạo instance. Nó không đăng ký instance đó thành Spring bean và không tự áp dụng vòng đời quản lý bean của IoC container.

## 2. Cú pháp constructor invocation

Cú pháp tổng quát:

    new Fully.Qualified.ClassName(argument1, argument2, ...)

Ví dụ:

    new java.util.Date()

    new java.math.BigDecimal('1250.50')

    new com.example.Customer('Lan', 30)

Với các class thuộc package java.lang, có thể bỏ tên package:

    new String('Spring')
    new Integer(42)
    new Boolean(true)

Với các class ở package khác, mặc định nên dùng tên class đầy đủ:

    new java.util.ArrayList()
    new java.math.BigDecimal('99.95')
    new com.example.Order('ORD-001')

Tên đầy đủ giúp TypeLocator xác định chính xác class cần tạo. Nếu muốn dùng tên ngắn cho class ngoài java.lang, cần cấu hình TypeLocator với package import phù hợp.

## 3. Ví dụ tạo object Java tùy chỉnh

Giả sử ứng dụng có class Customer:

    package com.example;

    public class Customer {
        private final String name;
        private final int age;

        public Customer(String name, int age) {
            this.name = name;
            this.age = age;
        }

        public String getName() {
            return name;
        }

        public int getAge() {
            return age;
        }
    }

Có thể tạo Customer bằng SpEL:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    Expression expression = parser.parseExpression(
        "new com.example.Customer('Lan', 30)"
    );

    Customer customer =
        expression.getValue(context, Customer.class);

Kết quả là một instance Customer với name là Lan và age là 30.

Trong ví dụ này:

1. Parser phân tích cú pháp constructor expression.
2. Khi gọi getValue, SpEL tìm class com.example.Customer.
3. SpEL tìm constructor phù hợp với hai đối số String và số nguyên.
4. Constructor được gọi và instance mới được trả về.

Việc parse expression chưa tạo object. Constructor chỉ được thực thi khi expression được đánh giá.

## 4. Truyền variable vào constructor

Các đối số của constructor có thể là variable trong EvaluationContext thay vì literal cố định.

Ví dụ:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("customerName", "Lan");
    context.setVariable("customerAge", 30);

    Expression expression = parser.parseExpression(
        "new com.example.Customer(#customerName, #customerAge)"
    );

    Customer customer =
        expression.getValue(context, Customer.class);

Cú pháp #customerName và #customerAge tham chiếu variable đã đăng ký trong context.

Cách này giúp tái sử dụng cùng một expression với dữ liệu khác nhau:

    context.setVariable("customerName", "Minh");
    context.setVariable("customerAge", 25);

    Customer anotherCustomer =
        expression.getValue(context, Customer.class);

Mỗi lần getValue, SpEL đánh giá các đối số theo context hiện tại rồi gọi constructor để tạo instance mới.

Nếu variable chưa được đăng ký hoặc giá trị không tương thích với tham số constructor, evaluation có thể thất bại dù expression đã parse thành công.

## 5. Truyền biểu thức làm đối số

Đối số constructor không nhất thiết phải là variable hoặc literal đơn giản. Có thể truyền kết quả của phép toán hoặc expression khác.

Ví dụ:

    new com.example.Customer(
        #firstName + ' ' + #lastName,
        #birthYear < 2000 ? 26 : 18
    )

SpEL đánh giá các đối số rồi truyền giá trị kết quả vào constructor.

Một ví dụ đơn giản hơn:

    new java.math.BigDecimal(#amount.toString())

Nếu amount là variable có giá trị phù hợp, biểu thức tạo BigDecimal từ kết quả của lời gọi toString.

Hãy bảo đảm các expression đối số trả về kiểu mà constructor có thể nhận hoặc có thể được TypeConverter chuyển đổi.

Không nên đưa logic quá phức tạp vào một constructor expression. Nếu có nhiều bước nghiệp vụ, hãy chuẩn bị dữ liệu ở Java rồi truyền vào expression dưới dạng variable.

## 6. Constructor overload và chuyển đổi kiểu

Một class có thể khai báo nhiều constructor cùng tên nhưng khác danh sách tham số. Đây là constructor overloading.

Ví dụ:

    public class Customer {
        public Customer(String name) {
            // ...
        }

        public Customer(String name, int age) {
            // ...
        }
    }

SpEL cần chọn constructor phù hợp với số lượng và kiểu của các đối số.

Ví dụ:

    new com.example.Customer('Lan')

chọn constructor nhận một String nếu constructor đó có thể truy cập và phù hợp.

Ví dụ:

    new com.example.Customer('Lan', 30)

chọn constructor nhận String và int nếu phù hợp với các giá trị được cung cấp.

SpEL sử dụng cơ chế chuyển đổi kiểu trong EvaluationContext để hỗ trợ những trường hợp đối số có thể chuyển đổi sang kiểu tham số. Việc chuyển đổi phụ thuộc TypeConverter và ConversionService được cấu hình.

Nếu có nhiều overload gần giống nhau hoặc đối số có kiểu không rõ ràng, hãy làm rõ kiểu dữ liệu trong Java trước khi truyền vào expression. Không nên dựa vào chuyển đổi ngầm khi constructor có ý nghĩa nghiệp vụ quan trọng.

## 7. Varargs constructor

SpEL hỗ trợ varargs khi gọi constructor.

Ví dụ class:

    public class LabelSet {
        private final List<String> labels;

        public LabelSet(String... labels) {
            this.labels = List.of(labels);
        }

        public List<String> getLabels() {
            return labels;
        }
    }

Có thể truyền nhiều đối số:

    new com.example.LabelSet('Java', 'Spring', 'SpEL')

Constructor nhận các đối số dạng varargs và tạo danh sách nhãn.

Khi dùng varargs, số lượng đối số có thể thay đổi theo nhu cầu. Tuy nhiên, nếu class có nhiều constructor overload, cần kiểm tra kỹ constructor nào được resolver chọn.

Varargs không có nghĩa là SpEL tự chuyển mọi loại collection thành tham số varargs trong mọi trường hợp. Hãy kiểm tra kiểu đối số và chữ ký constructor thực tế.

## 8. TypeLocator và cách tìm class

Trước khi gọi constructor, SpEL phải tìm được class tương ứng với tên được viết sau new.

Việc này do TypeLocator trong EvaluationContext đảm nhiệm.

StandardEvaluationContext mặc định sử dụng StandardTypeLocator. Type locator mặc định hiểu package java.lang, nên có thể viết:

    new String('Hello')

Nhưng với class ngoài java.lang, nên dùng tên đầy đủ:

    new java.util.ArrayList()

Nếu muốn dùng tên ngắn, có thể đăng ký package import:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    StandardTypeLocator typeLocator =
        new StandardTypeLocator();

    typeLocator.registerImport("com.example");

    context.setTypeLocator(typeLocator);

Sau đó có thể viết:

    new Customer('Lan', 30)

vì TypeLocator đã được cấu hình để tìm class trong package com.example.

Import ở đây thuộc TypeLocator của SpEL. Nó không phải câu lệnh import của Java source và không tự thay đổi classpath.

## 9. ClassLoader và môi trường chạy

Trong một số ứng dụng, đặc biệt môi trường plugin, application server hoặc runtime có class loader riêng, TypeLocator có thể không tìm thấy class dù class đó tồn tại trong ứng dụng.

Có thể cấu hình StandardTypeLocator với ClassLoader phù hợp:

    StandardTypeLocator typeLocator =
        new StandardTypeLocator(
            MyApplication.class.getClassLoader()
        );

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setTypeLocator(typeLocator);

Điều này giúp SpEL tìm class qua đúng ClassLoader của ứng dụng.

Nếu gặp lỗi không tìm thấy class, hãy kiểm tra:

- Tên class trong expression có chính xác không.
- Package có được viết đầy đủ không.
- Class có nằm trong runtime classpath không.
- ClassLoader mà TypeLocator sử dụng có nhìn thấy class không.
- Package import đã được đăng ký nếu dùng tên ngắn chưa.

Không nên nhầm lỗi class not found với lỗi không tìm được constructor. Hai lỗi xảy ra ở các bước khác nhau.

## 10. ConstructorResolver

Sau khi TypeLocator tìm được class, SpEL cần chọn constructor phù hợp. Công việc này do ConstructorResolver đảm nhiệm.

StandardEvaluationContext mặc định có reflective constructor resolver, sử dụng reflection để tìm constructor tương ứng.

Nếu ứng dụng có yêu cầu tạo object đặc biệt, có thể đăng ký ConstructorResolver tùy chỉnh vào EvaluationContext. Cách này cho phép mở rộng cơ chế khởi tạo ngoài hành vi reflection mặc định.

Một constructor resolver tùy chỉnh cần xử lý rõ:

- Class nào được phép tạo.
- Constructor nào được phép sử dụng.
- Cách đối chiếu số lượng và kiểu đối số.
- Cách chuyển đổi giá trị.
- Cách báo lỗi khi không tìm thấy constructor phù hợp.

Không nên mở rộng resolver chỉ để tránh lỗi constructor thông thường. Trước tiên hãy kiểm tra class, constructor công khai phù hợp, kiểu đối số và TypeConverter.

## 11. Phân biệt new với type reference T()

SpEL có toán tử T() để tham chiếu đối tượng Class của Java.

Ví dụ:

    T(java.util.Date)

Expression trên trả về đối tượng Class đại diện cho java.util.Date. Nó không tạo instance Date.

Trong khi đó:

    new java.util.Date()

gọi constructor và tạo instance Date mới.

So sánh:

| Cú pháp | Ý nghĩa | Kết quả |
| --- | --- | --- |
| T(java.util.Date) | Tham chiếu kiểu | Class object |
| new java.util.Date() | Gọi constructor | Instance Date |
| T(java.lang.Math).max(3, 5) | Gọi static method | Giá trị trả về của method |

Dùng T() khi cần tham chiếu class, enum, static field hoặc static method. Dùng new khi cần tạo instance.

Không nên nhầm việc TypeLocator tìm class với việc constructor được gọi. TypeLocator chỉ giúp tìm kiểu; constructor resolver mới đảm nhiệm bước tạo instance.

## 12. Phân biệt new với Spring bean reference

Hai cách sau có ý nghĩa rất khác nhau:

    new com.example.Customer('Lan', 30)

    @customerService

Biểu thức đầu tạo một instance mới bằng constructor.

Biểu thức thứ hai tìm bean tên customerService trong Spring BeanFactory thông qua BeanResolver.

Một object tạo bằng new trong SpEL không tự động được Spring container quản lý. Nó không tự nhận dependency injection, không được áp dụng bean lifecycle callback, không tự có AOP proxy và không tuân theo bean scope.

Nếu cần một service hoặc component đã được Spring quản lý, hãy dùng bean reference tại điểm tích hợp hỗ trợ SpEL và cung cấp BeanResolver phù hợp.

Nếu chỉ cần tạo một object dữ liệu đơn giản hoặc giá trị tạm thời, constructor expression có thể phù hợp.

## 13. Constructor và array construction

SpEL dùng toán tử new cho cả constructor invocation và array construction, nhưng cú pháp và kiểu kết quả khác nhau.

Tạo object:

    new java.util.ArrayList()

Tạo array có kích thước:

    new int[4]

Tạo array với initializer:

    new int[] {1, 2, 3}

Tạo array nhiều chiều:

    new int[4][5]

Ví dụ trong Java:

    int[] numbers = (int[]) parser
        .parseExpression("new int[] {1, 2, 3}")
        .getValue(context);

    int[][] matrix = (int[][]) parser
        .parseExpression("new int[4][5]")
        .getValue(context);

Với array nhiều chiều, SpEL hiện không hỗ trợ cung cấp initializer trong cùng cú pháp tạo array nhiều chiều. Có thể tạo array theo kích thước rồi gán từng phần tử bằng Java.

Array construction khác inline List:

    {1, 2, 3}

Biểu thức này tạo inline List.

    new int[] {1, 2, 3}

Biểu thức này tạo primitive int array.

Hãy chọn cú pháp theo kiểu dữ liệu mà code phía sau yêu cầu.

## 14. Dùng constructor expression bên trong method invocation

Một constructor expression có thể được dùng làm đối số của method call.

Ví dụ:

    Members.add(
        new com.example.Inventor('Albert Einstein', 'German')
    )

Trong expression SpEL:

    Members.add(
        new com.example.Inventor('Albert Einstein', 'German')
    )

SpEL tạo Inventor mới rồi truyền instance đó vào method add của collection Members.

Cách này có thể hữu ích khi expression cần bổ sung một object mới vào collection hoặc truyền object mới cho một method.

Tuy nhiên, method được gọi có thể làm thay đổi object hoặc trạng thái ứng dụng. Hãy cân nhắc side effect và quyền truy cập của EvaluationContext trước khi cho phép expression thực hiện các thao tác như vậy.

## 15. SimpleEvaluationContext và giới hạn constructor

SimpleEvaluationContext được thiết kế để chỉ hỗ trợ một tập con tính năng SpEL, phù hợp với các trường hợp data binding hoặc property-based filtering cần giới hạn quyền.

Context này không hỗ trợ constructor invocation, type references và bean references.

Vì vậy, expression:

    new com.example.Customer('Lan', 30)

không phù hợp với SimpleEvaluationContext.

Nếu cần sử dụng constructor expression, phải dùng EvaluationContext hỗ trợ đầy đủ tính năng như StandardEvaluationContext hoặc một context tùy chỉnh cho phép constructor resolution.

Không nên chuyển sang StandardEvaluationContext chỉ để làm expression chạy mà chưa đánh giá quyền truy cập. StandardEvaluationContext mạnh hơn và cần được cấu hình cẩn thận khi expression đến từ nguồn bên ngoài.

## 16. Lỗi thường gặp khi dùng new

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Type cannot be found | Tên class sai hoặc TypeLocator không tìm thấy class | Dùng tên đầy đủ, kiểm tra classpath và ClassLoader |
| Constructor cannot be found | Không có constructor phù hợp với đối số | Kiểm tra số lượng, thứ tự và kiểu tham số |
| Argument conversion error | Không chuyển đổi được đối số sang kiểu tham số | Chuẩn bị đúng kiểu ở Java hoặc cấu hình TypeConverter |
| Expression parse error | Cú pháp new, dấu ngoặc hoặc argument list sai | Kiểm tra grammar và dấu phân cách |
| Constructor không chạy trong SimpleEvaluationContext | Context không hỗ trợ constructor invocation | Dùng context hỗ trợ đầy đủ nếu nghiệp vụ cho phép |
| Object không được inject dependency | Instance được tạo trực tiếp bằng new, ngoài container | Dùng Spring bean thay vì tự tạo instance nếu cần DI |
| Class có nhiều overload bị chọn ngoài dự kiến | Nhiều constructor có tham số tương thích | Làm rõ kiểu đối số và kiểm tra overload |
| Không tìm thấy class trong môi trường plugin | TypeLocator dùng ClassLoader không phù hợp | Cấu hình StandardTypeLocator với ClassLoader đúng |

Hãy phân biệt ba giai đoạn khi debug:

1. Parsing: expression có cú pháp hợp lệ không?
2. Type lookup: TypeLocator có tìm được class không?
3. Constructor resolution: có constructor nào phù hợp và được phép gọi không?

Sau khi tạo object, lỗi có thể tiếp tục xảy ra trong method hoặc property access tiếp theo. Vì vậy, hãy tách expression thành các bước nhỏ khi cần xác định vị trí lỗi.

## 17. Bảo mật và side effect

Constructor invocation có thể chạy code khởi tạo của class. Constructor có thể đọc cấu hình, tạo tài nguyên, mở kết nối hoặc thực hiện logic khác tùy implementation.

Vì vậy, expression có toán tử new không nên được đánh giá tùy ý nếu người dùng không tin cậy có thể kiểm soát nội dung expression.

Các nguyên tắc:

- Không đánh giá SpEL tùy ý do người dùng gửi lên trong context có đầy đủ quyền.
- Giới hạn class có thể được tìm thấy qua TypeLocator nếu nghiệp vụ yêu cầu.
- Kiểm soát ConstructorResolver và các khả năng reflection được cấp.
- Không đưa class có constructor tạo side effect nguy hiểm vào phạm vi expression không tin cậy.
- Ưu tiên tạo object trong Java code khi cần validation, transaction hoặc quản lý tài nguyên rõ ràng.
- Dùng context giới hạn tính năng khi constructor invocation không cần thiết.

Việc thay đổi cú pháp hoặc dùng một wrapper không tự loại bỏ rủi ro nếu expression vẫn có quyền gọi constructor hoặc method.

## 18. Những điểm cần nhớ

- Toán tử new dùng để gọi constructor và tạo instance.
- Cú pháp thông thường là new Fully.Qualified.ClassName(arguments).
- Có thể bỏ package java.lang khi tham chiếu các class trong package đó.
- Class ngoài java.lang nên dùng tên đầy đủ, trừ khi TypeLocator đã được cấu hình package import.
- TypeLocator tìm class; ConstructorResolver tìm và gọi constructor.
- StandardEvaluationContext mặc định cung cấp cơ chế reflection cho constructor resolution.
- Constructor có thể overload và hỗ trợ varargs; kiểu đối số phải tương thích hoặc chuyển đổi được.
- T() trả về Class object; new tạo instance.
- Array construction như new int[4] và new int[] {1, 2, 3} khác inline List {1, 2, 3}.
- new tạo instance ngoài vòng đời quản lý bean của Spring.
- SimpleEvaluationContext không hỗ trợ constructor invocation.
- Constructor có thể có side effect; không đánh giá expression không tin cậy với quyền tạo object rộng.

Khi dùng new trong SpEL, hãy xác định class cần tạo, constructor mong muốn, kiểu đối số và ClassLoader đang dùng. Đồng thời phân biệt rõ object tự tạo với bean Spring để không kỳ vọng dependency injection hoặc lifecycle tự động xuất hiện.

## Tài liệu tham khảo

- Spring Framework Reference — Constructors: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html
- Spring Framework Reference — Array Construction: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/array-construction.html
- Spring Framework Reference — Types: https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/types.html
- Spring Framework Reference — EvaluationContext and Security: https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html
