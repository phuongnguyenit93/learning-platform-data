# Custom converter và phạm vi áp dụng trong SpEL

## 1. Vì sao cần custom converter?

Spring Expression Language (SpEL) có thể chuyển đổi giá trị giữa các kiểu dữ liệu trong lúc đánh giá expression. Spring đã hỗ trợ nhiều phép chuyển đổi phổ biến như String sang số, chuyển đổi giữa các kiểu số và String sang enum. Ứng dụng cũng thường có kiểu dữ liệu miền nghiệp vụ riêng như Money, ProductCode hoặc Temperature với quy tắc chuyển đổi cụ thể.

Custom converter định nghĩa cách chuyển một kiểu nguồn sang một kiểu đích. Ví dụ, chuỗi "125.50" có thể được chuyển thành object Money để expression gán vào property, truyền làm đối số method hoặc trả về một kiểu kết quả cụ thể.

SpEL sử dụng một TypeConverter trong EvaluationContext để thực hiện những chuyển đổi cần thiết. StandardEvaluationContext mặc định dùng StandardTypeConverter. StandardTypeConverter có thể làm việc với Spring ConversionService, vì vậy có thể đăng ký converter vào ConversionService rồi gắn service đó vào context mà expression sử dụng.

## 2. Phân biệt Converter, ConversionService và TypeConverter

Ba thành phần có trách nhiệm khác nhau:

| Thành phần | Vai trò |
|---|---|
| Converter<S, T> | Định nghĩa cách chuyển một kiểu nguồn S thành kiểu đích T |
| ConversionService | Quản lý và tìm converter phù hợp cho một cặp kiểu |
| TypeConverter | Giao diện SpEL gọi để chuyển đổi giá trị trong lúc evaluate expression |

Một converter không tự động có hiệu lực trên mọi expression trong toàn bộ JVM. Converter phải được đăng ký vào ConversionService đang được sử dụng, và ConversionService đó phải được nối với TypeConverter của evaluation context hoặc cơ chế Spring đang đánh giá expression.

Trong ứng dụng thông thường, nên dùng StandardTypeConverter làm adapter giữa SpEL và ConversionService. Chỉ triển khai TypeConverter riêng khi cần chính sách chuyển đổi đặc biệt mà ConversionService không đáp ứng.

## 3. Tạo kiểu dữ liệu miền nghiệp vụ

Ví dụ dưới đây dùng kiểu Money làm kiểu đích. Money giữ một giá trị BigDecimal và expose getter để SpEL có thể đọc property:

~~~java
import java.math.BigDecimal;

public class Money {
    private final BigDecimal amount;

    public Money(BigDecimal amount) {
        this.amount = amount;
    }

    public BigDecimal getAmount() {
        return amount;
    }

    @Override
    public String toString() {
        return amount.toPlainString();
    }
}
~~~

Một object Invoice có property Money:

~~~java
public class Invoice {
    private Money amount;

    public Money getAmount() {
        return amount;
    }

    public void setAmount(Money amount) {
        this.amount = amount;
    }
}
~~~

Mục tiêu là cho phép expression nhận một String và gán nó vào property amount có kiểu Money. Java không thể gán String trực tiếp cho Money; custom converter cung cấp bước chuyển đổi đó.

## 4. Viết Converter<S, T>

Spring cung cấp interface Converter<S, T> cho một phép chuyển đổi giữa hai kiểu cụ thể:

~~~java
import java.math.BigDecimal;
import org.springframework.core.convert.converter.Converter;

public class StringToMoneyConverter implements Converter<String, Money> {

    @Override
    public Money convert(String source) {
        if (source == null) {
            return null;
        }

        String normalized = source.trim();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Money value must not be empty");
        }

        return new Money(new BigDecimal(normalized));
    }
}
~~~

Converter nhận String và trả về Money. Việc phân tích chuỗi dùng BigDecimal để giữ độ chính xác thập phân tốt hơn kiểu double.

Một converter nên tập trung vào một phép chuyển đổi có ý nghĩa rõ ràng. Nếu đầu vào không hợp lệ, hãy phát sinh lỗi có thông tin phù hợp thay vì âm thầm trả về giá trị mặc định có thể che giấu dữ liệu sai.

