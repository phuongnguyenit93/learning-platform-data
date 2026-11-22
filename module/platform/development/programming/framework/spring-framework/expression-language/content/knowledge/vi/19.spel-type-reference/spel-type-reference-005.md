# Truy cập hằng static trong SpEL

## 1. Type reference và static member là gì?

Spring Expression Language (SpEL) có toán tử type reference `T(...)` để tham chiếu một Java class trong biểu thức. Sau khi chỉ định class, biểu thức có thể truy cập static field, static constant, enum constant hoặc gọi static method của class đó.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("T(java.lang.Math).PI");

Double pi = expression.getValue(Double.class);
System.out.println(pi); // 3.141592653589793
~~~

Trong ví dụ này:

- `T(java.lang.Math)` tham chiếu class `java.lang.Math`.
- `.PI` truy cập static field `PI` của class.
- `getValue(Double.class)` lấy kết quả theo kiểu mong đợi.

Type reference không tạo một instance mới. Nó cho SpEL biết class nào cần được tham chiếu để phân giải các static member.

## 2. Cú pháp T(...)

Cú pháp tổng quát:

~~~text
T(fully.qualified.TypeName)
~~~

Tên class thường được viết đầy đủ package để tránh nhầm lẫn:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression typeExpression =
        parser.parseExpression("T(java.lang.String)");

Class<?> stringType = typeExpression.getValue(Class.class);
System.out.println(stringType.getName()); // java.lang.String
~~~

Chữ `T` phải viết hoa. Bên trong dấu ngoặc là tên class cần tham chiếu. Với class nằm ngoài package `java.lang`, nên dùng tên đầy đủ như `T(java.time.LocalDate)` hoặc `T(java.math.BigDecimal)`.

StandardTypeLocator mặc định có import prefix cho package java.lang, nên các class quen thuộc trong package này thường có thể được tham chiếu bằng tên ngắn:

~~~java
Expression expression =
        parser.parseExpression("T(Math).PI");

Double pi = expression.getValue(Double.class);
~~~

Dù vậy, dùng tên đầy đủ thường giúp biểu thức dễ đọc hơn khi có nhiều class trùng tên hoặc khi người đọc chưa biết quy tắc type lookup của context.

## 3. Truy cập static constant và static field

Sau type reference, dùng dấu chấm và tên member để đọc static field:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Integer maxInt = parser.parseExpression(
        "T(java.lang.Integer).MAX_VALUE")
        .getValue(Integer.class);

BigDecimal zero = parser.parseExpression(
        "T(java.math.BigDecimal).ZERO")
        .getValue(BigDecimal.class);

System.out.println(maxInt); // 2147483647
System.out.println(zero);   // 0
~~~

Một số hằng static thường gặp:

| Class | Member | Ý nghĩa |
|---|---|---|
| `java.lang.Math` | `PI` | Hằng số pi |
| `java.lang.Math` | `E` | Cơ số logarit tự nhiên |
| `java.lang.Integer` | `MAX_VALUE` | Giá trị int lớn nhất |
| `java.lang.Integer` | `MIN_VALUE` | Giá trị int nhỏ nhất |
| `java.math.BigDecimal` | `ZERO` | Giá trị BigDecimal bằng 0 |
| `java.math.BigDecimal` | `ONE` | Giá trị BigDecimal bằng 1 |
| `java.nio.charset.StandardCharsets` | `UTF_8` | Charset UTF-8 |

Các ví dụ:

~~~java
Double pi = parser.parseExpression("T(java.lang.Math).PI")
        .getValue(Double.class);

Integer maxRetries = parser.parseExpression("T(java.lang.Integer).MAX_VALUE")
        .getValue(Integer.class);

BigDecimal defaultAmount = parser.parseExpression("T(java.math.BigDecimal).ZERO")
        .getValue(BigDecimal.class);

Charset charset = parser.parseExpression(
        "T(java.nio.charset.StandardCharsets).UTF_8")
        .getValue(Charset.class);
~~~

Tên member phải đúng với class đang tham chiếu và phải được phép truy cập qua evaluation context. Nếu class hoặc field không được phân giải, SpEL sẽ phát sinh lỗi khi đánh giá expression.

## 4. Truy cập enum constant

Enum constant cũng là static member của enum class. Dùng type reference để chọn một giá trị enum:

~~~java
Expression expression =
        parser.parseExpression("T(java.time.DayOfWeek).MONDAY");

DayOfWeek day = expression.getValue(DayOfWeek.class);
System.out.println(day); // MONDAY
~~~

