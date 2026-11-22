# Chặn type reference, constructor và method nguy hiểm trong SpEL

## Mục tiêu

Spring Expression Language (SpEL) có thể làm nhiều hơn việc đọc property và so sánh giá trị. Tùy `EvaluationContext` được cung cấp, một expression có thể tham chiếu class bằng `T(...)`, tạo object bằng `new`, gọi instance hoặc static method, truy cập Spring bean bằng `@beanName`, và đi qua property accessor của object đầu vào.

Những khả năng này rất hữu ích với expression do ứng dụng kiểm soát. Khi expression hoặc một phần source expression đến từ người dùng, file cấu hình bên ngoài hoặc dữ liệu lưu trong database, chúng có thể mở ra đường thực thi code, truy cập tài nguyên hoặc tiêu thụ tài nguyên ngoài dự kiến.

Nguyên tắc an toàn là chỉ expose đúng những khả năng mà rule cần. Nếu chỉ cần đọc vài property và tính điều kiện, dùng context giới hạn và object dữ liệu đơn giản. Nếu bắt buộc dùng type reference, constructor hoặc method, hãy allowlist class và method cụ thể, đồng thời kiểm soát bean, function và property accessor được cung cấp.

## 1. Những đường thực thi cần kiểm soát

| Khả năng SpEL | Ví dụ | Rủi ro nếu mở quá rộng |
| --- | --- | --- |
| Type reference | `T(java.lang.Math).max(1, 2)` | Có thể tham chiếu class và gọi static member của class đó. |
| Constructor invocation | `new java.math.BigDecimal('12.50')` | Có thể tạo object, kể cả object có constructor tốn tài nguyên hoặc có tác dụng phụ. |
| Method invocation | `customer.refresh()` | Có thể gọi method trên root object, biến hoặc object lồng nhau. |
| Bean reference | `@pricingService.calculate(total)` | Có thể expose service, repository hoặc bean có quyền truy cập hệ thống. |
| Function | `#calculate(value)` | Function đã đăng ký có thể thực thi bất kỳ Java code nào mà method đó làm. |
| Property/index access | `customer.profile.name`, `items[#index]` | Getter hoặc accessor tùy chỉnh có thể tải dữ liệu, thay đổi trạng thái hoặc mở rộng collection. |

Không chỉ cú pháp `T(...)` hoặc `new` mới cần chú ý. Một expression không có type reference vẫn có thể gọi method trên object được expose hoặc kích hoạt logic bên trong getter.

## 2. Chọn SimpleEvaluationContext khi chỉ cần data binding

`SimpleEvaluationContext` được thiết kế cho một tập tính năng SpEL giới hạn hơn. Nó không hỗ trợ type references, constructor invocation hoặc bean references. Method invocation bị tắt mặc định; ứng dụng có thể opt-in instance methods khi thật sự cần.

Với rule chỉ đọc property, bắt đầu bằng read-only data binding:

```java
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "active == true and age >= 18");

Boolean allowed = expression.getValue(
        context, customerView, Boolean.class);
```

Context này phù hợp với DTO/view object có property đơn giản. Không cần cung cấp toàn bộ ApplicationContext hoặc domain service nếu rule chỉ đọc dữ liệu đã chuẩn bị.

Nếu expression cần ghi property, `forReadWriteDataBinding()` có thể bật data-binding write access. Chỉ dùng chế độ này khi cập nhật object là yêu cầu thực sự; rule chỉ kiểm tra nên giữ read-only.

### Khi cần instance methods

Builder có thể bật instance method invocation:

```java
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .withInstanceMethods()
        .build();
```

Đây là opt-in cho method invocation, không phải allowlist theo tên method. Chỉ bật nó khi object được expose có API hẹp, dễ dự đoán và không chứa method ghi dữ liệu hoặc truy cập tài nguyên. `SimpleEvaluationContext` vẫn không hỗ trợ `T(...)`, `new` hoặc `@beanName`.

