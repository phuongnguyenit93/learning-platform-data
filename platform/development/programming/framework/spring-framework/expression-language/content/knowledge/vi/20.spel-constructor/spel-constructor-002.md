# Khởi tạo kiểu bằng tên đầy đủ trong SpEL

Spring Expression Language (SpEL) hỗ trợ tạo object ngay trong biểu thức bằng toán tử `new`. Khi tạo một instance, biểu thức nêu tên kiểu và truyền các đối số cho constructor tương ứng. Cách viết tên lớp đầy đủ giúp xác định rõ class cần khởi tạo, đặc biệt khi lớp không thuộc package `java.lang` hoặc khi ứng dụng có nhiều class trùng tên.

Ví dụ:

    new java.lang.String('Spring Expression Language')
    new java.math.BigDecimal('123.4500')
    new com.example.domain.Customer('An', 25)

SpEL cần tìm được class trước, sau đó mới phân giải constructor phù hợp và thực hiện việc tạo instance. Hai bước này liên quan tới TypeLocator và ConstructorResolver trong EvaluationContext.

## 1. Cú pháp constructor invocation

Cú pháp cơ bản:

    new fully.qualified.ClassName(argument1, argument2, ...)

Trong đó:

- `new` là từ khóa tạo instance.
- `fully.qualified.ClassName` là tên lớp, gồm package và tên class.
- Danh sách đối số nằm trong dấu ngoặc đơn; có thể rỗng nếu class có constructor không tham số.

Ví dụ tạo một String và một BigDecimal:

    new java.lang.String('Hello')
    new java.math.BigDecimal('19.99')

Ví dụ tạo object nghiệp vụ:

    new com.example.domain.Customer('Lan', 'lan@example.com')

Constructor được chọn phải phù hợp với số lượng và kiểu đối số. Nếu lớp không có constructor tương ứng hoặc constructor không thể truy cập, biểu thức sẽ thất bại khi được đánh giá.

Tên đầy đủ giúp tránh phụ thuộc vào import mặc định và làm rõ class nào đang được tạo. Đây là lựa chọn phù hợp cho expression được lưu trong cấu hình hoặc được chia sẻ giữa nhiều module.

## 2. Khác biệt giữa tên đầy đủ và tên lớp ngắn

StandardTypeLocator mặc định hỗ trợ package `java.lang`. Vì vậy, một số class thuộc package này có thể được tham chiếu bằng tên ngắn:

    new String('Hello')
    new Integer('42')

Với class ngoài `java.lang`, cách rõ ràng và ổn định là dùng tên đầy đủ:

    new java.util.Date()
    new java.math.BigDecimal('123.45')

Nếu viết:

    new BigDecimal('123.45')

thì SpEL cần TypeLocator biết package `java.math` để tìm class BigDecimal. Nếu không có import phù hợp, parser có thể chấp nhận cấu trúc expression nhưng bước đánh giá sẽ không resolve được type.

Không nên giả định mọi package Java hoặc package của ứng dụng đều được import tự động. Khi không chắc về cấu hình TypeLocator, dùng tên đầy đủ để tránh phụ thuộc vào import.

## 3. TypeLocator tìm class trước khi tạo instance

EvaluationContext cung cấp TypeLocator để tìm class theo tên được viết trong expression. StandardEvaluationContext mặc định sử dụng StandardTypeLocator.

Ví dụ:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    ExpressionParser parser = new SpelExpressionParser();

    BigDecimal amount = parser.parseExpression(
            "new java.math.BigDecimal('123.4500')"
    ).getValue(context, BigDecimal.class);

Trong ví dụ này, SpEL dùng TypeLocator để tìm `java.math.BigDecimal`, sau đó tìm constructor nhận một String và tạo object.

Có thể cấu hình import prefix cho StandardTypeLocator:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    StandardTypeLocator typeLocator =
            new StandardTypeLocator();

    typeLocator.registerImport("java.math");
    context.setTypeLocator(typeLocator);

    ExpressionParser parser = new SpelExpressionParser();

    BigDecimal amount = parser.parseExpression(
            "new BigDecimal('19.99')"
    ).getValue(context, BigDecimal.class);

