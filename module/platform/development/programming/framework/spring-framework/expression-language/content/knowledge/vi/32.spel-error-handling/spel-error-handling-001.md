# ParseException và lỗi cú pháp trong SpEL

Spring Expression Language (SpEL) chuyển chuỗi biểu thức thành một đối tượng Expression thông qua ExpressionParser. Nếu chuỗi không tuân theo grammar của SpEL, parser không thể tạo expression và ném lỗi phân tích cú pháp. Trong Spring, lỗi chuyên biệt thường gặp là SpelParseException, một dạng ParseException cung cấp thông tin về vị trí và loại lỗi mà parser phát hiện.

Cần phân biệt lỗi parse với lỗi xảy ra khi evaluate. Một expression có cú pháp hợp lệ vẫn có thể thất bại lúc chạy vì biến chưa được đăng ký, property không tồn tại, kiểu dữ liệu không tương thích, bean không phân giải được hoặc method ném exception. Phân biệt đúng hai giai đoạn giúp xử lý lỗi chính xác, tránh sửa nhầm cú pháp khi vấn đề thực sự nằm ở dữ liệu hoặc EvaluationContext.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Giải thích parser làm gì và khi nào SpEL ném ParseException.
- Nhận biết SpelParseException và các thông tin chẩn đoán của nó.
- Phân biệt lỗi cú pháp với lỗi evaluate và lỗi nghiệp vụ.
- Xác định lỗi thường gặp ở dấu ngoặc, dấu nháy, toán tử, collection và template delimiter.
- Dùng vị trí lỗi để tìm vùng cú pháp cần kiểm tra.
- Viết test xác nhận expression hợp lệ và expression không hợp lệ.
- Parse expression một lần và tái sử dụng khi phù hợp.
- Trả lỗi cấu hình dễ hiểu mà không làm lộ thông tin nhạy cảm.
- Kiểm soát nguồn và kích thước expression trước khi đưa vào runtime.

Bạn nên biết cách tạo SpelExpressionParser, gọi parseExpression(), tạo EvaluationContext và đánh giá Expression bằng getValue().

## 2. ParseException xảy ra ở giai đoạn nào?

Quá trình làm việc với SpEL thường có hai giai đoạn:

1. Parse source string: parser đọc cú pháp, kiểm tra grammar và tạo đối tượng Expression.
2. Evaluate expression: expression sử dụng root object, variables, property accessors, resolvers và dữ liệu runtime để tính kết quả.

Ví dụ cú pháp hợp lệ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#quantity * #unitPrice");
~~~

Ở thời điểm parse, parser có thể tạo expression dù context chưa có biến quantity hoặc unitPrice. Việc thiếu biến chỉ được phát hiện khi evaluate.

Ngược lại, biểu thức thiếu toán hạng:

~~~text
#quantity *
~~~

không thể được parse thành expression hoàn chỉnh và gây lỗi parse ngay tại parseExpression().

Luồng cơ bản:

~~~text
Source string
     |
     v
ExpressionParser.parseExpression(...)
     |
     +---- cú pháp không hợp lệ ----> ParseException
     |
     v
Expression
     |
     v
Expression.getValue(context)
     |
     +---- lỗi dữ liệu/quyền/runtime -> EvaluationException
     |
     v
Kết quả
~~~

ParseException cho biết parser không thể hiểu source theo grammar. Nó không phải thông báo tổng quát cho mọi lỗi SpEL.

## 3. SpelParseException là gì?

Spring cung cấp SpelParseException trong package org.springframework.expression.spel. Đây là exception chuyên biệt cho lỗi phân tích cú pháp SpEL và kế thừa ParseException của Spring Expression API.

Thông tin hữu ích có thể gồm:

- Vị trí parser phát hiện lỗi.
- Message code mô tả loại lỗi.
- Các giá trị chèn vào thông báo lỗi, ví dụ token hoặc ký hiệu liên quan.
- Thông điệp giải thích lỗi.

