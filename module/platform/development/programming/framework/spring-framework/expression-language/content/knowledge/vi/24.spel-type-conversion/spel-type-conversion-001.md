# TypeConverter trong quá trình đánh giá SpEL

Spring Expression Language (SpEL) có thể chuyển đổi giá trị giữa các kiểu dữ liệu khi đánh giá biểu thức. Cơ chế chuyển đổi được cung cấp qua **TypeConverter** của EvaluationContext. Nhờ đó, giá trị đọc từ property, biến hoặc expression có thể được chuyển sang kiểu mà property, method, constructor hoặc bên gọi yêu cầu.

TypeConverter là một phần của quá trình đánh giá, không phải một bước parse cú pháp. Parser tạo Expression; khi Expression chạy với EvaluationContext, các thành phần của SpEL mới yêu cầu chuyển đổi nếu thao tác cần một kiểu đích cụ thể.

## 1. Vai trò của TypeConverter

EvaluationContext cung cấp TypeConverter qua phương thức `getTypeConverter()`. TypeConverter xác định một giá trị có thể chuyển sang kiểu đích hay không và thực hiện chuyển đổi đó.

Hợp đồng chính của interface gồm:

    boolean canConvert(
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );

    Object convertValue(
            Object value,
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );

TypeDescriptor mô tả kiểu dữ liệu cùng metadata liên quan. Nó có thể mang thêm thông tin như kiểu phần tử của collection, kiểu key/value của map hoặc annotation trên property. Điều này giúp việc chuyển đổi hiểu rõ hơn kiểu đích thay vì chỉ dựa vào class runtime đơn giản.

SpEL có thể dùng TypeConverter trong các tình huống như:

- Gán giá trị vào property có kiểu cụ thể.
- Chuyển đối số cho method hoặc constructor khi chữ ký yêu cầu kiểu khác.
- Chuyển kết quả expression sang kiểu được yêu cầu qua `getValue(context, TargetType.class)`.

TypeConverter chỉ chuyển đổi giá trị theo quy tắc được cấu hình. Nó không tự quyết định quyền truy cập property, quyền gọi method hay quy tắc nghiệp vụ của ứng dụng.

## 2. TypeConverter thuộc EvaluationContext

Mỗi lần đánh giá expression, SpEL sử dụng các dịch vụ được cung cấp bởi EvaluationContext. Vì vậy, hai context khác nhau có thể dùng các converter khác nhau và cho kết quả chuyển đổi khác nhau với cùng một expression.

StandardEvaluationContext mặc định cung cấp StandardTypeConverter. Converter này dựa trên Spring ConversionService để xử lý các chuyển đổi thông dụng.

Ví dụ:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    ExpressionParser parser = new SpelExpressionParser();

    Integer count = parser.parseExpression("'42'")
            .getValue(context, Integer.class);

Expression có giá trị chuỗi `'42'`. Khi yêu cầu kết quả kiểu Integer, SpEL dùng TypeConverter của context để chuyển giá trị sang Integer nếu conversion service hỗ trợ.

Có thể lấy converter hiện tại để kiểm tra hoặc cấu hình context:

    TypeConverter converter = context.getTypeConverter();

Nếu cần chính sách chuyển đổi riêng cho một use case, hãy tạo context với TypeConverter phù hợp thay vì thay đổi một converter dùng chung ngoài phạm vi cần thiết.

## 3. Chuyển đổi khi gán property

Khi expression gán một giá trị vào property, kiểu của giá trị nguồn có thể khác kiểu property đích. SpEL dùng TypeConverter của EvaluationContext để chuyển đổi nếu có converter phù hợp.

Ví dụ một object có property `quantity` kiểu Integer:

    public class OrderForm {
        private Integer quantity;

        public Integer getQuantity() {
            return quantity;
        }

        public void setQuantity(Integer quantity) {
            this.quantity = quantity;
        }
    }

Có thể gán một chuỗi số:

    OrderForm form = new OrderForm();

    StandardEvaluationContext context =
            new StandardEvaluationContext(form);

    ExpressionParser parser = new SpelExpressionParser();
    parser.parseExpression("quantity = '12'")
            .getValue(context);

