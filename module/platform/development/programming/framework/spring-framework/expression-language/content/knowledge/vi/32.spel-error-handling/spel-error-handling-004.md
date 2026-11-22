# Lỗi property, method, constructor và conversion

## Mục tiêu

Khi SpEL đánh giá một expression, nó phải truy cập property, gọi method, tạo object hoặc chuyển đổi kiểu dữ liệu theo yêu cầu của thao tác. Expression có thể parse thành công nhưng vẫn thất bại lúc chạy nếu property không đọc/ghi được, method hoặc constructor không được phân giải, đối số sai kiểu hay converter không hỗ trợ cặp kiểu cần thiết.

Chẩn đoán hiệu quả cần xác định đúng thao tác đang thất bại, object và kiểu runtime tại thời điểm đó, cấu hình EvaluationContext, vị trí expression và exception gốc. Không nên chỉ dựa vào dòng message cuối cùng hoặc thay đổi đồng thời nhiều phần của expression.

Sau bài này, bạn có thể:

- Phân biệt lỗi parse với lỗi evaluation.
- Chẩn đoán property không tồn tại, không đọc được hoặc không ghi được.
- Xử lý lỗi method resolution và overload.
- Xác định nguyên nhân constructor invocation thất bại.
- Chẩn đoán lỗi TypeConverter và ConversionService.
- Đọc message code, vị trí và cause chain của exception.
- Tạo log hữu ích mà không làm lộ dữ liệu nhạy cảm.
- Viết test tái hiện từng loại lỗi trong đúng EvaluationContext.

## 1. Xác định giai đoạn phát sinh lỗi

SpEL có hai giai đoạn chính:

1. **Parse:** parser đọc chuỗi và tạo Expression.
2. **Evaluate:** expression được chạy với root object, biến và EvaluationContext.

Lỗi parse thường do cú pháp không hợp lệ: thiếu dấu ngoặc, string literal chưa đóng, toán tử sai vị trí hoặc expression block không hoàn chỉnh.

Lỗi evaluation xuất hiện sau khi parse thành công. Các nguyên nhân có thể gồm:

- Property không tồn tại hoặc không thể đọc/ghi.
- Method không được tìm thấy hoặc không có overload phù hợp.
- Constructor không được tìm thấy.
- Đối số không tương thích với tham số.
- TypeConverter không thể chuyển giá trị sang kiểu đích.
- Method, getter, setter hoặc constructor ném exception.
- Root object, biến hoặc phần tử collection là null tại vị trí không được bảo vệ.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("price * quantity");
~~~

Dòng trên chỉ parse expression. Lỗi có thể chỉ xuất hiện khi gọi getValue():

~~~java
BigDecimal total =
    expression.getValue(context, BigDecimal.class);
~~~

Nếu root object không có property price hoặc quantity, hoặc kiểu dữ liệu không hỗ trợ phép nhân, lỗi xảy ra ở giai đoạn evaluation.

Hãy ghi nhận rõ lỗi xảy ra ở parseExpression(), getValue() hay setValue(). Đây là bước đầu tiên để chọn đúng hướng điều tra.

## 2. Các loại exception thường gặp

Các exception quan trọng trong luồng SpEL gồm:

| Exception | Vai trò |
|---|---|
| **ParseException** | Lỗi phân tích cú pháp expression |
| **SpelParseException** | Thông tin parse error chuyên biệt của SpEL |
| **EvaluationException** | Lỗi tổng quát khi đánh giá expression |
| **SpelEvaluationException** | Evaluation error của SpEL, thường kèm message code và vị trí |
| **AccessException** | Lỗi từ một PropertyAccessor hoặc accessor tùy chỉnh |
| **ConversionException** | Lỗi trong quá trình chuyển đổi kiểu |
| **ConversionFailedException** | ConversionService không thực hiện được conversion cần thiết |
| **ConverterNotFoundException** | Không có converter cho source type và target type |
| **ClassCastException** | Một giá trị bị sử dụng như kiểu không tương thích |
| **NullPointerException** | Code truy cập object null, thường trong method hoặc accessor |

