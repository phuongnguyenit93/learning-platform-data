# Toán tử instanceof kết hợp với type reference

Trong SpEL, toán tử instanceof kiểm tra kiểu runtime của một giá trị. Vế trái là object cần kiểm tra; vế phải thường là một type reference được viết bằng cú pháp T(...). Kết quả là Boolean: true nếu object tương thích với kiểu được chỉ định, false nếu không.

Kết hợp instanceof với type reference giúp biểu thức phân nhánh theo kiểu dữ liệu mà không phải tự gọi getClass() hoặc so sánh tên class. Cách này hữu ích khi một biến hoặc property có thể chứa nhiều loại object, chẳng hạn một trường Object, một giá trị nhận từ cấu hình hoặc các implementation khác nhau của cùng một interface.

## 1. Cú pháp instanceof và T(...)

Cú pháp tổng quát:

~~~text
value instanceof T(TypeName)
~~~

Trong đó:

- value là object cần kiểm tra, thường là root property hoặc biến context.
- instanceof là toán tử kiểm tra kiểu.
- T(TypeName) là type reference, biểu diễn một đối tượng Class mà SpEL phân giải được.

Ví dụ:

~~~text
#value instanceof T(String)
#value instanceof T(java.lang.Number)
#value instanceof T(java.time.LocalDate)
~~~

Biểu thức đầu kiểm tra value có phải String hay không. Biểu thức thứ hai kiểm tra object có thuộc Number hoặc một lớp con của Number hay không. Biểu thức thứ ba kiểm tra object có phải LocalDate hay không.

Ví dụ Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("value", "Spring");

Expression expression = parser.parseExpression(
        "#value instanceof T(String)"
);

Boolean result = expression.getValue(context, Boolean.class);

System.out.println(result); // true
~~~

T(...) không phải tên method hay biến. Đây là cú pháp đặc biệt của SpEL để tham chiếu kiểu Java. Toán tử instanceof dùng class được phân giải từ type reference để kiểm tra object ở vế trái.

## 2. Type reference phân giải tên lớp như thế nào?

Type reference dùng cú pháp T(...). Tên lớp có thể là tên đơn giản nếu lớp thuộc package đã được import trong TypeLocator, hoặc tên đầy đủ có package.

StandardEvaluationContext mặc định sử dụng StandardTypeLocator. TypeLocator mặc định có import java.lang, vì vậy có thể viết:

~~~text
T(String)
T(Integer)
T(Number)
T(Boolean)
~~~

Với lớp thuộc package khác, hãy viết tên đầy đủ:

~~~text
T(java.time.LocalDate)
T(java.math.BigDecimal)
T(java.util.UUID)
~~~

Nếu ứng dụng muốn dùng tên ngắn cho một package riêng, có thể đăng ký package import trên StandardTypeLocator:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

StandardTypeLocator typeLocator =
        new StandardTypeLocator();

typeLocator.registerImport("com.example.domain");

context.setTypeLocator(typeLocator);
~~~

Sau khi package được đăng ký, biểu thức có thể tham chiếu kiểu theo tên đơn giản nếu không bị trùng tên với kiểu khác. Trong biểu thức dùng chung hoặc lưu trong cấu hình lâu dài, tên đầy đủ thường dễ nhận diện hơn và giảm sự phụ thuộc vào import ẩn.

Nếu SpEL không phân giải được kiểu trong T(...), lỗi xảy ra khi đánh giá biểu thức. Hãy kiểm tra tên package, tên lớp và TypeLocator mà context đang sử dụng.

## 3. Kiểm tra kiểu runtime, không phải kiểu khai báo của biến

instanceof kiểm tra object thực tế đang được tham chiếu tại thời điểm đánh giá. Nó không chỉ nhìn vào kiểu khai báo của biến Java.

Ví dụ:

~~~java
Object value = "Spring Expression Language";

context.setVariable("value", value);

Boolean isString = parser.parseExpression(
        "#value instanceof T(String)"
).getValue(context, Boolean.class);
~~~

Dù biến Java được khai báo là Object, object thực tế là String nên kết quả là true.

Tương tự, nếu biến được khai báo là Number nhưng đang chứa Integer, phép kiểm tra với Integer vẫn có thể trả về true:

~~~java
Number amount = Integer.valueOf(42);
context.setVariable("amount", amount);

Boolean isInteger = parser.parseExpression(
        "#amount instanceof T(Integer)"
).getValue(context, Boolean.class);
~~~

Điều này quan trọng khi root object hoặc biến có kiểu tổng quát như Object, Number, Serializable hoặc một interface. Hãy suy nghĩ về kiểu runtime mà dữ liệu thực sự mang theo, không chỉ kiểu khai báo trong chữ ký Java.

## 4. Kế thừa và interface