Nếu định dạng nguồn có quy tắc phức tạp như mã tiền tệ, dấu phân cách hàng nghìn hoặc locale, hãy định nghĩa định dạng rõ ràng và kiểm thử các trường hợp đó. Không nên phụ thuộc vào locale mặc định của máy chủ nếu dữ liệu đầu vào cần định dạng ổn định.

## 5. Đăng ký converter vào ConversionService

DefaultConversionService là implementation có sẵn của ConversionService và ConverterRegistry. Có thể tạo instance riêng rồi đăng ký converter:

~~~java
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(new StringToMoneyConverter());

boolean supported =
        conversionService.canConvert(String.class, Money.class);
~~~

Sau khi đăng ký, ConversionService biết cách chuyển String thành Money. Có thể kiểm tra khả năng chuyển đổi bằng canConvert trước khi dùng nếu ứng dụng cần xác nhận cấu hình.

Nên đăng ký converter trong giai đoạn cấu hình ứng dụng, trước khi các expression được đánh giá. Tránh thay đổi danh sách converter liên tục trong lúc xử lý request vì điều đó làm hành vi chuyển đổi khó dự đoán và khó kiểm thử.

Không nên tùy tiện thêm converter vào một shared ConversionService toàn cục chỉ để một expression hoạt động. Dùng instance được quản lý rõ ràng giúp giới hạn nơi converter có hiệu lực và tránh ảnh hưởng ngoài ý muốn đến phần khác của ứng dụng.

## 6. Gắn ConversionService vào StandardEvaluationContext

StandardEvaluationContext dùng một TypeConverter để thực hiện chuyển đổi. Có thể gắn StandardTypeConverter được tạo từ ConversionService vừa cấu hình:

~~~java
import org.springframework.expression.ExpressionParser;
import org.springframework.expression.spel.standard.SpelExpressionParser;
import org.springframework.expression.spel.support.StandardEvaluationContext;
import org.springframework.expression.spel.support.StandardTypeConverter;
import org.springframework.core.convert.support.DefaultConversionService;

DefaultConversionService conversionService =
        new DefaultConversionService();
conversionService.addConverter(new StringToMoneyConverter());

Invoice invoice = new Invoice();

StandardEvaluationContext context =
        new StandardEvaluationContext(invoice);
context.setTypeConverter(new StandardTypeConverter(conversionService));

ExpressionParser parser = new SpelExpressionParser();
parser.parseExpression("amount").setValue(context, "125.50");

Money amount = parser.parseExpression("amount")
        .getValue(context, Money.class);

System.out.println(amount); // 125.50
~~~

Khi gọi setValue, SpEL cần gán một String vào property amount có kiểu Money. TypeConverter của context yêu cầu ConversionService chuyển đổi giá trị trước khi gọi setter.

Parser không sở hữu converter. Cùng một parser có thể đánh giá expression trên nhiều context với chính sách chuyển đổi khác nhau. Converter được dùng phụ thuộc vào TypeConverter của context truyền vào lần đánh giá đó.

## 7. Converter cũng có thể áp dụng cho method argument

SpEL có thể chuyển đổi đối số khi gọi method trên root object hoặc object được tham chiếu từ context. Nếu method yêu cầu Money nhưng expression truyền vào một String literal, custom converter có thể cung cấp kiểu đích:

~~~java
public class PriceFormatter {
    public String describe(Money money) {
        return "Amount: " + money.getAmount().toPlainString();
    }
}
~~~

Đăng ký formatter vào context:

~~~java
StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setVariable("formatter", new PriceFormatter());
context.setTypeConverter(new StandardTypeConverter(conversionService));

Expression expression = parser.parseExpression(
        "#formatter.describe('42.75')");

String description = expression.getValue(context, String.class);

System.out.println(description); // Amount: 42.75
~~~

Method describe nhận Money. Expression cung cấp String, nên SpEL dùng TypeConverter của context để chuyển đối số sang kiểu mà method yêu cầu nếu phép chuyển đổi đó được hỗ trợ.

Cơ chế này hữu ích khi expression gọi method có tham số miền nghiệp vụ. Method vẫn cần có contract rõ ràng và không nên thực hiện side effect bất ngờ khi được gọi trong expression.

## 8. Chuyển đổi kiểu kết quả của expression

Overload getValue(context, TargetType.class) cho phép yêu cầu kiểu kết quả cụ thể. Nếu giá trị expression không có đúng kiểu đích nhưng có thể chuyển đổi, TypeConverter của context có thể thực hiện việc chuyển đổi:

~~~java
Expression expression = parser.parseExpression("'125.50'");

Money amount = expression.getValue(context, Money.class);
~~~

Trong ví dụ này, expression trả về String; SpEL được yêu cầu trả về Money. Kết quả chỉ thành công khi TypeConverter của context có converter String sang Money.

Có thể kiểm tra trực tiếp ConversionService trước:

~~~java
assertTrue(conversionService.canConvert(String.class, Money.class));
~~~

Kiểu kết quả mong đợi nên phản ánh contract của code gọi expression. Nếu một expression lúc trả về String, lúc trả về Money tùy theo nhánh, hãy làm rõ kiểu kết quả và khả năng chuyển đổi thay vì để việc chuyển đổi ngầm trở thành hành vi khó đoán.

## 9. GenericConverter cho nhiều kiểu nguồn và đích

Converter<S, T> phù hợp với một cặp kiểu cụ thể. Khi cần xử lý nhiều cặp kiểu hoặc cần thông tin generic/annotation từ property, có thể dùng GenericConverter.

GenericConverter cung cấp tập ConvertiblePair và nhận TypeDescriptor của nguồn cùng đích:

~~~java
public final class StringToMoneyGenericConverter
        implements GenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Collections.singleton(
                new ConvertiblePair(String.class, Money.class));
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {

        if (source == null) {
            return null;
        }

        return new Money(new BigDecimal(source.toString().trim()));
    }
}
~~~

TypeDescriptor mang thêm thông tin về kiểu và metadata của property, bao gồm generic type và annotation. Điều này hữu ích khi converter cần biết đích là một property cụ thể hoặc một kiểu collection có phần tử được khai báo rõ.

Với một phép chuyển đổi đơn giản String sang Money, Converter<S, T> thường ngắn và dễ đọc hơn. Chỉ chọn GenericConverter khi thông tin kiểu bổ sung hoặc nhiều cặp chuyển đổi thực sự cần thiết.

## 10. ConditionalGenericConverter và điều kiện áp dụng

ConditionalGenericConverter cho phép converter chỉ được chọn khi một điều kiện phù hợp. Ví dụ, cùng một kiểu nguồn/đích có thể có cách chuyển đổi khác nhau tùy annotation trên property đích.

~~~java
public final class AnnotatedMoneyConverter
        implements ConditionalGenericConverter {

    @Override
    public Set<ConvertiblePair> getConvertibleTypes() {
        return Collections.singleton(
                new ConvertiblePair(String.class, Money.class));
    }

    @Override
    public boolean matches(
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return targetType.hasAnnotation(SpecialMoneyFormat.class);
    }

    @Override
    public Object convert(
            Object source,
            TypeDescriptor sourceType,
            TypeDescriptor targetType) {
        return parseSpecialMoney(source.toString());
    }
}
~~~

Đây là cấu trúc minh họa: ứng dụng cần tự định nghĩa annotation, hàm parse và chính sách xử lý lỗi tương ứng. matches quyết định converter có áp dụng cho cặp TypeDescriptor hiện tại hay không.

Conditional converter hữu ích khi phạm vi áp dụng phụ thuộc metadata. Nếu các định dạng khác nhau có ý nghĩa riêng, hãy tách converter hoặc đặt tên điều kiện thật rõ.

## 11. ConverterFactory cho một họ kiểu đích

Nếu một kiểu nguồn có thể chuyển sang nhiều kiểu đích cùng thuộc một họ, Spring cung cấp ConverterFactory<S, R>. Ví dụ điển hình là chuyển String sang các enum khác nhau.

~~~java
public class StringToEnumConverterFactory
        implements ConverterFactory<String, Enum> {

    @Override
    public <T extends Enum> Converter<String, T> getConverter(
            Class<T> targetType) {

        return source -> Enum.valueOf(targetType, source.trim());
    }
}
~~~

Có thể đăng ký factory vào ConversionService:

~~~java
conversionService.addConverterFactory(
        new StringToEnumConverterFactory());
~~~

Spring chọn converter cụ thể dựa trên kiểu enum đích. Factory phù hợp khi logic chuyển đổi dùng chung cho một họ kiểu; nếu chỉ có một kiểu đích riêng, Converter<S, T> đơn giản hơn.

