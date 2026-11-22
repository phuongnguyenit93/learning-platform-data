# Giới hạn type được phép tham chiếu trong Spring Expression Language

Spring Expression Language (SpEL) cho phép tham chiếu một kiểu Java bằng toán tử T(...). Từ tham chiếu kiểu, biểu thức có thể truy cập thành viên static, chẳng hạn hằng số hoặc phương thức static:

~~~spel
T(java.lang.Math).PI
T(java.lang.Math).max(10, 20)
~~~

Khả năng này hữu ích khi biểu thức cần dùng API Java, enum hoặc hằng số mà không cần truyền một object làm root. Tuy nhiên, trong ứng dụng thực tế, không phải lúc nào cũng muốn biểu thức được tham chiếu mọi kiểu mà classloader có thể tải.

SpEL giải quyết việc tìm kiểu thông qua TypeLocator trong EvaluationContext. Vì vậy, ứng dụng có thể cấu hình TypeLocator để chỉ cho phép một tập kiểu nhất định. Khi cần giới hạn ngôn ngữ biểu thức, cần hiểu rõ hành vi mặc định, cách tạo allow-list và phạm vi bảo vệ mà giới hạn type reference thực sự cung cấp.

## 1. Type reference là gì?

Type reference là cú pháp dùng toán tử T(...) để chỉ định một kiểu Java theo tên:

~~~spel
T(java.lang.String)
T(java.math.BigDecimal)
T(java.time.LocalDate)
~~~

Khi được đánh giá, SpEL yêu cầu TypeLocator tìm lớp tương ứng và trả về đối tượng Class. Từ đối tượng Class này, biểu thức có thể truy cập thành viên static được phép.

Ví dụ:

~~~spel
T(java.lang.Math).PI
T(java.lang.Math).abs(-10)
T(java.lang.Math).max(10, 20)
~~~

Kết quả lần lượt là hằng số PI, số 10 và số 20.

Type reference không phải là lời gọi constructor. Nếu muốn tạo instance, SpEL có cú pháp new riêng. Tương tự, T(...) không phải là bean reference: nó tìm kiểu Java, còn cú pháp @beanName tìm bean thông qua BeanResolver.

## 2. Tên kiểu đầy đủ và import mặc định

Với StandardTypeLocator được dùng mặc định trong StandardEvaluationContext, package java.lang được import sẵn. Vì vậy có thể viết:

~~~spel
T(String)
T(Math)
T(Integer)
~~~

Đối với các kiểu ngoài java.lang, thông thường cần dùng tên đầy đủ gồm package:

~~~spel
T(java.math.BigDecimal)
T(java.time.LocalDate)
T(java.util.UUID)
~~~

Có thể đăng ký package import trên StandardTypeLocator để dùng tên ngắn hơn:

~~~java
StandardTypeLocator typeLocator =
    new StandardTypeLocator();

typeLocator.registerImport("java.math");
typeLocator.registerImport("java.time");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

Sau khi đăng ký, biểu thức có thể tham chiếu:

~~~spel
T(BigDecimal)
T(LocalDate)
~~~

Import chỉ là cách rút gọn tên kiểu. Nó không có nghĩa các kiểu khác đã bị cấm. Nếu TypeLocator vẫn có thể tìm một tên đầy đủ khác qua classloader, biểu thức vẫn có thể tham chiếu kiểu đó.

Đây là điểm quan trọng khi thiết kế giới hạn: thêm một số package import không tạo ra allow-list.

## 3. TypeLocator chịu trách nhiệm tìm kiểu

EvaluationContext cung cấp TypeLocator để SpEL giải quyết tên kiểu xuất hiện trong T(...). Interface TypeLocator định nghĩa thao tác tìm một kiểu từ tên được truyền vào.

Trong StandardEvaluationContext, TypeLocator mặc định thường là StandardTypeLocator. Nó tìm lớp thông qua classloader và hỗ trợ các package import đã đăng ký, bao gồm java.lang mặc định.

