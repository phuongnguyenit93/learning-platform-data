# SpEL trong thuộc tính constructor và property của bean

Spring Expression Language (SpEL) có thể được dùng ngay trong các giá trị cấu hình bean để tính toán đối số constructor hoặc giá trị property trước khi Spring tạo và cấu hình object. Thay vì chỉ truyền một literal cố định, bean definition có thể chứa một biểu thức như #{T(java.lang.Math).PI}, đọc system property, tham chiếu bean khác hoặc kết hợp nhiều giá trị.

Trong Spring, SpEL xuất hiện trong XML bean definition, annotation @Value và một số điểm tích hợp cấu hình khác. Khi dùng đúng chỗ, nó giúp cấu hình linh hoạt. Tuy nhiên, cần phân biệt expression với bean reference thông thường, hiểu thời điểm container đánh giá biểu thức, kiểu kết quả cần gán và phạm vi quyền mà expression được phép sử dụng.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Dùng SpEL trong constructor argument và property value của bean.
- Phân biệt value expression với cơ chế inject bean reference bằng ref.
- Hiểu cách cú pháp #{...} được xử lý trong XML và @Value.
- Kết hợp SpEL với system properties, environment và bean reference.
- Phân biệt property placeholder với SpEL.
- Hiểu chuyển đổi kiểu từ kết quả expression sang kiểu constructor/property.
- Nhận biết thời điểm expression được đánh giá trong vòng đời bean.
- Chọn giữa XML, annotation và Java configuration.
- Giới hạn nguồn expression và capability để tránh cấu hình không an toàn.

Bạn nên biết Spring IoC container, bean definition, constructor injection, setter/property injection, ApplicationContext và cú pháp SpEL cơ bản.

## 2. SpEL trong bean definition

Bean definition mô tả cách Spring tạo và cấu hình một bean. Trong XML, một giá trị thuộc tính hoặc constructor argument có thể chứa SpEL expression được bao quanh bởi #{ và }.

Ví dụ:

~~~xml
<bean id="reportSettings" class="com.example.ReportSettings">
    <property name="maxRows" value="#{100 * 5}" />
    <property name="pi" value="#{T(java.lang.Math).PI}" />
</bean>
~~~

Spring đánh giá từng expression khi phân giải giá trị bean definition. Kết quả được dùng để gán cho property tương ứng.

Trong ví dụ:

- maxRows nhận kết quả phép nhân 100 * 5.
- pi nhận hằng số PI từ class java.lang.Math.
- Phần value là một SpEL expression vì có delimiter #{...}.

Nếu giá trị chỉ là chuỗi literal, không cần bọc trong SpEL. Chỉ dùng expression khi cần tính toán, truy cập dữ liệu hoặc tham chiếu động.

## 3. Dùng SpEL cho constructor argument

Constructor injection cho phép Spring truyền giá trị đã được resolve vào constructor khi tạo bean. XML có thể dùng expression trong thuộc tính value của constructor-arg.

~~~xml
<bean id="reportSettings" class="com.example.ReportSettings">
    <constructor-arg value="#{100 * 5}" />
    <constructor-arg value="#{T(java.lang.Math).PI}" />
</bean>
~~~

Ví dụ class:

~~~java
public class ReportSettings {
    private final int maxRows;
    private final double pi;

    public ReportSettings(int maxRows, double pi) {
        this.maxRows = maxRows;
        this.pi = pi;
    }
}
~~~

SpEL tạo kết quả cho từng argument. BeanFactory sau đó chuyển đổi kết quả sang kiểu tham số constructor nếu cần và nếu conversion service hỗ trợ.

Nếu constructor có nhiều overload, hãy khai báo index hoặc type phù hợp trong bean definition khi cần làm rõ cách Spring chọn constructor. Đừng dựa vào conversion ngầm để phân biệt những constructor có chữ ký gần giống nhau.

### 3.1. Truyền giá trị từ system properties

