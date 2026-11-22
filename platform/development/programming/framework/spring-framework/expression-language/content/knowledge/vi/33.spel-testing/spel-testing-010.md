# Kiểm thử giới hạn quyền và expression không tin cậy trong SpEL

## Mục tiêu

Khi ứng dụng đánh giá Spring Expression Language (SpEL), `EvaluationContext` quyết định những khả năng mà expression có thể sử dụng: đọc và ghi property, gọi method, tham chiếu class bằng `T(...)`, tạo object bằng `new`, truy cập bean qua `@beanName` hoặc gọi function đã đăng ký. Với expression do người dùng hoặc nguồn cấu hình bên ngoài kiểm soát, cần kiểm thử rằng chỉ những khả năng được phép mới hoạt động.

Kiểm thử bảo mật không chỉ xác nhận một expression hợp lệ trả về đúng kết quả. Bộ test cần có cả trường hợp dương tính và âm tính: property được phép vẫn đọc được; type, constructor, method, bean hoặc function ngoài allowlist bị từ chối; dữ liệu đầu vào được truyền như dữ liệu; lỗi không làm lộ source, secret hoặc chi tiết nội bộ.

## 1. Xác định chính sách trước khi viết test

Trước tiên, ghi rõ expression được phép làm gì. Một policy đơn giản cho rule chỉ đọc có thể gồm:

- Đọc một số property đã biết trên DTO/view object.
- Dùng literal, phép so sánh, toán tử logic và phép tính cần thiết.
- Dùng các biến có kiểu do ứng dụng cung cấp.
- Không ghi property.
- Không gọi method tùy ý.
- Không dùng type reference `T(...)`, constructor `new` hoặc bean reference `@bean`.
- Không gọi function nếu rule không cần function.
- Không truy cập repository, HTTP client, filesystem, message broker hoặc service quản trị.

Nếu use case cần một method hoặc function cụ thể, ghi rõ tên, chữ ký, class đích và hành vi được phép. Policy cụ thể giúp test có thể chứng minh từng quyền được bật hoặc bị chặn.

## 2. Dùng SimpleEvaluationContext làm baseline hạn chế

`SimpleEvaluationContext` phù hợp khi rule chỉ cần data binding. Nó không hỗ trợ type references, constructor invocation hoặc bean references. Method invocation bị tắt mặc định; builder có thể bật instance methods khi cần.

Ví dụ tạo context chỉ đọc:

~~~java
EvaluationContext context = SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .build();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression(
        "active == true and age >= 18");

Boolean allowed = expression.getValue(
        context, customerView, Boolean.class);
~~~

Với cấu hình này, test nên xác nhận property cần thiết hoạt động và các tính năng bị loại trừ đều thất bại. Nếu cần ghi property, hãy có test riêng cho `forReadWriteDataBinding()` và chỉ cho phép đúng các field cần thay đổi.

Read-only chỉ kiểm soát việc ghi qua property accessor. Nó không bảo đảm getter là thuần đọc. Hãy dùng DTO/view object có getter đơn giản, không truy cập tài nguyên và không thay đổi trạng thái.

## 3. Tổ chức test với JUnit

Một bộ test cơ bản có thể dùng JUnit 5 và AssertJ. Dùng object test nhỏ để xác định chính xác property nào được expose:

~~~java
final class CustomerView {
    private final String name;
    private final int age;
    private final boolean active;

    CustomerView(String name, int age, boolean active) {
        this.name = name;
        this.age = age;
        this.active = active;
    }

    public String getName() { return name; }
    public int getAge() { return age; }
    public boolean isActive() { return active; }
}
~~~

Ví dụ test property được phép:

~~~java
class SpelSecurityTests {

    private final ExpressionParser parser = new SpelExpressionParser();
    private final EvaluationContext context = SimpleEvaluationContext
            .forReadOnlyDataBinding()
            .build();
    private final CustomerView customer =
            new CustomerView("Lan", 28, true);