Luồng xử lý:

~~~text
Biểu thức T(java.math.BigDecimal)
             |
             v
SpEL nhận diện type reference
             |
             v
EvaluationContext.getTypeLocator()
             |
             v
TypeLocator.findType(typeName)
             |
       +-----+-----+
       |           |
    Tìm thấy    Không tìm thấy
       |           |
       v           v
    Class<?>    Evaluation error
       |
       v
Truy cập thành viên static nếu biểu thức yêu cầu
~~~

Nếu tên kiểu sai, lớp không có trên classpath hoặc classloader không thể tải kiểu đó, quá trình đánh giá có thể phát sinh lỗi. Nếu TypeLocator chủ động từ chối tên kiểu, biểu thức cũng không thể tiếp tục.

## 4. Hành vi mặc định không phải là allow-list

StandardTypeLocator giúp tìm kiểu theo tên và classloader. Nó không được thiết kế như một cơ chế chỉ cho phép một danh sách lớp an toàn.

Ví dụ, nếu ứng dụng dùng StandardEvaluationContext với TypeLocator mặc định, biểu thức có thể tham chiếu các kiểu Java khác nhau miễn là chúng có thể được tìm thấy và các thao tác tiếp theo được phép thực hiện.

Việc chỉ thêm import:

~~~java
typeLocator.registerImport("java.math");
~~~

không giới hạn biểu thức vào các kiểu thuộc java.math. Tên đầy đủ của một kiểu khác vẫn có thể được phân giải nếu classloader tải được nó.

Do đó:

- **Import:** giúp viết tên ngắn cho một package.
- **ClassLoader:** quyết định các lớp nào có thể được tải trong môi trường.
- **TypeLocator:** quyết định cách một tên kiểu trong expression được giải quyết.
- **Allow-list:** là chính sách do ứng dụng chủ động áp dụng để chỉ cho phép những tên kiểu đã chọn.

Nếu mục tiêu là giới hạn kiểu được tham chiếu, cần triển khai chính sách allow-list trong TypeLocator hoặc dùng một context không hỗ trợ type reference.

## 5. Giới hạn type bằng TypeLocator allow-list

Có thể tạo TypeLocator tùy chỉnh để chỉ chấp nhận một số tên kiểu cụ thể. Những tên khác sẽ bị từ chối trước khi SpEL lấy được đối tượng Class.

Ví dụ sau chỉ cho phép tham chiếu Math và BigDecimal:

~~~java
import java.math.BigDecimal;
import java.util.Set;

import org.springframework.expression.EvaluationException;
import org.springframework.expression.TypeLocator;
import org.springframework.expression.spel.support.StandardTypeLocator;

public class AllowListTypeLocator implements TypeLocator {

    private final TypeLocator delegate =
        new StandardTypeLocator();

    private final Set<String> allowedTypes = Set.of(
        "java.lang.Math",
        "java.math.BigDecimal"
    );

    @Override
    public Class<?> findType(String typeName)
            throws EvaluationException {

        if (!allowedTypes.contains(typeName)) {
            throw new EvaluationException(
                "Type is not allowed: " + typeName
            );
        }

        return delegate.findType(typeName);
    }
}
~~~

Đăng ký TypeLocator:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(new AllowListTypeLocator());

ExpressionParser parser = new SpelExpressionParser();

Integer result = parser.parseExpression(
    "T(java.lang.Math).max(10, 20)"
).getValue(context, Integer.class);
~~~

Kết quả là 20.

Nếu expression yêu cầu một kiểu không có trong allow-list, chẳng hạn:

~~~spel
T(java.lang.System)
~~~

TypeLocator tùy chỉnh từ chối tên kiểu và ném EvaluationException. SpEL không thể tiếp tục đánh giá type reference đó.