Nếu converter hỗ trợ String sang Integer, property `quantity` nhận giá trị Integer 12. Việc gán còn phụ thuộc PropertyAccessor có cho phép ghi property đó hay không; TypeConverter không cấp quyền ghi.

Cũng có thể dùng API `setValue`:

    parser.parseExpression("quantity")
            .setValue(context, "25");

SpEL chuyển giá trị sang kiểu property khi cần. Nếu chuỗi không biểu diễn được một Integer hợp lệ, chuyển đổi thất bại và thao tác gán không hoàn tất như mong đợi. Hãy xử lý lỗi chuyển đổi ở tầng gọi thay vì giả định giá trị đã được ghi.

## 4. Chuyển đổi đối số khi gọi method

Method có chữ ký tham số cụ thể. Khi expression gọi method với các đối số có kiểu khác, cơ chế phân giải method và TypeConverter có thể phối hợp để tìm và gọi method phù hợp.

Ví dụ:

    public class ShippingService {
        public String estimate(Integer weight) {
            return "weight=" + weight;
        }
    }

    context.setVariable("shippingService", new ShippingService());
    context.setVariable("rawWeight", "1500");

    String result = parser.parseExpression(
            "#shippingService.estimate(#rawWeight)"
    ).getValue(context, String.class);

Đối số `#rawWeight` có kiểu String, trong khi method nhận Integer. Nếu TypeConverter có khả năng chuyển String sang Integer, lời gọi có thể được thực hiện với giá trị 1500.

Nếu class có nhiều overload, ví dụ `estimate(Integer)`, `estimate(Long)` và `estimate(String)`, kiểu runtime và khả năng chuyển đổi có thể ảnh hưởng method được chọn. Khi overload có thể gây mơ hồ, hãy chuẩn hóa kiểu đối số trước trong Java hoặc dùng method có chữ ký rõ ràng.

Chuyển đổi thành công cũng không đồng nghĩa dữ liệu hợp lệ về nghiệp vụ. Một chuỗi có thể chuyển thành số nhưng vẫn nằm ngoài giới hạn khối lượng mà dịch vụ cho phép.

## 5. Chuyển đổi đối số khi tạo object

Constructor invocation cũng có thể cần chuyển đổi đối số để khớp với constructor của class:

    new com.example.Customer('Lan', '25')

Giả sử Customer có constructor nhận `String name` và `Integer age`. Nếu TypeConverter hỗ trợ String sang Integer, SpEL có thể chuyển đối số thứ hai để gọi constructor phù hợp.

ConstructorResolver chịu trách nhiệm tìm constructor; TypeConverter hỗ trợ chuyển đổi kiểu khi cần. Hai thành phần có vai trò khác nhau. Nếu class không resolve được, không có constructor phù hợp hoặc converter không thể chuyển đổi đối số, quá trình tạo instance sẽ thất bại.

Nếu cần tạo object với dữ liệu không tin cậy, hãy kiểm tra giá trị trước khi gọi constructor. Không dùng khả năng chuyển đổi kiểu thay cho validation hoặc giới hạn class được phép khởi tạo.

## 6. Chuyển kiểu kết quả bằng getValue

Expression cung cấp overload `getValue` nhận kiểu đích. SpEL đánh giá expression trước, sau đó dùng TypeConverter để chuyển kết quả sang kiểu được yêu cầu nếu cần.

Ví dụ:

    Integer result = parser.parseExpression("10 + 5")
            .getValue(context, Integer.class);

Hoặc chuyển một giá trị chuỗi:

    Long id = parser.parseExpression("'123456'")
            .getValue(context, Long.class);

Đây là chuyển đổi kết quả cuối cùng. Nó không làm thay đổi kiểu của các toán hạng trong lúc phép toán đã được thực hiện.

Ví dụ, phép chia hai số nguyên có thể tạo kết quả nguyên trước khi chuyển đổi:

    Double result = parser.parseExpression("1 / 2")
            .getValue(context, Double.class);

Nếu phép chia được thực hiện như phép chia số nguyên, kết quả trung gian là 0; chuyển kết quả đó sang Double vẫn cho 0.0. Muốn có 0.5, hãy dùng toán hạng số thực ngay từ đầu:

    Double result = parser.parseExpression("1.0 / 2")
            .getValue(context, Double.class);

