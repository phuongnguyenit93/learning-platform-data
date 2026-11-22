# Phân biệt lỗi parse với lỗi evaluation trong SpEL

Khi làm việc với Spring Expression Language (SpEL), một biểu thức có thể thất bại ở hai giai đoạn khác nhau: lúc parser chuyển source thành đối tượng Expression, hoặc lúc Expression được đánh giá với dữ liệu và EvaluationContext cụ thể. Hai nhóm lỗi này thường có nguyên nhân và cách khắc phục khác nhau.

Lỗi parse thường liên quan đến grammar: thiếu toán hạng, dấu ngoặc không cân bằng, chuỗi literal chưa đóng hoặc delimiter template sai. Lỗi evaluation xảy ra sau khi expression đã được tạo, chẳng hạn biến chưa được đăng ký, property không tồn tại, method không phân giải được, receiver null hoặc kiểu dữ liệu không tương thích. Phân biệt đúng giai đoạn giúp tìm nguyên nhân nhanh hơn và tránh sửa cú pháp khi vấn đề nằm ở context hoặc dữ liệu runtime.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Phân biệt parse-time failure và evaluation-time failure.
- Nhận biết ParseException, SpelParseException, EvaluationException và SpelEvaluationException.
- Hiểu vì sao một tên biến hoặc property sai có thể chỉ lỗi khi evaluate.
- Dùng vị trí và mã lỗi để chẩn đoán expression.
- Kiểm tra root object, variable, property accessor, method resolver và type converter.
- Tách riêng bước parse và evaluate trong code.
- Viết test cho cú pháp hợp lệ, cú pháp sai và expression lỗi theo context.
- Xử lý lỗi phù hợp ở tầng cấu hình, ứng dụng và giao diện người dùng.
- Tránh che giấu lỗi bằng cách bắt exception rồi trả về giá trị mặc định không phù hợp.

Bạn nên biết cách tạo SpelExpressionParser, Expression và EvaluationContext, đồng thời hiểu root object, variable, property access và method invocation.

## 2. Hai giai đoạn trong vòng đời expression

Quy trình xử lý một biểu thức SpEL gồm hai giai đoạn chính:

1. **Parse:** ExpressionParser đọc source, kiểm tra grammar và tạo đối tượng Expression.
2. **Evaluate:** Expression sử dụng EvaluationContext, root object và dữ liệu runtime để tính kết quả.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("#order.total > 100");
~~~

Đoạn code trên parse expression. Nó chưa cần biết biến order có tồn tại hay object order có property total hay không.

Khi đánh giá:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("order", order);

Boolean allowed =
    expression.getValue(context, Boolean.class);
~~~

SpEL mới cần đọc biến order, truy cập total, thực hiện phép so sánh và chuyển kết quả sang Boolean nếu cần.

Luồng xử lý:

~~~text
Source string
     |
     v
parseExpression(source)
     |
     +---- grammar không hợp lệ ----> ParseException
     |
     v
Expression
     |
     v
getValue(context)
     |
     +---- dữ liệu/context/runtime lỗi ---> EvaluationException
     |
     v
Kết quả
~~~

Parse thành công chỉ xác nhận source có thể được hiểu theo grammar. Nó không chứng minh expression có thể chạy với mọi context hoặc mọi dữ liệu.

## 3. Lỗi parse là gì?

Lỗi parse xảy ra khi parser không thể xây dựng expression từ source. Trong SpEL, SpelParseException là exception chuyên biệt cho lỗi cú pháp và kế thừa ParseException của Spring Expression API.

Ví dụ thiếu toán hạng:

~~~java
parser.parseExpression("#amount *");
~~~

Ví dụ chuỗi literal chưa đóng:

~~~java
parser.parseExpression("'hello");
~~~

Ví dụ ngoặc không cân bằng:

~~~java
parser.parseExpression("(#price + #tax");
~~~

Các lỗi này xuất hiện trong lời gọi parseExpression(), trước khi có EvaluationContext hoặc dữ liệu runtime tham gia.

Nguyên nhân thường gặp:

- Thiếu hoặc thừa dấu ngoặc tròn, vuông hoặc nhọn.
- Chuỗi literal không có dấu nháy đóng.
- Toán tử thiếu toán hạng.
- Dấu phẩy hoặc dấu hai chấm đặt sai vị trí.
- Cú pháp list, map, selection hoặc projection không hợp lệ.
- Cú pháp template thiếu prefix/suffix hoặc dùng sai ParserContext.
- Escape bị thay đổi ở tầng Java, XML, JSON hoặc nguồn lưu trữ trước khi SpEL nhận chuỗi.

