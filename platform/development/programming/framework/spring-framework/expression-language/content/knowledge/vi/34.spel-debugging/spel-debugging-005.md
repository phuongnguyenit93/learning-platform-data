# Kiểm tra kiểu runtime trước khi chọn toán tử trong SpEL

## 1. Vì sao phải kiểm tra kiểu runtime?

Spring Expression Language (SpEL) đánh giá biểu thức trên các object và giá trị có thật tại thời điểm chạy. Một property khai báo là Object, một variable được thay đổi theo request, hoặc một method trả về nhiều kiểu dữ liệu có thể khiến cùng một expression nhận những kiểu runtime khác nhau.

Toán tử chỉ có ý nghĩa khi kiểu của toán hạng phù hợp. Ví dụ:

- Cộng hai giá trị số để tính tổng.
- Nối chuỗi khi muốn tạo nội dung văn bản.
- Dùng and, or và not với điều kiện Boolean.
- Dùng matches với chuỗi và regular expression.
- Dùng selection trên collection.
- So sánh enum với constant thuộc đúng enum type.
- Dùng method chỉ tồn tại trên một kiểu cụ thể.

Nếu chọn toán tử dựa trên giả định về kiểu thay vì kiểu runtime thực tế, expression có thể phát sinh lỗi evaluation hoặc trả về kết quả khác ý định. Khi debug, hãy xác định kiểu của từng toán hạng trước, sau đó mới quyết định phép toán phù hợp.

## 2. Phân biệt kiểu khai báo và kiểu runtime

Kiểu khai báo là kiểu được viết trong class hoặc interface. Kiểu runtime là class thực tế của object đang được giữ tại thời điểm expression được đánh giá.

Ví dụ:

~~~java
public class Message {
    private Object value;

    public Message(Object value) {
        this.value = value;
    }

    public Object getValue() {
        return value;
    }
}
~~~

Property value có kiểu khai báo Object, nhưng ở runtime có thể chứa String, Integer, BigDecimal hoặc một object miền nghiệp vụ:

~~~java
Message first = new Message("hello");
Message second = new Message(42);
Message third = new Message(new BigDecimal("12.50"));
~~~

Cùng một expression có thể gặp những kiểu thực tế khác nhau tùy object được truyền vào. Không nên suy luận rằng value luôn là String chỉ vì một test fixture đầu tiên sử dụng String.

Với property có kiểu cụ thể như String hoặc BigDecimal, hợp đồng kiểu thường rõ ràng hơn. Với Object, interface rộng hoặc collection chứa nhiều kiểu phần tử, hãy kiểm tra runtime type và xác định các trường hợp hợp lệ.

## 3. Dùng instanceof để kiểm tra kiểu

SpEL hỗ trợ toán tử instanceof để kiểm tra object có tương thích với một Java type hay không:

~~~java
#value instanceof T(java.lang.String)
~~~

Type reference T(...) chỉ rõ class dùng để kiểm tra. Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression isString =
        parser.parseExpression("#value instanceof T(java.lang.String)");

Expression isNumber =
        parser.parseExpression("#value instanceof T(java.lang.Number)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", "hello");

assertTrue(isString.getValue(context, Boolean.class));
assertFalse(isNumber.getValue(context, Boolean.class));

context.setVariable("value", Integer.valueOf(42));

assertFalse(isString.getValue(context, Boolean.class));
assertTrue(isNumber.getValue(context, Boolean.class));
~~~

instanceof kiểm tra khả năng tương thích kiểu của object thực tế. Một Integer là Number, vì vậy kiểm tra với Number cũng trả về true.

Phép kiểm tra này không chuyển đổi giá trị. Chuỗi "42" vẫn là String; nó không trở thành Integer chỉ vì nội dung có thể parse thành số.

## 4. Kiểm tra interface hoặc lớp cha

instanceof có thể kiểm tra interface và lớp cha, không chỉ class cụ thể:

~~~java
#value instanceof T(java.lang.CharSequence)
#value instanceof T(java.lang.Number)
#value instanceof T(java.util.Collection)
#value instanceof T(java.util.Map)
~~~

Ví dụ kiểm tra một giá trị có phải collection hay không:

~~~java
Expression expression = parser.parseExpression(
        "#value instanceof T(java.util.Collection)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", List.of("A", "B"));

