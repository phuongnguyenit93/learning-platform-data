# ConversionService và tích hợp chuyển đổi kiểu của Spring

Spring Framework cung cấp hệ thống chuyển đổi kiểu tập trung thông qua **ConversionService**. Thay vì để từng thành phần tự viết logic chuyển String sang số, enum, kiểu miền hoặc collection, ứng dụng có thể đăng ký converter một lần rồi dùng chung ở nhiều nơi.

ConversionService được tích hợp trong nhiều thành phần Spring như SpEL, DataBinder, Spring MVC và cơ chế binding cấu hình. Nhờ đó, cùng một quy tắc chuyển đổi có thể được áp dụng nhất quán khi đọc dữ liệu, gán property, bind request hoặc đánh giá biểu thức.

Cần phân biệt **chuyển đổi kiểu (conversion)** với **định dạng văn bản (formatting)**. Conversion biến một giá trị từ kiểu nguồn sang kiểu đích; formatting thường chuyển giữa kiểu dữ liệu và dạng văn bản có xét locale, ví dụ ngày tháng hoặc tiền tệ.

## 1. ConversionService là gì?

### 1.1. Vai trò của ConversionService

ConversionService là abstraction trung tâm để kiểm tra và thực hiện chuyển đổi giữa các kiểu Java.

Ví dụ:

- String sang Integer hoặc Long.
- String sang enum.
- Number sang kiểu số khác.
- String sang kiểu định danh do ứng dụng định nghĩa.
- Collection có phần tử nguồn sang collection có phần tử đích, khi có converter phù hợp.
- Object sang kiểu đích theo quy tắc được đăng ký.

Thay vì gọi một hàm tiện ích riêng ở mỗi nơi, thành phần Spring có thể yêu cầu ConversionService thực hiện chuyển đổi theo cùng một chính sách.

### 1.2. Interface chính

Các phương thức thường dùng của ConversionService gồm:

~~~java
public interface ConversionService {

    boolean canConvert(
            Class<?> sourceType,
            Class<?> targetType
    );

    <T> T convert(
            Object source,
            Class<T> targetType
    );

    boolean canConvert(
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );
}
~~~

Hai nhóm overload phục vụ các nhu cầu khác nhau:

- Dùng Class khi chỉ cần biết kiểu nguồn và kiểu đích ở mức class.
- Dùng TypeDescriptor khi cần metadata chi tiết hơn, chẳng hạn kiểu phần tử generic hoặc annotation trên field/parameter.

Ví dụ kiểm tra khả năng chuyển đổi:

~~~java
ConversionService conversionService =
        new DefaultConversionService();

boolean supported =
        conversionService.canConvert(String.class, Integer.class);
~~~

Thực hiện chuyển đổi:

~~~java
Integer quantity =
        conversionService.convert("42", Integer.class);
~~~

Nếu không có converter phù hợp hoặc dữ liệu không thể chuyển đổi, thao tác convert có thể ném ConversionException hoặc subtype cụ thể. canConvert giúp kiểm tra trước khả năng hỗ trợ, nhưng không bảo đảm mọi giá trị runtime đều hợp lệ. Ví dụ, String có thể chuyển sang Integer về mặt kiểu, nhưng chuỗi "abc" vẫn không thể parse thành số.

### 1.3. ConversionService và ConverterRegistry

ConversionService cung cấp API đọc và thực hiện chuyển đổi. Việc đăng ký converter được quản lý qua ConverterRegistry.

Các implementation phổ biến như DefaultConversionService và GenericConversionService triển khai cả hai vai trò: cung cấp khả năng chuyển đổi và cho phép đăng ký converter.

Về mặt thiết kế, thành phần sử dụng thường chỉ cần phụ thuộc vào interface ConversionService. Phần cấu hình ứng dụng giữ reference tới ConverterRegistry hoặc implementation cụ thể để đăng ký converter.

## 2. Các implementation thường dùng