    @Test
    void allowsApprovedPropertyReads() {
        Boolean result = parser.parseExpression(
                "active == true and age >= 18")
                .getValue(context, customer, Boolean.class);

        assertThat(result).isTrue();
    }
}
~~~

Test này là positive test: nó chứng minh context vẫn làm được công việc nghiệp vụ được cho phép. Một suite chỉ có negative tests có thể vô tình chặn cả chức năng hợp lệ.

## 4. Kiểm thử type reference bị chặn

Type reference có cú pháp `T(package.ClassName)`. Nếu rule không cần truy cập class, `SimpleEvaluationContext` không cung cấp type reference. Hãy kiểm tra một lời gọi đại diện đến class có quyền mạnh:

~~~java
@Test
void rejectsTypeReferences() {
    assertThatThrownBy(() -> parser
            .parseExpression("T(java.lang.Runtime).getRuntime()")
            .getValue(context, Object.class))
            .isInstanceOf(EvaluationException.class);
}
~~~

Không chỉ test một class. Hãy chọn các class đại diện cho policy của ứng dụng, ví dụ class hệ thống, class tiện ích và class nội bộ không được expose. Test nên kiểm tra kết quả là bị từ chối; không phụ thuộc vào toàn bộ nội dung exception message vì message có thể thay đổi theo phiên bản Spring.

Nếu use case cần một vài type trong `StandardEvaluationContext`, thay `StandardTypeLocator` bằng implementation allowlist. Test cả type được phép và type bị từ chối, đồng thời kiểm tra tên đầy đủ của class để tránh allowlist theo package quá rộng.

## 5. Kiểm thử constructor invocation bị chặn

Constructor invocation dùng `new`. Nếu không có nhu cầu tạo object trong expression, `SimpleEvaluationContext` không hỗ trợ khả năng này:

~~~java
@Test
void rejectsConstructorInvocation() {
    assertThatThrownBy(() -> parser
            .parseExpression("new java.lang.String('unexpected')")
            .getValue(context, Object.class))
            .isInstanceOf(EvaluationException.class);
}
~~~

Nếu ứng dụng dùng `StandardEvaluationContext`, hãy kiểm tra cấu hình `ConstructorResolver`. Có thể bỏ reflective constructor resolver khi không cần constructor invocation, hoặc cung cấp resolver allowlist chỉ cho những constructor cụ thể.

Test nên bao gồm constructor được phép (nếu có) và constructor không được phép. Không chỉ kiểm tra một constructor bị chặn rồi suy ra mọi class khác cũng bị chặn.

## 6. Kiểm thử method invocation bị chặn

Method invocation có thể thực thi Java code trên root object hoặc object lồng nhau. Với `SimpleEvaluationContext`, method invocation tắt mặc định:

~~~java
@Test
void rejectsInstanceMethodInvocationByDefault() {
    assertThatThrownBy(() -> parser
            .parseExpression("name.toUpperCase()")
            .getValue(context, customer, String.class))
            .isInstanceOf(EvaluationException.class);
}
~~~

Test này kiểm tra một method thông thường trên giá trị property. Hãy bổ sung test với method nhạy cảm giả lập trên một fixture, ví dụ `resetAccount()`, `deleteRecord()` hoặc `sendMessage()`, và xác nhận method không được gọi.

Ví dụ dùng counter để xác nhận method không chạy:

~~~java
final class SideEffectProbe {
    private int calls;

    public void dangerousAction() {
        calls++;
    }

    public int getCalls() {
        return calls;
    }
}

@Test
void blockedMethodDoesNotRun() {
    SideEffectProbe probe = new SideEffectProbe();

    assertThatThrownBy(() -> parser
            .parseExpression("dangerousAction()")
            .getValue(context, probe))
            .isInstanceOf(EvaluationException.class);

    assertThat(probe.getCalls()).isZero();
}
~~~

