# Giới hạn implicit conversion để tránh kết quả bất ngờ trong SpEL

Spring Expression Language (SpEL) có thể chuyển đổi kiểu tự động khi một thao tác cần giá trị ở kiểu khác với kiểu runtime của dữ liệu. Cơ chế này được gọi là implicit conversion: ứng dụng truyền một giá trị, còn SpEL dùng TypeConverter của EvaluationContext để chuyển đổi khi có converter phù hợp.

Implicit conversion giúp expression linh hoạt, nhưng cũng có thể che giấu lỗi dữ liệu. Một chuỗi có thể được chuyển thành số, một giá trị có thể được chuyển sang kiểu tham số của method hoặc kiểu property đích. Nếu việc chuyển đổi không đúng với ý nghĩa nghiệp vụ, expression vẫn có thể chạy nhưng cho kết quả sai hoặc khó giải thích.

Bài học này tập trung vào nơi SpEL thực hiện chuyển đổi ngầm, cách TypeConverter và Spring ConversionService phối hợp, những rủi ro khi cho phép quá nhiều conversion và cách giới hạn quy tắc chuyển đổi để dữ liệu có kiểu rõ ràng.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Giải thích implicit conversion trong SpEL.
- Phân biệt kiểu runtime của dữ liệu với kiểu mà expression hoặc method đích yêu cầu.
- Nhận biết vai trò của TypeConverter và ConversionService.
- Xác định các vị trí thường có chuyển đổi tự động: property assignment, method argument và kiểu kết quả.
- Hiểu vì sao overload và converter tổng quát có thể làm hành vi khó dự đoán.
- Giữ kiểu dữ liệu đầu vào ổn định và validate trước khi evaluate.
- Cấu hình converter có phạm vi hẹp cho EvaluationContext.
- Kiểm thử cả conversion thành công, conversion thất bại và trường hợp chuyển đổi hợp lệ về kiểu nhưng sai về nghiệp vụ.

Bạn nên biết cách tạo SpelExpressionParser, Expression, EvaluationContext, JavaBean property, method overload và Spring ConversionService.

## 2. Implicit conversion là gì?

Giả sử một property Java có kiểu boolean, nhưng ứng dụng cung cấp giá trị dạng String:

~~~java
public class FeatureConfig {
    private boolean enabled;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Có thể gán bằng SpEL:

~~~java
FeatureConfig config = new FeatureConfig();

ExpressionParser parser = new SpelExpressionParser();
Expression expression = parser.parseExpression("enabled");

expression.setValue(config, "true");
~~~

Nếu TypeConverter hiện tại hỗ trợ chuyển String sang Boolean, giá trị chuỗi được chuyển thành boolean trước khi gọi setter. Sau thao tác, config.isEnabled() trả về true.

Người gọi không trực tiếp gọi Boolean.parseBoolean; việc chuyển đổi được thực hiện thông qua cơ chế conversion của SpEL.

Implicit conversion có thể xuất hiện khi một thao tác có kiểu đích rõ ràng. Ví dụ:

- Property assignment cần giá trị đúng kiểu property.
- Method invocation cần đối số tương thích với kiểu tham số.
- getValue(context, TargetType.class) yêu cầu kết quả theo kiểu đích.
- Một số thao tác data binding hoặc collection cần chuyển đổi phần tử theo TypeDescriptor.

Không nên suy luận rằng mọi toán tử SpEL đều tự chuyển mọi kiểu sang mọi kiểu khác. Quy tắc cụ thể phụ thuộc toán tử, kiểu nguồn, kiểu đích và converter hiện có.

## 3. TypeConverter và ConversionService

EvaluationContext cung cấp TypeConverter để SpEL hỏi xem có thể chuyển một giá trị từ kiểu nguồn sang kiểu đích hay không và thực hiện chuyển đổi.

Trong Spring, StandardTypeConverter là adapter kết nối SpEL với Spring ConversionService. StandardEvaluationContext mặc định có TypeConverter tiêu chuẩn; ứng dụng có thể thay nó nếu cần chính sách chuyển đổi khác.

Các thành phần có vai trò riêng:

| Thành phần | Trách nhiệm |
|---|---|
| TypeConverter | API mà SpEL sử dụng để kiểm tra và thực hiện chuyển đổi |
| ConversionService | Cơ chế Spring quản lý converter và quy tắc chuyển đổi |
| Converter | Chuyển một kiểu nguồn cụ thể sang một kiểu đích |
| ConverterFactory | Tạo converter cho một họ kiểu đích |
| GenericConverter | Hỗ trợ nhiều cặp kiểu và có thể dùng TypeDescriptor |
| TypeDescriptor | Mang thông tin kiểu, bao gồm metadata generic của property hoặc collection |

SpEL làm việc với TypeConverter trong EvaluationContext. Ứng dụng có thể dùng ConversionService của Spring để đăng ký converter chuẩn hoặc converter riêng theo domain.

## 4. Chuyển đổi khi gán property

Một vị trí thường gặp là Expression.setValue(...). Kiểu property quyết định kiểu đích mà SpEL cần ghi.

~~~java
public class Account {
    private int retryCount;

