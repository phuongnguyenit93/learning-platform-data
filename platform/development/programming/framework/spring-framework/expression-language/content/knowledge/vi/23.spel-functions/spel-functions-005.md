# Quản lý vòng đời và khả năng thay đổi của biến trong SpEL

Biến trong Spring Expression Language (SpEL) là dữ liệu được đăng ký trong EvaluationContext và được tham chiếu trong biểu thức bằng tiền tố #. Biến giúp tách dữ liệu runtime khỏi chuỗi expression: cùng một biểu thức có thể được đánh giá nhiều lần với các giá trị khác nhau mà không cần parse lại cú pháp.

Để quản lý biến đúng cách, cần hiểu biến thuộc về context nào, tồn tại trong bao lâu, cách thay thế giá trị, và điều gì xảy ra khi biến tham chiếu tới một object mutable. SpEL không tự gắn vòng đời của biến với request, session hay bean scope. Vòng đời thực tế phụ thuộc vào cách ứng dụng tạo, chia sẻ và giải phóng EvaluationContext.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Khai báo, đọc và cập nhật biến bằng API của EvaluationContext.
- Phân biệt biến với root object, property và bean reference.
- Giải thích vì sao vòng đời biến gắn với vòng đời của EvaluationContext.
- Tái sử dụng Expression với nhiều context độc lập.
- Phân biệt thay thế object reference với thay đổi trạng thái object được tham chiếu.
- Xử lý biến không được cung cấp, giá trị null và kiểu dữ liệu không tương thích.
- Hiểu phép gán biến trong SpEL và tác động lên context.
- Tránh chia sẻ context mutable giữa các request hoặc luồng không liên quan.
- Thiết kế kiểm thử cho vòng đời, giá trị và khả năng thay đổi của biến.

Bạn nên biết cách tạo SpelExpressionParser, Expression và EvaluationContext, cùng với Java object, collection và các kiểu dữ liệu cơ bản.

## 2. Khai báo và đọc biến

Biến được đăng ký trong EvaluationContext. Khi tham chiếu trong SpEL, tên biến có tiền tố #.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customerName", "An");

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("#customerName");

String name = expression.getValue(context, String.class);
~~~

Kết quả là An.

Tên truyền vào setVariable không có ký tự #; ký tự này chỉ xuất hiện trong expression. Ví dụ, setVariable("customerName", value) tương ứng với #customerName.

Biến có thể chứa nhiều loại object:

- String, Number và Boolean.
- DTO hoặc domain object.
- List, Set và Map.
- Object do ứng dụng tạo để phục vụ một lần đánh giá.
- Các giá trị có cấu trúc phức tạp, miễn là EvaluationContext và accessor có thể truy cập chúng.

SpEL không yêu cầu mọi biến phải là chuỗi. Kiểu runtime của giá trị ảnh hưởng tới property access, method invocation, phép toán và kiểu kết quả.

## 3. Vòng đời của biến gắn với EvaluationContext

Biến được lưu trong context mà ứng dụng đã đăng ký nó. Vì vậy, thời gian tồn tại của biến phụ thuộc vào thời gian tồn tại và cách sử dụng context đó.

~~~java
StandardEvaluationContext requestA =
    new StandardEvaluationContext();

requestA.setVariable("userId", 101);

StandardEvaluationContext requestB =
    new StandardEvaluationContext();
~~~

Biến userId được đăng ký trong requestA không tự xuất hiện trong requestB. Hai context có vùng biến riêng.

Có thể hình dung:

~~~text
requestA
  variables:
    userId -> 101

requestB
  variables:
    (chưa đăng ký userId)
~~~

Expression chứa cấu trúc đã parse. Giá trị biến được tra cứu trong context được truyền vào khi evaluate. Do đó, cùng một Expression có thể được tái sử dụng với nhiều context:

~~~java
Expression expression =
    parser.parseExpression("#userId");

StandardEvaluationContext contextA =
    new StandardEvaluationContext();
contextA.setVariable("userId", 101);

StandardEvaluationContext contextB =
    new StandardEvaluationContext();
contextB.setVariable("userId", 202);

Integer first = expression.getValue(contextA, Integer.class);
Integer second = expression.getValue(contextB, Integer.class);
~~~

Kết quả lần lượt là 101 và 202.

