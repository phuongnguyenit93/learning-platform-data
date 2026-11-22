# SpEL trong điều kiện cấu hình và thuộc tính bean

Spring cho phép dùng SpEL trong nhiều điểm cấu hình để tính giá trị cho thuộc tính bean hoặc quyết định một cấu hình có được áp dụng hay không. Trong annotation, hai cách thường gặp là dùng @Value với biểu thức SpEL và dùng @ConditionalOnExpression trong Spring Boot để quyết định có đăng ký bean hay không.

Khi đọc cấu hình, cần phân biệt property placeholder với SpEL. Placeholder lấy giá trị từ nguồn cấu hình theo tên property; SpEL phân tích và đánh giá một biểu thức có thể truy cập object, gọi method, thực hiện phép toán hoặc đọc bean. Hai cơ chế có thể kết hợp, nhưng chúng có cú pháp và thời điểm xử lý khác nhau.

## 1. Dùng SpEL trong @Value

Annotation @Value hỗ trợ biểu thức SpEL được đặt trong cặp dấu phân cách #{}. Spring đánh giá biểu thức rồi gán kết quả vào field, tham số constructor hoặc tham số method phù hợp.

Ví dụ:

~~~java
@Component
public class AppInfo {

    @Value("#{ 'Spring Framework' }")
    private String productName;

    @Value("#{2 * 3}")
    private int workerCount;

    @Value("#{T(java.lang.Math).PI}")
    private double pi;
}
~~~

Biểu thức đầu trả về chuỗi. Biểu thức thứ hai thực hiện phép nhân. Biểu thức thứ ba tham chiếu static field PI thông qua type reference T(...).

SpEL không chỉ đọc một property đã có. Nó có thể tính toán giá trị từ literal, biến, property, method hoặc bean reference mà EvaluationContext của Spring cho phép truy cập.

Hãy dùng @Value khi giá trị cần inject có thể được biểu diễn gọn bằng một biểu thức. Nếu phép tính chứa nhiều quy tắc nghiệp vụ hoặc cần xử lý lỗi phức tạp, hãy chuyển logic sang một bean hoặc method có tên rõ ràng rồi inject kết quả cần thiết.

## 2. Phân biệt property placeholder và SpEL

Property placeholder và SpEL có mục đích khác nhau:

| Cú pháp | Cơ chế | Mục đích |
|---|---|---|
| ${app.name} | Property placeholder | Lấy giá trị property từ Environment hoặc nguồn cấu hình |
| #{2 * 3} | SpEL | Đánh giá biểu thức |
| #{${app.limit:10} * 2} | Placeholder kết hợp SpEL | Lấy property, sau đó dùng giá trị trong biểu thức |

Ví dụ placeholder:

~~~java
@Value("${app.name:Spring}")
private String appName;
~~~

Spring tìm property app.name. Nếu không có, giá trị mặc định Spring được dùng.

Ví dụ SpEL:

~~~java
@Value("#{2 * 3}")
private int limit;
~~~

Ở đây không đọc property bên ngoài; Spring đánh giá biểu thức số học và inject kết quả 6.

Có thể kết hợp hai cơ chế:

~~~java
@Value("#{${app.limit:10} * 2}")
private int doubledLimit;
~~~

Placeholder được phân giải trước để thay thế giá trị app.limit, sau đó phần nằm trong #{} được đánh giá như SpEL. Nếu app.limit có giá trị 15, kết quả inject là 30.

Không nên nhầm dấu phân cách. Dùng ${...} khi chỉ cần đọc property cấu hình; dùng #{...} khi cần đánh giá biểu thức. Chỉ kết hợp khi thật sự cần thực hiện phép tính hoặc truy cập object trên giá trị property.

## 3. Dùng placeholder cho cấu hình đơn giản

Với giá trị cấu hình đơn giản, placeholder thường là lựa chọn rõ ràng nhất:

~~~java
@Component
public class MailSettings {

    @Value("${mail.host:localhost}")
    private String host;

    @Value("${mail.port:25}")
    private int port;

    @Value("${mail.enabled:false}")
    private boolean enabled;
}
~~~

Các property có thể đến từ application.properties, application.yml, biến môi trường, tham số dòng lệnh hoặc nguồn cấu hình khác được Environment hỗ trợ.

