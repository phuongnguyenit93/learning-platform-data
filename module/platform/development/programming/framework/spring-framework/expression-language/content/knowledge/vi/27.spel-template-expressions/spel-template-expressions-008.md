# Kiểm soát dữ liệu được chèn vào chuỗi kết quả trong SpEL Template Expression

SpEL Template Expression cho phép kết hợp văn bản cố định với các biểu thức được đánh giá tại runtime. Ví dụ, một mẫu có thể tạo lời chào từ tên người dùng hoặc tạo thông báo từ trạng thái đơn hàng. Khi dữ liệu được chèn vào chuỗi kết quả, cần kiểm soát cả nguồn expression, giá trị runtime và nơi chuỗi kết quả sẽ được sử dụng.

Template expression chỉ thay thế phần được đánh dấu bằng delimiter của parser. Nó không tự làm sạch dữ liệu, không tự escape HTML, SQL, JavaScript hay URL, và cũng không biến một template không tin cậy thành an toàn. Hãy giữ cấu trúc template trong mã hoặc nguồn đã được phê duyệt, truyền dữ liệu qua biến có kiểu rõ ràng và mã hóa đầu ra theo đúng ngữ cảnh sử dụng.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Hiểu cách TemplateParserContext phân tách văn bản cố định và phần expression.
- Tạo chuỗi kết quả từ nhiều đoạn literal và giá trị runtime.
- Truyền dữ liệu qua biến thay vì ghép input vào source expression.
- Phân biệt expression injection với việc chèn một giá trị dữ liệu thông thường.
- Hiểu template expression không tự escape hoặc encode đầu ra.
- Chọn cách encode phù hợp với HTML, URL, JavaScript, JSON, SQL, CSV và log.
- Xử lý null, kiểu dữ liệu, locale, timezone và độ dài đầu ra.
- Giới hạn EvaluationContext và nguồn template.
- Kiểm thử các chuỗi chứa delimiter, ký tự đặc biệt và payload độc hại.

Bạn nên biết SpelExpressionParser, Expression, EvaluationContext, biến có tiền tố # và cách ứng dụng trả chuỗi ra một hệ thống khác.

## 2. Template expression hoạt động như thế nào?

Một expression thông thường được parse như một biểu thức SpEL hoàn chỉnh. Template expression cho phép trộn văn bản thuần với các đoạn SpEL nằm giữa delimiter.

Mặc định, TemplateParserContext dùng tiền tố và hậu tố là dấu mở #{ và dấu đóng }.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression(
    "Hello, #{#name}!",
    new TemplateParserContext()
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("name", "An");

String message = expression.getValue(context, String.class);
~~~

Kết quả:

~~~text
Hello, An!
~~~

Parser giữ phần Hello, và ! như văn bản literal; phần #name bên trong delimiter được đánh giá như một expression. Kết quả của các phần được ghép thành một chuỗi.

Một template có thể chứa nhiều đoạn expression:

~~~text
Order #{#order.number} has status #{#order.status}.
~~~

Mỗi đoạn được đánh giá trong cùng EvaluationContext, sau đó kết quả được kết hợp theo thứ tự xuất hiện.

### 2.1. Cấu trúc template và giá trị runtime là hai thứ khác nhau

Giả sử template cố định là:

~~~text
Welcome, #{#displayName}.
~~~

Giá trị displayName được truyền qua context. Nếu giá trị đó chứa ký tự như #{, }, dấu nháy hoặc chuỗi trông giống cú pháp SpEL, nó vẫn là giá trị của biến trong lần đánh giá hiện tại. SpEL không tự parse đệ quy nội dung chuỗi được trả về từ biến thành một template mới.

Rủi ro xuất hiện khi ứng dụng nối dữ liệu không tin cậy vào source template rồi parse lại chuỗi đã ghép. Khi đó input có thể trở thành cú pháp SpEL thay vì chỉ là dữ liệu.

