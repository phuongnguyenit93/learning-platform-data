# Khác biệt giữa function và method của root object trong Spring Expression Language (SpEL)

SpEL cho phép gọi cả **function được đăng ký trong EvaluationContext** và **method của root object**. Hai cách gọi có cú pháp và mục đích khác nhau:

~~~text
#normalize('  Spring  ')
greeting('Hello')
~~~

`#normalize(...)` gọi một function đã được đăng ký trong context. `greeting(...)` gọi method trên root object hiện tại. Một function thường là phương thức Java static được đăng ký bằng một đối tượng `Method`; method của root object là hành vi của instance đang được dùng làm đối tượng gốc.

Hiểu rõ khác biệt này giúp chọn đúng nơi đặt logic, cấu hình context đúng cách và tránh nhầm lẫn giữa biến, function, method của root object và method của bean.

## 1. Hai cơ chế gọi có vai trò khác nhau

### Function trong EvaluationContext

Function là một phương thức Java được đăng ký với tên trong EvaluationContext. Khi gọi trong SpEL, tên function có tiền tố `#`:

~~~text
#functionName(argument1, argument2)
~~~

Ví dụ:

~~~text
#normalize('  Spring Expression Language  ')
#isValidCode('SKU-100')
~~~

Function không cần root object phải có method cùng tên. SpEL tìm function trong namespace biến/function của EvaluationContext.

### Method của root object

Method của root object là phương thức có sẵn trên đối tượng gốc đang được dùng để đánh giá biểu thức. Có thể gọi method trực tiếp:

~~~text
methodName(argument1, argument2)
~~~

Hoặc chỉ rõ đối tượng gốc:

~~~text
#root.methodName(argument1, argument2)
~~~

Ví dụ:

~~~text
greeting('Hello')
#root.calculateDiscount('VIP')
~~~

Ở đây, SpEL gọi method trên instance root object. Method có thể đọc trạng thái của chính đối tượng đó thông qua các field hoặc property của instance.

## 2. Bảng so sánh function và method của root object

| Tiêu chí | Function | Method của root object |
|---|---|---|
| Cách gọi | `#functionName(...)` | `methodName(...)` hoặc `#root.methodName(...)` |
| Nơi khai báo | Phương thức Java được đăng ký trong EvaluationContext | Phương thức của lớp root object |
| Cách phân giải | Tên function trong context | MethodResolver trên đối tượng đích |
| Đối tượng nhận lời gọi | Function đã đăng ký; thường là method static | Instance root object |
| Phụ thuộc root object | Không cần method thuộc root object | Cần root object có method phù hợp |
| Mục đích thường gặp | Hàm tiện ích, chuẩn hóa, kiểm tra hoặc tính toán dùng chung | Hành vi gắn với dữ liệu và trạng thái của đối tượng miền nghiệp vụ |

Một function có thể nhận dữ liệu lấy từ root object làm đối số. Ngược lại, method của root object có thể sử dụng trực tiếp trạng thái của instance mà không cần truyền lại chính đối tượng đó.

## 3. Đăng ký function trong StandardEvaluationContext

`StandardEvaluationContext` cung cấp phương thức `registerFunction(String, Method)` để đăng ký function.

Ví dụ, tạo một lớp tiện ích có phương thức static:

~~~java
public final class TextFunctions {

    private TextFunctions() {
    }

    public static String normalize(String value) {
        if (value == null) {
            return null;
        }

        return value.trim().toLowerCase(Locale.ROOT);
    }

    public static boolean isValidCode(String value) {
        return value != null && value.matches("[A-Z]{3}-[0-9]+");
    }
}
~~~

Lấy đối tượng Method bằng reflection rồi đăng ký:

~~~java
import java.lang.reflect.Method;

Method normalizeMethod =
        TextFunctions.class.getDeclaredMethod("normalize", String.class);

Method validCodeMethod =
        TextFunctions.class.getDeclaredMethod("isValidCode", String.class);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.registerFunction("normalize", normalizeMethod);
context.registerFunction("isValidCode", validCodeMethod);
~~~

Trong ví dụ, hai function được đăng ký với tên normalize và isValidCode. Khi viết biểu thức, thêm tiền tố `#` trước tên đã đăng ký.

~~~java
ExpressionParser parser = new SpelExpressionParser();

String normalized = parser.parseExpression(
        "#normalize('  Spring  ')"
).getValue(context, String.class);

Boolean valid = parser.parseExpression(
        "#isValidCode('SKU-100')"
).getValue(context, Boolean.class);
~~~

