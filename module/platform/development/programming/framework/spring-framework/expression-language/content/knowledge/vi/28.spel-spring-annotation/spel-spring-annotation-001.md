# SpEL trong @Value trong Spring Framework

Spring cung cấp annotation @Value để đưa giá trị cấu hình hoặc kết quả của một biểu thức vào field, tham số constructor, tham số phương thức hay setter. Khi nội dung được viết trong cặp dấu ngoặc nhọn và ký hiệu thăng, Spring đánh giá nó bằng Spring Expression Language (SpEL).

Ví dụ, biểu thức sau tính một giá trị số:

~~~java
@Value("#{2 * T(java.lang.Math).PI}")
private double circleConstant;
~~~

Biểu thức lấy hằng số PI của java.lang.Math rồi nhân với 2. Spring chuyển kết quả sang kiểu double của field.

SpEL trong @Value còn có thể đọc property, gọi bean, thực hiện phép tính, chọn giá trị mặc định và tạo collection. Bài này trình bày cú pháp, các kiểu giá trị thường dùng, cách kết hợp với property placeholder, cách Spring chuyển đổi kiểu và những lỗi cần tránh.

## 1. @Value và ba dạng giá trị

@Value có thể nhận giá trị theo ba cách thường gặp:

| Dạng | Ví dụ | Ý nghĩa |
|---|---|---|
| Giá trị literal | @Value("Spring") | Đưa chuỗi literal vào điểm inject. |
| Property placeholder | @Value("${app.name:Demo}") | Đọc property từ cấu hình bên ngoài; phần sau dấu hai chấm là mặc định nếu key chưa có giá trị. |
| SpEL expression | @Value("#{2 * 3}") | Đánh giá biểu thức SpEL rồi inject kết quả. |

Ví dụ:

~~~java
@Component
public class AppSettings {

    @Value("Spring")
    private String label;

    @Value("${app.name:Demo}")
    private String applicationName;

    @Value("#{2 * 3}")
    private int batchSize;
}
~~~

Dấu phân cách rất quan trọng:

- ${...} là cú pháp property placeholder.
- #{...} là cú pháp SpEL expression.
- Một chuỗi không có hai dạng trên thường được xử lý như giá trị literal.

Không nên nhầm placeholder với SpEL. Placeholder tìm giá trị cấu hình theo key; SpEL phân tích và đánh giá một biểu thức.

## 2. Cú pháp SpEL trong @Value

Một SpEL expression trong @Value thường có dạng:

~~~java
@Value("#{expression}")
private SomeType value;
~~~

Phần bên trong #{...} là biểu thức SpEL. Nó có thể là literal, phép toán, truy cập property, gọi method, tham chiếu bean hoặc kết hợp nhiều thao tác.

Ví dụ:

~~~java
@Value("#{10 + 5}")
private int limit;

@Value("#{T(java.lang.Math).max(10, 20)}")
private int maximum;

@Value("#{ 'Hello ' + 'Spring' }")
private String greeting;
~~~

Spring đánh giá biểu thức trong quá trình xử lý dependency injection. Kết quả sau đó được cung cấp cho field hoặc tham số tương ứng.

SpEL không yêu cầu mọi biểu thức phải trả về cùng kiểu với vị trí inject. Spring có thể dùng ConversionService hoặc cơ chế chuyển đổi của context để chuyển kết quả sang kiểu đích nếu có converter phù hợp.

## 3. Inject bằng constructor, field và setter

@Value có thể được dùng tại nhiều điểm inject. Constructor injection thường làm dependency và cấu hình hiện rõ ngay khi tạo đối tượng.

### 3.1. Constructor parameter

~~~java
@Component
public class CheckoutSettings {

    private final String currency;
    private final int retryLimit;

    public CheckoutSettings(
            @Value("#{ 'VND' }") String currency,
            @Value("#{2 + 3}") int retryLimit) {
        this.currency = currency;
        this.retryLimit = retryLimit;
    }

    public String getCurrency() {
        return currency;
    }