### 3.1. Biến không có scope tự động như request hoặc session

SpEL không tự hiểu một biến là request-scoped, session-scoped hay application-scoped. Context được tạo ở đâu và giữ lại bao lâu là quyết định của ứng dụng.

Ví dụ:

- Tạo context cho mỗi lần xử lý request: biến thường chỉ được dùng trong lần xử lý đó.
- Tạo context trong một tác vụ batch: biến có thể sống trong suốt tác vụ.
- Giữ context trong một object singleton: biến có thể tồn tại lâu hơn dự kiến nếu không được quản lý.
- Tạo context riêng cho từng tenant: dữ liệu biến được tách theo context, miễn là object bên trong cũng không bị chia sẻ ngoài ý muốn.

Không suy ra scope từ tên biến. Hãy xác định nơi tạo context, nơi đăng ký biến, nơi evaluate và thời điểm context được giải phóng.

## 4. Thay thế giá trị giữa các lần đánh giá

Có thể gọi setVariable nhiều lần với cùng tên. Giá trị mới thay thế giá trị hiện tại của tên đó trong context:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("threshold", 100);

Expression expression =
    parser.parseExpression("#amount >= #threshold");

context.setVariable("amount", 120);
Boolean first = expression.getValue(context, Boolean.class);

context.setVariable("threshold", 150);
Boolean second = expression.getValue(context, Boolean.class);
~~~

Lần đầu kết quả là true; lần sau là false.

Expression không cần parse lại chỉ vì giá trị biến thay đổi. Khi evaluate, SpEL đọc giá trị hiện tại từ context.

Cách này hữu ích khi quy tắc biểu thức ổn định nhưng dữ liệu thay đổi. Tuy nhiên, nếu thay đổi kiểu của biến giữa các lần đánh giá, expression có thể cho kết quả khác hoặc phát sinh lỗi do kiểu toán hạng không còn tương thích.

### 4.1. Thay thế reference khác với sửa object đang được tham chiếu

Giả sử biến customer chứa một object:

~~~java
Customer customer = new Customer();
customer.setName("An");

context.setVariable("customer", customer);
~~~

Có hai loại thay đổi khác nhau:

1. Gọi setVariable("customer", anotherCustomer) thay thế object được tham chiếu bởi tên biến customer.
2. Gọi customer.setName("Binh") thay đổi trạng thái của object hiện đang được biến tham chiếu.

Trong trường hợp thứ hai, biến vẫn tham chiếu cùng object; nội dung object đã thay đổi. Lần evaluate tiếp theo có thể nhìn thấy giá trị mới vì expression đọc object hiện tại.

Biến không tạo bản sao sâu của object được gán vào nó. Nếu object mutable còn được giữ bởi một thành phần khác, thay đổi object có thể được nhìn thấy ở nhiều nơi.

## 5. Biến chưa được cung cấp và giá trị null

Cần phân biệt dữ liệu không được cung cấp với một thuộc tính có giá trị null.

Trong StandardEvaluationContext, setVariable(name, null) được dùng để loại bỏ tên biến khỏi vùng biến. Vì vậy, nếu ứng dụng cần biểu diễn một đầu vào có giá trị null, hãy đặt nó trong một DTO hoặc wrapper có property mang giá trị null rồi truyền object đó vào context.

Ví dụ:

~~~java
public class Input {
    private String nickname;

    public String getNickname() {
        return nickname;
    }

    public void setNickname(String nickname) {
        this.nickname = nickname;
    }
}

Input input = new Input();
input.setNickname(null);

context.setVariable("input", input);
~~~

Expression có thể đọc:

~~~text
#input.nickname
~~~

Kết quả property là null. Cách này giữ được sự khác biệt giữa object đầu vào đã được cung cấp nhưng một field null và tên biến không có trong context.

Có thể dùng lookupVariable để đọc giá trị hiện tại:

~~~java
Object value = context.lookupVariable("input");
~~~

Nếu cần phân biệt rõ tên chưa được đăng ký với một giá trị nghiệp vụ không có, hãy quản lý schema hoặc tập tên đầu vào ở tầng Java. Không dựa vào một giá trị null duy nhất để diễn giải trạng thái request nếu nghiệp vụ cần phân biệt.

### 5.1. Xử lý null trong expression

Nếu property bên trong object có thể null, hãy dùng guard hoặc null-safe navigation:

~~~text
#input.nickname != null and #input.nickname.length() > 0
~~~

AND short-circuit giúp không gọi length khi nickname null.

Hoặc cung cấp giá trị mặc định nếu điều đó đúng với nghiệp vụ:

~~~text
#input.nickname ?: 'Guest'
~~~

Không nên thay null bằng giá trị mặc định một cách máy móc. Null có thể có nghĩa là chưa xác định, chưa được nhập hoặc không hợp lệ; mỗi trường hợp có thể cần cách xử lý khác nhau.

## 6. Kiểu dữ liệu của biến

setVariable nhận Object, vì vậy context có thể chứa nhiều kiểu runtime khác nhau. Expression sử dụng kiểu thực tế của giá trị khi truy cập property hoặc gọi method.

~~~java
context.setVariable("quantity", 3);
context.setVariable("unitPrice", new BigDecimal("12.50"));
context.setVariable("enabled", true);
~~~

Các expression tương ứng:

~~~text
#quantity * #unitPrice
~~~

~~~text
#enabled and #quantity > 0
~~~

Khi lấy kết quả, nên yêu cầu kiểu mong muốn nếu hợp lý:

~~~java
BigDecimal total =
    parser.parseExpression("#quantity * #unitPrice")
        .getValue(context, BigDecimal.class);
~~~

Nếu một biến ban đầu là Integer nhưng sau đó được thay bằng String, expression số học có thể không còn hoạt động. Hãy giữ kiểu biến ổn định theo hợp đồng của expression.

Với collection, nên dùng generic type rõ ràng trong Java, ví dụ List<Order> hoặc Map<String, BigDecimal>, để code cung cấp dữ liệu và code tiêu thụ kết quả dễ hiểu hơn.

## 7. Gán lại biến từ bên trong expression

SpEL hỗ trợ toán tử gán =. Trong context và use case cho phép cập nhật, biến có thể được gán lại trong biểu thức:

~~~text
#status = 'READY'
~~~

Một biểu thức có thể dùng giá trị hiện tại để tính giá trị mới:

~~~text
#counter = #counter + 1
~~~

Phép gán cập nhật giá trị của biến trong EvaluationContext đang được dùng để đánh giá. Những lần evaluate sau trên cùng context có thể đọc giá trị mới.

Ví dụ:

~~~java
context.setVariable("counter", 0);

Expression increment =
    parser.parseExpression("#counter = #counter + 1");

Integer first = increment.getValue(context, Integer.class);
Integer second = increment.getValue(context, Integer.class);
~~~

Lần đầu biến counter thành 1; lần tiếp theo thành 2.

Phép gán là một side effect. Không nên dùng nó trong expression chỉ được kỳ vọng là truy vấn hoặc kiểm tra điều kiện. Nếu expression được đánh giá nhiều lần hoặc trong nhiều nhánh, kết quả có thể phụ thuộc thứ tự đánh giá.

Nếu chỉ cần tính một giá trị mới mà không cần cập nhật context, hãy dùng expression thuần và nhận kết quả trong Java thay vì gán lại biến.

## 8. Biến và function trong context

SpEL cho phép đăng ký function để gọi từ expression bằng cú pháp #functionName(...). Function được đăng ký trong context thông qua một Method:

~~~java
Method formatMethod =
    Formatter.class.getDeclaredMethod("format", String.class);

context.registerFunction("formatName", formatMethod);
~~~

Expression gọi function:

~~~text
#formatName(#name)
~~~

Function được đăng ký trong cùng cơ chế tên biến của context. Vì vậy, tránh dùng cùng một tên cho function và biến dữ liệu. Hãy chọn tên có ý nghĩa, chẳng hạn formatName cho function và customerName cho biến.

Chỉ đăng ký function do ứng dụng kiểm soát. Function có thể gọi method Java và thực hiện side effect tùy implementation; không expose method tùy ý chỉ vì muốn expression ngắn hơn.

## 9. Phân biệt biến, root object và bean reference

Ba cách cung cấp dữ liệu thường gặp:

| Cách cung cấp | Cú pháp trong SpEL | Nguồn giá trị |
|---|---|---|
| Root object | name hoặc #root.name | Object được đặt làm root |
| Variable | #customer | setVariable trong EvaluationContext |
| Bean reference | @customerService | BeanResolver và Spring container |