Exception thực tế phụ thuộc thao tác, resolver, accessor, converter và phiên bản Spring. Một số lỗi bên dưới có thể được SpEL bọc trong SpelEvaluationException, vì vậy cần đọc cả cause chain.

Không nên giả định rằng mọi lỗi property đều có cùng exception class hoặc mọi lỗi conversion đều trực tiếp ném ConverterNotFoundException. Hãy ghi nhận exception thực tế và nguyên nhân sâu nhất có ý nghĩa.

## 3. Lỗi đọc property

Property expression có thể dùng dấu chấm hoặc cú pháp property phù hợp với target:

~~~text
#root.customer.name
#root.address.postalCode
~~~

Lỗi đọc property thường xuất hiện khi:

- Property hoặc field không tồn tại trên target.
- Tên property sai chính tả hoặc sai chữ hoa/thường.
- Getter không có hoặc không thể truy cập.
- PropertyAccessor không hỗ trợ kiểu target.
- Getter ném exception.
- Target hoặc một object trung gian là null.
- EvaluationContext bị giới hạn quyền truy cập property.

Ví dụ:

~~~java
Expression expression =
    parser.parseExpression("customer.displayName");

String name = expression.getValue(context, String.class);
~~~

Nếu root object không có customer, hoặc customer không cung cấp property displayName có thể đọc được, evaluation thất bại.

### Cách chẩn đoán

1. Kiểm tra kiểu runtime của root object.
2. Kiểm tra property path từng cấp, bắt đầu từ cấp đầu tiên.
3. Xác nhận getter hoặc field có thể truy cập theo PropertyAccessor đang dùng.
4. Kiểm tra object trung gian có null không.
5. Kiểm tra EvaluationContext có custom PropertyAccessor hoặc giới hạn read access không.
6. Nếu getter ném exception, đọc cause để tìm lỗi bên trong getter.

Đừng giả định một property Java luôn đọc được chỉ vì field tồn tại. SpEL truy cập qua PropertyAccessor; quyền đọc phụ thuộc accessor và cấu hình context.

## 4. Lỗi ghi property

Ghi property thường xuất hiện trong setValue() hoặc phép gán bên trong expression:

~~~java
Expression expression =
    parser.parseExpression("retryCount");

expression.setValue(context, 5);
~~~

Các nguyên nhân thường gặp:

- Property không có setter hoặc không có cơ chế ghi được hỗ trợ.
- Setter không thể truy cập.
- Property chỉ đọc trong SimpleEvaluationContext.
- Kiểu giá trị mới không thể chuyển sang kiểu property.
- Setter ném exception do validation hoặc quy tắc nghiệp vụ.
- Target hoặc object trung gian là null.
- Custom PropertyAccessor từ chối thao tác ghi.

Ví dụ property có setter:

~~~java
public class RetrySettings {
    private Integer retryCount;

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

Expression gán giá trị:

~~~text
retryCount = 3
~~~

Nếu context được cấu hình read-only, hoặc property không có setter mà accessor không hỗ trợ ghi trực tiếp, thao tác sẽ thất bại.

### Phân biệt lỗi ghi với lỗi conversion

Nếu property có setter nhưng nhận Integer trong khi expression cung cấp một String không hợp lệ, lỗi có thể nằm ở conversion trước khi setter được gọi.

Nếu conversion thành công nhưng setter từ chối giá trị, lỗi nằm trong logic setter.

Để phân biệt, kiểm tra kiểu nguồn, kiểu property, converter được dùng và cause chain. Có thể test trực tiếp setter với giá trị đã chuyển đổi để xác định setter có phải nguồn lỗi hay không.

## 5. Lỗi method resolution

SpEL gọi method trên object bằng cú pháp:

~~~text
#root.customer.calculateDiscount(#amount)
~~~

Method resolution có thể thất bại khi:

- Tên method sai hoặc không tồn tại.
- Số lượng đối số không khớp.
- Kiểu đối số không tương thích với tham số.
- Không có overload phù hợp.
- Có nhiều overload gây nhập nhằng theo dữ liệu và conversion.
- Method không thể truy cập qua resolver đang cấu hình.
- EvaluationContext không cho phép loại method access cần thiết.
- Object target null.
- Method được tìm thấy nhưng ném exception khi thực thi.

Ví dụ Java:

~~~java
public class Customer {
    public BigDecimal calculateDiscount(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.10"));
    }
}
~~~

Expression:

~~~text
#root.calculateDiscount(#amount)
~~~

Đảm bảo biến amount có kiểu phù hợp với tham số BigDecimal.

### Kiểm tra overload

Giả sử class có các overload:

~~~java
public String format(Integer value) { ... }

public String format(BigDecimal value) { ... }
~~~

Nếu expression truyền một giá trị có kiểu khác hoặc null, việc chọn overload có thể không như dự kiến. Hãy kiểm tra kiểu runtime của đối số và tránh dựa vào conversion mơ hồ.

Khi cần ổn định, chuẩn hóa kiểu trước khi gọi method hoặc cung cấp một method Java trung gian có chữ ký duy nhất và rõ ràng.

### Method được gọi nhưng ném exception

Method resolution thành công không có nghĩa method thực thi thành công. Nếu method ném IllegalArgumentException, NullPointerException hoặc exception nghiệp vụ, SpEL có thể báo evaluation error với cause tương ứng.

Đọc exception gốc để phân biệt method không được tìm thấy với lỗi phát sinh bên trong method.

## 6. Lỗi constructor invocation

Constructor expression dùng cú pháp:

~~~text
new fully.qualified.ClassName(arguments)
~~~

Ví dụ:

~~~text
new java.math.BigDecimal('125.50')
~~~

Constructor invocation có thể thất bại vì:

- Class name sai hoặc class không có trên runtime classpath.
- TypeLocator hoặc class loader không tìm thấy class.
- Constructor không tồn tại với số lượng đối số được truyền.
- Kiểu đối số không tương thích.
- Không có conversion phù hợp cho constructor parameter.
- Constructor không thể truy cập.
- Constructor được gọi nhưng ném exception.
- EvaluationContext không hỗ trợ constructor invocation.

Ví dụ một class yêu cầu hai đối số:

~~~java
public class Range {
    public Range(int minimum, int maximum) {
        // Validate and initialize.
    }
}
~~~

Expression:

~~~text
new com.example.Range(10, 20)
~~~

Nếu chỉ truyền một đối số hoặc truyền giá trị không thể chuyển sang kiểu tham số, SpEL không thể gọi constructor phù hợp.

### Cách chẩn đoán

1. Xác nhận fully qualified class name.
2. Kiểm tra class có trên runtime classpath và class loader phù hợp.
3. Xem các constructor public và chữ ký tham số.
4. So sánh số lượng, kiểu và giá trị đối số thực tế.
5. Kiểm tra TypeConverter nếu cần conversion.
6. Đọc cause nếu constructor đã được gọi và ném exception.

Nếu object cần dependency injection, proxy hoặc lifecycle của Spring, hãy để container tạo object. Constructor expression chỉ tạo instance Java; nó không tự tạo Spring-managed bean.

## 7. Lỗi conversion

Conversion có thể xuất hiện khi:

- Gán giá trị cho property.
- Truyền đối số vào method.
- Truyền đối số vào constructor.
- Yêu cầu kiểu kết quả trong getValue(context, targetType).
- Chuyển đổi phần tử trong collection hoặc Map.

Ví dụ yêu cầu chuyển String thành Integer:

~~~java
Expression expression =
    parser.parseExpression("'not-a-number'");

Integer value =
    expression.getValue(context, Integer.class);
~~~

Expression parse thành công nhưng conversion có thể thất bại khi getValue yêu cầu Integer.

Các nguyên nhân thường gặp:

- Không có converter cho source type và target type.
- Dữ liệu không đúng định dạng.
- Giá trị nằm ngoài miền hợp lệ của kiểu đích.
- Converter tùy chỉnh ném exception.
- EvaluationContext dùng ConversionService khác với service ứng dụng mong đợi.
- Generic collection thiếu thông tin kiểu đích hoặc một phần tử không thể chuyển.

### TypeConverter và ConversionService

EvaluationContext cung cấp TypeConverter cho SpEL. StandardTypeConverter thường tích hợp với Spring ConversionService.

Có thể gắn một ConversionService cụ thể:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(rootObject);

context.setTypeConverter(
    new StandardTypeConverter(applicationConversionService)
);
~~~

Nếu converter đã đăng ký trong một ConversionService khác, expression không tự động sử dụng converter đó. Hãy xác nhận đúng instance được gắn vào context đang đánh giá.

Không dùng conversion để che giấu dữ liệu không hợp lệ. Nếu đầu vào cần theo một định dạng nghiệp vụ cụ thể, hãy validate trước khi evaluate hoặc viết converter có hợp đồng rõ ràng.

## 8. Phân biệt lỗi resolution với lỗi thực thi

Một thao tác có thể thất bại ở nhiều thời điểm:

| Giai đoạn | Ví dụ lỗi |
|---|---|
| Parse | Cú pháp method call sai, thiếu ngoặc |
| Resolve property | Không tìm thấy property hoặc không có quyền đọc |
| Resolve method | Không tìm thấy method/overload |
| Resolve constructor | Không tìm thấy class hoặc constructor phù hợp |
| Convert argument | Không chuyển được giá trị sang kiểu tham số |
| Execute getter/method/constructor | Code Java bên trong ném exception |
| Convert result | Không chuyển được kết quả sang target type yêu cầu |

Ví dụ, với expression:

~~~text
#root.customer.calculateDiscount(#amount)
~~~

có thể gặp lỗi do customer không tồn tại, customer null, method không có, amount sai kiểu, conversion thất bại hoặc chính calculateDiscount ném exception.

Hãy tìm bước đầu tiên thất bại thay vì chỉ nhìn tên method trong expression rồi kết luận đó là lỗi method resolution.

## 9. Đọc SpelEvaluationException

SpelEvaluationException là nguồn thông tin quan trọng khi SpEL evaluation thất bại. Tùy loại lỗi và phiên bản Spring, exception có thể cung cấp:

- Message code để phân loại lỗi.
- Vị trí trong expression.
- Các giá trị được dùng để tạo message.
- Cause chain chứa exception gốc.

Ví dụ bắt lỗi:

~~~java
try {
    return expression.getValue(context, Boolean.class);
}
catch (SpelEvaluationException ex) {
    logger.warn(
        "SpEL evaluation failed: code={}, position={}",
        ex.getMessageCode(),
        ex.getPosition()
    );
    throw ex;
}
~~~

Tên method và thông tin accessor cụ thể cần đối chiếu với phiên bản Spring đang dùng. Có thể kiểm tra cause bằng getCause() hoặc duyệt cause chain.

Message code hữu ích hơn việc so sánh toàn bộ câu message. Wording có thể thay đổi giữa các phiên bản, trong khi code phân loại thường phù hợp hơn cho diagnostic và test.

Không nên bắt mọi RuntimeException rồi trả về null hoặc false. Làm như vậy có thể biến lỗi cấu hình, dữ liệu hoặc lập trình thành kết quả nghiệp vụ có vẻ hợp lệ.

## 10. Thiết kế logging và diagnostic

Một log tốt phải giúp tái hiện lỗi mà không làm lộ dữ liệu nhạy cảm.

Nên ghi nhận:

- ID hoặc tên rule/expression.
- Phiên bản expression nếu nội dung có thể thay đổi.
- Giai đoạn lỗi: parse, property, method, constructor hay conversion.
- Message code và vị trí lỗi nếu có.
- Kiểu runtime của root object.
- Kiểu source và target khi conversion thất bại.
- Tên operation/property/method liên quan nếu có.
- Class của exception gốc và cause chain.
- Correlation ID hoặc request ID.
- Loại EvaluationContext và cấu hình converter/accessor liên quan.

Tránh log:

- Toàn bộ object graph.
- Password, token, secret hoặc credential.
- Nội dung cá nhân không cần thiết.
- Toàn bộ giá trị biến nếu chúng có thể chứa dữ liệu nhạy cảm.
- Expression do người dùng nhập nếu expression có thể chứa dữ liệu riêng tư.

Có thể log kiểu dữ liệu, ID tham chiếu, tên biến hoặc một phần đã được làm sạch thay vì giá trị thô.

## 11. Cách xử lý theo từng loại lỗi

| Loại lỗi | Kiểm tra đầu tiên | Hướng xử lý |
|---|---|---|
| Property không đọc được | Target type, property path, getter, accessor | Sửa tên/path hoặc cấu hình PropertyAccessor phù hợp |
| Property không ghi được | Setter, read-only context, target type | Cung cấp setter/accessor ghi hoặc dùng context có quyền phù hợp |
| Method không tìm thấy | Tên, số lượng và kiểu đối số | Sửa lời gọi hoặc tạo method wrapper có chữ ký rõ |
| Method overload nhập nhằng | Kiểu runtime của đối số | Chuẩn hóa kiểu và giảm nhập nhằng overload |
| Method ném exception | Cause bên trong method | Sửa dữ liệu hoặc logic method; giữ nguyên lỗi nghiệp vụ |
| Constructor không tìm thấy | Class, class loader, constructor signature | Sửa class name và đối số |
| Constructor ném exception | Cause từ constructor | Kiểm tra invariant và dữ liệu khởi tạo |
| Conversion thất bại | Source/target type, ConversionService | Validate dữ liệu hoặc đăng ký converter đúng |
| Null trong property path | Object trung gian | Dùng safe navigation khi null là hợp lệ hoặc validate đầu vào |
| Chỉ lỗi trong production | Context/configuration khác test | Dùng chung context factory và cấu hình conversion |

Không sửa expression bằng cách thêm safe navigation nếu lỗi thực tế là property không tồn tại hoặc method không có. Safe navigation chỉ bảo vệ target null ở vị trí được áp dụng; nó không thay thế property, method hay converter bị thiếu.

## 12. Kiểm thử property, method, constructor và conversion

Mỗi loại thao tác cần test riêng để xác định đúng điểm thất bại.

### Property read và write

~~~java
@Test
void readsAndWritesProperty() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context =
        new StandardEvaluationContext(new RetrySettings());