Spring cung cấp các biến hệ thống trong bean expression context. Có thể đọc system property bằng systemProperties:

~~~xml
<bean id="clientSettings" class="com.example.ClientSettings">
    <constructor-arg value="#{systemProperties['user.language']}" />
</bean>
~~~

Kết quả là giá trị của system property user.language tại thời điểm expression được đánh giá. Kiểu kết quả thường là String, phù hợp với constructor nhận String.

Không nên dùng system property làm nguồn dữ liệu bảo mật hoặc dữ liệu nghiệp vụ có thể thay đổi mà không có kiểm soát. Hãy xác định rõ nguồn cấu hình và giá trị mặc định nếu property có thể không tồn tại.

## 4. Dùng SpEL cho property value

Với setter/property injection, expression đặt trong thuộc tính value của phần tử property:

~~~xml
<bean id="featureSettings" class="com.example.FeatureSettings">
    <property name="enabled" value="#{true}" />
    <property name="retryCount" value="#{3 + 2}" />
    <property name="description" value="#{'Default configuration'}" />
</bean>
~~~

Spring đánh giá expression rồi gán kết quả cho property tương ứng. Nếu kiểu kết quả chưa khớp với property, BeanFactory có thể dùng TypeConverter hoặc ConversionService để chuyển đổi.

Ví dụ class:

~~~java
public class FeatureSettings {
    private boolean enabled;
    private int retryCount;
    private String description;

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }

    public void setDescription(String description) {
        this.description = description;
    }
}
~~~

Property phải có cơ chế ghi phù hợp. Với JavaBean thông thường, setter là cách phổ biến. Nếu property chỉ có getter hoặc object immutable, việc gán qua property injection có thể không phù hợp; hãy dùng constructor injection hoặc factory tạo object hoàn chỉnh.

## 5. Tham chiếu bean khác trong constructor/property expression

SpEL có thể lấy một bean từ Spring container bằng cú pháp @beanName, sau đó đọc property hoặc gọi method nếu context cho phép.

Ví dụ XML:

~~~xml
<bean id="endpointSettings" class="com.example.EndpointSettings">
    <property name="baseUrl" value="#{@endpointProvider.defaultUrl}" />
</bean>
~~~

Ở đây:

1. BeanResolver tìm bean endpointProvider trong BeanFactory.
2. SpEL đọc property defaultUrl trên bean đó.
3. Kết quả được gán vào property baseUrl của endpointSettings.

Có thể gọi method:

~~~xml
<bean id="messageSettings" class="com.example.MessageSettings">
    <property name="welcomeMessage"
              value="#{@messageFactory.createWelcomeMessage()}" />
</bean>
~~~

Chỉ dùng expression khi cần tính toán hoặc lấy một giá trị từ bean khác. Nếu mục đích chỉ là inject chính bean đó vào property, dùng ref sẽ rõ ràng hơn:

~~~xml
<property name="messageFactory" ref="messageFactory" />
~~~

Tương tự, với constructor argument chỉ cần bean reference, dùng constructor-arg ref thay vì expression. Cách khai báo ref thể hiện dependency trực tiếp và giúp container theo dõi quan hệ phụ thuộc rõ hơn.

## 6. Phân biệt value expression và bean reference

XML bean definition có nhiều cách truyền giá trị:

| Nhu cầu | Cách khai báo |
|---|---|
| Truyền literal | value="ACTIVE" |
| Đánh giá SpEL | value="#{...}" |
| Inject bean reference | ref="someBean" |
| Inject bean qua expression để đọc property/tính toán | value="#{@someBean.someProperty}" |

Ví dụ:

~~~xml
<bean id="serviceSettings" class="com.example.ServiceSettings">
    <property name="mode" value="SAFE" />
    <property name="timeout" value="#{30 * 1000}" />
    <property name="policy" ref="accessPolicy" />
    <property name="policyName" value="#{@accessPolicy.name}" />
</bean>
~~~