instanceof tuân theo quan hệ tương thích kiểu của Java. Một instance của lớp con cũng được xem là instance của lớp cha và các interface mà nó triển khai.

Ví dụ:

~~~java
Integer value = 42;
context.setVariable("value", value);
~~~

Các biểu thức sau đều trả về true:

~~~text
#value instanceof T(Integer)
#value instanceof T(Number)
#value instanceof T(Comparable)
~~~

Integer là lớp con của Number và triển khai Comparable. Vì vậy, phép kiểm tra với kiểu cha hoặc interface tương ứng vẫn thành công.

Điều này hữu ích khi biểu thức chỉ quan tâm đến một khả năng chung thay vì một implementation cụ thể. Ví dụ, kiểm tra Number cho phép chấp nhận Integer, Long, Double hoặc BigDecimal; kiểm tra một interface có thể chấp nhận nhiều implementation khác nhau.

Hãy ưu tiên kiểm tra interface hoặc lớp cha khi nghiệp vụ cần hành vi chung. Chỉ kiểm tra implementation cụ thể khi sự khác biệt giữa các loại object thực sự quan trọng.

## 5. Phân biệt instanceof với so sánh class chính xác

instanceof kiểm tra tính tương thích kiểu, bao gồm cả lớp con. Nó khác với việc so sánh chính xác class runtime.

Ví dụ:

~~~java
Object value = Integer.valueOf(42);
context.setVariable("value", value);
~~~

Biểu thức:

~~~text
#value instanceof T(Number)
~~~

trả về true vì Integer là một Number.

Nếu cần kiểm tra class chính xác, có thể so sánh kết quả getClass() với type reference:

~~~text
#value.getClass() == T(Integer)
~~~

Biểu thức này chỉ đúng khi class runtime chính xác là Integer. Nếu value là một lớp con khác của Number, phép so sánh class sẽ false dù instanceof Number là true.

Chọn cách kiểm tra theo ý nghĩa nghiệp vụ:

| Nhu cầu | Cách viết |
|---|---|
| Object thuộc kiểu hoặc lớp con tương thích | value instanceof T(Type) |
| Object có class runtime chính xác | value.getClass() == T(Type) |
| Object triển khai một interface | value instanceof T(InterfaceType) |

Không dùng so sánh tên class dạng chuỗi nếu có thể dùng type reference. So sánh Class trực tiếp tránh phụ thuộc vào cách viết tên đầy đủ hoặc tên rút gọn.

## 6. Xử lý null

Một giá trị null không phải instance của bất kỳ kiểu tham chiếu nào, vì vậy phép kiểm tra instanceof với null cho kết quả false.

Ví dụ:

~~~java
context.setVariable("value", null);

Boolean result = parser.parseExpression(
        "#value instanceof T(String)"
).getValue(context, Boolean.class);

System.out.println(result); // false
~~~

Nếu cần phân biệt rõ null với một object không đúng kiểu, có thể viết hai điều kiện:

~~~text
#value == null
#value != null and #value instanceof T(String)
~~~

AND có short-circuit. Nếu #value là null, vế phải không cần được đánh giá.

Thông thường, bản thân instanceof đã trả false khi giá trị null. Tuy nhiên, kiểm tra null tường minh vẫn hữu ích khi biểu thức tiếp tục gọi method hoặc đọc property sau phép kiểm tra kiểu:

~~~text
#value instanceof T(String) and #value.length() > 0
~~~

Nếu value là null hoặc không phải String, vế trái false và phần gọi length() bị bỏ qua. Cách viết này vừa kiểm tra kiểu vừa bảo vệ thao tác chỉ hợp lệ với String.

## 7. Dùng instanceof để chọn nhánh theo kiểu dữ liệu

instanceof có thể kết hợp với AND, OR và các biểu thức logic khác để tạo điều kiện phân loại dữ liệu.

~~~text
#payload instanceof T(String) and #payload.length() > 0
#amount instanceof T(Number) and #amount.doubleValue() > 0
#date instanceof T(java.time.LocalDate)
~~~

Ví dụ, một biến có thể chứa nhiều kiểu dữ liệu:

~~~java
context.setVariable("payload", "HELLO");

Expression expression = parser.parseExpression(
        "#payload instanceof T(String) and #payload.length() >= 5"
);

Boolean accepted = expression.getValue(context, Boolean.class);
~~~

Nếu payload là String, biểu thức mới kiểm tra độ dài. Nếu payload là Integer hoặc null, điều kiện đầu false và vế phải không được thực hiện.

Có thể kết hợp nhiều nhánh:

~~~text
#value instanceof T(String) or #value instanceof T(Number)
~~~

Biểu thức trả true nếu value là String hoặc Number. Với logic phức tạp, hãy dùng ngoặc để thể hiện rõ nhóm điều kiện và tránh nhầm lẫn về thứ tự ưu tiên.