Ví dụ bắt lỗi:

~~~java
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.SpelParseException;
import org.springframework.expression.spel.standard.SpelExpressionParser;

ExpressionParser parser = new SpelExpressionParser();

try {
    parser.parseExpression("#quantity *");
}
catch (SpelParseException ex) {
    int position = ex.getPosition();
    String message = ex.getMessage();

    // Ghi nhận lỗi cấu hình theo chính sách của ứng dụng.
}
~~~

Ứng dụng có thể bắt ParseException ở mức abstraction chung nếu không cần thông tin riêng của SpEL. Nếu cần message code hoặc thông tin chuyên biệt, bắt SpelParseException.

Không nên phụ thuộc vào toàn bộ nội dung message để quyết định logic nghiệp vụ. Message hiển thị có thể thay đổi theo phiên bản Spring hoặc cách format thông báo. Dùng loại exception và thông tin có cấu trúc cho xử lý; dùng message chủ yếu để hỗ trợ chẩn đoán.

## 4. Đọc vị trí lỗi

SpelParseException cung cấp vị trí mà parser phát hiện lỗi thông qua getPosition(). Vị trí này giúp thu hẹp vùng cần kiểm tra trong source expression.

Ví dụ:

~~~text
#order.total + )
~~~

Parser có thể phát hiện dấu đóng ngoặc không có biểu thức phù hợp ở phía trước. Hãy xem source xung quanh vị trí được báo, kiểm tra token ngay trước và sau nó, rồi đối chiếu với cấu trúc expression dự kiến.

Khi hiển thị lỗi trong editor:

- Giữ nguyên source string đã parse.
- Dùng vị trí exception để đánh dấu gần ký tự có vấn đề.
- Không tự giả định vị trí luôn là số dòng hoặc số cột.
- Nếu template nhiều dòng, tự xây dựng ánh xạ offset sang dòng/cột từ source gốc.
- Kiểm tra cách API và phiên bản Spring biểu diễn vị trí trước khi chuyển thành chỉ số hiển thị cho người dùng.

Với source có ký tự Unicode ngoài BMP, chỉ số ký tự của Java có thể liên quan đến UTF-16 code unit. Nếu editor dùng code point hoặc grapheme cluster, cần chuyển đổi offset trước khi đánh dấu chính xác.

Vị trí parser phát hiện lỗi không phải lúc nào cũng chính là nơi người viết bắt đầu sai. Ví dụ thiếu dấu nháy mở có thể khiến parser chỉ nhận ra lỗi ở token xuất hiện sau đó. Hãy kiểm tra cả vùng lân cận thay vì chỉ sửa một ký tự được đánh dấu.

## 5. Các lỗi cú pháp thường gặp

### 5.1. Thiếu hoặc thừa dấu ngoặc

Ví dụ thiếu dấu đóng ngoặc:

~~~text
(#price + #tax
~~~

Ví dụ dấu đóng không có cặp:

~~~text
#price + #tax)
~~~

Cách xử lý:

- Đếm cặp ngoặc tròn, vuông và nhọn theo cấu trúc expression.
- Kiểm tra nested expression và map/list inline.
- Tách expression dài thành các phần nhỏ để tìm vị trí mất cân bằng.
- Không thêm dấu ngoặc tùy ý nếu chưa xác định cấu trúc mong muốn.

### 5.2. Chuỗi literal không đóng

Ví dụ:

~~~text
#user.name == 'An
~~~

Chuỗi bắt đầu bằng dấu nháy đơn nhưng không có dấu nháy đóng. Hãy kiểm tra dấu nháy mở/đóng và quy tắc escape của chuỗi trong SpEL.

Nếu source được tạo từ Java string, JSON hoặc XML, cần kiểm tra cả tầng escape của ngôn ngữ chứa expression. Một dấu gạch chéo ngược có thể bị xử lý ở tầng Java trước khi SpEL nhận chuỗi.

### 5.3. Thiếu toán hạng hoặc toán tử

Ví dụ:

~~~text
#quantity *
~~~

~~~text
#amount > and #active
~~~

Kiểm tra xem mỗi toán tử có đủ toán hạng và có dùng đúng từ khóa/toán tử của SpEL hay không. Nếu nối các mảnh expression bằng code, xác nhận từng mảnh không tạo ra toán tử bị bỏ dở ở ranh giới.

### 5.4. Dùng sai cú pháp biến

Biến trong SpEL có tiền tố #:

~~~text
#customerName
~~~

Viết customerName không có # thường được hiểu là property trên root object, không phải variable. Đây có thể là lỗi evaluate nếu grammar hợp lệ nhưng root object không có property đó; không nhất thiết là ParseException.

Cần phân biệt lỗi cú pháp với lỗi phân giải tên. Cú pháp #customerName có thể parse thành công ngay cả khi context chưa đăng ký biến.

### 5.5. Sai cú pháp truy cập collection hoặc map

Ví dụ map indexing:

~~~text
#settings['theme']
~~~

Ví dụ selection:

~~~text
#orders.?[total > 100]
~~~

Ví dụ projection:

~~~text
#orders.![number]
~~~

Các dấu chấm, dấu ngoặc vuông và dấu phân cách phải đúng vị trí. Khi expression kết hợp nhiều collection operation, hãy kiểm tra từng đoạn riêng rồi ghép lại.

### 5.6. Sai cú pháp method call

Ví dụ đúng:

~~~text
#calculator.calculate(#amount)
~~~

Các lỗi thường gặp gồm thiếu dấu ngoặc gọi method, dấu phẩy thừa giữa đối số hoặc chuỗi literal chưa đóng. Method không tồn tại hoặc chữ ký không phù hợp thường được phát hiện ở giai đoạn phân giải/evaluate, dù cú pháp gọi method vẫn hợp lệ.

## 6. Lỗi trong template expression

Template expression kết hợp văn bản literal với đoạn SpEL nằm trong delimiter. Mặc định TemplateParserContext dùng prefix và suffix là #{ và }.

Ví dụ:

~~~java
Expression template = parser.parseExpression(
    "Hello, #{#name}!",
    new TemplateParserContext()
);
~~~

Các lỗi thường gặp:

- Thiếu dấu đóng }.
- Expression bên trong delimiter không hợp lệ.
- Dùng nhầm delimiter của template engine khác.
- Chuỗi literal chứa delimiter nhưng không được xử lý theo quy tắc template.
- Dùng TemplateParserContext không khớp với format source.

Ví dụ thiếu delimiter đóng:

~~~text
Hello, #{#name!
~~~

Hãy kiểm tra source template và parser context được truyền vào parseExpression(). Một chuỗi có thể parse như expression thông thường nhưng không parse như template, hoặc ngược lại, vì parser context làm thay đổi cách diễn giải source.

Nếu dùng delimiter tùy chỉnh, lưu cấu hình delimiter cùng template version. Khi mở lại template, phải dùng cùng ParserContext để parse.

## 7. Phân biệt ParseException với lỗi evaluate

Đây là phân biệt quan trọng nhất khi chẩn đoán.

| Hiện tượng | Giai đoạn thường gặp | Loại lỗi thường gặp |
|---|---|---|
| Thiếu toán hạng, ngoặc hoặc dấu nháy | Parse | SpelParseException |
| Token không thuộc grammar | Parse | SpelParseException |
| Biến chưa đăng ký | Evaluate | SpelEvaluationException hoặc lỗi EvaluationException phù hợp |
| Property không tồn tại | Evaluate | Lỗi property/accessor |
| Method không được tìm thấy | Evaluate | Lỗi method resolution |
| Type trong T(...) không phân giải được | Evaluate | Lỗi type resolution |
| Bean reference không tồn tại | Evaluate | Lỗi bean resolution |
| Đối số không chuyển đổi được | Evaluate | Lỗi conversion |
| Method ném exception | Evaluate | Lỗi thực thi được bọc trong exception của Spring |
| Điều kiện trả false | Nghiệp vụ | Không phải lỗi parse |