policy nhận object accessPolicy. policyName nhận một giá trị được đọc từ bean đó. Hai property có thể có kiểu khác nhau và thể hiện hai mục đích khác nhau.

Đừng dùng expression chỉ để thay thế một ref đơn giản. Expression thêm một bước phân giải và có thể làm dependency khó nhìn thấy hơn khi đọc bean definition.

## 7. Phân biệt property placeholder và SpEL

Spring thường dùng hai dạng cú pháp cấu hình khác nhau:

- Property placeholder: ký hiệu dollar theo sau bởi cặp ngoặc nhọn.
- SpEL expression: ký hiệu thăng theo sau bởi cặp ngoặc nhọn.

Placeholder lấy giá trị từ property source, ví dụ application.properties, environment variable hoặc nguồn cấu hình được Spring đăng ký.

SpEL đánh giá biểu thức, có thể thực hiện phép toán, truy cập property, tham chiếu bean hoặc gọi method được phép.

Ví dụ placeholder trong annotation có thể viết bằng hằng chuỗi Java:

~~~java
@Value("$" + "{app.name}")
private String appName;
~~~

Ví dụ SpEL:

~~~java
@Value("#{T(java.lang.Math).PI}")
private double pi;
~~~

Có thể kết hợp placeholder bên trong SpEL khi ứng dụng đã cấu hình xử lý placeholder. Placeholder được resolve thành giá trị cấu hình trước khi SpEL đánh giá phần biểu thức. Cú pháp lồng nhau cần giữ đúng dấu nháy và delimiter; nếu không cần tính toán, dùng placeholder trực tiếp sẽ đơn giản hơn.

Không nhầm placeholder với SpEL. Placeholder thay thế một giá trị cấu hình; SpEL đánh giá một biểu thức.

## 8. Dùng @Value trên field, setter và constructor parameter

Annotation @Value cho phép dùng SpEL trong các điểm inject được Spring hỗ trợ.

### 8.1. Field injection

~~~java
@Component
public class MathSettings {

    @Value("#{T(java.lang.Math).PI}")
    private double pi;
}
~~~

Spring đánh giá expression rồi chuyển kết quả sang kiểu field nếu cần.

### 8.2. Setter injection

~~~java
@Component
public class RetrySettings {
    private int retryCount;

    @Value("#{2 + 3}")
    public void setRetryCount(int retryCount) {
        this.retryCount = retryCount;
    }
}
~~~

### 8.3. Constructor parameter

~~~java
@Component
public class ReportService {

    private final int maxRows;

    public ReportService(
            @Value("#{100 * 5}") int maxRows) {
        this.maxRows = maxRows;
    }
}
~~~

Constructor parameter phù hợp khi giá trị là dependency bắt buộc và object nên được tạo ở trạng thái hoàn chỉnh. Với cấu hình có nhiều trường liên quan, có thể cân nhắc một configuration properties object thay vì nhiều expression rải rác.

## 9. Dùng SpEL trong Java configuration

Trong Java configuration, có thể dùng @Value trên tham số của phương thức @Bean:

~~~java
@Configuration
public class AppConfig {

    @Bean
    public ReportSettings reportSettings(
            @Value("#{100 * 5}") int maxRows,
            @Value("#{T(java.lang.Math).PI}") double pi) {
        return new ReportSettings(maxRows, pi);
    }
}
~~~

Spring resolve các tham số @Value trước khi gọi phương thức tạo bean. Bản thân phương thức Java vẫn chịu trách nhiệm tạo object và có thể áp dụng validation hoặc default logic rõ ràng.

Nếu giá trị chỉ cần inject trực tiếp từ bean khác, có thể khai báo tham số bean trong phương thức @Bean:

~~~java
@Bean
public ReportService reportService(AccessPolicy accessPolicy) {
    return new ReportService(accessPolicy);
}
~~~

Cách này thường rõ hơn việc dùng SpEL để lấy một bean reference rồi truyền lại.

## 10. Bean expression context và thời điểm đánh giá