Assertion `calls == 0` quan trọng hơn việc chỉ kiểm tra có exception: nó chứng minh side effect không xảy ra trước khi evaluation thất bại.

Nếu bật `withInstanceMethods()`, đừng coi đó là allowlist theo tên method. Hãy kiểm tra object được expose và dùng resolver/filter phù hợp khi cần giới hạn method cụ thể.

## 7. Kiểm thử bean reference bị chặn

Bean reference có cú pháp `@beanName` và cần `BeanResolver`. `SimpleEvaluationContext` không hỗ trợ bean references. Với context thủ công, đừng cấu hình resolver nếu expression không cần Spring bean.

~~~java
@Test
void rejectsBeanReferences() {
    assertThatThrownBy(() -> parser
            .parseExpression("@adminService.resetAll()")
            .getValue(context, Object.class))
            .isInstanceOf(EvaluationException.class);
}
~~~

Trong test, không cần khởi tạo một service thật có quyền xóa dữ liệu. Nếu cần xác minh hành vi resolver, dùng bean giả với counter và kiểm tra counter không tăng. Test phải chứng minh resolver không thể phân giải bean hoặc bean ngoài allowlist không thể được lấy.

Nếu ứng dụng cần một số bean trong expression, cung cấp facade nhỏ hoặc BeanResolver allowlist. Test bean hợp lệ, bean không hợp lệ và bean alias nếu alias là một phần của policy.

## 8. Kiểm thử function đã đăng ký và function không được đăng ký

Function được gọi bằng `#functionName(...)` và được đăng ký trong context. MethodResolver không tự động kiểm soát mọi function; cần kiểm tra riêng các function được thêm vào context.

Test function chưa đăng ký:

~~~java
@Test
void rejectsUnregisteredFunction() {
    assertThatThrownBy(() -> parser
            .parseExpression("#dangerousAction()")
            .getValue(context, Object.class))
            .isInstanceOf(EvaluationException.class);
}
~~~

Nếu policy cho phép function thuần, đăng ký đúng method và test kết quả:

~~~java
public final class RuleFunctions {
    private RuleFunctions() { }

    public static String normalize(String value) {
        return value == null ? null : value.trim().toLowerCase(Locale.ROOT);
    }
}

Method normalize = RuleFunctions.class.getMethod(
        "normalize", String.class);
standardContext.registerFunction("normalize", normalize);

Expression expression = parser.parseExpression("#normalize('  LAN  ')");
assertThat(expression.getValue(standardContext, String.class))
        .isEqualTo("lan");
~~~

Không đăng ký function có thể gọi command, đọc/ghi file, truy cập URL tùy ý, cập nhật database hoặc gửi message. Thêm test xác nhận function thuần không thay đổi object đầu vào hoặc trạng thái dùng chung.

## 9. Kiểm thử property access và side effect của getter

Chặn method invocation không đồng nghĩa chặn getter. Khi SpEL đọc `customer.name`, property accessor có thể gọi `getName()`. Getter có thể chứa logic ngoài dự kiến như lazy loading, truy cập database hoặc thay đổi trạng thái.

Để kiểm thử:

- Dùng fixture có getter tăng counter hoặc ghi nhận lần gọi.
- Đánh giá property trong context dự định sử dụng.
- Xác nhận chỉ getter được phép được gọi.
- Không đưa entity ORM có quan hệ lazy hoặc service-backed property vào root object của expression không tin cậy.
- Nếu cần allowlist property chính xác, dùng DTO/view object hoặc custom `PropertyAccessor` có danh sách property cho phép.

Với custom accessor, test cả target class đúng, target class sai, property được phép, property bị chặn và thao tác ghi. Không giả định read-only builder sẽ biến mọi accessor tùy chỉnh thành read-only; chính implementation accessor cần tuân thủ policy.

## 10. Kiểm thử input được truyền như dữ liệu, không phải source

Không nối chuỗi người dùng trực tiếp vào source expression. Dùng expression cố định và truyền giá trị qua variable:

~~~java
Expression expression = parser.parseExpression("name == #suppliedName");
StandardEvaluationContext context = new StandardEvaluationContext(customer);
context.setVariable("suppliedName", suppliedInput);

Boolean matches = expression.getValue(context, Boolean.class);
~~~

Test nên dùng một chuỗi giống cú pháp SpEL nhưng coi nó là dữ liệu:

~~~java
String suppliedInput = "T(java.lang.Runtime).getRuntime()";
~~~

Kết quả so sánh chỉ là true/false theo giá trị chuỗi. Nội dung đó không được parse lần thứ hai và không được thực thi như type reference.

Đây là test quan trọng để phát hiện expression injection. Tuy nhiên, truyền input qua variable không làm source expression do người dùng kiểm soát trở nên an toàn. Nếu user có thể sửa source, phải giới hạn context và cú pháp được hỗ trợ hoặc thay SpEL tùy ý bằng DSL/schema có kiểu.

## 11. Kiểm thử expression không hợp lệ và quyền bị từ chối

Phân biệt ba trường hợp:

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| Expression hợp lệ và dùng tính năng được phép | Đánh giá thành công với kết quả mong đợi. |
| Expression sai cú pháp | Parse thất bại với `ParseException`. |
| Expression có cú pháp hợp lệ nhưng dùng quyền bị chặn | Evaluation thất bại với `EvaluationException` hoặc subtype tương ứng. |

Ví dụ parse error:

~~~java
assertThatThrownBy(() -> parser.parseExpression("age > > 18"))
        .isInstanceOf(ParseException.class);
~~~

Ví dụ denied capability cần được kiểm tra ở giai đoạn `getValue`, vì nhiều expression chỉ được phân giải khi evaluation diễn ra.

Không dựa vào chính xác message text như “method not found” hoặc “type not allowed” trong test dài hạn. Ưu tiên kiểm tra exception family, mã lỗi ứng dụng và việc side effect không xảy ra.

## 12. Kiểm thử giới hạn khi dùng StandardEvaluationContext

Nếu use case cần `StandardEvaluationContext`, hãy cấu hình từng extension point theo policy:

| Extension point | Quyền cần kiểm soát | Test nên có |
| --- | --- | --- |
| `TypeLocator` | Class được tham chiếu bằng `T(...)`. | Type allowlist được resolve; type ngoài allowlist bị từ chối. |
| `ConstructorResolver` | Class/constructor có thể gọi bằng `new`. | Constructor được phép chạy; constructor ngoài allowlist không chạy. |
| `MethodResolver` | Instance/static method có thể gọi. | Method và chữ ký được phép; method nguy hiểm không được resolve. |
| `MethodFilter` | Các method reflective trên một type cụ thể. | Method nằm trong filter được giữ; method khác bị loại. |
| `BeanResolver` | Bean được lấy bằng `@beanName`. | Bean allowlist được resolve; bean ngoài allowlist bị từ chối. |
| Registered functions | Java method được gọi bằng `#function(...)`. | Function cho phép hoạt động; function không đăng ký không hoạt động. |
| `PropertyAccessor` | Property được đọc/ghi. | Property allowlist và read/write policy được thực thi. |

Ví dụ chặn toàn bộ method và constructor invocation khi không cần:

~~~java
StandardEvaluationContext context = new StandardEvaluationContext(customerView);
context.setMethodResolvers(Collections.emptyList());
context.setConstructorResolvers(Collections.emptyList());
~~~

Để giới hạn type, thay `StandardTypeLocator` bằng một `TypeLocator` allowlist. Không cấu hình `BeanResolver` nếu không cần bean reference. Kiểm tra cả variables và root object vì resolver restriction không làm object được expose trở nên vô hại.

`MethodFilter` chỉ áp dụng cho reflective method resolver trên type đã đăng ký. Nếu thay resolver hoặc expose class khác, cần test chính sách cho đường truy cập đó nữa.