Với dữ liệu enum không khớp tên constant, converter cần xác định cách xử lý chữ hoa/thường, alias và giá trị không hợp lệ. Không nên tự động đoán constant khi điều đó có thể làm thay đổi ý nghĩa dữ liệu.

## 12. Phạm vi áp dụng trong các EvaluationContext

Converter chỉ có hiệu lực trong phạm vi ConversionService được gắn vào TypeConverter của evaluation context đang dùng.

| Nơi đánh giá expression | Converter được dùng |
|---|---|
| StandardEvaluationContext tự tạo | TypeConverter được gắn bằng setTypeConverter |
| Nhiều StandardEvaluationContext dùng chung một ConversionService | Converter trong instance ConversionService dùng chung |
| SimpleEvaluationContext | ConversionService được cấu hình trong builder |
| Expression được Spring BeanFactory đánh giá | ConversionService mà BeanFactory expression resolver sử dụng |
| Một SpEL context khác được tạo độc lập | Chính sách chuyển đổi của context độc lập đó |

Ví dụ hai context có chính sách khác nhau:

~~~java
StandardEvaluationContext moneyContext =
        new StandardEvaluationContext(invoice);
moneyContext.setTypeConverter(
        new StandardTypeConverter(moneyConversionService));

StandardEvaluationContext defaultContext =
        new StandardEvaluationContext(invoice);
~~~

Expression chạy với moneyContext có thể dùng custom converter String sang Money. Expression chạy với defaultContext chỉ dùng TypeConverter mặc định của context đó. Việc đăng ký converter vào một ConversionService không tự động thay đổi các context đã được tạo với một ConversionService khác.

Nếu nhiều context cần cùng quy tắc, hãy tạo một ConversionService dùng chung, cấu hình hoàn chỉnh rồi gắn nó vào từng context phù hợp. Việc chia sẻ cùng instance phải là quyết định cấu hình rõ ràng, không dựa vào giả định rằng mọi parser hoặc mọi context đều tự nhận converter.

## 13. Phạm vi trong ứng dụng Spring được quản lý bởi BeanFactory

Trong ứng dụng Spring, bean factory có thể được cấu hình với một ConversionService. Theo quy ước của Spring, bean ConversionService có tên conversionService có thể được BeanFactory sử dụng cho các chuyển đổi của container. StandardBeanExpressionResolver cũng dùng ConversionService của BeanFactory khi tạo evaluation context cho các expression trong bean definition.

Có thể khai báo một ConversionService chứa custom converter:

~~~java
@Configuration
public class ConversionConfiguration {

    @Bean
    public ConversionService conversionService() {
        DefaultConversionService service =
                new DefaultConversionService();

        service.addConverter(new StringToMoneyConverter());

        return service;
    }
}
~~~

Khi dùng bean factory expression evaluation, việc đăng ký này cho phép các expression được resolver của BeanFactory đánh giá sử dụng ConversionService đã cấu hình. Hành vi cụ thể nên được xác nhận bằng integration test trên cấu hình Spring thực tế của ứng dụng, nhất là khi có nhiều ApplicationContext hoặc nhiều ConversionService.

Một StandardEvaluationContext được tạo thủ công trong code vẫn cần được gắn TypeConverter tương ứng. Đừng giả định rằng chỉ vì ứng dụng có bean ConversionService thì mọi context tự tạo đều tự động sử dụng bean đó.

## 14. Phân biệt với Spring MVC FormatterRegistry

Spring MVC có cơ chế đăng ký converter và formatter riêng thông qua FormatterRegistry, ví dụ trong WebMvcConfigurer.addFormatters. Converter đăng ký ở MVC thường phục vụ data binding và chuyển đổi dữ liệu trong phạm vi MVC.

~~~java
@Configuration
public class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addFormatters(FormatterRegistry registry) {
        registry.addConverter(new StringToMoneyConverter());
    }
}
~~~

Không nên mặc định rằng converter được thêm vào MVC FormatterRegistry sẽ xuất hiện trong mọi StandardEvaluationContext hoặc mọi expression resolver. Phạm vi thực tế phụ thuộc vào ConversionService instance được MVC và BeanFactory sử dụng.

