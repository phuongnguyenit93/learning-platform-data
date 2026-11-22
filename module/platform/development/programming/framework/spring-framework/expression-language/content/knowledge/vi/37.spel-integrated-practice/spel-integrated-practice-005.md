# Dùng variable và function trong một EvaluationContext tối thiểu

## Mục tiêu

`EvaluationContext` cung cấp dữ liệu và quy tắc mà Spring Expression Language (SpEL) dùng khi đánh giá expression. Một context có thể chứa root object, variables, property accessors, method resolvers, type conversion và những cơ chế phân giải khác.

Với một rule nhỏ, thường chỉ cần root DTO, một vài variables và một function thuần. `SimpleEvaluationContext` là lựa chọn builder-based để bật một tập tính năng giới hạn hơn `StandardEvaluationContext`. Nó hỗ trợ variables và functions, đồng thời có thể cấu hình property access ở chế độ read-only.

Bài này ghép ba phần thành một ví dụ hoàn chỉnh: truyền dữ liệu vào context bằng `setVariable`, đăng ký function bằng một `Method`, rồi đánh giá expression trên root object. Mục tiêu là giữ context nhỏ, rõ ràng và chỉ cung cấp những quyền cần cho rule.

## 1. Ba thành phần trong một lần đánh giá

Một expression thường lấy dữ liệu từ ba nơi:

| Thành phần | Cách tham chiếu trong SpEL | Nguồn giá trị |
| --- | --- | --- |
| Root object | Property không prefix, `#root` hoặc `#this` | Object truyền vào `getValue(...)` hoặc root đã đặt trong context. |
| Variable | `#variableName` | Giá trị ứng dụng đăng ký bằng `context.setVariable(...)`. |
| Function | `#functionName(arguments)` | `Method` hoặc `MethodHandle` đăng ký trong context. |

Ví dụ:

~~~spel
active == true and #isAtLeast(age, #minimumAge)
~~~

Trong expression này, `active` và `age` được đọc từ root object; `#minimumAge` là variable; `#isAtLeast(...)` gọi function đã đăng ký. Dấu `#` xuất hiện trước variable và function, không xuất hiện trong tên truyền cho `setVariable`.

## 2. Tạo một root DTO đơn giản

Root object nên chứa đúng dữ liệu mà rule cần. Tránh truyền toàn bộ entity hoặc service object nếu chỉ cần vài field.

~~~java
public final class CustomerView {
    private final String name;
    private final int age;
    private final boolean active;

