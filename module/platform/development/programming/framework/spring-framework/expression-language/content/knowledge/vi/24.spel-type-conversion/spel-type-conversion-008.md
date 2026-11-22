# Phân biệt conversion với validation

## Mục tiêu

Sau bài này, bạn có thể phân biệt chuyển đổi kiểu dữ liệu (conversion) với kiểm tra tính hợp lệ (validation) khi làm việc với Spring Expression Language (SpEL); xác định những thời điểm SpEL tự yêu cầu chuyển đổi; cấu hình TypeConverter hoặc ConversionService; và thiết kế bước kiểm tra dữ liệu sau khi chuyển đổi. Bạn cũng sẽ biết cách xử lý giá trị null, lỗi chuyển đổi, giới hạn số, định dạng và các quy tắc nghiệp vụ mà conversion không thể tự bảo đảm.

## 1. Conversion và validation giải quyết hai vấn đề khác nhau

**Conversion** thay đổi cách biểu diễn hoặc kiểu dữ liệu của một giá trị để nó phù hợp với nơi sử dụng. Ví dụ, chuyển chuỗi "42" thành Integer hoặc chuyển một giá trị thành kiểu ngày giờ mà ứng dụng cần.

**Validation** kiểm tra dữ liệu có đáp ứng các điều kiện được yêu cầu hay không. Ví dụ, tuổi phải lớn hơn hoặc bằng 18, email phải có định dạng được chấp nhận, ngày kết thúc phải sau ngày bắt đầu hoặc tổng tiền phải nằm trong hạn mức.

Hai việc này có liên quan nhưng không thay thế cho nhau:

| Tình huống | Conversion | Validation |
|---|---|---|
| Chuỗi "42" thành Integer | Chuyển được nếu converter hỗ trợ | Kiểm tra 42 có nằm trong miền tuổi hợp lệ không |
| Chuỗi "abc" thành Integer | Thường thất bại vì không biểu diễn được số nguyên | Báo dữ liệu đầu vào không hợp lệ |
| Chuỗi "999" thành Integer | Có thể chuyển thành công | Có thể không hợp lệ nếu giới hạn tối đa là 120 |
| Ngày "2026-02-30" | Chuyển đổi ngày có thể thất bại vì ngày không tồn tại | Kiểm tra ngày có nằm trong thời hạn nghiệp vụ không |
| Số tiền -10.00 thành BigDecimal | Chuyển được thành công | Có thể không hợp lệ nếu số tiền phải không âm |

Conversion trả lời câu hỏi: "Giá trị này có thể được biểu diễn bằng kiểu đích không?" Validation trả lời: "Giá trị sau khi được hiểu đúng có được phép sử dụng không?"

## 2. SpEL chuyển đổi kiểu ở những thời điểm nào?

SpEL sử dụng TypeConverter của EvaluationContext khi một thao tác cần giá trị ở kiểu khác. Một số tình huống thường gặp:

- Khi yêu cầu kiểu kết quả cụ thể qua getValue với kiểu đích.
- Khi gán giá trị vào property có kiểu khác với biểu thức nguồn.
- Khi truyền đối số vào một phương thức và cần chuyển đổi sang kiểu tham số.
- Khi thực hiện các thao tác khác mà cơ chế đánh giá cần chuyển giá trị sang kiểu đích.

Ví dụ yêu cầu kết quả Integer:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("'42'");

Integer value = expression.getValue(Integer.class);
~~~

Biểu thức literal tạo ra một String. Khi ứng dụng yêu cầu kết quả Integer, SpEL dùng TypeConverter của context để thử chuyển giá trị sang kiểu đích.

Ví dụ truyền đối số cho phương thức:

~~~text
#accountService.findById('42')
~~~

Nếu phương thức được chọn nhận một kiểu số như Long và converter hỗ trợ chuyển String sang Long, SpEL có thể chuyển đối số trước khi gọi phương thức.

Chuyển đổi chỉ xảy ra khi thao tác cần nó. Không nên giả định mọi giá trị trong context sẽ được chuẩn hóa ngay khi đăng ký biến hoặc ngay khi parse biểu thức.

## 3. TypeConverter trong EvaluationContext

EvaluationContext cung cấp TypeConverter để SpEL thực hiện chuyển đổi. StandardEvaluationContext sử dụng StandardTypeConverter theo cấu hình mặc định.