    Expression expression = parser.parseExpression("retryCount");
    expression.setValue(context, 3);

    assertEquals(
        Integer.valueOf(3),
        expression.getValue(context, Integer.class)
    );
}
~~~

Thêm test cho property không tồn tại, read-only context, setter ném exception và giá trị không chuyển đổi được.

### Method invocation

~~~java
@Test
void invokesMethodWithCompatibleArgument() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context =
        new StandardEvaluationContext(new Customer());

    context.setVariable("amount", new BigDecimal("100"));

    Expression expression =
        parser.parseExpression("calculateDiscount(#amount)");

    assertNotNull(expression.getValue(context));
}
~~~

Thêm test cho method thiếu, overload, đối số null và exception bên trong method.

### Constructor invocation

~~~java
@Test
void createsValueWithConstructorExpression() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context =
        new StandardEvaluationContext();

    Expression expression = parser.parseExpression(
        "new java.math.BigDecimal('10.25')"
    );

    assertEquals(
        new BigDecimal("10.25"),
        expression.getValue(context, BigDecimal.class)
    );
}
~~~

Thêm test cho class thiếu, constructor signature sai và constructor ném exception.

### Conversion

~~~java
@Test
void convertsStringResultToInteger() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context =
        new StandardEvaluationContext();

    Expression expression = parser.parseExpression("'42'");

    assertEquals(
        Integer.valueOf(42),
        expression.getValue(context, Integer.class)
    );
}
~~~