Read-only cũng không đảm bảo getter thuần đọc. Getter có thể kích hoạt ORM lazy loading, truy vấn database, gọi service hoặc thay đổi trạng thái. Hãy dùng view object có getter đơn giản và chỉ expose dữ liệu cần thiết.

## 3. Hạn chế type reference bằng TypeLocator

Trong `StandardEvaluationContext`, type reference `T(...)` được phân giải qua `TypeLocator`. `StandardTypeLocator` thuận tiện cho expression nội bộ, nhưng có thể tìm nhiều class trong classpath. Với expression không hoàn toàn tin cậy, hãy thay bằng locator chỉ trả về những type được cho phép.

Ví dụ allowlist chỉ cho phép `java.lang.Math`:

```java
public final class AllowlistedTypeLocator implements TypeLocator {

    private final Map<String, Class<?>> allowedTypes = Map.of(
            "java.lang.Math", Math.class);

    @Override
    public Class<?> findType(String typeName) throws EvaluationException {
        Class<?> type = allowedTypes.get(typeName);
        if (type == null) {
            throw new EvaluationException("Type is not allowed: " + typeName);
        }
        return type;
    }
}
```

Cấu hình context:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setTypeLocator(new AllowlistedTypeLocator());
```

Giờ expression có thể dùng `T(java.lang.Math)` nếu method resolution cho phép method tương ứng. Các type khác sẽ bị từ chối ngay ở bước tìm type.

Type allowlist nên dùng tên class đầy đủ và chính xác. Tránh quy tắc rộng như cho phép mọi class trong một package hoặc mọi class có tên bắt đầu bằng một prefix, vì package có thể chứa class không dự định expose.

## 4. Hạn chế method invocation

Method invocation là đường thực thi code trên root object, property object, variable hoặc class được tham chiếu. Nếu expression không cần gọi method, có thể bỏ toàn bộ reflective method resolvers:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setMethodResolvers(Collections.emptyList());
```

Điều này chặn method invocation qua các resolver đã cấu hình trong context. Nếu cần một số method, hãy dùng resolver/filter có allowlist thay vì mở mọi method trên mọi object.

### Dùng MethodFilter cho các class được phép

`StandardEvaluationContext.registerMethodFilter(...)` có thể giới hạn danh sách method mà reflective method resolver xem xét trên một type cụ thể:

```java
Set<String> allowedNames = Set.of("max", "min", "abs");

StandardEvaluationContext context = new StandardEvaluationContext();
context.registerMethodFilter(Math.class, methods ->
        methods.stream()
                .filter(method -> allowedNames.contains(method.getName()))
                .toList());
```

Filter này chỉ áp dụng cho type đã đăng ký và reflective method resolver. Nếu thay resolver mặc định bằng resolver khác, phải bảo đảm resolver mới thực thi cùng chính sách. Cũng cần kiểm soát các object khác trong root/context; giới hạn method của `Math` không tự giới hạn method trên một service object khác.

Nếu method invocation cần được allowlist trên nhiều class, đăng ký filter cho từng class được expose hoặc cung cấp một `MethodResolver` tùy chỉnh chỉ phân giải các chữ ký được phép.

## 5. Chặn constructor invocation

Constructor invocation dùng `ConstructorResolver`. Nếu expression không cần tạo object, có thể xóa reflective constructor resolvers khỏi context:

```java
StandardEvaluationContext context = new StandardEvaluationContext();
context.setConstructorResolvers(Collections.emptyList());
```

Khi không có constructor resolver phù hợp, expression dạng `new SomeType(...)` không thể được phân giải.

Nếu cần một số constructor cụ thể, dùng `ConstructorResolver` tùy chỉnh để chỉ cho phép class và chữ ký cần thiết. Không allowlist chỉ theo tên package hoặc chỉ theo class nếu class đó có constructor overload với hành vi khác nhau.

Trong nhiều trường hợp, cách đơn giản và an toàn hơn là tạo object ở Java rồi truyền object đã tạo vào root object hoặc variable. Điều này giữ quyền tạo object trong code ứng dụng, nơi có thể validate input và quản lý tài nguyên.