### 2.1. GenericConversionService

GenericConversionService là implementation nền tảng, quản lý tập converter và phân giải converter phù hợp cho cặp kiểu nguồn/đích.

Ứng dụng có thể tạo instance và đăng ký converter:

~~~java
GenericConversionService conversionService =
        new GenericConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

Sau khi đăng ký, có thể dùng interface ConversionService để chuyển đổi:

~~~java
CustomerCode code =
        conversionService.convert("C-100", CustomerCode.class);
~~~

GenericConversionService phù hợp khi ứng dụng muốn tự quyết định tập converter được đăng ký. Nếu cần các converter phổ biến có sẵn, DefaultConversionService thường tiện hơn.

### 2.2. DefaultConversionService

DefaultConversionService cung cấp các converter tiêu chuẩn thường dùng cho kiểu Java và collection. Nó là lựa chọn phổ biến cho ứng dụng cần bộ chuyển đổi mặc định của Spring.

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

Integer count =
        conversionService.convert("25", Integer.class);

Boolean enabled =
        conversionService.convert("true", Boolean.class);
~~~

DefaultConversionService cũng triển khai ConverterRegistry, vì vậy có thể đăng ký converter bổ sung:

~~~java
conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

Nếu ứng dụng cần nhiều quy tắc chuyển đổi dùng chung, hãy cấu hình một ConversionService tại composition root rồi truyền interface này tới những thành phần cần sử dụng.

### 2.3. FormattingConversionService

FormattingConversionService mở rộng hệ thống conversion để hỗ trợ Formatter và annotation formatting. Nó phù hợp với các tình huống cần chuyển đổi giữa chuỗi và kiểu dữ liệu theo locale.

Ví dụ, ngày tháng có thể có nhiều cách biểu diễn tùy locale. Một Formatter có thể parse chuỗi đầu vào thành LocalDate và in LocalDate thành chuỗi theo định dạng được cấu hình.

DefaultFormattingConversionService cung cấp cấu hình formatting mặc định cùng các converter phổ biến. Đây là nền tảng thường gặp trong binding dữ liệu web.

### 2.4. Chọn implementation

| Implementation | Mục đích chính | Khi nào dùng |
|---|---|---|
| GenericConversionService | Bộ máy conversion nền tảng | Muốn tự đăng ký tập converter |
| DefaultConversionService | ConversionService với converter tiêu chuẩn | Cần chuyển đổi kiểu thông dụng |
| FormattingConversionService | Conversion kết hợp Formatter | Cần định dạng theo locale và annotation |
| DefaultFormattingConversionService | Formatting service với cấu hình mặc định | Cần conversion và formatting thông dụng |

Không nên tạo nhiều ConversionService riêng lẻ với các quy tắc khác nhau nếu nghiệp vụ yêu cầu chuyển đổi nhất quán. Hãy xác định rõ phạm vi: toàn ứng dụng, tầng web hay một context SpEL riêng.

## 3. Đăng ký converter tùy chỉnh

### 3.1. Converter<S, T>

Converter là cách đơn giản để định nghĩa chuyển đổi từ một kiểu nguồn sang một kiểu đích:

~~~java
public interface Converter<S, T> {
    T convert(S source);
}
~~~

Ví dụ tạo kiểu định danh:

~~~java
public record CustomerCode(String value) {
    public CustomerCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer code is required"
            );
        }
    }
}
~~~

Đăng ký converter từ String sang CustomerCode:

~~~java
Converter<String, CustomerCode> customerCodeConverter =
        CustomerCode::new;

DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(customerCodeConverter);
~~~

Sử dụng:

~~~java
CustomerCode code =
        conversionService.convert("C-100", CustomerCode.class);
~~~

Converter nên tập trung vào một cặp kiểu và có hành vi xác định. Nếu dữ liệu đầu vào không hợp lệ, hãy ném lỗi phù hợp thay vì âm thầm tạo object sai.

