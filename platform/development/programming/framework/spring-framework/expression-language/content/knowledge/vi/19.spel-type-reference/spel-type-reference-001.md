# Toán tử T(Type) trong SpEL

## 1. Type reference là gì?

Spring Expression Language (SpEL) có toán tử đặc biệt `T(...)` để tham chiếu một kiểu Java. Kết quả của biểu thức này là một đối tượng `java.lang.Class` đại diện cho kiểu được chỉ định.

Cú pháp tổng quát:

```text
T(fully.qualified.TypeName)
```

Ví dụ:

```java
ExpressionParser parser = new SpelExpressionParser();

Class<?> dateType = parser.parseExpression(
        "T(java.util.Date)")
        .getValue(Class.class);

Class<?> stringType = parser.parseExpression(
        "T(String)")
        .getValue(Class.class);
```

`T(java.util.Date)` trả về đối tượng Class của `java.util.Date`; `T(String)` trả về Class của `java.lang.String`. Toán tử này chỉ tham chiếu kiểu. Nó không tạo instance mới của class. Muốn gọi constructor, dùng toán tử `new`.

Type reference hữu ích khi expression cần:

- Truy cập static field hoặc hằng số của một class.
- Gọi static method.
- Tham chiếu enum constant.
- So sánh hoặc kiểm tra kiểu bằng `instanceof`.
- Trả về đối tượng Class cho một API hoặc property có kiểu `Class`.

## 2. Cú pháp và quy tắc tên kiểu

Tên kiểu trong `T(...)` được TypeLocator giải quyết khi expression được đánh giá. Với cấu hình mặc định của SpEL:

- Các kiểu trong package `java.lang` có thể viết bằng tên ngắn, ví dụ `T(String)`, `T(Math)`, `T(Integer)`.
- Các kiểu thuộc package khác cần dùng tên đầy đủ, ví dụ `T(java.util.Date)`, `T(java.math.BigDecimal)`.
- Tên kiểu không đặt trong dấu nháy. `T('java.util.Date')` là cú pháp sai vì phần trong ngoặc phải là tên kiểu, không phải String literal.

Ví dụ:

```text
T(String)
T(java.util.UUID)
T(java.math.BigDecimal)
T(java.time.LocalDate)
```

Nếu dùng tên không đầy đủ cho class ngoài `java.lang`, SpEL có thể không tìm thấy kiểu và phát sinh lỗi `TYPE_NOT_FOUND`. Khi chưa cấu hình import prefix, hãy ưu tiên tên đầy đủ để biểu thức rõ ràng và tránh xung đột giữa các class trùng tên đơn giản.

## 3. Lấy đối tượng Class từ T(...)

Vì kết quả của type reference là `Class`, có thể gán trực tiếp vào biến Java hoặc truyền cho API nhận Class:

```java
ExpressionParser parser = new SpelExpressionParser();

Class<?> dateClass = parser.parseExpression(
        "T(java.util.Date)")
        .getValue(Class.class);

Class<?> stringClass = parser.parseExpression(
        "T(String)")
        .getValue(Class.class);

System.out.println(dateClass.getName());
// java.util.Date

System.out.println(stringClass.getName());
// java.lang.String
```

Nếu chỉ cần tên class, có thể dùng property `name` trên kết quả Class:

```text
T(java.util.UUID).name
```

Tuy nhiên, khi cần truy cập metadata kiểu trong Java, nhận kết quả `Class<?>` thường rõ ràng hơn:

```java
Class<?> type = parser.parseExpression(
        "T(java.util.UUID)")
        .getValue(Class.class);

boolean isFinal = java.lang.reflect.Modifier.isFinal(
        type.getModifiers());
```

Không nhầm `T(java.util.UUID)` với `new java.util.UUID(...)`: một biểu thức trả về Class object, biểu thức còn lại yêu cầu tạo instance qua constructor.

## 4. Truy cập static field và hằng số

Giá trị quan trọng của `T(...)` là khả năng truy cập static member của kiểu được tham chiếu. Sau type reference, dùng dấu chấm để đọc static field:

```java
Double pi = parser.parseExpression(
        "T(java.lang.Math).PI")
        .getValue(Double.class);

// pi gần bằng 3.141592653589793
```

Một số ví dụ khác:

```text
T(java.lang.Integer).MAX_VALUE
T(java.lang.Integer).MIN_VALUE
T(java.lang.Boolean).TRUE
T(java.math.BigDecimal).ZERO
T(java.math.BigDecimal).ONE
```

Có thể tham chiếu enum constant như một static field:

```java
Object roundingMode = parser.parseExpression(
        "T(java.math.RoundingMode).HALF_UP")
        .getValue();
```

Ví dụ so sánh hai enum constant trong Spring Reference:

```java
boolean result = parser.parseExpression(
        "T(java.math.RoundingMode).CEILING < " +
        "T(java.math.RoundingMode).FLOOR")
        .getValue(Boolean.class);

// true
```

Enum Java triển khai `Comparable`, vì vậy các constant cùng enum type có thể được so sánh theo thứ tự khai báo. Trong quy tắc nghiệp vụ, thường nên dùng equality hoặc so sánh enum theo ý nghĩa miền dữ liệu để biểu thức dễ hiểu.

## 5. Gọi static method

Sau type reference, có thể gọi static method bằng cú pháp method invocation thông thường:

```java
Integer maximum = parser.parseExpression(
        "T(java.lang.Math).max(12, 30)")
        .getValue(Integer.class);

// 30
```

Ví dụ tính căn bậc hai:

```text
T(Math).sqrt(81)
```

Ví dụ làm tròn số:

```text
T(java.lang.Math).round(12.6)
```

Ví dụ chuyển đổi thành String:

```text
T(String).valueOf(12345)
```

Static method có thể nhận literal, biến, property hoặc kết quả của biểu thức khác:

```java
context.setVariable("amount", new BigDecimal("125.50"));

BigDecimal absolute = parser.parseExpression(
        "T(java.math.BigDecimal).valueOf(#amount.doubleValue()).abs()")
        .getValue(context, BigDecimal.class);
```

Trong biểu thức trên, SpEL tìm class BigDecimal, gọi static method `valueOf`, rồi gọi instance method `abs()` trên kết quả trả về. Với phép tính tiền tệ thực tế, nên tránh chuyển qua double vì có thể mất độ chính xác; ví dụ này chỉ minh họa cách kết hợp static và instance method.

## 6. Dùng T(...) với enum và quy tắc nghiệp vụ

Enum là một trường hợp dùng type reference rất phổ biến. Có thể truy cập constant enum mà không cần đăng ký từng giá trị thành biến:

```java
String state = parser.parseExpression(
        "T(com.example.OrderStatus).PAID.name()")
        .getValue(context, String.class);
```

Trong ví dụ, `com.example.OrderStatus` là tên đầy đủ của enum trong ứng dụng. `PAID` là enum constant; `name()` là instance method trên constant đó.

Có thể so sánh một property enum trên root object:

```text
status == T(com.example.OrderStatus).PAID
```

Hoặc chọn nhãn hiển thị theo trạng thái:

```text
status == T(com.example.OrderStatus).PAID ? 'Completed' : 'Pending'
```

Cách viết này tránh so sánh enum với chuỗi tùy ý. Nó giúp biểu thức thể hiện đúng kiểu dữ liệu của property.

## 7. Kết hợp type reference với instanceof

Toán tử `instanceof` trong SpEL kiểm tra một giá trị có thuộc kiểu được chỉ định hay không. Có thể dùng `T(...)` làm toán hạng kiểu:

```java
boolean isString = parser.parseExpression(
        "#value instanceof T(String)")
        .getValue(context, Boolean.class);
```

Ví dụ kiểm tra một biến có phải BigDecimal:

```text
#amount instanceof T(java.math.BigDecimal)
```

Ví dụ chọn xử lý theo kiểu:

```text
#value instanceof T(String) ? #value.toUpperCase() : #value
```

Hãy dùng `instanceof` khi biểu thức thực sự cần phân biệt kiểu runtime. Nếu có thể thiết kế một API hoặc model thống nhất, việc dựa quá nhiều vào kiểm tra kiểu trong expression có thể khiến quy tắc khó bảo trì.

## 8. TypeLocator: cách SpEL tìm class

SpEL dùng interface `TypeLocator` để tìm class khi đánh giá biểu thức `T(...)`. Trong `StandardEvaluationContext`, implementation mặc định là `StandardTypeLocator`.

`StandardTypeLocator`:

- Sử dụng ClassLoader mặc định (thường là thread context ClassLoader) nếu không truyền ClassLoader riêng.
- Có thể nhận một ClassLoader cụ thể qua constructor.
- Hỗ trợ các import prefix để tìm kiểu bằng tên không đầy đủ.
- Có thể thêm hoặc xóa import prefix bằng `registerImport()` và `removeImport()`.

Ví dụ, nếu ứng dụng có enum `com.example.domain.OrderStatus`, có thể cấu hình prefix để dùng tên ngắn `T(OrderStatus)`:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext(order);

StandardTypeLocator typeLocator =
        new StandardTypeLocator(
                Order.class.getClassLoader());

typeLocator.registerImport("com.example.domain");
context.setTypeLocator(typeLocator);

OrderStatus status = parser.parseExpression(
        "T(OrderStatus).PAID")
        .getValue(context, OrderStatus.class);