    public int getRetryCount() {
        return retryCount;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

Ví dụ:

~~~java
Account account = new Account();

Expression expression =
    parser.parseExpression("retryCount");

expression.setValue(account, "5");
~~~

Nếu converter mặc định hỗ trợ String sang Integer, setter nhận giá trị số 5. Nếu chuỗi không thể chuyển thành số, thao tác ghi thất bại trong quá trình conversion.

Property có thể ghi không có nghĩa mọi giá trị đều gán được. Cần phân biệt:

1. PropertyAccessor có quyền ghi property hay không.
2. TypeConverter có thể chuyển giá trị sang kiểu property hay không.
3. Setter hoặc tầng nghiệp vụ có chấp nhận giá trị sau chuyển đổi hay không.

Ví dụ chuỗi "-1" có thể chuyển thành int thành công, nhưng setter hoặc validation nghiệp vụ vẫn có thể từ chối retryCount âm.

## 5. Chuyển đổi đối số khi gọi method

SpEL có thể dùng TypeConverter để chuyển đối số sang kiểu tham số method khi resolver tìm được lời gọi phù hợp.

Ví dụ method nhận BigDecimal:

~~~java
public class PriceCalculator {
    public BigDecimal applyRate(BigDecimal rate) {
        return rate.multiply(new BigDecimal("100"));
    }
}
~~~

Nếu biến rate được cung cấp dưới dạng String và context có converter tương ứng, lời gọi có thể được chuyển đổi:

~~~java
context.setVariable("rate", "0.15");

Expression expression =
    parser.parseExpression("#calculator.applyRate(#rate)");
~~~

Để ví dụ hoạt động, calculator phải được cung cấp trong context và TypeConverter phải hỗ trợ String sang BigDecimal. Trong ứng dụng thực tế, tốt hơn nên truyền BigDecimal từ Java nếu dữ liệu đã có kiểu đó.

### 5.1. Overload làm tăng độ phức tạp

Giả sử class có nhiều method cùng tên:

~~~java
public String format(Integer value) { ... }

public String format(BigDecimal value) { ... }

public String format(String value) { ... }
~~~

Khi expression gọi format với một giá trị có kiểu khác, method resolver và conversion có thể cùng tham gia chọn lời gọi phù hợp. Kết quả có thể khác với điều người đọc suy luận chỉ từ nội dung chuỗi.

Để giảm bất ngờ:

- Tránh overload quá nhiều khi method được gọi từ SpEL.
- Dùng tên method riêng cho từng mục đích nếu các kiểu có ý nghĩa khác nhau.
- Truyền biến với kiểu runtime đúng thay vì dựa vào conversion.
- Kiểm thử từng chữ ký và kiểu đầu vào được hỗ trợ.
- Không dùng converter quá rộng để làm mọi lời gọi đều có vẻ hợp lệ.

## 6. Chuyển đổi kiểu kết quả

Expression có thể được yêu cầu trả về một kiểu cụ thể:

~~~java
Expression expression =
    parser.parseExpression("#quantity");

context.setVariable("quantity", 12);

String result =
    expression.getValue(context, String.class);
~~~

SpEL có thể dùng TypeConverter để chuyển kết quả sang String nếu conversion service hỗ trợ.

Điều này khác với việc expression bên trong tự tạo ra một chuỗi. Expression trả về giá trị theo kiểu runtime của nó; overload getValue(context, TargetType.class) yêu cầu chuyển kết quả sang kiểu đích.

Hãy chọn kiểu kết quả tường minh để code Java thể hiện hợp đồng mong muốn. Nếu conversion không được hỗ trợ hoặc thất bại, xử lý lỗi tại ranh giới ứng dụng thay vì giả định kết quả luôn đúng kiểu.

## 7. Conversion trong collection và property generic

TypeDescriptor giúp Spring giữ thông tin kiểu của property, bao gồm generic element type trong một số tình huống data binding.

Ví dụ property:

~~~java
public class Preferences {
    private List<Boolean> flags;

    public List<Boolean> getFlags() {
        return flags;
    }

    public void setFlags(List<Boolean> flags) {
        this.flags = flags;
    }
}
~~~

Khi ghi một phần tử List, kiểu đích có thể được xác định là Boolean:

~~~text
flags[0]
~~~

Nếu ứng dụng gán chuỗi "true" vào phần tử đó và conversion service hỗ trợ, giá trị có thể được chuyển thành Boolean.

Tuy nhiên, không nên dựa vào generic metadata khi model khai báo collection raw hoặc kiểu phần tử quá tổng quát. Nếu property chỉ khai báo List hoặc List<Object>, thông tin kiểu đích có thể không đủ để áp dụng conversion mong muốn.

Với collection nhận dữ liệu ngoài hệ thống, hãy validate từng phần tử và kích thước collection. Conversion thành công không đồng nghĩa nội dung collection đã hợp lệ theo nghiệp vụ.

## 8. Rủi ro khi implicit conversion quá rộng

### 8.1. Chuỗi có thể che giấu dữ liệu sai

Một trường dữ liệu có thể được nhận dưới dạng String trong khi nghiệp vụ yêu cầu số, ngày hoặc enum. Nếu converter chuyển được, lỗi hợp đồng dữ liệu có thể không được phát hiện ở nơi nhận.

Ví dụ chuỗi "0012" có thể được chuyển thành số 12. Nếu các số 0 ở đầu có ý nghĩa như mã định danh, việc chuyển sang Number làm mất thông tin.

Hãy phân biệt dữ liệu định lượng với dữ liệu định danh. Mã tài khoản, mã bưu chính hoặc mã sản phẩm thường nên giữ dạng String dù chỉ chứa chữ số.

### 8.2. Conversion hợp lệ về kiểu nhưng sai về ý nghĩa

Chuỗi "false" chuyển thành Boolean false là hợp lệ về kiểu. Nhưng nếu hệ thống quy ước chuỗi rỗng hoặc "unknown" mang nghĩa chưa xác định, việc tự động đổi thành false có thể làm thay đổi logic.

Tương tự, chuyển số thập phân sang số nguyên có thể làm mất phần thập phân hoặc không phù hợp với cách làm tròn nghiệp vụ. Đừng dùng conversion mặc định để quyết định chính sách làm tròn, tiền tệ hoặc đơn vị đo.

### 8.3. Locale, timezone và định dạng

Chuyển đổi ngày, giờ và số thập phân có thể phụ thuộc formatter, locale hoặc timezone được cấu hình. Một chuỗi ngày có thể được hiểu khác nhau nếu định dạng ngày/tháng không thống nhất.

Đối với dữ liệu ngày giờ:

- Chọn định dạng đầu vào rõ ràng, tốt nhất có quy ước ISO phù hợp.
- Xác định timezone tại ranh giới ứng dụng.
- Không dựa vào locale mặc định của máy chủ.
- Kiểm thử các giá trị mơ hồ như ngày có thể đọc theo dd/MM hoặc MM/dd.

### 8.4. Converter tùy chỉnh có thể thực hiện hành vi ngoài dự kiến

Converter là code Java. Nếu converter gọi database, mạng hoặc thay đổi trạng thái, một thao tác evaluate tưởng như đơn giản có thể phát sinh side effect.

Ưu tiên converter thuần: nhận một giá trị, kiểm tra và trả về giá trị mới. Không dùng converter để thực hiện nghiệp vụ, I/O hoặc truy vấn tài nguyên bên ngoài.

### 8.5. Overload và conversion cùng ảnh hưởng kết quả

Một giá trị String có thể chuyển thành nhiều kiểu tham số khác nhau. Nếu method có nhiều overload, lựa chọn cuối cùng có thể khó dự đoán khi API thay đổi.

Giữ method được expose cho SpEL nhỏ và có chữ ký rõ. Nếu cần logic phức tạp, chuyển phần xử lý vào một facade có method duy nhất với kiểu tham số cụ thể.

## 9. Giới hạn conversion bằng cách truyền dữ liệu đúng kiểu

Cách đơn giản và dễ kiểm soát nhất là chuyển đổi dữ liệu ở tầng Java trước khi đưa vào EvaluationContext.

Thay vì:

~~~java
context.setVariable("amount", request.getParameter("amount"));
~~~

hãy parse và validate trước:

~~~java
BigDecimal amount =
    new BigDecimal(request.getParameter("amount"));

context.setVariable("amount", amount);
~~~

Ví dụ trên chỉ minh họa với chuỗi số hợp lệ; code production cần bắt lỗi parse và áp dụng giới hạn nghiệp vụ.

Khi biến đã có kiểu BigDecimal, expression có thể thực hiện phép toán mà không cần dựa vào chuyển đổi String sang Number ở runtime.

Các nguyên tắc:

- Parse dữ liệu tại ranh giới nhận input.
- Validate kiểu, miền giá trị và đơn vị trước khi evaluate.
- Đưa DTO đã được xác thực vào context.
- Giữ kiểu biến ổn định giữa các lần evaluate.
- Dùng String cho identifier và Number cho đại lượng cần tính toán.
- Không dựa vào implicit conversion để sửa dữ liệu đầu vào không đúng hợp đồng.

## 10. Cấu hình ConversionService rõ ràng

StandardTypeConverter có thể được cấu hình với ConversionService cụ thể:

~~~java
ConversionService conversionService =
    new DefaultConversionService();

StandardEvaluationContext context =
    new StandardEvaluationContext();

context.setTypeConverter(
    new StandardTypeConverter(conversionService)
);
~~~

Cách này giúp context dùng chính sách conversion mà ứng dụng đã chọn. Nếu cần converter riêng, đăng ký vào ConversionService trước khi dùng nó với StandardTypeConverter.

Ví dụ converter domain:

~~~java
public final class CurrencyCode {
    private final String value;

    public CurrencyCode(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

Đăng ký chuyển String sang CurrencyCode:

~~~java
DefaultConversionService conversionService =
    new DefaultConversionService();

conversionService.addConverter(
    String.class,
    CurrencyCode.class,
    source -> new CurrencyCode(source.trim().toUpperCase(Locale.ROOT))
);
~~~

Sau đó tạo TypeConverter từ conversion service đó và gắn vào EvaluationContext.

Converter trên chỉ minh họa cách chuẩn hóa một mã tiền tệ. Ứng dụng thực tế cần kiểm tra mã có nằm trong tập giá trị được hỗ trợ hay không; chuyển đổi chữ hoa/thường không thay thế validation.

## 11. Xây dựng chính sách conversion giới hạn

Nếu biểu thức chỉ được phép chuyển đổi một số cặp kiểu, có thể dùng ConversionService riêng chỉ đăng ký những converter cần thiết, hoặc bọc TypeConverter để từ chối các cặp kiểu ngoài allowlist.

Một chính sách giới hạn nên xác định:

- Kiểu nguồn nào được chấp nhận.
- Kiểu đích nào được phép.
- Có cho phép conversion collection và phần tử lồng nhau không.
- Có cho phép chuyển đổi từ String sang Number, Boolean hoặc enum không.
- Có yêu cầu format cụ thể cho ngày giờ không.
- Có giới hạn độ dài chuỗi và miền giá trị không.
- Conversion nào chỉ dùng cho binding, conversion nào được phép trong expression.

Không có một nút bật/tắt phổ quát có thể thay thế việc định nghĩa chính sách theo use case. Nếu muốn strict behavior, hãy cung cấp TypeConverter/ConversionService hẹp và truyền dữ liệu đã có kiểu chính xác.

Với SimpleEvaluationContext, builder có thể nhận ConversionService cụ thể:

~~~java
SimpleEvaluationContext context =
    SimpleEvaluationContext
        .forReadOnlyDataBinding()
        .withConversionService(conversionService)
        .build();
~~~

Chọn context và conversion service theo đúng nhu cầu. Read-only giới hạn khả năng ghi property; nó không tự đảm bảo mọi conversion đều phù hợp về nghiệp vụ.

## 12. Xử lý lỗi conversion

Conversion có thể thất bại vì:

- Không có converter cho cặp kiểu nguồn/đích.
- Chuỗi không đúng định dạng.
- Giá trị vượt phạm vi kiểu đích.
- Collection có phần tử không thể chuyển đổi.
- Converter tùy chỉnh từ chối dữ liệu.
- Setter hoặc method tiếp tục validation và ném exception.

Hãy xử lý lỗi ở ranh giới ứng dụng:

1. Xác định dữ liệu đầu vào và kiểu đích.
2. Kiểm tra conversion service có hỗ trợ cặp kiểu đó không nếu cần.
3. Bắt lỗi chuyển đổi và chuyển thành lỗi validation phù hợp.
4. Không tiếp tục dùng giá trị mặc định âm thầm nếu nghiệp vụ cần báo lỗi.
5. Không trả stack trace hoặc thông tin nội bộ cho client.
6. Ghi log có kiểm soát, tránh ghi dữ liệu nhạy cảm.

Không nên bắt mọi exception rồi trả null hoặc 0. Cách đó che giấu lỗi dữ liệu và làm hệ thống khó chẩn đoán.

## 13. Kiểm thử implicit conversion

Một bộ test nên bao gồm:

| Trường hợp | Đầu vào | Điều cần xác nhận |
|---|---|---|
| String sang Boolean | "true" | Chuyển đúng nếu converter được cấu hình |
| String sang số nguyên | "12" | Chuyển đúng sang kiểu đích |
| Chuỗi số không hợp lệ | "twelve" | Conversion thất bại rõ ràng |
| String sang BigDecimal | "12.50" | Giữ đúng giá trị thập phân theo converter |
| Giá trị gán property | String cho property boolean/int | Setter nhận đúng kiểu sau conversion |
| Method argument | String cho tham số BigDecimal | Chỉ chuyển khi resolver và converter hỗ trợ |
| Kết quả expression | Number yêu cầu String | Kết quả được chuyển theo TypeConverter |
| Collection generic | String cho phần tử Boolean | Xác nhận generic TypeDescriptor được dùng đúng |
| Identifier có số 0 đầu | "0012" | Không vô tình chuyển thành số nếu cần giữ định danh |
| Ngày tháng mơ hồ | Chuỗi ngày theo nhiều format | Format/locale được xác định rõ |
| Converter tùy chỉnh từ chối | Mã không hợp lệ | Lỗi validation được truyền đúng |
| Overload | Nhiều method cùng tên | Method được chọn đúng hoặc bị từ chối theo chính sách |

Ngoài giá trị trả về, hãy kiểm tra kiểu runtime và trạng thái object sau khi gán. Với converter có chuẩn hóa dữ liệu, kiểm tra cả trường hợp đầu vào hợp lệ và không hợp lệ.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Property assignment thất bại | Không có converter sang kiểu property | Cung cấp dữ liệu đúng kiểu hoặc converter cần thiết |
| Method không được gọi | Đối số không tương thích hoặc overload không rõ | Kiểm tra chữ ký và kiểu biến |
| Giá trị đổi ngoài dự kiến | Conversion hợp lệ về kiểu nhưng sai ý nghĩa | Validate theo domain trước khi đưa vào context |
| Mất số 0 đầu | Identifier bị chuyển thành Number | Giữ identifier dưới dạng String |
| Sai ngày hoặc số thập phân | Locale/format không thống nhất | Cấu hình format và timezone rõ ràng |
| Conversion hoạt động ở context này nhưng không ở context khác | Hai context dùng TypeConverter khác nhau | Kiểm tra cấu hình EvaluationContext |
| Converter tạo side effect | Converter chứa logic I/O hoặc nghiệp vụ | Giữ converter thuần và chuyển nghiệp vụ về service |
| Lỗi chỉ xuất hiện với collection | Generic metadata thiếu hoặc phần tử không hợp lệ | Kiểm tra TypeDescriptor và kiểu collection |

## 15. Bài tập thực hành

1. Tạo property boolean và gán giá trị String bằng Expression.setValue; quan sát conversion.
2. Tạo property int và thử chuỗi số hợp lệ cùng chuỗi không hợp lệ.
3. Gọi method nhận BigDecimal với biến String, sau đó đổi biến thành BigDecimal.
4. Tạo hai overload cùng tên và kiểm tra hành vi khi đầu vào có kiểu String.
5. Yêu cầu getValue(context, String.class) cho một expression trả Number.
6. Tạo ConversionService riêng với một converter domain.
7. Thử mã định danh có số 0 đầu và xác nhận nó không bị chuyển thành số.
8. Tạo context dùng converter hẹp và kiểm tra cặp kiểu ngoài allowlist bị từ chối.
9. Viết test cho ngày tháng, locale và giá trị vượt phạm vi.
10. Kiểm tra converter không gọi I/O hoặc thay đổi trạng thái bên ngoài.

## 16. Checklist trước khi cho phép implicit conversion

- [ ] Đã xác định kiểu runtime của từng biến chưa?
- [ ] Đã xác định kiểu đích của property, method hoặc kết quả chưa?
- [ ] Có thể truyền dữ liệu đúng kiểu ngay từ Java không?
- [ ] TypeConverter của context có được cấu hình rõ ràng không?
- [ ] ConversionService có chứa converter rộng hơn nhu cầu không?
- [ ] Có overload khiến conversion chọn method khó dự đoán không?
- [ ] Identifier có bị chuyển nhầm thành Number không?
- [ ] Locale, timezone, format và rounding có được quy định không?
- [ ] Converter tùy chỉnh có thuần và không tạo side effect không?
- [ ] Đã kiểm thử conversion thành công, thất bại và sai ý nghĩa nghiệp vụ chưa?
- [ ] Có xử lý lỗi conversion tại ranh giới ứng dụng không?
- [ ] Context có chỉ cho phép các conversion cần thiết không?

## 17. Kết luận

Implicit conversion giúp SpEL chuyển giá trị sang kiểu mà property, method hoặc bên nhận kết quả yêu cầu khi TypeConverter có quy tắc phù hợp. StandardTypeConverter kết nối SpEL với Spring ConversionService, nơi ứng dụng có thể quản lý converter chuẩn và converter riêng. Conversion quá rộng có thể che giấu dữ liệu sai, làm mất thông tin định danh, gây mơ hồ overload hoặc phụ thuộc locale. Hãy ưu tiên truyền dữ liệu đã có kiểu, validate ở ranh giới ứng dụng, cấu hình ConversionService theo allowlist khi cần và kiểm thử cả kiểu kết quả lẫn ý nghĩa nghiệp vụ.