Ví dụ:

~~~text
#unknownVariable
~~~

Cú pháp này hợp lệ. Nếu context không đăng ký variable, lỗi xảy ra khi evaluate.

Tương tự:

~~~text
#customer.nonExistingProperty
~~~

Cấu trúc cú pháp có thể hợp lệ nhưng property không được tìm thấy khi expression chạy trên object thực tế.

Không sửa grammar khi lỗi nằm ở dữ liệu, context hoặc model. Hãy xác định exception phát sinh từ parseExpression() hay getValue() trước khi xử lý.

## 8. Tổ chức code để tách parse và evaluate

Nên đặt hai giai đoạn trong các khối xử lý riêng để phân loại lỗi rõ ràng:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
}
catch (SpelParseException ex) {
    throw new IllegalArgumentException(
        "Expression syntax is invalid", ex);
}

try {
    return expression.getValue(context);
}
catch (EvaluationException ex) {
    throw new IllegalStateException(
        "Expression could not be evaluated", ex);
}
~~~

Đây là ví dụ cấu trúc xử lý. Ứng dụng thực tế nên dùng exception domain phù hợp và không trả nguyên message nội bộ cho người dùng cuối.

Tách parse và evaluate có các lợi ích:

- Biết lỗi phát sinh ở giai đoạn nào.
- Có thể kiểm tra expression trước khi publish.
- Có thể cache Expression đã parse theo source/version.
- Mỗi lần evaluate có thể dùng context riêng với dữ liệu runtime.
- Log và metric có thể phân loại syntax error và runtime error riêng.

Nếu parse được thực hiện lúc khởi động hoặc lúc lưu policy, lỗi cú pháp có thể được phát hiện sớm trước khi request nghiệp vụ sử dụng expression.

## 9. Parse một lần và tái sử dụng Expression

Nếu source expression không thay đổi, không cần parse lại ở mọi lần evaluate.

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#subtotal * (1 + #taxRate)");
~~~

Sau đó đánh giá với các context khác nhau:

~~~java
StandardEvaluationContext contextA =
    new StandardEvaluationContext();
contextA.setVariable("subtotal", new BigDecimal("100"));
contextA.setVariable("taxRate", new BigDecimal("0.10"));

StandardEvaluationContext contextB =
    new StandardEvaluationContext();
contextB.setVariable("subtotal", new BigDecimal("250"));
contextB.setVariable("taxRate", new BigDecimal("0.08"));

Object resultA = expression.getValue(contextA);
Object resultB = expression.getValue(contextB);
~~~

Expression giữ cấu trúc đã parse; dữ liệu runtime đến từ context được truyền vào.

Nếu expression do quản trị viên cấu hình, hãy parse và kiểm tra cú pháp khi lưu hoặc publish. Cache theo ID và version để khi nội dung thay đổi, ứng dụng không vô tình dùng Expression cũ.

Không chia sẻ EvaluationContext mutable giữa request chỉ vì Expression được tái sử dụng. Expression và context có vòng đời cùng trách nhiệm khác nhau.

## 10. Kiểm tra source trước khi parse

Nếu expression được nhập qua giao diện quản trị, có thể thực hiện các kiểm tra đầu vào trước khi gọi parser:

- Giới hạn độ dài source.
- Kiểm tra source không rỗng nếu use case yêu cầu.
- Xác định parser context/delimiter đúng.
- Gắn source với policy ID và version.
- Xác định người tạo và quyền chỉnh sửa.
- Không tự nối dữ liệu request vào source.
- Không dùng regex đơn giản để kết luận expression an toàn.
- Parse bằng parser đúng phiên bản và cấu hình của runtime.