Với enum của ứng dụng, dùng tên package đầy đủ:

~~~java
Expression expression =
        parser.parseExpression("T(com.example.order.OrderStatus).PAID");

OrderStatus status = expression.getValue(OrderStatus.class);
~~~

Có thể so sánh property enum của root object với một enum constant:

~~~java
Expression expression = parser.parseExpression(
        "status == T(com.example.order.OrderStatus).PAID");

Boolean paid = expression.getValue(order, Boolean.class);
~~~

Ở đây `status` được đọc từ root object `order`; phần `T(...)` tham chiếu enum class và `PAID` là constant cần so sánh. Cách viết này tránh so sánh enum với chuỗi ký tự, đồng thời giữ đúng kiểu dữ liệu enum.

## 5. Gọi static method

Static method được gọi bằng cách đặt tên method và danh sách đối số sau type reference:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
        parser.parseExpression("T(java.lang.Math).max(12, 30)");

Integer maximum = expression.getValue(Integer.class);
System.out.println(maximum); // 30
~~~

Một số ví dụ khác:

~~~java
Integer parsed = parser.parseExpression(
        "T(java.lang.Integer).parseInt('42')")
        .getValue(Integer.class);

Double squareRoot = parser.parseExpression(
        "T(java.lang.Math).sqrt(81)")
        .getValue(Double.class);

Boolean isNull = parser.parseExpression(
        "T(java.util.Objects).isNull(null)")
        .getValue(Boolean.class);
~~~

Static method có thể nhận literal, variable hoặc property được phân giải từ context:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("minimum", 5);
context.setVariable("maximum", 18);

Expression expression = parser.parseExpression(
        "T(java.lang.Math).max(#minimum, #maximum)");

Integer result = expression.getValue(context, Integer.class);
System.out.println(result); // 18
~~~

SpEL phân giải method dựa trên class được tham chiếu, tên method, số lượng đối số và kiểu đối số. Với method overload, hãy truyền kiểu dữ liệu rõ ràng nếu nhiều overload có thể phù hợp hoặc nếu việc chuyển đổi kiểu làm kết quả không như mong đợi.

## 6. Kết hợp static constant với phép toán

Static constant có thể được dùng trong công thức, điều kiện hoặc phép nối chuỗi:

~~~java
Expression expression = parser.parseExpression(
        "T(java.lang.Math).PI * 2");

Double circumferenceFactor = expression.getValue(Double.class);
~~~

Ví dụ dùng BigDecimal constant trong điều kiện:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("amount", new BigDecimal("125.00"));

Expression expression = parser.parseExpression(
        "#amount.compareTo(T(java.math.BigDecimal).ZERO) > 0");

Boolean positive = expression.getValue(context, Boolean.class);
~~~

Một cách khác là gọi static method để tạo giá trị cần so sánh:

~~~java
Expression expression = parser.parseExpression(
        "T(java.lang.Integer).parseInt('100') > 50");

Boolean result = expression.getValue(Boolean.class);
~~~

Type reference chỉ cung cấp class và static member; các toán tử SpEL còn lại vẫn hoạt động theo quy tắc biểu thức thông thường. Dùng dấu ngoặc khi công thức có nhiều phép toán để làm rõ thứ tự đánh giá.

## 7. Dùng static member trong @Value

Trong cấu hình Spring, SpEL thường được đặt trong dấu `#{...}` của annotation `@Value`. Có thể inject một hằng static vào bean:

~~~java
@Component
public class MathSettings {
    @Value("#{T(java.lang.Math).PI}")
    private double pi;

    @Value("#{T(java.lang.Integer).MAX_VALUE}")
    private int maximumInteger;

    public double getPi() {
        return pi;
    }

    public int getMaximumInteger() {
        return maximumInteger;
    }
}
~~~

Spring đánh giá biểu thức khi xử lý bean definition và chuyển kết quả sang kiểu field nếu cần. Với static method, cú pháp tương tự:

~~~java
@Component
public class RetrySettings {
    @Value("#{T(java.lang.Math).max(3, 5)}")
    private int retryFloor;

    public int getRetryFloor() {
        return retryFloor;
    }
}
~~~

Có thể inject enum constant:

~~~java
@Component
public class OrderDefaults {
    @Value("#{T(com.example.order.OrderStatus).PENDING}")
    private OrderStatus initialStatus;
}
~~~