### 3.2. ConverterFactory<S, R>

ConverterFactory phù hợp khi một kiểu nguồn có thể chuyển sang một họ kiểu đích có chung kiểu cha hoặc interface.

Ví dụ điển hình là chuyển String sang các enum:

~~~java
public class StringToEnumConverterFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {

        return source -> (T) Enum.valueOf(
                targetType,
                source.trim().toUpperCase(Locale.ROOT)
        );
    }
}
~~~

Đăng ký factory:

~~~java
conversionService.addConverterFactory(
        new StringToEnumConverterFactory()
);
~~~

Sau đó có thể chuyển String sang enum đích tương ứng nếu tên hằng hợp lệ.

Ví dụ:

~~~java
OrderStatus status =
        conversionService.convert("paid", OrderStatus.class);
~~~

Trong ví dụ, chuẩn hóa chữ hoa được thực hiện theo Locale.ROOT để tránh phụ thuộc locale mặc định của máy. Hãy chọn chính sách chuẩn hóa phù hợp với domain; không phải enum nào cũng nên bỏ qua chữ hoa/chữ thường hoặc khoảng trắng.

### 3.3. GenericConverter

GenericConverter phù hợp khi cần hỗ trợ nhiều cặp kiểu nguồn/đích hoặc cần thông tin kiểu chi tiết hơn.

Interface này cung cấp tập ConvertiblePair và phương thức convert nhận source cùng TypeDescriptor của hai phía:

~~~java
public interface GenericConverter {

    Set<ConvertiblePair> getConvertibleTypes();

    Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType
    );
}
~~~

Ví dụ converter có thể khai báo hỗ trợ một cặp kiểu:

~~~java
public Set<ConvertiblePair> getConvertibleTypes() {
    return Set.of(
            new ConvertiblePair(String.class, CustomerCode.class)
    );
}
~~~

GenericConverter hữu ích khi quy tắc chuyển đổi phụ thuộc vào generic type, metadata hoặc nhiều kiểu đích. Với một cặp đơn giản, Converter thường dễ đọc và ít mã hơn.

### 3.4. ConditionalGenericConverter

ConditionalGenericConverter bổ sung điều kiện để quyết định một converter có áp dụng cho cặp TypeDescriptor cụ thể hay không.

Điều này hữu ích khi cùng một cặp kiểu có nhiều quy tắc nhưng chỉ một số trường hoặc annotation cần dùng converter đó.

Ví dụ về cấu trúc:

~~~java
public class CustomConditionalConverter
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Set.of(
                new ConvertiblePair(String.class, CustomerCode.class)
        );
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return targetType.hasAnnotation(SpecialCode.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return new CustomerCode(source.toString());
    }
}
~~~

Đoạn mã minh họa cách dùng metadata đích để chọn converter. Trong ứng dụng thực tế, annotation phải được đặt trên metadata mà TypeDescriptor có thể nhìn thấy và converter cần kiểm tra cả null, dữ liệu sai định dạng cùng các invariant của kiểu đích.

## 4. TypeDescriptor và generic type

### 4.1. Vì sao Class chưa đủ?

Java generic bị type erasure ở runtime. Hai trường sau đều có raw type là List nhưng kiểu phần tử khác nhau:

~~~java
List<String> names;
List<Integer> quantities;
~~~

Nếu chỉ nhìn List.class, ConversionService không biết phần tử cần chuyển sang String hay Integer.

TypeDescriptor giữ thêm metadata về kiểu collection, kiểu phần tử, annotation và nguồn khai báo khi có sẵn.

### 4.2. Tạo TypeDescriptor

Có thể lấy descriptor từ field hoặc method parameter:

~~~java
Field field = Report.class.getDeclaredField("quantities");

TypeDescriptor sourceType =
        new TypeDescriptor(field);
~~~

Có thể tạo descriptor cho collection với kiểu phần tử cụ thể:

~~~java
TypeDescriptor stringListType =
        TypeDescriptor.collection(
                List.class,
                TypeDescriptor.valueOf(String.class)
        );
~~~

Và descriptor cho kiểu đích:

~~~java
TypeDescriptor integerListType =
        TypeDescriptor.collection(
                List.class,
                TypeDescriptor.valueOf(Integer.class)
        );
~~~

Dùng overload convert nhận TypeDescriptor khi muốn ConversionService biết cả kiểu phần tử:

~~~java
Object converted = conversionService.convert(
        List.of("10", "20"),
        stringListType,
        integerListType
);
~~~

Khả năng chuyển đổi collection phụ thuộc converter được đăng ký và metadata nguồn/đích. TypeDescriptor cung cấp thông tin để converter xử lý đúng, nhưng không tự tạo ra một quy tắc chuyển đổi chưa được hỗ trợ.

### 4.3. Annotation trên TypeDescriptor

TypeDescriptor có thể mang annotation của field hoặc parameter. Formatter hoặc ConditionalGenericConverter có thể dùng metadata đó để chọn cách xử lý.

Ví dụ, một field có annotation định dạng ngày có thể cần parse theo pattern riêng. Việc đọc annotation từ TypeDescriptor giúp converter/formatter áp dụng quy tắc theo nơi khai báo thay vì hard-code theo tên property.

Không nên dùng annotation làm nơi chứa dữ liệu nhạy cảm hoặc chính sách phân quyền. Metadata chỉ hỗ trợ lựa chọn conversion/formatting; quyền truy cập vẫn phải được kiểm tra ở tầng phù hợp.

## 5. Kiểm tra và thực hiện conversion

### 5.1. Dùng canConvert trước khi convert

Có thể kiểm tra cặp kiểu:

~~~java
if (conversionService.canConvert(String.class, Integer.class)) {
    Integer value =
            conversionService.convert("42", Integer.class);
}
~~~

canConvert trả lời liệu service có đường chuyển đổi cho kiểu nguồn/đích hay không. Nó không kiểm tra trước mọi giá trị cụ thể.

Ví dụ, String sang Integer có thể được hỗ trợ, nhưng chuỗi không phải số vẫn gây lỗi khi convert.

### 5.2. Xử lý ConversionException

Khi dữ liệu đến từ người dùng, hãy xử lý lỗi chuyển đổi rõ ràng:

~~~java
try {
    Integer quantity =
            conversionService.convert(input, Integer.class);
} catch (ConversionException ex) {
    throw new IllegalArgumentException(
            "Quantity must be a valid integer",
            ex
    );
}
~~~

Không nên bắt exception rồi trả về 0 nếu 0 không phải giá trị thay thế hợp lệ theo nghiệp vụ. Giữ nguyên cause để log nội bộ có thể xác định converter hoặc dữ liệu nào gây lỗi.

### 5.3. Null và kiểu đích primitive

Các kiểu tham chiếu có thể biểu diễn null, còn primitive như int và boolean thì không. Khi nguồn null hoặc conversion không thể tạo giá trị primitive, thao tác có thể thất bại.

Nếu trường có thể thiếu, cân nhắc dùng wrapper như Integer hoặc Boolean, hoặc validate bắt buộc trước khi chuyển đổi. Không tự động coi null là 0 hoặc false nếu domain chưa định nghĩa như vậy.

## 6. Tích hợp ConversionService với SpEL

### 6.1. SpEL dùng TypeConverter

SpEL sử dụng TypeConverter của EvaluationContext để chuyển đổi giá trị khi cần, ví dụ:

- Gán giá trị cho property có kiểu đích.
- Chuyển argument để gọi method.
- Chuyển argument khi gọi constructor.
- Chuyển kết quả theo kiểu mà caller yêu cầu trong getValue.

StandardTypeConverter là adapter kết nối SpEL với hệ thống ConversionService của Spring.

### 6.2. Dùng ConversionService mặc định

