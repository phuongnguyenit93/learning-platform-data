# Gọi method tĩnh qua type reference

Trong Spring Expression Language (SpEL), **type reference** cho phép biểu thức tham chiếu đến một kiểu Java thông qua toán tử **T(...)**. Khi đã tham chiếu đến kiểu, biểu thức có thể gọi các **static method** hoặc đọc **static field** của kiểu đó.

Cú pháp này hữu ích khi một biểu thức cần dùng hàm tiện ích, hằng số hoặc giá trị enum mà không cần có một instance object làm root object. Ví dụ thường gặp là gọi **Math.max(...)**, tạo UUID bằng **UUID.randomUUID()** hoặc đọc hằng số **Math.PI**.

## Cú pháp T(...) và static method

Cú pháp tổng quát:

~~~text
T(fully.qualified.TypeName).staticMethod(arguments)
~~~

Trong đó:

- **T(...)** là toán tử type reference của SpEL.
- Nội dung trong ngoặc là tên kiểu Java mà type locator có thể phân giải.
- Sau dấu chấm là static method của kiểu đó.
- Các đối số được truyền theo chữ ký method và quy tắc chuyển đổi kiểu của SpEL.

Ví dụ gọi phương thức Math.max:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

Expression expression =
        parser.parseExpression("T(java.lang.Math).max(10, 25)");

Integer result =
        expression.getValue(context, Integer.class);
~~~

Kết quả là 25. Biểu thức tham chiếu trực tiếp đến kiểu java.lang.Math và gọi static method max. Không cần tạo object Math vì các phương thức trong Math là static.

Có thể gọi những phương thức static khác:

~~~java
Double randomValue =
        parser.parseExpression("T(java.lang.Math).random()")
                .getValue(context, Double.class);

Integer absoluteValue =
        parser.parseExpression("T(java.lang.Math).abs(-12)")
                .getValue(context, Integer.class);
~~~

Trong các ví dụ này, **random()** và **abs(...)** được gọi trên kiểu Math. Kết quả phụ thuộc vào phương thức được gọi và đối số, chứ không phụ thuộc vào một instance root object.

## Type reference không phải instance method call

Cần phân biệt việc gọi static method thông qua type reference với việc gọi instance method trên một object:

~~~java
// Gọi static method trên một kiểu Java
Expression staticCall =
        parser.parseExpression("T(java.lang.Math).max(10, 25)");

// Gọi instance method trên root object
Expression instanceCall =
        parser.parseExpression("name.toUpperCase()");
~~~

Biểu thức thứ nhất tìm kiểu Math rồi gọi phương thức static max. Biểu thức thứ hai đọc property name từ root object rồi gọi phương thức instance toUpperCase trên giá trị đó, nếu evaluation context cho phép.

Một cách phân biệt khác:

| Cú pháp | Ý nghĩa |
|---|---|
| **T(java.lang.Math).max(1, 2)** | Gọi static method trên kiểu Java |
| **name.toUpperCase()** | Gọi instance method trên giá trị property |
| **#value** | Đọc biến trong EvaluationContext |
| **@pricingService** | Tham chiếu bean nếu context có BeanResolver |

Type reference không tạo ra một bean Spring. Nó phân giải một lớp Java theo tên kiểu. Nếu cần gọi logic của một Spring service hoặc component, hãy dùng bean reference trong context phù hợp hoặc gọi service từ Java theo thiết kế ứng dụng.

## Đọc static field và hằng số

Type reference cũng có thể được dùng để truy cập static field:

~~~java
Double pi =
        parser.parseExpression("T(java.lang.Math).PI")
                .getValue(context, Double.class);
~~~

Ở đây, **PI** là static field của Math. Biểu thức đọc giá trị hằng số mà không cần khởi tạo một đối tượng Math.

Có thể dùng cùng cú pháp với các hằng số public static final trong kiểu do ứng dụng định nghĩa:

~~~java
String defaultRegion =
        parser.parseExpression(
                "T(com.example.config.AppDefaults).REGION")
                .getValue(context, String.class);
~~~

Tên kiểu trong ví dụ cần là tên đầy đủ mà type locator có thể tìm thấy. Field phải truy cập được theo cơ chế truy cập mà SpEL hỗ trợ.

Type reference cũng thường được dùng để lấy enum constant:

~~~java
DayOfWeek day =
        parser.parseExpression("T(java.time.DayOfWeek).MONDAY")
                .getValue(context, DayOfWeek.class);
~~~

Enum constant là thành viên tĩnh của kiểu enum. Cách viết này hữu ích khi biểu thức cần so sánh hoặc chọn một giá trị enum cụ thể.

## Gọi static method của kiểu do ứng dụng định nghĩa

Giả sử ứng dụng có một lớp tiện ích:

~~~java
package com.example.util;

public final class PriceRules {
    private PriceRules() {
    }

    public static BigDecimal addTax(
            BigDecimal amount,
            BigDecimal taxRate) {
        return amount.multiply(BigDecimal.ONE.add(taxRate));
    }
}
~~~