Boolean isCollection = expression.getValue(context, Boolean.class);
assertTrue(isCollection);
~~~

Kiểm tra theo interface thường hữu ích hơn kiểm tra implementation cụ thể. Ví dụ, nếu expression chỉ cần size() và iteration, kiểm tra Collection cho phép List, Set và các implementation phù hợp cùng được chấp nhận.

Chỉ kiểm tra đúng kiểu cần cho thao tác tiếp theo. Nếu logic phụ thuộc vào thứ tự, hãy xác định thêm rằng dữ liệu có contract List hoặc một collection có thứ tự phù hợp.

## 5. Kiểm tra null trước khi gọi method hoặc đọc property

Null không có runtime class để kiểm tra bằng getClass. Toán tử instanceof trả về false khi toán hạng trái là null. Có thể dùng điều kiện tường minh để làm rõ nhánh xử lý:

~~~java
Expression expression = parser.parseExpression(
        "#value != null and #value instanceof T(java.lang.String)");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", null);

Boolean result = expression.getValue(context, Boolean.class);
assertFalse(result);
~~~

Nếu cần gọi method trên object có thể null, dùng null-safe navigation hoặc biểu thức điều kiện:

~~~text
#value?.toString()
~~~

Hoặc:

~~~text
#value != null ? #value.toString() : 'No value'
~~~

Null-safe navigation bảo vệ thao tác ngay sau toán tử. Với đường dẫn nhiều cấp, hãy kiểm tra từng object trung gian có thể null.

Đừng coi null là một kiểu dữ liệu khác như String rỗng, số 0 hoặc Boolean false. Các trạng thái đó có ý nghĩa riêng và cần được xử lý theo yêu cầu nghiệp vụ.

## 6. Chọn toán tử số học khi toán hạng là số

Các phép toán số học như +, -, *, / và % cần toán hạng có thể tham gia phép tính số. Nếu dữ liệu có thể là nhiều kiểu số, hãy xác định phạm vi kiểu được chấp nhận trước khi tính.

Ví dụ kiểm tra Number:

~~~java
Expression expression = parser.parseExpression(
        "#value instanceof T(java.lang.Number) "
        + "? #value + 10 "
        + ": null");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", Integer.valueOf(5));

Object result = expression.getValue(context);
assertEquals(15, result);
~~~

Number bao gồm nhiều kiểu wrapper số và BigDecimal. Tuy nhiên, phép toán trên các kiểu số khác nhau có thể có quy tắc chuyển đổi và độ chính xác khác nhau. Với tiền tệ hoặc dữ liệu cần độ chính xác thập phân, ưu tiên BigDecimal và kiểm soát kiểu của cả hai toán hạng.

Không dùng phép toán số học trực tiếp trên một String chỉ vì chuỗi đó trông giống số. Nếu dữ liệu đầu vào là văn bản, hãy chuyển đổi rõ ràng sang kiểu số ở ranh giới phù hợp, kiểm tra lỗi parse và sau đó mới thực hiện phép tính.

## 7. Phân biệt phép cộng số với nối chuỗi

Trong SpEL, toán tử + có thể được dùng cho phép cộng số hoặc nối chuỗi tùy kiểu toán hạng. Điều này khiến expression có thể có hành vi khác nhau nếu kiểu runtime thay đổi.

Ví dụ:

~~~java
Expression expression = parser.parseExpression("#left + #right");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("left", 10);
context.setVariable("right", 5);

assertEquals(15, expression.getValue(context));

context.setVariable("left", "10");
context.setVariable("right", "5");

assertEquals("105", expression.getValue(context));
~~~

Cùng một ký hiệu + nhưng kết quả phụ thuộc vào kiểu dữ liệu. Nếu mục tiêu luôn là phép cộng số, hãy chuẩn hóa hai giá trị thành kiểu số trước khi evaluate hoặc kiểm tra kiểu trước khi áp dụng toán tử.

Nếu mục tiêu luôn là tạo chuỗi, hãy chuyển đổi các thành phần sang String một cách rõ ràng và dùng expression có ý nghĩa văn bản. Đừng dựa vào một toán tử + duy nhất khi dữ liệu đầu vào có thể thay đổi kiểu.

## 8. Chọn toán tử logic cho Boolean

Các toán tử and, or và not dùng để kết hợp hoặc đảo điều kiện Boolean. Không nên giả định SpEL coi mọi giá trị khác null là true như một số ngôn ngữ scripting khác.