Spring xử lý chuyển đổi kiểu khi inject giá trị vào field. Ví dụ chuỗi "25" có thể được chuyển thành int nếu conversion phù hợp. Nếu property sai định dạng hoặc không thể chuyển đổi, quá trình tạo bean có thể thất bại.

Placeholder phù hợp khi cấu hình chỉ cần một giá trị. Không cần bọc mọi property trong SpEL nếu không có phép tính hoặc logic bổ sung.

## 4. Dùng SpEL để tính giá trị cấu hình

SpEL có thể kết hợp các property để tạo một giá trị mới:

~~~java
@Component
public class RetrySettings {

    @Value("#{${retry.base-delay:1000} * 2}")
    private long secondDelay;

    @Value("#{${retry.max-attempts:3} + 1}")
    private int totalAttempts;
}
~~~

Biểu thức đầu nhân giá trị retry.base-delay với 2. Biểu thức thứ hai cộng thêm một lần thử vào retry.max-attempts.

Có thể dùng toán tử số học, so sánh, logic và điều kiện để tính giá trị. Khi biểu thức dài, hãy chuyển công thức thành method hoặc bean cấu hình để dễ kiểm tra.

Hãy xác định kiểu đích của field. Kết quả SpEL cần tương thích với kiểu đó hoặc có thể chuyển đổi thông qua cơ chế conversion của Spring. Nếu kết quả là null nhưng field là primitive, quá trình inject có thể thất bại.

## 5. Truy cập Environment trong SpEL

Trong môi trường Spring, biểu thức có thể truy cập các object được cung cấp trong evaluation context, bao gồm Environment ở những ngữ cảnh phù hợp.

Ví dụ:

~~~java
@Value("#{environment['app.region']}")
private String region;

@Value("#{environment['feature.audit.enabled']}")
private boolean auditEnabled;
~~~

Cách viết này dùng property accessor để đọc key từ Environment. Nếu property có thể không tồn tại, hãy xác định cách xử lý null hoặc cung cấp giá trị mặc định bằng placeholder:

~~~java
@Value("${app.region:local}")
private String region;
~~~

Với cấu hình chỉ cần lấy một property, placeholder thường dễ đọc hơn. Truy cập Environment qua SpEL hữu ích khi giá trị đó là một phần của biểu thức lớn hơn hoặc cần kết hợp với object khác.

Không nên giả định mọi biểu thức SpEL đều tự có biến environment. Khả năng truy cập phụ thuộc EvaluationContext được Spring tạo cho vị trí cấu hình cụ thể.

## 6. Dùng SpEL với bean reference

SpEL có thể tham chiếu bean trong Spring container bằng cú pháp @beanName, nếu EvaluationContext có BeanResolver phù hợp.

Ví dụ:

~~~java
@Component
public class GreetingProvider {

    public String greeting() {
        return "Hello from Spring";
    }
}

@Component
public class WelcomeMessage {

    @Value("#{ @greetingProvider.greeting() }")
    private String message;
}
~~~

Biểu thức gọi method greeting() trên bean greetingProvider. Kết quả method được inject vào field message.

Có thể dùng bean reference để lấy property hoặc gọi method có tham số:

~~~java
@Value("#{ @currencySettings.defaultCurrency }")
private String currency;

@Value("#{ @priceCalculator.withTax(100, 0.08) }")
private BigDecimal total;
~~~

Bean phải được đăng ký trong ApplicationContext và có thể được phân giải từ context đang đánh giá biểu thức. Tên bean sai hoặc method/property không truy cập được sẽ gây lỗi khi inject hoặc đánh giá.

Chỉ nên dùng bean reference cho các thao tác nhỏ, dễ hiểu. Nếu @Value gọi một chuỗi nhiều method hoặc phụ thuộc nhiều service, hãy tạo một bean cấu hình chuyên trách để tránh giấu logic khởi tạo trong annotation.

## 7. Gọi static method và tham chiếu kiểu

SpEL hỗ trợ type reference T(...) để truy cập class và gọi static method:

~~~java
@Value("#{T(java.lang.Math).max(10, 20)}")
private int maximum;

@Value("#{T(java.util.UUID).randomUUID().toString()}")
private String instanceId;
~~~

Biểu thức đầu gọi Math.max. Biểu thức thứ hai tạo UUID rồi chuyển thành String.