Có thể gọi phương thức tĩnh bằng tên kiểu đầy đủ:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("amount", new BigDecimal("100.00"));
context.setVariable("taxRate", new BigDecimal("0.08"));

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
        "T(com.example.util.PriceRules).addTax(#amount, #taxRate)");

BigDecimal total =
        expression.getValue(context, BigDecimal.class);
~~~

Trong biểu thức:

- **T(com.example.util.PriceRules)** tham chiếu đến lớp tiện ích.
- **addTax(...)** là static method được gọi.
- **#amount** và **#taxRate** là biến do ứng dụng đặt trong EvaluationContext.
- Kết quả được lấy theo kiểu BigDecimal.

Cách này cho phép biểu thức phối hợp một static method với dữ liệu động từ context. Tuy nhiên, nếu logic tính thuế là một quy tắc nghiệp vụ quan trọng, cần cân nhắc đặt việc quyết định và kiểm soát nghiệp vụ trong service Java. SpEL nên giữ vai trò khai báo biểu thức ngắn ở những điểm tích hợp phù hợp.

## Tên kiểu đầy đủ và package java.lang

Thông thường, type reference dùng tên kiểu đầy đủ, ví dụ **T(java.lang.Math)** hoặc **T(java.time.LocalDate)**. Package **java.lang** được StandardTypeLocator nhập mặc định, vì vậy trong cấu hình mặc định có thể tham chiếu một số kiểu thuộc package này bằng tên ngắn:

~~~java
Expression expression =
        parser.parseExpression("T(Math).max(10, 25)");
~~~

Dù vậy, dùng tên đầy đủ thường giúp biểu thức dễ hiểu và tránh nhầm lẫn khi có nhiều kiểu trùng tên.

Với kiểu trong package khác, có thể dùng tên đầy đủ hoặc đăng ký package import với StandardTypeLocator. Không nên giả định mọi package trong classpath đều được tự động import.

## Cấu hình TypeLocator

Khi SpEL đánh giá **T(...)**, nó dùng một thành phần gọi là **TypeLocator** để phân giải tên kiểu thành Class Java. **StandardEvaluationContext** mặc định sử dụng StandardTypeLocator.

Nếu muốn bổ sung package import, có thể cấu hình locator:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("com.example.util");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

Sau khi đăng ký import, biểu thức có thể dùng tên kiểu ngắn nếu tên đó được phân giải duy nhất trong các package đã import:

~~~java
Expression expression =
        parser.parseExpression("T(PriceRules).addTax(#amount, #taxRate)");
~~~

Việc đăng ký package giúp rút gọn tên trong biểu thức. Nó không tự động tạo bean và cũng không có nghĩa mọi lớp trong package đều là API nghiệp vụ nên expose cho người viết biểu thức.

StandardTypeLocator còn có thể được tạo với một ClassLoader cụ thể:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator(applicationClassLoader);
~~~

Điều này hữu ích trong ứng dụng có class loader riêng, plugin hoặc môi trường triển khai đặc biệt. Kiểu chỉ phân giải được nếu lớp nằm trong phạm vi class loader mà locator sử dụng và có thể được nạp tại thời điểm đánh giá.

## Type reference và EvaluationContext

Type reference là một khả năng của SpEL cần được hỗ trợ bởi evaluation context. **StandardEvaluationContext** cung cấp type locator và các cơ chế cần thiết để dùng cú pháp T(...).

Ngược lại, **SimpleEvaluationContext** được thiết kế cho một tập con khả năng của SpEL, chủ yếu dành cho data binding. Context này không hỗ trợ type reference, constructor invocation hoặc bean reference như StandardEvaluationContext.

Ví dụ, không nên kỳ vọng biểu thức sau hoạt động trong SimpleEvaluationContext chỉ đọc:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

Expression expression =
        parser.parseExpression("T(java.lang.Math).max(1, 2)");
~~~

Nếu use case bắt buộc phải gọi static method qua T(...), cần một context hỗ trợ type reference. Khi đó, phải cân nhắc cẩn thận phạm vi lớp mà biểu thức có thể truy cập và những method tĩnh có thể gọi.

Nếu mục tiêu chỉ là đọc property của DTO, hãy dùng SimpleEvaluationContext và tránh mở thêm type reference không cần thiết.

## Overload và kiểu đối số

Một lớp Java có thể có nhiều static method cùng tên nhưng khác kiểu tham số. SpEL phải chọn overload phù hợp dựa trên kiểu của các đối số và khả năng chuyển đổi kiểu trong context.

Ví dụ:

~~~java
Expression expression =
        parser.parseExpression("T(java.lang.Math).max(10, 25)");

Integer result =
        expression.getValue(context, Integer.class);
~~~

Trong trường hợp này, hai đối số là số nguyên nên overload tương ứng được chọn. Nếu đối số đến từ biến hoặc property có kiểu không rõ ràng, hãy cung cấp dữ liệu với kiểu cụ thể để tránh lựa chọn overload ngoài ý muốn.

