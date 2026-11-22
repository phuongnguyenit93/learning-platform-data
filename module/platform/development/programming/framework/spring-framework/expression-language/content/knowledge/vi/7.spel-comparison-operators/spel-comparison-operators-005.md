# Phân biệt so sánh giá trị với so sánh identity

Khi dùng Spring Expression Language (SpEL), toán tử **==** thường được đọc là “bằng”. Tuy nhiên, cần xác định “bằng” theo quy tắc nào. Trong Java, toán tử **==** trên hai reference kiểm tra chúng có trỏ đến cùng một object hay không (reference identity). Còn phép so sánh bằng trong SpEL dùng quy tắc equality của SpEL; với object thông thường, việc so sánh dựa trên **equals()**. Hai cách kiểm tra này có thể cho kết quả khác nhau.

Phân biệt rõ hai khái niệm giúp tránh lỗi khi viết điều kiện phân quyền, lọc dữ liệu, cache key, event condition hoặc các expression khác có chứa object.

## 1. Value equality và reference identity là gì?

### Value equality — hai object có giá trị được xem là bằng nhau

Value equality trả lời câu hỏi: hai giá trị có đại diện cho cùng nội dung hoặc trạng thái theo định nghĩa của kiểu dữ liệu hay không?

Ví dụ, hai đối tượng String được tạo riêng biệt nhưng cùng chứa nội dung spring:

~~~java
String first = new String("spring");
String second = new String("spring");

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false
~~~

equals() trả về true vì hai chuỗi có cùng nội dung. Toán tử Java == trả về false vì hai biến tham chiếu đến hai object khác nhau.

### Reference identity — hai reference có trỏ đến cùng object hay không?

Reference identity trả lời câu hỏi: hai biến có cùng trỏ đến đúng một object trong bộ nhớ hay không?

~~~java
String first = new String("spring");
String alias = first;

System.out.println(first.equals(alias)); // true
System.out.println(first == alias);      // true
~~~

Ở đây cả hai phép so sánh đều trả về true, vì hai reference trỏ đến cùng object và object đó cũng bằng chính nó theo equals().

Có thể nhớ ngắn gọn:

- **Value equality:** so sánh theo quy tắc bằng nhau của kiểu dữ liệu.
- **Reference identity:** so sánh hai reference có cùng trỏ đến một object hay không.

## 2. Toán tử == và != trong SpEL

Trong SpEL, **==** và **!=** là toán tử equality và inequality. Với các object thông thường, SpEL kiểm tra equality theo quy tắc equals() của object; đây không phải phép kiểm tra reference identity như toán tử Java ==.

Ví dụ:

~~~java
String first = new String("spring");
String second = new String("spring");

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("first", first);
context.setVariable("second", second);

ExpressionParser parser = new SpelExpressionParser();

Boolean equal = parser
        .parseExpression("#first == #second")
        .getValue(context, Boolean.class);

Boolean notEqual = parser
        .parseExpression("#first != #second")
        .getValue(context, Boolean.class);

System.out.println(equal);    // true
System.out.println(notEqual); // false
~~~

Mặc dù first và second là hai object khác nhau, expression **#first == #second** trả về true vì hai chuỗi bằng nhau theo nội dung.

| Biểu thức | Ý nghĩa | Kết quả với hai String khác object nhưng cùng nội dung |
| --- | --- | --- |
| Java **first == second** | Reference identity | false |
| Java **first.equals(second)** | Value equality | true |
| SpEL **#first == #second** | Equality theo quy tắc SpEL | true |
| SpEL **#first != #second** | Phủ định của equality | false |

Vì vậy, khi đọc expression, không nên tự động mang ý nghĩa của toán tử Java == sang SpEL.

## 3. Kết quả phụ thuộc vào cách kiểu dữ liệu định nghĩa equals()

SpEL sử dụng equality của object, nên kết quả phụ thuộc vào implementation equals() của lớp đó.

### 3.1. Kiểu có equals() so sánh nội dung

