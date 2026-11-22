# Giới hạn constructor trong SimpleEvaluationContext

## 1. Vì sao SimpleEvaluationContext giới hạn constructor?

Spring Expression Language (SpEL) có thể tạo object mới bằng constructor reference, ví dụ:

```text
new java.lang.String('hello')
new com.example.Address('Ho Chi Minh City')
```

Khả năng này hữu ích khi expression cần tạo một giá trị hoặc object trong lúc đánh giá. Tuy nhiên, constructor invocation cũng cho phép expression tạo những kiểu object mà ứng dụng không muốn phơi bày cho người viết expression.

`SimpleEvaluationContext` được thiết kế cho các trường hợp cần một tập con SpEL có giới hạn, thường là data binding và lọc dữ liệu dựa trên property. Vì vậy, nó chủ động loại trừ ba nhóm tính năng:

- Java type references bằng `T(...)`.
- Constructor references bằng `new Type(...)`.
- Bean references bằng cú pháp `@beanName`.

Đây là một phần trong thiết kế của context, không phải lỗi cấu hình. Builder của `SimpleEvaluationContext` không có tùy chọn bật constructor invocation hoặc đăng ký `ConstructorResolver`.

## 2. Constructor reference trong SpEL hoạt động thế nào?

Cú pháp tạo object:

```text
new FullyQualifiedTypeName(argument1, argument2, ...)
```

Ví dụ với kiểu Java chuẩn:

```java
ExpressionParser parser = new SpelExpressionParser();

String greeting = parser.parseExpression(
        "new java.lang.String('hello')")
        .getValue(String.class);
```

Ví dụ với class của ứng dụng:

```text
new com.example.Address('Ho Chi Minh City', 'VN')
```

SpEL cần xác định kiểu được tạo và tìm constructor phù hợp với số lượng, kiểu của các đối số. Việc tìm constructor được thực hiện qua các `ConstructorResolver` mà EvaluationContext cung cấp.

Trong `StandardEvaluationContext`, SpEL cung cấp resolver mặc định dựa trên reflection để tìm constructor. Trong `SimpleEvaluationContext`, danh sách constructor resolver luôn rỗng, vì vậy expression không thể phân giải constructor.

## 3. SimpleEvaluationContext không cho phép tạo object bằng new

Ví dụ sau có thể parse được về mặt cú pháp, nhưng không thể thực thi thành công với SimpleEvaluationContext:

```java
ExpressionParser parser = new SpelExpressionParser();

var simpleContext =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

var expression = parser.parseExpression(
        "new java.lang.String('hello')");

// Không được hỗ trợ trong SimpleEvaluationContext:
String value = expression.getValue(simpleContext, String.class);
```

Khi đánh giá, SpEL không tìm thấy constructor resolver để xử lý `new`. Việc gọi `getValue()` vì thế thất bại với lỗi đánh giá SpEL. Đừng dựa vào một thông báo lỗi cụ thể giữa các phiên bản; điều ổn định là constructor invocation không thuộc tập tính năng của context này.

Constructor của class ứng dụng cũng bị giới hạn tương tự:

```text
new com.example.Address('District 1')
```

Không có cách gọi `withConstructors()` hoặc `withConstructorResolvers()` trên builder để bật tính năng này. Nếu expression cần tạo object bằng `new`, hãy xem lại thiết kế context hoặc chuyển việc tạo object ra Java.

## 4. Cách kiểm tra giới hạn bằng API

`SimpleEvaluationContext` triển khai `EvaluationContext`. API `getConstructorResolvers()` của context này trả về danh sách rỗng:

```java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

boolean hasConstructorResolvers =
        !context.getConstructorResolvers().isEmpty();

// false
```

Danh sách rỗng là bằng chứng kỹ thuật cho thấy context không cung cấp cơ chế giải quyết constructor. Builder không có phương thức để thay danh sách này.

SimpleEvaluationContext cũng không hỗ trợ type references. TypeLocator của nó được cấu hình để báo lỗi khi expression cố phân giải `T(...)`. Vì vậy, cả hai biểu thức sau đều nằm ngoài phạm vi hỗ trợ:

```text
new java.lang.String('hello')
T(java.lang.String)
```

Constructor reference và type reference có liên quan nhưng là hai cú pháp riêng: `new` yêu cầu tạo instance, còn `T(...)` tham chiếu đối tượng Class. SimpleEvaluationContext loại trừ cả hai.

## 5. Những khả năng builder vẫn hỗ trợ