Sau khi đăng ký import `java.math`, biểu thức có thể dùng tên ngắn `BigDecimal`. Import prefix chỉ hỗ trợ việc tìm class; nó không tạo bean, không đăng ký class vào Spring container và cũng không quyết định constructor nào được gọi.

Nếu ứng dụng dùng classloader riêng, có thể khởi tạo StandardTypeLocator với classloader phù hợp hoặc cung cấp TypeLocator tùy chỉnh. Điều này quan trọng trong môi trường plugin, application server hoặc ứng dụng có nhiều classloader.

## 4. ConstructorResolver chọn constructor phù hợp

Sau khi class được tìm thấy, SpEL cần xác định constructor nào có thể nhận các đối số đã đánh giá. EvaluationContext cung cấp danh sách ConstructorResolver để thực hiện việc phân giải.

Trong StandardEvaluationContext, resolver mặc định là ReflectiveConstructorResolver. Resolver này tìm constructor có thể truy cập trên class và trả về một ConstructorExecutor để thực thi.

Quy trình có thể hình dung như sau:

1. SpEL đọc tên class trong expression.
2. TypeLocator tìm class tương ứng.
3. SpEL đánh giá từng đối số.
4. ConstructorResolver tìm constructor phù hợp với kiểu và số lượng đối số.
5. ConstructorExecutor gọi constructor và trả về instance dưới dạng TypedValue.

Nếu class tồn tại nhưng không có constructor phù hợp, lỗi xảy ra ở bước phân giải hoặc thực thi constructor. Nếu class không tồn tại hoặc TypeLocator không tìm được, lỗi xảy ra trước khi constructor được chọn.

Có thể cấu hình resolver riêng trên StandardEvaluationContext bằng `setConstructorResolvers(...)`. Khi thay danh sách resolver mặc định, chỉ thêm lại ReflectiveConstructorResolver nếu ứng dụng vẫn cần fallback reflection.

## 5. Truyền đối số vào constructor

Đối số constructor có thể là literal, biến, property hoặc expression được đánh giá trong cùng context.

**Literal:**

    new com.example.domain.Customer('Lan', 25)

