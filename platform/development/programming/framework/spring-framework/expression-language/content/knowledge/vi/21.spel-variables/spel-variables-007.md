# Phân biệt biến SpEL với property của root object

## Mục tiêu

Sau bài này, bạn có thể phân biệt biến được đăng ký trong EvaluationContext với thuộc tính của root object trong Spring Expression Language (SpEL); viết đúng cú pháp có và không có tiền tố dấu thăng; thiết lập root object và biến từ Java; xử lý trường hợp tên biến trùng tên thuộc tính; và sử dụng đúng #root, #this trong biểu thức lồng nhau. Bạn cũng sẽ biết cách tránh lỗi do thiếu biến, root object null hoặc nhầm namespace.

## 1. Hai nguồn dữ liệu trong một biểu thức SpEL

Một biểu thức SpEL thường cần đọc dữ liệu từ hai nguồn:

- **Root object:** đối tượng được cung cấp làm đối tượng gốc khi đánh giá biểu thức. Thuộc tính của nó thường được truy cập trực tiếp bằng tên property.
- **EvaluationContext variables:** các giá trị được ứng dụng đăng ký vào context. Biến được tham chiếu bằng tiền tố #.

Ví dụ:

~~~text
name
#name
~~~

Hai biểu thức trên không tương đương:

- `name` yêu cầu SpEL đọc property tên name từ đối tượng hiện tại, ở cấp ngoài cùng thường là root object.
- `#name` yêu cầu SpEL đọc biến tên name đã được đăng ký trong EvaluationContext.

Việc cùng dùng một tên không làm hai nguồn dữ liệu trở thành một. Tiền tố # là dấu hiệu để parser tra cứu biến trong context; không có tiền tố thì SpEL thực hiện truy cập property trên đối tượng hiện tại.

## 2. Truy cập property của root object

Root object là đối tượng làm điểm bắt đầu cho việc đánh giá biểu thức. Ví dụ, một ứng dụng truyền đối tượng Customer vào SpEL:

~~~java
Customer customer = new Customer();
customer.setName("An");
customer.setAge(28);

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("name");

String name = expression.getValue(customer, String.class);
~~~

Trong ví dụ này, customer là root object. Biểu thức `name` đọc property name của đối tượng đó và trả về "An".

Có thể đọc nhiều cấp property:

~~~text
address.city
customer.profile.displayName
~~~

Mỗi tên property được giải quyết trên đối tượng hiện tại ở bước tương ứng. Đối tượng trung gian phải tồn tại và property phải có thể truy cập thông qua PropertyAccessor của EvaluationContext.

Nếu root object là một Order có property customer, biểu thức `customer.name` đọc customer từ root rồi đọc name từ đối tượng Customer con.

## 3. Tham chiếu biến bằng tiền tố #

Biến được ứng dụng đăng ký vào EvaluationContext và được tham chiếu bằng dấu #:

~~~text
#minimumAge
#currentUser
#allowedStatuses
~~~

Ví dụ Java:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("minimumAge", 18);
context.setVariable("currentUser", currentUser);
context.setVariable(
    "allowedStatuses",
    List.of("PAID", "SHIPPED")
);
~~~

Sau đó biểu thức có thể sử dụng các biến:

~~~text
#minimumAge
#currentUser.name
#allowedStatuses
~~~

Biến có thể chứa số, chuỗi, boolean, object nghiệp vụ, mảng hoặc collection. SpEL đọc giá trị mà ứng dụng đã cung cấp; nó không tự tạo biến chỉ vì tên biến xuất hiện trong biểu thức.

Cách truyền dữ liệu qua biến giúp giữ chuỗi expression ổn định trong khi dữ liệu đầu vào thay đổi theo từng lần đánh giá. Hãy đăng ký giá trị bằng Java thay vì nối trực tiếp dữ liệu đầu vào vào chuỗi SpEL.

## 4. Thiết lập root object và biến trong cùng context

Có thể cung cấp root object ngay khi tạo StandardEvaluationContext:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

context.setVariable("minimumAge", 18);
context.setVariable("requiredCity", "Da Nang");

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "age >= #minimumAge and address.city == #requiredCity"
);