## 3. Giữ template cố định, truyền dữ liệu qua biến

Cách nên dùng là parse template đã được ứng dụng kiểm soát, rồi truyền giá trị động qua EvaluationContext.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression template = parser.parseExpression(
    "Customer #{#customerName} has #{#itemCount} items.",
    new TemplateParserContext()
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("customerName", customerName);
context.setVariable("itemCount", itemCount);

String output = template.getValue(context, String.class);
~~~

Cấu trúc expression không thay đổi theo dữ liệu đầu vào. Tên biến và kiểu dữ liệu được xác định rõ trong code.

Tránh cách làm sau:

~~~java
String source =
    "Customer " + userInput + " is active";

Expression expression = parser.parseExpression(source);
~~~

Trong ví dụ này, userInput trở thành một phần source được parser xử lý. Nếu chuỗi chứa cú pháp SpEL hợp lệ, nó có thể thay đổi ý nghĩa expression hoặc kích hoạt capability của EvaluationContext.

Nếu cần chèn dữ liệu tùy ý, hãy giữ dữ liệu trong biến:

~~~java
Expression template = parser.parseExpression(
    "Customer #{#customerName} is active",
    new TemplateParserContext()
);

context.setVariable("customerName", userInput);
~~~

Giá trị userInput lúc này được xử lý như dữ liệu được cung cấp cho expression đã cố định, không phải source code mới.

## 4. Phân biệt expression injection và output injection

Đây là hai rủi ro khác nhau:

| Rủi ro | Xảy ra ở đâu? | Biện pháp chính |
|---|---|---|
| Expression injection | Input không tin cậy bị đưa vào source SpEL rồi parse/evaluate | Không ghép input vào source; chỉ dùng template đã phê duyệt và context giới hạn |
| Output injection | Chuỗi kết quả được đưa vào HTML, JavaScript, URL, SQL, log hoặc định dạng khác mà không encode đúng ngữ cảnh | Encode hoặc serialize tại điểm xuất dữ liệu theo đúng ngữ cảnh |

Giữ template cố định và truyền biến giúp ngăn dữ liệu đầu vào trở thành cú pháp SpEL. Nhưng điều đó chưa bảo đảm chuỗi kết quả an toàn khi trình duyệt hoặc hệ thống khác xử lý nó.

Ví dụ, tên người dùng có thể chứa:

~~~text
<script>alert(1)</script>
~~~

Nếu giá trị này được chèn vào một template rồi hiển thị trực tiếp như HTML, trình duyệt có thể hiểu nó là markup hoặc script. SpEL không tự biết chuỗi đang được dùng làm HTML và không tự mã hóa các ký tự đặc biệt.

Do đó cần bảo vệ ở cả hai ranh giới: source expression và output sink.

## 5. Template expression không tự escape dữ liệu

SpEL template parser chỉ đánh giá phần expression và kết hợp các kết quả với literal text. Nó không phải HTML template engine có auto-escaping theo ngữ cảnh.

Ví dụ:

~~~text
<p>Hello, #{#name}</p>
~~~

Nếu name chứa HTML markup, kết quả vẫn chứa nội dung đó. Khi trả kết quả ra trình duyệt, phải encode dữ liệu theo HTML text context hoặc dùng template engine/framework có cơ chế auto-escaping đã được cấu hình đúng.

Không dùng một hàm escape chung cho mọi loại đầu ra. HTML text, HTML attribute, JavaScript string, CSS, URL component và JSON có quy tắc khác nhau.

### 5.1. Encode tại điểm sử dụng

Một chuỗi có thể được tạo ở tầng service rồi được dùng trong nhiều ngữ cảnh khác nhau. Vì vậy, thường nên giữ giá trị dữ liệu ở dạng chưa encode trong model và encode tại nơi xuất dữ liệu.

Ví dụ:

- Khi hiển thị trong HTML, dùng HTML escaping phù hợp với text hoặc attribute context.
- Khi đặt vào URL query parameter, URL-encode riêng giá trị parameter.
- Khi tạo JSON, dùng JSON serializer thay vì tự ghép dấu ngoặc và dấu nháy.
- Khi hiển thị trong JavaScript, tránh nối chuỗi thủ công; dùng cơ chế serialize dữ liệu an toàn.
- Khi ghi log, dùng structured logging và xử lý ký tự xuống dòng để tránh log injection.

Encode quá sớm có thể gây double-encoding khi chuỗi được dùng ở một context khác. Hãy xác định output sink rồi áp dụng đúng bộ mã hóa ở ranh giới đó.

## 6. Không tạo câu SQL bằng template expression

Không dùng SpEL template để ghép dữ liệu vào SQL rồi thực thi chuỗi kết quả.

Ví dụ thiết kế không an toàn:

~~~text
SELECT * FROM account WHERE username = '#{#username}'
~~~

Nếu chuỗi kết quả được gửi trực tiếp tới JDBC như SQL hoàn chỉnh, dữ liệu có thể làm thay đổi cấu trúc câu lệnh.

Hãy dùng PreparedStatement hoặc cơ chế parameter binding của Spring JDBC/JPA:

~~~java
jdbcTemplate.query(
    "select * from account where username = ?",
    rowMapper,
    username
);
~~~

Template expression có thể phù hợp để tạo nội dung hiển thị hoặc thông báo, nhưng không thay thế parameterized query. SQL identifier như tên bảng hoặc tên cột cũng không thể được bảo vệ chỉ bằng cách bind value; nếu cần lựa chọn identifier động, dùng allowlist ở Java.

## 7. Không tạo shell command hoặc source code từ dữ liệu

Không dùng template expression để nối dữ liệu không tin cậy thành shell command, script, Java source hoặc nội dung sẽ được đánh giá như code ở một bước tiếp theo.

Ví dụ:

~~~text
run-command --user "#{#username}"
~~~

Nếu chuỗi kết quả được chuyển thẳng cho shell, dấu nháy hoặc ký tự điều khiển trong username có thể làm thay đổi cách shell phân tích lệnh.

Cách an toàn hơn là gọi API/process với danh sách đối số tách biệt, không qua shell, và validate từng đối số theo hợp đồng. Với source code hoặc expression lồng nhau, hãy dùng parser/serializer chuyên biệt và một allowlist ngôn ngữ hẹp; không parse lại chuỗi kết quả chỉ vì nó có vẻ là cú pháp hợp lệ.

## 8. Giới hạn EvaluationContext

Ngay cả khi template được cố định, các expression bên trong vẫn có thể truy cập những gì EvaluationContext cho phép.

Một context rộng có thể expose:

- Property và field trên root object.
- Variable chứa service hoặc object mutable.
- Method invocation.
- Type reference bằng T(...).
- Constructor invocation.
- Bean reference bằng @beanName.
- Property assignment hoặc các capability có side effect.

Với template chỉ cần nội suy vài trường, hãy cung cấp DTO nhỏ và context chỉ đọc:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext.forReadOnlyDataBinding().build();

context.setVariable("customerName", customerName);
context.setVariable("itemCount", itemCount);
~~~

Không đưa ApplicationContext, BeanFactory, repository, service quản trị hoặc entity graph lớn vào context chỉ để lấy một giá trị. Nếu expression cần method, expose facade nhỏ với method thuần và giới hạn resolver cụ thể.

SimpleEvaluationContext không phải sandbox tuyệt đối; dữ liệu và accessor được cung cấp vẫn cần được kiểm soát. Hãy chọn capability theo nhu cầu thật của template.

## 9. Dùng delimiter tùy chỉnh khi cần

TemplateParserContext cho phép chỉ định tiền tố và hậu tố riêng:

~~~java
ParserContext parserContext =
    new TemplateParserContext("[[", "]]");

Expression template = parser.parseExpression(
    "Hello [[#name]]!",
    parserContext
);
~~~

Trong ví dụ, đoạn expression được đặt giữa [[ và ]]. Delimiter tùy chỉnh có thể hữu ích khi văn bản literal thường chứa chuỗi #{ hoặc khi tích hợp với một định dạng template khác.

Chọn delimiter ít có khả năng xuất hiện tự nhiên trong nội dung. Ghi rõ quy ước này trong cấu hình và test các trường hợp delimiter xuất hiện trong văn bản. Không đổi delimiter để thay thế kiểm soát nguồn template; một template không tin cậy vẫn có thể chứa delimiter mới.

Nếu template cần đi qua nhiều tầng xử lý, hãy tránh dùng chung delimiter với công cụ khác nếu điều đó gây parse nhầm hoặc làm khó xác định tầng nào sở hữu cú pháp.

## 10. Xử lý null và giá trị mặc định

Nếu property hoặc variable có thể null, hãy quyết định rõ chuỗi nào sẽ xuất hiện trong kết quả.

Ví dụ:

~~~text
Hello, #{#customer?.displayName ?: 'Guest'}.
~~~

Safe navigation bảo vệ property khi customer null; Elvis cung cấp giá trị mặc định nếu kết quả null.

Có thể dùng giá trị mặc định cho số lượng:

~~~text
You have #{#itemCount ?: 0} items.
~~~

Chỉ dùng default khi null thực sự có nghĩa là dùng giá trị đó. Nếu null biểu thị dữ liệu bắt buộc bị thiếu, nên validation và báo lỗi thay vì âm thầm thay bằng chuỗi mặc định.

Đừng dựa vào cách một giá trị null được chuyển thành chuỗi. Hãy viết rõ Elvis hoặc xử lý null trong Java để kết quả có ý nghĩa nhất quán.

## 11. Kiểm soát kiểu và định dạng dữ liệu

Template expression có thể chèn String, Number, Boolean, ngày giờ hoặc kết quả của method. Cách chuyển giá trị thành chuỗi có thể ảnh hưởng nội dung hiển thị.

Với dữ liệu cần định dạng cụ thể:

- Tiền tệ: xác định currency, scale và rounding trước khi tạo nội dung.
- Số thập phân: quy định dấu phân cách thập phân và locale.
- Ngày giờ: quy định timezone và format, không phụ thuộc mặc định máy chủ.
- Boolean và enum: chọn nhãn hiển thị ổn định thay vì dựa vào tên kỹ thuật nếu người dùng cuối đọc kết quả.
- Collection: giới hạn số phần tử và định nghĩa cách phân tách.
- Object tùy chỉnh: dùng một property hoặc formatter rõ ràng thay vì dựa vào toString() mặc định.

Ví dụ nên chuẩn hóa giá trị trước trong Java rồi đưa vào context:

~~~java
context.setVariable("formattedTotal", moneyFormatter.format(total));
context.setVariable("formattedDate", dateFormatter.format(createdAt));
~~~

Template chỉ làm nhiệm vụ ghép các giá trị đã được chuẩn bị:

~~~text
Total: #{#formattedTotal}; created at #{#formattedDate}
~~~

Cách này tách logic định dạng khỏi cấu trúc câu và giúp kiểm thử formatter độc lập.

## 12. Kiểm soát độ dài và chi phí tạo chuỗi

Template có thể chèn nội dung lớn hoặc gọi expression tốn tài nguyên. Nếu dữ liệu đầu vào không được giới hạn, một thông báo tưởng như đơn giản có thể tạo chuỗi rất lớn hoặc làm runtime tốn nhiều thời gian.

Hãy:

- Giới hạn độ dài của dữ liệu đầu vào.
- Giới hạn số lượng phần tử collection được đưa vào template.
- Không gọi method thực hiện I/O hoặc truy vấn không giới hạn trong template.
- Giữ expression nhỏ, tránh projection trên collection lớn khi không cần.
- Giới hạn kích thước template và số đoạn expression ở tầng quản lý policy.
- Dùng timeout/giới hạn tài nguyên phù hợp ở tầng ứng dụng khi có xử lý tốn kém.
- Không coi giới hạn độ dài là thay thế cho allowlist capability.

Nếu cần render báo cáo lớn, email phức tạp hoặc trang HTML, hãy dùng công cụ template chuyên dụng có quản lý escaping, layout và giới hạn tài nguyên phù hợp.

## 13. Parse một lần, evaluate theo context hiện tại

Nếu template cố định và được dùng nhiều lần, có thể parse một lần rồi evaluate với context riêng cho mỗi lần xử lý.

~~~java
Expression template = parser.parseExpression(
    "Order #{#orderNumber}: #{#status}",
    new TemplateParserContext()
);

String render(String orderNumber, String status) {
    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setVariable("orderNumber", orderNumber);
    context.setVariable("status", status);

    return template.getValue(context, String.class);
}
~~~

Cấu trúc template có thể được tái sử dụng; context chứa dữ liệu runtime nên được tạo hoặc quản lý theo phạm vi của lần render.

Không chia sẻ một EvaluationContext mutable giữa các request đồng thời rồi ghi đè biến. Làm như vậy có thể khiến dữ liệu của request này xuất hiện trong kết quả của request khác.

Nếu template được lưu theo cấu hình, cache Expression theo ID và version của template. Khi nội dung thay đổi hoặc bị thu hồi, vô hiệu hóa phiên bản cache tương ứng. Không cache chuỗi đã render giữa các người dùng nếu key cache không phản ánh đầy đủ dữ liệu và quyền liên quan.

## 14. Kiểm thử dữ liệu được chèn vào template

Hãy kiểm thử cả nội dung kết quả và cách output được sử dụng:

| Trường hợp | Dữ liệu | Điều cần xác nhận |
|---|---|---|
| Giá trị thông thường | name = An | Nội suy đúng vị trí |
| Giá trị chứa delimiter | name chứa #{...} | Giá trị không bị parse đệ quy |
| Dấu nháy và dấu gạch chéo | name có quote/backslash | Nội suy không làm hỏng template |
| HTML markup | name chứa thẻ script | Output được HTML-encode tại sink |
| Ký tự URL | value có khoảng trắng và dấu & | Parameter được URL-encode đúng |
| Null | customer = null | Safe navigation/default hoạt động theo thiết kế |
| Property thiếu | Sai tên property | Lỗi được phát hiện, không biến thành allow |
| Input quá dài | Chuỗi vượt giới hạn | Bị từ chối theo chính sách rõ ràng |
| Template không tin cậy | Nội dung có expression tùy ý | Không được publish/evaluate nếu chưa được phê duyệt |
| Context rộng | Variable chứa service | Test xác nhận context runtime không expose capability ngoài nhu cầu |
| Nhiều request | Hai bộ biến khác nhau | Kết quả không lẫn dữ liệu |

Ngoài unit test cho expression, hãy test tại điểm output thực tế: HTML renderer, URL builder, JSON serializer hoặc logging framework. An toàn của chuỗi chỉ có thể đánh giá đầy đủ khi biết sink cuối cùng.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Input làm thay đổi cú pháp expression | Nối dữ liệu vào source trước khi parse | Giữ template cố định và truyền input qua variable |
| Giá trị chứa #{...} bị coi là code | Ứng dụng parse lại chuỗi kết quả như template mới | Không parse đệ quy nội dung dữ liệu |
| HTML bị thực thi hoặc render ngoài ý muốn | Template expression không tự HTML-escape | Encode theo HTML context tại output sink |
| SQL bị thay đổi | Dùng chuỗi template làm câu SQL thực thi | Dùng PreparedStatement hoặc parameter binding |
| URL bị lỗi hoặc có thể bị thao túng | Chèn value mà không encode parameter | Dùng URI builder và encode từng parameter |
| Null xuất hiện không như mong đợi | Không định nghĩa default rõ ràng | Dùng Elvis hoặc xử lý null trong Java |
| Template không parse đúng delimiter | Delimiter trùng nội dung literal hoặc công cụ khác | Chọn parser context/delimiter phù hợp và test |
| Dữ liệu giữa request bị lẫn | Chia sẻ context mutable | Tạo context riêng cho từng lần render |
| Chuỗi kết quả quá lớn | Input hoặc collection không có giới hạn | Giới hạn kích thước và số phần tử |
| Expression gọi được method ngoài ý muốn | EvaluationContext có resolver quá rộng | Dùng context hẹp và facade allowlist |

## 16. Bài tập thực hành

1. Tạo template Hello, #{#name}! và đánh giá với hai giá trị name khác nhau.
2. Truyền một giá trị chứa chuỗi #{T(java.lang.Math).PI} qua biến; xác nhận nội dung đó được chèn như dữ liệu, không được parse lại.
3. Thử nối trực tiếp input vào source expression trong một test riêng để hiểu ranh giới expression injection.
4. Tạo template có customer null và dùng safe navigation cùng Elvis.
5. Thử delimiter tùy chỉnh bằng TemplateParserContext.
6. Render tên có HTML markup rồi encode tại HTML output sink.
7. Tạo URL query parameter bằng URI builder thay vì nối chuỗi thủ công.
8. Dùng PreparedStatement cho truy vấn có dữ liệu người dùng, không tạo SQL bằng template.
9. Tạo hai EvaluationContext riêng và kiểm tra dữ liệu giữa hai lần render không bị lẫn.
10. Giới hạn độ dài input và số phần tử collection rồi kiểm tra hành vi khi vượt giới hạn.

## 17. Checklist trước khi đưa dữ liệu vào chuỗi kết quả

- [ ] Template có nguồn tin cậy và được quản lý phiên bản không?
- [ ] Dữ liệu động được truyền qua variable thay vì nối vào source expression không?
- [ ] Có tránh parse đệ quy chuỗi kết quả không?
- [ ] EvaluationContext chỉ expose root object, variable và capability cần thiết không?
- [ ] Null và giá trị mặc định đã được định nghĩa rõ chưa?
- [ ] Output sink cuối cùng đã được xác định chưa?
- [ ] Dữ liệu đã được encode theo đúng HTML/attribute/URL/JavaScript context chưa?
- [ ] Có dùng serializer JSON thay vì ghép JSON thủ công không?
- [ ] Có dùng parameter binding thay vì tạo SQL bằng template không?
- [ ] Có tránh đưa chuỗi kết quả trực tiếp vào shell hoặc source code không?
- [ ] Locale, timezone và format dữ liệu đã rõ chưa?
- [ ] Độ dài template, input và collection đã được giới hạn chưa?
- [ ] Context có được cô lập giữa các request đồng thời không?
- [ ] Đã test delimiter, quote, markup, null và payload đặc biệt chưa?

## 18. Kết luận

Template expression kết hợp literal text với các đoạn SpEL được đánh dấu bằng delimiter, mặc định là #{ và }. Hãy giữ template trong nguồn tin cậy, truyền dữ liệu qua variable và tránh ghép input vào source expression hoặc parse lại chuỗi kết quả. SpEL không tự escape đầu ra: HTML, URL, JavaScript, JSON, SQL, shell và log đều cần cơ chế xử lý riêng tại điểm sử dụng. Giới hạn EvaluationContext, xử lý null/format rõ ràng, giới hạn kích thước và kiểm thử cả ranh giới expression lẫn output sink để chuỗi kết quả không làm thay đổi ý nghĩa của hệ thống nhận nó.