Ví dụ trên dùng tên đầy đủ chính xác để chính sách dễ kiểm tra. Nếu muốn hỗ trợ alias hoặc tên ngắn, cần định nghĩa rõ các tên được phép và chuẩn hóa chúng trước khi kiểm tra; không nên vô tình mở rộng chính sách bằng cách chấp nhận mọi tên mà delegate có thể tìm thấy.

## 6. Vì sao cần kiểm tra trước khi gọi delegate?

Một TypeLocator allow-list thường bọc một TypeLocator khác. Delegate chịu trách nhiệm tìm lớp sau khi chính sách đã chấp nhận tên.

Thứ tự đúng là:

1. Nhận tên kiểu từ expression.
2. Kiểm tra tên có nằm trong danh sách cho phép không.
3. Nếu không, từ chối ngay.
4. Nếu có, gọi delegate để tìm Class.
5. Trả Class về cho SpEL.

Nếu gọi delegate trước rồi mới kiểm tra, ứng dụng đã cho phép cơ chế tải và phân giải kiểu chạy trước khi chính sách được áp dụng. Đặt kiểm tra ở đầu giúp chính sách rõ ràng và dễ kiểm soát hơn.

Ngoài ra, allow-list cần được quản lý tập trung. Khi thêm một kiểu mới, cần xem xét kiểu đó cung cấp static method, field hoặc khả năng nào mà expression có thể truy cập.

## 7. Dùng SimpleEvaluationContext khi không cần type reference

Nếu ứng dụng chỉ cần một tập con tính năng SpEL cho data binding, có thể cân nhắc SimpleEvaluationContext.

SimpleEvaluationContext được thiết kế với phạm vi cú pháp hạn chế hơn StandardEvaluationContext. Nó không hỗ trợ các tính năng như:

- Java type reference bằng T(...).
- Constructor invocation bằng new.
- Bean reference bằng @beanName.

Ví dụ tạo context cho data binding:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding()
        .build();
~~~

Context này phù hợp khi biểu thức chỉ cần đọc property theo cơ chế data binding được cấu hình. Nếu ứng dụng cần type reference, constructor hoặc bean reference, phải chọn context có khả năng tương ứng và giới hạn các khả năng đó theo chính sách riêng.

SimpleEvaluationContext là một lựa chọn giảm bề mặt tính năng, nhưng vẫn cần cấu hình property accessor và các khả năng khác đúng với dữ liệu ứng dụng.

## 8. Giới hạn type reference không đồng nghĩa với sandbox hoàn chỉnh

Đây là giới hạn quan trọng nhất cần hiểu khi đánh giá expression không đáng tin cậy.

TypeLocator allow-list chỉ kiểm soát những kiểu được giải quyết qua cú pháp T(...). Nó không tự động kiểm soát mọi object mà expression có thể truy cập.

Ví dụ, nếu root object là một service có nhiều method công khai, biểu thức vẫn có thể gọi những method đó nếu MethodResolver và context cho phép. Tương tự, một biến hoặc bean được đăng ký có thể cung cấp đường truy cập đến object khác.

Vì vậy, chỉ giới hạn T(...) là chưa đủ để tạo một môi trường đánh giá an toàn. Cần xem xét đồng thời:

- **Root object:** chỉ cung cấp object và dữ liệu mà expression thực sự cần.
- **Variables:** không đăng ký những object có quyền truy cập rộng nếu không cần thiết.
- **PropertyAccessor:** giới hạn property mà expression được phép đọc hoặc ghi.
- **MethodResolver:** giới hạn method có thể gọi và các method có tác dụng phụ.
- **BeanResolver:** không đăng ký nếu expression không cần tham chiếu bean; nếu cần, chỉ cung cấp phạm vi bean phù hợp.
- **ConstructorResolver:** kiểm soát hoặc không cung cấp khả năng tạo object nếu không cần.
- **TypeLocator:** áp dụng allow-list cho các type reference.
- **Giá trị đầu vào:** xác thực dữ liệu trước khi đánh giá.