Hãy giữ expression trong annotation ngắn. Nếu giá trị cần được tính từ nhiều điều kiện hoặc phụ thuộc vào nhiều nguồn dữ liệu, hãy cân nhắc chuyển phần quyết định sang Java configuration hoặc một bean có tên rõ ràng.

## 8. Type reference và root object, variable

Type reference khác với root object và variable trong evaluation context:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| Tên property trực tiếp | Đọc property trên root object | `status` |
| `#name` | Đọc variable trong context | `#threshold` |
| `T(...)` | Tham chiếu Java class | `T(java.lang.Math)` |
| `@beanName` | Tham chiếu bean trong context có bean resolver | `@pricingService` |

Có thể kết hợp chúng trong cùng một expression:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setVariable("minimum", 100);

Expression expression = parser.parseExpression(
        "total >= #minimum and status == T(com.example.order.OrderStatus).PAID");

Boolean eligible = expression.getValue(context, Boolean.class);
~~~

Trong ví dụ này, `total` và `status` được đọc từ root object `order`, `#minimum` được đọc từ variable, còn `T(...)` tham chiếu enum class. Phân biệt các nguồn dữ liệu này giúp biểu thức rõ ràng và dễ cấu hình.

## 9. Dùng tên class ngắn qua StandardTypeLocator

StandardTypeLocator chịu trách nhiệm phân giải tên class trong type reference. Mặc định, nó dùng class loader phù hợp và đăng ký import prefix cho java.lang.

Nếu ứng dụng có nhiều class constants trong cùng package, có thể đăng ký package đó để dùng tên ngắn:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context = new StandardEvaluationContext();

StandardTypeLocator typeLocator = new StandardTypeLocator();
typeLocator.registerImport("com.example.constants");
context.setTypeLocator(typeLocator);

Expression expression =
        parser.parseExpression("T(AppLimits).MAX_RETRIES");

Integer retries = expression.getValue(context, Integer.class);
~~~

Trong ví dụ này, `AppLimits` được tìm trong package import `com.example.constants`. Class thực tế phải có thể được tải bởi class loader mà type locator sử dụng.

Có thể tiếp tục dùng tên đầy đủ ngay cả khi đã đăng ký import. Tên đầy đủ thường phù hợp hơn trong expression được lưu lâu dài hoặc được chia sẻ giữa nhiều module vì nó thể hiện chính xác class được tham chiếu.

## 10. Cấu hình class loader và type resolution

Type locator cần class loader có thể nhìn thấy class được tham chiếu. Trong ứng dụng chạy với class loader tùy chỉnh, plugin system hoặc môi trường container, class có thể tồn tại trong ứng dụng nhưng không được class loader mặc định của type locator nhìn thấy.

Có thể tạo `StandardTypeLocator` với class loader cụ thể:

~~~java
StandardTypeLocator typeLocator =
        new StandardTypeLocator(MyApplication.class.getClassLoader());

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeLocator(typeLocator);
~~~

Chỉ cấu hình class loader khi ứng dụng thực sự cần điều đó. Trong ứng dụng Spring thông thường, class loader mặc định thường đủ để phân giải các class trên application classpath.

Khi SpEL báo không tìm thấy type, hãy kiểm tra tên package/class, dependency có mặt trên runtime classpath và class loader được gắn với type locator. Lỗi phân giải type khác với lỗi không tìm thấy static field hoặc method sau khi class đã được tải thành công.

## 11. Static member và instance member

Static member thuộc về class; instance member thuộc về một object cụ thể.

~~~java
// Static field:
T(java.lang.Math).PI

// Static method:
T(java.lang.Math).max(10, 20)

// Instance property:
customer.name

// Instance method:
customer.getName()
~~~

Không dùng type reference để đọc property của một instance chưa được cung cấp. Ví dụ, `T(com.example.Customer).name` tìm static member `name` trên class; nó không có nghĩa là đọc `name` của một biến `customer`.

Nếu cần thao tác trên instance, truyền root object, variable hoặc bean reference vào evaluation context. Nếu cần giá trị cố định của class, dùng `T(...)`.

## 12. Lỗi thường gặp

**Quên chữ T viết hoa**

Type reference dùng `T(...)`. Viết thường `t(...)` không phải cú pháp type reference.

**Thiếu package hoặc nhầm class cùng tên**

Với class ngoài `java.lang`, dùng fully qualified name hoặc đăng ký import prefix trong `StandardTypeLocator`. Nếu có hai class cùng tên, tên đầy đủ giúp tránh phân giải nhầm.

**Nhầm static field với instance property**