StandardEvaluationContext có TypeConverter mặc định dựa trên cơ chế chuyển đổi chuẩn của Spring. Với các kiểu thông dụng, có thể không cần cấu hình thêm.

Ví dụ method yêu cầu Long:

~~~java
public String findCustomer(Long id) {
    return "Customer-" + id;
}
~~~

Expression truyền String:

~~~java
#service.findCustomer('42')
~~~

Nếu converter mặc định hỗ trợ String sang Long, SpEL có thể chuyển argument trước khi gọi method.

### 6.3. Gắn ConversionService riêng vào SpEL

Khi ứng dụng có converter miền riêng, tạo StandardTypeConverter từ ConversionService đó:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

context.setVariable("customerService", customerService);
~~~

Nếu method nhận CustomerCode:

~~~java
public String lookup(CustomerCode code) {
    return code.value();
}
~~~

Expression:

~~~java
#customerService.lookup('C-100')
~~~

SpEL dùng TypeConverter của context để chuyển String thành CustomerCode trước khi gọi method.

### 6.4. Conversion khi setValue

ConversionService cũng có thể được dùng khi gán giá trị vào property có kiểu đích:

~~~java
parser.parseExpression("quantity")
        .setValue(context, "25");
~~~

Nếu property quantity là Integer và TypeConverter hỗ trợ String sang Integer, SpEL có thể chuyển đổi giá trị trước khi ghi.

Điều này phụ thuộc property có thể ghi và PropertyAccessor hỗ trợ thao tác set. Một property chỉ đọc không thể cập nhật chỉ vì có converter phù hợp.

### 6.5. Conversion của kết quả getValue

Có thể yêu cầu kiểu kết quả:

~~~java
Integer quantity = parser
        .parseExpression("'25'")
        .getValue(context, Integer.class);
~~~

Trong trường hợp này, SpEL yêu cầu TypeConverter chuyển kết quả String sang Integer nếu cần.

Đây là conversion ở phía kết quả, khác với conversion của argument trước khi gọi method. Khi debug, hãy tách hai vị trí để biết dữ liệu thất bại ở bước nào.

## 7. Tích hợp với Spring MVC và DataBinder

### 7.1. DataBinder

DataBinder dùng cơ chế conversion và binding để đưa dữ liệu đầu vào vào property của object đích. Khi request hoặc dữ liệu form được bind vào DTO, Spring cần chuyển giá trị dạng chuỗi sang kiểu property tương ứng.

Ví dụ DTO:

~~~java
public class SearchForm {

    private Integer pageSize;

    public Integer getPageSize() {
        return pageSize;
    }

    public void setPageSize(Integer pageSize) {
        this.pageSize = pageSize;
    }
}
~~~

Dữ liệu văn bản "20" có thể được chuyển thành Integer khi binder có ConversionService phù hợp.

DataBinder cũng quản lý lỗi binding và BindingResult, giúp ứng dụng báo lỗi theo field thay vì để exception conversion lan ra ngoài.

### 7.2. Cấu hình ConversionService cho binder

Có thể cung cấp ConversionService cho DataBinder:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

DataBinder binder = new DataBinder(new SearchForm());
binder.setConversionService(conversionService);
~~~

Sau đó binder sử dụng service này khi chuyển dữ liệu vào property.

Trong ứng dụng web thực tế, Spring MVC quản lý binder và conversion service theo cấu hình MVC. Không nên tạo một DataBinder mới cho từng field nếu framework đã cung cấp cơ chế binding chuẩn.

### 7.3. Spring MVC và WebMvcConfigurer

Có thể đăng ký converter hoặc formatter cho Spring MVC thông qua WebMvcConfigurer:

~~~java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(
                String.class,
                CustomerCode.class,
                CustomerCode::new
        );
    }
}
~~~

FormatterRegistry cho phép đăng ký Converter, ConverterFactory, GenericConverter và Formatter phù hợp.