Ví dụ:

~~~java
Expression expression = parser.parseExpression(
        "#active and #approved");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("active", true);
context.setVariable("approved", false);

Boolean allowed = expression.getValue(context, Boolean.class);
assertFalse(allowed);
~~~

Nếu variable có thể là null hoặc không phải Boolean, hãy xác định chính sách trước khi kết hợp điều kiện:

~~~text
#active == true and #approved == true
~~~

So sánh tường minh với true làm rõ điều kiện mong đợi. Nếu variable được khai báo là Object, kiểm tra runtime type hoặc chuyển đổi ở bước đầu vào thay vì để expression phụ thuộc vào coercion không rõ ràng.

Khi điều kiện phức tạp, chia thành các biểu thức nhỏ hoặc method Java có tên để dễ debug từng nhánh.

## 9. Dùng matches cho chuỗi

Toán tử matches kiểm tra một chuỗi có khớp regular expression hay không. Hãy bảo đảm toán hạng trái là String trước khi dùng:

~~~java
Expression expression = parser.parseExpression(
        "#value instanceof T(java.lang.String) "
        + "and #value matches '[A-Z]{3}-[0-9]{4}'");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", "INV-2026");

Boolean valid = expression.getValue(context, Boolean.class);
assertTrue(valid);
~~~

Nếu value là Integer hoặc null, điều kiện kiểu không cho phép nhánh matches được sử dụng. Khi cần xử lý dữ liệu không phải chuỗi, hãy quyết định có chuyển đổi sang String hay từ chối dữ liệu.

Regular expression chỉ kiểm tra định dạng văn bản. Nó không chứng minh mã đó tồn tại, hợp lệ trong database hoặc được phép sử dụng trong nghiệp vụ.

## 10. Chọn toán tử cho collection và Map

Trước khi dùng selection hoặc projection, hãy xác định target có phải collection phù hợp hay không:

~~~java
Expression expression = parser.parseExpression(
        "#items instanceof T(java.util.Collection) "
        + "? #items.?[active] "
        + ": null");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable(
        "items",
        List.of(new Item("A", true), new Item("B", false)));

List<?> activeItems = expression.getValue(context, List.class);
assertEquals(1, activeItems.size());
~~~

Nếu target là Map, cần nhớ Map có key và value; thao tác index access dùng key, còn selection duyệt entry theo ngữ nghĩa collection của SpEL. Đừng áp dụng predicate dành cho List vào Map mà không xác định rõ đang xét entry hay value.

Null-safe collection operators có thể giúp xử lý target collection null trong các phiên bản Spring Framework hỗ trợ cú pháp đó. Chúng không tự bảo vệ phần tử null bên trong collection; predicate vẫn cần kiểm tra phần tử trước khi đọc property.

## 11. Kiểm tra enum trước khi so sánh

Enum constant là giá trị thuộc một enum type cụ thể. Khi expression nhận một variable có thể là String hoặc enum, hãy kiểm tra kiểu và so sánh với constant đúng kiểu:

~~~java
Expression expression = parser.parseExpression(
        "#status instanceof T(com.example.OrderStatus) "
        + "and #status == T(com.example.OrderStatus).PAID");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("status", OrderStatus.PAID);

Boolean paid = expression.getValue(context, Boolean.class);
~~~

Nếu status là String "PAID", instanceof với OrderStatus trả về false. String và enum là hai kiểu khác nhau dù nội dung hiển thị giống nhau.

Nếu dữ liệu đến từ request dưới dạng String, hãy chuyển đổi nó thành enum tại tầng binding hoặc service và xử lý giá trị không hợp lệ. Không so sánh enum với chuỗi rồi giả định SpEL tự động biến chuỗi thành enum.

## 12. Phân biệt kiểm tra kiểu với chuyển đổi kiểu

instanceof và conversion là hai thao tác khác nhau:

| Mục đích | Cách thực hiện | Kết quả |
|---|---|---|
| Kiểm tra object có phải String | #value instanceof T(String) | Boolean, không thay đổi object |
| Kiểm tra object có phải Number | #value instanceof T(Number) | Boolean, không thay đổi object |
| Chuyển String thành Integer | Dùng ConversionService hoặc bước binding phù hợp | Tạo giá trị Integer nếu chuyển đổi thành công |
| Yêu cầu kiểu kết quả từ SpEL | getValue(context, Integer.class) | Có thể áp dụng TypeConverter cho kết quả |
| Gán String vào property Integer | Expression.setValue với TypeConverter phù hợp | Chuyển đổi trước khi gán nếu được hỗ trợ |