Nếu cần cùng converter cho MVC và SpEL, hãy tổ chức cấu hình để cả hai cơ chế dùng chung ConversionService phù hợp, hoặc đăng ký converter ở từng registry tương ứng. Sau đó viết integration test cho cả luồng MVC data binding và luồng SpEL để xác nhận cấu hình thực sự được chia sẻ như mong muốn.

## 15. SimpleEvaluationContext và conversion service

SimpleEvaluationContext là lựa chọn giới hạn hơn khi expression chỉ cần data binding hoặc truy cập property trong phạm vi cho phép. Builder hỗ trợ cấu hình ConversionService:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadOnlyDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

Nếu cần ghi property, có thể chọn builder đọc/ghi phù hợp:

~~~java
SimpleEvaluationContext context =
        SimpleEvaluationContext.forReadWriteDataBinding()
                .withConversionService(conversionService)
                .build();
~~~

ConversionService ở đây vẫn là nguồn quy tắc chuyển đổi cho context được tạo từ builder. Các giới hạn về property access, method resolution và type access của SimpleEvaluationContext vẫn được áp dụng; thêm converter không tự mở rộng các quyền khác của expression.

Hãy chọn context theo khả năng expression thực sự cần. Nếu chỉ cần đọc/ghi property và chuyển đổi kiểu, SimpleEvaluationContext có thể phù hợp hơn một StandardEvaluationContext có nhiều khả năng hơn mức cần thiết.

## 16. Null, dữ liệu không hợp lệ và lỗi chuyển đổi

Converter nên xác định rõ cách xử lý đầu vào null, chuỗi rỗng và dữ liệu sai định dạng. Đây là ba trường hợp khác nhau:

- Null có thể được xử lý bởi cơ chế chuyển đổi trước khi converter được gọi, tùy đường chuyển đổi.
- Chuỗi rỗng là một String có độ dài bằng 0; converter cần quyết định có chấp nhận hay phát sinh lỗi.
- Chuỗi không hợp lệ, chẳng hạn abc khi cần BigDecimal, nên tạo lỗi có nguyên nhân rõ ràng.

Ví dụ converter Money ở trên từ chối chuỗi rỗng và BigDecimal sẽ từ chối dữ liệu số không hợp lệ. Khi lỗi xảy ra trong lúc evaluate, SpEL có thể bọc lỗi chuyển đổi trong exception thuộc nhánh evaluation. Hãy kiểm tra cause để tìm converter hoặc dữ liệu đầu vào gây lỗi.

Nếu nghiệp vụ cần giá trị mặc định cho null, hãy biểu đạt rõ trong expression hoặc Java thay vì để converter âm thầm đổi mọi đầu vào lỗi thành zero. Ví dụ:

~~~text
#amountText ?: '0.00'
~~~

Sau đó để converter xử lý chuỗi hợp lệ. Việc tách defaulting khỏi conversion giúp từng trách nhiệm rõ ràng và dễ kiểm thử.

## 17. Kiểm thử custom converter và phạm vi áp dụng

Nên kiểm thử converter độc lập, ConversionService sau khi đăng ký, và expression context sử dụng service đó.

Test converter:

~~~java
@Test
void convertsStringToMoney() {
    StringToMoneyConverter converter =
            new StringToMoneyConverter();

    Money result = converter.convert("125.50");

    assertEquals(
            new BigDecimal("125.50"),
            result.getAmount());
}
~~~

Test ConversionService:

~~~java
@Test
void conversionServiceKnowsCustomMoneyConverter() {
    DefaultConversionService service =
            new DefaultConversionService();

    service.addConverter(new StringToMoneyConverter());

    assertTrue(service.canConvert(String.class, Money.class));

    Money result = service.convert("42.75", Money.class);

    assertEquals(new BigDecimal("42.75"), result.getAmount());
}
~~~

Test SpEL context:

~~~java
@Test
void spelUsesCustomConverterWhenSettingRootProperty() {
    DefaultConversionService service =
            new DefaultConversionService();
    service.addConverter(new StringToMoneyConverter());

    Invoice invoice = new Invoice();

    StandardEvaluationContext context =
            new StandardEvaluationContext(invoice);
    context.setTypeConverter(new StandardTypeConverter(service));

    ExpressionParser parser = new SpelExpressionParser();
    parser.parseExpression("amount").setValue(context, "42.75");

    assertEquals(
            new BigDecimal("42.75"),
            invoice.getAmount().getAmount());
}
~~~