Trong ApplicationContext thông thường, Spring tích hợp một BeanExpressionResolver để đánh giá biểu thức trong bean definition và các điểm cấu hình hỗ trợ SpEL. StandardBeanExpressionResolver là resolver tiêu chuẩn.

Context này được kết nối với BeanFactory và cung cấp các khả năng như:

- Tham chiếu bean bằng @beanName.
- Truy cập systemProperties và systemEnvironment.
- Truy cập environment theo cấu hình Spring.
- Đọc property trên object được cung cấp làm root.
- Dùng type conversion theo cấu hình của container.

Khi bean definition được resolve để tạo bean, giá trị expression được đánh giá trong quá trình container chuẩn bị argument/property. Với singleton, việc tạo bean thường diễn ra một lần trong vòng đời ApplicationContext; với prototype, quá trình tạo bean diễn ra mỗi lần container tạo một instance. Scope và lifecycle cụ thể ảnh hưởng thời điểm giá trị được resolve.

Đừng giả định mọi expression được đánh giá đúng một lần khi ứng dụng khởi động. Hãy xem xét scope của bean, cách tạo instance và nguồn dữ liệu mà expression đọc.

## 11. Cấu hình BeanExpressionResolver khi tự tạo BeanFactory

Khi dùng ApplicationContext tiêu chuẩn, Spring thường cấu hình resolver cần thiết. Nếu tự tạo BeanFactory độc lập hoặc thay đổi cách container khởi tạo, cần bảo đảm bean expression resolver được cài đặt.

Ví dụ minh họa:

~~~java
DefaultListableBeanFactory beanFactory =
    new DefaultListableBeanFactory();

beanFactory.setBeanExpressionResolver(
    new StandardBeanExpressionResolver()
);
~~~

Trong ứng dụng thực tế, cần kết nối resolver với class loader, bean factory và các thành phần conversion phù hợp. Không tự tạo một resolver rời rồi giả định nó tự biết toàn bộ bean hoặc environment của ứng dụng.

Nếu dùng GenericApplicationContext hoặc AnnotationConfigApplicationContext, ưu tiên lifecycle chuẩn của context để Spring cấu hình các thành phần tích hợp. Chỉ tùy chỉnh BeanExpressionResolver khi có yêu cầu cụ thể và đã hiểu ảnh hưởng tới toàn bộ bean definition.

## 12. Chuyển đổi kiểu kết quả sang constructor/property

Expression có thể trả về một kiểu khác với kiểu constructor parameter hoặc property đích. BeanFactory sử dụng TypeConverter và ConversionService của container để chuyển đổi nếu có converter phù hợp.

Ví dụ expression trả về một số:

~~~xml
<property name="retryCount" value="#{2 + 3}" />
~~~

Nếu retryCount có kiểu int, kết quả có thể được gán trực tiếp hoặc chuyển đổi theo cơ chế type conversion.

Cần phân biệt:

1. Expression có đánh giá thành công không?
2. Kết quả có chuyển đổi được sang kiểu đích không?
3. Setter hoặc constructor có chấp nhận giá trị theo nghiệp vụ không?

Conversion thành công về kiểu không đảm bảo giá trị hợp lệ. Ví dụ retryCount bằng -1 vẫn là một int hợp lệ nhưng có thể vi phạm quy tắc ứng dụng.

Với ngày giờ, tiền tệ, enum hoặc kiểu domain, hãy cấu hình ConversionService rõ ràng và validate dữ liệu. Không dựa vào format mặc định của máy chủ.

## 13. Xử lý giá trị null và default

Một expression có thể trả null nếu biến/property nguồn null hoặc bean method trả null. Khi kết quả được dùng làm constructor argument hoặc property value, cần biết đích có chấp nhận null hay không.

Có thể dùng Elvis để cung cấp giá trị mặc định:

~~~xml
<property name="displayName"
          value="#{@profileProvider.displayName ?: 'Guest'}" />
~~~