Giới hạn constructor không có nghĩa SimpleEvaluationContext không thể tùy chỉnh. Builder cho phép chọn các khả năng cần thiết cho data binding:

| Cách tạo context | Khả năng chính |
|---|---|
| `forReadOnlyDataBinding()` | Đọc public property bằng DataBindingPropertyAccessor. |
| `forReadWriteDataBinding()` | Đọc và ghi public property. |
| `forPropertyAccessors(...)` | Dùng PropertyAccessor tùy chỉnh, thường dành cho cấu trúc dữ liệu riêng. |
| `withInstanceMethods()` | Bật một DataBindingMethodResolver để gọi instance method trong phạm vi data binding. |
| `withMethodResolvers(...)` | Đăng ký các MethodResolver được kiểm soát. |
| `withTypeConverter(...)` hoặc `withConversionService(...)` | Cấu hình chuyển đổi kiểu. |
| `withRootObject(...)` | Chọn root object mặc định. |
| `withAssignmentDisabled()` | Tắt phép gán trong expression. |

Không phương thức nào trong bảng bật constructor invocation. Đặc biệt, `withInstanceMethods()` chỉ cho phép gọi instance method qua DataBindingMethodResolver; nó không mở constructor, static method, type reference hoặc bean reference.

Ví dụ tạo context chỉ cho đọc property:

```java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withRootObject(customer)
                .build();

String name = parser.parseExpression("name")
        .getValue(context, String.class);
```

Ví dụ cho phép instance method trong data binding:

```java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withInstanceMethods()
                .withRootObject(customer)
                .build();

String displayName = parser.parseExpression(
        "displayName('Customer:')")
        .getValue(context, String.class);
```

Việc bật instance method không thay đổi danh sách constructor resolver; `new Type(...)` vẫn không được hỗ trợ.

## 6. Thay thế 1: tạo object trong Java rồi truyền vào context

Nếu object cần thiết đã biết trước, cách đơn giản nhất là khởi tạo nó bằng Java trước khi đánh giá expression. Sau đó, truyền object làm root hoặc đăng ký nó thành variable.

Ví dụ truyền object làm root:

```java
Address address = new Address("Ho Chi Minh City", "VN");

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withRootObject(address)
                .build();

String city = parser.parseExpression("city")
        .getValue(context, String.class);
```

Ví dụ truyền object qua variable:

```java
Address address = new Address("Ho Chi Minh City", "VN");

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("address", address);

String city = parser.parseExpression("#address.city")
        .getValue(context, String.class);
```

Cách này giữ trách nhiệm tạo object trong Java, nơi ứng dụng kiểm soát constructor và đối số. Expression chỉ đọc hoặc xử lý object đã được cung cấp.

## 7. Thay thế 2: dùng factory method được cho phép rõ ràng

Nếu expression cần yêu cầu tạo một giá trị theo một số tham số, có thể cung cấp một factory method có phạm vi hẹp thay vì cho phép gọi constructor tùy ý.

SimpleEvaluationContext hỗ trợ function đăng ký dưới dạng biến. Function có thể là static Java Method hoặc MethodHandle. Ví dụ:

```java
public final class AddressFunctions {

    private AddressFunctions() {
    }

    public static Address createAddress(String city) {
        return new Address(city, "VN");
    }
}
```

Đăng ký method factory:

```java
Method factory = AddressFunctions.class.getMethod(
        "createAddress", String.class);

SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("createAddress", factory);

Address address = parser.parseExpression(
        "#createAddress('Ho Chi Minh City')")
        .getValue(context, Address.class);
```

Cách này không bật constructor invocation. Expression chỉ có thể gọi function cụ thể mà ứng dụng đã đăng ký. Hãy giới hạn factory ở một nhiệm vụ rõ ràng, xác thực đối số và tránh trả về object có nhiều method nhạy cảm.

Function và variable dùng chung namespace trong SimpleEvaluationContext. Vì vậy, không đăng ký function và variable trùng tên.

Nếu không cần tạo object động, truyền object đã khởi tạo bằng root hoặc variable vẫn đơn giản và dễ kiểm soát hơn.

## 8. Khi nào cần StandardEvaluationContext?

Nếu yêu cầu nghiệp vụ thực sự cần expression tự gọi constructor, SpEL đầy đủ cung cấp `StandardEvaluationContext`. Context này có danh sách constructor resolver mặc định dựa trên reflection và hỗ trợ type reference.

Ví dụ với expression được ứng dụng tin cậy định nghĩa:

```java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

String value = parser.parseExpression(
        "new java.lang.String('hello')")
        .getValue(context, String.class);

// hello
```