Static method có thể thuận tiện cho phép tính hoặc tiện ích nhỏ. Tuy nhiên, method tạo giá trị ngẫu nhiên hoặc phụ thuộc trạng thái hệ thống có thể tạo kết quả khác nhau ở các lần đánh giá. Hãy cân nhắc thời điểm bean được tạo và việc giá trị có cần ổn định trong suốt vòng đời bean hay không.

Nếu cần giá trị cố định từ cấu hình, hãy dùng placeholder. Nếu cần logic có thể kiểm thử hoặc phụ thuộc nhiều dịch vụ, hãy chuyển logic sang bean chuyên biệt.

## 8. Điều kiện cấu hình với @ConditionalOnExpression

Spring Boot cung cấp @ConditionalOnExpression để chỉ đăng ký bean hoặc cấu hình khi một biểu thức SpEL trả về true.

Ví dụ:

~~~java
@Configuration
@ConditionalOnExpression("${feature.audit.enabled:false}")
public class AuditConfiguration {

    @Bean
    public AuditService auditService() {
        return new AuditService();
    }
}
~~~

Nếu property feature.audit.enabled là true, cấu hình được áp dụng và bean AuditService được đăng ký. Nếu giá trị là false, cấu hình bị loại khỏi ApplicationContext.

Vì biểu thức được đánh giá như điều kiện Boolean, hãy bảo đảm kết quả có ý nghĩa Boolean. Một chuỗi hoặc object không phù hợp có thể gây lỗi chuyển đổi hoặc lỗi đánh giá.

@ConditionalOnExpression thuộc Spring Boot, không phải annotation cốt lõi của Spring Framework. Nó thường được dùng trong auto-configuration hoặc cấu hình ứng dụng Spring Boot.

## 9. Kết hợp nhiều property trong điều kiện

Điều kiện có thể dựa trên nhiều property:

~~~java
@Configuration
@ConditionalOnExpression(
    "${feature.audit.enabled:false} and ${app.environment:dev} == 'prod'"
)
public class ProductionAuditConfiguration {
}
~~~

Ý định là chỉ áp dụng cấu hình khi audit được bật và environment là prod. Trong thực tế, hãy chú ý cách placeholder được phân giải và kiểu dữ liệu của giá trị. Biểu thức cuối cùng sau khi thay placeholder phải là cú pháp SpEL hợp lệ.

Một cách viết khác là dùng trực tiếp Environment hoặc bean cấu hình nếu context hỗ trợ. Tuy nhiên, điều kiện nhiều property thường dễ quản lý hơn nếu được đặt trong một property tổng hợp hoặc một điều kiện Java có tên rõ ràng.

Dùng ngoặc khi kết hợp AND/OR để tránh nhầm lẫn về nhóm điều kiện:

~~~text
(feature.alpha.enabled and app.region == 'west')
or feature.override.enabled
~~~

Giữ điều kiện ngắn để người đọc có thể hiểu vì sao bean được đăng ký hoặc bị loại.

## 10. Khi nào nên dùng @ConditionalOnProperty thay vì SpEL?

Nếu chỉ kiểm tra một property Boolean hoặc so sánh property với một giá trị cố định, @ConditionalOnProperty thường rõ ràng hơn.

Ví dụ:

~~~java
@Configuration
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class AuditConfiguration {
}
~~~

Annotation này diễn đạt trực tiếp ý định: bật cấu hình khi feature.audit.enabled là true. Không cần tạo một biểu thức SpEL.

Dùng @ConditionalOnExpression khi điều kiện thực sự cần kết hợp nhiều biểu thức hoặc thao tác SpEL. Nếu điều kiện chỉ là bật/tắt một feature, ưu tiên @ConditionalOnProperty. Với điều kiện phức tạp cần truy vấn trạng thái ứng dụng, một Condition implementation riêng có thể dễ kiểm thử và bảo trì hơn.

## 11. Cẩn trọng khi tham chiếu bean trong điều kiện

Tránh tham chiếu bean nghiệp vụ trong @ConditionalOnExpression nếu không thật sự cần. Spring Boot đánh giá điều kiện trong giai đoạn xử lý cấu hình. Việc tham chiếu một bean trong biểu thức có thể khiến bean đó được khởi tạo rất sớm, trước thời điểm thông thường và trước khi một số post-processor có thể áp dụng đầy đủ.

Điều này có thể dẫn đến bean không được xử lý như mong đợi, đặc biệt nếu bean phụ thuộc proxy, AOP hoặc các post-processing khác.

