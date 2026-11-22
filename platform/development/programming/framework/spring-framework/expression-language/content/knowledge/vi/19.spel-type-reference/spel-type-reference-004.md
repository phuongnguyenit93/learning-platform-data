# Gọi method static qua type reference trong SpEL

## Mục tiêu

Spring Expression Language (SpEL) có thể gọi method static của một class mà không cần tạo instance. Cách làm là dùng type reference `T(...)` để chỉ định class, sau đó dùng dấu chấm để gọi static method hoặc đọc static field.

Ví dụ:

```spel
T(java.lang.Math).max(10, 20)
T(java.lang.Integer).parseInt('42')
T(java.time.LocalDate).of(2026, 11, 12)
```

`T(...)` làm cho class trở thành đối tượng đích của phần truy cập tiếp theo. SpEL tìm static member trên class đó và thực hiện lời gọi bằng cơ chế method resolution của evaluation context.

## 1. Cú pháp type reference

Cú pháp tổng quát:

```spel
T(fully.qualified.ClassName)
```

Để gọi static method, nối tên method và đối số phía sau:

```spel
T(java.lang.Math).sqrt(81)
T(java.util.UUID).randomUUID()
T(java.lang.Integer).parseInt('123')
```

Để đọc static field, dùng cùng cú pháp type reference:

```spel
T(java.lang.Math).PI
T(java.lang.Integer).MAX_VALUE
```

Type reference là cú pháp `T` viết hoa, có ngoặc đơn bao quanh tên class. Tên class có thể là tên đầy đủ gồm package. Với class trong `java.lang`, `StandardTypeLocator` mặc định đã đăng ký package này nên có thể viết ngắn:

```spel
T(Math).max(10, 20)
T(Integer).parseInt('42')
```

Với class ngoài `java.lang`, nên dùng tên đầy đủ hoặc đăng ký package import trong type locator.

## 2. Ví dụ Java hoàn chỉnh

Để đánh giá lời gọi static method qua SpEL, tạo parser, evaluation context và lấy kết quả theo kiểu cần dùng:

```java
ExpressionParser parser = new SpelExpressionParser();
EvaluationContext context = new StandardEvaluationContext();

Integer max = parser.parseExpression("T(java.lang.Math).max(10, 20)")
        .getValue(context, Integer.class);

Integer parsed = parser.parseExpression("T(java.lang.Integer).parseInt('42')")
        .getValue(context, Integer.class);

LocalDate date = parser.parseExpression(
        "T(java.time.LocalDate).of(2026, 11, 12)")
        .getValue(context, LocalDate.class);
```

Trong ví dụ trên:

- `Math.max` gọi method static và trả về số lớn hơn.
- `Integer.parseInt` chuyển chuỗi thành số nguyên.
- `LocalDate.of` tạo giá trị ngày từ năm, tháng và ngày.

Không cần tạo `new Math()`, `new Integer()` hoặc `new LocalDate()` để gọi các method static này. Type reference chỉ ra class chứa member cần gọi.

## 3. Static method có đối số động

Đối số của static method có thể là literal, property của root object hoặc biến trong `EvaluationContext`. Điều này giúp tái sử dụng cùng một expression với dữ liệu thay đổi:

```java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "T(java.lang.Math).max(#minimum, #candidate)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("minimum", 10);
context.setVariable("candidate", 27);

Integer result = expression.getValue(context, Integer.class);
```

Kết quả là `27`. Nếu `candidate` thay đổi trong context của lần đánh giá tiếp theo, cùng expression sẽ gọi method với giá trị mới.

Cũng có thể dùng property từ root object:

```spel
T(java.lang.Math).max(minimumAllowed, requestedValue)
```

Ở đây các property được phân giải từ root object; `T(java.lang.Math)` vẫn xác định class chứa static method.

## 4. Đăng ký package import cho type locator

SpEL dùng `TypeLocator` để tìm class được nêu trong `T(...)`. `StandardTypeLocator` mặc định hỗ trợ tên đầy đủ và package `java.lang`. Nếu muốn viết tên class ngắn cho package khác, đăng ký package import:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
StandardTypeLocator typeLocator = new StandardTypeLocator();
typeLocator.registerImport("java.time");
context.setTypeLocator(typeLocator);