Khi method nhận BigDecimal, LocalDate hoặc một kiểu tùy chỉnh, nên đưa biến đúng kiểu vào context thay vì truyền chuỗi rồi trông chờ SpEL tự chuyển đổi. Nếu có nhiều overload hoặc giá trị null khiến việc chọn method không rõ ràng, có thể cần chuyển đổi dữ liệu trước trong Java hoặc gọi một wrapper method có chữ ký đơn giản hơn.

## Xử lý lỗi khi phân giải kiểu và gọi static method

Có hai nhóm lỗi cần phân biệt:

- **Parse error:** cú pháp biểu thức không hợp lệ, ví dụ viết sai cấu trúc T(...), thiếu dấu ngoặc hoặc đặt method call sai vị trí.
- **Evaluation error:** biểu thức parse được nhưng kiểu không thể phân giải, static method không tồn tại, đối số không tương thích hoặc method phát sinh lỗi khi chạy.

Ví dụ xử lý lỗi:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(
            "T(java.lang.Math).max(10, 25)");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    Integer result =
            expression.getValue(context, Integer.class);
} catch (EvaluationException ex) {
    throw new IllegalStateException(
            "Cannot resolve type or invoke static method", ex);
}
~~~

Nếu lỗi đến từ class loader, hãy kiểm tra tên kiểu, package, module và class loader đang được sử dụng. Nếu lỗi do overload hoặc kiểu đối số, kiểm tra kiểu runtime của biến và property. Nếu static method phát sinh exception bên trong, cần xử lý nguyên nhân từ chính method đó thay vì chỉ thay đổi parser.

## Rủi ro khi cho phép type reference trong biểu thức bên ngoài

Type reference mở ra khả năng truy cập các kiểu Java mà TypeLocator phân giải được. Khi kết hợp với static method, biểu thức có thể gọi những hàm có tác động phụ như tạo tài nguyên, truy cập hệ thống hoặc thực hiện thao tác khác tùy API được gọi.

Vì vậy, không nên đánh giá biểu thức tùy ý từ người dùng bằng StandardEvaluationContext có type locator rộng và root object chứa nhiều khả năng. Một biểu thức bên ngoài có thể làm nhiều hơn phép tính hoặc so sánh mà giao diện ban đầu gợi ý.

Nếu cần hỗ trợ biểu thức do bên ngoài cung cấp:

- Chỉ expose các kiểu và method thật sự cần thiết.
- Dùng TypeLocator theo allowlist nếu ứng dụng cần cho phép một số lớp cụ thể.
- Giới hạn root object, biến, property accessor và method resolver.
- Tránh expose service, repository hoặc object có quyền truy cập tài nguyên.
- Kiểm soát nguồn biểu thức, độ dài, quyền sửa và cách xử lý lỗi.
- Ưu tiên wrapper method nhỏ, thuần và có hợp đồng rõ ràng thay vì expose một lớp tiện ích có nhiều chức năng.

Đăng ký import package trong StandardTypeLocator giúp phân giải tên ngắn thuận tiện hơn, nhưng bản thân import không phải một cơ chế sandbox hoặc chính sách allowlist đầy đủ. Nếu cần kiểm soát bảo mật, phải giới hạn type resolution và những thành phần mà context cho phép truy cập.

## Khi nào nên gọi static method qua SpEL?

Cú pháp T(...) phù hợp khi biểu thức cần một phép tính tiện ích ngắn hoặc một hằng số từ kiểu Java, ví dụ:

- Gọi **Math.max(...)**, **Math.min(...)** hoặc một hàm toán học đơn giản.
- Đọc hằng số như **Math.PI**.
- Tham chiếu enum constant.
- Gọi một static helper có chữ ký đơn giản và không tạo tác động phụ.
- Dùng biểu thức trong một điểm tích hợp Spring vốn đã hỗ trợ SpEL.

Nếu method thực hiện nhiều bước nghiệp vụ, truy cập tài nguyên, ghi dữ liệu hoặc cần quyền và transaction, hãy gọi nó từ service Java. Nếu biểu thức được đánh giá từ dữ liệu bên ngoài, chỉ cho phép các kiểu và method đã được chọn rõ ràng.

## Kết luận

Type reference **T(...)** cho phép SpEL tham chiếu đến một kiểu Java để gọi static method hoặc đọc static field. StandardEvaluationContext cung cấp TypeLocator để phân giải tên kiểu; có thể dùng tên đầy đủ hoặc đăng ký package import khi cần. Khả năng này khác với instance method call, variable reference và Spring bean reference.

T(...) hữu ích cho các phép tính và hằng số đơn giản, nhưng cũng mở rộng những gì một biểu thức có thể thực hiện. Hãy dùng context phù hợp, kiểm soát TypeLocator và chỉ expose các kiểu cần thiết, đặc biệt khi biểu thức đến từ nguồn bên ngoài.