## 8. instanceof với property của root object

Không cần đưa object vào biến riêng nếu nó đã có sẵn trong root object. Có thể kiểm tra trực tiếp property:

~~~text
payload instanceof T(String)
amount instanceof T(java.math.BigDecimal)
metadata instanceof T(java.util.Map)
~~~

Ví dụ:

~~~java
public class Message {

    private Object payload;

    public Object getPayload() {
        return payload;
    }

    public void setPayload(Object payload) {
        this.payload = payload;
    }
}
~~~

Đánh giá:

~~~java
Message message = new Message();
message.setPayload("Hello");

StandardEvaluationContext context =
        new StandardEvaluationContext(message);

Expression expression = parser.parseExpression(
        "payload instanceof T(String)"
);

Boolean isText = expression.getValue(context, Boolean.class);
~~~

SpEL đọc property payload trên root object, sau đó kiểm tra kiểu runtime của giá trị trả về. Nếu payload là một object khác hoặc null, kết quả tương ứng là false.

Nếu property nằm sâu trong object graph, hãy bảo đảm các mắt xích trung gian có thể truy cập. Khi object trung gian có thể null, kiểm tra null trước hoặc dùng một cấu trúc dữ liệu có trạng thái rõ ràng.

## 9. instanceof với các kiểu số

Các kiểu số trong Java có quan hệ kế thừa khác nhau. Integer, Long, Double và BigDecimal đều có thể được kiểm tra bằng Number, nhưng chúng không phải cùng một class.

~~~text
#value instanceof T(Number)
#value instanceof T(Integer)
#value instanceof T(Long)
#value instanceof T(Double)
#value instanceof T(java.math.BigDecimal)
~~~

Ví dụ:

~~~java
context.setVariable("value", new BigDecimal("19.90"));

Boolean isNumber = parser.parseExpression(
        "#value instanceof T(Number)"
).getValue(context, Boolean.class);

Boolean isDecimal = parser.parseExpression(
        "#value instanceof T(java.math.BigDecimal)"
).getValue(context, Boolean.class);
~~~

Cả hai kết quả đều true vì BigDecimal là một lớp con của Number.

Nếu biểu thức chỉ cần biết giá trị có phải kiểu số hay không, kiểm tra Number thường linh hoạt hơn. Nếu cần hành vi riêng của BigDecimal như scale hoặc phép tính decimal, hãy kiểm tra BigDecimal cụ thể hoặc thiết kế method phù hợp.

Đừng nhầm chuyển đổi kiểu với instanceof. Một chuỗi "42" có thể chuyển đổi thành số trong một phép gán hoặc lời gọi method nếu converter hỗ trợ, nhưng bản thân chuỗi đó không phải instance của Number.

## 10. Giới hạn với generic type

instanceof kiểm tra class runtime, không kiểm tra đầy đủ tham số generic của Java. Do type erasure, các kiểu như List<String> và List<Integer> đều có cùng class runtime là List.

Ví dụ:

~~~java
List<String> names = List.of("Lan", "Minh");
context.setVariable("value", names);
~~~

Biểu thức:

~~~text
#value instanceof T(java.util.List)
~~~

trả true. Nhưng SpEL không thể dùng type reference thông thường để phân biệt trực tiếp List<String> với List<Integer> bằng phép instanceof.

Nếu cần kiểm tra kiểu phần tử, hãy kiểm tra từng phần tử hoặc chuẩn hóa dữ liệu ở Java:

~~~text
#value instanceof T(java.util.List)
~~~

Sau đó, ứng dụng có thể lặp qua List và kiểm tra kiểu từng phần tử bằng Java, hoặc cung cấp một method thuần có tên rõ ràng để xác nhận hợp đồng dữ liệu.

Không nên giả định rằng một List đã vượt qua instanceof List thì mọi phần tử bên trong đều có kiểu mà nghiệp vụ mong đợi. Kiểu collection và kiểu phần tử là hai điều cần kiểm soát riêng.

## 11. TypeLocator và phạm vi kiểu được phép tham chiếu

Type reference cần TypeLocator để phân giải tên lớp. StandardEvaluationContext thường dùng StandardTypeLocator, cho phép phân giải nhiều kiểu theo tên đầy đủ và các package import.

Nếu ứng dụng đánh giá biểu thức do người dùng cung cấp, khả năng tham chiếu kiểu cần được cân nhắc như một quyền truy cập. Không nên cho phép biểu thức tự do tham chiếu mọi class trên classpath nếu use case chỉ cần kiểm tra một số kiểu domain đã biết.