Điều kiện cấu hình nên chủ yếu dựa trên property và thông tin môi trường có sẵn. Nếu cần logic phức tạp hoặc cần đọc trạng thái bean, hãy cân nhắc một Condition implementation phù hợp hoặc tổ chức cấu hình để điều kiện không phải khởi tạo bean nghiệp vụ quá sớm.

Không dùng method có side effect trong biểu thức điều kiện. Điều kiện có thể được đánh giá trong quá trình khởi động và không nên gửi thông báo, ghi dữ liệu hoặc thay đổi trạng thái ứng dụng.

## 12. SpEL trong XML bean definition

SpEL cũng có thể được dùng trong XML configuration để thiết lập property hoặc constructor argument:

~~~xml
<bean id="cacheSettings" class="com.example.CacheSettings">
    <property name="maximumSize" value="#{100 * 2}" />
    <property name="enabled" value="#{systemProperties['app.cache.enabled']}" />
</bean>
~~~

Thuộc tính value chứa biểu thức trong #{}. Spring đánh giá biểu thức rồi chuyển kết quả sang kiểu property đích nếu cần.

Có thể tham chiếu bean khác trong biểu thức:

~~~xml
<property name="defaultCurrency" value="#{@currencySettings.defaultCurrency}" />
~~~

Nếu chỉ cần inject một property cấu hình, XML cũng có thể dùng placeholder ${...} thông qua cấu hình placeholder resolver. Hãy giữ cách viết nhất quán và chọn cơ chế phù hợp với nguồn dữ liệu.

## 13. Inject vào field, constructor và method

@Value có thể được dùng trên field, constructor parameter hoặc method parameter tùy cách cấu hình bean.

Ví dụ constructor injection:

~~~java
@Component
public class ApiSettings {

    private final String baseUrl;
    private final int timeout;

    public ApiSettings(
            @Value("${api.base-url}") String baseUrl,
            @Value("${api.timeout:5000}") int timeout) {

        this.baseUrl = baseUrl;
        this.timeout = timeout;
    }
}
~~~

Có thể dùng SpEL ở tham số:

~~~java
public ApiSettings(
        @Value("#{${api.timeout:5000} * 2}") int timeout) {
    this.timeout = timeout;
}
~~~

Constructor injection làm dependency và cấu hình cần thiết hiển thị ngay khi tạo object. Với các giá trị cấu hình liên quan chặt chẽ, một @ConfigurationProperties class thường thuận tiện hơn nhiều @Value rải rác.

## 14. @Value và @ConfigurationProperties

@Value phù hợp cho một số giá trị đơn lẻ hoặc một biểu thức nhỏ. Khi có nhiều property thuộc cùng một nhóm, @ConfigurationProperties thường dễ tổ chức hơn.

Ví dụ:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host;
    private int port = 25;
    private boolean enabled;

    // getters and setters
}
~~~

Cấu hình có cấu trúc được bind vào object. Cơ chế này hỗ trợ type conversion và validation phù hợp cho nhóm property.

SpEL trong @Value có thể tính toán một giá trị riêng, nhưng không nên dùng nó để thay thế toàn bộ quy trình bind một cây cấu hình lớn. Hãy chọn @ConfigurationProperties khi cần cấu hình có cấu trúc, nhiều field và validation tập trung.

## 15. Thời điểm đánh giá và vòng đời bean

Biểu thức @Value thường được xử lý trong quá trình Spring tạo và cấu hình bean. Giá trị được inject tại thời điểm xử lý bean definition/bean instance tương ứng, sau khi placeholder và SpEL được giải quyết theo cơ chế của container.

Đối với singleton bean, giá trị field được inject thường được giữ trong instance đó. Nếu property nguồn thay đổi sau khi bean đã tạo, field không tự động cập nhật chỉ vì Environment thay đổi.

Nếu cần cấu hình có thể refresh, hãy dùng cơ chế refresh/configuration phù hợp của ứng dụng thay vì kỳ vọng @Value tự theo dõi mọi thay đổi.

Điều kiện @ConditionalOnExpression được dùng để quyết định cấu hình hoặc bean có được đăng ký trong quá trình khởi tạo ApplicationContext hay không. Đây không phải một điều kiện được đánh giá lại tự động mỗi lần gọi method hoặc mỗi request.

