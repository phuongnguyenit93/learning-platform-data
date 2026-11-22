# Quản lý vòng đời và khả năng thay đổi của biến trong SpEL

Biến trong Spring Expression Language (SpEL) là dữ liệu được đặt trong EvaluationContext và được tham chiếu trong biểu thức bằng tiền tố #. Biến giúp tách dữ liệu runtime khỏi chuỗi expression: cùng một biểu thức có thể được đánh giá nhiều lần với các giá trị khác nhau mà không phải tạo lại cú pháp.

Để quản lý biến đúng cách, cần hiểu biến thuộc về EvaluationContext nào, tồn tại trong bao lâu, cách cập nhật hoặc thay thế giá trị, và điều gì xảy ra khi biến tham chiếu tới object mutable. SpEL không tự gắn vòng đời của biến với request, session hay bean scope; vòng đời thực tế phụ thuộc vào cách ứng dụng tạo, chia sẻ và loại bỏ context.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Khai báo và đọc biến bằng setVariable và cú pháp #variable.
- Phân biệt biến với root object, property và bean reference.
- Hiểu biến được lưu trong EvaluationContext và không tự tồn tại toàn cục.
- Thay đổi giá trị biến giữa các lần evaluate.
- Phân biệt thay thế tham chiếu của biến với thay đổi trạng thái object mà biến đang tham chiếu.
- Dùng phép gán trong SpEL khi use case cho phép cập nhật.
- Quản lý biến null, kiểu dữ liệu và tên biến.
- Tránh chia sẻ context mutable giữa các luồng hoặc request không liên quan.
- Viết test cho vòng đời, giá trị và khả năng thay đổi của biến.

Bạn nên biết cách tạo SpelExpressionParser, Expression và EvaluationContext, cùng với Java object, collection và kiểu dữ liệu cơ bản.

## 2. Biến trong SpEL là gì?

Biến là một giá trị được đăng ký trong EvaluationContext. Khi viết expression, tham chiếu biến bằng ký tự # ở đầu tên:

~~~text
#name
~~~

Trong Java, đăng ký biến bằng tên không có ký tự #:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("name", "An");
~~~

Đọc giá trị:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("#name");

String name = expression.getValue(context, String.class);
~~~

Kết quả là An.

Tên trong setVariable là name; trong expression là #name. Không truyền # vào tên khi gọi setVariable.

Biến có thể chứa nhiều loại object:

- String, Number và Boolean.
- DTO hoặc domain object.
- List, Set và Map.
- Giá trị null.
- Object do ứng dụng tạo để phục vụ một lần đánh giá.

SpEL không yêu cầu mọi biến phải là chuỗi. Kiểu runtime của object được đặt vào context ảnh hưởng tới property access, method invocation, toán tử và kiểu kết quả.

## 3. Vòng đời của biến gắn với EvaluationContext

Biến được lưu trong context mà ứng dụng đã đăng ký nó. Vì vậy, thời gian tồn tại của biến phụ thuộc vào thời gian tồn tại và cách sử dụng context đó.

~~~java
StandardEvaluationContext firstContext =
    new StandardEvaluationContext();

firstContext.setVariable("user", "An");

StandardEvaluationContext secondContext =
    new StandardEvaluationContext();
~~~

Biến user được đăng ký trong firstContext không tự xuất hiện trong secondContext. Hai context có vùng biến riêng.

Có thể hình dung:

~~~text
firstContext
  variables:
    user -> "An"

secondContext
  variables:
    (chưa đăng ký user)
~~~

Tạo một Expression rồi đánh giá nó với context khác không làm biến tự chuyển từ context cũ sang context mới. Expression chứa cấu trúc đã parse; giá trị biến được tra cứu trong context truyền vào khi evaluate.

Điều này cho phép tái sử dụng cùng một Expression với nhiều context:

~~~java
Expression expression = parser.parseExpression("#user");

StandardEvaluationContext contextA =
    new StandardEvaluationContext();
contextA.setVariable("user", "An");

StandardEvaluationContext contextB =
    new StandardEvaluationContext();
contextB.setVariable("user", "Binh");

String a = expression.getValue(contextA, String.class);
String b = expression.getValue(contextB, String.class);
~~~

Kết quả lần lượt là An và Binh.

### 3.1. Biến không có scope tự động như request hoặc session

SpEL không tự hiểu một biến là request-scoped, session-scoped hay application-scoped. Context được tạo ở đâu và giữ lại bao lâu là quyết định của ứng dụng.