Ví dụ, chuỗi "42" không phải Integer:

~~~java
context.setVariable("value", "42");

Boolean isInteger = parser.parseExpression(
        "#value instanceof T(java.lang.Integer)")
        .getValue(context, Boolean.class);

assertFalse(isInteger);
~~~

Có thể yêu cầu ConversionService chuyển đổi:

~~~java
Integer converted = conversionService.convert("42", Integer.class);
assertEquals(Integer.valueOf(42), converted);
~~~

Sau chuyển đổi, object mới có kiểu Integer. Hãy phân biệt rõ giá trị ban đầu và giá trị đã chuyển đổi để tránh debug nhầm kiểu runtime.

## 13. Chú ý khi dùng getValue với kiểu kết quả

Overload getValue(context, TargetType.class) có thể yêu cầu SpEL chuyển đổi kết quả sang kiểu đích thông qua TypeConverter. Vì vậy, kiểu biến nhận kết quả không nhất thiết là kiểu runtime ban đầu của node cuối cùng trong expression.

Ví dụ:

~~~java
Expression expression = parser.parseExpression("'42'");

Object raw = expression.getValue();
Integer converted = expression.getValue(Integer.class);

assertEquals("42", raw);
assertEquals(Integer.valueOf(42), converted);
~~~

Nếu đang debug kiểu runtime của kết quả expression, trước tiên hãy gọi getValue không truyền target type và kiểm tra object trả về trong Java:

~~~java
Object raw = expression.getValue(context);

String runtimeType =
        raw == null ? "null" : raw.getClass().getName();
~~~

Sau đó mới kiểm tra việc chuyển đổi sang kiểu mà code ứng dụng yêu cầu. Điều này giúp phân biệt lỗi trong expression với lỗi hoặc hành vi chuyển đổi ở ranh giới getValue.

## 14. Kiểm tra từng toán hạng trước khi áp dụng toán tử

Khi expression lớn thất bại, đừng chỉ debug toàn bộ chuỗi. Hãy parse và evaluate các phần con để xác định kiểu và giá trị từng toán hạng.

Ví dụ expression:

~~~text
#left + #right > #minimum
~~~

Có thể kiểm tra từng variable:

~~~java
Object left = context.lookupVariable("left");
Object right = context.lookupVariable("right");
Object minimum = context.lookupVariable("minimum");

System.out.println(left == null ? "null" : left.getClass().getName());
System.out.println(right == null ? "null" : right.getClass().getName());
System.out.println(minimum == null ? "null" : minimum.getClass().getName());
~~~

Sau đó evaluate từng phép toán:

~~~java
Object sum = parser.parseExpression("#left + #right")
        .getValue(context);

Boolean aboveMinimum = parser.parseExpression(
        "#left + #right > #minimum")
        .getValue(context, Boolean.class);
~~~

Nếu sum đã sai kiểu hoặc lỗi, vấn đề nằm ở phép cộng hoặc dữ liệu đầu vào. Nếu sum đúng nhưng phép so sánh lỗi, kiểm tra kiểu minimum và cách toán tử relational xử lý hai toán hạng.

Không ghi log dữ liệu nhạy cảm chỉ để xem kiểu. Trong môi trường production, chỉ log tên kiểu, trạng thái null và thông tin đã được phép tiết lộ.

## 15. Kiểm tra ảnh hưởng của ConversionService và TypeConverter

SpEL dùng TypeConverter của EvaluationContext cho các thao tác cần chuyển đổi kiểu, chẳng hạn gán giá trị vào property hoặc chuyển đổi kết quả theo kiểu đích. Context có thể dùng StandardTypeConverter kết nối tới ConversionService mặc định hoặc custom ConversionService.

Khi kết quả khác dự đoán:

- Kiểm tra context nào đang được dùng.
- Kiểm tra TypeConverter của context.
- Kiểm tra ConversionService có custom converter hay không.
- Kiểm tra kiểu nguồn và kiểu đích thực tế.
- Kiểm thử riêng trường hợp có và không có converter.

