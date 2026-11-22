# Chuyển collection hoặc map theo yêu cầu kiểu

Trong Spring Expression Language (SpEL), một biểu thức có thể đọc hoặc cập nhật giá trị collection và Map. Khi giá trị nguồn và kiểu đích khác nhau, Spring có thể dùng **TypeConverter** để chuyển đổi dữ liệu. Cơ chế này dựa trên hạ tầng chuyển đổi kiểu của Spring, đặc biệt là **ConversionService**, và có thể tận dụng thông tin kiểu generic khi thông tin đó được cung cấp bởi property hoặc TypeDescriptor.

Điểm quan trọng là chuyển đổi collection không chỉ là đổi kiểu của container. Ứng dụng có thể cần chuyển từng phần tử của List, hoặc chuyển cả key và value của Map. Kết quả phụ thuộc kiểu đích mà SpEL biết được, converter đã đăng ký và khả năng tạo ra collection hoặc Map đích.

## TypeConverter và ConversionService trong SpEL

**TypeConverter** là abstraction mà SpEL sử dụng khi cần chuyển một giá trị sang kiểu khác. Trong StandardEvaluationContext, converter mặc định là **StandardTypeConverter**, tích hợp với cơ chế chuyển đổi của Spring.

ConversionService cung cấp các converter có sẵn cho nhiều kiểu phổ biến, ví dụ String sang Integer, Boolean hoặc enum; chuyển đổi giữa các kiểu số; và chuyển đổi collection hoặc Map khi có đủ thông tin kiểu nguồn và kiểu đích.

Có thể cấu hình StandardEvaluationContext với ConversionService riêng:

~~~java
ConversionService conversionService =
        new DefaultConversionService();

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
~~~

Trong ví dụ, SpEL dùng StandardTypeConverter được tạo từ ConversionService mà ứng dụng cung cấp. Nếu ứng dụng cần chuyển đổi theo quy tắc riêng, có thể đăng ký thêm Converter hoặc GenericConverter vào một ConfigurableConversionService trước khi gắn nó vào context.

Nếu không có nhu cầu đặc biệt, converter mặc định của StandardEvaluationContext thường đã đáp ứng các chuyển đổi thông dụng. Chỉ tạo conversion service riêng khi ứng dụng cần kiểm soát hoặc mở rộng quy tắc chuyển đổi.

## Chuyển đổi một collection theo kiểu phần tử đích

Giả sử dữ liệu nguồn là List các chuỗi số, nhưng property đích được khai báo là List<Integer>:

~~~java
public class BatchSettings {
    private List<Integer> retryLimits;

    public List<Integer> getRetryLimits() {
        return retryLimits;
    }

    public void setRetryLimits(List<Integer> retryLimits) {
        this.retryLimits = retryLimits;
    }
}
~~~

Có thể dùng SpEL để gán một List<String> vào property này:

~~~java
BatchSettings settings = new BatchSettings();

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("settings", settings);

ExpressionParser parser = new SpelExpressionParser();

List<String> source =
        List.of("2", "5", "8");

Expression expression =
        parser.parseExpression("#settings.retryLimits");

expression.setValue(context, source);
~~~

Property đích có kiểu **List<Integer>**. Khi gán, SpEL lấy thông tin kiểu của property và sử dụng TypeConverter để chuyển các phần tử String thành Integer nếu converter phù hợp. Sau khi gán, danh sách trong settings chứa các số nguyên 2, 5 và 8.

Đây là điểm hữu ích của generic-aware conversion: SpEL không chỉ biết container đích là List mà còn có thể biết kiểu phần tử Integer từ khai báo property Java.

## Chuyển một phần tử trong collection có kiểu generic

Thông tin generic cũng có ích khi cập nhật một phần tử cụ thể. Giả sử property flags được khai báo là List<Boolean>:

~~~java
public class FeatureSettings {
    private List<Boolean> flags =
            new ArrayList<>(List.of(false, false));