Ngoài trường hợp thành công, hãy kiểm tra chuỗi rỗng, dữ liệu sai định dạng, null và context không được gắn custom TypeConverter. Test cuối giúp xác nhận converter chỉ xuất hiện trong đúng phạm vi đã cấu hình.

Nếu converter được dùng qua BeanFactory hoặc Spring MVC, hãy thêm integration test cho đúng cơ chế đó. Unit test một StandardEvaluationContext tự tạo không chứng minh rằng cấu hình MVC hoặc BeanFactory đã nhận cùng ConversionService.

## 18. Lỗi thường gặp

**Chỉ viết Converter nhưng quên đăng ký**

Converter không tự được SpEL phát hiện. Hãy thêm nó vào ConversionService và bảo đảm context dùng TypeConverter kết nối với service đó.

**Đăng ký vào nhầm ConversionService**

Một converter được thêm vào MVC registry hoặc service của một context không nhất thiết áp dụng cho context khác. Kiểm tra chính xác instance mà expression resolver sử dụng.

**Nhầm parser với evaluation context**

Parser tạo Expression từ source. Conversion behavior thuộc TypeConverter của context lúc evaluate hoặc setValue.

**Dùng converter quá rộng**

Một converter áp dụng cho nhiều kiểu có thể thay đổi hành vi của nhiều điểm trong ứng dụng. Giới hạn source/target type và dùng ConditionalGenericConverter khi thật sự cần điều kiện theo metadata.

**Dùng converter để che dữ liệu sai**

Trả về giá trị mặc định cho dữ liệu không hợp lệ có thể khiến lỗi nghiệp vụ khó phát hiện. Hãy phân biệt null, chuỗi rỗng và dữ liệu sai định dạng.

**Giả định MVC converter tự áp dụng cho SpEL**

MVC FormatterRegistry và SpEL EvaluationContext có thể dùng ConversionService khác nhau. Chia sẻ service phải được cấu hình rõ và kiểm thử ở từng luồng.

**Thay đổi registry khi ứng dụng đang chạy**

Đăng ký converter trong giai đoạn cấu hình giúp hành vi ổn định. Tránh thay đổi converter động trong lúc xử lý expression nếu không có thiết kế đồng bộ rõ ràng.

## 19. Khi nào nên dùng loại converter nào?

| Nhu cầu | Lựa chọn |
|---|---|
| Một cặp kiểu nguồn/đích rõ ràng | Converter<S, T> |
| Một họ kiểu đích dùng chung quy tắc | ConverterFactory<S, R> |
| Nhiều cặp kiểu hoặc cần TypeDescriptor | GenericConverter |
| Chỉ áp dụng khi metadata/annotation thỏa điều kiện | ConditionalGenericConverter |
| Chuyển đổi có định dạng và locale | Formatter trong FormattingConversionService |
| Quy tắc chuyển đổi phụ thuộc context nghiệp vụ phức tạp | Method/service Java có tên rõ ràng |

Chọn abstraction nhỏ nhất đáp ứng nhu cầu. Một converter đơn giản dễ đọc, dễ kiểm thử và dễ giới hạn phạm vi hơn một GenericConverter tổng quát không cần thiết.

## 20. Ghi nhớ

- Custom converter định nghĩa phép chuyển đổi giữa kiểu nguồn và kiểu đích.
- SpEL gọi TypeConverter của EvaluationContext khi cần chuyển đổi giá trị.
- StandardTypeConverter là adapter để dùng Spring ConversionService với SpEL.
- Đăng ký converter vào đúng ConversionService mà context hoặc expression resolver đang sử dụng.
- StandardEvaluationContext tự tạo cần được gắn StandardTypeConverter; parser không tự sở hữu converter.
- Converter có thể tham gia chuyển đổi khi setValue, method argument hoặc kiểu kết quả được yêu cầu.
- BeanFactory expression evaluation và MVC data binding có thể dùng ConversionService theo phạm vi cấu hình riêng.
- SimpleEvaluationContext có thể nhận ConversionService qua builder.
- Dùng Converter cho một cặp kiểu, ConverterFactory cho một họ kiểu, GenericConverter khi cần TypeDescriptor và ConditionalGenericConverter khi cần điều kiện áp dụng.
- Kiểm thử converter, service, expression context và từng integration scope riêng biệt.