Root object là đối tượng mặc định khi expression truy cập property không có tiền tố. #root đại diện root object; #this đại diện object hiện tại tại vị trí đánh giá.

Variable được tham chiếu bằng # và có vòng đời gắn với EvaluationContext. Bean reference dùng @ và được phân giải qua BeanResolver.

Không đưa service hoặc object có quyền rộng vào biến chỉ để thuận tiện. Nếu expression chỉ cần dữ liệu, truyền DTO nhỏ làm root object hoặc variable. Nếu cần bean, hãy expose đúng bean và giới hạn method có thể gọi.

## 10. Quản lý context mutable và tính đồng thời

EvaluationContext có thể chứa biến và cấu hình accessor/resolver. Khi ứng dụng gọi setVariable, context thay đổi trạng thái. Vì vậy, không nên dùng một context mutable chung rồi thay các biến theo từng request đồng thời mà không có cơ chế cô lập hoặc đồng bộ.

Ví dụ về một thiết kế có nguy cơ lẫn dữ liệu:

~~~text
Request A: setVariable("user", userA)
Request B: setVariable("user", userB)
Request A: evaluate #user.name
~~~

Nếu hai request dùng chung một context mutable, Request A có thể đọc giá trị do Request B vừa ghi. Dữ liệu giữa các request có thể bị lẫn.

Cách tổ chức an toàn hơn:

- Tạo context riêng cho mỗi request hoặc mỗi lần đánh giá cần dữ liệu riêng.
- Tái sử dụng Expression đã parse, nhưng truyền context phù hợp với từng lần evaluate.
- Không lưu biến chứa dữ liệu người dùng trong context singleton.
- Nếu phải chia sẻ context, không thay đổi biến đồng thời; cần cơ chế đồng bộ và hợp đồng sử dụng rõ ràng.
- Không chia sẻ object mutable giữa các request nếu không có kiểm soát ownership.

Có thể tái sử dụng Expression, nhưng điều đó không có nghĩa mọi EvaluationContext chứa dữ liệu runtime cũng nên được chia sẻ.

## 11. SimpleEvaluationContext và biến

SimpleEvaluationContext cũng hỗ trợ variable thông qua hợp đồng EvaluationContext, đồng thời giới hạn nhiều capability so với StandardEvaluationContext.

Ví dụ:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimum", 100);
~~~

Expression có thể đọc biến:

~~~text
#amount >= #minimum
~~~

Chọn SimpleEvaluationContext khi use case chỉ cần data binding với quyền hạn chế. Nếu cần method invocation, type reference hoặc bean reference, hãy xem xét kỹ nhu cầu và cấu hình riêng; đừng chuyển sang context rộng hơn chỉ để tránh một lỗi mà chưa xác định nguyên nhân.

Biến chỉ là dữ liệu được cung cấp. Quyền đọc/ghi property hoặc gọi method trên object mà biến tham chiếu vẫn phụ thuộc accessor và resolver trong context.

## 12. Kiểm thử vòng đời và khả năng thay đổi

Một bộ test nên kiểm tra:

| Trường hợp | Thao tác | Điều cần xác nhận |
|---|---|---|
| Biến trong context mới | Đăng ký user ở context A | Context B không tự có user |
| Thay giá trị | Gọi setVariable hai lần cùng tên | Lần evaluate sau đọc giá trị mới |
| Thay object reference | Gán object khác vào biến | Expression đọc object mới |
| Thay đổi object mutable | Gọi setter trên object hiện tại | Expression nhìn thấy trạng thái mới |
| Biến chưa đăng ký | Không gọi setVariable | Ứng dụng xử lý trường hợp thiếu đầu vào |
| Property null | Đặt field DTO thành null | Expression xử lý null theo thiết kế |
| Thay đổi kiểu | Đổi Number thành String | Expression xử lý hoặc từ chối kiểu không tương thích |
| Assignment trong expression | Gán lại #counter | Context giữ giá trị mới cho lần evaluate sau |
| Function trùng tên variable | Đăng ký cùng tên | Thiết kế tên tránh xung đột |
| Context đồng thời | Dùng dữ liệu hai request | Không có giá trị biến bị lẫn |