Có thể lấy converter từ context:

~~~java
TypeConverter converter = context.getTypeConverter();
~~~

Và kiểm tra một cặp kiểu có thể chuyển đổi hay không:

~~~java
boolean canConvert =
    converter.canConvert(sourceTypeDescriptor, targetTypeDescriptor);
~~~

Khi cần tùy chỉnh, ứng dụng có thể cung cấp một TypeConverter khác cho context. Ví dụ, StandardTypeConverter có thể được tạo từ một Spring ConversionService:

~~~java
ConversionService conversionService = ...;

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

Nhờ đó, SpEL sử dụng các converter và formatter đã đăng ký trong ConversionService khi cần chuyển đổi.

Hãy cấu hình converter một cách nhất quán với phần còn lại của ứng dụng. Nếu cùng một giá trị được chuyển đổi ở controller, service và SpEL nhưng mỗi nơi dùng quy tắc khác nhau, kết quả có thể khó dự đoán.

## 4. ConversionService và converter tùy chỉnh

Spring ConversionService cung cấp cơ chế chuyển đổi kiểu tập trung. Ứng dụng có thể đăng ký converter cho các cặp kiểu cụ thể, ví dụ String sang một kiểu mã nghiệp vụ hoặc một kiểu giá trị riêng.

Ví dụ một kiểu mã:

~~~java
public record CustomerCode(String value) {
}
~~~

Converter:

~~~java
public class StringToCustomerCodeConverter
        implements Converter<String, CustomerCode> {

    @Override
    public CustomerCode convert(String source) {
        if (source == null) {
            return null;
        }
        return new CustomerCode(source.trim().toUpperCase(Locale.ROOT));
    }
}
~~~

Sau khi converter được đăng ký vào ConversionService và ConversionService được cung cấp cho StandardTypeConverter, SpEL có thể sử dụng quy tắc đó khi cần chuyển String thành CustomerCode.

Converter nên tập trung vào chuyển đổi và chuẩn hóa biểu diễn. Ví dụ trên loại bỏ khoảng trắng và chuẩn hóa chữ hoa. Nếu CustomerCode còn phải thỏa mãn quy tắc như tiền tố hợp lệ, trạng thái đang hoạt động hoặc quyền sử dụng, những điều kiện đó thuộc validation hoặc logic nghiệp vụ riêng.

Không nên đặt tất cả quy tắc nghiệp vụ vào converter. Một converter được gọi tự động ở nhiều vị trí nên có hành vi đơn giản, xác định và không gây tác dụng phụ.

## 5. Ví dụ: getValue với kiểu kết quả đích

Giả sử ứng dụng nhận một biến dạng chuỗi nhưng muốn lấy kết quả dạng Integer:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setVariable("quantityText", "25");

ExpressionParser parser = new SpelExpressionParser();
Expression expression =
    parser.parseExpression("#quantityText");

Integer quantity =
    expression.getValue(context, Integer.class);
~~~

Nếu converter mặc định hỗ trợ chuyển String sang Integer và chuỗi có định dạng số hợp lệ, kết quả là 25.

Tuy nhiên, việc lấy được Integer không chứng minh quantity hợp lệ theo nghiệp vụ. Ví dụ, hệ thống chỉ cho phép số lượng từ 1 đến 10. Giá trị 25 chuyển đổi thành công nhưng vẫn phải bị validation từ chối.

Có thể kiểm tra sau khi chuyển đổi:

~~~java
if (quantity == null || quantity < 1 || quantity > 10) {
    throw new IllegalArgumentException(
        "Quantity must be between 1 and 10"
    );
}
~~~

Hãy giữ rõ hai bước: chuyển kiểu trước, sau đó kiểm tra miền giá trị. Nếu cần báo lỗi thân thiện, hãy chuyển lỗi kỹ thuật của conversion và lỗi nghiệp vụ của validation thành thông báo phù hợp ở lớp ứng dụng.

## 6. Gán property và chuyển đổi giá trị

SpEL có thể gán giá trị vào property của root object:

~~~text
quantity = '25'
~~~

Giả sử property quantity có kiểu Integer nhưng biểu thức bên phải tạo ra String. Nếu EvaluationContext có TypeConverter hỗ trợ cặp kiểu đó và property có thể ghi, SpEL có thể chuyển giá trị trước khi gọi setter hoặc thực hiện thao tác ghi.