## 13. Kiểm thử dữ liệu lớn và giới hạn tài nguyên

Expression không tin cậy có thể tiêu thụ tài nguyên ngay cả khi không gọi method nguy hiểm. Hãy đặt và kiểm thử các giới hạn ở tầng ứng dụng:

- Độ dài source expression tối đa.
- Số lượng expression được parse/lưu và tốc độ tạo expression.
- Kích thước list/map, độ sâu object và số phần tử được selection/projection duyệt.
- Kích thước array và collection auto-growth.
- Độ dài chuỗi và regex được phép.
- Thời gian của các function/method được expose.
- Số request đánh giá đồng thời và rate limit.

Không giả định SpEL cung cấp timeout tổng quát hoặc sandbox có ngân sách CPU/bộ nhớ. Nếu cần giới hạn thời gian thực thi, đặt evaluation trong kiến trúc có thể kiểm soát timeout/concurrency phù hợp; không dựa vào một thread interrupt để đảm bảo mọi code Java dừng ngay lập tức.

Với regex do người dùng kiểm soát, cân nhắc bỏ tính năng `matches` hoặc dùng một policy/engine regex có giới hạn rõ ràng. Kiểm thử cả input dài và pattern có thể gây backtracking.

## 14. Kiểm thử fail-closed và thông báo lỗi

Nếu expression dùng cho authorization hoặc quyết định cho phép hành động, lỗi evaluation không được biến thành `true` hoặc được xem như thành công.

Test cần xác nhận:

- Rule trả true hợp lệ thì policy cho phép theo nghiệp vụ.
- Rule trả false hợp lệ thì policy từ chối theo nghiệp vụ.
- Parse/evaluation error tạo trạng thái lỗi riêng và không cho phép hành động.
- Response không chứa raw expression, stack trace, exception message hoặc secret.
- Log mặc định chỉ ghi rule ID/version, correlation ID và error category.

Ví dụ kiểm tra trạng thái fail-closed:

~~~java
RuleResult result = ruleEvaluator.evaluate(untrustedRule, customerView);

assertThat(result.status()).isEqualTo(RuleStatus.ERROR);
assertThat(result.isAllowed()).isFalse();
~~~

`RuleResult` là kiểu ứng dụng tự định nghĩa. Giữ `ERROR` khác `DENY` để vận hành có thể phân biệt rule đã đánh giá thành công nhưng từ chối với rule không thể đánh giá.

## 15. Regression matrix cho CI

Một bảng kiểm thử ngắn giúp bảo đảm thay đổi context hoặc Spring version không vô tình mở thêm quyền:

| Nhóm | Positive test | Negative test |
| --- | --- | --- |
| Property | Đọc field DTO được phép. | Đọc property ngoài allowlist. |
| Write access | Cập nhật field được phép nếu use case cần. | Ghi field nhạy cảm hoặc ghi trong read-only context. |
| Type reference | Resolve type trong allowlist nếu được phép. | Resolve `Runtime` hoặc class ngoài allowlist. |
| Constructor | Gọi constructor được duyệt nếu cần. | Tạo class không được phép. |
| Method | Gọi method thuần được allowlist. | Gọi method có side effect hoặc method ngoài allowlist. |
| Bean | Resolve facade bean được phép. | Resolve repository/admin bean ngoài allowlist. |
| Function | Gọi helper thuần đã đăng ký. | Gọi function chưa đăng ký hoặc function nguy hiểm. |
| Input | Dữ liệu chứa ký tự SpEL được so sánh như chuỗi. | Input bị ghép vào source hoặc parse lần hai. |
| Error handling | Mã lỗi ổn định, response an toàn. | Source, secret, stack trace hoặc rejected value bị lộ. |
| Resource limits | Expression trong giới hạn chạy bình thường. | Source quá dài, collection quá lớn hoặc regex quá phức tạp bị từ chối. |

