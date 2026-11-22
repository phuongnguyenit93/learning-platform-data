# Chuyển đổi khi gán property trong Spring Expression Language

Spring Expression Language (SpEL) có thể ghi giá trị vào property của một object Java thông qua \`Expression.setValue(...)\` hoặc toán tử gán \`=\`. Khi kiểu của giá trị đầu vào khác kiểu mà property yêu cầu, SpEL có thể chuyển đổi giá trị trước khi ghi.

Ví dụ, property \`retryCount\` có kiểu \`Integer\`, nhưng dữ liệu đầu vào lại là chuỗi \`"5"\`. Nếu EvaluationContext có TypeConverter hỗ trợ chuyển String thành Integer, SpEL có thể chuyển đổi rồi gọi setter \`setRetryCount(Integer)\`.

Quá trình này liên quan đến ba thành phần:

- **PropertyAccessor:** xác định property đích và cách ghi giá trị.
- **TypeDescriptor:** mô tả kiểu đích, bao gồm thông tin kiểu generic trong những trường hợp cần thiết.
- **TypeConverter:** kiểm tra và thực hiện chuyển đổi từ kiểu giá trị đầu vào sang kiểu mà property yêu cầu.

Hiểu mối quan hệ này giúp tránh lỗi khi binding dữ liệu, cập nhật property lồng nhau hoặc dùng dữ liệu dạng chuỗi trong expression.

## 1. Gán property có kiểu dữ liệu khác với giá trị đầu vào

Giả sử một JavaBean có property số nguyên:

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

Tạo object và EvaluationContext:

~~~java
RetrySettings settings = new RetrySettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();
Expression property =
    parser.parseExpression("retryCount");
~~~

Có thể gán một chuỗi cho property Integer:

~~~java
property.setValue(context, "5");

System.out.println(settings.getRetryCount());
~~~

Kết quả:

~~~text
5
~~~

Giá trị được truyền vào là String, còn setter yêu cầu Integer. Nếu TypeConverter hiện tại hỗ trợ chuyển đổi String sang Integer, SpEL chuyển giá trị trước khi ghi property.

Vì vậy, câu lệnh setValue không có nghĩa là SpEL luôn gán trực tiếp object đầu vào cho setter. Quá trình ghi có thể bao gồm một bước chuyển đổi kiểu.

## 2. TypeConverter tham gia vào lúc nào?

Khi ghi một property, SpEL cần biết kiểu mà property đích yêu cầu. Với JavaBean thông thường, PropertyAccessor reflection có thể tìm setter tương ứng, xác định kiểu tham số của setter rồi yêu cầu TypeConverter chuyển giá trị đầu vào nếu cần.

Có thể mô tả luồng xử lý:

~~~text
Expression.setValue(context, "5")
             |
             v
PropertyAccessor tìm property đích
             |
             v
Xác định setter và kiểu đích Integer
             |
             v
TypeConverter kiểm tra chuyển String -> Integer
             |
        +----+----+
        |         |
     Chuyển được  Không chuyển được
        |         |
        v         v
   Giá trị Integer  Conversion error
        |
        v
Gọi setRetryCount(Integer)
        |
        v
Property được cập nhật
~~~

Nếu giá trị đầu vào đã tương thích với kiểu đích, có thể không cần chuyển đổi thực tế. Nếu hai kiểu khác nhau, TypeConverter quyết định liệu có chuyển đổi được hay không.

PropertyAccessor chịu trách nhiệm ghi vào object. TypeConverter chịu trách nhiệm chuyển đổi giá trị theo kiểu mà accessor yêu cầu.

## 3. Gán bằng Expression.setValue

\`Expression.setValue(...)\` là API tường minh để ghi vào một expression đích có thể ghi.

~~~java
RetrySettings settings = new RetrySettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();

Expression retryCount =
    parser.parseExpression("retryCount");

retryCount.setValue(context, "8");
~~~

SpEL thực hiện các bước:

1. Dùng context để xác định root object.
2. Giải quyết property \`retryCount\`.
3. Xác định kiểu đích từ property hoặc setter.
4. Chuyển String \`"8"\` thành Integer nếu TypeConverter hỗ trợ.
5. Ghi giá trị vào property.

Có thể kiểm tra property có hỗ trợ ghi trước khi gọi setValue:

~~~java
if (retryCount.isWritable(context)) {
    retryCount.setValue(context, "8");
}
~~~

\`isWritable\` giúp kiểm tra khả năng ghi trong context hiện tại. Nó không bảo đảm mọi giá trị đầu vào đều chuyển đổi được hoặc setter chắc chắn chạy thành công. Việc chuyển đổi và ghi vẫn có thể phát sinh lỗi lúc runtime.

## 4. Chuyển đổi khi dùng toán tử gán =

SpEL cũng hỗ trợ toán tử gán trong chuỗi biểu thức:

~~~spel
retryCount = '8'
~~~

Nếu expression được đánh giá với root object có property \`retryCount\` có thể ghi, SpEL thực hiện phép gán. Quá trình ghi cũng sử dụng cơ chế chuyển đổi kiểu của EvaluationContext khi cần.

Ví dụ:

~~~java
RetrySettings settings = new RetrySettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();

Expression assignment =
    parser.parseExpression("retryCount = '8'");

assignment.getValue(context);

System.out.println(settings.getRetryCount());
~~~

Kết quả:

~~~text
8
~~~

Cần phân biệt:

- \`=\` là phép gán, có thể thay đổi object đích.
- \`==\` là phép so sánh, trả về Boolean và không tự ghi property.

Cả \`setValue\` và toán tử gán đều có thể dẫn đến việc chuyển đổi giá trị trước khi property được cập nhật.

## 5. TypeDescriptor giúp xác định kiểu đích

TypeConverter cần biết kiểu đích để chọn phép chuyển đổi phù hợp. Trong Spring, \`TypeDescriptor\` mô tả kiểu dữ liệu phong phú hơn một đối tượng Class đơn thuần.

Ngoài kiểu lớp, TypeDescriptor có thể chứa thông tin về:

- Kiểu phần tử của collection.
- Kiểu key và value của map.
- Kiểu thành phần của array.
- Annotation gắn với property hoặc field.
- Metadata cần thiết cho một số converter.

Ví dụ, hai property sau có cùng kiểu lớp List nhưng kiểu phần tử khác nhau:

~~~java
private List<Integer> retryCodes;
private List<String> labels;
~~~

TypeDescriptor có thể giữ thông tin generic để hệ thống chuyển đổi biết phần tử đích cần kiểu nào.

Điều này quan trọng khi dữ liệu đầu vào là collection hoặc map. Chuyển đổi không chỉ là đổi kiểu của container; trong những trường hợp được hỗ trợ, Spring còn có thể chuyển đổi từng phần tử theo metadata kiểu đích.

## 6. Chuyển đổi String sang các kiểu property phổ biến

TypeConverter mặc định trong môi trường SpEL thông thường hỗ trợ nhiều phép chuyển đổi tiêu chuẩn thông qua Spring ConversionService.

Ví dụ, tùy kiểu đích và định dạng đầu vào, các chuyển đổi phổ biến có thể gồm:

| Kiểu property đích | Giá trị đầu vào | Ví dụ kết quả |
|---|---|---|
| Integer | String \`"12"\` | Integer 12 |
| Long | String \`"9000"\` | Long 9000 |
| Boolean | String \`"true"\` | Boolean true |
| BigDecimal | String \`"1250.75"\` | BigDecimal 1250.75 |
| Enum | String \`"PAID"\` | Enum constant PAID |
| String | Number 42 | String \`"42"\` |

Khả năng chuyển đổi cụ thể phụ thuộc ConversionService, converter được đăng ký và định dạng dữ liệu. Không nên giả định mọi chuỗi đều chuyển được sang mọi kiểu.

Ví dụ, chuỗi \`"five"\` không thể chuyển thành Integer theo converter số thông thường. Trong trường hợp đó, thao tác gán sẽ thất bại trước khi property nhận giá trị mới.

## 7. Ví dụ chuyển đổi String sang Enum khi gán property

Giả sử ứng dụng có enum:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}
~~~

JavaBean:

~~~java
public class OrderSettings {
    private OrderStatus status;

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
~~~

Có thể gán tên enum dưới dạng String:

~~~java
OrderSettings settings = new OrderSettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();

Expression status =
    parser.parseExpression("status");

status.setValue(context, "PAID");
~~~

Nếu ConversionService đang dùng hỗ trợ chuyển String sang enum, property nhận giá trị \`OrderStatus.PAID\`.

Nếu đầu vào là \`"UNKNOWN"\`, không có enum constant tương ứng và quá trình chuyển đổi có thể thất bại. Property không nên được xem là đã cập nhật thành công chỉ vì lời gọi setValue đã bắt đầu.

## 8. Dùng ConversionService tùy chỉnh

Ứng dụng có thể đăng ký converter riêng khi kiểu dữ liệu domain không được hỗ trợ bởi các converter mặc định.

Ví dụ, giả sử có kiểu CurrencyCode:

~~~java
public record CurrencyCode(String value) {
}
~~~

Ứng dụng muốn chuyển String thành CurrencyCode. Có thể đăng ký converter trong ConversionService:

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(
    String.class,
    CurrencyCode.class,
    CurrencyCode::new
);
~~~

Tạo TypeConverter dùng ConversionService đó:

~~~java
StandardTypeConverter typeConverter =
    new StandardTypeConverter(conversionService);

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

context.setTypeConverter(typeConverter);
~~~

Khi expression gán một chuỗi cho property kiểu CurrencyCode, TypeConverter sử dụng converter đã đăng ký để tạo object đích.

Ví dụ JavaBean:

~~~java
public class PaymentSettings {
    private CurrencyCode currency;

    public CurrencyCode getCurrency() {
        return currency;
    }

    public void setCurrency(CurrencyCode currency) {
        this.currency = currency;
    }
}
~~~

Gán giá trị:

~~~java
Expression currency =
    parser.parseExpression("currency");

currency.setValue(context, "VND");
~~~

Nếu context được cấu hình với TypeConverter ở trên và root object là PaymentSettings, setter nhận một CurrencyCode có giá trị VND.

Converter tùy chỉnh nên xác định rõ định dạng đầu vào, cách chuẩn hóa và hành vi khi dữ liệu không hợp lệ. Không nên âm thầm biến dữ liệu sai thành một giá trị mặc định nếu điều đó có thể che giấu lỗi nghiệp vụ.

## 9. Cấu hình TypeConverter trực tiếp trên EvaluationContext

\`EvaluationContext\` cung cấp TypeConverter được SpEL dùng trong quá trình đánh giá. Với StandardEvaluationContext, có thể thay TypeConverter bằng phương thức \`setTypeConverter\`.

Ví dụ:

~~~java
StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ConversionService conversionService =
    new DefaultConversionService();

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

Sau khi cấu hình, những thao tác cần chuyển đổi trong context có thể sử dụng ConversionService đã chọn, bao gồm property assignment.

Cần lưu ý rằng việc thay TypeConverter có thể ảnh hưởng đến nhiều thao tác khác trong cùng context, không chỉ một property cụ thể. Các chuyển đổi khi gọi method hoặc xử lý giá trị có kiểu đích cũng có thể dùng cùng cơ chế.

Nếu chỉ cần thêm một converter, hãy bổ sung converter vào ConversionService hiện có thay vì thay thế toàn bộ cấu hình mà ứng dụng đang dựa vào.

## 10. Chuyển đổi khi gán property lồng nhau

Property đích có thể nằm trong một object lồng nhau:

~~~spel
customer.age = '35'
~~~

Giả sử root object có property customer và Customer có setter \`setAge(Integer)\`. SpEL đi theo đường dẫn:

1. Đọc property customer trên root object.
2. Nhận object Customer.
3. Giải quyết property age trên Customer.
4. Xác định kiểu đích Integer.
5. Chuyển String \`"35"\` thành Integer nếu được hỗ trợ.
6. Ghi giá trị bằng cơ chế setter tương ứng.

Nếu customer là null, SpEL không thể tiếp tục truy cập property age theo cách thông thường. Chuyển đổi kiểu không tạo ra object trung gian bị thiếu. Ứng dụng phải bảo đảm object trung gian tồn tại hoặc cấu hình cơ chế tự khởi tạo phù hợp nếu có chủ đích sử dụng.

Nếu property lồng nhau tồn tại nhưng không thể ghi, thao tác vẫn thất bại dù converter có thể chuyển đổi giá trị.

## 11. Chuyển đổi khi gán phần tử collection hoặc map

Indexer có thể nhắm đến một phần tử collection hoặc map:

~~~spel
retryCodes[0] = '5'
thresholds['warning'] = '80.5'
~~~

Kiểu đích có thể được suy ra từ cấu trúc dữ liệu và metadata kiểu có sẵn. Với property collection có khai báo generic rõ ràng, TypeDescriptor có thể cung cấp thông tin kiểu phần tử cho cơ chế chuyển đổi.

Ví dụ:

~~~java
public class RuleSettings {
    private List<Integer> retryCodes;
    private Map<String, BigDecimal> thresholds;

    public List<Integer> getRetryCodes() {
        return retryCodes;
    }

    public void setRetryCodes(List<Integer> retryCodes) {
        this.retryCodes = retryCodes;
    }

    public Map<String, BigDecimal> getThresholds() {
        return thresholds;
    }

    public void setThresholds(
            Map<String, BigDecimal> thresholds) {
        this.thresholds = thresholds;
    }
}
~~~

Nếu accessor và TypeConverter có đủ thông tin kiểu, giá trị chuỗi có thể được chuyển sang kiểu phần tử tương ứng trước khi ghi.

Tuy nhiên, khả năng ghi còn phụ thuộc collection hoặc map thực tế có cho phép cập nhật hay không. Một List bất biến, Map không hỗ trợ sửa đổi hoặc index không hợp lệ có thể khiến thao tác thất bại. Chuyển đổi kiểu thành công không đồng nghĩa vị trí đích chắc chắn ghi được.

## 12. Null và kiểu đích khi gán

Null là một giá trị cần được xử lý theo kiểu property đích.

- Property tham chiếu như String, Integer hoặc BigDecimal có thể nhận null nếu setter và logic ứng dụng cho phép.
- Property primitive như int hoặc boolean không thể lưu null.
- Setter có thể từ chối null bằng validation hoặc ném exception.
- Converter tùy chỉnh có thể định nghĩa cách xử lý null theo hợp đồng riêng.

Ví dụ, nếu setter yêu cầu int:

~~~java
public void setRetryCount(int retryCount) {
    this.retryCount = retryCount;
}
~~~

việc gán null không thể tạo một giá trị int hợp lệ. SpEL hoặc cơ chế chuyển đổi có thể phát sinh lỗi thay vì ghi null vào property.

Nếu domain cho phép trạng thái chưa có giá trị, kiểu wrapper như Integer hoặc Boolean có thể phù hợp hơn kiểu primitive.

## 13. Property không writable thì chuyển đổi cũng không giúp được

TypeConverter chỉ giải quyết sự khác biệt kiểu dữ liệu. Nó không tạo quyền ghi cho một property vốn không thể ghi.

Ví dụ:

~~~java
public class ReadOnlySettings {
    public Integer getRetryCount() {
        return 3;
    }
}
~~~

Property retryCount có thể đọc được nhưng không có setter tương ứng. Nếu accessor hiện tại không có cơ chế ghi khác, setValue sẽ thất bại.

Có thể kiểm tra trước:

~~~java
Expression property =
    parser.parseExpression("retryCount");

if (property.isWritable(context)) {
    property.setValue(context, "5");
}
~~~

Nếu isWritable trả về false, hãy xem lại kiểu object, setter, PropertyAccessor và quyền ghi của EvaluationContext. Đăng ký thêm converter không giải quyết được lỗi property chỉ đọc.

## 14. Chuyển đổi thành công nhưng setter vẫn có thể thất bại

Chuyển đổi kiểu và ghi property là hai bước riêng.

Giả sử converter chuyển String thành Integer thành công, nhưng setter có validation:

~~~java
public void setRetryCount(Integer retryCount) {
    if (retryCount != null && retryCount < 0) {
        throw new IllegalArgumentException(
            "retryCount must be non-negative"
        );
    }
    this.retryCount = retryCount;
}
~~~

Gán \`"5"\` có thể thành công vì chuyển được thành Integer 5 và setter chấp nhận giá trị.

Gán \`"-1"\` cũng có thể chuyển thành Integer thành công, nhưng setter từ chối giá trị âm. Khi đó lỗi phát sinh ở bước ghi hoặc logic setter, không phải ở converter.

Khi điều tra lỗi, cần xác định exception đến từ:

- Không tìm thấy property hoặc setter.
- Property không hỗ trợ ghi.
- TypeConverter không thể chuyển đổi.
- Setter hoặc accessor phát sinh exception khi ghi.

## 15. Cách điều tra lỗi chuyển đổi khi gán property

Khi setValue hoặc assignment expression thất bại, có thể kiểm tra theo trình tự:

1. **Xác định property đích:** tên property và đường dẫn lồng nhau có đúng không?
2. **Kiểm tra khả năng ghi:** property có setter hoặc accessor hỗ trợ write không?
3. **Xác định kiểu đích:** kiểu tham số setter hoặc TypeDescriptor của property là gì?
4. **Kiểm tra kiểu đầu vào:** giá trị truyền vào có kiểu gì và có định dạng hợp lệ không?
5. **Kiểm tra TypeConverter:** context đang dùng converter nào? Converter có hỗ trợ chuyển đổi này không?
6. **Kiểm tra generic metadata:** nếu đích là collection hoặc map, kiểu phần tử/key/value có được mô tả không?
7. **Kiểm tra setter:** sau khi chuyển đổi, setter có validation hoặc logic nào từ chối giá trị không?
8. **Đọc exception gốc:** lỗi là conversion failure, property access failure hay exception từ setter?

Không nên chỉ thay đổi kiểu dữ liệu đầu vào một cách phỏng đoán. Hãy xác định kiểu đích và converter đang hoạt động để biết chính xác bước nào thất bại.

## 16. Ví dụ hoàn chỉnh: gán String vào property số và enum

Ví dụ sau có hai property với kiểu đích khác nhau:

~~~java
public enum OrderStatus {
    PENDING,
    PAID,
    CANCELLED
}

public class OrderSettings {
    private Integer retryCount;
    private OrderStatus status;

    public Integer getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(Integer retryCount) {
        this.retryCount = retryCount;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public void setStatus(OrderStatus status) {
        this.status = status;
    }
}
~~~

Gán các giá trị dạng chuỗi:

~~~java
OrderSettings settings = new OrderSettings();

StandardEvaluationContext context =
    new StandardEvaluationContext(settings);

ExpressionParser parser = new SpelExpressionParser();

Expression retryCount =
    parser.parseExpression("retryCount");

Expression status =
    parser.parseExpression("status");

retryCount.setValue(context, "5");
status.setValue(context, "PAID");

System.out.println(settings.getRetryCount());
System.out.println(settings.getStatus());
~~~

Với TypeConverter mặc định hỗ trợ các chuyển đổi tương ứng, kết quả là:

~~~text
5
PAID
~~~

Trong ví dụ này:

- PropertyAccessor xác định hai property đích và cách ghi.
- TypeDescriptor hoặc metadata property cho biết kiểu đích lần lượt là Integer và OrderStatus.
- TypeConverter thực hiện các chuyển đổi cần thiết.
- Setter nhận giá trị đã chuyển đổi và cập nhật object.

Nếu đầu vào không hợp lệ, chẳng hạn retryCount là \`"five"\` hoặc status là \`"UNKNOWN"\`, quá trình chuyển đổi có thể thất bại và property không được cập nhật theo cách mong muốn.

## 17. Những nhầm lẫn thường gặp

**Nhầm lẫn 1: setValue luôn gán nguyên object đầu vào cho setter.**  
SpEL có thể chuyển đổi giá trị qua TypeConverter trước khi ghi nếu kiểu đầu vào khác kiểu đích.

**Nhầm lẫn 2: TypeConverter quyết định property có writable hay không.**  
PropertyAccessor và object đích quyết định khả năng ghi. TypeConverter chỉ chuyển đổi giá trị.

**Nhầm lẫn 3: ConversionService và TypeConverter là cùng một interface.**  
ConversionService là cơ chế chuyển đổi của Spring; StandardTypeConverter là adapter để SpEL dùng ConversionService thông qua TypeConverter.

**Nhầm lẫn 4: Chuyển đổi thành công có nghĩa setter chắc chắn thành công.**  
Setter có thể validation, từ chối giá trị hoặc ném exception.

**Nhầm lẫn 5: Collection generic không ảnh hưởng chuyển đổi.**  
TypeDescriptor có thể mang thông tin kiểu phần tử, key và value, giúp chuyển đổi dữ liệu collection/map đúng kiểu khi được hỗ trợ.

**Nhầm lẫn 6: Mọi kiểu đều có thể nhận null.**  
Property primitive không thể lưu null; setter hoặc converter cũng có thể từ chối null với property tham chiếu.

## 18. Ghi nhớ

- Khi gán property, SpEL xác định kiểu đích qua cơ chế truy cập property và metadata tương ứng.
- TypeConverter của EvaluationContext có thể chuyển giá trị đầu vào sang kiểu property yêu cầu trước khi ghi.
- TypeDescriptor mô tả kiểu đích và có thể chứa metadata generic của collection hoặc map.
- StandardTypeConverter kết nối SpEL với Spring ConversionService.
- Có thể thay TypeConverter trên StandardEvaluationContext hoặc cung cấp ConversionService tùy chỉnh.
- \`Expression.setValue(...)\` và toán tử gán \`=\` đều có thể kích hoạt chuyển đổi khi ghi property.
- Chuyển đổi kiểu không làm một property chỉ đọc trở thành writable.
- Chuyển đổi thành công không bảo đảm setter chấp nhận giá trị.
- Null, primitive, collection bất biến, index không hợp lệ và converter tùy chỉnh đều cần được xử lý theo hợp đồng dữ liệu.
- Khi debug, hãy tách riêng lỗi property access, lỗi conversion và lỗi trong setter.

Khi gán property bằng SpEL, hãy xác định kiểu đích, kiểm tra property có thể ghi, rồi xem TypeConverter của context có thể chuyển đổi dữ liệu đầu vào hay không. Sau đó kiểm tra setter và trạng thái object để xác nhận thao tác cập nhật đã hoàn tất.
