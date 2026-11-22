# Ghi tài liệu về context, bean và biến mà expression cần

## Mục tiêu

Sau bài này, bạn có thể lập tài liệu đầy đủ về những dependency mà một biểu thức Spring Expression Language (SpEL) cần để parse và đánh giá; mô tả root object, variables, bean references, functions, property accessors, method resolvers, type conversion và parser configuration; và biến các thông tin đó thành một hợp đồng có thể kiểm tra. Bạn cũng sẽ biết cách ghi rõ kiểu dữ liệu, nullability, quyền truy cập, lifecycle, side effect, lỗi có thể xảy ra và cách khởi tạo EvaluationContext tương ứng.

## 1. Vì sao phải ghi tài liệu dependency của expression?

Một chuỗi SpEL thường ngắn, nhưng có thể phụ thuộc vào nhiều thành phần bên ngoài chuỗi đó. Ví dụ:

~~~text
@pricingService.calculate(#order, #minimumTotal)
~~~

Chỉ nhìn expression này chưa đủ để biết:

- Bean pricingService được đăng ký ở đâu và có alias nào.
- Bean có kiểu gì và method calculate nhận những tham số nào.
- Variable order có kiểu gì, có thể null hay không và chứa dữ liệu nào.
- minimumTotal là BigDecimal, Integer hay một kiểu khác.
- Context có BeanResolver và TypeConverter nào.
- Method có truy cập dữ liệu bên ngoài hoặc thay đổi trạng thái không.
- Expression được đánh giá với root object nào và trong lifecycle nào.

Nếu những thông tin đó không được ghi lại, người bảo trì phải suy đoán từ code hoặc chờ lỗi runtime mới phát hiện dependency bị thiếu. Một expression có thể parse thành công nhưng vẫn thất bại khi context không có biến, bean hoặc accessor cần thiết.

Tài liệu dependency biến expression thành một hợp đồng rõ ràng giữa người viết biểu thức, mã Java khởi tạo context và dữ liệu được truyền vào khi chạy.

## 2. Phân biệt ParserContext với EvaluationContext

Hai context có vai trò khác nhau:

| Thành phần | Trách nhiệm | Thông tin cần ghi |
|---|---|---|
| ParserContext | Quy định cách parser đọc chuỗi, ví dụ template delimiter | Expression thuần hay template, prefix/suffix |
| EvaluationContext | Cung cấp object, variable và cơ chế truy cập khi đánh giá | Root type, variable, resolver, accessor, converter |
| SpelParserConfiguration | Cấu hình hành vi parser và compiler | Compiler mode, auto-grow, giới hạn và ClassLoader |

Ví dụ expression thuần:

~~~java
Expression expression =
    parser.parseExpression("#order.total >= #minimumTotal");
~~~

Ví dụ template:

~~~java
Expression expression = parser.parseExpression(
    "Order #{#order.id} is ready",
    new TemplateParserContext()
);
~~~

TemplateParserContext chỉ cho parser biết phần nào là văn bản literal và phần nào là SpEL. Nó không đăng ký variable, bean hoặc function.

Khi viết tài liệu, cần có hai mục riêng: cấu hình parse và hợp đồng đánh giá. Đừng ghi chung chung rằng expression cần một context mà không chỉ ra đó là ParserContext hay EvaluationContext.

## 3. Ghi rõ root object

Root object là đối tượng được dùng khi đánh giá các property không có tiền tố #. Ví dụ:

~~~text
customer.name
total >= #minimumTotal
#root.id
~~~

Nếu expression được đánh giá với OrderView làm root object, các property như customer và total phải tồn tại trên OrderView hoặc được truy cập qua PropertyAccessor phù hợp.

Tài liệu nên ghi:

- Kiểu root object cụ thể, không chỉ ghi tên khái niệm như Order.
- Những property expression đọc.
- Kiểu của từng property.
- Property có thể null hay không.
- Các object lồng nhau và điều kiện tồn tại của chúng.
- Root object được tạo ở đâu và có bất biến trong lúc đánh giá không.
- Root object có chứa service, entity hoặc dữ liệu nhạy cảm không.

Ví dụ:

| Property | Kiểu | Nullability | Mục đích |
|---|---|---|---|
| id | String | Bắt buộc | Mã đơn hàng |
| total | BigDecimal | Bắt buộc | Tổng tiền đã tính |
| customer | CustomerView | Có thể null | Thông tin khách hàng |
| status | String | Bắt buộc | Trạng thái hiện tại |

Nên ưu tiên một DTO hoặc view nhỏ làm root object. Nếu expression chỉ cần id, total và status, không nên truyền toàn bộ entity có quan hệ tới repository, credential hoặc service.

## 4. Phân biệt property không tiền tố với #variable

SpEL có các namespace khác nhau:

| Cú pháp | Nguồn dữ liệu | Ví dụ |
|---|---|---|
| total | Property của evaluation object hiện tại | total |
| #minimumTotal | Variable trong EvaluationContext | #minimumTotal |
| #root.id | Property của root object ban đầu | #root.id |
| #this.name | Property của evaluation object hiện tại | #this.name |
| @pricingService | Bean được phân giải qua BeanResolver | @pricingService |

Nếu root object có property name và context cũng có variable name, hai cách tham chiếu vẫn khác nhau:

~~~text
name
#name
#root.name
~~~

Tài liệu cần nói rõ mỗi tên thuộc namespace nào. Không ghi một danh sách tên chung như name, order, service mà không chỉ ra cách truy cập.

Với selection và projection, #this có thể chuyển sang phần tử hiện tại, trong khi #root vẫn trỏ tới root object ban đầu. Nếu expression dùng collection operation, hãy ghi rõ property nào đến từ phần tử và property nào đến từ root.

## 5. Lập danh sách variables

Variable được ứng dụng đăng ký vào EvaluationContext và được tham chiếu bằng dấu #.

Ví dụ:

~~~java
context.setVariable("minimumTotal", new BigDecimal("100.00"));
context.setVariable("currentUserId", "U-1024");
context.setVariable("featureEnabled", true);
~~~

Expression:

~~~text
total >= #minimumTotal and #featureEnabled
~~~

Với từng variable, hãy ghi:

| Trường | Ý nghĩa |
|---|---|
| Name | Tên sau dấu # |
| Java type | Kiểu thực tế được đăng ký |
| Required | Có bắt buộc phải có trong context không |
| Nullable | Giá trị có thể null không |
| Meaning | Ý nghĩa nghiệp vụ |
| Source | Thành phần Java cung cấp giá trị |
| Constraints | Miền giá trị, format hoặc giới hạn |
| Lifecycle | Giá trị được tạo/cập nhật ở thời điểm nào |

Ví dụ variable minimumTotal có thể là BigDecimal, bắt buộc, không null và được lấy từ cấu hình chính sách giá. Variable currentUserId có thể là String được lấy từ security context.

Đừng chỉ ghi variable là "number" hoặc "user". Hãy ghi kiểu Java cụ thể và hợp đồng giá trị để người tích hợp không truyền nhầm kiểu.

## 6. Phân biệt variable bắt buộc, tùy chọn và null

Có ba trạng thái cần ghi riêng:

- Variable bắt buộc: phải được đăng ký trước khi đánh giá.
- Variable tùy chọn: có thể không có hoặc có giá trị null theo hợp đồng.
- Variable có giá trị mặc định: expression hoặc Java code quy định rõ cách xử lý khi thiếu.

Ví dụ:

~~~text
#customer != null ? #customer.name : 'Guest'
~~~

Expression này có nhánh xử lý khi customer null, nhưng tài liệu vẫn phải ghi customer có thể null hay không và vì sao.

Không nên coi việc variable chưa đăng ký giống hệt variable đã đăng ký với null. Tùy cách sử dụng, hai trường hợp có thể dẫn tới kết quả hoặc lỗi khác nhau.

Nếu variable bắt buộc, hãy kiểm tra sự hiện diện và kiểu ở Java trước khi gọi getValue. Nếu variable tùy chọn, ghi rõ safe navigation, Elvis hoặc điều kiện null được dùng ở đâu.

## 7. Ghi bean references và alias

Bean reference dùng cú pháp @:

~~~text
@pricingService.calculate(#order)
~~~

Khi context được tạo thủ công, bean reference cần BeanResolver. Với Spring BeanFactory, có thể dùng BeanFactoryResolver:

~~~java
context.setBeanResolver(
    new BeanFactoryResolver(beanFactory)
);
~~~

Tài liệu cho từng bean nên ghi:

| Trường | Ví dụ nội dung |
|---|---|
| Bean name | pricingService |
| Alias | pricing.service nếu có |
| Java type | PricingService |
| Method được expression gọi | calculate(OrderView) |
| Nguồn đăng ký | Spring configuration |
| Scope/lifecycle | singleton, request hoặc scope khác |
| Side effect | Chỉ tính toán hay truy cập hệ thống ngoài |
| Quyền truy cập | Ai được phép dùng expression này |

Nếu tên bean chứa dấu chấm hoặc ký tự đặc biệt, SpEL có thể cần tên được đặt trong string literal, ví dụ:

~~~text
@'pricing.service'.calculate(#order)
~~~

Ghi đúng tên hoặc alias mà container đăng ký. Không suy luận rằng parser tự chuẩn hóa dấu chấm, dấu gạch nối hoặc chữ hoa/thường.

## 8. Không cung cấp bean rộng hơn nhu cầu

Mỗi bean được phơi bày cho expression có thể mở thêm các method và dependency mà expression gọi được.

Nếu expression chỉ cần kết quả tính giá, có thể gọi service trong Java trước rồi truyền kết quả:

~~~java
context.setVariable(
    "calculatedTotal",
    pricingService.calculate(order)
);
~~~

Expression chỉ cần:

~~~text
#calculatedTotal >= #minimumTotal
~~~

Trong tài liệu, hãy giải thích vì sao bean reference được dùng và vì sao không thể truyền một giá trị đã chuẩn bị thay thế. Nếu thực sự cần bean, ghi rõ method nào được gọi, các đối số, side effect và quyền cần thiết.

Không ghi đơn giản rằng expression có quyền truy cập ApplicationContext. Hãy nêu BeanResolver cụ thể và phạm vi bean mà nó có thể phân giải.

## 9. Ghi functions đã đăng ký

Function là Method Java được đăng ký trong EvaluationContext và gọi bằng cú pháp #functionName(...).

Ví dụ:

~~~java
Method normalizeMethod =
    TextFunctions.class.getMethod("normalize", String.class);

context.registerFunction("normalize", normalizeMethod);
~~~

Expression:

~~~text
#normalize(#customerCode)
~~~

Với từng function, hãy ghi:

- Tên function trong SpEL.
- Lớp khai báo Method.
- Chữ ký method đầy đủ.
- Kiểu và thứ tự tham số.
- Kiểu trả về.
- Quy tắc xử lý null.
- Có ném exception nào không.
- Có tác dụng phụ hay không.
- Có được gọi lặp trong selection/projection không.

Function thường dùng static method. Nếu cần gọi method trên service instance có dependency, hãy cân nhắc bean reference hoặc gọi service trong Java.

Function và variable dùng chung namespace. Không đặt variable cùng tên function vì setVariable có thể ghi đè Method đã đăng ký theo cách làm expression không còn gọi được function như dự kiến.

## 10. Ghi PropertyAccessor và quyền đọc/ghi

PropertyAccessor quyết định cách SpEL đọc hoặc ghi property trên target object.

Tài liệu nên ghi:

- Accessor mặc định hoặc custom accessor được đăng ký.
- Target type mà accessor hỗ trợ.
- Property được phép đọc.
- Property được phép ghi.
- Cách xử lý property không tồn tại.
- Cách xử lý target null.
- Accessor có fallback sang accessor khác hay không.

Ví dụ:

| Target type | Property | Đọc | Ghi |
|---|---|---|---|
| OrderView | id | Có | Không |
| OrderView | total | Có | Không |
| OrderView | status | Có | Không |
| OrderEntity | internalNote | Hạn chế | Không |

Nếu expression chỉ đọc dữ liệu, hãy ghi rõ context là read-only. Nếu có assignment hoặc setValue, phải ghi quyền ghi cụ thể và accessor thực hiện kiểm soát.

Không coi setter public là bằng chứng rằng expression được phép ghi. Quyền ghi phụ thuộc context và accessor đang hoạt động.

## 11. Ghi method resolver và các method được gọi

MethodResolver quyết định SpEL có thể tìm và gọi method trên object hay không.

Với StandardEvaluationContext, cần ghi rõ resolver mặc định hoặc resolver tùy chỉnh đang được dùng. Với SimpleEvaluationContext, instance method invocation không được bật mặc định; nếu builder bật khả năng này, phải ghi rõ vì sao cần.

Mỗi method được expression gọi nên có:

- Target type.
- Method name và chữ ký.
- Kiểu đối số.
- Kiểu trả về.
- Quyền truy cập.
- Side effect và thời gian thực thi dự kiến.
- Exception có thể phát sinh.

Một expression đọc dữ liệu có thể vô tình gọi method thay đổi trạng thái nếu object được truyền vào có method đó và context cho phép. Root DTO chỉ có getter giúp giảm phạm vi method có thể truy cập.

## 12. Ghi TypeConverter và quy tắc chuyển đổi

SpEL sử dụng TypeConverter của EvaluationContext khi cần chuyển kết quả, gán property hoặc truyền đối số method sang kiểu đích.

Tài liệu cần ghi:

- TypeConverter cụ thể.
- StandardTypeConverter hay converter tùy chỉnh.
- ConversionService được kết nối nếu có.
- Những cặp kiểu được chuyển đổi.
- Format, locale hoặc timezone liên quan.
- Giá trị null và chuỗi rỗng được xử lý thế nào.
- Lỗi conversion có thể phát sinh.

Ví dụ, expression truyền chuỗi '42' cho method nhận Long. Nếu converter hỗ trợ, SpEL có thể chuyển đối số trước khi gọi method.

Conversion không phải validation. Việc chuỗi chuyển thành Integer thành công không chứng minh số đó nằm trong giới hạn nghiệp vụ. Tài liệu cần ghi riêng quy tắc validation và nơi thực hiện nó.

## 13. Ghi TypeLocator và ConstructorResolver nếu có

Nếu expression dùng type reference hoặc constructor:

~~~text
T(java.time.LocalDate)
new java.math.BigDecimal('125.50')
~~~

hãy ghi TypeLocator và ConstructorResolver đang được sử dụng, kiểu nào được phép tham chiếu và constructor nào có thể được gọi.

Thông tin cần ghi:

- Tên lớp đầy đủ.
- Constructor signature.
- Kiểu và giới hạn đối số.
- Object có được tạo mỗi lần evaluate không.
- Constructor có I/O hoặc side effect không.
- Ai chịu trách nhiệm quản lý lifecycle và đóng tài nguyên.
- Có allowlist hoặc giới hạn package/type không.

Nếu expression không cần tạo object, ghi rõ constructor invocation không được cung cấp hoặc không nằm trong yêu cầu. Không cấp context rộng chỉ để tiện cho một biểu thức đọc property.

## 14. Ghi parser configuration

Expression có thể phụ thuộc vào SpelParserConfiguration:

- Compiler mode: OFF, IMMEDIATE hoặc MIXED.
- ClassLoader dùng cho compiled expression.
- Auto-grow null references.
- Auto-grow collections.
- Maximum auto-grow size.
- ParserContext và template delimiter.

Nếu expression được parse như template, ghi rõ prefix/suffix. Nếu dùng compiler, ghi mode và điều kiện kiểu dữ liệu cần ổn định.

Parser configuration không thay thế EvaluationContext. Hãy ghi hai phần riêng để người vận hành biết chuỗi được parse thế nào và expression được đánh giá với những quyền/dữ liệu nào.

## 15. Ghi collection shape và dữ liệu lồng nhau

Nếu expression dùng selection hoặc projection, tài liệu cần mô tả cấu trúc collection:

~~~text
#orders.?[total >= #minimumTotal].![id]
~~~

Ví dụ hợp đồng:

| Dữ liệu | Kiểu | Điều kiện |
|---|---|---|
| orders | List<OrderView> | Có thể rỗng, không null |
| phần tử | OrderView | Không null |
| total | BigDecimal | Không null |
| id | String | Bắt buộc |
| minimumTotal | BigDecimal | Bắt buộc |

Ghi rõ collection có thể null hay rỗng, có thứ tự hay không, phần tử có thể null không và kết quả khi không có phần tử phù hợp.

Selection thường trả về collection rỗng nếu không có phần tử phù hợp. First/last selection có thể trả về null khi không tìm thấy phần tử. Projection tạo kết quả cho các phần tử nguồn và không tự lọc chúng.

Nếu expression dùng #this, ghi rõ #this đang đại diện phần tử nào ở mỗi cấp lồng nhau. Nếu cần dữ liệu root trong collection operation, ghi rõ tham chiếu #root.

## 16. Ghi kiểu kết quả và hợp đồng đầu ra

Mỗi expression nên có kiểu kết quả mong đợi:

- String cho message hoặc nhãn.
- Boolean cho điều kiện.
- BigDecimal cho phép tính tiền.
- Collection cho selection/projection.
- Object hoặc DTO nếu expression tạo cấu trúc dữ liệu.

Ghi thêm:

- Có thể trả null không.
- Có cần getValue(context, targetType) không.
- Có conversion ở đầu ra không.
- Collection có kiểu phần tử nào.
- Giá trị có được dùng để ghi dữ liệu hoặc quyết định nghiệp vụ không.

Ví dụ expression:

~~~text
total >= #minimumTotal
~~~

có hợp đồng đầu ra Boolean. Nếu ứng dụng yêu cầu Boolean không null, hãy xác định cách xử lý khi total hoặc minimumTotal null thay vì để người gọi tự suy đoán.

Với BigDecimal, ghi rõ scale, currency và quy tắc làm tròn ở tầng nghiệp vụ nếu kết quả được dùng cho tiền.

## 17. Ví dụ tài liệu dependency hoàn chỉnh

Một bản ghi expression có thể có cấu trúc như sau:

~~~text
Expression ID: order-eligibility-v1
Purpose: Kiểm tra đơn hàng có đạt ngưỡng tối thiểu hay không
Source: total >= #minimumTotal and active

Parser:
  Type: Standard SpelExpressionParser
  ParserContext: Expression thuần
  CompilerMode: OFF

Root object:
  Type: OrderView
  Properties:
    total: BigDecimal, required
    active: boolean
  Mutable: No

Variables:
  minimumTotal:
    Type: BigDecimal
    Required: Yes
    Nullable: No
    Source: PricingPolicy

Beans:
  None

Functions:
  None

Access:
  PropertyAccessor: Read-only data binding
  Method invocation: Not required
  BeanResolver: Not configured
  Type reference: Not required
  Constructor invocation: Not required

Conversion:
  StandardTypeConverter
  No custom conversion required

Result:
  Type: Boolean
  Nullable: No

Errors:
  Missing root property
  Missing minimumTotal variable
  Incompatible total type
~~~

Đây là ví dụ minh họa cách ghi hợp đồng. Giá trị thực tế phải lấy từ expression và cách ứng dụng tạo context, không sao chép các tên hoặc kiểu ví dụ nếu dự án dùng cấu trúc khác.

## 18. Ví dụ Java khởi tạo context theo hợp đồng

Giả sử expression chỉ cần OrderView và minimumTotal:

~~~java
public record OrderView(
        BigDecimal total,
        boolean active) {
}

public Expression createEligibilityExpression() {
    return new SpelExpressionParser().parseExpression(
        "active and total >= #minimumTotal"
    );
}

public Boolean evaluate(
        Expression expression,
        OrderView order,
        BigDecimal minimumTotal) {

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    context.setVariable("minimumTotal", minimumTotal);

    return expression.getValue(
        context,
        order,
        Boolean.class
    );
}
~~~

Hợp đồng của đoạn code:

- Root type là OrderView.
- total là BigDecimal và active là boolean.
- minimumTotal là variable bắt buộc, kiểu BigDecimal.
- Không cần bean reference hoặc function.
- Không cần ghi property hoặc gọi method.
- Kết quả là Boolean.

Nếu expression thay đổi để dùng bean, function hoặc method, phải cập nhật cả code tạo context và tài liệu dependency. Không để expression mới phụ thuộc một capability mà context chưa cung cấp.

## 19. Lifecycle và phạm vi chia sẻ context

Tài liệu cần nói rõ Expression và EvaluationContext được tạo, lưu và tái sử dụng như thế nào.

Thông thường có thể parse một expression cố định một lần rồi tái sử dụng. EvaluationContext lại có thể chứa root object và variables thay đổi theo request.

Nếu context mutable được chia sẻ giữa nhiều request, một request có thể ghi đè variable hoặc root object mà request khác đang sử dụng. Điều đó có thể gây rò rỉ dữ liệu hoặc kết quả không xác định.

Hãy ghi:

- Expression được parse khi khởi động, khi nạp cấu hình hay theo request.
- Parser có được dùng chung không.
- Context được tạo theo request, transaction hay job.
- Variables được cập nhật ở đâu.
- Context có mutable state hay không.
- Có resolver hoặc accessor giữ state không.
- Ai chịu trách nhiệm tạo và giải phóng tài nguyên.

Ưu tiên Expression được tái sử dụng cùng EvaluationContext riêng cho đơn vị xử lý cần dữ liệu riêng. Không chia sẻ context mutable nếu không có thiết kế đồng bộ và cô lập rõ ràng.

## 20. Ghi lỗi cấu hình và lỗi runtime dự kiến

Mỗi expression nên ghi các lỗi có thể phát sinh và cách phân loại:

| Lỗi | Nhóm | Nơi kiểm tra |
|---|---|---|
| Sai cú pháp | Parse/configuration | Khi nạp expression |
| Thiếu variable | Context setup hoặc runtime | Trước evaluate |
| Bean name sai | Dependency/configuration | Khi tạo context hoặc evaluate |
| Property không tồn tại | Hợp đồng model/accessor | Test theo root type |
| Property null | Dữ liệu runtime | Khi evaluate |
| Conversion thất bại | Dữ liệu hoặc converter config | Khi chuyển kiểu |
| Giá trị ngoài giới hạn | Validation nghiệp vụ | Sau conversion |
| Method ném exception | Logic method/runtime | Trong evaluate |

Ghi rõ exception type hoặc cause quan trọng, expression identifier và nơi chịu trách nhiệm xử lý. Không ghi toàn bộ object, password, token hoặc dữ liệu nhạy cảm vào log.

Nếu expression là cấu hình cố định, parse và kiểm tra dependency càng sớm càng tốt. Nếu expression phụ thuộc dữ liệu request, kiểm tra các phần tĩnh trước và xử lý dữ liệu cụ thể tại ranh giới nghiệp vụ.

## 21. Ghi quyền truy cập và rủi ro bảo mật

Context là một phần của ranh giới bảo mật. Tài liệu cần ghi:

- Root object có chứa dữ liệu nhạy cảm không.
- Property nào được phép đọc hoặc ghi.
- Method nào có thể được gọi.
- Bean nào được phân giải.
- Function nào được đăng ký.
- Có cho phép type reference hoặc constructor invocation không.
- Expression đến từ code, file cấu hình, quản trị viên hay người dùng.
- Ai có quyền thay đổi expression.
- Output có được đưa vào HTML, email, SQL hoặc URL không.

Với expression không đáng tin cậy, ưu tiên root object nhỏ, context chỉ đọc và không cung cấp bean hoặc method có tác dụng phụ. Không coi ParserContext hoặc việc parse thành công là sandbox.

Nếu kết quả được chèn vào HTML/email, cần encode theo ngữ cảnh đầu ra. SpEL không tự escape nội dung.

## 22. Kiểm thử hợp đồng dependency

Tài liệu dependency cần đi cùng test để tránh bị lỗi thời.

Positive tests xác nhận:

- Root object đúng kiểu được truy cập.
- Mọi variable bắt buộc được đăng ký.
- Bean/function cần thiết được phân giải.
- Property và method được truy cập đúng.
- Kiểu kết quả và giá trị đầu ra đúng.

Negative tests xác nhận:

- Thiếu variable bắt buộc được phát hiện.
- Bean ngoài allowlist không được phân giải.
- Property không được phép đọc/ghi bị từ chối.
- Method không cần thiết không thể gọi.
- Constructor hoặc type reference ngoài phạm vi bị từ chối.
- Dữ liệu null hoặc sai kiểu được xử lý theo hợp đồng.

Ví dụ kiểm tra expression parse và đánh giá:

~~~java
@Test
void eligibilityExpressionUsesDocumentedInputs() {
    Expression expression =
        new SpelExpressionParser().parseExpression(
            "active and total >= #minimumTotal"
        );

    SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding().build();

    context.setVariable(
        "minimumTotal",
        new BigDecimal("100.00")
    );

    OrderView order = new OrderView(
        new BigDecimal("125.00"),
        true
    );

    assertEquals(
        Boolean.TRUE,
        expression.getValue(context, order, Boolean.class)
    );
}
~~~

Ngoài test kết quả, hãy test context thiếu variable và dữ liệu biên. Một test parse thành công không chứng minh các dependency đã được đăng ký đầy đủ.

## 23. Quản lý thay đổi và version của expression

Khi expression thay đổi, dependency contract có thể thay đổi theo. Ví dụ thêm `@pricingService.calculate(...)` sẽ bổ sung bean dependency; thêm `#discountRate` sẽ bổ sung variable; thêm `new SomeType(...)` sẽ bổ sung constructor dependency.

Nên gắn identifier và version cho expression được lưu ngoài code. Mỗi lần thay đổi, cập nhật:

- Expression source.
- Root object type và property paths.
- Variable names, types và nullability.
- Bean names, aliases và method signatures.
- Function signatures.
- Accessor/resolver/converter configuration.
- Result type.
- Security review và test liên quan.

Không chỉ sửa chuỗi expression mà quên cập nhật code tạo context. Ngược lại, không thêm bean hoặc function vào context mà không ghi lý do và dependency sử dụng.

Có thể dùng version để xác định chính xác expression nào đang được triển khai khi điều tra lỗi runtime.

## 24. Mẫu bảng dependency để dùng cho mỗi expression

Một mẫu ngắn gọn có thể dùng thống nhất:

| Mục | Nội dung cần điền |
|---|---|
| Expression ID/version | Tên ổn định và revision |
| Purpose | Mục đích nghiệp vụ |
| Source | Chuỗi SpEL hoặc template |
| ParserContext | Expression thuần hay template; delimiter |
| Parser configuration | Compiler mode, auto-grow, ClassLoader |
| Root object | Kiểu, property paths, nullability |
| Variables | Name, Java type, required, nullable, source |
| Beans | Name/alias, type, methods, scope, side effects |
| Functions | Name, Method signature, arguments, return type |
| Property access | Accessor, read/write allowlist |
| Method access | Resolver và method được phép |
| Type conversion | TypeConverter, ConversionService, custom rules |
| Type/constructor | TypeLocator, ConstructorResolver, allowed types |
| Result | Kiểu, nullability, collection shape |
| Errors | Parse, context, conversion, runtime, validation |
| Security | Nguồn expression, quyền sửa, dữ liệu nhạy cảm |
| Lifecycle | Parse, context creation, reuse, cleanup |
| Tests | Positive, negative, null, boundary, missing dependency |

Không cần mọi expression dùng hết mọi capability. Với mục không áp dụng, ghi rõ "Không dùng" thay vì bỏ trống khiến người đọc không biết đã xem xét hay chưa.

## 25. Ghi nhớ

Một expression chỉ hoạt động đúng khi chuỗi nguồn, ParserContext, EvaluationContext và dữ liệu runtime khớp với nhau. Hãy ghi riêng root object, variables, bean references, functions, property accessors, method resolvers, TypeConverter, TypeLocator, ConstructorResolver và parser configuration.

Với mỗi dependency, ghi tên chính xác, Java type, nullability, nguồn cung cấp, lifecycle, quyền truy cập và lỗi có thể phát sinh. Phân biệt property không tiền tố với #variable, #root với #this, và @bean với function #name.

Ưu tiên root DTO nhỏ, variables có kiểu rõ ràng và context chỉ cung cấp capability cần thiết. Nếu expression không cần bean, method, constructor hoặc ghi property, hãy ghi rõ các khả năng đó không được sử dụng. Tài liệu phải đi cùng positive/negative tests để thay đổi expression không vô tình mở rộng quyền hoặc làm thiếu dependency.

## Tài liệu tham khảo

- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [EvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationContext.html)
- [StandardEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardEvaluationContext.html)
- [SimpleEvaluationContext Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/SimpleEvaluationContext.html)
- [BeanResolver Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/BeanResolver.html)
- [PropertyAccessor Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/PropertyAccessor.html)