Ví dụ Java:

~~~java
ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("quantity = '25'");

StandardEvaluationContext context =
    new StandardEvaluationContext();

OrderDraft draft = new OrderDraft();

expression.getValue(context, draft);
~~~

Sau phép gán, property quantity có thể nhận giá trị Integer 25.

Conversion không kiểm tra các điều kiện như quantity phải lớn hơn 0 hoặc không vượt tồn kho. Nếu property nhận được một số nguyên hợp lệ về kiểu nhưng sai về nghiệp vụ, ứng dụng vẫn cần validation.

Ngoài ra, việc ghi property còn phụ thuộc PropertyAccessor và quyền ghi của EvaluationContext. Một TypeConverter có thể chuyển giá trị nhưng không tự cấp quyền ghi vào một property chỉ đọc.

## 7. Conversion khi gọi method

SpEL có thể chuyển đổi đối số khi gọi phương thức nếu TypeConverter hỗ trợ kiểu đích và method resolution tìm được phương thức phù hợp.

Ví dụ, một service có method:

~~~java
public Account findById(Long id) {
    // Tìm tài khoản theo ID.
}
~~~

Biểu thức:

~~~text
#accountService.findById('42')
~~~

có thể chuyển chuỗi '42' thành Long trước khi gọi method nếu context và converter hỗ trợ.

Điều này tiện cho biểu thức ngắn, nhưng không nên dùng conversion ngầm để che giấu dữ liệu đầu vào chưa được xác thực. Nếu ID đến từ request, hãy kiểm tra nó có đúng định dạng và có thuộc phạm vi được phép truy cập trước khi gọi service.

Một method có thể ném lỗi vì không tìm thấy tài khoản, tài khoản bị khóa hoặc người gọi không có quyền. Đó không phải lỗi conversion. Hãy phân biệt lỗi chuyển đổi đối số với lỗi nghiệp vụ do chính method thực hiện.

## 8. Conversion không kiểm tra miền giá trị

Một giá trị có thể chuyển đổi thành công nhưng vẫn không hợp lệ.

Ví dụ:

~~~java
Integer age = Integer.valueOf("150");
~~~

Chuyển đổi thành công vì 150 là số nguyên hợp lệ. Tuy nhiên, nếu hệ thống quy định tuổi người dùng tối đa là 120, giá trị này phải bị validation từ chối.

Tương tự:

- -5 chuyển thành Integer nhưng có thể không hợp lệ nếu số lượng không âm.
- 999999.99 chuyển thành BigDecimal nhưng có thể vượt hạn mức giao dịch.
- Một chuỗi có thể chuyển thành enum nhưng trạng thái đó có thể không được phép trong quy trình hiện tại.
- Một ngày có thể chuyển thành LocalDate nhưng nằm ngoài thời gian đăng ký cho phép.
- Một mã có thể chuyển thành CustomerCode nhưng không tồn tại trong hệ thống.

Không dùng canConvert như một phép kiểm tra nghiệp vụ. Nó chỉ cho biết converter có khả năng xử lý cặp kiểu theo cấu hình; nó không xác nhận giá trị cụ thể được phép.

## 9. Validation cần kiểm tra điều gì?

Validation thường gồm nhiều lớp điều kiện:

**Kiểm tra cấu trúc và kiểu dữ liệu**

- Có thể chuyển thành kiểu mong muốn không?
- Chuỗi có đúng định dạng không?
- Giá trị có null khi trường bắt buộc không?

**Kiểm tra miền giá trị**

- Số có nằm trong giới hạn tối thiểu và tối đa không?
- Chuỗi có độ dài cho phép không?
- Ngày có nằm trong khoảng thời gian hợp lệ không?

**Kiểm tra quan hệ giữa các trường**

- Ngày kết thúc có sau ngày bắt đầu không?
- Số lượng có phù hợp với đơn giá và tổng tiền không?
- Địa chỉ giao hàng có tương thích với phương thức vận chuyển không?

**Kiểm tra nghiệp vụ và trạng thái**

- Mã khách hàng có tồn tại và đang hoạt động không?
- Tài khoản có quyền thực hiện thao tác không?
- Đơn hàng có đang ở trạng thái cho phép cập nhật không?
- Hạn mức hiện tại có đủ cho giao dịch không?