    public List<Boolean> getFlags() {
        return flags;
    }

    public void setFlags(List<Boolean> flags) {
        this.flags = flags;
    }
}
~~~

Có thể gán chuỗi vào một phần tử:

~~~java
FeatureSettings settings = new FeatureSettings();

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("settings", settings);

ExpressionParser parser = new SpelExpressionParser();

Expression flagExpression =
        parser.parseExpression("#settings.flags[0]");

flagExpression.setValue(context, "true");
~~~

Property flags có kiểu phần tử Boolean. SpEL có thể dùng metadata generic của property để chuyển chuỗi **"true"** thành Boolean true trước khi ghi vào phần tử. Việc chuyển đổi phụ thuộc converter và accessor đang được sử dụng.

Nếu collection chỉ được khai báo bằng raw type như List mà không có thông tin phần tử, SpEL có thể không biết kiểu đích của từng phần tử. Khi đó, không nên kỳ vọng việc chuyển đổi generic diễn ra giống trường hợp List<Boolean> hoặc List<Integer>.

## Chuyển đổi Map: key và value

Map có hai kiểu generic độc lập: kiểu key và kiểu value. Ví dụ:

~~~java
public class RuntimeConfig {
    private Map<String, Integer> limits;

    public Map<String, Integer> getLimits() {
        return limits;
    }

    public void setLimits(Map<String, Integer> limits) {
        this.limits = limits;
    }
}
~~~

Nếu nguồn là Map<String, String>, có thể gán vào property Map<String, Integer>:

~~~java
RuntimeConfig config = new RuntimeConfig();

StandardEvaluationContext context =
        new StandardEvaluationContext();
context.setVariable("config", config);

Map<String, String> source = Map.of(
        "connectTimeout", "10",
        "readTimeout", "30");

ExpressionParser parser = new SpelExpressionParser();

Expression limitsExpression =
        parser.parseExpression("#config.limits");

limitsExpression.setValue(context, source);
~~~

Khi property metadata được cung cấp đầy đủ, ConversionService có thể chuyển các value từ String sang Integer trong khi giữ key String. Kết quả có kiểu Map<String, Integer>.

Nếu cả key và value đều cần chuyển đổi, chẳng hạn Map<String, String> sang Map<Integer, Boolean>, converter phải có khả năng chuyển từng key và từng value theo kiểu đích. Không nên giả định mọi cặp kiểu đều có converter mặc định.

## TypeDescriptor và generic metadata

Java generic bị type erasure ở runtime, nhưng Spring có **TypeDescriptor** để giữ và truyền thông tin kiểu phong phú hơn, bao gồm kiểu phần tử của collection và kiểu key/value của Map khi metadata có sẵn.

Ví dụ, có thể mô tả kiểu đích của một List<Integer> bằng TypeDescriptor:

~~~java
TypeDescriptor sourceType =
        TypeDescriptor.forObject(source);

TypeDescriptor targetType =
        TypeDescriptor.collection(
                List.class,
                TypeDescriptor.valueOf(Integer.class));

@SuppressWarnings("unchecked")
List<Integer> converted =
        (List<Integer>) conversionService.convert(
                source,
                sourceType,
                targetType);
~~~

Đoạn mã này minh họa trực tiếp ConversionService: kiểu nguồn được suy ra từ object thực tế; kiểu đích mô tả một List có phần tử Integer. ConversionService dùng thông tin đó để chuyển đổi từng phần tử nếu có converter phù hợp.

Với Map, có thể mô tả cả hai kiểu generic:

~~~java
TypeDescriptor mapTargetType =
        TypeDescriptor.map(
                Map.class,
                TypeDescriptor.valueOf(String.class),
                TypeDescriptor.valueOf(Integer.class));
~~~

TypeDescriptor này mô tả Map có key String và value Integer. Có thể dùng overload convert nhận source TypeDescriptor và target TypeDescriptor để yêu cầu chuyển đổi theo cấu trúc kiểu đó.