Regex có thể hữu ích để kiểm tra format sơ bộ, nhưng không thay thế parser. Grammar SpEL có nested expression, string literal, collection và nhiều toán tử; một regex cấm ký tự có thể bỏ sót cú pháp hoặc từ chối nhầm expression hợp lệ.

Parse thành công chỉ xác nhận cú pháp. Nó không chứng minh expression an toàn, có quyền truy cập đúng hoặc trả kết quả đúng nghiệp vụ.

## 11. Thông báo lỗi cho người dùng và log cho developer

Không nên hiển thị nguyên stack trace hoặc chi tiết class nội bộ cho người dùng cuối.

Có thể phân chia thông tin:

**Thông báo dành cho người cấu hình:**

- Expression không hợp lệ.
- Vị trí gần nơi parser phát hiện lỗi.
- Gợi ý kiểm tra dấu ngoặc, dấu nháy hoặc toán tử.
- Mã lỗi tham chiếu để tra cứu.

**Thông tin log nội bộ:**

- Policy ID và version.
- Parser context hoặc loại template.
- Exception class và message code.
- Position nếu có.
- Correlation ID của request/quá trình publish.
- Source đã được redaction nếu có dữ liệu nhạy cảm.

Source expression có thể chứa tên field, cấu trúc nghiệp vụ hoặc dữ liệu bí mật được nhúng sai cách. Chỉ log source đầy đủ khi chính sách dữ liệu cho phép và có kiểm soát truy cập/retention.

Không dùng message text làm mã lỗi ổn định cho client. Hãy ánh xạ exception sang error code do ứng dụng quản lý.

## 12. Kiểm thử ParseException

Unit test nên xác nhận expression hợp lệ parse thành công và expression sai cú pháp bị từ chối.

Ví dụ JUnit:

~~~java
class SpelSyntaxTest {

    private final ExpressionParser parser =
        new SpelExpressionParser();

    @Test
    void parsesValidExpression() {
        assertThatCode(() ->
            parser.parseExpression("#amount > 100")
        ).doesNotThrowAnyException();
    }

    @Test
    void rejectsMissingOperand() {
        assertThatThrownBy(() ->
            parser.parseExpression("#amount >")
        ).isInstanceOf(SpelParseException.class);
    }
}
~~~

Có thể kiểm tra thêm position hoặc message code nếu test cần bảo đảm giao diện editor hiển thị thông tin chẩn đoán. Tránh assert toàn bộ message vì cách format có thể thay đổi giữa các phiên bản.

Một bộ test nên có:

| Trường hợp | Kết quả mong đợi |
|---|---|
| Expression số học hợp lệ | Parse thành công |
| Expression thiếu toán hạng | ParseException |
| Chuỗi literal chưa đóng | ParseException |
| Ngoặc không cân bằng | ParseException |
| Template thiếu delimiter đóng | ParseException |
| Template với delimiter tùy chỉnh đúng | Parse thành công |
| Biến chưa đăng ký | Parse thành công, evaluate thất bại theo context |
| Property không tồn tại | Parse thành công, evaluate thất bại |
| Method không được phân giải | Parse thành công, evaluate thất bại |
| Type conversion thất bại | Parse thành công, evaluate thất bại |
| Expression trả false | Parse/evaluate thành công, kết quả nghiệp vụ false |

