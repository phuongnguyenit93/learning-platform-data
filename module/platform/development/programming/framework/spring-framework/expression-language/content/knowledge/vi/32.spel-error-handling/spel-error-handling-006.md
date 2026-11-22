# Phân biệt lỗi cấu hình với lỗi dữ liệu runtime

## Mục tiêu

Sau bài này, bạn có thể phân biệt lỗi phát sinh do cấu hình ứng dụng với lỗi do dữ liệu hoặc trạng thái tại thời điểm chạy khi dùng Spring Expression Language (SpEL); nhận biết lỗi parse, lỗi đánh giá, lỗi phân giải property/method/bean và lỗi chuyển đổi kiểu; xác định thời điểm nên phát hiện từng nhóm lỗi; và thiết kế cách xử lý, ghi log, trả thông báo phù hợp. Bạn cũng sẽ biết cách kiểm tra expression và EvaluationContext khi khởi động để tránh đưa lỗi cấu hình có thể phát hiện sớm tới request thật.

## 1. Hai nhóm nguyên nhân cần phân biệt

Một biểu thức SpEL có thể thất bại vì cấu hình của ứng dụng không đúng hoặc vì dữ liệu runtime không đáp ứng điều kiện mà biểu thức yêu cầu.

**Lỗi cấu hình** xuất phát từ cách ứng dụng định nghĩa, phân tích hoặc thiết lập môi trường đánh giá. Ví dụ: chuỗi expression sai cú pháp, thiếu BeanResolver, tên bean cấu hình sai, property accessor không hỗ trợ kiểu object, function chưa được đăng ký hoặc cấu hình parser không phù hợp.

**Lỗi dữ liệu runtime** xuất phát từ giá trị cụ thể được đưa vào khi đánh giá. Ví dụ: biến bắt buộc là null, property trung gian không tồn tại trên dữ liệu hiện tại, index vượt phạm vi, chuỗi không chuyển được thành số hoặc trạng thái đơn hàng không đáp ứng điều kiện nghiệp vụ.

| Nhóm | Nguyên nhân điển hình | Thời điểm thường phát hiện |
|---|---|---|
| Cấu hình | Expression sai cú pháp | Khi parse hoặc khởi tạo bean |
| Cấu hình | Thiếu BeanResolver cho biểu thức dùng @bean | Khi đánh giá; nên phát hiện lúc khởi động |
| Cấu hình | Function chưa đăng ký hoặc đăng ký sai Method | Khi đánh giá; nên kiểm tra khi tạo context |
| Cấu hình | PropertyAccessor/MethodResolver không phù hợp | Khi đánh giá trên kiểu object tương ứng |
| Runtime | Biến hoặc property có giá trị null | Khi đánh giá với dữ liệu cụ thể |
| Runtime | Index không tồn tại | Khi truy cập collection hoặc array |
| Runtime | Giá trị không chuyển đổi được | Khi converter được yêu cầu |
| Runtime/nghiệp vụ | Trạng thái hoặc giá trị không hợp lệ | Khi kiểm tra quy tắc nghiệp vụ |

Không phải mọi lỗi cấu hình đều xuất hiện ngay khi parse. Parser chỉ kiểm tra cấu trúc ngôn ngữ; một số lỗi liên quan đến resolver, kiểu object và quyền truy cập chỉ lộ ra khi expression được đánh giá. Vì vậy, cần chủ động kiểm tra các phụ thuộc của expression bằng dữ liệu và context đại diện.

## 2. Parse và evaluate là hai giai đoạn khác nhau

SpEL thường có hai bước chính:

1. Parse chuỗi nguồn thành một đối tượng Expression.
2. Đánh giá Expression với EvaluationContext và root object cụ thể.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#order.total >= #minimum");

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("order", order);
context.setVariable("minimum", new BigDecimal("100.00"));

Boolean accepted =
    expression.getValue(context, Boolean.class);