Hoặc dùng safe navigation:

~~~xml
<property name="city"
          value="#{@customerProvider.currentCustomer?.address?.city}" />
~~~

Safe navigation trả null khi receiver ở một mắt xích được bảo vệ là null. Nếu property đích không chấp nhận null, hãy cung cấp default hoặc validate trước khi tạo bean.

Không dùng default một cách máy móc. Với cấu hình bắt buộc như secret, endpoint hoặc database name, thiếu giá trị nên làm startup thất bại với thông báo rõ ràng thay vì âm thầm dùng một giá trị không an toàn.

## 14. Tham chiếu static field và static method

SpEL có thể dùng T(...) trong bean definition để đọc static field hoặc gọi static method.

Ví dụ:

~~~xml
<property name="pi" value="#{T(java.lang.Math).PI}" />
<property name="maxConnections"
          value="#{T(java.lang.Math).max(10, 20)}" />
~~~

T(...) dùng TypeLocator của evaluation context để phân giải class. Sau đó SpEL truy cập thành viên static thông qua cơ chế property/method tương ứng.

Dùng static member cho hằng số hoặc phép tính thuần, đơn giản. Không dùng expression để gọi static API có side effect hoặc truy cập tài nguyên hệ thống trong cấu hình nếu không thực sự cần thiết.

## 15. Khi nào nên dùng SpEL và khi nào nên dùng cấu hình có kiểu?

SpEL hữu ích khi cần tính một giá trị ngắn từ các nguồn đã có:

- Tính toán một hằng số.
- Chọn một giá trị từ system property hoặc environment.
- Đọc một property từ bean đã quản lý.
- Kết hợp vài giá trị cấu hình.
- Cung cấp default đơn giản.

Nên dùng configuration properties hoặc Java configuration có kiểu khi:

- Có nhiều trường cấu hình liên quan.
- Cần validation phức tạp.
- Cần bind danh sách hoặc map lớn.
- Cần hỗ trợ profile, metadata và tài liệu cấu hình.
- Cần kiểm soát kiểu, đơn vị, range hoặc format.
- Logic tính toán dài hoặc có nhiều nhánh.

Không biến bean definition thành nơi chứa toàn bộ nghiệp vụ. Expression dài thường khó debug, khó test và làm dependency giữa bean trở nên khó nhận diện.

## 16. Bảo mật và độ tin cậy của expression trong cấu hình

Bean definition thường đến từ source code hoặc cấu hình do đội phát triển kiểm soát. Tuy nhiên, nếu ứng dụng cho phép người dùng hoặc tenant tải lên cấu hình chứa SpEL, expression có thể truy cập nhiều capability của EvaluationContext.

Các rủi ro bao gồm:

- Gọi method trên bean được tham chiếu.
- Truy cập static method thông qua T(...).
- Tạo object bằng constructor nếu capability được cấp.
- Đọc property hoặc gọi method trên root object.
- Kích hoạt side effect nếu expression gọi API có tác dụng phụ.

Không evaluate expression không tin cậy bằng context rộng. Nếu cần biểu thức do quản trị viên cấu hình, hãy có quy trình validate, review, approve và publish; giới hạn bean, type, method và property được phép truy cập.

Nếu chỉ cần cấu hình dữ liệu, ưu tiên property placeholder và configuration properties. Không cho phép expression tùy ý chỉ để thay đổi một giá trị đơn giản.