Ví dụ:

- Tạo context cho mỗi lần xử lý request: biến thường chỉ được dùng trong lần xử lý đó.
- Tạo context trong một tác vụ batch: biến có thể sống trong suốt tác vụ.
- Giữ context trong một object singleton: biến có thể tồn tại lâu hơn dự kiến nếu không được quản lý.
- Tạo context mới cho từng tenant: dữ liệu biến được tách theo context nếu ứng dụng không chia sẻ object bên trong.

Không nên dựa vào tên biến để suy ra scope. Hãy xác định nơi tạo context, nơi đăng ký biến, nơi evaluate và thời điểm context được giải phóng.

## 4. Thay đổi giá trị biến giữa các lần đánh giá

Có thể gọi setVariable nhiều lần với cùng tên. Giá trị mới thay thế giá trị đang được đăng ký cho tên đó trong context:

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

Cách làm này hữu ích khi quy tắc biểu thức ổn định nhưng dữ liệu thay đổi. Tuy nhiên, nếu thay đổi kiểu của biến giữa các lần đánh giá, expression có thể cho kết quả khác hoặc phát sinh lỗi do kiểu toán hạng không còn tương thích.

### 4.1. Thay thế giá trị khác với sửa object đang được tham chiếu

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

Đây là khác biệt quan trọng khi làm việc với object mutable. Một biến không tạo bản sao sâu của object được gán vào nó.

## 5. Giá trị null và biến chưa được đăng ký

Một biến có thể mang giá trị null nếu ứng dụng đăng ký như vậy. Khi expression đọc biến, kết quả có thể là null; thao tác tiếp theo cần xử lý null theo đúng nghiệp vụ.

Ví dụ:

~~~java
context.setVariable("nickname", null);
~~~

Expression:

~~~text
#nickname
~~~

có thể trả về null. Nếu biểu thức tiếp tục truy cập property hoặc gọi method trên biến đó, cần dùng null-safe navigation hoặc guard phù hợp:

~~~text
#nickname != null and #nickname.length() > 0
~~~

AND short-circuit giúp không gọi length khi nickname null.

Biến chưa được đăng ký là tình huống khác về mặt cấu hình. Khi tra cứu, ứng dụng có thể dùng lookupVariable để kiểm tra giá trị hiện tại:

~~~java
Object value = context.lookupVariable("nickname");
~~~

Nếu cần phân biệt rõ biến không được cung cấp với biến được cung cấp nhưng có giá trị null, hãy quản lý một tập tên biến đầu vào hoặc một object request có schema rõ ràng. Không nên dựa vào một phép đọc null duy nhất để diễn giải trạng thái dữ liệu nếu nghiệp vụ cần phân biệt hai trường hợp đó.

## 6. Kiểu dữ liệu của biến

setVariable nhận Object, vì vậy context có thể chứa nhiều kiểu runtime khác nhau. Expression sử dụng kiểu thực tế của giá trị khi truy cập property hoặc gọi method.

Ví dụ:

~~~java
context.setVariable("quantity", 3);
context.setVariable("price", new BigDecimal("12.50"));
context.setVariable("enabled", true);
~~~

Các expression tương ứng:

~~~text
#quantity * #price
~~~

~~~text
#enabled and #quantity > 0
~~~

Khi lấy kết quả, nên yêu cầu kiểu mong muốn nếu hợp lý:

~~~java
BigDecimal total =
    parser.parseExpression("#quantity * #price")
        .getValue(context, BigDecimal.class);
~~~

Nếu một biến ban đầu là Integer nhưng sau đó được thay bằng một chuỗi, expression số học có thể không còn hoạt động. Hãy giữ kiểu biến ổn định theo hợp đồng của expression.

Với collection, nên dùng generic type rõ ràng trong Java, ví dụ List<Order> hoặc Map<String, BigDecimal>, để code cung cấp dữ liệu và code tiêu thụ kết quả dễ hiểu hơn. SpEL vẫn làm việc với object runtime, nhưng khai báo kiểu ở Java giúp giảm lỗi từ dữ liệu không nhất quán.

## 7. Gán lại biến từ bên trong expression

SpEL hỗ trợ toán tử gán =. Trong các context và use case cho phép ghi, biến có thể được gán lại trong biểu thức:

~~~text
#status = 'READY'
~~~

Một biểu thức có thể dùng giá trị hiện tại để tính giá trị mới:

~~~text
#counter = #counter + 1
~~~

Phép gán cập nhật giá trị của biến trong EvaluationContext đang được dùng để đánh giá. Những lần evaluate sau trên cùng context có thể đọc giá trị mới.

Ví dụ Java:

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

## 8. Biến và function dùng chung không gian tên

SpEL cho phép đăng ký function để gọi từ expression bằng cú pháp #functionName(...). Function được đăng ký trong context thông qua một Method, và về mặt lưu trữ nó sử dụng cơ chế biến của context.

Ví dụ:

~~~java
Method formatMethod =
    Formatter.class.getDeclaredMethod("format", String.class);

context.registerFunction("formatName", formatMethod);
~~~

Expression gọi function:

~~~text
#formatName(#name)
~~~

Vì function và variable cùng sử dụng cơ chế tên trong context, tránh đặt cùng một tên cho một biến dữ liệu và một function. Hãy chọn tên có ý nghĩa, chẳng hạn formatName cho function và customerName cho biến.

Chỉ đăng ký các function được ứng dụng kiểm soát. Function có thể gọi method Java và thực hiện side effect tùy implementation; không expose method tùy ý chỉ vì muốn expression ngắn hơn.

## 9. Biến, root object và bean reference

Ba cách cung cấp dữ liệu thường gặp:

| Cách cung cấp | Cú pháp trong SpEL | Nguồn giá trị |
|---|---|---|
| Root object | name hoặc #root.name | Object được đặt làm root |
| Variable | #customer | setVariable trong EvaluationContext |
| Bean reference | @customerService | BeanResolver và Spring container |

Root object là đối tượng mặc định khi expression truy cập property không có tiền tố. #root luôn đại diện root object; #this đại diện object hiện tại tại vị trí đánh giá.

Variable được tham chiếu bằng # và có vòng đời gắn với EvaluationContext. Bean reference dùng @ và được phân giải qua BeanResolver.

Không nên đưa service hoặc object có quyền rộng vào biến chỉ để thuận tiện. Nếu expression chỉ cần dữ liệu, truyền DTO nhỏ làm root object hoặc variable. Nếu cần bean, hãy expose đúng bean và giới hạn method có thể gọi.

## 10. Quản lý context mutable và tính đồng thời

EvaluationContext có thể chứa biến và cấu hình accessor/resolver. Khi ứng dụng gọi setVariable, context thay đổi trạng thái. Vì vậy, không nên dùng một context dùng chung rồi thay các biến theo từng request đồng thời mà không có cơ chế cô lập hoặc đồng bộ.

Ví dụ nguy hiểm về mặt thiết kế:

~~~text
Request A: setVariable("user", userA)
Request B: setVariable("user", userB)
Request A: evaluate #user.name
~~~

Nếu hai request dùng chung một context mutable, Request A có thể đọc giá trị do Request B vừa ghi. Kết quả là dữ liệu giữa các request có thể bị lẫn.

Cách tổ chức an toàn hơn:

- Tạo context riêng cho mỗi request hoặc mỗi lần đánh giá cần dữ liệu riêng.
- Tạo một context mới từ cấu hình chung đã được chuẩn bị trước nếu cần tái sử dụng resolver/accessor.
- Không lưu biến chứa dữ liệu người dùng trong context singleton.
- Nếu phải chia sẻ context, không thay đổi biến đồng thời; cần cơ chế đồng bộ và hợp đồng sử dụng rõ ràng.
- Không chia sẻ object mutable giữa các request nếu không có kiểm soát ownership.

Có thể tái sử dụng Expression đã parse, nhưng điều đó không có nghĩa mọi EvaluationContext chứa dữ liệu runtime cũng nên được chia sẻ.

## 11. SimpleEvaluationContext và biến

SimpleEvaluationContext cũng hỗ trợ biến thông qua hợp đồng EvaluationContext, đồng thời giới hạn nhiều capability so với StandardEvaluationContext.

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

Biến chỉ là dữ liệu được cung cấp. Quyền đọc/ghi property hoặc gọi method trên object được biến tham chiếu vẫn phụ thuộc accessor và resolver trong context.

## 12. Kiểm thử vòng đời và khả năng thay đổi

Một bộ test nên kiểm tra:

| Trường hợp | Thao tác | Điều cần xác nhận |
|---|---|---|
| Biến trong context mới | Đăng ký user ở context A | Context B không tự có user |
| Thay giá trị | Gọi setVariable hai lần cùng tên | Lần evaluate sau đọc giá trị mới |
| Thay object reference | Gán object khác vào biến | Expression đọc object mới |
| Thay đổi object mutable | Gọi setter trên object hiện tại | Expression nhìn thấy trạng thái mới |
| Giá trị null | Đăng ký biến null | Expression xử lý null theo thiết kế |
| Biến chưa đăng ký | Không gọi setVariable | Ứng dụng phát hiện dữ liệu chưa được cung cấp |
| Thay đổi kiểu | Đổi Number thành String | Expression xử lý hoặc từ chối kiểu không tương thích |
| Assignment trong expression | Gán lại #counter | Context giữ giá trị mới cho lần evaluate sau |
| Function trùng tên variable | Đăng ký cùng tên | Thiết kế tên tránh xung đột |
| Context đồng thời | Dùng dữ liệu hai request | Không có giá trị biến bị lẫn |

Hãy test cả giá trị trả về và trạng thái context/object sau khi evaluate. Với expression có assignment, kiểm tra biến đã thay đổi. Với expression chỉ đọc, xác nhận dữ liệu đầu vào không bị thay đổi ngoài dự kiến.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Expression không tìm thấy biến | Chưa đăng ký đúng tên hoặc dùng sai context | Kiểm tra setVariable và context truyền vào getValue |
| Biến trả về null | Giá trị được đăng ký là null hoặc dữ liệu không được cung cấp | Xác định rõ chính sách null và kiểm tra nguồn dữ liệu |
| Lần evaluate sau vẫn dùng giá trị cũ | Đã cập nhật biến trong context khác | Kiểm tra đúng instance EvaluationContext |
| Expression lỗi sau khi thay kiểu biến | Kiểu runtime không còn tương thích với toán tử hoặc method | Giữ kiểu theo hợp đồng hoặc validate trước khi set |
| Thay đổi biến làm object khác bị ảnh hưởng | Biến giữ reference tới object mutable dùng chung | Tạo object riêng hoặc quản lý ownership |
| Giá trị giữa các request bị lẫn | Dùng chung context mutable | Tách context theo request hoặc đồng bộ đúng cách |
| Function bị gọi sai | Tên function trùng tên variable hoặc đăng ký nhầm Method | Dùng namespace tên rõ và kiểm tra method signature |
| Assignment không được phép | Context/accessor không cấp quyền ghi hoặc expression không phải đích gán hợp lệ | Kiểm tra context và cách viết expression |

Khi debug, hãy ghi nhận context instance, tên biến, kiểu runtime và thời điểm setVariable được gọi. Đừng chỉ kiểm tra chuỗi expression; cùng một expression có thể cho kết quả khác nhau với context và dữ liệu khác nhau.

## 14. Bài tập thực hành

1. Tạo context và đăng ký biến name, age, active; đọc chúng bằng expression.
2. Parse một expression duy nhất rồi đánh giá với hai context có dữ liệu khác nhau.
3. Thay giá trị biến bằng setVariable và quan sát kết quả lần evaluate tiếp theo.
4. Đăng ký một Customer object, thay đổi property của object và đánh giá lại.
5. Thay object reference bằng một Customer khác và phân biệt với thay đổi property.
6. Đăng ký biến null và thử safe navigation cùng Elvis.
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
- [ ] Giá trị null và biến chưa được cung cấp có được xử lý rõ không?
- [ ] Có dùng assignment trong expression không, và side effect đó có cần thiết không?
- [ ] Tên function có xung đột với tên variable không?
- [ ] Có chia sẻ context mutable giữa các luồng hoặc request không?
- [ ] Object trong biến có chứa service hoặc dữ liệu nhạy cảm không?
- [ ] Context có cấp đúng quyền đọc/ghi và gọi method cần thiết không?

## 16. Kết luận

Biến SpEL được lưu trong EvaluationContext và được đọc bằng tiền tố #. Vòng đời của biến phụ thuộc vào vòng đời context do ứng dụng quản lý; nó không tự gắn với request, session hay bean scope. setVariable có thể thay giá trị cho những lần evaluate tiếp theo, còn object mutable được tham chiếu có thể thay đổi mà không cần thay chính biến. Hãy giữ kiểu dữ liệu ổn định, xử lý null rõ ràng, tránh assignment không cần thiết và cô lập context mutable giữa các request. Expression đã parse có thể được tái sử dụng với nhiều context độc lập, giúp tách quy tắc khỏi dữ liệu runtime.