Boolean eligible = expression.getValue(context, Boolean.class);
~~~

Trong biểu thức:

- `age` và `address.city` được đọc từ root object customer.
- `#minimumAge` và `#requiredCity` được đọc từ EvaluationContext.

Cách viết này tách dữ liệu chính cần đánh giá khỏi các tham số hoặc ngưỡng cấu hình. Root object cung cấp trạng thái của đối tượng đang xét; biến cung cấp các giá trị phụ trợ mà biểu thức cần dùng.

Cũng có thể thiết lập root object sau khi tạo context:

~~~java
context.setRootObject(customer);
~~~

Nếu muốn cung cấp root object riêng cho một lần đánh giá, có thể truyền nó qua overload của getValue:

~~~java
Boolean eligible =
    expression.getValue(context, customer, Boolean.class);
~~~

Chọn một cách thiết lập nhất quán với vòng đời context của ứng dụng. Không nên thay root object giữa các lần đánh giá mà không chủ ý, vì cùng một expression khi đó có thể đọc các đối tượng khác nhau.

## 5. So sánh cú pháp root property và variable

Bảng dưới đây tóm tắt cách phân giải hai loại tham chiếu:

| Cú pháp | Nguồn tra cứu | Ví dụ |
|---|---|---|
| `name` | Property của đối tượng hiện tại | `name` |
| `address.city` | Property lồng nhau trên đối tượng hiện tại | `address.city` |
| `#name` | Variable trong EvaluationContext | `#name` |
| `#customer.name` | Property của object được lưu trong biến customer | `#customer.name` |
| `#root.name` | Property name của root object | `#root.name` |
| `#this.name` | Property name của đối tượng đang là evaluation object hiện tại | `#this.name` |

Ví dụ, nếu root object là Customer, thì `name` và `#root.name` thường đọc cùng property. Tuy nhiên, `#name` đọc biến tên name trong context; biến đó có thể chứa một giá trị hoàn toàn khác.

Việc thêm hoặc bỏ dấu # có thể làm thay đổi nguồn dữ liệu được đọc, vì vậy hãy viết cú pháp có chủ đích thay vì dựa vào tên biến hoặc property giống nhau.

## 6. Khi biến và property trùng tên

Một ứng dụng có thể có property name trên root object và đồng thời đăng ký variable name:

~~~java
Customer customer = new Customer();
customer.setName("An");

StandardEvaluationContext context =
    new StandardEvaluationContext(customer);

context.setVariable("name", "Binh");
~~~

Ba biểu thức sau có ý nghĩa khác nhau:

~~~text
name
#name
#root.name
~~~

Kết quả:

- `name` đọc property của root object và trả về "An".
- `#name` đọc variable và trả về "Binh".
- `#root.name` đọc rõ ràng property name của root object và trả về "An".

Đây là cách giải quyết xung đột tên minh bạch. Khi biểu thức dài hoặc có nhiều đối tượng, dùng `#root.property` có thể giúp người đọc nhận biết rõ dữ liệu đến từ root object.

Nên đặt tên biến theo vai trò, ví dụ `#minimumTotal`, `#currentUser` hoặc `#featureEnabled`, để giảm khả năng trùng với property của mô hình dữ liệu.

## 7. #root và #this khác nhau như thế nào?

SpEL cung cấp hai tham chiếu đặc biệt:

- `#root` luôn trỏ đến root object của lần đánh giá.
- `#this` trỏ đến evaluation object hiện tại. Ở cấp ngoài cùng, #this thường chính là root object; trong các biểu thức lồng như selection và projection, nó có thể thay đổi theo phần tử đang được xử lý.

Ví dụ ở cấp ngoài cùng:

~~~text
#root.name
#this.name
name
~~~

Nếu không có một ngữ cảnh lồng làm thay đổi evaluation object, ba cách này có thể đọc cùng property của root.

Trong selection:

~~~text
#orders.?[total >= #root.minimumTotal]
~~~

Ở đây, `total` được đọc từ đơn hàng hiện tại, còn `#root.minimumTotal` đọc ngưỡng từ root object ban đầu.

Trong projection:

~~~text
#orders.![#this.id]
~~~

`#this` là từng đơn hàng đang được chiếu. `#root` vẫn là root object ban đầu của lần đánh giá.

Phân biệt hai tham chiếu này đặc biệt quan trọng trong collection operation, vì một tên property không có tiền tố # bên trong selection/projection thường được giải quyết trên phần tử hiện tại chứ không phải root object ban đầu.

## 8. Dùng variable chứa object thay cho root object

Không phải mọi object đều cần được đặt làm root. Có thể truyền nhiều object qua các biến:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customer", customer);
context.setVariable("order", order);
context.setVariable("policy", policy);
~~~

Biểu thức:

~~~text
#customer.name
#order.total
#policy.maximumDiscount
~~~

Cách này hữu ích khi một quy tắc cần kết hợp nhiều đối tượng độc lập. Mỗi biến có tên riêng nên nguồn dữ liệu dễ nhận biết.

So sánh:

~~~text
customer.name
~~~

với:

~~~text
#customer.name
~~~

Biểu thức đầu tìm property customer trên root object rồi đọc name. Biểu thức sau tìm variable customer trong context rồi đọc name trên object được lưu trong biến.

Nếu root object chính là Customer, biểu thức `customer.name` chỉ hợp lệ khi Customer có property tên customer. Nó không tự động có nghĩa là biến customer.

## 9. Biến trong selection và projection

Biến được đăng ký trong EvaluationContext có thể được dùng ở bên trong selection và projection.

Ví dụ lọc các đơn hàng có tổng tiền đạt ngưỡng:

~~~text
#orders.?[total >= #minimumTotal]
~~~

Trong biểu thức điều kiện:

- `total` là property của đơn hàng hiện tại.
- `#minimumTotal` là variable được cung cấp từ context.

Lấy mã của các đơn hàng đạt ngưỡng:

~~~text
#orders.?[total >= #minimumTotal].![id]
~~~

Nếu cần truy cập property của root object trong điều kiện lồng:

~~~text
#orders.?[total >= #root.minimumTotal]
~~~

Ở đây #root vẫn tham chiếu root object ban đầu, ngay cả khi #this đang đại diện cho một đơn hàng.

Ví dụ dùng cả ba nguồn:

~~~text
#orders.?[
    total >= #minimumTotal and
    customerId == #root.customer.id
].![id]
~~~

Điều kiện kết hợp property của phần tử hiện tại, variable của context và property của root object. Khi biểu thức lồng trở nên khó đọc, hãy đặt dữ liệu cần thiết vào các biến có tên rõ ràng hoặc chuyển quy tắc nhiều bước sang Java.

## 10. Giá trị null và biến chưa được đăng ký

Biến có thể được đăng ký với giá trị null. Một tham chiếu variable không có giá trị hữu ích cần được xử lý rõ ràng:

~~~text
#optionalNote == null
#currentUser != null
~~~

Đừng giả định rằng mọi biến được nhắc đến trong expression đều đã được đăng ký. Nếu biến bắt buộc chưa được cung cấp, biểu thức có thể nhận null hoặc thất bại ở bước truy cập tiếp theo, tùy cách dùng.

Ví dụ:

~~~text
#currentUser.name
~~~

Nếu `#currentUser` là null, việc đọc name trên giá trị null có thể phát sinh lỗi. Có thể dùng safe navigation:

~~~text
#currentUser?.name
~~~

Hoặc cung cấp mặc định:

~~~text
#currentUser?.name ?: 'Guest'
~~~

Root object cũng có thể null. Nếu biểu thức đọc property trực tiếp như `name` khi root object null, thao tác truy cập không thể thực hiện. Hãy kiểm tra dữ liệu đầu vào trước khi đánh giá hoặc dùng một điều kiện bảo vệ phù hợp.

Nếu biến là bắt buộc cho nghiệp vụ, nên xác thực sự hiện diện và kiểu của biến ở Java trước khi gọi getValue. Điều này giúp phân biệt dữ liệu thiếu với một giá trị null hợp lệ.

## 11. Đăng ký, đọc và cập nhật biến từ Java