Một converter thường chỉ nhận một giá trị nguồn và tạo một giá trị đích. Validation nghiệp vụ có thể cần nhiều trường, dữ liệu từ repository hoặc trạng thái hiện tại của hệ thống; hãy đặt nó ở lớp phù hợp thay vì ép vào conversion.

## 10. Sử dụng Bean Validation hoặc Spring Validator

Java Bean Validation (Jakarta Validation) cung cấp annotation để mô tả nhiều ràng buộc dữ liệu:

~~~java
public class RegistrationRequest {

    @NotBlank
    private String username;

    @Min(18)
    @Max(120)
    private Integer age;

    @Email
    private String email;

    // getters and setters
}
~~~

Sau khi dữ liệu được bind và chuyển đổi sang các kiểu field, ứng dụng có thể chạy Validator để kiểm tra các constraint.

Với Spring Validator, có thể triển khai các quy tắc riêng cho một object:

~~~java
public class RegistrationValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return RegistrationRequest.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationRequest request =
            (RegistrationRequest) target;

        if (request.getAge() != null && request.getAge() < 18) {
            errors.rejectValue(
                "age",
                "registration.age.tooYoung"
            );
        }
    }
}
~~~

SpEL không tự chạy toàn bộ Bean Validation hoặc Spring Validator chỉ vì một giá trị được chuyển đổi. Ứng dụng phải gọi validator ở đúng bước trong luồng xử lý.

Có thể dùng SpEL để diễn đạt một điều kiện đơn giản, nhưng validation của request hoặc object thường nên được tổ chức bằng cơ chế validation chuyên dụng để có lỗi theo field, message code và khả năng tái sử dụng.

## 11. Xử lý null và chuỗi rỗng

Null và chuỗi rỗng là hai trạng thái khác nhau:

- null nghĩa là không có giá trị object.
- "" là một String tồn tại nhưng không có ký tự.
- Chuỗi chỉ chứa khoảng trắng vẫn là một String có ký tự khoảng trắng.

Converter có thể xử lý các trường hợp này theo quy tắc riêng. Một số converter của Spring có thể coi chuỗi rỗng hoặc chuỗi chỉ có khoảng trắng là giá trị null trong một số phép chuyển đổi; hành vi cụ thể phụ thuộc converter và kiểu đích.

Đừng dựa vào giả định chung rằng mọi chuỗi rỗng đều thành null hoặc mọi giá trị null đều bị từ chối.

Ví dụ, nếu username bắt buộc có nội dung:

~~~java
if (username == null || username.isBlank()) {
    throw new IllegalArgumentException(
        "Username is required"
    );
}
~~~

Nếu trường không bắt buộc, ứng dụng có thể cho phép null nhưng vẫn cần xác định cách xử lý chuỗi rỗng. Hãy chuẩn hóa đầu vào theo hợp đồng API rồi mới chuyển đổi hoặc validation, đặc biệt khi khoảng trắng có ý nghĩa trong dữ liệu.

## 12. Conversion, parsing và định dạng

Conversion và parsing thường liên quan nhưng không hoàn toàn đồng nghĩa trong cách thiết kế ứng dụng.

- Parsing thường diễn giải văn bản theo một cú pháp hoặc định dạng cụ thể.
- Conversion chuyển một giá trị từ kiểu nguồn sang kiểu đích.
- Formatting chuyển giá trị thành biểu diễn văn bản để hiển thị hoặc đọc từ input.
- Validation xác nhận giá trị đáp ứng quy tắc được yêu cầu.

Ví dụ, ngày 31/12/2026 có thể được parse theo định dạng ngày-tháng-năm. Nếu dùng nhầm định dạng tháng-ngày-năm, kết quả có thể sai hoặc không parse được.

Với tiền tệ hoặc ngày giờ, hãy cấu hình locale, timezone và format rõ ràng. Không nên dựa vào định dạng mặc định của máy chủ hoặc môi trường chạy, vì cùng một chuỗi có thể được hiểu khác nhau giữa các locale.

Sau khi parse thành công, vẫn cần validation: ngày có nằm trong thời hạn cho phép không, số tiền có đúng đơn vị không và giá trị có phù hợp với trạng thái nghiệp vụ không.

## 13. Sử dụng TypeDescriptor khi cần metadata kiểu