Kết quả của function được trả về như kết quả của biểu thức. Kiểu Java mong đợi có thể được chỉ định bằng overload `getValue(Class<T>)`.

### 3.1. Chữ ký phương thức dùng làm function

Function được đăng ký thông qua đối tượng `java.lang.reflect.Method`. Phương thức static là lựa chọn thông thường vì function không có instance root object làm receiver.

Khi lấy Method, tên phương thức và danh sách kiểu tham số phải khớp với chữ ký thực tế:

~~~java
Method method =
        TextFunctions.class.getDeclaredMethod(
                "normalize",
                String.class
        );
~~~

Nếu tên hoặc kiểu tham số không khớp, `getDeclaredMethod(...)` sẽ không tìm thấy phương thức. Hãy xử lý `NoSuchMethodException` trong mã Java khi cấu hình context.

Function nên có đầu vào và kết quả rõ ràng. Nếu function có tác dụng phụ, phụ thuộc trạng thái toàn cục hoặc thực hiện thao tác khó dự đoán, biểu thức sẽ khó kiểm thử và khó hiểu hơn.

## 4. Gọi method của root object

Để gọi method của root object, tạo context với đối tượng có method cần dùng.

~~~java
public class Customer {
    private final String name;
    private final int age;

    public Customer(String name, int age) {
        this.name = name;
        this.age = age;
    }

    public String getName() {
        return name;
    }

    public int getAge() {
        return age;
    }

    public String greeting(String prefix) {
        return prefix + ", " + name;
    }

    public boolean isAdult() {
        return age >= 18;
    }
}
~~~

Đặt Customer làm root object và gọi method:

~~~java
Customer customer = new Customer("Lan", 25);

StandardEvaluationContext context =
        new StandardEvaluationContext(customer);

ExpressionParser parser = new SpelExpressionParser();

String greeting = parser.parseExpression(
        "greeting('Hello')"
).getValue(context, String.class);

Boolean adult = parser.parseExpression(
        "isAdult()"
).getValue(context, Boolean.class);
~~~

`greeting('Hello')` được gọi trên instance customer. Method sử dụng name của chính instance để tạo lời chào. `isAdult()` cũng đọc age từ instance đó.

Có thể viết tường minh qua `#root`:

~~~text
#root.greeting('Hello')
#root.isAdult()
~~~

Cách viết này hữu ích khi biểu thức có nhiều đối tượng hiện hành hoặc được lồng trong selection/projection.

## 5. Cách phân giải method của root object

Khi SpEL gặp lời gọi method trên root object, nó dùng MethodResolver trong EvaluationContext để tìm phương thức phù hợp với tên và các đối số.

Với `StandardEvaluationContext`, cơ chế phản chiếu mặc định có thể phân giải các method phù hợp trên đối tượng Java.

Ví dụ:

~~~text
calculateTotal(3, 4)
#root.calculateTotal(3, 4)
~~~

Nếu lớp root object có nhiều overload cùng tên, SpEL cần chọn method phù hợp dựa trên số lượng và kiểu đối số, cùng các quy tắc chuyển đổi được context hỗ trợ.

Khi method không được tìm thấy hoặc đối số không tương thích, quá trình đánh giá có thể phát sinh lỗi. Hãy kiểm tra:

- Tên method và chữ ký tham số.
- Kiểu runtime của đối số.
- Kiểu trả về mà mã Java mong đợi.
- Method có thể được truy cập trong môi trường hiện tại hay không.
- MethodResolver được cấu hình trong EvaluationContext.

Method của root object thường nên thể hiện hành vi hợp lý của đối tượng. Không nên đưa toàn bộ logic ứng dụng hoặc thao tác hệ thống vào các method chỉ để gọi từ SpEL.

## 6. Function và method có thể nhận cùng một dữ liệu nhưng khác receiver

Một function và một method có thể thực hiện phép tính tương tự, nhưng chúng được gọi theo hai cơ chế khác nhau.

Ví dụ, function tính giá sau giảm giá:

~~~java
public final class PricingFunctions {

    private PricingFunctions() {
    }

    public static BigDecimal discountedPrice(
            BigDecimal price,
            BigDecimal rate) {
        return price.multiply(BigDecimal.ONE.subtract(rate));
    }
}
~~~

Đăng ký và gọi:

~~~java
Method method = PricingFunctions.class.getDeclaredMethod(
        "discountedPrice",
        BigDecimal.class,
        BigDecimal.class
);

context.registerFunction("discountedPrice", method);

BigDecimal result = parser.parseExpression(
        "#discountedPrice(100M, 0.1M)"
).getValue(context, BigDecimal.class);
~~~