EvaluationContext cung cấp API để ứng dụng quản lý variable:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("minimum", 100);
context.setVariable("enabled", true);

Object minimum = context.lookupVariable("minimum");

context.setVariable("minimum", 150);
~~~

`setVariable(...)` đăng ký hoặc thay thế giá trị của biến. `lookupVariable(...)` cho phép Java đọc lại giá trị đã đăng ký.

Sau khi cập nhật biến, cùng một Expression có thể được đánh giá lại với dữ liệu mới:

~~~java
Expression expression =
    parser.parseExpression("#amount >= #minimum");

context.setVariable("amount", 120);
context.setVariable("minimum", 100);

Boolean first = expression.getValue(context, Boolean.class);

context.setVariable("minimum", 150);

Boolean second = expression.getValue(context, Boolean.class);
~~~

Lần đánh giá đầu trả về true; lần thứ hai trả về false vì ngưỡng đã thay đổi.

Nên cập nhật biến trước mỗi lần đánh giá theo dữ liệu đầu vào tương ứng. Nếu nhiều luồng dùng chung một context có thể thay đổi, các giá trị root và variable có thể ảnh hưởng lẫn nhau. Hãy cân nhắc tạo context riêng cho từng lần xử lý hoặc từng luồng khi cần tính cô lập.

## 12. Biến không phải bean reference

SpEL dùng các tiền tố khác nhau cho các namespace khác nhau:

| Cú pháp | Ý nghĩa |
|---|---|
| `#orderService` | Variable tên orderService trong EvaluationContext |
| `@orderService` | Bean tên orderService được tìm qua BeanResolver |
| `orderService` | Property orderService của đối tượng hiện tại |

Ví dụ, đăng ký một biến từ Java:

~~~java
context.setVariable("orderService", serviceMock);
~~~

Biểu thức `#orderService` đọc serviceMock. Biểu thức `@orderService` yêu cầu BeanResolver tìm bean trong Spring container. Hai cách này có thể trả về hai object khác nhau dù tên giống nhau.

Nếu tự tạo StandardEvaluationContext và muốn dùng bean reference, cần cấu hình BeanResolver. Việc đăng ký variable bằng setVariable không tự tạo bean reference và cũng không cần BeanResolver.

Không có tiền tố # hoặc @, SpEL xử lý tên theo quy tắc property access trên evaluation object hiện tại.

## 13. Biến và property trong SimpleEvaluationContext

SimpleEvaluationContext là context giới hạn, được cấu hình theo nhu cầu truy cập property và phương thức. Nó vẫn có thể nhận dữ liệu qua các biến được ứng dụng đăng ký bằng API:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("minimumAge", 18);
~~~

Biểu thức có thể đọc biến:

~~~text
age >= #minimumAge
~~~

Ở đây age được đọc từ root object hiện tại, còn #minimumAge được đọc từ variable trong context.

Khả năng truy cập property phụ thuộc PropertyAccessor được cấu hình. SimpleEvaluationContext không cung cấp toàn bộ tính năng của StandardEvaluationContext, vì vậy không nên giả định mọi method, type reference, bean reference hoặc constructor invocation đều được hỗ trợ.

Nếu một biểu thức chỉ cần đọc một vài property và so sánh với các tham số được truyền vào, context giới hạn có thể phù hợp. Hãy cấu hình rõ quyền truy cập cần thiết và kiểm thử với đúng loại context mà ứng dụng dùng khi chạy.

## 14. Lỗi thường gặp khi nhầm variable và root property

Các lỗi phổ biến gồm:

- **Quên dấu #:** viết `minimumAge` trong khi minimumAge chỉ được đăng ký là variable.
- **Thêm dấu # sai chỗ:** viết `#name` trong khi name là property của root object và không có variable tương ứng.
- **Root object không đúng kiểu:** biểu thức truy cập property không tồn tại trên object được truyền vào.
- **Trùng tên:** variable và property cùng tên nhưng người viết không xác định rõ nguồn cần đọc.
- **Nhầm bean với variable:** dùng `#service` trong khi chỉ có bean `@service` được đăng ký.
- **Root object null:** truy cập property trực tiếp khi không có đối tượng gốc.
- **Variable null:** đọc property tiếp theo trên object null.
- **Nhầm #this với #root:** trong selection/projection, #this đã chuyển sang phần tử hiện tại nhưng biểu thức lại cần property của root object.