Các converter đăng ký tại đây có thể được dùng trong quá trình binding request parameter, path variable và dữ liệu web khác theo cơ chế MVC.

Hãy tránh đăng ký converter quá tổng quát, ví dụ String sang Object hoặc một converter làm thay đổi semantics của nhiều kiểu. Một converter hẹp cho kiểu miền cụ thể dễ kiểm soát hơn.

## 8. Tích hợp với Spring Boot và cấu hình ứng dụng

### 8.1. Dùng ConversionService do ứng dụng quản lý

Ứng dụng có thể khai báo bean ConversionService để các thành phần phụ thuộc dùng chung:

~~~java
@Configuration
public class ConversionConfiguration {

    @Bean
    public ConversionService conversionService() {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(
                String.class,
                CustomerCode.class,
                CustomerCode::new
        );

        return service;
    }
}
~~~

Tên bean và cách Spring Boot hoặc Spring MVC chọn ConversionService có thể phụ thuộc loại ứng dụng và cấu hình hiện có. Khi cần tích hợp cho MVC, WebMvcConfigurer.addFormatters là extension point rõ ràng; khi cần dùng trong SpEL, hãy truyền service vào StandardTypeConverter của EvaluationContext.

Không nên giả định một bean ConversionService tùy ý luôn thay thế mọi service nội bộ của tất cả subsystem. Hãy kiểm tra đúng điểm tích hợp mà ứng dụng đang dùng.

### 8.2. Binding cấu hình

Spring Boot sử dụng conversion trong quá trình bind cấu hình vào các kiểu Java. Ví dụ, chuỗi trong properties hoặc YAML có thể được chuyển thành Duration, DataSize, enum hoặc kiểu ứng dụng nếu có converter phù hợp.

Ví dụ cấu hình:

~~~yaml
app:
  retry-count: 3
  timeout: 5s
~~~

DTO cấu hình:

~~~java
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    private int retryCount;
    private Duration timeout;

    // getters và setters
}
~~~

Spring chuyển các giá trị cấu hình sang kiểu property theo conversion service và các converter được cấu hình cho binding.

Với custom type, cần đăng ký converter theo extension point phù hợp với cơ chế configuration binding của phiên bản Spring Boot đang dùng. Đừng nhầm converter cho MVC với mọi converter của configuration properties nếu phạm vi đăng ký khác nhau.

## 9. ConversionService và Formatter

### 9.1. Conversion khác formatting

Conversion tập trung vào chuyển một giá trị từ kiểu này sang kiểu khác. Formatting tập trung vào cách biểu diễn dữ liệu thành văn bản và parse văn bản trở lại, thường phụ thuộc locale.

Ví dụ:

- String "42" sang Integer 42: conversion.
- LocalDate sang "12/11/2026" theo locale: formatting.
- String theo pattern ngày tháng sang LocalDate: parse bằng Formatter.

Formatter có hai thao tác chính:

~~~java
public interface Formatter<T> extends Printer<T>, Parser<T> {
}
~~~

Printer tạo chuỗi từ object; Parser đọc chuỗi thành object theo Locale.

### 9.2. Đăng ký Formatter

Ví dụ formatter cho LocalDate:

~~~java
public class IsoDateFormatter implements Formatter<LocalDate> {

    @Override
    public LocalDate parse(
            String text,
            Locale locale) {
        return LocalDate.parse(text);
    }

    @Override
    public String print(
            LocalDate object,
            Locale locale) {
        return object.toString();
    }
}
~~~

Đăng ký:

~~~java
DefaultFormattingConversionService service =
        new DefaultFormattingConversionService();

service.addFormatter(new IsoDateFormatter());
~~~

Formatter này dùng định dạng ISO của LocalDate. Nếu ứng dụng cần định dạng theo locale hoặc pattern cấu hình, hãy dùng formatter phù hợp và kiểm thử nhiều locale.

### 9.3. Annotation formatting