Đừng giả định mọi toán tử đều chuyển đổi mọi kiểu đầu vào theo cùng một cách. Việc một String có thể chuyển thành Integer ở property binding không có nghĩa mọi phép toán trên String sẽ tự động mang ý nghĩa số học.

Nếu cần phép tính số, chuẩn hóa dữ liệu thành kiểu số rõ ràng trước khi thực hiện. Nếu cần so sánh chuỗi, giữ dữ liệu ở kiểu String và dùng phép toán văn bản tương ứng.

## 16. OperatorOverloader có thể thay đổi cách toán tử hoạt động

SpEL cho phép cấu hình OperatorOverloader để định nghĩa hành vi toán tử cho các kiểu miền nghiệp vụ. StandardOperatorOverloader cung cấp hành vi mặc định; một context có thể được gắn custom overloader.

Ví dụ một ứng dụng có kiểu Distance và muốn dùng toán tử cộng cho hai khoảng cách:

~~~java
public class Distance {
    private final BigDecimal meters;

    public Distance(BigDecimal meters) {
        this.meters = meters;
    }

    public BigDecimal getMeters() {
        return meters;
    }
}
~~~

Custom OperatorOverloader có thể nhận diện cặp Distance và Distance cho toán tử ADD rồi trả về Distance mới. Đây là phần mở rộng có chủ đích; không nên giả định SpEL mặc định hiểu phép cộng cho mọi class tùy chỉnh.

Khi debug một expression dùng toán tử trên object miền nghiệp vụ, kiểm tra OperatorOverloader của EvaluationContext. Cùng một source có thể có hành vi khác nếu ứng dụng gắn overloader khác nhau.

Chỉ overload những phép toán có ý nghĩa tự nhiên và nhất quán. Nếu quy tắc phức tạp hoặc có side effect, method Java có tên thường dễ hiểu và dễ kiểm thử hơn toán tử tùy chỉnh.

## 17. Kiểm thử nhiều runtime type với JUnit 5

Parameterized test giúp xác nhận expression xử lý đúng các kiểu có thể xuất hiện:

~~~java
@ParameterizedTest
@MethodSource("values")
void identifiesRuntimeType(Object value, boolean expectedNumber) {
    StandardEvaluationContext context =
            new StandardEvaluationContext();
    context.setVariable("value", value);

    Expression expression = new SpelExpressionParser()
            .parseExpression("#value instanceof T(java.lang.Number)");

    Boolean actual = expression.getValue(context, Boolean.class);

    assertEquals(expectedNumber, actual);
}

static Stream<Arguments> values() {
    return Stream.of(
            Arguments.of(Integer.valueOf(10), true),
            Arguments.of(new BigDecimal("10.50"), true),
            Arguments.of("10", false),
            Arguments.of(Boolean.TRUE, false),
            Arguments.of((Object) null, false));
}
~~~

Test này kiểm tra kiểu runtime mà không chuyển đổi dữ liệu. Có thể bổ sung test riêng cho String, Collection, Map, enum và các class miền nghiệp vụ mà expression thực sự nhận.

Nếu expression thực hiện phép toán, hãy kiểm tra cả kết quả đúng lẫn kiểu đầu vào không hợp lệ. Không chỉ test một trường hợp thành công vì dữ liệu production có thể chứa kiểu khác.

## 18. Kiểm thử nhánh toán tử bằng biểu thức điều kiện

Toán tử ba ngôi có thể chọn phép toán dựa trên runtime type:

~~~java
Expression expression = parser.parseExpression(
        "#value instanceof T(java.lang.Number) "
        + "? #value + 10 "
        + ": (#value instanceof T(java.lang.String) "
        + "? #value.toUpperCase() : 'Unsupported')");

StandardEvaluationContext context = new StandardEvaluationContext();
context.setVariable("value", Integer.valueOf(5));

assertEquals(15, expression.getValue(context));

context.setVariable("value", "hello");

assertEquals("HELLO", expression.getValue(context));

context.setVariable("value", Boolean.TRUE);

assertEquals("Unsupported", expression.getValue(context));
~~~

Mỗi nhánh chỉ thực hiện thao tác phù hợp với kiểu đã kiểm tra. Cách này có thể hữu ích với expression ngắn và một số kiểu được hỗ trợ rõ ràng.