Thêm test cho chuỗi sai định dạng, custom converter, target type khác và context dùng ConversionService riêng.

## 13. Quy trình điều tra lỗi có hệ thống

Khi expression thất bại trong môi trường thực tế:

1. **Ghi nhận expression và giai đoạn lỗi.** Xác định parseExpression(), getValue() hay setValue() phát sinh exception.
2. **Lấy message code và vị trí.** Dùng thông tin từ SpelEvaluationException nếu có.
3. **Xác định target.** Ghi kiểu runtime của root object và object hiện tại tại thao tác lỗi.
4. **Thu hẹp expression.** Kiểm tra từng property path hoặc method call độc lập với dữ liệu đại diện.
5. **Kiểm tra access.** Xác nhận PropertyAccessor, MethodResolver hoặc ConstructorResolver hỗ trợ thao tác.
6. **Kiểm tra chữ ký.** So sánh kiểu và số lượng đối số với method/constructor.
7. **Kiểm tra conversion.** Xác định source type, target type và ConversionService thực tế.
8. **Đọc cause chain.** Tìm lỗi gốc từ getter, setter, method, constructor hoặc converter.
9. **Tái hiện bằng test.** Dùng cùng Expression, EvaluationContext, root object và converter configuration.
10. **Sửa đúng tầng.** Sửa dữ liệu, model, accessor, resolver, converter hoặc expression theo nguyên nhân.
11. **Thêm test hồi quy.** Bao phủ trường hợp thành công, lỗi và dữ liệu biên.