## 6. Kiểm soát bean references

Bean reference `@beanName` chỉ hoạt động khi `EvaluationContext` có `BeanResolver`. Nếu expression không cần Spring bean, đừng cấu hình resolver. Context được tạo thủ công thường không có bean resolver cho đến khi ứng dụng thêm nó.

Nếu cần một số bean, không nên expose toàn bộ ApplicationContext hoặc một resolver cho phép phân giải bean tùy ý. Hãy cung cấp một facade hẹp với các method thuần đọc cần thiết, hoặc triển khai resolver chỉ trả về một tập bean cụ thể.

`SimpleEvaluationContext` không hỗ trợ bean references. Đây là một lý do để chọn nó khi rule chỉ cần property data binding.

Không expose trực tiếp repository, HTTP client, filesystem service, process runner, message publisher hoặc bean quản trị cho expression không tin cậy. Một method public trên bean có thể thực hiện hành động ngoài hệ thống dù cú pháp expression trông đơn giản.

## 7. Kiểm soát functions và variables

Function được đăng ký trong context thường gọi một Java `Method` qua cú pháp `#functionName(...)`. MethodResolver allowlist không tự động thay thế việc kiểm tra function: function reference có cơ chế đánh giá riêng.

Chỉ đăng ký function cần thiết và ưu tiên phép tính thuần:

```java
Method normalize = TextFunctions.class.getMethod(
        "normalize", String.class);
context.registerFunction("normalize", normalize);
```

Không đăng ký function có thể chạy command, truy cập URL tùy ý, đọc/ghi file, gửi message hoặc thực hiện database update. Function trong selection/projection có thể được gọi một lần cho mỗi phần tử; expression được đánh giá lại cũng gọi function lại.

Variables cũng cần được kiểm soát. Không đưa service hoặc object có quyền rộng vào context chỉ để tiện truy cập. Ưu tiên scalar, immutable value object, collection đã được giới hạn và DTO chỉ chứa property cần dùng.

## 8. Property accessors cũng là một ranh giới bảo mật

Ngay cả khi đã chặn type reference, constructor và method invocation, expression vẫn có thể đọc property qua các `PropertyAccessor` đã đăng ký. Reflective accessor có thể truy cập nhiều getter trên object được expose.

Với rule bên ngoài, hãy giới hạn root object thành DTO/view object chỉ có dữ liệu cần thiết. Nếu cần kiểm soát chi tiết hơn, cung cấp `PropertyAccessor` tùy chỉnh chỉ cho phép một tập property cụ thể.

Tránh expose entity có getter lazy-loading hoặc getter thực hiện I/O. `forReadOnlyDataBinding()` chỉ giới hạn việc ghi qua accessor; nó không chứng minh getter là không có side effect.

Index access cũng cần được cân nhắc: map, list và custom `IndexAccessor` có thể mở ra đường truy cập thêm. Nếu dùng custom accessor, chỉ hỗ trợ target và key/index được dự định.

## 9. Ví dụ cấu hình context với quyền tối thiểu

Ví dụ sau minh họa một context không cho type reference, constructor, bean reference hoặc method invocation. Expression chỉ đọc property qua accessor đã chọn:

```java
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "accountEnabled == true and creditLimit >= #requestedAmount");
```

Đưa vào context chỉ một view object có các property cần thiết và giá trị `requestedAmount` theo cơ chế variable mà ứng dụng sử dụng. Không đưa service/repository vào root.

Nếu cần một phép tính phụ, ưu tiên tính trong Java rồi đưa kết quả vào view object. Nếu buộc phải cho phép method, expose object nhỏ chỉ có method an toàn hoặc bật method invocation với một chính sách allowlist được kiểm tra.

## 10. Expression do người dùng cung cấp và expression cố định

Phân biệt rõ hai mô hình:

- **Expression do ứng dụng quản lý:** source expression nằm trong code hoặc cấu hình nội bộ đã được review. Có thể dùng SpEL đầy đủ nếu context và quyền truy cập được thiết kế phù hợp.
- **Expression do người dùng kiểm soát:** người dùng có thể gửi hoặc sửa source expression. Hãy coi đây là code cần giới hạn, không phải dữ liệu thông thường.

Nếu người dùng chỉ cần chọn một phép toán hoặc điều kiện, cân nhắc cung cấp DSL nhỏ, danh sách operator cho phép hoặc các field cấu hình có kiểu. Đừng yêu cầu họ gửi một đoạn SpEL tùy ý khi một cấu trúc dữ liệu đơn giản có thể diễn đạt cùng nhu cầu.

Không nối dữ liệu người dùng trực tiếp vào source expression:

```java
// Tránh tạo expression bằng cách nối input vào source.
String source = "name == '" + userInput + "'";

// Dùng expression cố định và truyền dữ liệu qua context.
Expression expression = parser.parseExpression("name == #input");
StandardEvaluationContext context = new StandardEvaluationContext(view);
context.setVariable("input", userInput);
```

Truyền input qua variable ngăn dữ liệu được diễn giải như cú pháp SpEL. Tuy nhiên, nếu chính `source` là do người dùng kiểm soát, việc truyền biến không biến source đó thành an toàn; cần giới hạn expression hoặc dùng DSL.

## 11. Giới hạn tài nguyên và độ phức tạp

Giới hạn class và method không tự giải quyết mọi rủi ro tài nguyên. Expression có thể gây tốn CPU hoặc bộ nhớ thông qua collection lớn, regex phức tạp, nested property access, method được expose hoặc collection auto-growth.

Biện pháp thực tế:

- Giới hạn độ dài source expression và số lượng expression được lưu/đánh giá.
- Giới hạn kích thước collection và độ sâu của dữ liệu đầu vào.
- Tắt auto-grow null references/collections nếu use case không cần; nếu bật, đặt maximum auto-grow size phù hợp.
- Không expose method có thời gian chạy không giới hạn hoặc gọi dịch vụ bên ngoài.
- Tránh regex do người dùng kiểm soát nếu không có giới hạn độ dài và độ phức tạp phù hợp.
- Thực hiện evaluation ở tầng có thể áp dụng timeout, rate limit và kiểm soát concurrency nếu ứng dụng cần các giới hạn đó.
- Không giả định SpEL tự cung cấp một sandbox tổng quát hoặc ngân sách thời gian thực thi cho mọi expression.

Không dùng compiler mode như một ranh giới bảo mật. Việc expression được thông dịch hay biên dịch không thay thế việc giới hạn type, constructor, method, bean, function và property access.

## 12. Xử lý lỗi và quan sát

Khi một expression cố gọi type, constructor hoặc method không được phép, evaluation sẽ thất bại. Hãy xử lý lỗi ở ranh giới ứng dụng:

- Trả thông báo lỗi an toàn, không đưa stack trace hoặc tên class nội bộ ra client.
- Ghi nhận expression ID, người gọi và kết quả policy; tránh log secret hoặc toàn bộ dữ liệu đầu vào nhạy cảm.
- Phân biệt expression không hợp lệ, quyền bị từ chối và lỗi nghiệp vụ.
- Không nuốt exception rồi trả `true` hoặc giá trị mặc định có thể làm rule được thông qua ngoài ý muốn.
- Kiểm thử cả trường hợp hợp lệ và trường hợp cố gọi chức năng ngoài allowlist.

## 13. Checklist trước khi đánh giá expression