Khi gỡ lỗi, hãy xác định từng tên trong expression thuộc namespace nào: property của evaluation object, variable của context hay bean được resolver tìm. Sau đó kiểm tra object thực tế, kiểu dữ liệu và giá trị đã được đăng ký từ Java.

## 15. Ví dụ tổng hợp

Giả sử ứng dụng cần đánh giá một đơn hàng dựa trên root object, biến ngưỡng và biến trạng thái được phép:

~~~java
Order order = loadOrder();

StandardEvaluationContext context =
    new StandardEvaluationContext(order);

context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("allowedStatus", List.of("PAID", "SHIPPED"));

ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "total >= #minimumTotal and #allowedStatus.contains(status)"
);

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

Trong biểu thức:

- `total` và `status` là property của root object Order.
- `#minimumTotal` là biến chứa ngưỡng tiền.
- `#allowedStatus` là biến chứa danh sách trạng thái được phép.

Có thể viết rõ nguồn property bằng #root:

~~~text
#root.total >= #minimumTotal
and #allowedStatus.contains(#root.status)
~~~

Hai cách diễn đạt cùng ý nghĩa khi evaluation object ở cấp ngoài cùng là root object. Cách viết tường minh có thể hữu ích khi biểu thức có nhiều cấp lồng nhau.

## 16. Kiểm thử namespace của biểu thức

Khi kiểm thử, hãy tạo các trường hợp phân biệt rõ root property và variable:

| Trường hợp | Dữ liệu | Điều cần xác nhận |
|---|---|---|
| Root property | Root có name = "An" | `name` đọc "An" |
| Variable | Context có name = "Binh" | `#name` đọc "Binh" |
| Cùng tên | Root name = "An", variable name = "Binh" | Hai cú pháp trả về hai giá trị khác nhau |
| Root tham chiếu tường minh | Root có name = "An" | `#root.name` đọc "An" |
| Current object | Đánh giá ở cấp ngoài cùng | `#this` trỏ đến root |
| Collection lồng | Selection trên danh sách | `#this` là phần tử hiện tại |
| Root null | Không có đối tượng gốc | Property access được xử lý phù hợp |
| Variable null | Variable có giá trị null | Safe navigation hoặc điều kiện null hoạt động |
| Variable thiếu | Không đăng ký biến bắt buộc | Validation phát hiện dữ liệu đầu vào thiếu |
| Bean cùng tên | Có bean và variable cùng tên | `@name` khác `#name` |

Kiểm thử cả trường hợp bình thường và trường hợp tên bị trùng giúp tránh lỗi lấy nhầm dữ liệu khi expression được chỉnh sửa hoặc context thay đổi.

## 17. Ghi nhớ

Property không có tiền tố # được đọc từ evaluation object hiện tại; ở cấp ngoài cùng, đó thường là root object. Variable được đăng ký trong EvaluationContext phải được tham chiếu bằng #, ví dụ #minimumAge hoặc #currentUser.name.

Có thể thiết lập root object bằng constructor của context, setRootObject hoặc overload getValue nhận root object. Dùng setVariable để cung cấp dữ liệu phụ trợ. Khi variable và property trùng tên, name đọc property còn #name đọc variable; #root.name chỉ rõ property của root.

#root luôn tham chiếu root object ban đầu. #this tham chiếu evaluation object hiện tại và có thể thay đổi trong selection/projection. Trong biểu thức lồng, hãy dùng #root khi cần dữ liệu của root và #this hoặc property không tiền tố khi cần phần tử hiện tại.

Bean reference @name là namespace riêng, không giống variable #name. Hãy xác thực root object và các biến bắt buộc, xử lý null có chủ đích, và tạo context phù hợp với quyền truy cập mà biểu thức cần.

## Tài liệu tham khảo

- [Spring Framework Reference — Variables](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref/variables.html)
- [Spring Framework Reference — Evaluation Context](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)