## 16. Xử lý giá trị thiếu, null và sai kiểu

Một placeholder không có giá trị có thể gây lỗi nếu không có default và không có property tương ứng. Có thể chỉ định default:

~~~java
@Value("${app.region:local}")
private String region;
~~~

Với SpEL, biểu thức có thể trả null:

~~~java
@Value("#{systemProperties['missing.key']}")
private String optionalValue;
~~~

Nếu field đích là kiểu tham chiếu, null có thể được gán nếu conversion và injection cho phép. Nếu field là primitive như int hoặc boolean, null không thể biểu diễn và có thể gây lỗi.

Với biểu thức có nhiều bước, hãy kiểm tra null trước khi truy cập sâu hoặc gọi method. Nếu cấu hình bắt buộc phải có, hãy để ứng dụng fail-fast với thông báo rõ ràng thay vì âm thầm dùng một giá trị mặc định không phù hợp.

## 17. Kiểm thử cấu hình dùng SpEL

Có thể kiểm thử bean và điều kiện bằng Spring test context. Một số trường hợp nên có:

- Property được đặt đúng và biểu thức trả kết quả mong đợi.
- Property không tồn tại và default được áp dụng.
- Giá trị property sai định dạng gây lỗi chuyển đổi.
- Điều kiện true khiến bean được đăng ký.
- Điều kiện false khiến bean không được đăng ký.
- Điều kiện kết hợp nhiều property xử lý đúng từng nhánh.
- Bean reference trong biểu thức được phân giải đúng.
- Cấu hình không khởi tạo bean phụ thuộc quá sớm ngoài ý muốn.

Với @ConditionalOnExpression, nên kiểm tra cả trường hợp property thiếu và giá trị Boolean sai định dạng. Điều kiện được đánh giá khi context khởi tạo, vì vậy test nên tạo ApplicationContext với bộ property riêng cho từng trường hợp.

Không chỉ kiểm tra field có giá trị; hãy kiểm tra cả việc bean có tồn tại trong context khi điều kiện cấu hình được dùng.

## 18. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Placeholder không được thay thế | Sai tên property hoặc thiếu property resolver | Kiểm tra nguồn cấu hình và default |
| SpEL không parse được | Thiếu #{} hoặc cú pháp biểu thức sai | Kiểm tra delimiter và expression |
| Inject sai kiểu | Kết quả không chuyển được sang kiểu field | Kiểm tra TypeConverter và kiểu đích |
| Giá trị null vào primitive | Biểu thức trả null nhưng field là primitive | Cung cấp default hoặc dùng wrapper |
| Bean không được đăng ký | @ConditionalOnExpression trả false | Kiểm tra giá trị property sau khi resolve |
| Điều kiện cấu hình gây lỗi | Biểu thức cuối cùng không phải Boolean hợp lệ | Kiểm tra expression và kiểu giá trị |
| Bean bị khởi tạo quá sớm | Điều kiện tham chiếu bean khác | Tránh bean reference trong condition |
| Dùng SpEL quá phức tạp trong annotation | Logic nghiệp vụ bị giấu trong cấu hình | Chuyển logic sang bean hoặc Condition riêng |
| Cấu hình không cập nhật sau khi property đổi | Giá trị đã được inject khi bean khởi tạo | Dùng cơ chế refresh phù hợp nếu cần |

## 19. Ghi nhớ

Dùng ${...} để lấy property từ Environment và #{...} để đánh giá SpEL. @Value hỗ trợ cả placeholder, biểu thức SpEL và sự kết hợp của hai cơ chế. SpEL có thể tính toán, đọc property, gọi method, tham chiếu type hoặc bean nếu EvaluationContext cho phép.

Trong Spring Boot, @ConditionalOnExpression dùng SpEL để quyết định cấu hình hoặc bean có được đăng ký hay không. Với điều kiện đơn giản dựa trên một property, @ConditionalOnProperty thường rõ ràng hơn. Tránh tham chiếu bean nghiệp vụ trong điều kiện vì có thể khiến bean được khởi tạo quá sớm.

Với nhóm cấu hình lớn, hãy cân nhắc @ConfigurationProperties thay vì nhiều @Value rời rạc. Giữ biểu thức trong annotation ngắn, dễ đọc, xác định default và kiểu đích rõ ràng, kiểm thử cả trường hợp thiếu property, sai kiểu và điều kiện true/false.