    public int getRetryLimit() {
        return retryLimit;
    }
}
~~~

Trong ví dụ, Spring đánh giá từng biểu thức rồi truyền kết quả vào constructor. Các field được gán trong constructor và có thể khai báo final.

### 3.2. Field injection

~~~java
@Component
public class FeatureSettings {

    @Value("#{true}")
    private boolean checkoutEnabled;

    @Value("#{100 * 2}")
    private int maximumItems;

    public boolean isCheckoutEnabled() {
        return checkoutEnabled;
    }

    public int getMaximumItems() {
        return maximumItems;
    }
}
~~~

Field injection ngắn gọn nhưng giá trị chỉ có sau khi Spring xử lý bean. Không nên đọc field được inject trong constructor của chính bean vì quá trình inject field diễn ra sau khi constructor chạy.

### 3.3. Setter hoặc method parameter

~~~java
@Component
public class ReportSettings {

    private String reportTitle;

    @Value("#{ 'Monthly report' }")
    public void setReportTitle(String reportTitle) {
        this.reportTitle = reportTitle;
    }
}
~~~

Spring đánh giá biểu thức và gọi setter với kết quả. Có thể dùng @Value trên tham số của phương thức được Spring quản lý, chẳng hạn tham số của một phương thức @Bean.

## 4. Truy cập property và phép toán

SpEL có thể đọc property của root object hoặc property được cung cấp trong evaluation context. Trong @Value, Spring chuẩn bị context phù hợp với cơ chế tích hợp.

Một số ví dụ:

~~~java
@Value("#{systemProperties['user.language']}")
private String language;

@Value("#{systemEnvironment['JAVA_HOME']}")
private String javaHome;

@Value("#{2 * 60 * 1000}")
private long timeoutMillis;
~~~

Có thể kết hợp toán tử số học, so sánh và logic:

~~~java
@Value("#{10 + 5}")
private int total;

@Value("#{100 > 50}")
private boolean thresholdReached;

@Value("#{true and (5 < 10)}")
private boolean enabled;
~~~

Khi biểu thức dài, hãy dùng ngoặc để thể hiện thứ tự tính toán. Một biểu thức cấu hình nên ngắn, có ý nghĩa rõ ràng và dễ kiểm tra.

## 5. Tham chiếu bean trong @Value

SpEL có thể tham chiếu bean do Spring container quản lý bằng ký hiệu @ trước tên bean.

Ví dụ, giả sử ứng dụng có bean pricingService với property defaultCurrency:

~~~java
@Component
public class CheckoutSettings {

    private final String currency;

    public CheckoutSettings(
            @Value("#{ @pricingService.defaultCurrency }")
            String currency) {
        this.currency = currency;
    }
}
~~~

Có thể gọi method của bean nếu method phù hợp với biểu thức:

~~~java
@Value("#{ @pricingService.defaultTaxRate() }")
private BigDecimal taxRate;
~~~

Hoặc truyền đối số:

~~~java
@Value("#{ @pricingService.rateFor('VN') }")
private BigDecimal vietnamRate;
~~~

Bean phải tồn tại trong ApplicationContext đang xử lý @Value và tên tham chiếu phải khớp tên bean hoặc alias. Nếu bean không được phân giải, việc đánh giá biểu thức sẽ thất bại.

Không nên gọi method có tác dụng phụ trong @Value. Giá trị cấu hình nên có kết quả xác định và không làm thay đổi trạng thái ứng dụng khi bean được khởi tạo.

## 6. Dùng static method và type reference

SpEL dùng toán tử T(...) để tham chiếu một kiểu Java. Sau đó có thể truy cập hằng số static hoặc gọi static method.

Ví dụ:

~~~java
@Value("#{T(java.lang.Math).PI}")
private double pi;

@Value("#{T(java.lang.Math).max(12, 30)}")
private int maximum;

@Value("#{T(java.util.Locale).ROOT.toString()}")
private String rootLocale;
~~~

Type reference hữu ích khi cần hằng số hoặc phép tính có sẵn trong thư viện Java. Chỉ dùng các kiểu và method cần thiết; biểu thức cấu hình không nên trở thành nơi thực hiện logic phức tạp.