Spring sử dụng TypeDescriptor để mô tả kiểu dữ liệu cùng metadata liên quan, ví dụ kiểu phần tử của collection, kiểu key/value của Map hoặc annotation trên property.

Điều này quan trọng khi chuyển đổi collection có generic type. Ví dụ, một List<String> cần được chuyển thành List<Integer>; chỉ biết kiểu đích bên ngoài là List.class chưa đủ để mô tả đầy đủ kiểu phần tử.

TypeDescriptor giúp converter hiểu kiểu nguồn và đích chi tiết hơn. Khi viết converter tùy chỉnh cho collection hoặc property có metadata, hãy kiểm tra TypeDescriptor thay vì chỉ dựa vào Class<?>.

Tuy nhiên, metadata kiểu không thay thế validation nội dung. Một List<Integer> vẫn có thể chứa giá trị ngoài giới hạn nghiệp vụ; TypeDescriptor chỉ hỗ trợ việc chuyển đổi theo kiểu được mô tả.

## 14. Xử lý lỗi conversion và validation riêng biệt

Conversion có thể thất bại vì:

- Chuỗi không thể parse thành kiểu đích.
- Kiểu nguồn không được converter hỗ trợ.
- Giá trị không thể biểu diễn bằng kiểu đích.
- Converter tùy chỉnh ném lỗi.
- Định dạng ngày, số hoặc enum không phù hợp.

Validation có thể thất bại vì:

- Giá trị null ở trường bắt buộc.
- Giá trị nằm ngoài min/max.
- Hai trường không nhất quán.
- Trạng thái không được phép.
- Người dùng không có quyền thực hiện thao tác.
- Dữ liệu không thỏa quy tắc nghiệp vụ.

Hãy giữ hai nhóm lỗi riêng trong luồng xử lý. Lỗi conversion thường chỉ ra dữ liệu không thể chuyển sang kiểu đích; lỗi validation cho biết giá trị đã được hiểu nhưng không được phép sử dụng.

Khi bắt lỗi ở Java, hãy giữ nguyên nguyên nhân gốc và ánh xạ sang thông báo phù hợp. Không nên trả về một giá trị mặc định tùy tiện khi conversion thất bại, vì điều đó có thể biến input sai thành dữ liệu có vẻ hợp lệ.

## 15. Một luồng xử lý điển hình

Một quy trình rõ ràng có thể gồm các bước:

1. Nhận dữ liệu đầu vào từ request hoặc nguồn cấu hình.
2. Kiểm tra các yêu cầu định dạng cơ bản nếu cần.
3. Chuyển đổi sang kiểu dữ liệu của mô hình.
4. Chạy validation cấu trúc và miền giá trị.
5. Chạy validation liên trường hoặc nghiệp vụ.
6. Chỉ khi hợp lệ mới thực hiện thao tác ghi hoặc gọi service có tác dụng phụ.

Ví dụ:

~~~java
String quantityText = request.getParameter("quantity");

Integer quantity;
try {
    quantity = conversionService.convert(
        quantityText,
        Integer.class
    );
}
catch (ConversionException ex) {
    throw new BadRequestException("Quantity must be an integer", ex);
}

if (quantity == null || quantity < 1 || quantity > 10) {
    throw new BadRequestException("Quantity must be between 1 and 10");
}

orderService.updateQuantity(orderId, quantity);
~~~

Trong thực tế, cách gọi ConversionService có thể cần cung cấp cả kiểu nguồn và kiểu đích tùy API đang dùng. Ví dụ trên minh họa thứ tự xử lý; hãy dùng đúng overload tương ứng với phiên bản Spring của dự án.

Không nên dùng SpEL làm nơi duy nhất để xác thực dữ liệu đầu vào. SpEL có thể biểu diễn điều kiện, nhưng ứng dụng vẫn cần một luồng validation rõ ràng trước khi thực hiện hành động.

## 16. Conversion trong SimpleEvaluationContext và StandardEvaluationContext

Cả hai loại EvaluationContext đều cung cấp TypeConverter cho quá trình đánh giá, nhưng phạm vi tính năng của chúng khác nhau.

**StandardEvaluationContext** cung cấp nhiều khả năng SpEL hơn và cho phép cấu hình TypeConverter, PropertyAccessor, MethodResolver, BeanResolver và các cơ chế khác.