Vì vậy, cần phân biệt chuyển đổi kiểu kết quả với cách toán tử xử lý kiểu của toán hạng.

## 7. StandardTypeConverter và ConversionService

StandardTypeConverter là implementation TypeConverter thường dùng trong StandardEvaluationContext. Nó ủy quyền việc chuyển đổi cho Spring ConversionService.

Có thể tạo ConversionService riêng, đăng ký converter của ứng dụng rồi gắn vào context:

    DefaultConversionService conversionService =
            new DefaultConversionService();

    conversionService.addConverter(
            String.class,
            ShippingMode.class,
            ShippingMode::valueOf
    );

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeConverter(
            new StandardTypeConverter(conversionService)
    );

    context.setVariable("rawMode", "EXPRESS");

    ShippingMode mode = parser.parseExpression("#rawMode")
            .getValue(context, ShippingMode.class);

Trong ví dụ, converter chuyển chuỗi thành enum ShippingMode. `DefaultConversionService` cung cấp các converter mặc định; ứng dụng có thể đăng ký thêm converter cho kiểu domain riêng.

Khi cấu hình converter tùy chỉnh, cần xác định rõ đầu vào hợp lệ và cách xử lý giá trị không hợp lệ. Converter nên tập trung vào chuyển đổi biểu diễn dữ liệu, không nên thực hiện truy vấn database, gọi API hoặc thay đổi trạng thái hệ thống.

## 8. Dùng TypeConverter với SimpleEvaluationContext

SimpleEvaluationContext cung cấp tập tính năng hạn chế hơn StandardEvaluationContext. Có thể cấu hình ConversionService riêng qua builder:

    SimpleEvaluationContext context =
            SimpleEvaluationContext.forReadOnlyDataBinding()
                    .withConversionService(conversionService)
                    .build();

Cách này hữu ích khi expression cần chuyển đổi kiểu nhưng không cần các tính năng rộng như type reference, constructor invocation hoặc bean reference.

SimpleEvaluationContext không hỗ trợ constructor invocation và bean reference. Việc thêm ConversionService không bật lại các tính năng đó; nó chỉ cấu hình cơ chế chuyển đổi cho các thao tác được context hỗ trợ.

Chọn builder read-only hoặc read-write theo mục đích truy cập property. Converter không quyết định property nào được phép ghi.

## 9. Chuyển đổi collection và kiểu generic

TypeDescriptor giúp Spring giữ thông tin về kiểu phần tử trong collection và kiểu key/value của map. Vì vậy, ConversionService có thể chuyển đổi dữ liệu collection khi kiểu nguồn và kiểu đích được mô tả đầy đủ.

Ví dụ, ứng dụng có thể cần chuyển một danh sách chuỗi số thành danh sách Integer. Việc chuyển đổi phụ thuộc vào TypeDescriptor của property hoặc tham số đích và các converter đã đăng ký.

Khi làm việc với collection, hãy kiểm tra cả kiểu container và kiểu phần tử. Chuyển đổi một List sang List khác không chỉ là thay class của collection; từng phần tử cũng có thể cần được chuyển đổi. Nếu một phần tử không hợp lệ, toàn bộ thao tác chuyển đổi có thể thất bại.

Không nên giả định mọi kiểu collection hoặc cấu trúc lồng nhau đều được chuyển đổi tự động theo cùng một cách. Với cấu trúc domain phức tạp, một converter chuyên biệt hoặc bước mapping rõ ràng trong Java thường dễ kiểm soát hơn.

## 10. Null, kiểu primitive và lỗi chuyển đổi

Null có thể được truyền qua expression, nhưng không phải kiểu đích nào cũng nhận được null. Kiểu tham chiếu như Integer hoặc Boolean có thể biểu diễn null; kiểu primitive như `int` hoặc `boolean` thì không.

Ví dụ, nếu method nhận `int`, một đối số null không thể được chuyển thành giá trị primitive hợp lệ nếu không có quy tắc mặc định do ứng dụng cung cấp. Hãy xử lý null trước khi gọi method hoặc dùng kiểu wrapper nếu null là một trạng thái hợp lệ.

Các lỗi chuyển đổi thường gặp:

- Chuỗi không có định dạng phù hợp với kiểu đích.
- Giá trị số vượt miền biểu diễn của kiểu đích.
- Converter không được đăng ký hoặc không hỗ trợ cặp kiểu nguồn/đích.
- Collection có phần tử không thể chuyển đổi.
- Null được truyền tới kiểu primitive.
- Nhiều overload có thể nhận giá trị sau chuyển đổi và gây mơ hồ khi phân giải.

Khi lỗi xảy ra, hãy kiểm tra kiểu runtime của giá trị nguồn, TypeDescriptor đích và converter đang được context sử dụng. Không nên bắt lỗi rồi âm thầm trả về giá trị mặc định nếu điều đó có thể làm sai dữ liệu nghiệp vụ.

## 11. Tạo custom Converter đúng phạm vi

Nếu domain có kiểu riêng, hãy đăng ký converter tường minh thay vì rải logic parse chuỗi trong nhiều expression.

Ví dụ:

    public enum ShippingMode {
        STANDARD,
        EXPRESS
    }

    Converter<String, ShippingMode> shippingModeConverter =
            source -> ShippingMode.valueOf(
                    source.trim().toUpperCase(Locale.ROOT)
            );

    DefaultConversionService conversionService =
            new DefaultConversionService();

    conversionService.addConverter(shippingModeConverter);

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setTypeConverter(
            new StandardTypeConverter(conversionService)
    );

Converter này chuẩn hóa chuỗi rồi chuyển thành enum. Với đầu vào không khớp enum, `valueOf` ném exception; ứng dụng có thể chuyển lỗi đó thành thông báo validation phù hợp ở tầng gọi.

Giữ converter đơn giản, có thể kiểm thử độc lập và không phụ thuộc trạng thái của request. Nếu chuyển đổi cần ngữ cảnh người dùng, quyền truy cập hoặc dữ liệu từ database, hãy thực hiện ở service nghiệp vụ rồi truyền giá trị đã xác thực vào EvaluationContext.

## 12. Kiểm soát và kiểm thử chuyển đổi

Khi cấu hình TypeConverter, nên kiểm tra các trường hợp:

1. Giá trị nguồn đúng định dạng và chuyển đổi thành công.
2. Giá trị nguồn sai định dạng.
3. Giá trị vượt miền của kiểu đích.
4. Giá trị null và kiểu primitive.
5. Chuyển đổi đối số method và constructor.
6. Chuyển đổi khi gán property.
7. Chuyển đổi kết quả qua `getValue(context, TargetType.class)`.
8. Collection có phần tử hợp lệ và không hợp lệ.
9. Converter tùy chỉnh được áp dụng đúng context.

Có thể kiểm tra khả năng chuyển đổi trước:

    TypeConverter converter = context.getTypeConverter();

    boolean supported = converter.canConvert(
            TypeDescriptor.valueOf(String.class),
            TypeDescriptor.valueOf(Integer.class)
    );

Kiểm tra này cho biết converter có hỗ trợ cặp kiểu được mô tả hay không; nó không bảo đảm mọi giá trị String cụ thể đều chuyển đổi thành công. Muốn xác nhận dữ liệu thực tế, vẫn cần thực hiện conversion và xử lý lỗi.

Nếu cùng một Expression được đánh giá với nhiều EvaluationContext, hãy kiểm thử từng context vì chúng có thể dùng TypeConverter khác nhau.

## 13. Ghi nhớ

TypeConverter là dịch vụ chuyển đổi kiểu của EvaluationContext trong lúc SpEL đánh giá expression. Nó hỗ trợ chuyển giá trị khi gán property, truyền đối số cho method/constructor và lấy kết quả theo kiểu yêu cầu. StandardEvaluationContext mặc định dùng StandardTypeConverter dựa trên ConversionService; có thể đăng ký converter tùy chỉnh và gắn vào context. TypeDescriptor giúp giữ metadata kiểu, kể cả thông tin collection. Chuyển đổi kiểu không thay thế validation, không cấp quyền truy cập và không thay đổi quy tắc số học đã áp dụng cho toán hạng. Hãy kiểm tra null, miền giá trị, overload và lỗi conversion; chỉ đăng ký converter cần thiết cho use case.