Test này giúp bảo đảm không nhầm lỗi grammar với lỗi runtime.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| ParseException ở cuối expression | Thiếu toán hạng hoặc token đóng | Kiểm tra toán tử cuối và phần source trước đó |
| Lỗi gần dấu ngoặc | Ngoặc thiếu/thừa hoặc lồng sai | Đối chiếu cặp ngoặc theo từng đoạn |
| Lỗi gần dấu nháy | String literal chưa đóng hoặc escape sai | Kiểm tra chuỗi ở cả tầng Java/XML/JSON |
| Template không parse | Prefix/suffix thiếu hoặc sai ParserContext | Kiểm tra TemplateParserContext và delimiter |
| Parser báo lỗi tại vị trí có vẻ hợp lệ | Lỗi thật có thể nằm ở token trước đó | Kiểm tra vùng lân cận và cấu trúc expression |
| Parse thành công nhưng getValue thất bại | Nhầm lỗi runtime với lỗi cú pháp | Kiểm tra EvaluationException và context |
| Biến không tìm thấy | Chưa setVariable hoặc dùng sai context | Đăng ký đúng tên và truyền đúng context |
| Property không tìm thấy | Model/accessor không cung cấp property | Kiểm tra getter, field và PropertyAccessor |
| Message khác sau khi nâng Spring | Message format hoặc parser diagnostic thay đổi | Dựa vào exception type, code và position; cập nhật test phù hợp |
| Lỗi chỉ xảy ra ở production | Parser context, version hoặc source khác môi trường test | Ghi nhận parser configuration và policy version |

## 14. Bài tập thực hành

1. Parse expression số học hợp lệ và đọc kết quả.
2. Thử expression thiếu toán hạng và bắt SpelParseException.
3. Tạo chuỗi literal thiếu dấu nháy đóng và xem vị trí parser báo.
4. Thử thiếu/thừa ngoặc trong expression lồng nhau.
5. Tạo template với prefix/suffix mặc định rồi cố ý bỏ delimiter đóng.
6. Tạo TemplateParserContext với delimiter tùy chỉnh và kiểm thử cả source đúng lẫn sai.
7. Parse một variable expression hợp lệ nhưng không đăng ký biến; so sánh lỗi parse với lỗi evaluate.
8. Dùng một property không tồn tại để quan sát lỗi ở giai đoạn evaluate.
9. Viết JUnit test kiểm tra exception type và position.
10. Tạo một editor nhỏ hiển thị lỗi gần vị trí parser phát hiện mà không lộ stack trace.
11. Parse expression khi publish policy và lưu policy version.
12. Thử cùng source trên phiên bản Spring mà ứng dụng triển khai để xác nhận diagnostic thực tế.

## 15. Checklist khi xử lý ParseException

- [ ] Lỗi phát sinh từ parseExpression() hay getValue()?
- [ ] Exception có phải SpelParseException không?
- [ ] Source expression đúng phiên bản và parser context không?
- [ ] Dấu ngoặc tròn, vuông và nhọn đã cân bằng chưa?
- [ ] String literal đã đóng và escape đúng chưa?
- [ ] Mỗi toán tử có đủ toán hạng chưa?
- [ ] Cú pháp variable, indexing, selection và projection có đúng không?
- [ ] Template prefix/suffix có khớp ParserContext không?
- [ ] Đã kiểm tra source quanh position được báo chưa?
- [ ] Đã phân biệt tên biến/property/method không tồn tại với lỗi cú pháp chưa?
- [ ] Có giới hạn độ dài và nguồn expression không?
- [ ] Có test cả expression hợp lệ, parse lỗi và evaluate lỗi không?
- [ ] Thông báo cho người dùng có tránh lộ stack trace và dữ liệu nhạy cảm không?

## 16. Kết luận

ParseException xảy ra khi ExpressionParser không thể chuyển source thành cấu trúc Expression hợp lệ. SpelParseException cung cấp thông tin chuyên biệt như vị trí và message code để hỗ trợ chẩn đoán. Một expression parse thành công vẫn có thể lỗi khi evaluate do biến, property, method, type, bean hoặc conversion. Hãy tách parse khỏi evaluate, kiểm tra source quanh vị trí lỗi, dùng test cho cả hai giai đoạn và xử lý thông báo theo error code của ứng dụng. Parse sớm khi publish cấu hình giúp phát hiện lỗi cú pháp trước khi policy đi vào runtime.