Một expression có thể không dùng T(...) nhưng vẫn gọi method nguy hiểm trên object được truyền vào. Ngược lại, cho phép một kiểu không có nghĩa mọi thao tác trên kiểu đó đều tự động được kiểm soát đầy đủ bởi TypeLocator.

TypeLocator là một lớp kiểm soát trong kiến trúc đánh giá, không phải ranh giới bảo mật duy nhất.

## 9. Kiểm soát cả static member được sử dụng

Khi một kiểu được cho phép, SpEL có thể truy cập những static member mà cơ chế truy cập cho phép, ví dụ:

~~~spel
T(java.lang.Math).PI
T(java.lang.Math).abs(-10)
~~~

Vì vậy, khi thêm một kiểu vào allow-list, cần xem xét không chỉ tên lớp mà cả API static mà lớp cung cấp.

Nếu ứng dụng chỉ cần một hằng số hoặc một phép tính cụ thể, có thể cân nhắc cung cấp giá trị đó dưới dạng variable hoặc một object wrapper có giao diện nhỏ, thay vì mở toàn bộ kiểu cho expression.

Ví dụ, thay vì cho phép expression tự truy cập một API rộng, ứng dụng có thể đăng ký một biến chứa giá trị đã tính sẵn:

~~~java
context.setVariable("pi", Math.PI);
~~~

Expression chỉ cần tham chiếu:

~~~spel
#pi
~~~

Cách này làm rõ dữ liệu nào được cung cấp và tránh phải cho phép type reference chỉ để lấy một giá trị cố định.

## 10. ClassLoader và khả năng phân giải kiểu

StandardTypeLocator tìm lớp thông qua classloader. Trong ứng dụng nhiều module, plugin hoặc container, classloader có thể ảnh hưởng đến việc kiểu nào được tìm thấy.

Một kiểu có thể tồn tại trong một module hoặc dependency nhưng không nhìn thấy từ classloader mà TypeLocator sử dụng. Khi đó, expression vẫn có thể thất bại dù tên kiểu đúng.

StandardTypeLocator cho phép cấu hình classloader phù hợp:

~~~java
StandardTypeLocator typeLocator =
    new StandardTypeLocator(
        Thread.currentThread().getContextClassLoader()
    );
~~~

Sau đó có thể đăng ký import hoặc dùng tên đầy đủ như bình thường.

Nếu dùng custom TypeLocator bọc StandardTypeLocator, hãy cấu hình delegate với classloader mà ứng dụng mong muốn. Chính sách allow-list và khả năng tải lớp là hai điều kiện riêng: tên được cho phép vẫn phải là kiểu có thể tải được.

## 11. Phân biệt lỗi type reference và lỗi thao tác sau khi tìm kiểu

Có hai giai đoạn lỗi cần tách biệt:

**Lỗi phân giải kiểu:**

- Tên kiểu sai hoặc không đầy đủ.
- Kiểu không có trên classpath hoặc không nhìn thấy qua classloader.
- TypeLocator không cho phép tên kiểu.
- Context không hỗ trợ type reference.

Trong trường hợp này, SpEL chưa nhận được Class phù hợp để tiếp tục.

**Lỗi sau khi tìm kiểu:**

- Thành viên static được yêu cầu không tồn tại.
- Method static có số lượng hoặc kiểu đối số không phù hợp.
- Thành viên không thể truy cập.
- Method được gọi nhưng chính phần thân method ném exception.

Ở nhóm thứ hai, TypeLocator có thể đã hoạt động thành công. Cần kiểm tra member, overload, quyền truy cập và exception gốc thay vì thay đổi allow-list một cách phỏng đoán.

## 12. Ví dụ hoàn chỉnh: chỉ cho phép một số type reference

Giả sử ứng dụng muốn cho expression sử dụng Math và BigDecimal, nhưng không cho phép tham chiếu kiểu khác.

Tạo context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeLocator(new AllowListTypeLocator());

ExpressionParser parser = new SpelExpressionParser();

