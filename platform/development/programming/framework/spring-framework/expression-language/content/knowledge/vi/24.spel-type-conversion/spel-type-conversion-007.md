# Conversion error và thông tin chẩn đoán

## Mục tiêu

Spring Expression Language (SpEL) có thể chuyển đổi giá trị giữa các kiểu dữ liệu khi đánh giá biểu thức. Việc chuyển đổi thường xuất hiện khi gán giá trị cho property, truyền đối số vào method hoặc constructor, hoặc yêu cầu kết quả của expression ở một kiểu Java cụ thể. Nếu không có converter phù hợp, dữ liệu không hợp lệ hoặc phép chuyển đổi không thể thực hiện, quá trình đánh giá sẽ phát sinh lỗi.

Chẩn đoán đúng cần xác định **giá trị nguồn**, **kiểu đích**, **thời điểm chuyển đổi** và **TypeConverter/ConversionService** mà EvaluationContext đang sử dụng. Thông báo lỗi chỉ là điểm bắt đầu; cần xem cả message code, vị trí expression và exception gốc để tìm nguyên nhân.

Sau bài này, bạn có thể:

- Nhận biết những thao tác SpEL có thể kích hoạt type conversion.
- Hiểu vai trò của TypeConverter và ConversionService.
- Phân biệt lỗi parse với lỗi chuyển đổi khi evaluate.
- Đọc SpelEvaluationException và thông tin chẩn đoán liên quan.
- Đăng ký custom Converter khi kiểu dữ liệu nghiệp vụ cần quy tắc riêng.
- Kiểm tra conversion cho property, method argument, constructor argument và kiểu kết quả.
- Tạo test tái hiện lỗi bằng đúng EvaluationContext của ứng dụng.

## 1. Khi nào SpEL thực hiện chuyển đổi kiểu?

SpEL không chỉ đọc và tính toán giá trị. Trong nhiều tình huống, nó cần chuyển một giá trị từ kiểu hiện tại sang kiểu mà thao tác yêu cầu.

### Gán giá trị cho property

Giả sử class có property số nguyên:

~~~java
public class Account {
    private Integer retryCount;

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

Expression gán một chuỗi vào property:

~~~text
retryCount = '5'
~~~

Nếu TypeConverter của context hỗ trợ chuyển String thành Integer, giá trị được gán có thể trở thành số nguyên 5. Nếu chuỗi không thể chuyển thành Integer, phép gán thất bại trong lúc đánh giá.

### Yêu cầu kiểu kết quả

Ứng dụng có thể yêu cầu kết quả ở một kiểu cụ thể:

~~~java
Expression expression = parser.parseExpression("'42'");
Integer value = expression.getValue(context, Integer.class);
~~~

Expression ban đầu tạo ra String, nhưng getValue yêu cầu Integer. SpEL sử dụng cơ chế conversion của context để chuyển kết quả nếu có converter phù hợp.

### Đối số method hoặc constructor

Khi gọi method hoặc constructor, kiểu đối số thực tế có thể khác kiểu tham số mà Java method yêu cầu. SpEL có thể dùng TypeConverter trong quá trình chuẩn bị đối số nếu conversion được hỗ trợ.

Ví dụ, một method nhận Integer có thể được gọi với giá trị expression có kiểu khác nếu context chuyển đổi được kiểu đó. Với overload, conversion và method resolution có thể ảnh hưởng tới việc chọn lời gọi. Hãy kiểm tra chữ ký method và kiểu đối số thực tế thay vì dựa vào giả định rằng mọi giá trị đều tự chuyển đổi được.

## 2. TypeConverter và ConversionService

**TypeConverter** là abstraction mà SpEL dùng để kiểm tra và thực hiện conversion. EvaluationContext cung cấp TypeConverter cho quá trình đánh giá expression.

Trong Spring, **StandardTypeConverter** là triển khai phổ biến. Nó tích hợp với Spring ConversionService để sử dụng các quy tắc chuyển đổi của Spring.

Có thể hình dung luồng xử lý:

1. SpEL xác định giá trị nguồn và kiểu đích mà thao tác cần.
2. SpEL yêu cầu TypeConverter kiểm tra khả năng chuyển đổi.
3. TypeConverter sử dụng ConversionService hoặc converter được cấu hình.
4. Nếu có conversion phù hợp, giá trị được chuyển sang kiểu đích.
5. Nếu không thể chuyển đổi, exception được phát sinh và expression không hoàn tất.

ConversionService có các thao tác kiểm tra và thực hiện conversion. Nó có thể dùng converter tích hợp sẵn của Spring hoặc converter do ứng dụng đăng ký.

Không nên coi conversion là phép ép kiểu Java thông thường. Ép kiểu chỉ thay đổi cách tham chiếu một object khi các kiểu có quan hệ tương thích; conversion có thể tạo ra một giá trị mới từ dữ liệu có kiểu khác, ví dụ String thành Integer hoặc String thành một enum.

## 3. Cấu hình ConversionService cho SpEL

Có thể tạo StandardTypeConverter từ ConversionService và gắn vào StandardEvaluationContext.

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

Khi đó, các conversion trong expression sử dụng ConversionService đã cấu hình.

Ví dụ đánh giá:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression = parser.parseExpression("'125'");
Integer result = expression.getValue(context, Integer.class);
~~~

Nếu ConversionService có converter phù hợp, kết quả là Integer 125.

Trong ứng dụng Spring, có thể sử dụng ConversionService do application context cung cấp thay vì tự tạo một instance riêng. Điều này giúp SpEL dùng cùng quy tắc conversion mà phần còn lại của ứng dụng đang sử dụng.

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(rootObject);

context.setTypeConverter(
    new StandardTypeConverter(applicationConversionService)
);
~~~

Tên biến applicationConversionService trong ví dụ đại diện cho ConversionService được ứng dụng cấu hình và cung cấp. Hãy dùng đúng bean hoặc instance mà ứng dụng quản lý.

Nếu ứng dụng sử dụng SimpleEvaluationContext, hãy cấu hình conversion service thông qua builder phù hợp với phiên bản Spring đang chạy. Không giả định hai loại EvaluationContext có cùng builder hoặc cùng tập khả năng.

## 4. Các loại conversion thường gặp

Spring ConversionService thường cung cấp nhiều conversion phổ biến, tùy source type, target type và cấu hình.

| Kiểu nguồn | Kiểu đích | Ví dụ dữ liệu |
|---|---|---|
| String | Integer | "42" |
| String | Boolean | "true" |
| String | Enum | "ACTIVE" |
| String | BigDecimal | "125.50" |
| Number | Một kiểu Number khác | Integer sang Long |
| Collection | Collection có element type khác | List<String> sang List<Integer>, nếu conversion hỗ trợ |
| String | LocalDate | "2026-11-12", khi có converter/formatter phù hợp |

Không nên giả định mọi chuỗi đều hợp lệ. Ví dụ:

- Chuỗi rỗng có thể có hành vi khác nhau tùy converter.
- Chuỗi chứa ký tự không phải chữ số không thể chuyển thành Integer theo converter số thông thường.
- Tên enum phải khớp quy tắc của converter.
- Ngày tháng phụ thuộc định dạng và converter/formatter được cấu hình.
- Collection conversion còn phụ thuộc khả năng chuyển từng phần tử và thông tin kiểu đích.

Nếu định dạng dữ liệu đến từ người dùng hoặc file cấu hình, hãy xác thực trước khi đưa vào expression. ConversionService hỗ trợ chuyển kiểu; nó không thay thế validation nghiệp vụ.

## 5. Đọc thông báo lỗi conversion

Khi SpEL không thể chuyển đổi giá trị, exception thường được thể hiện qua **SpelEvaluationException**. Thông báo có thể chứa message code và thông tin về kiểu nguồn, kiểu đích hoặc thao tác không thực hiện được.

Ví dụ minh họa:

~~~text
EL1001E: Type conversion problem, cannot convert from java.lang.String to java.lang.Integer
~~~

Nội dung cụ thể phụ thuộc phiên bản Spring, converter và dữ liệu thực tế. Không nên viết logic ứng dụng dựa trên việc so sánh toàn bộ chuỗi message vì wording có thể thay đổi.

Khi đọc lỗi, xác định:

- Kiểu nguồn: expression hoặc property đang trả về kiểu gì?
- Kiểu đích: thao tác đang yêu cầu kiểu gì?
- Giá trị thực tế: dữ liệu có đúng định dạng và miền giá trị không?
- Conversion path: converter nào được sử dụng hoặc đang thiếu?
- Vị trí expression: lỗi phát sinh ở phần nào của biểu thức?
- Exception gốc: converter có ném lỗi chi tiết hơn ở cause chain không?

Thông báo kiểu nguồn và kiểu đích thường giúp khoanh vùng nhanh. Tuy nhiên, nếu lỗi xuất phát từ một converter tùy chỉnh, nguyên nhân sâu hơn có thể là định dạng nghiệp vụ hoặc validation bên trong converter.

## 6. Phân biệt parse error và conversion error

SpEL có các giai đoạn khác nhau, nên cần xác định lỗi xảy ra ở giai đoạn nào.

**Parse error** xuất hiện khi parser không thể phân tích cú pháp expression. Ví dụ, dấu nháy không cân bằng hoặc toán tử đặt sai vị trí có thể khiến expression không được tạo thành công.

**Evaluation error** xuất hiện sau khi expression đã parse, khi SpEL thực hiện truy cập property, gọi method, gán giá trị hoặc conversion.

Ví dụ:

~~~java
ExpressionParser parser = new SpelExpressionParser();

Expression expression =
    parser.parseExpression("'not-a-number'");

Integer value = expression.getValue(context, Integer.class);
~~~

Expression có cú pháp hợp lệ và parse thành công. Lỗi chỉ xuất hiện khi getValue yêu cầu chuyển String thành Integer.

Tách hai giai đoạn giúp tránh điều tra nhầm. Nếu parse thất bại, kiểm tra cú pháp. Nếu parse thành công nhưng evaluate thất bại, kiểm tra root object, biến, property, method, converter và dữ liệu đầu vào.

## 7. Lấy thông tin chẩn đoán từ exception

Có thể bắt SpelEvaluationException tại ranh giới nơi ứng dụng đánh giá expression:

~~~java
try {
    Integer result = expression.getValue(context, Integer.class);
    return result;
}
catch (SpelEvaluationException ex) {
    // Ghi nhận mã lỗi, vị trí và ID expression.
    throw ex;
}
~~~

SpelEvaluationException cung cấp thông tin như message code, các giá trị được chèn vào thông báo và vị trí liên quan trong expression. Các accessor cụ thể có thể được kiểm tra theo phiên bản Spring đang dùng.

Ví dụ cách ghi nhận thông tin có cấu trúc:

~~~java
catch (SpelEvaluationException ex) {
    logger.warn(
        "SpEL evaluation failed: expressionId={}, messageCode={}, position={}",
        expressionId,
        ex.getMessageCode(),
        ex.getPosition()
    );
    throw ex;
}
~~~

Nếu cần chẩn đoán sâu hơn, kiểm tra cause chain để tìm ConversionException hoặc exception cụ thể do converter phát sinh. Với Spring ConversionService, các lỗi có thể thuộc nhóm như ConverterNotFoundException hoặc ConversionFailedException.

Không phải mọi conversion failure đều có cùng loại exception gốc. Hãy ghi nhận class của exception và cause thực tế thay vì giả định một loại duy nhất.

### Thông tin nên ghi nhận

Một log chẩn đoán hữu ích thường có:

- ID hoặc tên rule/expression.
- Phiên bản expression.
- Message code của SpEL.
- Vị trí lỗi nếu có.
- Kiểu nguồn và kiểu đích khi xác định được.
- Class của exception gốc.
- Correlation ID hoặc request ID.
- Loại EvaluationContext và conversion configuration có liên quan.

Không ghi toàn bộ expression input hoặc giá trị biến nếu chúng có thể chứa mật khẩu, token, dữ liệu cá nhân hay thông tin nhạy cảm. Có thể ghi kiểu dữ liệu, độ dài hoặc mã tham chiếu thay vì giá trị thô.

## 8. Đăng ký custom Converter

Khi kiểu nghiệp vụ có quy tắc chuyển đổi riêng, ứng dụng có thể đăng ký Converter với ConversionService.

Ví dụ chuyển một chuỗi mã trạng thái thành enum:

~~~java
public enum OrderStatus {
    NEW, PAID, SHIPPED, CANCELLED
}
~~~

Converter:

~~~java
public class StringToOrderStatusConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        if (source == null || source.isBlank()) {
            throw new IllegalArgumentException(
                "Order status must not be blank");
        }