## 4. Lỗi evaluation là gì?

Lỗi evaluation xảy ra sau khi parser đã tạo được Expression nhưng engine không thể tính kết quả trong context cụ thể. SpelEvaluationException là exception chuyên biệt thường gặp trong giai đoạn này và thuộc nhóm EvaluationException.

Ví dụ expression hợp lệ về cú pháp:

~~~text
#unknownVariable
~~~

Expression này có thể parse thành công. Nhưng nếu context không có biến unknownVariable, việc evaluate sẽ thất bại.

Ví dụ khác:

~~~text
#customer.nonExistingProperty
~~~

Cú pháp property access hợp lệ, nhưng object customer thực tế có thể không có property đó hoặc PropertyAccessor không hỗ trợ truy cập.

Các nguyên nhân thường gặp:

- Biến chưa được đăng ký hoặc tên biến không khớp.
- Root object null hoặc không có property được yêu cầu.
- Property path sai hoặc getter không truy cập được.
- Method không tồn tại, không truy cập được hoặc đối số không tương thích.
- Bean reference không phân giải được.
- Type reference không tìm thấy class.
- Constructor không phân giải được.
- Type conversion thất bại.
- Receiver null tại vị trí không được bảo vệ.
- Method được gọi ném exception.
- Property accessor hoặc resolver từ chối quyền truy cập.

## 5. Bảng phân biệt nhanh

| Dấu hiệu | Parse failure | Evaluation failure |
|---|---|---|
| Thời điểm | Trong parseExpression() | Trong getValue() hoặc setValue() |
| Expression object | Không được tạo thành công | Đã được tạo |
| Context cần thiết | Không cần context để phát hiện grammar lỗi | Thường phụ thuộc context và dữ liệu |
| Ví dụ | #amount * | #missingVariable |
| Exception thường gặp | SpelParseException | SpelEvaluationException |
| Cách sửa | Sửa grammar/source | Sửa context, model, dữ liệu, resolver hoặc logic |
| Có thể parse trước khi có dữ liệu không? | Có, nếu grammar hợp lệ | Có; lỗi chỉ xuất hiện khi evaluate |

Một lỗi có thể trông giống lỗi tên nhưng thực chất thuộc giai đoạn khác. Ví dụ, viết customerName không có # có thể là cú pháp hợp lệ và được hiểu là property trên root object. Nếu root object không có property customerName, lỗi chỉ xảy ra khi evaluate.

## 6. Ví dụ: cùng một source nhưng lỗi ở hai giai đoạn

Ví dụ lỗi parse:

~~~java
Expression expression =
    parser.parseExpression("#quantity +");
~~~

Lời gọi parseExpression ném SpelParseException vì biểu thức thiếu toán hạng bên phải.

Ví dụ lỗi evaluation:

~~~java
Expression expression =
    parser.parseExpression("#quantity + 1");

StandardEvaluationContext context =
    new StandardEvaluationContext();

Integer result =
    expression.getValue(context, Integer.class);
~~~

Expression đã parse thành công. Lỗi xuất hiện khi evaluate vì biến quantity chưa được đăng ký.

Sửa context:

~~~java
context.setVariable("quantity", 4);

Integer result =
    expression.getValue(context, Integer.class);
~~~

Kết quả là 5.

Khi debug, luôn xác định exception phát sinh ở dòng parse hay dòng evaluate. Đừng gom cả hai vào một khối catch chung nếu cần thông báo chính xác cho người cấu hình.

## 7. Phân tích vị trí lỗi và mã lỗi

SpelParseException cung cấp thông tin chẩn đoán như vị trí parser phát hiện lỗi, message code và thông tin liên quan đến token. SpelEvaluationException cũng có thể cung cấp vị trí hoặc mã lỗi hữu ích tùy loại lỗi.

Ví dụ:

~~~java
try {
    parser.parseExpression("#amount *");
}
catch (SpelParseException ex) {
    int position = ex.getPosition();
    Object messageCode = ex.getMessageCode();

    // Dùng position và messageCode cho chẩn đoán.
}
~~~

Khi evaluate:

~~~java
try {
    expression.getValue(context);
}
catch (SpelEvaluationException ex) {
    Object messageCode = ex.getMessageCode();

    // Phân loại lỗi runtime và ghi nhận theo chính sách.
}
~~~

Vị trí lỗi giúp thu hẹp vùng source cần xem xét, nhưng không nhất thiết là nơi người viết bắt đầu sai. Ví dụ thiếu dấu nháy mở có thể khiến parser chỉ phát hiện vấn đề ở token phía sau.

Không phụ thuộc vào toàn bộ message text để quyết định logic. Message có thể thay đổi theo phiên bản Spring hoặc cách format. Dùng exception type, message code và dữ liệu có cấu trúc để phân loại; message dành cho con người chủ yếu phục vụ chẩn đoán.

Nếu source nhiều dòng, ứng dụng có thể ánh xạ offset sang dòng/cột để hiển thị trong editor. Cần tính đến cách Java biểu diễn chỉ số chuỗi bằng UTF-16 code unit nếu source chứa ký tự Unicode ngoài BMP.

## 8. Chẩn đoán lỗi biến và root object

Nếu expression tham chiếu biến bằng #name, kiểm tra biến đã được đăng ký trong đúng context truyền vào getValue() chưa.

~~~java
context.setVariable("customer", customer);

Expression expression =
    parser.parseExpression("#customer.name");
~~~

Các câu hỏi cần kiểm tra:

- Tên trong setVariable có bỏ dấu # không?
- Có đang evaluate bằng cùng context đã đăng ký biến không?
- Giá trị biến có null hoặc sai kiểu không?
- Biến có bị thay thế hoặc xóa trước khi evaluate không?
- Expression có nhầm variable với property của root object không?

Với root object, property không cần tiền tố #:

~~~text
customer.name
~~~

Còn biến cần tiền tố:

~~~text
#customer.name
~~~

Nếu một expression parse thành công nhưng đọc nhầm nguồn dữ liệu, hãy xác định rõ root object và variable. Đây thường là lỗi thiết kế context, không phải lỗi grammar.

## 9. Chẩn đoán property path và null

Property path có thể gồm nhiều tầng:

~~~text
#order.customer.address.city
~~~

Nếu một tầng trung gian null, truy cập tiếp có thể gây evaluation failure. Kiểm tra từng tầng object và dùng null-safe navigation tại receiver có thể null:

~~~text
#order?.customer?.address?.city
~~~

Dấu ?. bảo vệ receiver ngay trước nó. Nếu order null, phần còn lại của đường dẫn được xử lý theo null-safe semantics. Nếu một property khác có thể null, cần đặt dấu ?. tại vị trí phù hợp.

Cần phân biệt:

- Property không tồn tại: model hoặc accessor không cung cấp property đó.
- Property tồn tại nhưng giá trị null: dữ liệu runtime không có giá trị.
- Root object null: không có object để bắt đầu truy cập.
- Variable chưa đăng ký: context không cung cấp tên biến.

Null-safe navigation giải quyết receiver null; nó không sửa tên property sai hoặc tự tạo dữ liệu thiếu.

## 10. Chẩn đoán method invocation

Ví dụ:

~~~text
#calculator.calculate(#amount)
~~~

Nếu expression parse được nhưng evaluate thất bại, kiểm tra:

- Biến calculator có được đăng ký không?
- Giá trị calculator có null không?
- Method calculate có tồn tại và truy cập được không?
- Số lượng đối số có đúng không?
- Kiểu runtime của từng đối số có tương thích không?
- Có overload khiến method resolution mơ hồ không?
- Method có ném exception bên trong không?
- MethodResolver có giới hạn method đó không?

Một method call hợp lệ về grammar vẫn có thể thất bại ở runtime. Nếu method tồn tại nhưng ném exception, hãy xem nguyên nhân bên trong method thay vì sửa cú pháp expression.

Không gọi method có side effect trong expression chỉ đọc nếu không cần. Side effect làm việc tái hiện lỗi và so sánh kết quả khó hơn.

## 11. Chẩn đoán conversion và kiểu dữ liệu

Expression có thể parse và bắt đầu evaluate nhưng thất bại khi một giá trị cần chuyển sang kiểu đích.

Ví dụ property assignment:

~~~java
Expression expression =
    parser.parseExpression("retryCount");

expression.setValue(context, rootObject, "not-a-number");
~~~