Nếu có nhiều nhánh kiểu, logic dài hoặc nhiều quy tắc chuyển đổi, chuyển việc phân loại và xử lý sang Java method có tên rõ ràng. Một expression quá nhiều nhánh sẽ khó đọc và khó kiểm thử hơn code Java thông thường.

## 19. Lỗi thường gặp

**Dùng phép toán số trên String**

Chuỗi chứa chữ số vẫn là String. Kiểm tra kiểu hoặc chuyển đổi rõ ràng trước khi thực hiện phép toán số học.

**Dùng matches trên giá trị không phải String**

matches kiểm tra regular expression trên chuỗi. Xác định kiểu đầu vào trước khi áp dụng.

**Nhầm instanceof với conversion**

instanceof chỉ kiểm tra khả năng tương thích kiểu; nó không parse hoặc chuyển đổi object.

**Bỏ qua null**

Null không có class để đọc property hoặc gọi method. Kiểm tra null hoặc dùng null-safe navigation phù hợp.

**Giả định mọi Number có cùng độ chính xác**

Integer, Double và BigDecimal có đặc điểm số học khác nhau. Với tiền tệ, dùng BigDecimal và quy tắc scale/rounding rõ ràng.

**Dùng == thay cho kiểm tra class**

So sánh giá trị không phải là kiểm tra runtime type. Dùng instanceof khi cần xác nhận kiểu.

**Quên custom operator hoặc converter**

EvaluationContext có thể chứa OperatorOverloader và TypeConverter tùy chỉnh. Kiểm tra context thực tế khi hành vi khác với mặc định.

**Chỉ kiểm thử một kiểu dữ liệu**

Một expression có thể chạy với fixture đầu tiên nhưng thất bại với null, subclass hoặc kiểu khác. Dùng test case bao phủ mọi kiểu được contract cho phép.

**Chỉ xem kiểu đích của getValue**

getValue(context, TargetType.class) có thể chuyển đổi kết quả. Dùng getValue(context) để quan sát kiểu runtime thô trước khi chuyển đổi.

## 20. Quy trình debug trước khi chọn toán tử

Khi expression gặp lỗi hoặc trả về kết quả bất ngờ, thực hiện theo thứ tự:

1. Tách expression thành các toán hạng và xác định giá trị runtime của từng phần.
2. Kiểm tra null trước khi đọc property hoặc gọi method.
3. Dùng instanceof để xác nhận class/interface thực tế cần hỗ trợ.
4. Xác định toán tử phù hợp với kiểu: số học, chuỗi, Boolean, collection, enum hoặc object tùy chỉnh.
5. Kiểm tra có conversion service hoặc operator overloader tùy chỉnh hay không.
6. Evaluate từng phần nhỏ và kiểm tra kiểu kết quả thô.
7. Viết test cho mọi runtime type hợp lệ và các kiểu không được hỗ trợ.
8. Nếu logic phân nhánh trở nên dài, chuyển xử lý sang Java method có tên rõ ràng.

Mục tiêu là để expression chỉ áp dụng toán tử khi dữ liệu thỏa điều kiện kiểu đã xác định. Kiểm tra kiểu ở đúng ranh giới giúp lỗi dễ tìm và ngăn một giá trị có hình thức giống kiểu mong đợi bị xử lý sai.

## 21. Ghi nhớ

- Kiểu runtime có thể khác kiểu khai báo, đặc biệt với property Object, interface và dữ liệu động.
- Dùng instanceof T(Type) để kiểm tra class hoặc interface thực tế.
- instanceof không chuyển đổi giá trị; String "42" vẫn là String.
- Kiểm tra null trước khi truy cập property hoặc gọi method trên object có thể null.
- Chọn toán tử theo kiểu: số học cho Number, matches cho String, logic cho Boolean, selection cho collection và constant đúng kiểu cho enum.
- Toán tử + có thể cộng số hoặc nối chuỗi tùy kiểu toán hạng; không dựa vào giả định khi kiểu đầu vào thay đổi.
- getValue(context) cho biết kết quả thô; getValue(context, TargetType.class) có thể áp dụng TypeConverter.
- Kiểm tra TypeConverter, ConversionService và OperatorOverloader nếu context được tùy chỉnh.
- Kiểm thử nhiều kiểu runtime, null và kiểu không được hỗ trợ.
- Giữ expression ngắn; chuyển logic phân nhánh nhiều kiểu sang Java khi dễ đọc và bảo trì hơn.