Nếu ứng dụng cần logic nghiệp vụ có thể kiểm thử độc lập, hãy chuyển logic đó sang một bean/service rồi tham chiếu bean từ biểu thức hoặc inject dependency trực tiếp.

## 7. Property placeholder và SpEL có thể kết hợp

Placeholder ${...} lấy dữ liệu từ property source. SpEL #{...} đánh giá kết quả. Trong các môi trường Spring có cấu hình embedded value resolution, placeholder có thể được phân giải trước khi biểu thức SpEL được đánh giá.

Ví dụ, property app.timeout-seconds cung cấp số giây; biểu thức nhân giá trị đó với 1000 để tạo milliseconds:

~~~java
@Value("#{${app.timeout-seconds:30} * 1000}")
private long timeoutMillis;
~~~

Nếu property không được khai báo, placeholder dùng mặc định 30. Sau đó SpEL thực hiện phép nhân.

Có thể dùng placeholder đơn thuần khi chỉ cần lấy cấu hình:

~~~java
@Value("${app.name:Demo}")
private String applicationName;
~~~

Nên dùng placeholder cho các giá trị phụ thuộc môi trường như URL, tên ứng dụng, timeout hoặc feature configuration. Chỉ thêm SpEL khi thực sự cần tính toán hoặc truy cập dữ liệu khác.

Cú pháp kết hợp cần được kiểm tra trong cấu hình ứng dụng thực tế, đặc biệt khi giá trị property chứa ký tự đặc biệt hoặc bản thân giá trị cần được diễn giải như biểu thức.

## 8. Giá trị mặc định và toán tử Elvis

Có hai cách thường dùng để cung cấp giá trị mặc định.

### 8.1. Mặc định của property placeholder

~~~java
@Value("${app.region:unknown}")
private String region;
~~~

Nếu property app.region không được tìm thấy hoặc không có giá trị được cung cấp theo cơ chế placeholder, phần sau dấu hai chấm là giá trị mặc định.

### 8.2. Toán tử Elvis trong SpEL

Toán tử Elvis ?: chọn vế phải khi vế trái là null hoặc chuỗi rỗng. Nếu vế trái có giá trị hợp lệ, biểu thức giữ nguyên giá trị đó.

~~~java
@Value("#{systemProperties['app.region'] ?: 'unknown'}")
private String region;
~~~

Có thể dùng Elvis với property của bean:

~~~java
@Value("#{ @applicationSettings.region ?: 'unknown' }")
private String region;
~~~

Trong ví dụ, nếu property region trả về null hoặc chuỗi rỗng thì kết quả là unknown.

Hãy phân biệt hai cơ chế: placeholder default xử lý trường hợp property key chưa có giá trị; Elvis xử lý giá trị được đánh giá bởi SpEL. Nếu cần phân biệt null, chuỗi rỗng và chuỗi chỉ chứa khoảng trắng, hãy viết logic rõ ràng cho từng trường hợp.

## 9. Safe navigation và xử lý null

Khi một property có thể null, truy cập property tiếp theo có thể gây lỗi. SpEL cung cấp safe navigation operator ?. để dừng chuỗi truy cập và trả về null khi đối tượng bên trái là null.

Ví dụ:

~~~java
@Value("#{ @applicationSettings.contact?.email }")
private String contactEmail;
~~~

Nếu contact null, biểu thức trả về null thay vì cố truy cập email trên null.

Có thể kết hợp với Elvis để cung cấp mặc định:

~~~java
@Value("#{ @applicationSettings.contact?.email ?: 'support@example.com' }")
private String contactEmail;
~~~

Safe navigation chỉ bảo vệ đoạn truy cập mà nó áp dụng. Nếu biểu thức gọi method hoặc truy cập property khác có thể null, hãy kiểm tra từng vị trí cần thiết.

Cũng cần phân biệt object null với bean không tồn tại. Safe navigation không tự tạo ra bean hoặc xử lý mọi lỗi phân giải bean; tên bean vẫn phải được container phân giải theo cấu hình.