Có thể tạo TypeLocator tùy chỉnh để giới hạn tập kiểu được phân giải, hoặc chỉ đưa các object và khả năng cần thiết vào context. Hãy kiểm soát cả MethodResolver, PropertyAccessor, BeanResolver và các khả năng khác nếu biểu thức không đáng tin cậy.

SimpleEvaluationContext được thiết kế cho tập tính năng SpEL hạn chế và không cung cấp type reference như StandardEvaluationContext. Nếu biểu thức cần T(...), hãy xác nhận implementation/context được dùng hỗ trợ khả năng đó; không nên chuyển sang context đầy đủ rộng quyền chỉ để giải quyết một phép kiểm tra kiểu đơn giản.

## 12. Primitive và wrapper types

instanceof là phép kiểm tra object runtime. Trong Java, primitive như int, long hoặc boolean không phải object và không thể đứng trực tiếp ở vế trái của instanceof.

Khi làm việc với giá trị trong SpEL, hãy nhớ rằng dữ liệu được đánh giá như object và primitive Java thường được boxing thành wrapper tương ứng, chẳng hạn int thành Integer khi truyền qua API generic hoặc context.

Vì vậy, các type reference thường dùng trong kiểm tra instanceof là kiểu tham chiếu:

~~~text
#value instanceof T(Integer)
#value instanceof T(Boolean)
#value instanceof T(Double)
~~~

Không dùng T(int) như một cách thay thế cho T(Integer) trong phép kiểm tra object. Nếu cần kiểm tra kiểu dữ liệu mà context đang giữ, hãy kiểm tra wrapper class thực tế.

## 13. Kiểm tra mảng và kiểu container

Mảng trong Java là object, vì vậy một giá trị array có thể được kiểm tra với các kiểu cha hoặc interface mà array triển khai, ví dụ Object hoặc Cloneable. Tuy nhiên, việc kiểm tra array có component type cụ thể cần chú ý tới cách biểu diễn type reference và kiểu runtime thực tế.

Nếu biểu thức cần phân biệt một array cụ thể, hãy cân nhắc cung cấp một method kiểm tra có kiểu rõ ràng trong Java thay vì làm cú pháp type reference trở nên khó đọc. Tương tự, instanceof List chỉ xác nhận object là một List; nó không chứng minh collection có thứ tự nghiệp vụ mong muốn, không null và không có phần tử sai kiểu.

Đối với Map, Set và các collection khác, hãy kiểm tra interface phù hợp với yêu cầu. Ví dụ, instanceof Map xác nhận kiểu container; các quy tắc về key/value vẫn cần được kiểm tra riêng.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không phân giải được T(...) | Tên lớp sai hoặc TypeLocator không tìm thấy kiểu | Dùng tên đầy đủ hoặc cấu hình import phù hợp |
| instanceof trả false ngoài dự kiến | Object runtime khác kiểu được kiểm tra | Kiểm tra class thực tế của giá trị |
| Lớp con không được nhận diện | Đang so sánh class chính xác thay vì instanceof | Dùng instanceof khi chấp nhận kiểu con |
| Null làm điều kiện false | null không phải instance của kiểu tham chiếu | Xử lý null theo ý nghĩa nghiệp vụ |
| Muốn kiểm tra List<String> nhưng chỉ xác nhận được List | Generic type bị type erasure | Kiểm tra từng phần tử hoặc validate dữ liệu trong Java |
| Tên ngắn hoạt động ở môi trường này nhưng lỗi ở môi trường khác | Import của TypeLocator khác nhau | Dùng tên package đầy đủ hoặc cấu hình import tường minh |
| SimpleEvaluationContext không hỗ trợ type reference | Context giới hạn tính năng | Dùng context phù hợp hoặc chuyển kiểm tra kiểu sang Java |
| Chuỗi số bị coi là Number | Nhầm chuyển đổi với quan hệ kiểu runtime | Chuyển đổi dữ liệu trước rồi mới kiểm tra instanceof |

## 15. Ghi nhớ

Dùng cú pháp value instanceof T(Type) để kiểm tra kiểu runtime của object. T(...) là type reference do TypeLocator phân giải; StandardTypeLocator mặc định có import java.lang nên có thể dùng các tên như String, Integer hoặc Number, còn kiểu ở package khác nên viết đầy đủ.

instanceof chấp nhận lớp con và interface mà object triển khai, trong khi so sánh getClass() chỉ kiểm tra class chính xác. null luôn cho kết quả false. Generic type không được kiểm tra đầy đủ do type erasure, và primitive nên được kiểm tra thông qua wrapper object tương ứng.

Hãy dùng instanceof khi biểu thức cần phân nhánh theo kiểu thực tế, kết hợp short-circuit để bảo vệ các thao tác phụ thuộc kiểu, và giới hạn TypeLocator/context khi biểu thức đến từ nguồn không đáng tin cậy.