Các kiểu như String, BigInteger, BigDecimal và nhiều kiểu value object triển khai equals() để so sánh giá trị theo hợp đồng riêng của kiểu.

~~~java
String a = new String("order-100");
String b = new String("order-100");
~~~

Expression **#a == #b** trả về true đối với hai chuỗi này, dù chúng là hai reference khác nhau.

Với domain object, có thể chủ động định nghĩa equality theo các trường có ý nghĩa nghiệp vụ:

~~~java
public final class CustomerKey {

    private final String value;

    public CustomerKey(String value) {
        this.value = value;
    }

    @Override
    public boolean equals(Object other) {
        if (this == other) {
            return true;
        }
        if (!(other instanceof CustomerKey that)) {
            return false;
        }
        return Objects.equals(this.value, that.value);
    }

    @Override
    public int hashCode() {
        return Objects.hash(value);
    }
}
~~~

Hai CustomerKey riêng biệt nhưng có cùng value sẽ được xem là bằng nhau theo quy tắc của lớp:

~~~java
context.setVariable("left", new CustomerKey("CUS-001"));
context.setVariable("right", new CustomerKey("CUS-001"));
~~~

Expression **#left == #right** trả về true vì equals() đã được định nghĩa để so sánh mã khách hàng.

### 3.2. Kiểu không override equals()

Nếu một lớp không override equals(), implementation kế thừa từ Object.equals() so sánh identity của reference. Khi đó, hai instance riêng biệt thường không bằng nhau, kể cả khi các field của chúng giống hệt nhau.

~~~java
class Point {
    int x;
    int y;
}

Point p1 = new Point();
p1.x = 10;
p1.y = 20;

Point p2 = new Point();
p2.x = 10;
p2.y = 20;
~~~

Với hai object này, expression **#p1 == #p2** trả về false vì Point chưa định nghĩa equality theo giá trị. Đây là trường hợp kết quả của SpEL equality trùng với kết quả identity, nhưng nguyên nhân là implementation equals() mặc định của Java.

Nếu muốn hai điểm bằng nhau theo tọa độ, cần triển khai equals() và hashCode() phù hợp, hoặc dùng một kiểu dữ liệu đã định nghĩa value equality, chẳng hạn Java record:

~~~java
record Point(int x, int y) {}

Point p1 = new Point(10, 20);
Point p2 = new Point(10, 20);
~~~

Record tự sinh equals() và hashCode() dựa trên các component. Hai instance trên vì vậy được xem là bằng nhau theo giá trị, dù vẫn là hai object riêng biệt.

## 4. SpEL không cung cấp toán tử identity riêng

SpEL không có toán tử **===** tương đương một số ngôn ngữ khác để kiểm tra hai reference có cùng trỏ đến một object hay không. Không nên dùng **==** với mục đích identity khi đang viết SpEL.

Nếu nghiệp vụ thực sự cần kiểm tra identity, hãy đưa phép so sánh Java reference vào một method rõ ràng rồi gọi method đó từ expression.

Ví dụ helper:

~~~java
public class ReferenceCheck {

    public boolean same(Object left, Object right) {
        return left == right;
    }
}
~~~

Có thể đăng ký helper như một bean Spring rồi tham chiếu bean trong expression nếu EvaluationContext có BeanResolver:

~~~text
@referenceCheck.same(#left, #right)
~~~

Cú pháp bean reference yêu cầu context được kết nối với Spring BeanFactory. Nếu đang tự tạo StandardEvaluationContext độc lập, có thể đăng ký helper thành biến context rồi gọi method qua biến đó:

~~~java
context.setVariable("referenceCheck", new ReferenceCheck());

Boolean sameReference = parser
        .parseExpression("#referenceCheck.same(#left, #right)")
        .getValue(context, Boolean.class);
~~~

Expression trên thực hiện phép == của Java bên trong method same(), vì vậy kết quả phản ánh reference identity.

Không nên dùng System.identityHashCode() để thay thế phép so sánh reference. Hash code identity có thể trùng nhau giữa hai object khác nhau, nên so sánh hash code không chứng minh được hai reference có cùng identity.

## 5. Những điểm cần chú ý khi equality có nhiều kiểu dữ liệu

### 5.1. SpEL có thể thực hiện chuyển đổi kiểu khi so sánh

Khi hai toán hạng không cùng kiểu, SpEL có thể sử dụng cơ chế type conversion của nó để đưa toán hạng về kiểu phù hợp trước khi kiểm tra equality. Vì vậy, không nên giả định rằng mọi phép so sánh đều tương đương lời gọi Java equals() giữa hai biến giữ nguyên kiểu ban đầu.

Với các giá trị số thuộc các kiểu số khác nhau, SpEL xử lý theo quy tắc so sánh và chuyển đổi số của expression engine. Nếu logic nghiệp vụ phụ thuộc vào kiểu dữ liệu hoặc cách biểu diễn chính xác, hãy chuẩn hóa kiểu trước khi so sánh hoặc gọi một method Java có hợp đồng rõ ràng.

### 5.2. BigDecimal và scale

Trong Java, BigDecimal.equals() xét cả giá trị số và scale:

~~~java
BigDecimal a = new BigDecimal("10.0");
BigDecimal b = new BigDecimal("10.00");

System.out.println(a.equals(b));    // false
System.out.println(a.compareTo(b)); // 0
~~~

equals() phân biệt 10.0 với 10.00, trong khi compareTo() xem chúng có cùng giá trị số.

Nếu nghiệp vụ muốn so sánh giá trị tiền hoặc số thập phân theo trị số, hãy biểu đạt rõ ý định bằng cách chuẩn hóa scale hoặc gọi compareTo() trong một helper:

~~~text
#left.compareTo(#right) == 0
~~~

Cách này phù hợp khi hai toán hạng là BigDecimal và không null. Nếu có thể null, cần kiểm tra null trước hoặc đưa phép so sánh vào method Java có xử lý null.

### 5.3. Null

SpEL hỗ trợ so sánh với null:

~~~text
#left == null
#left != null
#left == #right
~~~

Hai vế cùng null được xem là bằng nhau; một vế null và vế còn lại khác null thì không bằng nhau. Khi cần gọi method như equals() hoặc compareTo(), phải bảo đảm đối tượng nhận lời gọi không null, hoặc dùng safe navigation phù hợp.

Ví dụ:

~~~text
#left != null and #left.equals(#right)
~~~

Điều kiện này kiểm tra left khác null trước khi gọi equals().

### 5.4. Collection và Map

Nhiều collection và map trong Java định nghĩa equals() theo nội dung. Do đó, hai collection riêng biệt có cùng phần tử theo thứ tự và quy tắc equality tương ứng có thể được SpEL xem là bằng nhau.

~~~java
context.setVariable("a", List.of("A", "B"));
context.setVariable("b", List.of("A", "B"));
~~~

Expression **#a == #b** trả về true vì List.equals() so sánh các phần tử theo thứ tự. Đổi thứ tự phần tử thành ["B", "A"] sẽ làm kết quả thành false.

Đừng nhầm việc hai collection bằng nhau theo nội dung với việc chúng là cùng một instance. Nếu cần identity, dùng helper Java như phần trước.

## 6. Chọn phép so sánh phù hợp với mục đích

| Nhu cầu | Cách dùng | Lý do |
| --- | --- | --- |
| So sánh nội dung chuỗi | **#name == 'admin'** | String equality theo nội dung |
| So sánh value object | **#left == #right** | Dùng equality do lớp định nghĩa |
| Kiểm tra khác nhau theo equality | **#left != #right** | Phủ định của equality |
| Kiểm tra object null | **#value == null** | So sánh với null |
| So sánh số thập phân theo trị số | **#left.compareTo(#right) == 0** | Diễn đạt rõ quy tắc BigDecimal |
| Kiểm tra cùng một instance | **@referenceCheck.same(#left, #right)** | Helper dùng Java reference == |
| So sánh collection theo nội dung | **#listA == #listB** | Dựa trên equals() của collection |

Nên chọn phép so sánh theo ý nghĩa nghiệp vụ:

- Nếu quan tâm mã định danh, tên, trạng thái hoặc nội dung, hãy dùng value equality với kiểu dữ liệu có equals() đúng.
- Nếu quan tâm một object cụ thể đã được chia sẻ hoặc truyền qua nhiều thành phần, hãy dùng reference identity qua method Java.
- Nếu kiểu dữ liệu có quy tắc so sánh đặc biệt, chẳng hạn BigDecimal, hãy viết rõ quy tắc thay vì dựa vào giả định về toán tử.

## 7. Áp dụng trong annotation của Spring

SpEL thường xuất hiện trong annotation, ví dụ điều kiện cache hoặc method security. Cần nhớ rằng các annotation này nhận expression theo context riêng, nhưng quy tắc equality của SpEL vẫn cần được hiểu đúng.

### Cache

~~~java
@Cacheable(
    cacheNames = "customer",
    key = "#customerKey",
    condition = "#customerKey != null"
)
public Customer find(CustomerKey customerKey) {
    // ...
}
~~~

Điều kiện trên chỉ kiểm tra customerKey khác null. Nếu dùng equality để so sánh một CustomerKey với key khác, kết quả phụ thuộc vào equals() của CustomerKey.

### Method Security

~~~java
@PreAuthorize("#requestedTenant == authentication.principal.tenantId")
public Invoice findInvoice(String requestedTenant) {
    // ...
}
~~~

Trong ví dụ, expression so sánh hai giá trị tenant theo equality của SpEL. Đây là kiểm tra nội dung/giá trị tenant, không phải yêu cầu hai object String phải là cùng instance.

Nếu cần chính sách phức tạp hơn, nên gọi một bean kiểm tra quyền có tên rõ ràng thay vì nhồi logic vào expression. Điều này cũng giúp việc review bảo mật dễ dàng hơn.

## 8. Các lỗi hiểu nhầm thường gặp

1. **Cho rằng SpEL == luôn giống Java ==:** sai với object có equals() override để so sánh nội dung.
2. **Cho rằng hai object có field giống nhau thì tự động bằng nhau:** chỉ đúng khi lớp định nghĩa equals() theo các field đó.
3. **Dùng != để kiểm tra object khác instance:** != là inequality theo quy tắc SpEL, không phải phép kiểm tra identity.
4. **Dùng identity hash code để chứng minh cùng object:** hash code có thể va chạm.
5. **Quên null khi gọi equals() hoặc compareTo():** method call trên receiver null có thể gây lỗi đánh giá.
6. **Bỏ qua chuyển đổi kiểu:** các toán hạng khác kiểu có thể được SpEL chuyển đổi trước khi so sánh.
7. **Dùng equality mặc định cho domain object mà chưa định nghĩa hợp đồng:** cần xác định rõ equality dựa trên ID, toàn bộ trạng thái hay một business key.

## 9. Ghi nhớ nhanh

- Value equality trả lời hai giá trị có được xem là bằng nhau theo hợp đồng của kiểu hay không.
- Reference identity trả lời hai reference có trỏ đến cùng một object hay không.
- SpEL **==** và **!=** là toán tử equality/inequality; với object thông thường, chúng dựa trên equals().
- Nếu lớp không override equals(), Object.equals() mặc định so sánh identity.
- Java == trên reference kiểm tra identity; không chuyển ý nghĩa đó sang SpEL.
- SpEL không có toán tử === chuyên biệt cho reference identity.
- Khi thật sự cần identity, gọi helper Java thực hiện left == right.
- Với BigDecimal, phân biệt equals() và compareTo() vì scale có thể làm kết quả khác nhau.
- Luôn xét null, type conversion và hợp đồng equality của kiểu dữ liệu trước khi viết expression.

## 10. Tài liệu tham khảo chính thức

- [Spring Expression Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions.html)
- [Spring Framework — Operators in SpEL](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/operators.html)
- [Spring Framework — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Java Object.equals() Contract](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Object.html#equals(java.lang.Object))
- [Java BigDecimal API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