Trong SpEL, thông tin generic thường đến từ property descriptor, field hoặc vị trí collection mà biểu thức đang cập nhật. Nếu ứng dụng chỉ yêu cầu kết quả bằng **getValue(context, List.class)**, kiểu đích chỉ là raw List; chữ ký Class<List> không mang theo kiểu phần tử generic như List<Integer>. Khi cần chuyển đổi generic rõ ràng, hãy dùng property có khai báo generic, TypeDescriptor hoặc thực hiện conversion trực tiếp qua ConversionService.

## Chuyển đổi kết quả collection và projection

Selection và projection là các collection operation của SpEL:

- **Selection .?[condition]** lọc phần tử thỏa điều kiện.
- **Projection .![expression]** tính một giá trị cho từng phần tử và thu thập kết quả.

Ví dụ, lấy tên từ các Product:

~~~java
Expression expression =
        parser.parseExpression("#products.![name]");

List<?> names =
        expression.getValue(context, List.class);
~~~

Projection tạo một List kết quả từ các giá trị name. Nếu name là String, các phần tử kết quả là String. Tuy nhiên, yêu cầu kiểu **List.class** chỉ cho biết container là List, không khai báo kiểu generic của phần tử ở chữ ký Java.

Nếu cần chuyển kết quả projection sang List<Integer> hoặc một kiểu phần tử khác, hãy xác định rõ kiểu đích và sử dụng ConversionService với TypeDescriptor phù hợp, hoặc gán kết quả vào một property có khai báo generic tương ứng. Không nên dựa vào raw Class để suy luận rằng mọi phần tử đã được chuyển đổi.

## Chuyển đổi collection giữa các kiểu container

ConversionService có thể hỗ trợ chuyển đổi giữa những loại collection khác nhau nếu có converter phù hợp và kiểu đích có thể được tạo. Ví dụ, dữ liệu nguồn có thể là Set<String> trong khi property đích là List<Integer>.

~~~java
public class ImportSettings {
    private List<Integer> ids;

    public List<Integer> getIds() {
        return ids;
    }

    public void setIds(List<Integer> ids) {
        this.ids = ids;
    }
}
~~~

~~~java
ImportSettings settings = new ImportSettings();

context.setVariable("settings", settings);

Set<String> source = new LinkedHashSet<>(
        List.of("101", "102", "103"));

parser.parseExpression("#settings.ids")
        .setValue(context, source);
~~~

Nếu các converter cần thiết có sẵn, SpEL có thể chuyển container và từng phần tử theo kiểu property đích. Thứ tự phần tử của collection kết quả phụ thuộc kiểu container được tạo và thứ tự duyệt của nguồn. Nếu thứ tự là yêu cầu nghiệp vụ, hãy chọn cấu trúc nguồn/đích phù hợp và kiểm tra hành vi converter được dùng.

Không phải mọi collection implementation đều có thể được tạo hoặc chuyển đổi tự động. Một kiểu đích đặc biệt, collection chỉ đọc hoặc collection không có constructor phù hợp có thể yêu cầu converter riêng hoặc logic chuyển đổi trong Java.

## Đăng ký Converter tùy chỉnh

Khi kiểu dữ liệu nghiệp vụ không được converter mặc định hỗ trợ, có thể đăng ký Converter riêng:

~~~java
public class RegionCode {
    private final String value;