Nếu retryCount có kiểu số, TypeConverter có thể không chuyển được chuỗi trên thành kiểu property.

Khi gặp lỗi conversion, kiểm tra:

- Kiểu runtime của giá trị nguồn.
- Kiểu property hoặc tham số đích.
- TypeConverter được gắn với EvaluationContext.
- ConversionService và converter tùy chỉnh.
- Locale hoặc format nếu dữ liệu là số/ngày giờ.
- Generic type nếu conversion xảy ra trong collection.

Conversion failure không phải ParseException. Source có thể hoàn toàn hợp lệ; dữ liệu runtime mới là nguyên nhân.

## 12. Chẩn đoán bean reference và type reference

Bean reference:

~~~text
@pricingPolicy.calculate(#total)
~~~

Nếu evaluate thất bại, kiểm tra BeanResolver đã được cấu hình chưa, bean name có đúng không, bean có tồn tại trong BeanFactory không và method có thể gọi được không.

Type reference:

~~~text
T(java.lang.Math).max(10, 20)
~~~

Nếu evaluate thất bại, kiểm tra TypeLocator có phân giải được class không và method static có phù hợp không.

Cả hai ví dụ đều có thể parse thành công ngay cả khi context không cung cấp resolver tương ứng. Việc parser hiểu cú pháp @beanName hoặc T(...) không có nghĩa runtime có quyền hoặc khả năng phân giải object/class đó.

## 13. Tách parse và evaluate trong code

Tách hai giai đoạn giúp phân loại lỗi và hiển thị thông báo chính xác:

~~~java
Expression expression;

try {
    expression = parser.parseExpression(source);
}
catch (SpelParseException ex) {
    throw new InvalidExpressionSyntaxException(
        "Expression syntax is invalid", ex);
}

try {
    return expression.getValue(context);
}
catch (EvaluationException ex) {
    throw new ExpressionExecutionException(
        "Expression could not be evaluated", ex);
}
~~~

Các exception domain trong ví dụ là do ứng dụng định nghĩa. Tùy hệ thống, có thể giữ nguyên exception Spring làm cause để log và chẩn đoán.

Lợi ích:

- Biết lỗi xảy ra ở parse hay evaluate.
- Có thể parse/validate trước khi publish cấu hình.
- Có thể cache Expression đã parse.
- Mỗi lần evaluate dùng context và dữ liệu hiện tại.
- Metric và log có thể phân loại syntax error với runtime error.

Nếu source đến từ cấu hình quản trị, parse khi lưu hoặc publish để phát hiện lỗi grammar sớm. Runtime vẫn phải xử lý evaluation failure vì dữ liệu, quyền và object có thể thay đổi.

## 14. Quy trình debug theo thứ tự

Khi expression thất bại, thực hiện lần lượt:

1. Xác định dòng code phát sinh exception: parseExpression, getValue hay setValue.
2. Ghi nhận exception class và message code.
3. Nếu lỗi parse, kiểm tra source quanh position, dấu ngoặc, dấu nháy, toán tử và delimiter.
4. Nếu lỗi evaluation, kiểm tra context instance và root object.
5. Xác nhận mọi variable cần thiết đã được đăng ký với đúng tên.
6. Kiểm tra từng property path và null ở từng tầng.
7. Kiểm tra method signature, overload và quyền của MethodResolver.
8. Kiểm tra BeanResolver hoặc TypeLocator nếu expression dùng @beanName hoặc T(...).
9. Kiểm tra TypeConverter nếu lỗi xảy ra trong chuyển đổi.
10. Tách expression dài thành các phần nhỏ để xác định đoạn gây lỗi.
11. Tái hiện bằng fixture tối thiểu có cùng kiểu dữ liệu và trạng thái.
12. Viết regression test cho nguyên nhân đã xác định.

Không thay đổi nhiều thành phần cùng lúc. Nếu vừa đổi source, context, resolver và converter trong một lần thử, sẽ khó biết thay đổi nào đã xử lý lỗi.

## 15. Parse một lần, evaluate nhiều lần

Nếu source không thay đổi, có thể parse một lần và tái sử dụng Expression:

~~~java
Expression expression =
    parser.parseExpression("#subtotal * (1 + #taxRate)");
~~~

Mỗi lần đánh giá có thể truyền context riêng:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("subtotal", new BigDecimal("100"));
context.setVariable("taxRate", new BigDecimal("0.10"));

Object result = expression.getValue(context);
~~~

Expression chứa cấu trúc đã parse; context chứa dữ liệu runtime. Hai đối tượng có trách nhiệm và vòng đời khác nhau.

Không dùng chung một EvaluationContext mutable giữa các request đồng thời nếu request thay đổi variable. Context riêng giúp tránh dữ liệu giữa các lần evaluate bị lẫn.

Nếu source thay đổi theo policy version, cache Expression theo ID/version và vô hiệu hóa khi policy bị thay thế hoặc thu hồi.

## 16. Xử lý lỗi ở tầng ứng dụng

Không phải mọi lỗi SpEL đều nên hiển thị nguyên văn cho người dùng cuối.

Có thể phân loại:

| Tình huống | Cách xử lý phù hợp |
|---|---|
| Cấu hình có syntax error | Từ chối lưu/publish và chỉ rõ vị trí |
| Biến hoặc property bắt buộc thiếu | Báo lỗi dữ liệu/context |
| Caller không có quyền truy cập capability | Từ chối truy cập |
| Conversion thất bại | Báo lỗi dữ liệu không hợp lệ |
| Method ném exception | Ghi nhận runtime failure và xử lý theo hợp đồng |
| Expression trả false | Kết quả nghiệp vụ false, không phải exception |
| Expression trả null khi cần Boolean | Xử lý theo chính sách; với quyết định truy cập nên fail closed |

Không bắt mọi exception rồi trả null, false hoặc giá trị mặc định. Làm như vậy có thể che giấu lỗi cấu hình và khiến hành vi nghiệp vụ khó dự đoán.

Với policy quyết định quyền truy cập, chỉ kết quả Boolean true mới được coi là pass nếu đó là hợp đồng đã định nghĩa. Parse/evaluate error, null hoặc kiểu kết quả khác phải bị từ chối hoặc chuyển thành lỗi vận hành phù hợp.

## 17. Logging và thông tin chẩn đoán

Log nội bộ có thể ghi:

- Policy ID và version.
- Giai đoạn lỗi: parse, evaluate hoặc setValue.
- Exception class.
- Message code và position nếu có.
- Correlation ID.
- Loại context/parser configuration.
- Mã lỗi domain đã ánh xạ.

Không ghi token, secret, dữ liệu cá nhân hoặc toàn bộ source expression nếu chính sách dữ liệu không cho phép. Expression có thể chứa tên field nội bộ hoặc thông tin cấu hình nhạy cảm.

Thông báo cho người cấu hình có thể nêu vị trí lỗi và gợi ý kiểm tra. Thông báo cho client thông thường nên dùng error code ổn định do ứng dụng định nghĩa, không trả stack trace hoặc cấu trúc nội bộ.

## 18. Kiểm thử parse failure và evaluation failure

Nên có test riêng cho hai giai đoạn.

Ví dụ JUnit cho parse:

~~~java
@Test
void rejectsInvalidSyntax() {
    assertThatThrownBy(() ->
        parser.parseExpression("#amount *")
    ).isInstanceOf(SpelParseException.class);
}
~~~

Ví dụ JUnit cho evaluate:

~~~java
@Test
void validSyntaxCanFailWhenVariableIsMissing() {
    Expression expression =
        parser.parseExpression("#missingValue + 1");

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    assertThatThrownBy(() ->
        expression.getValue(context)
    ).isInstanceOf(EvaluationException.class);
}
~~~

Bộ test nên bao gồm:

| Test case | Giai đoạn | Kết quả mong đợi |
|---|---|---|
| Expression số học hợp lệ | Parse | Thành công |
| Thiếu toán hạng | Parse | SpelParseException |
| Chuỗi literal chưa đóng | Parse | SpelParseException |
| Template thiếu delimiter | Parse | ParseException |
| Variable chưa đăng ký | Evaluate | EvaluationException |
| Property không tồn tại | Evaluate | EvaluationException |
| Receiver null không được bảo vệ | Evaluate | Runtime evaluation failure |
| Method không phân giải được | Evaluate | EvaluationException |
| Bean reference không có resolver | Evaluate | Resolution failure |
| Type conversion không hợp lệ | Evaluate/setValue | Conversion failure |
| Expression trả false | Evaluate | Thành công, kết quả false |
| Expression trả null | Evaluate | Thành công hoặc null theo expression; caller xử lý theo hợp đồng |

Tránh assert toàn bộ exception message vì format có thể thay đổi giữa các phiên bản. Ưu tiên exception type, message code khi ổn định và hành vi ứng dụng.

## 19. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Sửa dấu ngoặc nhưng lỗi vẫn còn | Lỗi thật nằm ở token trước vị trí parser báo | Kiểm tra source xung quanh position |
| Expression parse được nhưng không chạy | Thiếu variable hoặc property ở context | Kiểm tra dữ liệu và root object |
| Tên property bị hiểu nhầm là variable | Quên tiền tố # | Dùng #name cho variable |
| Null-safe navigation vẫn lỗi | Một receiver khác chưa được bảo vệ | Đặt ?. tại từng tầng có thể null |
| Method tồn tại nhưng vẫn lỗi | Overload, argument type hoặc resolver không phù hợp | Kiểm tra chữ ký và MethodResolver |
| Bean reference parse được nhưng không tìm thấy bean | BeanResolver chưa cấu hình hoặc bean name sai | Kiểm tra BeanFactory và resolver |
| Type reference parse được nhưng class không tìm thấy | TypeLocator không cho phép hoặc không phân giải class | Kiểm tra TypeLocator |
| Chuyển đổi lỗi | Kiểu nguồn/đích không tương thích | Kiểm tra TypeConverter/ConversionService |
| Lỗi chỉ xuất hiện ở production | Context, version, resolver hoặc dữ liệu khác test | Ghi nhận cấu hình và tạo fixture tương đương |
| Ứng dụng che giấu lỗi | Catch quá rộng và trả default | Phân loại lỗi, giữ cause và xử lý theo hợp đồng |

## 20. Bài tập thực hành

1. Parse một expression số học hợp lệ và đánh giá kết quả.
2. Tạo expression thiếu toán hạng, bắt SpelParseException.
3. Parse #missingVariable thành công rồi evaluate trong context không có biến.
4. Tạo property path sai và xác nhận lỗi xảy ra khi evaluate.
5. Tạo root object null và thử safe navigation.
6. Tạo method call có đối số sai kiểu để kiểm tra conversion/resolution.
7. Tạo expression dùng @beanName trong context không có BeanResolver.
8. Tạo expression dùng T(...) với TypeLocator giới hạn.
9. Tách parse/evaluate thành hai khối try-catch và ánh xạ sang error code riêng.
10. Viết test xác nhận expression trả false không bị phân loại là exception.
11. Tạo regression test cho một lỗi runtime đã sửa.
12. Thử log position và message code mà không ghi source hoặc dữ liệu nhạy cảm.

## 21. Checklist trước khi kết luận lỗi SpEL

- [ ] Exception phát sinh ở parseExpression, getValue hay setValue?
- [ ] Có phải SpelParseException hay EvaluationException không?
- [ ] Source có đúng parser context và delimiter không?
- [ ] Dấu ngoặc, dấu nháy và toán tử có đúng grammar không?
- [ ] Variable có được đăng ký trong đúng EvaluationContext không?
- [ ] Root object có đúng kiểu và trạng thái không?
- [ ] Property path có tồn tại và có tầng nào null không?
- [ ] Method signature và overload có phù hợp không?
- [ ] BeanResolver và TypeLocator có được cấu hình khi cần không?
- [ ] TypeConverter có hỗ trợ kiểu nguồn/đích không?
- [ ] Đã tái hiện bằng fixture nhỏ và dữ liệu tương đương chưa?
- [ ] Đã viết regression test cho nguyên nhân chưa?
- [ ] Logging có đủ chẩn đoán mà không lộ dữ liệu nhạy cảm không?
- [ ] Có tránh bắt exception quá rộng rồi trả default không?

## 22. Kết luận

Parse failure xảy ra khi parser không thể chuyển source thành Expression hợp lệ; evaluation failure xảy ra sau đó khi expression cần dữ liệu, property, method, bean, type hoặc conversion mà runtime không cung cấp hoặc không cho phép. SpelParseException thường chỉ ra vấn đề grammar; SpelEvaluationException và các EvaluationException liên quan chỉ ra vấn đề khi chạy. Hãy tách parse khỏi evaluate, kiểm tra exception type và vị trí, xác minh context cùng dữ liệu runtime, rồi tạo test riêng cho từng giai đoạn. Cách phân loại rõ ràng giúp xử lý lỗi chính xác và tránh che giấu vấn đề bằng giá trị mặc định.