Spring hỗ trợ annotation formatting để gắn metadata định dạng lên field hoặc parameter. TypeDescriptor có thể mang annotation này để FormattingConversionService chọn formatter phù hợp.

Ví dụ trong ứng dụng web, annotation định dạng ngày có thể quyết định cách parse request parameter thành LocalDate. Việc chọn formatter phụ thuộc metadata và cấu hình formatter registry.

Không nên dùng Formatter cho mọi conversion. Với kiểu miền không cần biểu diễn văn bản theo locale, Converter thường đơn giản hơn.

## 10. Thiết kế converter tốt

Một converter nên có phạm vi rõ và hành vi dễ dự đoán:

- Chỉ chuyển đổi cặp kiểu nguồn/đích mà nó thực sự hiểu.
- Kiểm tra dữ liệu sai định dạng và báo lỗi có ý nghĩa.
- Không truy cập database hoặc gọi network trong convert.
- Không ghi trạng thái hoặc thực hiện side effect.
- Không trả về giá trị giả như 0, false hoặc object rỗng để che lỗi.
- Xử lý null theo hợp đồng của ConversionService và kiểu đích.
- Dùng TypeDescriptor khi quy tắc phụ thuộc generic hoặc annotation.
- Tránh đăng ký converter quá rộng gây xung đột với converter tiêu chuẩn.

Converter nên nhẹ và thuần. Nếu cần tra cứu database để tạo object miền, hãy thực hiện ở service/application layer rồi truyền object đã xác thực vào nơi cần dùng.

### 10.1. Tránh converter mơ hồ

Nếu có nhiều converter cho cùng cặp kiểu hoặc nhiều đường chuyển đổi gián tiếp, kết quả có thể khó dự đoán. Hãy giữ tập converter gọn, tránh đăng ký hai quy tắc cạnh tranh cho cùng mục đích.

Với các kiểu miền khác nhau, nên tạo kiểu đích riêng và converter cụ thể thay vì một converter String sang Object.

### 10.2. Cấu hình trước khi sử dụng

ConversionService thường được chia sẻ giữa nhiều thành phần. Hãy hoàn tất việc đăng ký converter trong giai đoạn cấu hình trước khi phục vụ request hoặc đánh giá expression đồng thời.

Không nên thay đổi registry tùy tiện trong lúc nhiều luồng đang sử dụng service. Nếu cần thay đổi bộ converter, hãy quản lý vòng đời cấu hình rõ ràng.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| canConvert trả false | Không có converter cho cặp kiểu | Đăng ký converter phù hợp hoặc thay đổi kiểu đầu vào |
| canConvert true nhưng convert lỗi | Giá trị runtime sai định dạng | Validate dữ liệu và xử lý ConversionException |
| Collection chuyển đổi sai phần tử | Chỉ dùng raw Class, thiếu generic metadata | Dùng TypeDescriptor khi cần |
| Converter không được MVC sử dụng | Đăng ký ở sai phạm vi hoặc sai extension point | Kiểm tra WebMvcConfigurer và MVC configuration |
| SpEL không dùng converter tùy chỉnh | Context vẫn dùng TypeConverter mặc định khác | Gắn StandardTypeConverter với ConversionService cần dùng |
| Property không cập nhật | Property chỉ đọc hoặc accessor không hỗ trợ write | Kiểm tra setter và PropertyAccessor |
| Chuỗi ngày parse sai locale | Dùng converter/formatter không phù hợp | Đăng ký Formatter và kiểm thử locale |
| Nhiều converter cạnh tranh | Quy tắc đăng ký quá rộng hoặc trùng nhau | Thu hẹp cặp kiểu và kiểm tra registry |
| Dữ liệu sai bị thay bằng mặc định | Converter che giấu lỗi | Ném lỗi chuyển đổi và xử lý ở tầng phù hợp |

## 12. Ví dụ hoàn chỉnh: một converter dùng trong Java và SpEL