        return OrderStatus.valueOf(
            source.trim().toUpperCase(Locale.ROOT)
        );
    }
}
~~~

Đăng ký converter:

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(
    new StringToOrderStatusConverter()
);

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

Sau đó, expression hoặc thao tác gán cần chuyển String thành OrderStatus có thể sử dụng converter đã đăng ký.

Trong ứng dụng Spring, converter thường được đăng ký vào ConversionService dùng chung theo cấu hình của ứng dụng. Hãy tránh tạo một ConversionService riêng trong mỗi nơi nếu các phần khác của ứng dụng cần cùng quy tắc conversion.

Converter nên có hành vi xác định, thông báo lỗi rõ và không thực hiện side effect. Không nên dùng converter để truy cập database, gọi service từ xa hoặc thực hiện nghiệp vụ có trạng thái.

## 9. Conversion trong collection và generic type

Conversion không chỉ áp dụng cho một giá trị đơn. Spring có thể chuyển đổi collection hoặc phần tử của collection khi có đủ thông tin kiểu và converter phù hợp.

Ví dụ, một thao tác có thể yêu cầu List<Integer> trong khi nguồn là List<String>. Việc chuyển đổi cần converter cho từng phần tử và thông tin target type đủ cụ thể.

Khi làm việc với generic collection, TypeDescriptor giúp mô tả kiểu nguồn và kiểu đích chi tiết hơn kiểu Class đơn giản. Điều này quan trọng vì List.class không thể tự thể hiện rằng phần tử cần là Integer hay String.