1. Ai kiểm soát source expression: ứng dụng hay người dùng?
2. Expression có thật sự cần `T(...)`, `new`, method invocation hoặc `@bean` không?
3. Có thể dùng `SimpleEvaluationContext` read-only thay thế không?
4. Root object có phải DTO/view object nhỏ, chỉ chứa dữ liệu cần thiết không?
5. Getter, accessor và method có truy cập database, file, network hoặc trạng thái dùng chung không?
6. TypeLocator có allowlist class chính xác không?
7. ConstructorResolver và MethodResolver có giới hạn chữ ký được phép không?
8. BeanResolver và functions có expose đúng những API tối thiểu không?
9. Variables có chứa service hoặc object có quyền rộng không?
10. Độ dài expression, collection size, regex và chi phí evaluation có được giới hạn không?
11. Lỗi có được trả về an toàn và ghi log không lộ dữ liệu nhạy cảm không?

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Expression gọi được class ngoài dự kiến | StandardTypeLocator đang tìm class rộng hơn nhu cầu. | Thay bằng TypeLocator allowlist chỉ trả về class được phép. |
| `new SomeType(...)` vẫn chạy | Reflective ConstructorResolver còn được cấu hình. | Bỏ constructor resolver hoặc dùng resolver allowlist. |
| Method nguy hiểm vẫn gọi được | Reflective method resolver cho phép method trên object đang expose. | Bỏ method resolver nếu không cần; nếu cần, giới hạn bằng MethodFilter hoặc resolver riêng cho mọi target class liên quan. |
| Chặn method nhưng function vẫn chạy | Function reference không bị giới hạn chỉ bằng MethodResolver. | Kiểm tra từng function đã đăng ký; chỉ đăng ký helper thuần và allowlist. |
| `@beanName` phân giải được dù không mong muốn | Context có BeanResolver. | Không cấu hình resolver hoặc thay bằng resolver chỉ cho phép bean cần thiết. |
| Read-only expression vẫn truy cập database | Getter hoặc PropertyAccessor thực hiện lazy loading/I/O. | Dùng DTO đã chuẩn bị dữ liệu và accessor đơn giản. |
| Expression làm tăng bộ nhớ | Collection auto-grow hoặc input collection/index quá lớn. | Tắt auto-grow hoặc đặt giới hạn; xác thực kích thước đầu vào. |
| Dữ liệu người dùng làm thay đổi ý nghĩa expression | Input bị nối trực tiếp vào source expression. | Dùng expression cố định và truyền input qua biến có kiểu. |
| Cấu hình compiler bị xem là biện pháp sandbox | Compiler mode không giới hạn quyền truy cập của expression. | Thiết kế allowlist context và giới hạn resource độc lập với compiler mode. |

## Ghi nhớ

- `T(...)`, `new`, method invocation, `@beanName`, function và property access đều là những bề mặt cần kiểm soát.
- Dùng `SimpleEvaluationContext.forReadOnlyDataBinding()` khi chỉ cần đọc property; nó không hỗ trợ type references, constructors hoặc bean references.
- Method invocation trong SimpleEvaluationContext tắt mặc định; `withInstanceMethods()` bật rộng hơn và chỉ nên dùng với object có API hẹp.
- Với StandardEvaluationContext, TypeLocator kiểm soát class reference; ConstructorResolver kiểm soát `new`; MethodResolver/MethodFilter kiểm soát method invocation; BeanResolver kiểm soát `@bean`.
- Function được đăng ký cần allowlist riêng; không giả định MethodResolver chặn function.
- Chỉ expose DTO/view object, property accessor và variables cần thiết; getter cũng có thể có side effect.
- Không đánh giá source SpEL tùy ý từ người dùng với toàn bộ ApplicationContext hoặc domain services.
- Truyền dữ liệu qua variables thay vì nối input vào source; nhưng variable không làm source expression không tin cậy trở nên an toàn.
- Giới hạn expression size, collection size, auto-growth, regex và chi phí method; không giả định SpEL có sandbox hoặc timeout tổng quát.
- Compiler mode không phải ranh giới bảo mật.

## Tài liệu tham khảo

- [Spring Framework Reference — Evaluation and SimpleEvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Type References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/types.html)
- [Spring Framework Reference — Constructors](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html)
- [Spring Framework Reference — Methods](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework Reference — Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [Spring Framework API — TypeLocator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/TypeLocator.html)
- [Spring Framework API — ConstructorResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ConstructorResolver.html)
- [Spring Framework API — MethodFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/MethodFilter.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)