~~~

Nếu chuỗi thiếu dấu ngoặc hoặc toán tử không hợp lệ, lỗi xảy ra ở parseExpression(). Nếu chuỗi parse thành công nhưng biến order chưa được đăng ký, hoặc order là null khi truy cập total, lỗi xảy ra trong getValue().

Một expression parse thành công không chứng minh expression sẽ chạy được với mọi context. Nó chỉ chứng minh parser có thể tạo cấu trúc biểu thức từ chuỗi nguồn.

Với expression cố định trong cấu hình, hãy parse và kiểm tra các phụ thuộc càng sớm càng tốt. Khi request đến, chỉ cung cấp dữ liệu runtime hợp lệ và thực hiện đánh giá.

## 3. Lỗi cú pháp và lỗi parse

Lỗi parse thường cho thấy chuỗi expression không tuân theo cú pháp SpEL. Các nguyên nhân phổ biến:

- Thiếu dấu ngoặc đóng hoặc mở.
- Literal chuỗi không cân bằng dấu nháy.
- Dùng sai toán tử hoặc viết sai vị trí token.
- Sai cú pháp selection, projection hoặc template delimiter.
- Gọi constructor hoặc function với cú pháp không hợp lệ.
- Trộn văn bản literal và SpEL nhưng không dùng ParserContext dạng template.

Ví dụ sai:

~~~text
#order.total >=
~~~

Ví dụ đúng:

~~~text
#order.total >= #minimum
~~~

Có thể bắt lỗi parse ở bước nạp cấu hình:

~~~java
try {
    Expression expression = parser.parseExpression(source);
}
catch (ParseException ex) {
    // Báo lỗi cấu hình expression.
}
~~~

Trong SpEL, lỗi parse cụ thể thường được biểu diễn bởi SpelParseException, thuộc hệ thống ParseException của Spring Expression. Hãy giữ thông tin vị trí lỗi và message gốc để người cấu hình biết token nào cần sửa.

Không nên đợi đến khi một request hiếm gặp mới parse một expression cố định. Nếu expression được lưu trong file cấu hình hoặc database, hãy xác thực nó khi ứng dụng nạp cấu hình hoặc khi quản trị viên lưu thay đổi.

## 4. Lỗi cấu hình Parser và ParserContext

Parser được tạo với SpelParserConfiguration và có thể dùng ParserContext để xác định cách đọc template. Nếu cấu hình không phù hợp, expression có thể thất bại ngay từ đầu hoặc hoạt động khác mong đợi.

Ví dụ, một chuỗi template có văn bản thường và đoạn SpEL:

~~~text
Hello, #{#customer.name}!
~~~

Cần parse bằng TemplateParserContext:

~~~java
Expression expression = parser.parseExpression(
    template,
    new TemplateParserContext()
);
~~~

Nếu parse chuỗi đó như expression thông thường, parser cố coi toàn bộ câu là cú pháp SpEL và có thể báo lỗi.

Các vấn đề cấu hình khác gồm compiler mode, auto-grow, giới hạn kích thước auto-grow, classloader và cấu hình parser dành cho phiên bản Spring đang chạy. Hãy quản lý parser theo cấu hình rõ ràng và không dùng lẫn parser có ParserContext hoặc compiler mode khác nhau mà không chủ ý.

ParserContext quyết định cách phân tách chuỗi khi parse; nó không cung cấp biến, bean hoặc quyền truy cập khi đánh giá. Những phần đó thuộc EvaluationContext.

## 5. Lỗi thiếu hoặc sai EvaluationContext

EvaluationContext cung cấp root object, variable và các cơ chế truy cập như PropertyAccessor, MethodResolver, BeanResolver, TypeConverter và function đã đăng ký.

Một expression có thể parse đúng nhưng không chạy được nếu context thiếu thành phần cần thiết.

Ví dụ expression dùng variable:

~~~text
#minimumTotal
~~~

Nếu Java không gọi setVariable("minimumTotal", value), biểu thức không có dữ liệu như dự kiến.

Ví dụ expression tham chiếu bean:

~~~text
@pricingService.calculate(#order)
~~~

Nếu context được tạo thủ công nhưng không đăng ký BeanResolver, SpEL không thể phân giải bean reference.

Ví dụ expression gọi function:

~~~text
#normalize(#input)
~~~

Nếu function normalize chưa được đăng ký bằng registerFunction() hoặc cơ chế tương ứng của phiên bản Spring, việc đánh giá sẽ thất bại.

Hãy lập danh sách phụ thuộc của từng expression: root type, variable names, bean names, function names và khả năng truy cập cần thiết. Khởi tạo context với các phụ thuộc đó một cách có chủ đích.

## 6. Phân biệt thiếu cấu hình với thiếu dữ liệu

Cùng một lỗi truy cập có thể xuất hiện do hai nguyên nhân khác nhau.

Ví dụ:

~~~text
#order.customer.name
~~~

Nếu biến order chưa được đăng ký trong context, đây là lỗi chuẩn bị context. Nếu biến được đăng ký nhưng giá trị order là null, đó là dữ liệu runtime không có object. Nếu order tồn tại nhưng model thực tế không có property customer, có thể là lỗi hợp đồng kiểu dữ liệu hoặc thay đổi model.

Khi điều tra, hãy kiểm tra theo thứ tự:

1. Expression source có đúng không?
2. Context có chứa biến bắt buộc không?
3. Root object và variable có đúng kiểu dự kiến không?
4. Giá trị cụ thể có null ở bước nào?
5. PropertyAccessor có hỗ trợ target type và property đó không?
6. Property hoặc getter có thể đọc được không?

Không nên gộp mọi lỗi thành thông báo "SpEL expression failed". Cần giữ đủ thông tin để biết lỗi nằm ở cấu hình hay ở dữ liệu của một lần xử lý.

## 7. Lỗi property không tồn tại hoặc không truy cập được

Một expression có thể truy cập property trên root object hoặc object được lưu trong variable:

~~~text
#customer.profile.displayName
~~~

Lỗi có thể xảy ra khi:

- Kiểu object không có property profile.
- PropertyAccessor không hỗ trợ kiểu object.
- Getter hoặc property không thể truy cập theo cấu hình hiện tại.
- Object trung gian null.
- Model đã thay đổi nhưng expression chưa được cập nhật.

Nếu mọi customer trong hệ thống đều phải có profile theo hợp đồng dữ liệu, việc property không tồn tại có thể là lỗi model hoặc cấu hình. Nếu chỉ một bản ghi bị thiếu profile, đó có thể là dữ liệu runtime cần xử lý theo quy tắc nghiệp vụ.

Hãy phân biệt "property không tồn tại" với "property tồn tại nhưng giá trị null". Hai trường hợp cần cách sửa khác nhau.

Với expression dùng lâu dài, nên kiểm tra chúng trên các kiểu root object thực tế khi khởi động hoặc trong bộ kiểm thử cấu hình.

## 8. Lỗi method invocation và function

Một expression có thể gọi method trên root object, variable hoặc bean:

~~~text
#order.calculateTotal()
@pricingService.calculate(#order)
#normalize(#code)
~~~

Các lỗi có thể gồm:

- Method không tồn tại trên kiểu object thực tế.
- MethodResolver không cho phép lời gọi.
- Số lượng hoặc kiểu đối số không phù hợp.
- Function chưa đăng ký hoặc Method được đăng ký sai.
- Method ném exception trong quá trình thực thi.
- Method có tác dụng phụ hoặc phụ thuộc trạng thái bên ngoài.

Cần phân biệt lỗi tìm và gọi method với exception do chính method phát sinh. Ví dụ, method calculateTotal() có thể được tìm thấy và gọi thành công, nhưng bên trong nó ném lỗi vì dữ liệu đơn hàng thiếu.

Ở giai đoạn cấu hình, kiểm tra method/function mà expression cần. Ở runtime, ghi nhận exception gốc từ method cùng ngữ cảnh nghiệp vụ cần thiết, nhưng tránh ghi dữ liệu nhạy cảm.

## 9. Lỗi bean reference và alias

Biểu thức dùng @beanName phụ thuộc BeanResolver và tên bean trong container.

Ví dụ:

~~~text
@'order.service'.calculate(#order)
~~~

Các nguyên nhân có thể gồm:

- Context thủ công không có BeanResolver.
- Bean name hoặc alias không tồn tại.
- Tên bean chứa ký tự đặc biệt nhưng không được đặt trong string literal đúng cách.
- Bean tồn tại nhưng không thể khởi tạo do dependency khác bị lỗi.
- Bean được tìm thấy nhưng method tiếp theo không tồn tại hoặc không được phép gọi.

Nếu bean name sai trong cấu hình cố định, hãy coi đó là lỗi cấu hình và phát hiện khi khởi tạo ứng dụng. Nếu bean có scope hoặc dependency chỉ được tạo khi truy cập, lỗi có thể chỉ xuất hiện ở lần evaluate đầu tiên.

Không nên thay lỗi phân giải bean bằng null rồi tiếp tục tính toán. Điều đó có thể che giấu lỗi triển khai và tạo kết quả sai.

## 10. Lỗi conversion khác lỗi validation

SpEL có thể cần TypeConverter khi lấy kết quả theo kiểu đích, gán property hoặc truyền đối số vào method.

Ví dụ:

~~~java
Expression expression = parser.parseExpression("'abc'");
Integer value = expression.getValue(Integer.class);
~~~

Chuỗi abc không thể chuyển thành Integer bằng converter phù hợp nên việc đánh giá thất bại ở bước conversion.

Một trường hợp khác:

~~~text
#quantity >= 1
~~~

Nếu quantity là Integer 500, expression có thể chạy bình thường. Việc quantity vượt giới hạn nghiệp vụ là vấn đề validation, không phải lỗi conversion hoặc parse.

Hãy phân biệt:

- Conversion error: không thể chuyển giá trị sang kiểu cần thiết.
- Validation error: giá trị đã có kiểu phù hợp nhưng không đáp ứng quy tắc.
- Configuration error: converter cần thiết chưa được đăng ký hoặc cấu hình sai.
- Runtime data error: dữ liệu cụ thể không thể chuyển đổi hoặc có trạng thái không phù hợp.

Không dùng giá trị mặc định tùy tiện khi conversion thất bại, vì điều đó có thể biến dữ liệu sai thành kết quả trông hợp lệ.

## 11. Lỗi null, index và dữ liệu runtime

Những lỗi runtime thường gặp xuất phát từ giá trị thực tế:

- Root object là null.
- Variable có giá trị null.
- Property trung gian null.
- Collection rỗng hoặc index vượt phạm vi.
- Map không chứa key được yêu cầu.
- Phần tử collection có kiểu khác với dự kiến.
- Dữ liệu chuỗi sai định dạng.

Ví dụ:

~~~text
#orders[0].id
~~~

Expression giả định orders có phần tử đầu tiên và phần tử đó có property id. Nếu orders rỗng, null hoặc phần tử đầu là null, đánh giá có thể thất bại.

Nếu trường hợp thiếu dữ liệu được phép, hãy biểu diễn rõ trong expression:

~~~text
#customer?.profile?.displayName ?: 'Guest'
~~~

Nếu dữ liệu là bắt buộc, hãy xác thực trước khi gọi SpEL hoặc để lỗi runtime được chuyển thành lỗi nghiệp vụ có ý nghĩa. Không nên dùng safe navigation để che giấu một vi phạm hợp đồng dữ liệu bắt buộc.

## 12. Lỗi cấu hình compiler và compiled expression

SpEL compiler có thể thay đổi cách expression được thực thi. Một expression có thể chạy ở interpreted mode nhưng gặp vấn đề khi compiled do kiểu dữ liệu runtime không còn phù hợp với giả định của bản compiled hoặc do cấu trúc expression không được hỗ trợ.

Cần phân biệt:

- Compiler mode không phù hợp hoặc classloader sai là vấn đề cấu hình.
- Kiểu object thay đổi hợp lệ giữa các lần đánh giá có thể là điều kiện runtime.
- Expression không được hỗ trợ compilation có thể tiếp tục chạy interpreted.
- Lỗi nghiệp vụ do getter hoặc method không tự biến thành lỗi cấu hình compiler.

Khi điều tra, hãy thử cùng expression ở OFF để xác định lỗi có phụ thuộc compiled mode hay không. Kiểm tra kiểu root object, kiểu variable và các implementation được dùng trong runtime.

MIXED mode có cơ chế quay lại interpreted trong một số tình huống compiled expression không còn phù hợp. Không coi cơ chế đó là bộ xử lý mọi exception hoặc mọi lỗi dữ liệu.

## 13. Phân loại exception của Spring Expression

Các exception thường gặp thuộc hệ thống exception của Spring Expression:

| Loại | Vai trò |
|---|---|
| ParseException | Lỗi khi phân tích cú pháp expression |
| SpelParseException | Dạng lỗi parse cụ thể của SpEL, có thông tin vị trí |
| EvaluationException | Lỗi trong quá trình đánh giá expression |
| SpelEvaluationException | Dạng lỗi đánh giá cụ thể của SpEL |

Trong Java, có thể bắt ParseException ở giai đoạn parse và EvaluationException ở giai đoạn evaluate:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
}
catch (ParseException ex) {
    throw new IllegalStateException(
        "Invalid SpEL configuration", ex
    );
}

try {
    Object result = expression.getValue(context);
}
catch (EvaluationException ex) {
    throw new IllegalArgumentException(
        "Unable to evaluate expression for current data", ex
    );
}
~~~

Đoạn code minh họa cách phân tách ranh giới xử lý. Trong ứng dụng thực tế, exception có thể được bọc bởi bean creation, configuration loading hoặc tầng service. Hãy giữ cause chain để không mất nguyên nhân ban đầu.

Không nên chỉ bắt RuntimeException chung ở mọi nơi rồi trả về null. Việc đó làm mất thông tin phân biệt giữa lỗi cấu hình, dữ liệu và lỗi lập trình.

## 14. Phát hiện lỗi cấu hình khi khởi động

Với expression được khai báo trong file cấu hình, annotation hoặc database, nên kiểm tra càng sớm càng tốt.

Một quy trình khởi động có thể gồm:

1. Nạp danh sách expression.
2. Parse từng expression với đúng ParserContext.
3. Tạo EvaluationContext có resolver và accessor tương ứng.
4. Kiểm tra các variable, bean và function bắt buộc đã được đăng ký.
5. Đánh giá bằng dữ liệu kiểm thử đại diện hoặc object mẫu phù hợp.
6. Báo lỗi cấu hình có tên expression và vị trí khai báo.
7. Không đưa expression sai cấu hình vào luồng xử lý production.

Không phải expression nào cũng có thể đánh giá hoàn chỉnh khi khởi động vì nó phụ thuộc dữ liệu request. Trong trường hợp đó, hãy kiểm tra parse, kiểu và các phụ thuộc tĩnh trước; kiểm tra dữ liệu cụ thể ở runtime.

Có thể tạo một component khởi tạo hoặc bước validation cấu hình riêng để thực hiện các kiểm tra này. Tránh gọi service thật hoặc tạo tác dụng phụ chỉ để thử expression khi ứng dụng khởi động.

## 15. Xử lý lỗi runtime tại ranh giới phù hợp

Lỗi runtime nên được xử lý tại nơi ứng dụng hiểu được ý nghĩa của dữ liệu.

Ví dụ, một service nhận order rồi đánh giá điều kiện:

~~~java
public boolean isEligible(Order order) {
    if (order == null) {
        throw new IllegalArgumentException("Order is required");
    }

    StandardEvaluationContext context =
        new StandardEvaluationContext(order);

    context.setVariable(
        "minimumTotal",
        new BigDecimal("100.00")
    );

    return eligibilityExpression.getValue(
        context,
        Boolean.class
    );
}
~~~

Nếu order là null, service có thể từ chối ngay với lỗi đầu vào rõ ràng. Nếu expression thất bại do cấu hình đã được kiểm tra khi khởi động, đó có thể là lỗi nội bộ cần ghi log mức phù hợp và cảnh báo vận hành.

Đừng biến mọi EvaluationException thành lỗi người dùng. Một số lỗi là bug hoặc misconfiguration cần được xử lý như lỗi server; một số lỗi là dữ liệu đầu vào không hợp lệ và cần thông báo có thể sửa.

## 16. Ghi log đủ thông tin nhưng không lộ dữ liệu nhạy cảm

Log hữu ích cần cho biết:

- Expression identifier hoặc tên cấu hình.
- Giai đoạn lỗi: parse, context setup, evaluate hay conversion.
- Loại exception và cause chain.
- Loại root object và phiên bản cấu hình liên quan.
- Request correlation ID hoặc mã công việc nếu có.
- Vị trí parse error khi có.
- Nhóm dữ liệu đầu vào liên quan ở dạng đã được làm sạch.

Tránh ghi toàn bộ expression nếu nó chứa bí mật, token hoặc dữ liệu cá nhân. Không ghi nguyên object root, password, access token hoặc nội dung nhạy cảm vào log.

Với expression cố định, dùng một identifier ổn định để tìm cấu hình nguồn. Với expression do quản trị viên tạo, ghi version hoặc revision của template để xác định bản nào gây lỗi.

Thông báo cho người dùng nên ngắn gọn và không tiết lộ chi tiết nội bộ như tên bean, package, classloader hoặc cấu trúc domain object.

## 17. Không dùng fallback để che giấu lỗi cấu hình

Một số ứng dụng có thể muốn trả về giá trị mặc định khi expression thất bại. Điều này chỉ phù hợp khi mặc định là hành vi nghiệp vụ đã được xác định.

Ví dụ:

~~~text
#customer?.nickname ?: 'Customer'
~~~

Đây là fallback rõ ràng cho trường hợp nickname null.

Nhưng nếu @pricingService không tồn tại hoặc function normalize chưa đăng ký, trả về 0 hoặc chuỗi rỗng có thể che giấu lỗi cấu hình. Kết quả đó có thể tiếp tục đi vào hóa đơn, quyết định giá hoặc thông báo sai.

Hãy phân biệt fallback cho dữ liệu tùy chọn với việc nuốt exception. Fallback nên được viết rõ trong expression hoặc logic Java và chỉ áp dụng cho các trạng thái đã được chấp thuận.

## 18. Kiểm thử riêng hai nhóm lỗi

Nên tổ chức kiểm thử theo nguyên nhân:

| Nhóm | Tình huống | Kết quả mong đợi |
|---|---|---|
| Cấu hình | Expression sai cú pháp | Parse thất bại trước runtime |
| Cấu hình | Thiếu BeanResolver | Kiểm tra cấu hình phát hiện |
| Cấu hình | Sai bean name | Validation cấu hình hoặc test context thất bại |
| Cấu hình | Function chưa đăng ký | Kiểm tra phụ thuộc phát hiện |
| Cấu hình | Accessor không hỗ trợ kiểu | Test với target type thất bại rõ ràng |
| Cấu hình | Compiler/classloader không phù hợp | Phát hiện trong kiểm thử chế độ compiler |
| Runtime | Variable null | Theo hợp đồng null đã xác định |
| Runtime | Property trung gian null | Safe navigation hoặc lỗi nghiệp vụ rõ |
| Runtime | Index vượt phạm vi | Lỗi dữ liệu được xử lý phù hợp |
| Runtime | Chuỗi sai định dạng số | Conversion error |
| Runtime | Giá trị ngoài min/max | Validation error |
| Runtime | Method ném exception | Cause chain được giữ lại |

Cấu hình nên có unit test hoặc integration test độc lập với dữ liệu request. Runtime nên có test cho dữ liệu hợp lệ, null, thiếu trường và các trường hợp biên.

Một test chỉ xác nhận expression parse thành công là chưa đủ nếu expression còn phụ thuộc bean, function, method resolver hoặc property accessor.

## 19. Checklist điều tra khi expression thất bại

Khi nhận lỗi SpEL, hãy lần lượt xác định:

1. Lỗi xảy ra ở parseExpression hay getValue/setValue?
2. Expression source và ParserContext có đúng không?
3. Root object có đúng kiểu và không null không?
4. Các variable bắt buộc đã được đăng ký chưa?
5. BeanResolver, function và resolver cần thiết đã có chưa?
6. Property hoặc method có tồn tại trên kiểu runtime thực tế không?
7. Object trung gian hoặc collection có null/rỗng không?
8. TypeConverter có hỗ trợ chuyển đổi cần thiết không?
9. Giá trị đã chuyển đổi có vượt giới hạn nghiệp vụ không?
10. Lỗi có chỉ xuất hiện trong compiled mode không?
11. Exception gốc là lỗi của SpEL hay method/getter được gọi?
12. Đây là lỗi cấu hình cần sửa một lần hay dữ liệu của một request cần từ chối?

Cách phân loại này giúp chọn đúng nơi sửa. Đừng sửa dữ liệu request để che một bean name sai; cũng đừng thay đổi cấu hình toàn hệ thống chỉ vì một bản ghi thiếu giá trị tùy chọn.

## 20. Ghi nhớ

Lỗi cấu hình xuất phát từ expression source, parser, ParserContext, EvaluationContext hoặc các resolver và dependency được khai báo không đúng. Lỗi dữ liệu runtime xuất phát từ root object, variable, property, collection, kiểu hoặc trạng thái cụ thể ở thời điểm đánh giá.

Parse thành công không bảo đảm evaluate thành công. Hãy phân biệt ParseException/SpelParseException với EvaluationException/SpelEvaluationException; kiểm tra cấu hình cố định khi khởi động và xử lý dữ liệu runtime tại ranh giới nghiệp vụ phù hợp.

Khi điều tra, xác định giai đoạn lỗi, kiểm tra context và kiểu object, phân biệt property không tồn tại với giá trị null, conversion với validation, và lỗi gọi method với exception bên trong method. Giữ cause chain, log expression identifier và ngữ cảnh đã làm sạch, không ghi bí mật hoặc toàn bộ object nhạy cảm.

Không dùng giá trị mặc định để che giấu lỗi cấu hình. Chỉ áp dụng fallback cho dữ liệu tùy chọn theo quy tắc rõ ràng. Expression cố định cần được parse và kiểm tra phụ thuộc sớm; expression phụ thuộc request cần được kiểm thử với dữ liệu biên và xử lý lỗi runtime nhất quán.

## Tài liệu tham khảo

- [Spring Framework Reference — Evaluation](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Language Reference](https://docs.spring.io/spring-framework/reference/core/expressions/language-ref.html)
- [ParseException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/ParseException.html)
- [EvaluationException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/EvaluationException.html)
- [SpelEvaluationException Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/SpelEvaluationException.html)