## 10. Inline collection trong @Value

SpEL hỗ trợ tạo list và map trực tiếp trong biểu thức. Điều này hữu ích khi cần inject một tập giá trị cố định.

Ví dụ List:

~~~java
@Value("#{ {'reader', 'editor', 'admin'} }")
private List<String> roles;
~~~

Ví dụ Map:

~~~java
@Value("#{ {'maxAttempts': 3, 'enabled': true} }")
private Map<String, Object> options;
~~~

Các phần tử trong inline collection được đánh giá theo kiểu của từng biểu thức. Với list hoặc map không đồng nhất, hãy chọn kiểu nhận tổng quát phù hợp và tránh giả định mọi phần tử có cùng kiểu.

Có thể tạo mảng hoặc collection đích khi kiểu đích và cơ chế chuyển đổi hỗ trợ. Nếu ứng dụng yêu cầu một generic type cụ thể, nên kiểm tra kết quả và kiểu phần tử thay vì dựa vào phép ép kiểu không kiểm chứng.

## 11. Chuyển đổi kiểu kết quả

Kết quả của SpEL có thể là String, Boolean, số, collection hoặc object. Spring chuyển đổi kết quả sang kiểu đích của field hoặc tham số nếu có converter phù hợp.

Ví dụ:

~~~java
@Value("#{ '42' }")
private int maximumItems;

@Value("#{ 'true' }")
private boolean enabled;

@Value("#{2 * 60}")
private long timeoutSeconds;
~~~

Các ví dụ trên yêu cầu Spring chuyển đổi giá trị sang kiểu field. Với kiểu phức tạp, cần đảm bảo ConversionService có converter phù hợp.

Ví dụ inject Duration trực tiếp từ một biểu thức trả về Duration:

~~~java
@Value("#{T(java.time.Duration).ofSeconds(30)}")
private Duration cacheTtl;
~~~

Khi kiểu không tương thích hoặc không có converter phù hợp, Spring có thể báo lỗi trong quá trình tạo bean. Hãy kiểm tra kiểu thực tế của biểu thức và kiểu đích trước khi triển khai.

## 12. Thời điểm đánh giá và tính ổn định của giá trị

@Value được xử lý trong quá trình Spring tạo và inject bean. Kết quả biểu thức trở thành giá trị được inject vào field hoặc tham số tại thời điểm đó.

Ví dụ:

~~~java
@Value("#{T(java.lang.System).currentTimeMillis()}")
private long createdAt;
~~~

Biểu thức được đánh giá khi giá trị được inject. Field không tự cập nhật mỗi khi thời gian thay đổi.

Tương tự, nếu @Value đọc property từ bean khác, kết quả thường là giá trị được lấy trong quá trình inject. Nó không tự động trở thành một liên kết reactive với property của bean nguồn.

Nếu cần giá trị luôn mới, hãy inject dependency và gọi method khi cần, hoặc dùng cơ chế cấu hình động phù hợp với kiến trúc ứng dụng. Đừng dùng @Value như một cơ chế theo dõi thay đổi liên tục.

## 13. Dùng @Value trên tham số @Bean

Java configuration cho phép Spring inject giá trị vào tham số của phương thức @Bean:

~~~java
@Configuration
public class ApplicationConfiguration {

    @Bean
    public RetryPolicy retryPolicy(
            @Value("${app.retry-limit:3}") int retryLimit,
            @Value("#{2 * 1000}") long delayMillis) {
        return new RetryPolicy(retryLimit, delayMillis);
    }
}
~~~

Spring giải quyết placeholder và SpEL rồi truyền kết quả vào phương thức tạo bean. Cách này giữ cấu hình gần nơi bean được khai báo.

Nếu một bean cần dependency khác để thực hiện chức năng, ưu tiên khai báo dependency trực tiếp bằng tham số phương thức @Bean hoặc constructor. Dùng @Value cho giá trị cấu hình hoặc kết quả biểu thức phù hợp.