Nếu conversion collection thất bại, hãy xác định phần tử nào không chuyển được. Có thể kiểm thử converter trực tiếp với từng phần tử để tách lỗi dữ liệu khỏi lỗi cấu trúc collection.

Không nên giả định rằng mọi collection đều có thể chuyển đổi giữa mọi kiểu. Converter phải hỗ trợ conversion cần thiết và collection đích phải có thể được tạo theo cơ chế được dùng.

## 10. Kiểm tra converter trước khi đánh giá expression

Nếu ứng dụng cần chẩn đoán trước một conversion, có thể kiểm tra trực tiếp ConversionService:

~~~java
boolean supported = conversionService.canConvert(
    String.class,
    Integer.class
);
~~~

Nếu cần thực hiện conversion trực tiếp:

~~~java
Integer value = conversionService.convert("42", Integer.class);
~~~

Cách kiểm tra này giúp xác định ConversionService có hỗ trợ cặp kiểu đơn giản hay không. Tuy nhiên, nó không thay thế việc kiểm thử expression đầy đủ vì SpEL còn có root object, property accessor, method resolver, target descriptor và ngữ cảnh đánh giá.

Với generic type hoặc conversion phụ thuộc metadata, hãy sử dụng API TypeDescriptor phù hợp thay vì chỉ kiểm tra bằng Class.