ExpressionParser parser = new SpelExpressionParser();
LocalDate today = parser.parseExpression("T(LocalDate).now()")
        .getValue(context, LocalDate.class);
```

Sau khi đăng ký `java.time`, biểu thức có thể dùng `T(LocalDate)` thay cho `T(java.time.LocalDate)`. Nếu không đăng ký import, hãy dùng tên class đầy đủ để tránh lỗi không tìm thấy type.

Việc đăng ký import chỉ ảnh hưởng cách `TypeLocator` tìm class. Nó không import static method theo cú pháp Java và không làm cho method có thể được gọi mà không có `T(...)`.

## 5. Gọi static method overload

Static method cũng có thể được overload như method instance. SpEL lựa chọn chữ ký dựa trên tên method, số lượng và kiểu runtime của đối số, cùng khả năng chuyển đổi do `TypeConverter` cung cấp.

Ví dụ:

```spel
T(java.lang.Math).max(10, 20)
T(java.lang.Math).max(10.5, 20.5)
```

Lời gọi đầu cung cấp các số nguyên; lời gọi sau cung cấp các số thập phân. SpEL phân giải overload tương thích với kiểu đối số. Khi class có nhiều overload và đối số có thể chuyển đổi sang nhiều kiểu, nên tạo đối số có kiểu rõ ràng thay vì phụ thuộc vào conversion ngầm.

Ví dụ dùng `Long` rõ ràng:

```spel
T(java.lang.Long).valueOf('9000000000')
```

Kết quả của `valueOf` là một `Long`, có thể được truyền tiếp vào method cần kiểu `Long` hoặc `Number`.

Kiểu đích truyền vào `getValue(context, TargetType.class)` chỉ dùng để chuyển đổi kết quả sau khi biểu thức được đánh giá; nó không ép SpEL chọn một overload static cụ thể.

## 6. Static field và enum constant

Type reference không chỉ dùng cho method. Có thể đọc public static field hoặc enum constant thông qua class:

```spel
T(java.lang.Math).PI
T(java.lang.Integer).MAX_VALUE
T(com.example.OrderStatus).PAID
```

Ví dụ cuối truy cập enum constant `PAID` của enum `OrderStatus`. Tên package và class phải khớp ứng dụng thực tế, đồng thời type locator phải tìm được class đó.

Static field thường hữu ích cho hằng số do thư viện hoặc ứng dụng cung cấp. Nếu giá trị cần cấu hình theo môi trường hoặc request, nên truyền nó qua property/variable thay vì gắn cố định vào expression.

## 7. Static method và constructor là hai thao tác khác nhau

Type reference gọi method static trên class. Nếu muốn tạo instance bằng constructor, dùng cú pháp constructor `new` của SpEL:

```spel
T(java.time.LocalDate).now()
new java.math.BigDecimal('19.95')
```

Biểu thức đầu gọi static method `now()` của `LocalDate`. Biểu thức sau gọi constructor của `BigDecimal`. Không dùng `T(...)` như một cách tạo instance; `T(...)` chỉ tham chiếu đến class.

Nếu class cung cấp static factory method như `valueOf`, `of` hoặc `from`, có thể gọi factory đó qua type reference:

```spel
T(java.math.BigDecimal).valueOf(100L)
T(java.time.LocalDate).of(2026, 11, 12)
```

Factory method thường giúp diễn đạt rõ cách tạo giá trị theo API của class.

## 8. Phạm vi hỗ trợ của EvaluationContext

`StandardEvaluationContext` hỗ trợ type reference thông qua `TypeLocator`, đồng thời hỗ trợ reflective method resolution. Đây là lựa chọn thông dụng khi expression cần gọi static method của class.

`SimpleEvaluationContext` được thiết kế cho data binding với tập tính năng bị giới hạn; nó không hỗ trợ type references. Nếu expression cần `T(...)`, hãy dùng một context hỗ trợ tính năng này và giới hạn quyền truy cập theo chính sách ứng dụng.

Trong context tùy chỉnh, type locator có thể được thay bằng implementation riêng để kiểm soát class nào được phép tham chiếu. Method resolver và type converter cũng có thể được cấu hình để kiểm soát cách method được tìm và đối số được chuyển đổi.

## 9. An toàn khi đánh giá type reference

Type reference có thể mở đường tới static method và static field của class được phép tìm thấy. Vì vậy, không nên đánh giá expression do người dùng hoặc nguồn không tin cậy cung cấp bằng một `StandardEvaluationContext` có đầy đủ quyền reflection mà không có giới hạn.

Các nguyên tắc thực tế:

- Chỉ cho phép type locator tìm những class cần thiết cho nghiệp vụ.
- Tránh expose các class có static method có thể thực hiện thao tác nhạy cảm hoặc side effect.
- Giới hạn method resolver và object được đưa vào root/context theo nhu cầu thực tế.
- Với biểu thức do người dùng kiểm soát, cân nhắc context hạn chế và API helper allowlist thay vì cho phép type reference tùy ý.
- Không xem việc giới hạn package import là sandbox đầy đủ; các object khác trong context vẫn có thể expose method riêng.
- Không nối input bên ngoài trực tiếp vào tên class hoặc source expression. Truyền dữ liệu qua biến có kiểu rõ ràng.

Ví dụ, nếu chỉ cần tính giá trị lớn hơn giữa hai số, có thể expose một helper có API hẹp hoặc kiểm tra giá trị ở Java thay vì cho người dùng tự chọn class và method bất kỳ.

## 10. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `T(...)` không parse được | Sai cú pháp, thiếu ngoặc hoặc viết `t` thường thay vì `T`. | Dùng `T(package.ClassName)` với chữ T viết hoa. |
| Không tìm thấy class | Tên package/class sai, package chưa import hoặc classloader không nhìn thấy class. | Dùng tên đầy đủ; kiểm tra `TypeLocator` và classloader. |
| `T(LocalDate)` không hoạt động | `java.time` chưa được đăng ký trong type locator. | Dùng `T(java.time.LocalDate)` hoặc đăng ký import `java.time`. |
| Không tìm thấy static method | Sai tên, sai số đối số, method không public hoặc chữ ký không tương thích. | Kiểm tra API của class, kiểu đối số và method resolver. |
| Chọn overload không như mong muốn | Đối số có kiểu không rõ hoặc có thể chuyển đổi sang nhiều chữ ký. | Truyền đối số có kiểu cụ thể hoặc dùng helper có chữ ký riêng. |
| `T(...)` hoạt động trong context này nhưng không hoạt động trong context khác | Context khác nhau về TypeLocator hoặc loại context bị giới hạn. | Kiểm tra `EvaluationContext`; `SimpleEvaluationContext` không hỗ trợ type reference. |
| Biểu thức chạy được nhưng có side effect ngoài ý muốn | Static method được gọi thực hiện thao tác thay đổi trạng thái hoặc truy cập tài nguyên. | Chỉ expose và gọi method thuần/được cho phép; giới hạn type locator và resolver. |

## Ghi nhớ

- `T(fully.qualified.ClassName)` tham chiếu đến class trong SpEL.
- Gọi static method bằng `T(Class).method(arguments)`; đọc static field bằng `T(Class).FIELD`.
- `StandardTypeLocator` mặc định hỗ trợ `java.lang`; package khác có thể dùng tên đầy đủ hoặc đăng ký import.
- Static method có thể overload; kiểu và số lượng đối số cùng TypeConverter ảnh hưởng việc chọn chữ ký.
- Kiểu đích của `getValue` chuyển đổi kết quả, không chọn overload.
- `T(...)` tham chiếu class; `new ...` mới gọi constructor.
- `StandardEvaluationContext` hỗ trợ type reference; `SimpleEvaluationContext` không hỗ trợ.
- Giới hạn TypeLocator, MethodResolver và các object được expose khi expression không hoàn toàn đáng tin cậy.
- Truyền dữ liệu runtime qua biến có kiểu thay vì nối dữ liệu vào source expression.

## Tài liệu tham khảo

- [Spring Framework Reference — Types (Type References)](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/types.html)
- [Spring Framework Reference — Methods](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — StandardTypeLocator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardTypeLocator.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)