Trong trường hợp này, function nhận cả price và rate làm đối số. Nó không cần một PricingPolicy làm root object.

Ngược lại, method của PricingPolicy có thể sử dụng rate được lưu trong instance:

~~~java
public class PricingPolicy {
    private final BigDecimal discountRate;

    public PricingPolicy(BigDecimal discountRate) {
        this.discountRate = discountRate;
    }

    public BigDecimal discountedPrice(BigDecimal price) {
        return price.multiply(BigDecimal.ONE.subtract(discountRate));
    }
}
~~~

Gọi method của root object:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext(new PricingPolicy(new BigDecimal("0.10")));

BigDecimal result = parser.parseExpression(
        "discountedPrice(100M)"
).getValue(context, BigDecimal.class);
~~~

Method chỉ nhận price vì discountRate đã nằm trong trạng thái của root object.

Chọn function khi phép xử lý là tiện ích dùng chung và các đầu vào cần được truyền tường minh. Chọn method khi hành vi gắn với dữ liệu hoặc trạng thái của chính đối tượng.

## 7. Namespace của function và biến

Function được đăng ký trong EvaluationContext bằng tên và được gọi với tiền tố `#`. Biến cũng sử dụng tiền tố đó:

~~~text
#minimumAge
#normalize('Spring')
~~~

Vì function và biến cùng dùng namespace tham chiếu có tiền tố `#`, tránh đăng ký một biến và một function trùng tên trong cùng context. Tên trùng có thể làm biểu thức khó hiểu hoặc gây xung đột khi phân giải.

Ví dụ:

~~~java
context.setVariable("minimumAge", 18);
context.registerFunction("normalize", normalizeMethod);
~~~

Sau khi đăng ký:

~~~text
age >= #minimumAge
#normalize(name)
~~~

`#minimumAge` lấy giá trị biến; `#normalize(name)` gọi function normalize với đối số được lấy từ root object.

Không cần thêm `#` trước tên method của root object khi gọi method trực tiếp:

~~~text
isAdult()
#root.isAdult()
~~~

Đây là khác biệt cú pháp quan trọng khi đọc biểu thức.

## 8. Gọi function và method bên trong collection expression

Function đã đăng ký có thể được dùng trong biểu thức selection hoặc projection. Method của phần tử hiện hành cũng có thể được gọi trong các biểu thức đó.

Ví dụ, root object là CustomerReport có collection customers:

~~~text
customers.?[#this.isAdult()].![#normalize(#this.name)]
~~~

Trong biểu thức:

- `#this.isAdult()` gọi method trên Customer hiện hành.
- `#normalize(...)` gọi function đã đăng ký trong EvaluationContext.
- `#this.name` lấy property name từ Customer hiện hành.

Nếu cần gọi method trên root object bên ngoài collection, dùng `#root`:

~~~text
customers.?[#root.isAllowed(#this)].![#this.name]
~~~

Cách này phân biệt rõ method của root object với method của phần tử hiện tại. Không nên dựa vào tên không tiền tố trong biểu thức lồng nhau nếu chưa xác định đối tượng hiện hành ở vị trí đó.

## 9. So sánh với method của bean được tham chiếu

Method của root object và method của bean tham chiếu cũng là hai cách gọi khác nhau.

Ví dụ bean reference:

~~~text
@pricingService.discountedPrice(100M)
~~~

`@pricingService` yêu cầu BeanResolver tìm bean theo tên rồi gọi method trên bean đó.

So sánh:

| Cách gọi | Đối tượng nhận lời gọi |
|---|---|
| `discountedPrice(100M)` | Root object hiện tại |
| `#root.discountedPrice(100M)` | Root object được chỉ định tường minh |
| `#discountedPrice(100M)` | Function đăng ký trong EvaluationContext |
| `@pricingService.discountedPrice(100M)` | Bean pricingService được BeanResolver phân giải |

Ba trường hợp cuối có thể trông gần giống nhau nhưng cơ chế phân giải khác nhau. Hãy xác định receiver trước khi đọc hoặc viết biểu thức.

## 10. Giá trị trả về, chuyển đổi kiểu và lỗi

Function và method đều trả về giá trị mà SpEL tiếp tục sử dụng trong biểu thức. Kiểu trả về có thể là String, Boolean, số, object miền nghiệp vụ hoặc null.

Ví dụ:

~~~java
String label = parser.parseExpression(
        "#normalize(name)"
).getValue(context, String.class);
~~~

SpEL dùng kiểu kết quả cùng TypeConverter của context khi cần cung cấp giá trị theo kiểu được yêu cầu. Nếu không thể chuyển đổi, quá trình đánh giá có thể phát sinh EvaluationException.

Các lỗi thường gặp:

- Function chưa được đăng ký trong context.
- Tên function trong biểu thức khác tên lúc registerFunction.
- Method Java dùng làm function không có chữ ký được yêu cầu.
- Root object không có method tương ứng.
- Đối số không tương thích với tham số method.
- Method hoặc function ném exception khi thực thi.
- Kết quả null nhưng biểu thức tiếp tục truy cập property hoặc gọi method trên kết quả đó.

Khi chẩn đoán, phân biệt lỗi phân tích cú pháp với lỗi đánh giá. Kiểm tra nơi function được đăng ký, root object hiện tại, method signature và kiểu đối số thực tế.

## 11. Lưu ý thiết kế và bảo mật

Function và method đều có thể thực thi mã Java khi biểu thức được đánh giá. Nếu biểu thức được cung cấp từ người dùng hoặc nguồn không đáng tin cậy, cần kiểm soát các function được đăng ký và các method mà root object cho phép truy cập.

Một số nguyên tắc:

1. Chỉ đăng ký function thực sự cần thiết.
2. Dùng function có đầu vào rõ ràng và tránh tác dụng phụ.
3. Giữ method của root object tập trung vào hành vi thuộc trách nhiệm của đối tượng.
4. Chỉ cung cấp root object chứa dữ liệu và hành vi cần thiết cho biểu thức.
5. Không đánh giá biểu thức không đáng tin cậy bằng một StandardEvaluationContext có quyền truy cập rộng.
6. Nếu cần giới hạn tính năng, cân nhắc SimpleEvaluationContext và cấu hình cụ thể các khả năng được phép; không giả định mọi function hoặc method đều được bật trong context giới hạn.

Không nên dùng function như một cách vòng qua thiết kế đối tượng, cũng không nên biến root object thành một cổng truy cập tùy ý tới toàn bộ ứng dụng.

## 12. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi function mà quên `#` | Function được tham chiếu qua namespace biến với tiền tố #. | Dùng `#functionName(...)`. |
| Gọi method root như function | Method của root object không cần được đăng ký bằng registerFunction. | Gọi `methodName(...)` hoặc `#root.methodName(...)`. |
| Function không tồn tại | Chưa gọi registerFunction hoặc tên đăng ký không khớp. | Đăng ký Method đúng tên trong context đang đánh giá. |
| Dùng instance method làm function nhưng không có receiver phù hợp | Function đăng ký bằng Method thường được thiết kế là phương thức static. | Dùng static utility method hoặc chuyển hành vi sang method của root object. |
| Nhầm function với biến | Cả hai đều dùng tiền tố #. | Tránh tên trùng và ghi rõ mục đích của từng tên. |
| Gọi method trên root object sai chữ ký | Method không tồn tại hoặc đối số không tương thích. | Kiểm tra method signature và kiểu đối số. |
| Gọi nhầm root method trong selection/projection | Đối tượng hiện hành đã chuyển thành phần tử collection. | Dùng `#root.methodName(...)` để chỉ rõ root object. |
| Cho rằng function tự truy cập root object | Function được gọi theo Method đã đăng ký và đối số truyền vào. | Truyền dữ liệu cần thiết làm đối số hoặc dùng method của root object. |
| Biểu thức gây tác dụng phụ khó dự đoán | Function hoặc method thay đổi trạng thái khi được gọi. | Ưu tiên logic thuần, kết quả xác định và dễ kiểm thử. |

## 13. Ghi nhớ

- Function được đăng ký trong EvaluationContext và gọi bằng cú pháp `#functionName(...)`.
- `StandardEvaluationContext.registerFunction(...)` nhận tên và đối tượng Java Method.
- Function thường là phương thức static, độc lập với instance root object.
- Method của root object được gọi bằng `methodName(...)` hoặc `#root.methodName(...)`.
- Method của root object là hành vi của instance hiện tại và có thể dùng trạng thái của instance.
- Function và biến cùng dùng namespace tham chiếu `#`; tránh đặt tên trùng.
- Trong selection/projection, `#this` là phần tử hiện hành, còn `#root` vẫn là root object ban đầu.
- `@beanName.method(...)` là lời gọi method trên bean được BeanResolver phân giải, không phải function hay method trực tiếp của root object.
- Chọn function cho tiện ích dùng chung; chọn root method cho hành vi gắn với đối tượng.
- Giới hạn function, root object và quyền truy cập khi đánh giá biểu thức không đáng tin cậy.