Hãy kiểm tra cả giá trị trả về và trạng thái context/object sau khi evaluate. Với expression có assignment, xác nhận biến đã thay đổi. Với expression chỉ đọc, xác nhận dữ liệu đầu vào không bị thay đổi ngoài dự kiến.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Expression không tìm thấy biến | Chưa đăng ký đúng tên hoặc dùng sai context | Kiểm tra setVariable và context truyền vào getValue |
| Biến không có giá trị mong đợi | Giá trị đã bị thay thế hoặc context khác được dùng | Kiểm tra đúng instance EvaluationContext |
| Biến bị loại khỏi context | Gọi setVariable với giá trị null | Dùng DTO/wrapper có property null nếu cần biểu diễn null |
| Expression lỗi sau khi thay kiểu biến | Kiểu runtime không còn tương thích với toán tử hoặc method | Giữ kiểu theo hợp đồng hoặc validate trước khi set |
| Thay đổi biến làm object khác bị ảnh hưởng | Biến giữ reference tới object mutable dùng chung | Tạo object riêng hoặc quản lý ownership |
| Giá trị giữa các request bị lẫn | Dùng chung context mutable | Tách context theo request hoặc đồng bộ đúng cách |
| Function bị gọi sai | Tên function trùng tên variable hoặc đăng ký nhầm Method | Dùng tên rõ và kiểm tra method signature |
| Assignment không hoạt động như mong đợi | Context hoặc expression không phù hợp với thao tác ghi | Kiểm tra context, tên biến và cú pháp gán |

Khi debug, hãy ghi nhận context instance, tên biến, kiểu runtime và thời điểm setVariable được gọi. Cùng một expression có thể cho kết quả khác nhau với context và dữ liệu khác nhau.

## 14. Bài tập thực hành

1. Tạo context và đăng ký biến name, age, active; đọc chúng bằng expression.
2. Parse một expression duy nhất rồi đánh giá với hai context có dữ liệu khác nhau.
3. Thay giá trị biến bằng setVariable và quan sát kết quả lần evaluate tiếp theo.
4. Đăng ký một Customer object, thay đổi property của object và đánh giá lại.
5. Thay object reference bằng một Customer khác và phân biệt với thay đổi property.
6. Tạo DTO có field null và đọc property đó qua variable.
7. Dùng phép gán #counter = #counter + 1 rồi kiểm tra trạng thái sau nhiều lần evaluate.
8. Đăng ký function và biến, bảo đảm tên không xung đột.
9. Tạo hai context độc lập cho hai user và xác nhận dữ liệu không lẫn.
10. Thử SimpleEvaluationContext với biến và kiểm tra giới hạn capability.

## 15. Checklist trước khi đưa biến vào ứng dụng

- [ ] Đã xác định context nào sở hữu biến chưa?
- [ ] Đã xác định biến sống trong bao lâu chưa?
- [ ] Có tạo context riêng cho request hoặc lần evaluate cần dữ liệu riêng không?
- [ ] Tên trong setVariable có khớp tên sau dấu # không?
- [ ] Kiểu runtime của biến có ổn định theo hợp đồng expression không?
- [ ] Đã phân biệt thay reference với thay đổi object mutable chưa?
- [ ] Đã phân biệt biến chưa đăng ký với property có giá trị null chưa?
- [ ] Có dùng assignment trong expression không, và side effect đó có cần thiết không?
- [ ] Tên function có xung đột với tên variable không?
- [ ] Có chia sẻ context mutable giữa các luồng hoặc request không?
- [ ] Object trong biến có chứa service hoặc dữ liệu nhạy cảm không?
- [ ] Context có cấp đúng quyền đọc/ghi và gọi method cần thiết không?

## 16. Kết luận

Biến SpEL được lưu trong EvaluationContext và được đọc bằng tiền tố #. Vòng đời của biến phụ thuộc vào vòng đời context do ứng dụng quản lý; nó không tự gắn với request, session hay bean scope. setVariable có thể thay giá trị cho những lần evaluate tiếp theo, còn object mutable được tham chiếu có thể thay đổi mà không cần thay chính biến. Hãy giữ kiểu dữ liệu ổn định, xử lý null rõ ràng, tránh assignment không cần thiết và cô lập context mutable giữa các request. Expression đã parse có thể được tái sử dụng với nhiều context độc lập, giúp tách quy tắc khỏi dữ liệu runtime.