    public RegionCode(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

~~~java
DefaultConversionService conversionService =
        new DefaultConversionService();

conversionService.addConverter(
        String.class,
        RegionCode.class,
        RegionCode::new);

StandardEvaluationContext context =
        new StandardEvaluationContext();

context.setTypeConverter(
        new StandardTypeConverter(conversionService));
~~~

Sau khi đăng ký, một property đích kiểu RegionCode có thể nhận dữ liệu String nếu SpEL thực hiện conversion qua context này. Với collection có phần tử RegionCode, converter String-to-RegionCode có thể được áp dụng cho từng phần tử khi metadata generic của kiểu đích được cung cấp.

Nếu chuyển đổi phụ thuộc nhiều thông tin ngoài giá trị nguồn, chẳng hạn locale, tenant hoặc cấu hình runtime, hãy cân nhắc **ConverterFactory**, **GenericConverter** hoặc **ConditionalGenericConverter** phù hợp. Các abstraction này cho phép mô tả conversion phức tạp hơn converter một nguồn-một đích đơn giản.

Converter nên có hợp đồng rõ ràng, xử lý input không hợp lệ nhất quán và tránh side effect. Chuyển đổi kiểu thường được gọi ở nhiều nơi trong ứng dụng; không nên để một converter âm thầm ghi dữ liệu hoặc truy cập tài nguyên bên ngoài.

## Sử dụng ConversionService trực tiếp khi cần kiểm soát chi tiết

Không phải mọi chuyển đổi đều cần được viết trong biểu thức SpEL. Nếu logic cần chuyển collection phức tạp, cần kiểm tra lỗi từng phần tử hoặc cần quyết định cách xử lý phần tử không hợp lệ, có thể gọi ConversionService trong Java:

~~~java
TypeDescriptor sourceDescriptor =
        TypeDescriptor.forObject(source);

TypeDescriptor targetDescriptor =
        TypeDescriptor.map(
                Map.class,
                TypeDescriptor.valueOf(String.class),
                TypeDescriptor.valueOf(Integer.class));

Object converted = conversionService.convert(
        source,
        sourceDescriptor,
        targetDescriptor);
~~~

Cách này giúp chỉ định kiểu key và value đích một cách tường minh. Ứng dụng cũng có thể bắt lỗi chuyển đổi ở một vị trí rõ ràng và trả về thông báo phù hợp với nghiệp vụ.

SpEL phù hợp với biểu thức ngắn tại điểm cấu hình hoặc tích hợp. Nếu chuyển đổi cần nhiều bước, log chi tiết, bỏ qua một số phần tử hoặc tổng hợp lỗi, Java thường dễ kiểm soát hơn.

## Lỗi chuyển đổi và cách chẩn đoán

Một biểu thức có thể parse thành công nhưng thất bại khi đánh giá vì không chuyển đổi được collection, key, value hoặc phần tử. Các nguyên nhân thường gặp:

- Không có Converter cho kiểu nguồn và kiểu đích.
- Chuỗi nguồn không có định dạng hợp lệ, ví dụ **"abc"** không thể chuyển thành Integer.
- Property đích có kiểu generic khác với dữ liệu thực tế.
- Map key hoặc value không thể chuyển sang kiểu đích.
- Collection đích không thể được khởi tạo hoặc không hỗ trợ thao tác cần thiết.
- Converter tùy chỉnh phát sinh exception khi xử lý dữ liệu.

Có thể tách lỗi parse và evaluation:

~~~java
Expression expression;

try {
    expression = parser.parseExpression("#settings.retryLimits");
} catch (ParseException ex) {
    throw new IllegalArgumentException("Invalid SpEL syntax", ex);
}

try {
    expression.setValue(context, List.of("2", "5", "invalid"));
} catch (EvaluationException ex) {
    throw new IllegalArgumentException(
            "Cannot convert the supplied collection", ex);
}
~~~

ParseException cho biết chuỗi biểu thức sai cú pháp. EvaluationException cho biết biểu thức không thể thực hiện trên context hoặc dữ liệu hiện tại; lỗi chuyển đổi có thể xuất hiện bên trong nhóm này, thường kèm nguyên nhân chi tiết từ ConversionService.

Khi xử lý lỗi, nên xác định phần tử hoặc entry nào không hợp lệ và kiểu đích được yêu cầu. Không nên thay mọi lỗi chuyển đổi bằng một collection rỗng vì điều đó có thể che giấu dữ liệu đầu vào sai.

## Null trong collection và Map

Collection hoặc Map có thể chứa phần tử null, key null hoặc value null tùy implementation. ConversionService không thể chuyển một giá trị null thành mọi kiểu đích theo cùng một cách; kết quả phụ thuộc converter và quy tắc null của kiểu đích.

Ví dụ, một List<String> có phần tử null khi chuyển sang List<Integer> cần chính sách rõ ràng: giữ null nếu kiểu đích cho phép, từ chối dữ liệu hoặc thay bằng giá trị mặc định theo nghiệp vụ. Với Map, cần xem riêng key và value null.

Nếu null không được phép, hãy xác thực nguồn trước khi gọi SpEL hoặc ConversionService. Nếu null hợp lệ, kiểm tra converter và target collection thực tế thay vì giả định conversion sẽ tự loại bỏ phần tử null.

## Giới hạn của SimpleEvaluationContext

**SimpleEvaluationContext** cung cấp một tập con khả năng của SpEL dành cho data binding và cho phép ứng dụng kiểm soát việc đọc/ghi property. Nó không cung cấp toàn bộ tính năng của StandardEvaluationContext, ví dụ type reference, constructor invocation và bean reference.

Nếu use case cần chuyển collection hoặc Map khi gán property, cần bảo đảm context có TypeConverter phù hợp và property accessor hỗ trợ thao tác. Với StandardEvaluationContext, có thể cấu hình rõ StandardTypeConverter như các ví dụ trên. Với SimpleEvaluationContext, hãy dùng builder và các khả năng được phiên bản Spring đang dùng hỗ trợ; không giả định mọi tính năng của StandardEvaluationContext đều có sẵn.

Read-only data binding cũng không có nghĩa collection được trả về tự động immutable. Chính sách chuyển đổi kiểu và quyền ghi property là hai vấn đề riêng; collection nguồn và collection kết quả vẫn có mutability theo implementation Java của chúng.

## Quy tắc thực hành

- Khai báo property collection và Map với generic cụ thể như **List<Integer>** hoặc **Map<String, Boolean>** khi kiểu phần tử có ý nghĩa.
- Dùng TypeDescriptor khi cần mô tả rõ kiểu phần tử, key và value đích.
- Dùng StandardTypeConverter gắn với ConversionService phù hợp cho các biểu thức cần conversion.
- Đăng ký Converter tùy chỉnh cho kiểu nghiệp vụ chưa được hỗ trợ.
- Không kỳ vọng **getValue(context, List.class)** tự mang thông tin generic của phần tử.
- Kiểm tra dữ liệu nguồn, null và định dạng trước khi chuyển đổi.
- Nếu cần kiểm soát chi tiết từng lỗi hoặc quy tắc nhiều bước, thực hiện conversion trong Java.
- Không coi read-only EvaluationContext là cơ chế làm collection trở thành immutable.

## Kết luận

SpEL dùng **TypeConverter** để chuyển giá trị theo kiểu mà biểu thức hoặc vị trí đích yêu cầu. StandardEvaluationContext mặc định tích hợp StandardTypeConverter; ứng dụng có thể cung cấp ConversionService riêng và đăng ký converter bổ sung. Với collection và Map, thông tin generic giúp chuyển đổi từng phần tử, key hoặc value khi kiểu đích được biết thông qua property metadata hoặc TypeDescriptor.

Muốn chuyển List<String> thành List<Integer> hoặc Map<String, String> thành Map<String, Integer>, hãy khai báo kiểu đích rõ ràng và bảo đảm có converter phù hợp. Đừng dựa vào raw List.class để suy luận kiểu phần tử. Khi chuyển đổi phức tạp hoặc cần xử lý lỗi chi tiết, hãy dùng ConversionService trực tiếp trong Java để kiểm soát đầu vào, kiểu đích và kết quả.