**SimpleEvaluationContext** giới hạn một số khả năng ngôn ngữ và quyền truy cập, nhưng vẫn có thể dùng TypeConverter để hỗ trợ chuyển đổi trong các thao tác được phép. Có thể cấu hình converter qua builder phù hợp của phiên bản Spring đang sử dụng.

Không nên hiểu rằng context giới hạn sẽ tự động validate dữ liệu tốt hơn. Việc giảm quyền truy cập và việc xác thực giá trị là hai vấn đề riêng biệt. Hãy chọn context theo khả năng biểu thức cần dùng, sau đó thiết kế validation ở lớp ứng dụng.

## 17. Kiểm thử conversion và validation

Nên kiểm thử hai phần riêng để xác định chính xác lỗi nằm ở đâu.

| Dữ liệu đầu vào | Conversion | Validation ví dụ |
|---|---|---|
| "5" | Thành công thành Integer 5 | Hợp lệ nếu giới hạn là 1–10 |
| "25" | Thành công thành Integer 25 | Không hợp lệ nếu giới hạn là 1–10 |
| "abc" | Thất bại khi chuyển thành Integer | Chưa tới bước validation miền số |
| null | Phụ thuộc converter và kiểu đích | Có thể không hợp lệ nếu trường bắt buộc |
| "" | Phụ thuộc converter | Có thể không hợp lệ nếu cần giá trị |
| "-1" | Thành công thành Integer -1 | Không hợp lệ nếu số lượng phải dương |
| "2026-02-30" | Parse ngày có thể thất bại | Chưa tới bước kiểm tra thời hạn |
| Ngày hợp lệ nhưng đã quá hạn | Thành công | Không hợp lệ theo nghiệp vụ |
| BigDecimal "999999.99" | Thành công | Có thể vượt hạn mức |

Các nhóm kiểm thử nên bao gồm:

- Kiểu nguồn và kiểu đích được hỗ trợ.
- Kiểu không hỗ trợ hoặc dữ liệu sai định dạng.
- Null, chuỗi rỗng và chuỗi chỉ có khoảng trắng.
- Giá trị ở đúng biên min/max và ngay ngoài biên.
- Giá trị có thể chuyển đổi nhưng sai nghiệp vụ.
- Converter tùy chỉnh.
- Locale, timezone và định dạng ngày/số.
- Collection có generic type.
- Conversion trong getValue, property assignment và method invocation.
- Lỗi validation được trả về đúng field và message.

## 18. Ghi nhớ

Conversion thay đổi kiểu hoặc cách biểu diễn của dữ liệu. Validation kiểm tra dữ liệu có đáp ứng yêu cầu cấu trúc, miền giá trị, quan hệ giữa các trường và quy tắc nghiệp vụ hay không. Một giá trị chuyển đổi thành công vẫn có thể không hợp lệ.

SpEL sử dụng TypeConverter của EvaluationContext khi cần chuyển kết quả, property assignment hoặc đối số method sang kiểu đích. StandardTypeConverter có thể làm việc với Spring ConversionService; converter tùy chỉnh giúp chuẩn hóa các kiểu nghiệp vụ riêng. TypeDescriptor cung cấp thêm metadata khi chuyển collection, Map hoặc property.

Không dùng canConvert như phép kiểm tra giá trị hợp lệ. Hãy phân biệt lỗi chuyển đổi với lỗi validation, xác định rõ cách xử lý null và chuỗi rỗng, rồi chạy validation sau khi dữ liệu đã được hiểu theo kiểu mong muốn. Với quy tắc liên trường, quyền truy cập và trạng thái nghiệp vụ, hãy dùng Bean Validation, Spring Validator hoặc service Java phù hợp.

SpEL nên hỗ trợ các phép chuyển đổi và điều kiện biểu thức ngắn. Việc xác thực dữ liệu đầu vào, phân quyền và quyết định có thực hiện hành động hay không vẫn thuộc trách nhiệm của ứng dụng.

## Tài liệu tham khảo

- [Spring Framework Reference — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html)
- [Spring Framework Reference — EvaluationContext](https://docs.spring.io/spring-framework/reference/core/expressions/evaluation.html)
- [Spring Framework Reference — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [TypeConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/TypeConverter.html)
- [StandardTypeConverter Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/expression/spel/support/StandardTypeConverter.html)