    public CustomerView(String name, int age, boolean active) {
        this.name = name;
        this.age = age;
        this.active = active;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Property accessor của context đọc các getter tương ứng. Giữ getter đơn giản và không thực hiện database query, network call, file access hoặc thay đổi trạng thái. Read-only binding ngăn expression ghi property qua accessor, nhưng không tự chứng minh getter là thuần đọc.

## 3. Tạo function Java thuần

Function được đăng ký bằng một `Method` hoặc `MethodHandle`. Khi đăng ký một `Method`, method phải là static. Hãy dùng method public, chữ ký rõ ràng và kết quả có thể dự đoán.

~~~java
public final class RuleFunctions {

    private RuleFunctions() {
    }

    public static boolean isAtLeast(Integer actual, Integer minimum) {
        return actual != null
                && minimum != null
                && actual >= minimum;
    }

    public static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

`isAtLeast` xác định rõ cách xử lý null: nếu một trong hai đối số null thì trả về false. `normalize` trả về null nếu input null. Việc quy định null behavior trong function giúp expression ngắn hơn và dễ kiểm thử.

Không đăng ký function thực hiện database update, gửi message, gọi URL, đọc/ghi file hoặc thay đổi trạng thái dùng chung. Function có thể được gọi nhiều lần trong một lần evaluation, đặc biệt khi đặt bên trong selection hoặc projection.

## 4. Tạo SimpleEvaluationContext và đăng ký variables

Với rule chỉ cần đọc property, dùng `forReadOnlyDataBinding()`. `SimpleEvaluationContext` hỗ trợ `setVariable(...)` để đăng ký variable và function:

~~~java
ExpressionParser parser = new SpelExpressionParser();

EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

context.setVariable("minimumAge", 18);
context.setVariable("countryCode", "VN");
~~~

Expression tham chiếu các giá trị đó bằng `#minimumAge` và `#countryCode`:

~~~spel
age >= #minimumAge and countryCode == #countryCode
~~~

Trong ví dụ trên, nếu root object cũng có property `countryCode`, tên không prefix là property của root; `#countryCode` là variable trong context. Dùng tên variable khác với property khi có thể để tránh nhầm lẫn.

Variable có thể là scalar, enum, collection hoặc một DTO/value object nhỏ. Chỉ đưa dữ liệu expression thực sự cần vào context; tránh đăng ký cả request, session, repository hoặc service chỉ để tiện truy cập.

## 5. Đăng ký function trong SimpleEvaluationContext

Trong `SimpleEvaluationContext`, đăng ký function như một variable có giá trị là `Method`:

~~~java
Method isAtLeast = RuleFunctions.class.getMethod(
        "isAtLeast", Integer.class, Integer.class);

context.setVariable("isAtLeast", isAtLeast);
~~~

Sau đó gọi function trong expression:

~~~spel
#isAtLeast(age, #minimumAge)
~~~

Function reference là một tính năng riêng của SpEL. Không cần bật general instance method invocation bằng `withInstanceMethods()` chỉ để gọi function đã đăng ký. `withInstanceMethods()` mở thêm khả năng gọi instance method trên object trong expression; chỉ bật khi use case thực sự cần.

Function và variable dùng chung một namespace. Không đăng ký một variable và một function trùng tên; giá trị đăng ký sau có thể thay thế giá trị trước trong context.

## 6. Ví dụ hoàn chỉnh: root, variable và function

Ví dụ sau kết hợp cả ba thành phần trong một expression:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Method isAtLeast = RuleFunctions.class.getMethod(
        "isAtLeast", Integer.class, Integer.class);

EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

context.setVariable("minimumAge", 18);
context.setVariable("isAtLeast", isAtLeast);

CustomerView customer = new CustomerView("Lan", 28, true);

Expression rule = parser.parseExpression(
        "active == true and #isAtLeast(age, #minimumAge)");

Boolean eligible = rule.getValue(
        context, customer, Boolean.class);
~~~

Kết quả là `true` vì customer đang active và age đạt ngưỡng. Trong lần gọi `getValue` này:

- `customer` là root object.
- `active` và `age` là property của root.
- `#minimumAge` là variable có giá trị 18.
- `#isAtLeast(...)` gọi static method đã đăng ký.

Expression chỉ đọc DTO, dùng một variable scalar và gọi một function cụ thể. Không cần type reference, constructor invocation, bean reference hoặc một service object trong context.

## 7. Dùng function và variable trong collection operations

Variables và functions cũng có thể dùng trong selection và projection. `#this` là phần tử hiện tại của collection; variables/functions vẫn được tra trong cùng evaluation context:

~~~spel
#customers.?[active == true and #isAtLeast(age, #minimumAge)]
~~~

Ví dụ Java:

~~~java
context.setVariable("minimumAge", 18);
context.setVariable("isAtLeast", isAtLeast);
context.setVariable("customers", customers);

Expression selection = parser.parseExpression(
        "#customers.?[active == true and #isAtLeast(age, #minimumAge)]");

List<?> eligibleCustomers = selection.getValue(context, List.class);
~~~

Function được gọi cho từng customer mà selection kiểm tra. Nếu collection có hàng nghìn phần tử, function có thể được gọi hàng nghìn lần. Giữ function nhỏ, nhanh và thuần; nếu phép tính tốn kém, tính trước trên Java rồi đưa kết quả vào view object.

Projection cũng có thể gọi function:

~~~spel
#customers.![#normalize(name)]
~~~

Projection tạo một kết quả cho mỗi phần tử. Nếu cần vừa lọc vừa biến đổi, nối selection và projection, đồng thời lưu ý chi phí duyệt và collection trung gian.

## 8. Dùng MethodHandle thay cho Method

EvaluationContext cho phép đăng ký function bằng `java.lang.invoke.MethodHandle` ngoài `java.lang.reflect.Method`. MethodHandle hữu ích khi cần một function đã được bind với receiver hoặc khi ứng dụng muốn kiểm soát cách tạo handle.

~~~java
MethodHandle handle = lookup.findStatic(
        RuleFunctions.class,
        "normalize",
        MethodType.methodType(String.class, String.class));

context.setVariable("normalize", handle);
~~~

Expression:

~~~spel
#normalize(name)
~~~

Ví dụ này minh họa static method handle. Nếu dùng handle cho instance method, cần bind receiver trước và chỉ bind một object có API hẹp, an toàn cho expression. Không expose handle có thể gọi service hoặc thực hiện thao tác ngoài ý muốn.

Với code đơn giản, đăng ký `Method` thường dễ đọc hơn. Chọn `MethodHandle` khi có lý do cụ thể về binding hoặc API; không cần dùng cả hai cách cho cùng function.

## 9. Khi nào dùng StandardEvaluationContext?

`SimpleEvaluationContext` hỗ trợ variables và functions, nhưng loại trừ một số tính năng SpEL đầy đủ như type reference `T(...)`, constructor `new` và bean reference `@bean`. Nó cũng yêu cầu chọn rõ property/method access.

Nếu use case cần các tính năng đó, có thể dùng `StandardEvaluationContext` và cấu hình tối thiểu các quyền cần thiết:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("minimumAge", 18);
context.registerFunction("isAtLeast", isAtLeast);
~~~

`StandardEvaluationContext` có reflective property/method access và constructor/type resolution mặc định. Vì vậy, chỉ dùng nó khi expression cần khả năng rộng hơn; nếu expression không cần gọi method tùy ý, hãy giới hạn resolver/accessor hoặc tiếp tục dùng `SimpleEvaluationContext`.

Không xem việc dùng `SimpleEvaluationContext` là sandbox bảo mật tổng quát. Spring cảnh báo rằng giới hạn tính năng được cung cấp theo hướng best-effort và không bảo đảm expression lấy từ nguồn không tin cậy là an toàn. Getter, property accessor và function đã đăng ký vẫn có thể thực thi code.

## 10. Namespace và quy tắc đặt tên

Variable và function share chung namespace trong một context. Vì vậy:

- Đặt tên variable và function khác nhau.
- Dùng tên mô tả vai trò, ví dụ `minimumAge`, `allowedCountries`, `normalizeCode`.
- Không dùng tên `this` hoặc `root` cho dữ liệu ứng dụng; đó là các biến đặc biệt của SpEL.
- Đăng ký tên không có dấu `#`; khi viết expression mới thêm `#`.
- Đăng ký tất cả variables/functions trước khi đánh giá expression.

Ví dụ:

~~~java
context.setVariable("minimumAge", 18);
context.setVariable("normalizeCode", normalizeMethod);
~~~

~~~spel
#normalizeCode(customerCode) == 'vn'
~~~

Không thay đổi ý nghĩa một tên variable thành function giữa các lần đánh giá. Việc dùng chung namespace khiến cấu hình như vậy khó đọc và dễ tạo lỗi runtime.

## 11. Quản lý vòng đời và tái sử dụng context

Parser và expression đã parse có thể được tái sử dụng. Variables và root object lại thường phụ thuộc request hoặc lần đánh giá:

~~~java
Expression rule = parser.parseExpression(
        "active and #isAtLeast(age, #minimumAge)");

EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();
context.setVariable("isAtLeast", isAtLeast);

for (CustomerView customer : customers) {
    context.setVariable("minimumAge", 18);
    Boolean eligible = rule.getValue(
            context, customer, Boolean.class);
}
~~~

Đoạn code minh họa cách tái sử dụng expression. Trong ứng dụng đa luồng, tránh chia sẻ một context mutable giữa các request nếu mỗi request có thể thay đổi variables hoặc dữ liệu context. Tạo context theo request/lần đánh giá hoặc dùng một factory tạo context đã cấu hình sẵn.

Không nhầm việc tái sử dụng expression với cache kết quả: mỗi lần `getValue` vẫn đánh giá expression theo root và variables hiện tại. Function cũng được gọi lại khi evaluation đi tới lời gọi function.

## 12. Xử lý null, kiểu dữ liệu và lỗi

Đăng ký variables với kiểu dữ liệu rõ ràng để expression dễ dự đoán. Ví dụ dùng `Integer` cho ngưỡng số, `Set<String>` cho danh sách mã được phép và enum cho trạng thái cố định.

~~~java
context.setVariable("minimumAge", Integer.valueOf(18));
context.setVariable("allowedRegions", Set.of("VN", "SG"));
~~~

~~~spel
#allowedRegions.contains(region)
~~~

Xác định null behavior cho function và variable:

- Nếu null là input không hợp lệ, validate trước khi gọi `getValue`.
- Nếu null là một trạng thái hợp lệ, viết function trả kết quả rõ ràng cho null.
- Không dựa vào conversion ngầm khi overload hoặc kiểu đối số mơ hồ.
- Nếu expression cần Boolean, yêu cầu kết quả Boolean rõ ràng và xử lý null như một trạng thái riêng.

Parse error và evaluation error là hai loại lỗi khác nhau. Parse source trước khi lưu rule; khi đánh giá, xử lý `EvaluationException` tại ranh giới ứng dụng. Không trả exception message hoặc raw expression cho người dùng cuối.

## 13. Giữ function thuần và context nhỏ

Function được đăng ký là một đường thực thi Java code. Dù context là SimpleEvaluationContext, function vẫn có thể làm bất cứ việc gì mà method đó được viết để làm.

Thiết kế nên theo các nguyên tắc:

- Chỉ đăng ký function expression thực sự cần.
- Ưu tiên static method thuần, deterministic và không có side effect.
- Không gọi database, HTTP, filesystem, message broker hoặc process từ function.
- Không truyền service, repository, application context hoặc object có quyền rộng vào variables.
- Không cho function giữ hoặc sửa root object/collection đầu vào.
- Giới hạn kích thước và miền giá trị của variables.
- Dùng DTO/view object chỉ có property cần thiết.

Đối với dữ liệu bên ngoài như kết quả truy vấn, tải dữ liệu ở service layer trước rồi truyền collection hoặc map đã được giới hạn vào context. Đừng dùng function để tạo I/O ẩn trong một rule.

## 14. Kiểm thử một EvaluationContext tối thiểu

Test nên kiểm tra cả kết quả hợp lệ và các quyền không được hỗ trợ:

~~~java
@Test
void evaluatesWithRootVariableAndFunction() throws Exception {
    ExpressionParser parser = new SpelExpressionParser();
    EvaluationContext context = SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();

    Method isAtLeast = RuleFunctions.class.getMethod(
            "isAtLeast", Integer.class, Integer.class);
    context.setVariable("minimumAge", 18);
    context.setVariable("isAtLeast", isAtLeast);

    CustomerView customer = new CustomerView("Lan", 28, true);
    Boolean result = parser.parseExpression(
            "active and #isAtLeast(age, #minimumAge)")
            .getValue(context, customer, Boolean.class);

    assertThat(result).isTrue();
}
~~~

Thêm test cho các trường hợp:

- Customer inactive trả về false.
- Age thấp hơn ngưỡng trả về false.
- Variable chưa được đăng ký tạo evaluation error.
- Function chưa được đăng ký tạo evaluation error.
- Function nhận null xử lý theo hợp đồng đã định nghĩa.
- Expression dùng `T(...)`, `new` hoặc `@bean` bị từ chối trong SimpleEvaluationContext.
- Function không thay đổi input hoặc trạng thái dùng chung.
- Hai request dùng variables khác nhau không đọc nhầm giá trị của nhau.

Trong test bảo mật, kiểm tra side effect bằng counter hoặc probe; chỉ kiểm tra exception chưa chứng minh code nguy hiểm không được chạy.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| `#minimumAge` không có giá trị | Variable chưa được đăng ký hoặc tên không khớp. | Gọi `setVariable("minimumAge", value)` trước evaluation và dùng đúng `#minimumAge`. |
| `#isAtLeast(...)` không tìm thấy function | Function chưa được đăng ký, method signature sai hoặc tên bị variable khác ghi đè. | Lấy đúng public Method, đăng ký bằng `setVariable` và tránh trùng namespace. |
| Function không chạy trong SimpleEvaluationContext | Đang nhầm function reference với instance method invocation. | Đăng ký `Method`/`MethodHandle` làm variable; không cần bật general instance methods cho function reference. |
| `name.toUpperCase()` không hoạt động | General instance method invocation bị tắt mặc định. | Chỉ bật `withInstanceMethods()` nếu cần, và giới hạn object được expose. |
| `T(...)`, `new` hoặc `@bean` không hoạt động | Đây là các tính năng không được SimpleEvaluationContext hỗ trợ. | Dùng Java để chuẩn bị giá trị hoặc chuyển sang StandardEvaluationContext với quyền được giới hạn. |
| Variable bị function thay thế hoặc ngược lại | Variables và functions dùng chung namespace. | Dùng tên riêng và đăng ký context theo một nơi duy nhất. |
| Function được gọi quá nhiều lần | Function nằm trong selection/projection hoặc expression được đánh giá lại. | Giữ function nhanh, thuần; tính trước dữ liệu đắt tiền. |
| Request này đọc variable của request khác | Chia sẻ context mutable giữa các lần đánh giá đồng thời. | Tạo context riêng cho request/lần đánh giá. |
| Read-only expression vẫn có I/O | Getter hoặc function truy cập tài nguyên. | Dùng DTO getter thuần và chỉ đăng ký function không I/O. |

## Ghi nhớ

- `EvaluationContext` cung cấp root object, variables, functions và các chiến lược truy cập cho SpEL.
- Dùng property không prefix hoặc `#root`/`#this` để đọc root; dùng `#name` cho variable; dùng `#function(args)` cho function.
- `SimpleEvaluationContext.forReadOnlyDataBinding()` phù hợp với rule chỉ đọc property.
- `SimpleEvaluationContext.setVariable(...)` đăng ký cả variable và function; function có thể là `Method` hoặc `MethodHandle`.
- Khi đăng ký `Method`, dùng public static method có chữ ký rõ ràng; `StandardEvaluationContext.registerFunction(...)` là API tiện dụng khi dùng Standard context.
- Function và variable share namespace; không dùng trùng tên.
- Function reference không đồng nghĩa với general instance method invocation; không cần bật `withInstanceMethods()` chỉ để gọi function đã đăng ký.
- SimpleEvaluationContext loại trừ `T(...)`, `new` và `@bean`, nhưng không phải sandbox tổng quát cho expression không tin cậy.
- Tái sử dụng parser/expression không cache kết quả; mỗi lần `getValue` vẫn dùng root, variables và function của lần đánh giá đó.
- Dùng context riêng khi variables thay đổi theo request; giữ function thuần, nhanh và không truy cập tài nguyên.

## Tài liệu tham khảo

- [Spring Framework Reference — Variables](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework Reference — Functions](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/functions.html)
- [Spring Framework Reference — EvaluationContext and SimpleEvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework API — EvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [Spring Framework API — SimpleEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)