Tạo kiểu miền:

~~~java
public record CustomerCode(String value) {
    public CustomerCode {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Customer code is required"
            );
        }
    }
}
~~~

Tạo ConversionService:

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);
~~~

Dùng trực tiếp trong Java:

~~~java
CustomerCode code =
        conversionService.convert("C-100", CustomerCode.class);
~~~

Dùng trong SpEL:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService)
);

context.setVariable("customerService", customerService);

CustomerCode result = parser
        .parseExpression(
                "#customerService.find('C-100')"
        )
        .getValue(context, CustomerCode.class);
~~~

Nếu method find nhận CustomerCode, SpEL có thể dùng TypeConverter để chuyển String argument sang kiểu miền trước khi gọi. Nếu method trả về CustomerCode, kiểu kết quả đã đúng và không cần conversion thêm.

Ví dụ này minh họa cách tái sử dụng cùng một quy tắc chuyển đổi ở Java và trong SpEL.

## 13. Kiểm thử ConversionService

Nên kiểm thử cả khả năng hỗ trợ kiểu, giá trị hợp lệ và dữ liệu lỗi:

~~~java
DefaultConversionService service =
        new DefaultConversionService();

assertTrue(
        service.canConvert(String.class, Integer.class)
);

assertEquals(
        Integer.valueOf(42),
        service.convert("42", Integer.class)
);
~~~

Kiểm thử converter tùy chỉnh:

~~~java
service.addConverter(
        String.class,
        CustomerCode.class,
        CustomerCode::new
);

assertEquals(
        new CustomerCode("C-100"),
        service.convert("C-100", CustomerCode.class)
);
~~~

Và kiểm thử dữ liệu không hợp lệ:

~~~java
assertThrows(
        IllegalArgumentException.class,
        () -> service.convert(" ", CustomerCode.class)
);
~~~

Tùy converter và cách exception được bọc, hãy xác nhận exception thực tế mà API công khai trả về. Không nên viết test phụ thuộc vào message nội bộ của framework nếu message không thuộc hợp đồng ứng dụng.

Với tích hợp SpEL, kiểm thử riêng:

- Argument method cần chuyển kiểu.
- Argument constructor cần chuyển kiểu.
- Gán property bằng setValue.
- getValue với kiểu đích khác kiểu kết quả.
- Generic collection có phần tử cần chuyển đổi.
- Converter tùy chỉnh và trường hợp converter thất bại.

Với Spring MVC, thêm kiểm thử binding request parameter và BindingResult để bảo đảm lỗi được gắn đúng field.

## 14. Tổng kết

ConversionService là abstraction chuyển đổi kiểu dùng chung của Spring. Nó hỗ trợ kiểm tra khả năng chuyển đổi, thực hiện conversion và tích hợp với các converter tùy chỉnh.

- **DefaultConversionService** cung cấp các converter thông dụng.
- **GenericConversionService** là nền tảng quản lý converter.
- **Converter**, **ConverterFactory**, **GenericConverter** và **ConditionalGenericConverter** đáp ứng các nhu cầu đăng ký khác nhau.
- **TypeDescriptor** giữ metadata generic và annotation khi chỉ dùng Class là chưa đủ.
- **StandardTypeConverter** kết nối ConversionService với SpEL.
- Spring MVC, DataBinder và configuration binding sử dụng conversion trong các quy trình binding tương ứng.
- **Formatter** xử lý parse/print văn bản và thường cần locale; nó bổ sung cho conversion chứ không thay thế mọi converter.

Hãy đăng ký converter cụ thể, nhẹ và có hành vi xác định; cấu hình service trước khi dùng; kiểm thử dữ liệu sai định dạng và các điểm tích hợp thực tế. Khi cần cùng một quy tắc chuyển đổi trong Java, SpEL và binding của Spring, hãy xác định đúng ConversionService tại từng phạm vi để hành vi nhất quán và dễ kiểm soát.