Expression allowedExpression =
    parser.parseExpression(
        "T(java.lang.Math).max(12, 30)"
    );

Integer result =
    allowedExpression.getValue(context, Integer.class);
~~~

Kết quả:

~~~text
30
~~~

Một expression khác:

~~~spel
T(java.time.LocalDate).now()
~~~

bị từ chối vì java.time.LocalDate không nằm trong allow-list, dù lớp đó có thể có trên classpath.

Kết quả của chính sách:

| Type reference | Chính sách | Hành vi |
|---|---|---|
| T(java.lang.Math) | Được phép | Delegate tìm kiểu và SpEL tiếp tục |
| T(java.math.BigDecimal) | Được phép | Delegate tìm kiểu và SpEL tiếp tục |
| T(java.time.LocalDate) | Bị từ chối | TypeLocator ném EvaluationException |
| T(java.lang.System) | Bị từ chối | TypeLocator ném EvaluationException |

Allow-list quyết định kiểu nào được tham chiếu. Delegate vẫn kiểm tra khả năng tải lớp, và các bước truy cập member tiếp theo vẫn phải hợp lệ.

## 13. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: Chỉ import một package là đã cấm các package khác.**  
Import chỉ giúp dùng tên ngắn. Nó không phải allow-list và không ngăn tên đầy đủ của kiểu khác được phân giải.

**Nhầm lẫn 2: StandardTypeLocator mặc định chỉ cho phép java.lang.**  
java.lang được import mặc định, nhưng StandardTypeLocator vẫn có thể tìm các kiểu khác bằng tên đầy đủ nếu classloader truy cập được.

**Nhầm lẫn 3: T(...) là bean reference.**  
T(...) tham chiếu một kiểu Java qua TypeLocator; @beanName tìm bean qua BeanResolver.

**Nhầm lẫn 4: T(...) tạo một instance mới.**  
T(...) trả về tham chiếu kiểu Class. Việc tạo instance dùng cú pháp new riêng.

**Nhầm lẫn 5: TypeLocator allow-list là sandbox hoàn chỉnh.**  
Nó chỉ kiểm soát type reference. Root object, variables, property accessor, method resolver và bean resolver vẫn có thể cung cấp những đường truy cập khác.

**Nhầm lẫn 6: Kiểu được allow-list thì mọi method trên kiểu chắc chắn gọi được.**  
TypeLocator chỉ tìm kiểu. Method resolution, quyền truy cập và việc thực thi member là các bước riêng.

## 14. Ghi nhớ

- Type reference dùng cú pháp T(...) để tìm một kiểu Java.
- TypeLocator trong EvaluationContext chịu trách nhiệm giải quyết tên kiểu.
- StandardEvaluationContext thường dùng StandardTypeLocator, với java.lang được import mặc định.
- Tên kiểu ngoài java.lang có thể dùng tên đầy đủ hoặc package import đã đăng ký.
- Import không phải allow-list; muốn giới hạn kiểu phải áp dụng chính sách rõ ràng trong TypeLocator.
- Custom TypeLocator có thể kiểm tra tên kiểu trước khi gọi delegate để tìm Class.
- SimpleEvaluationContext loại bỏ type reference, constructor invocation và bean reference trong tập tính năng được hỗ trợ.
- TypeLocator allow-list không kiểm soát mọi object, property hoặc method mà expression có thể truy cập.
- Cần phối hợp giới hạn root object, variables, accessor, resolver và bean exposure khi đánh giá expression không đáng tin cậy.
- Lỗi tìm kiểu khác với lỗi truy cập static member hoặc lỗi trong method được gọi.

Khi thiết kế type reference cho SpEL, hãy quyết định kiểu nào thực sự cần thiết, áp dụng allow-list ở TypeLocator, kiểm tra classloader và đánh giá cả các đường truy cập khác trong EvaluationContext. Điều đó giúp biểu thức có đủ khả năng cần dùng mà vẫn giữ phạm vi tham chiếu kiểu rõ ràng.