Với class ứng dụng, cần dùng tên đầy đủ nếu TypeLocator chưa có import prefix phù hợp:

```text
new com.example.Address('Ho Chi Minh City', 'VN')
```

Chuyển sang StandardEvaluationContext chỉ vì cần constructor có nghĩa là chuyển sang tập tính năng rộng hơn của SpEL. Context này cũng cho phép type reference, method invocation, bean reference và các khả năng khác tùy cấu hình. Chỉ dùng khi expression đến từ nguồn tin cậy và quyền truy cập rộng đó là có chủ đích.

Không dùng StandardEvaluationContext để đánh giá expression do người dùng cuối hoặc hệ thống bên ngoài không tin cậy cung cấp. Constructor và method invocation có thể thực thi hành vi của ứng dụng hoặc thư viện trên classpath.

## 9. Giới hạn constructor trong một context đầy đủ

Nếu ứng dụng cần StandardEvaluationContext cho một số tính năng nhưng không muốn cho phép constructor tùy ý, có thể cấu hình constructor resolver theo allow-list hoặc cung cấp một EvaluationContext chuyên biệt chỉ cho các constructor đã duyệt.

Ví dụ về hướng cấu hình:

```java
StandardEvaluationContext context =
        new StandardEvaluationContext(rootObject);

// Chỉ đăng ký ConstructorResolver do ứng dụng kiểm soát.
// Resolver phải từ chối mọi type/constructor ngoài allow-list.
context.setConstructorResolvers(
        List.of(new ApprovedConstructorResolver()));
```

`ApprovedConstructorResolver` ở đây là implementation do ứng dụng viết; SpEL không cung cấp sẵn một allow-list resolver tổng quát. Resolver phải xác thực cả kiểu được tạo, chữ ký constructor và đối số. Nếu cần type reference, cũng cần kiểm soát TypeLocator để expression không tham chiếu các class ngoài phạm vi.

Một resolver tùy chỉnh chỉ giới hạn constructor. Nó không tự giới hạn method invocation, property access, static method, bean reference hoặc object graph. Mỗi khả năng cần được kiểm soát riêng.

Nếu mục tiêu chỉ là data binding hoặc property filtering, dùng SimpleEvaluationContext vẫn là thiết kế phù hợp hơn.

## 10. Giới hạn constructor không phải bảo đảm an toàn tuyệt đối

Spring mô tả SimpleEvaluationContext là một context giới hạn tính năng theo hướng best-effort. Việc loại trừ constructor, type reference và bean reference làm giảm bề mặt khả năng của expression, nhưng không bảo đảm expression từ nguồn không tin cậy luôn an toàn.

Expression vẫn có thể truy cập property, gọi instance method hoặc function nếu context đã cấu hình cho phép. Một getter hoặc method có thể có side effect, đọc dữ liệu nhạy cảm hoặc thực hiện thao tác tốn kém. Root object, nested object, PropertyAccessor, MethodResolver, variable và function đều có thể làm lộ thêm hành vi.

Khi đánh giá expression do người dùng cung cấp:

- Chỉ cung cấp root object/variable có dữ liệu và hành vi tối thiểu.
- Ưu tiên DTO chuyên biệt thay vì entity hoặc service đầy đủ.
- Chỉ bật instance method khi thật sự cần; không đăng ký method resolver rộng một cách tùy tiện.
- Không đưa factory function có quyền rộng vào context.
- Kiểm tra PropertyAccessor và method có side effect.
- Giới hạn độ dài và độ phức tạp của expression theo yêu cầu ứng dụng.
- Không xem SimpleEvaluationContext như sandbox bảo mật tuyệt đối.

## 11. Kiểm thử giới hạn constructor

Có thể viết unit test để chứng minh constructor expression không hoạt động trong SimpleEvaluationContext và hoạt động trong StandardEvaluationContext khi dùng expression tin cậy:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.expression.Expression;
import org.springframework.expression.spel.SpelEvaluationException;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.SimpleEvaluationContext;
import org.springframework.expression.spel.support.StandardEvaluationContext;

class SimpleEvaluationContextConstructorTest {

    private final SpelExpressionParser parser =
            new SpelExpressionParser();

    @Test
    void constructorReferenceIsNotSupportedBySimpleContext() {
        Expression expression = parser.parseExpression(
                "new java.lang.String('hello')");

        SimpleEvaluationContext context =
                SimpleEvaluationContext.forReadOnlyDataBinding().build();

        assertThrows(
                SpelEvaluationException.class,
                () -> expression.getValue(context, String.class));
    }