Chạy regression suite khi thay đổi Spring Framework, `EvaluationContext`, resolver/accessor, function registration, root DTO hoặc rule parser. Cấu hình bảo mật là một phần hành vi ứng dụng và cần được kiểm thử như code.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| Test chỉ xác nhận expression ném exception | Method có thể đã chạy side effect trước khi lỗi phát sinh ở bước khác. | Dùng probe/counter để xác nhận hành động không xảy ra. |
| Negative test pass nhưng rule hợp lệ cũng bị chặn | Chỉ viết test từ chối, thiếu positive tests. | Test song song property/operation được phép và bị cấm. |
| `T(...)` vẫn hoạt động trong Standard context | `TypeLocator` mặc định còn được cấu hình. | Dùng locator allowlist hoặc context không hỗ trợ type reference. |
| Constructor vẫn chạy | Reflective constructor resolver còn hoạt động. | Bỏ resolver hoặc dùng resolver allowlist và test constructor ngoài policy. |
| Method nguy hiểm vẫn gọi được | Reflective method resolver hoặc object có API rộng vẫn được expose. | Giới hạn resolver, filter theo type và root object. |
| Bean reference hoạt động ngoài dự kiến | Context có BeanResolver hoặc dùng Spring expression template đã cấu hình sẵn. | Kiểm tra context thực tế; chỉ expose bean allowlist. |
| Function nguy hiểm vẫn chạy | Function đã được đăng ký như variable/method. | Kiểm kê và test riêng function registry. |
| Chuỗi input được thực thi như expression | Input bị nối vào source hoặc parse lần hai. | Dùng source cố định và truyền dữ liệu qua variable có kiểu. |
| Getter tạo truy vấn ngoài ý muốn | DTO thực tế là entity có lazy loading hoặc getter có side effect. | Dùng view object đã chuẩn bị dữ liệu và test getter/accessor. |
| Evaluation error được xem là allow | Exception bị catch rồi trả `true` hoặc giá trị mặc định. | Dùng trạng thái ERROR riêng và fail-closed. |

## Ghi nhớ

- Viết policy quyền trước, sau đó tạo positive và negative tests cho từng capability.
- Dùng `SimpleEvaluationContext.forReadOnlyDataBinding()` khi chỉ cần đọc property; method invocation tắt mặc định.
- Kiểm tra riêng type reference, constructor, method, bean reference, registered functions và property accessors.
- Test side effect bằng probe/counter; exception đơn thuần chưa chứng minh method không chạy.
- `MethodFilter` chỉ giới hạn reflective methods trên type đã đăng ký; không thay thế kiểm soát các resolver và object khác.
- Truyền user input qua variable, không nối vào source expression; nếu source do user kiểm soát thì vẫn phải giới hạn cú pháp và quyền.
- Dùng DTO/view object có getter thuần đọc; read-only context không tự bảo đảm getter không có side effect.
- Kiểm thử parse errors, evaluation errors và business false như ba kết quả khác nhau.
- Với authorization, evaluation error phải fail-closed và được biểu diễn bằng trạng thái ERROR riêng.
- Đặt giới hạn độ dài expression, kích thước collection, auto-growth, regex và concurrency; SpEL không cung cấp sandbox/timeout tổng quát.
- Chạy regression suite khi thay đổi Spring version hoặc cấu hình EvaluationContext/resolver/accessor.

## Tài liệu tham khảo

- [Spring Framework Reference — Evaluation and SimpleEvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Type References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/types.html)
- [Spring Framework Reference — Constructors](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/constructors.html)
- [Spring Framework Reference — Methods](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/methods.html)
- [Spring Framework Reference — Bean References](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/bean-references.html)
- [Spring Framework API — SimpleEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [Spring Framework API — TypeLocator](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/TypeLocator.html)
- [Spring Framework API — MethodFilter](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/MethodFilter.html)
- [Spring Framework API — ConstructorResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ConstructorResolver.html)
- [Spring Framework API — StandardEvaluationContext](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)