## 17. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Giá trị #{...} không được đánh giá | BeanExpressionResolver không được cấu hình hoặc cú pháp sai | Kiểm tra ApplicationContext/BeanFactory và delimiter |
| Không tìm thấy bean trong @beanName | Bean name sai hoặc resolver không có bean tương ứng | Kiểm tra tên bean và context |
| Constructor được chọn không như mong đợi | Nhiều overload và argument type mơ hồ | Khai báo index/type hoặc dùng constructor rõ ràng |
| Property injection thất bại | Không có setter hoặc property không writable | Kiểm tra JavaBean property hoặc dùng constructor |
| Lỗi conversion | Kết quả expression không chuyển được sang kiểu đích | Kiểm tra TypeConverter/ConversionService và kiểu kết quả |
| Giá trị null gây lỗi tạo bean | Constructor/property không chấp nhận null | Dùng default phù hợp hoặc validation fail-fast |
| Placeholder không được resolve | Chưa cấu hình property placeholder processor hoặc sai key | Kiểm tra PropertySourcesPlaceholderConfigurer và nguồn property |
| Expression chạy ở thời điểm khác dự kiến | Scope hoặc lifecycle của bean khác giả định | Kiểm tra singleton/prototype và thời điểm tạo instance |
| Dependency cycle khi tham chiếu bean | Expression lấy bean khác trong lúc khởi tạo gây vòng phụ thuộc | Dùng dependency injection trực tiếp hoặc tái cấu trúc bean graph |
| Cấu hình có thể gọi method ngoài dự kiến | Expression có nguồn không tin cậy hoặc context quá rộng | Giới hạn nguồn expression và EvaluationContext |

Khi debug, kiểm tra lần lượt: bean definition có được nạp không, expression có được parse không, BeanResolver có tìm được bean không, expression có trả đúng kiểu không, conversion có thành công không và constructor/setter có chấp nhận giá trị không.

## 18. Bài tập thực hành

1. Tạo bean có constructor nhận int và double; truyền hai giá trị bằng SpEL trong constructor-arg.
2. Dùng SpEL trong property value để tính retryCount và đọc Math.PI.
3. Tạo bean provider có property defaultUrl rồi tham chiếu property đó bằng @beanName.
4. So sánh property ref với value expression khi inject một bean.
5. Dùng @Value trên field, setter và constructor parameter.
6. Kết hợp placeholder với SpEL để lấy một giá trị cấu hình rồi biến đổi nó.
7. Tạo property đích kiểu enum hoặc BigDecimal và kiểm tra conversion.
8. Thử property expression trả null với property đích nullable và non-nullable.
9. Tạo prototype bean có expression đọc dữ liệu runtime và quan sát thời điểm resolve.
10. Kiểm tra lỗi khi expression tham chiếu bean không tồn tại hoặc tạo dependency cycle.

## 19. Checklist trước khi dùng SpEL trong bean definition

- [ ] Expression có thật sự cần thiết hay literal/ref/placeholder đã đủ?
- [ ] Đã dùng đúng cú pháp #{...} chưa?
- [ ] Đã phân biệt SpEL với property placeholder chưa?
- [ ] Constructor/property đích có kiểu và khả năng nhận giá trị phù hợp không?
- [ ] Có overload constructor gây mơ hồ không?
- [ ] Bean reference có thể dùng ref trực tiếp rõ ràng hơn không?
- [ ] Bean được tham chiếu có tồn tại và tránh dependency cycle không?
- [ ] Đã xác định scope và thời điểm expression được đánh giá chưa?
- [ ] Null và default có đúng nghiệp vụ không?
- [ ] ConversionService có hỗ trợ kiểu đích và format mong muốn không?
- [ ] Expression có nguồn tin cậy không?
- [ ] EvaluationContext có expose capability rộng hơn nhu cầu không?
- [ ] Logic có đủ ngắn để đọc và bảo trì không?

## 20. Kết luận

SpEL có thể được dùng trong constructor argument và property value của bean thông qua expression delimiter #{...}. Spring đánh giá biểu thức trong bean expression context, sau đó chuyển kết quả sang kiểu đích nếu cần. Dùng SpEL cho phép tính ngắn, đọc cấu hình hoặc lấy property từ bean khác; dùng ref cho dependency trực tiếp và placeholder cho giá trị cấu hình đơn giản. Hãy hiểu lifecycle của bean, xử lý null/conversion rõ ràng và chỉ evaluate expression từ nguồn tin cậy với context có quyền phù hợp.