    @Test
    void trustedConstructorReferenceWorksWithStandardContext() {
        Expression expression = parser.parseExpression(
                "new java.lang.String('hello')");

        StandardEvaluationContext context =
                new StandardEvaluationContext();

        assertEquals(
                "hello",
                expression.getValue(context, String.class));
    }
}
```

Test thứ nhất kiểm tra giới hạn của SimpleEvaluationContext. Test thứ hai minh họa khả năng của StandardEvaluationContext; chỉ dùng trong test với expression cố định, tin cậy.

Có thể kiểm tra thêm danh sách constructor resolver:

```java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

assertTrue(context.getConstructorResolvers().isEmpty());
```

Các test này kiểm tra hành vi và cấu hình của context, không phải kiểm tra chất lượng nội dung expression.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `new Type(...)` thất bại trong SimpleEvaluationContext | Context không cung cấp ConstructorResolver. | Tạo object trong Java hoặc dùng factory được đăng ký rõ ràng. |
| `T(Type)` báo không tìm thấy type | SimpleEvaluationContext không hỗ trợ type references. | Tránh type reference hoặc dùng context đầy đủ cho expression tin cậy. |
| Builder không có phương thức bật constructor | Constructor support bị loại trừ có chủ đích. | Không tìm cách bật bằng builder; chọn một thiết kế thay thế. |
| `withInstanceMethods()` vẫn không cho phép `new` | Tùy chọn này chỉ bật instance method resolver. | Phân biệt method invocation với constructor invocation. |
| Factory function không được gọi | Method chưa được đăng ký hoặc tên function không khớp. | Đăng ký Method/MethodHandle bằng `setVariable()` và gọi bằng `#functionName(...)`. |
| Factory có thể tạo object không mong muốn | Function được đăng ký quá rộng hoặc thiếu kiểm tra đối số. | Chỉ cung cấp factory chuyên biệt và kiểm tra đầu vào. |
| Chuyển sang StandardEvaluationContext làm tăng quyền expression | Context đầy đủ hỗ trợ nhiều tính năng hơn constructor. | Chỉ dùng với expression tin cậy và cấu hình quyền truy cập rõ ràng. |
| Cho rằng SimpleEvaluationContext an toàn tuyệt đối | Giới hạn là best-effort; method/property vẫn có thể có side effect. | Giới hạn object graph, accessor, resolver, variable và function. |

## 13. Quy trình chọn cách xử lý

1. Xác định expression có thật sự cần tạo instance mới hay chỉ cần đọc/ghi một object đã có.
2. Nếu object đã biết trước, tạo trong Java rồi truyền qua root object hoặc variable.
3. Nếu cần một thao tác tạo có tham số, cân nhắc factory method hẹp được đăng ký dưới dạng function.
4. Nếu chỉ cần đọc/ghi property, giữ SimpleEvaluationContext với quyền tối thiểu.
5. Nếu cần constructor invocation trong expression tin cậy, cân nhắc StandardEvaluationContext.
6. Nếu dùng StandardEvaluationContext nhưng muốn giới hạn constructor, triển khai ConstructorResolver allow-list và giới hạn TypeLocator phù hợp.
7. Kiểm tra riêng method invocation, property access, bean reference và các object mà context làm lộ ra.
8. Viết test xác nhận constructor bị từ chối trong SimpleEvaluationContext và test cho phương án thay thế đã chọn.

## 14. Ghi nhớ

- SimpleEvaluationContext chủ động loại trừ constructor reference `new Type(...)`, type reference `T(...)` và bean reference `@beanName`.
- `getConstructorResolvers()` của SimpleEvaluationContext luôn trả về danh sách rỗng; builder không có tùy chọn bật constructor.
- `withInstanceMethods()` chỉ bật instance method invocation có giới hạn, không bật constructor hoặc static method.
- Tạo object trong Java rồi truyền qua root object hoặc variable là cách thay thế đơn giản.
- Có thể đăng ký một factory Method/MethodHandle như function nếu chỉ cần cung cấp một hành động tạo object được kiểm soát.
- StandardEvaluationContext hỗ trợ constructor qua resolver mặc định, nhưng cũng mở rộng nhiều khả năng SpEL khác.
- Có thể dùng ConstructorResolver allow-list trong context tùy chỉnh khi thật sự cần kiểm soát constructor.
- SimpleEvaluationContext là giới hạn tính năng best-effort, không phải sandbox an toàn tuyệt đối.

## Tài liệu tham khảo

- [Spring Framework Reference — Understanding EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [EvaluationContext API — Constructor Resolvers](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