```

Khi đã đăng ký prefix `com.example.domain`, TypeLocator có thể thử tìm `OrderStatus` trong package đó. Nếu nhiều package có class trùng tên, tên đầy đủ vẫn an toàn và rõ ràng hơn.

Có thể xem danh sách prefix đang đăng ký:

```java
List<String> prefixes = typeLocator.getImportPrefixes();
```

Và xóa một prefix không còn cần:

```java
typeLocator.removeImport("com.example.domain");
```

Import prefix của TypeLocator chỉ phục vụ việc phân giải type reference trong SpEL. Nó không phải câu lệnh import Java và không tự động áp dụng cho source code Java.

## 9. ClassLoader trong ứng dụng Spring

Trong môi trường đơn giản, ClassLoader mặc định có thể tìm thấy các class của ứng dụng. Nhưng trong ứng dụng có plugin, module, application server, custom class loader hoặc nhiều class loader, SpEL có thể không tìm thấy một kiểu dù class đó thực sự có trong runtime.

Khi ứng dụng tự quản lý EvaluationContext, hãy cấu hình StandardTypeLocator bằng ClassLoader có thể nhìn thấy các kiểu cần dùng:

```java
ClassLoader applicationClassLoader =
        Order.class.getClassLoader();

StandardTypeLocator locator =
        new StandardTypeLocator(applicationClassLoader);

StandardEvaluationContext context =
        new StandardEvaluationContext(order);

context.setTypeLocator(locator);
```

Spring cũng áp dụng cấu hình tương tự trong `StandardBeanExpressionResolver` của module spring-context: TypeLocator được tạo với ClassLoader của BeanFactory tương ứng.

Khi gặp lỗi không tìm thấy type, kiểm tra theo thứ tự:

1. Tên class có đúng package và chính tả không?
2. Class có nằm trên runtime classpath/module path không?
3. ClassLoader đang dùng có nhìn thấy class đó không?
4. Nếu dùng tên ngắn, import prefix đã được đăng ký chưa?
5. Có class cùng tên ở nhiều package gây mơ hồ không?

Không giải quyết lỗi bằng cách thêm import prefix tùy tiện trước khi xác nhận ClassLoader và package thực tế.

## 10. StandardEvaluationContext và SimpleEvaluationContext

Không phải mọi EvaluationContext đều cho phép type reference.

| Context | Hỗ trợ `T(...)` | Mục đích |
|---|---|---|
| `StandardEvaluationContext` | Có, qua TypeLocator. | Đánh giá SpEL đầy đủ tính năng và cấu hình strategy. |
| `SimpleEvaluationContext` | Không hỗ trợ type reference. | Data binding và biểu thức cần giới hạn khả năng. |

Nếu expression dùng `T(java.lang.Math)` nhưng được đánh giá bằng `SimpleEvaluationContext`, SpEL không thể phân giải type reference và sẽ phát sinh lỗi.

Ví dụ context đầy đủ:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext();

Double pi = parser.parseExpression(
        "T(Math).PI")
        .getValue(context, Double.class);
```

Trong trường hợp chỉ cần đọc/ghi property hoặc lọc dữ liệu với một tập tính năng giới hạn, hãy cân nhắc SimpleEvaluationContext. Nếu biểu thức thực sự cần type reference, cần một context cho phép tính năng đó và phải kiểm soát nguồn biểu thức cũng như các kiểu được phép truy cập.

## 11. Bảo mật khi dùng type reference

Type reference mở ra khả năng truy cập static field và static method của class được phân giải. Điều đó có nghĩa expression có thể gọi API tĩnh mà ứng dụng không dự định cung cấp cho người viết expression.

Vì vậy:

- Không đánh giá biểu thức do người dùng hoặc nguồn bên ngoài không tin cậy cung cấp bằng StandardEvaluationContext với quyền truy cập type rộng.
- Hạn chế các class mà expression có thể phân giải, thay vì cho phép mọi class trên classpath.
- Nếu cần custom TypeLocator, cân nhắc allow-list các type cụ thể thay vì chỉ đăng ký package rộng.
- Không coi việc chỉ dùng tên class đầy đủ là một biện pháp bảo mật; tên đầy đủ chỉ xác định class.
- Đừng cho rằng SimpleEvaluationContext hỗ trợ T(...); nó chủ động loại bỏ type references.
- Kiểm tra cả static method và static field được phơi bày qua class được cho phép.

Custom TypeLocator có thể giới hạn những class mà SpEL tìm thấy, nhưng chỉ giới hạn type reference không thay thế việc kiểm soát expression, method invocation, property access và các object khác mà context cung cấp.

## 12. T(...) khác với new và bean reference

Ba cú pháp sau có ý nghĩa khác nhau:

| Cú pháp | Mục đích | Ví dụ |
|---|---|---|
| `T(Type)` | Lấy đối tượng Class và truy cập static member. | `T(Math).PI` |
| `new Type(...)` | Gọi constructor để tạo instance. | `new java.util.Date()` |
| `@beanName` | Tham chiếu bean trong Spring thông qua BeanResolver. | `@pricingService.currentRate` |

Ví dụ:

```text
T(java.util.Date)
```

trả về Class của Date.

```text
new java.util.Date()
```

tạo một Date instance.

```text
@clockService
```

tham chiếu bean tên `clockService` nếu EvaluationContext có BeanResolver phù hợp.

Không dùng T(...) để thay thế bean lookup. Nếu cần một service Spring, nên dùng cơ chế bean reference được cấu hình trong context hoặc truyền service qua root object/variable theo thiết kế ứng dụng.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy type | Tên class sai, thiếu package hoặc class không có trên runtime classpath. | Dùng tên đầy đủ và kiểm tra classpath/module path. |
| `T(String)` chạy nhưng `T(Date)` lỗi | Date thuộc java.util, không phải java.lang. | Dùng `T(java.util.Date)`. |
| Type reference lỗi trong SimpleEvaluationContext | Context này không hỗ trợ type references. | Dùng context cho phép type reference nếu thật sự cần, hoặc chuyển logic sang Java. |
| Class có trong ứng dụng nhưng SpEL không tìm thấy | TypeLocator dùng ClassLoader không nhìn thấy class. | Cấu hình StandardTypeLocator với ClassLoader của ứng dụng. |
| Tên ngắn không được phân giải | Chưa đăng ký import prefix cho package đó. | Dùng tên đầy đủ hoặc gọi `registerImport()`. |
| Gọi static method không được | Method không phải static, tên/signature sai hoặc type không được tìm thấy. | Xác nhận method là static và kiểm tra class/type locator. |
| Đọc enum constant lỗi | Type reference không đúng enum hoặc tên constant sai. | Kiểm tra package, enum type và tên constant. |
| Dùng `T(...)` nhưng mong đợi instance | Nhầm type reference với constructor. | Dùng `new ...(...)` để tạo object. |
| Biểu thức chạy trong môi trường này nhưng lỗi ở môi trường khác | ClassLoader hoặc import prefix khác nhau. | Cấu hình TypeLocator nhất quán với ClassLoader của ứng dụng. |
| Expression có thể gọi static API ngoài dự kiến | Cho phép type reference quá rộng với expression không tin cậy. | Hạn chế TypeLocator và không đánh giá expression không tin cậy. |

## 14. Quy trình kiểm tra một type reference

1. Xác định class cần tham chiếu và package đầy đủ.
2. Kiểm tra class thuộc `java.lang` hay package khác.
3. Dùng `T(FullyQualifiedName)` trước để xác nhận tên kiểu.
4. Lấy kết quả dưới dạng `Class<?>` và kiểm tra `getName()` nếu cần.
5. Nếu truy cập static member, kiểm tra tên member, tính static và chữ ký method.
6. Nếu dùng tên ngắn, kiểm tra import prefix trong StandardTypeLocator.
7. Nếu class không tìm thấy, kiểm tra ClassLoader và runtime classpath.
8. Xác nhận EvaluationContext hỗ trợ type reference; SimpleEvaluationContext không hỗ trợ.
9. Kiểm soát các type và static API mà expression được phép truy cập.
10. Kiểm thử cùng context và ClassLoader như môi trường ứng dụng.

## 15. Ghi nhớ

- `T(Type)` trả về một đối tượng `java.lang.Class`, không tạo instance.
- Tên trong `java.lang` có thể viết ngắn; các package khác nên dùng tên đầy đủ.
- Dùng `T(Type).FIELD` để đọc static field/enum constant và `T(Type).method(...)` để gọi static method.
- Có thể dùng type reference với `instanceof` để kiểm tra kiểu runtime.
- StandardEvaluationContext dùng TypeLocator; StandardTypeLocator hỗ trợ ClassLoader và import prefix.
- SimpleEvaluationContext không hỗ trợ type references.
- Dùng `new` để tạo object và `@beanName` để tham chiếu bean; hai thao tác này khác T(...).
- T(...) mở rộng quyền truy cập static API; không đánh giá expression không tin cậy và hãy giới hạn type có thể phân giải.

## Tài liệu tham khảo

- [Spring Framework Reference — Types and the T Operator](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/types.html)
- [StandardTypeLocator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardTypeLocator.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [SimpleEvaluationContext Source — Type References Excluded](https://github.com/spring-projects/spring-framework/blob/main/spring-expression/src/main/java/org/springframework/expression/spel/support/SimpleEvaluationContext.java)
- [Spring Framework Reference — EvaluationContext and Security](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