Một quy trình hữu ích là:

1. Kiểm tra converter độc lập với dữ liệu đầu vào.
2. Kiểm tra conversion service mà EvaluationContext đang sử dụng.
3. Đánh giá expression với cùng context.
4. So sánh kiểu kết quả thực tế với kiểu đích ứng dụng yêu cầu.

## 11. Những lỗi conversion thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| String không chuyển thành Integer | Chuỗi chứa ký tự không phải số hoặc rỗng | Xác thực định dạng trước khi evaluate |
| Không tìm thấy converter | ConversionService không có converter cho cặp kiểu | Đăng ký Converter phù hợp |
| Custom converter không được gọi | Converter được đăng ký vào service khác với service của context | Kiểm tra TypeConverter và ConversionService thực tế |
| Chuyển đổi enum thất bại | Tên enum sai hoặc khác quy tắc chuẩn hóa | Chuẩn hóa input và định nghĩa converter |
| Chuyển đổi ngày thất bại | Format không khớp hoặc thiếu converter/formatter | Quy định format và kiểm thử locale |
| Gán property thất bại | Giá trị nguồn không chuyển được sang kiểu property | Kiểm tra setter, target type và conversion service |
| getValue với target type thất bại | Kết quả expression không chuyển được sang kiểu được yêu cầu | Kiểm tra kiểu trả về và converter |
| Method invocation thất bại | Đối số không phù hợp tham số method | Kiểm tra chữ ký và kiểu đối số |
| Chỉ lỗi trong production | ConversionService hoặc context configuration khác test | Dùng chung context factory và cấu hình conversion |
| Message không đủ rõ | Chỉ log message chung, bỏ qua cause chain | Ghi message code, vị trí và exception gốc |

## 12. Kiểm thử conversion và lỗi

Nên kiểm thử cả trường hợp chuyển đổi thành công và thất bại.

Ví dụ kiểm tra conversion String thành Integer trong SpEL:

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

Ví dụ kiểm tra conversion thất bại:

~~~java
@Test
void reportsInvalidIntegerConversion() {
    ExpressionParser parser = new SpelExpressionParser();
    StandardEvaluationContext context =
        new StandardEvaluationContext();

    Expression expression =
        parser.parseExpression("'not-a-number'");

    assertThrows(
        SpelEvaluationException.class,
        () -> expression.getValue(context, Integer.class)
    );
}
~~~

Với custom converter, kiểm tra:

- Input hợp lệ được chuyển thành đúng kiểu.
- Input rỗng hoặc null theo hợp đồng.
- Input sai định dạng tạo lỗi có nguyên nhân rõ.
- Converter được đăng ký vào ConversionService đúng.
- StandardTypeConverter trong EvaluationContext sử dụng đúng service.
- Expression gọi conversion qua đúng thao tác thực tế.
- Cấu hình trong test giống production.

Với collection, thêm trường hợp một phần tử không hợp lệ giữa các phần tử hợp lệ. Xác định rõ conversion thất bại toàn bộ hay ứng dụng có chính sách xử lý từng phần tử riêng.

## 13. Quy trình chẩn đoán conversion error

Khi một expression phát sinh lỗi conversion:

1. **Xác định giai đoạn lỗi.** Kiểm tra lỗi xảy ra lúc parse hay lúc gọi getValue/setValue.
2. **Ghi lại expression ID và vị trí.** Dùng thông tin từ exception để xác định phần expression gây lỗi.
3. **Xác định source và target type.** Kiểm tra kiểu thực tế của giá trị và kiểu mà thao tác yêu cầu.
4. **Kiểm tra dữ liệu.** Xác nhận chuỗi, số, enum hoặc collection có đúng định dạng và miền giá trị.
5. **Kiểm tra context.** Xác nhận TypeConverter và ConversionService mà expression đang sử dụng.
6. **Kiểm tra converter.** Xem converter phù hợp có được đăng ký và có nhận đúng kiểu không.
7. **Đọc cause chain.** Tìm exception cụ thể do Spring conversion hoặc converter tùy chỉnh phát sinh.
8. **Tái hiện bằng test.** Dùng cùng root object, expression, context và dữ liệu gây lỗi.
9. **Sửa tại đúng ranh giới.** Chuẩn hóa dữ liệu, bổ sung converter hoặc sửa kiểu đích theo hợp đồng.
10. **Kiểm thử hồi quy.** Bao phủ dữ liệu hợp lệ, sai định dạng, null và các kiểu biên.

Đừng sửa lỗi bằng cách ép mọi giá trị thành String hoặc trả null khi conversion thất bại. Điều đó có thể che giấu dữ liệu sai và khiến nghiệp vụ tiếp tục với giá trị không hợp lệ.

## 14. Thực hành tốt

- Xác định rõ source type và target type cho mọi conversion quan trọng.
- Dùng ConversionService chung của ứng dụng khi cần quy tắc chuyển đổi nhất quán.
- Gắn StandardTypeConverter với đúng ConversionService trong EvaluationContext.
- Đăng ký custom Converter cho kiểu nghiệp vụ có quy tắc riêng.
- Giữ converter nhỏ, xác định và không có side effect.
- Xác thực dữ liệu trước khi đánh giá expression nếu định dạng có quy tắc nghiệp vụ.
- Không phụ thuộc vào wording của exception để điều khiển logic ứng dụng.
- Ghi message code, vị trí, kiểu dữ liệu và cause chain khi chẩn đoán.
- Không log giá trị nhạy cảm chỉ để tìm lỗi conversion.
- Kiểm thử conversion độc lập và trong expression thực tế.
- Dùng cùng EvaluationContext factory và ConversionService configuration trong test lẫn production.
- Phân biệt parse error, evaluation error và lỗi do converter bên trong.

## 15. Checklist review

Trước khi đưa expression có conversion vào sử dụng, hãy kiểm tra:

- [ ] Thao tác có thể kích hoạt conversion đã được xác định.
- [ ] Kiểu nguồn và kiểu đích đúng với hợp đồng dữ liệu.
- [ ] TypeConverter trong context được cấu hình như mong đợi.
- [ ] ConversionService cần thiết đã được đăng ký.
- [ ] Custom Converter xử lý dữ liệu hợp lệ, null và sai định dạng.
- [ ] Conversion collection có thông tin generic type phù hợp.
- [ ] Parse error được phân biệt với conversion/evaluation error.
- [ ] Exception message code, vị trí và cause chain có thể được ghi nhận.
- [ ] Log không làm lộ dữ liệu nhạy cảm.
- [ ] Có test thành công, thất bại và dữ liệu biên.
- [ ] Test dùng cấu hình conversion giống production.
- [ ] Lỗi conversion không bị che bằng giá trị mặc định hoặc null ngoài ý muốn.

## Kết luận

Conversion error trong SpEL xuất hiện khi một thao tác yêu cầu kiểu dữ liệu khác với kiểu giá trị hiện có và TypeConverter không thể thực hiện chuyển đổi. EvaluationContext cung cấp TypeConverter; StandardTypeConverter có thể tích hợp với ConversionService của Spring để dùng converter mặc định hoặc converter do ứng dụng đăng ký. Khi chẩn đoán, hãy xác định source type, target type, vị trí expression, cấu hình conversion và exception gốc. Kiểm thử converter độc lập lẫn trong expression thực tế, đồng thời giữ dữ liệu đầu vào có kiểu rõ ràng và không che giấu lỗi bằng cách trả null tùy tiện.