Đừng thay đổi đồng thời expression, model và ConversionService trước khi có test tái hiện. Việc cô lập từng tầng giúp biết thay đổi nào thực sự giải quyết nguyên nhân.

## 14. Thực hành tốt

- Phân biệt parse error và evaluation error trước khi sửa.
- Kiểm tra root type và property path từng cấp.
- Phân biệt property không đọc được với property không ghi được.
- Kiểm tra method signature và overload thay vì chỉ kiểm tra tên method.
- Xác nhận class, constructor và class loader khi dùng new.
- Dùng cùng ConversionService của ứng dụng nếu quy tắc conversion cần nhất quán.
- Validate input trước khi evaluate khi dữ liệu có format nghiệp vụ.
- Đọc message code, vị trí và cause chain.
- Không phụ thuộc vào toàn bộ message text để điều khiển logic.
- Không nuốt exception rồi trả null/false nếu đó không phải kết quả nghiệp vụ.
- Log đủ thông tin chẩn đoán nhưng không log secret hoặc object graph.
- Dùng cùng EvaluationContext factory trong test và production.
- Viết test riêng cho property, method, constructor và conversion.
- Chuyển logic phức tạp hoặc có side effect sang Java method có tên rõ.

## 15. Checklist review

Trước khi đưa expression vào sử dụng, hãy kiểm tra:

- [ ] Expression parse thành công.
- [ ] Đã xác định rõ thao tác có thể thất bại ở runtime.
- [ ] Root object và kiểu runtime đúng.
- [ ] Property path tồn tại và có thể đọc/ghi theo context.
- [ ] Null ở từng cấp được xử lý theo hợp đồng.
- [ ] Method name, số lượng và kiểu đối số phù hợp.
- [ ] Overload không nhập nhằng ngoài ý muốn.
- [ ] Constructor và class được phân giải đúng.
- [ ] ConversionService và TypeConverter được cấu hình đúng.
- [ ] Custom converter có test cho input hợp lệ và không hợp lệ.
- [ ] Exception được phân loại bằng message code/cause, không chỉ message text.
- [ ] Log không làm lộ dữ liệu nhạy cảm.
- [ ] Có test cho thành công, thất bại và giá trị biên.
- [ ] Test dùng cấu hình EvaluationContext giống production.

## Kết luận

Lỗi property, method, constructor và conversion trong SpEL thường xuất hiện ở giai đoạn evaluation, dù expression đã parse thành công. Hãy xác định thao tác thất bại, kiểu runtime của target và đối số, quyền của accessor/resolver, TypeConverter/ConversionService và exception gốc. SpelEvaluationException cung cấp message code và vị trí hữu ích; cause chain cho biết lỗi sâu hơn từ getter, setter, method, constructor hoặc converter. Kiểm tra từng tầng bằng test tái hiện, ghi log đủ để chẩn đoán mà không lộ dữ liệu nhạy cảm, và sửa đúng nguyên nhân thay vì che lỗi bằng null hoặc giá trị mặc định.