`T(SomeClass).LIMIT` truy cập static member của class. `limit` truy cập property của root object. Chọn cú pháp dựa trên nơi khai báo dữ liệu.

**Gọi sai static method hoặc truyền sai kiểu**

Tên method, số lượng và kiểu đối số phải phù hợp với method của class. Với method overload, hãy kiểm tra kiểu đầu vào và kiểu kết quả mong đợi.

**Class không có trên runtime classpath**

Một class có thể compile được trong module khác nhưng không có mặt trong runtime classpath của ứng dụng đang đánh giá expression. Hãy kiểm tra dependency runtime và class loader.

**Static member không thể truy cập**

Field hoặc method phải được phép truy cập qua cơ chế reflection và evaluation context đang dùng. Member không tồn tại hoặc không truy cập được sẽ gây lỗi evaluation.

**Đưa expression không tin cậy vào context có quyền rộng**

Type reference và static method call có thể mở rộng đáng kể những thao tác expression thực hiện được. Không đánh giá expression do người dùng tùy ý gửi lên với context cho phép truy cập class và method rộng.

## 13. Giới hạn type access khi cần bảo mật

StandardEvaluationContext hỗ trợ type locator và các khả năng đánh giá rộng. Nếu expression đến từ nguồn không hoàn toàn đáng tin cậy, việc cho phép `T(...)` tùy ý có thể khiến biểu thức tham chiếu những class mà ứng dụng không muốn expose.

Một số nguyên tắc:

- Chỉ nhận expression từ nguồn được ứng dụng kiểm soát nếu cần type reference và static method.
- Giới hạn các class được phép bằng một `TypeLocator` có allowlist phù hợp với miền nghiệp vụ.
- Chỉ expose static method thuần, có đầu vào/đầu ra rõ ràng; tránh method gây side effect hoặc truy cập hệ thống.
- Dùng evaluation context giới hạn khả năng khi nhu cầu chỉ là data binding.
- Không xem việc một class hoặc method là static như một bảo đảm an toàn.

SimpleEvaluationContext được thiết kế cho các trường hợp data binding với khả năng giới hạn hơn và không cung cấp đầy đủ type reference như StandardEvaluationContext. Nếu biểu thức không cần tham chiếu class, tránh bật khả năng type access chỉ vì tiện lợi.

## 14. Ví dụ tổng hợp

Ví dụ sau dùng static constant, static method và enum constant cùng với dữ liệu của root object:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}

public class Order {
    private OrderStatus status;
    private BigDecimal total;

    public Order(OrderStatus status, BigDecimal total) {
        this.status = status;
        this.total = total;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}

ExpressionParser parser = new SpelExpressionParser();

Order order = new Order(
        OrderStatus.PAID,
        new BigDecimal("150.00"));

StandardEvaluationContext context =
        new StandardEvaluationContext(order);
context.setVariable("minimum", new BigDecimal("100.00"));

Expression eligibleExpression = parser.parseExpression(
        "status == T(com.example.OrderStatus).PAID "
                + "and total.compareTo(#minimum) >= 0 "
                + "and total.compareTo(T(java.math.BigDecimal).ZERO) > 0");

Boolean eligible =
        eligibleExpression.getValue(context, Boolean.class);

Integer upperBound = parser.parseExpression(
        "T(java.lang.Math).max(10, 20)")
        .getValue(Integer.class);

System.out.println(eligible);   // true
System.out.println(upperBound); // 20
~~~

Expression đầu đọc `status` và `total` từ root object, so sánh status với enum constant, dùng variable `#minimum` và tham chiếu `BigDecimal.ZERO`. Expression thứ hai gọi static method `Math.max`. Mỗi type reference chỉ rõ class sở hữu member cần dùng.

## 15. Ghi nhớ

- Dùng `T(fully.qualified.TypeName)` để tham chiếu Java class trong SpEL.
- Dùng `T(Class).CONSTANT` hoặc `T(Class).FIELD` để đọc static field và constant.
- Dùng `T(Class).method(arguments)` để gọi static method.
- Enum constant có thể được tham chiếu qua `T(EnumType).CONSTANT`.
- `StandardTypeLocator` mặc định hỗ trợ import prefix `java.lang`; có thể đăng ký package khác hoặc cấu hình class loader.
- Phân biệt type reference với root object property, variable `#name` và bean reference `@beanName`.
- Dùng static member ngắn gọn trong expression; chuyển logic nhiều bước sang Java configuration hoặc method có tên.
- Kiểm soát type access và static method khi expression có nguồn không đáng tin cậy.