## 14. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Dùng placeholder khi muốn tính toán | Placeholder chỉ tra cứu property. | Dùng #{...} cho biểu thức SpEL. |
| Dùng #{...} khi chỉ cần đọc cấu hình | Biểu thức làm cấu hình phức tạp hơn cần thiết. | Dùng placeholder với key và default. |
| Quên dấu ngoặc nhọn hoặc dấu thăng | Spring không nhận diện đúng vùng SpEL. | Kiểm tra cú pháp #{expression}. |
| Bean reference không tồn tại | Tên bean sai hoặc bean không thuộc context hiện tại. | Kiểm tra bean name, alias và ApplicationContext. |
| Property lồng nhau có thể null | Truy cập tiếp trên null gây lỗi. | Dùng safe navigation và default phù hợp. |
| Giá trị không chuyển đổi được | Kiểu biểu thức không tương thích kiểu đích. | Chọn kiểu literal phù hợp hoặc cấu hình converter. |
| Gọi method có tác dụng phụ | Việc tạo bean có thể gây thay đổi trạng thái ngoài dự kiến. | Ưu tiên biểu thức thuần và getter/method chỉ đọc. |
| Mong field tự cập nhật sau inject | @Value cung cấp giá trị tại thời điểm xử lý bean. | Dùng dependency và truy vấn giá trị khi cần. |
| Dùng biểu thức quá dài | Logic khó đọc và khó kiểm thử. | Chuyển logic sang bean chuyên trách hoặc mã Java. |
| Đưa biểu thức do người dùng kiểm soát vào @Value | Có thể mở rộng hành vi đánh giá ngoài dự kiến. | Chỉ dùng biểu thức cấu hình đáng tin cậy và giới hạn nguồn đầu vào. |

Khi chẩn đoán, phân biệt lỗi placeholder resolution, lỗi parse SpEL, lỗi đánh giá biểu thức, lỗi tìm bean và lỗi chuyển đổi kiểu. Xem thông báo exception và vị trí inject để xác định giai đoạn thất bại.

## 15. Nguyên tắc sử dụng

1. Dùng placeholder cho cấu hình theo môi trường và dùng SpEL khi cần tính toán hoặc truy cập đối tượng.
2. Ưu tiên constructor injection để làm giá trị cấu hình và dependency hiện rõ.
3. Dùng tên bean và property rõ ràng khi tham chiếu bean.
4. Dùng Elvis hoặc placeholder default khi có giá trị thay thế hợp lý.
5. Xử lý null ở từng cấp của property path.
6. Chọn kiểu đích tương thích với kết quả và kiểm tra converter khi cần.
7. Giữ biểu thức ngắn, dễ đọc; chuyển logic nghiệp vụ phức tạp sang Java.
8. Không dùng @Value để gọi method có tác dụng phụ hoặc thực hiện thao tác ghi.
9. Không đánh giá biểu thức không đáng tin cậy hoặc được ghép trực tiếp từ dữ liệu người dùng.
10. Nhớ rằng giá trị được inject tại thời điểm xử lý bean, không tự cập nhật liên tục.

## 16. Ghi nhớ

- @Value("#{...}") yêu cầu Spring đánh giá biểu thức SpEL.
- ${...} là property placeholder; #{...} là SpEL.
- SpEL trong @Value có thể dùng literal, toán tử, property, method, bean reference và type reference.
- Có thể inject bằng constructor parameter, field, setter hoặc tham số phương thức @Bean.
- Toán tử Elvis ?: hỗ trợ giá trị thay thế khi kết quả là null hoặc chuỗi rỗng.
- Safe navigation ?. giúp tránh truy cập property trên object null.
- Inline list và map có thể được tạo trực tiếp trong biểu thức.
- Spring chuyển đổi kết quả sang kiểu đích nếu có converter phù hợp.
- @Value được đánh giá trong quá trình inject bean; field không tự cập nhật khi nguồn thay đổi.
- Giữ biểu thức cấu hình rõ ràng, ngắn gọn và có nguồn đáng tin cậy.