**Biến trong EvaluationContext:**

    context.setVariable("customerName", "Lan");
    context.setVariable("customerAge", 25);

    new com.example.domain.Customer(#customerName, #customerAge)

**Property của root object hoặc biến:**

    new com.example.domain.Invoice(#order.id, #order.total)

**Expression tính toán:**

    new com.example.domain.Rectangle(#width * 2, #height + 5)

SpEL đánh giá các đối số trước khi gọi constructor. Kiểu runtime của từng giá trị ảnh hưởng tới việc chọn overload. Nếu một property trả về null hoặc một expression con ném lỗi, việc tạo instance cũng có thể thất bại trước khi constructor được gọi.

Khi expression dài, có thể tính và kiểm tra dữ liệu trong Java trước, sau đó truyền các giá trị đã chuẩn hóa vào context. Điều này giúp constructor nhận đúng kiểu và làm rõ trách nhiệm validation.

## 6. Constructor overload và chuyển đổi kiểu

Một class có thể có nhiều constructor cùng tên lớp nhưng khác danh sách tham số:

    public Customer(String name) { ... }

    public Customer(String name, Integer age) { ... }

    public Customer(String name, Integer age, boolean active) { ... }

SpEL dùng ConstructorResolver để chọn constructor phù hợp với số lượng và kiểu đối số. TypeConverter của EvaluationContext có thể hỗ trợ chuyển đổi đối số sang kiểu tham số khi cần.

Ví dụ:

    new com.example.domain.Customer('Lan', 25)

Nếu constructor thứ hai nhận String và Integer, SpEL sẽ phân giải theo các kiểu đối số tương ứng. Khi có nhiều overload có thể nhận giá trị sau chuyển đổi, việc lựa chọn có thể không như ý hoặc trở nên mơ hồ.

Để tránh vấn đề:

- Dùng literal có kiểu rõ ràng khi cần, ví dụ `25L` cho Long.
- Chuẩn hóa biến trong Java trước khi đưa vào context.
- Tránh overload có chữ ký quá giống nhau nếu expression được tạo động.
- Kiểm tra kiểu runtime của đối số và constructor được chọn trong test.
- Không dựa vào chuyển đổi ngầm để thay thế validation dữ liệu.

TypeConverter chỉ hỗ trợ chuyển đổi biểu diễn dữ liệu. Nó không bảo đảm giá trị thỏa mãn quy tắc nghiệp vụ của constructor hoặc domain object.

## 7. Tạo BigDecimal và BigInteger chính xác

Constructor invocation thường hữu ích khi cần tạo kiểu số có độ chính xác cao. Với BigDecimal, nên truyền chuỗi thập phân trực tiếp:

    new java.math.BigDecimal('1234567890.12345678901234567890')

Cách này giữ nguyên các chữ số thập phân được cung cấp. Không nên tạo BigDecimal từ một literal Double rồi mong đợi khôi phục độ chính xác đã mất do floating point.

Với số nguyên lớn:

    new java.math.BigInteger('123456789012345678901234567890')

BigInteger giữ chính xác các chữ số nguyên mà không bị giới hạn trong miền Integer hoặc Long.

Nếu ứng dụng sử dụng SimpleEvaluationContext, constructor invocation không được hỗ trợ. Khi đó hãy tạo BigDecimal hoặc BigInteger trong Java rồi truyền qua biến:

    context.setVariable(
            "amount",
            new BigDecimal("1234567890.1234567890")
    );

    #amount

Cách này cũng phù hợp khi dữ liệu đến từ database hoặc API và cần được parse, validate trước khi expression sử dụng.

## 8. Tạo array bằng constructor syntax

SpEL hỗ trợ tạo array bằng từ khóa `new` và kích thước hoặc initializer:

    new int[3]
    new java.lang.String[2]
    new int[]{10, 20, 30}

`new int[3]` tạo array có ba phần tử với giá trị mặc định của kiểu int là 0. Cú pháp initializer tạo array và khởi tạo các phần tử ngay trong expression.

Có thể truy cập phần tử của array vừa tạo:

    new int[]{10, 20, 30}[1]

Kết quả là 20. Array cũng có thể được truyền làm đối số cho constructor hoặc method khác nếu kiểu tham số tương thích.

Cần phân biệt array constructor syntax với inline list:

    {10, 20, 30}

Inline list tạo collection; `new int[]{10, 20, 30}` tạo một array kiểu int. Kiểu dữ liệu và API nhận hai cấu trúc này có thể khác nhau.

## 9. Constructor invocation khác type reference và bean reference

Ba cú pháp dưới đây có mục đích khác nhau:

| Cú pháp | Ý nghĩa |
|---|---|
| `new com.example.Customer('Lan')` | Tạo instance mới bằng constructor |
| `T(com.example.Customer)` | Tham chiếu đối tượng Class để dùng type/static member |
| `@customerService` | Resolve bean có tên customerService trong Spring container |

Type reference không tự tạo object. Bean reference cũng không tạo instance theo constructor trong expression; nó lấy object do container quản lý.

Ví dụ gọi static factory:

    T(com.example.CustomerFactory).create('Lan')

Đây là lời gọi static method trên class được tham chiếu bằng `T(...)`, không phải constructor invocation. Static factory có thể áp dụng quy tắc tạo object riêng, nhưng việc gọi nó chịu các giới hạn method invocation của context.

Dùng `new` khi thật sự cần một instance mới qua constructor. Dùng bean reference khi cần component do Spring quản lý, giữ scope, dependency injection và proxy của container.

## 10. Giới hạn constructor invocation trong EvaluationContext

StandardEvaluationContext mặc định hỗ trợ constructor invocation thông qua ReflectiveConstructorResolver. SimpleEvaluationContext được thiết kế với tập tính năng hạn chế hơn và không hỗ trợ constructor invocation.

Ví dụ tạo context đơn giản chỉ đọc:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withRootObject(order)
                    .build();

    ExpressionParser parser = new SpelExpressionParser();

    // Constructor invocation không được hỗ trợ trong context này.
    parser.parseExpression(
            "new java.math.BigDecimal('19.99')"
    ).getValue(context);

Nếu use case yêu cầu constructor invocation, cần dùng context có hỗ trợ và cấu hình nó một cách có chủ đích. Không chuyển sang StandardEvaluationContext chỉ để làm cho expression chạy được nếu biểu thức đến từ nguồn không tin cậy.

## 11. An toàn khi cho phép tạo class từ expression

Constructor invocation có thể khởi tạo class bất kỳ mà TypeLocator resolve được và constructor có thể truy cập. Trong classpath của ứng dụng, có thể tồn tại class có constructor thực hiện I/O, mở kết nối, cấp phát tài nguyên hoặc tạo object có quyền rộng.

Vì vậy, không nên cho phép expression do người dùng cung cấp tự do dùng `new` trên toàn bộ classpath. Một số biện pháp cần cân nhắc:

- Dùng SimpleEvaluationContext khi không cần type reference hoặc constructor invocation.
- Nếu cần constructor, dùng TypeLocator tùy chỉnh để chỉ resolve các class nằm trong allowlist.
- Cấu hình ConstructorResolver giới hạn những kiểu hoặc constructor được phép.
- Không cho phép tạo trực tiếp các class truy cập file, process, network hoặc tài nguyên quản trị nếu use case không cần.
- Xác thực dữ liệu constructor nhận vào và giới hạn kích thước object/array được tạo.
- Ưu tiên factory hoặc facade hẹp do ứng dụng kiểm soát khi quy trình tạo object có quy tắc nghiệp vụ.

Một custom TypeLocator hoặc ConstructorResolver cần được kiểm tra kỹ để không vô tình fallback sang resolver rộng. Chỉ giới hạn tên package bằng quy ước không đủ nếu trong package đó vẫn có class nhạy cảm.

## 12. Lỗi thường gặp và cách xử lý

- **Không dùng tên đầy đủ cho class ngoài java.lang:** dùng `new java.math.BigDecimal(...)` hoặc đăng ký import prefix trong TypeLocator.
- **Nhầm type reference với constructor:** `T(com.example.Customer)` trả về Class reference; dùng `new com.example.Customer(...)` để tạo instance.
- **Class không resolve được:** kiểm tra tên package, classpath và TypeLocator.
- **Không có constructor phù hợp:** kiểm tra số lượng, kiểu đối số và khả năng truy cập constructor.
- **Overload mơ hồ:** chuẩn hóa kiểu đối số hoặc đơn giản hóa các overload.
- **Dữ liệu số mất chính xác:** tạo BigDecimal từ chuỗi thay vì từ Double.
- **Dùng constructor trong SimpleEvaluationContext:** context này không hỗ trợ constructor invocation; tạo object trong Java và truyền qua biến.
- **Cho phép class tùy ý:** giới hạn TypeLocator/ConstructorResolver khi expression không hoàn toàn tin cậy.
- **Nhầm bean với instance mới:** dùng `@beanName` cho bean container quản lý, dùng `new` cho instance được tạo trong lần đánh giá expression.

## 13. Ghi nhớ

Constructor invocation trong SpEL dùng cú pháp `new fully.qualified.ClassName(arguments)`. TypeLocator tìm class; ConstructorResolver chọn constructor; TypeConverter có thể hỗ trợ chuyển đổi đối số. StandardTypeLocator mặc định nhận biết package `java.lang`, còn class ngoài package này nên dùng tên đầy đủ hoặc đăng ký import prefix. Có thể tạo array bằng cú pháp `new Type[size]` hoặc initializer. StandardEvaluationContext hỗ trợ constructor invocation, trong khi SimpleEvaluationContext không hỗ trợ. Khi expression không hoàn toàn tin cậy, hãy giới hạn class và constructor được phép tạo thay vì mở toàn bộ classpath.
