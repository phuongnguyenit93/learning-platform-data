# Giới hạn expression trong cấu hình để giữ hệ thống dễ hiểu

SpEL giúp cấu hình Spring biểu đạt những phép tính và điều kiện linh hoạt ngay trong bean definition hoặc annotation. Nhưng biểu thức càng dài, càng nhiều tầng truy cập và càng phụ thuộc vào method hay bean khác thì cấu hình càng khó đọc, khó kiểm thử và khó chẩn đoán khi khởi động ứng dụng.

Mục tiêu của expression trong cấu hình là diễn đạt một quyết định nhỏ, rõ ràng và ổn định. Khi logic bắt đầu chứa quy tắc nghiệp vụ, nhiều nhánh điều kiện hoặc side effect, hãy chuyển phần đó sang Java configuration, một bean có tên rõ nghĩa hoặc một implementation Condition phù hợp. Cấu hình nên cho người đọc biết bean nào được tạo và nhận giá trị gì mà không buộc họ phải lần theo một chuỗi biểu thức phức tạp.

## 1. Dùng expression cho phần việc nhỏ và có thể đọc ngay

Một expression phù hợp thường có một mục tiêu đơn giản: đọc property, kết hợp vài giá trị, thực hiện phép tính ngắn hoặc kiểm tra một điều kiện trực tiếp.

Ví dụ:

~~~java
@Value("${server.port:8080}")
private int port;

@Value("#{${worker.base-count:2} * 2}")
private int workerCount;

@Value("#{T(java.lang.Math).max(1, 4)}")
private int minimumConnections;
~~~

Người đọc có thể hiểu ngay nguồn dữ liệu và kết quả. Biểu thức không che giấu một quy trình nghiệp vụ hoặc một chuỗi phụ thuộc dài.

Ngược lại, một biểu thức phải gọi nhiều method, kiểm tra nhiều object lồng nhau, kết hợp nhiều nhánh AND/OR và xử lý null ở nhiều vị trí thường là dấu hiệu logic nên được chuyển ra khỏi annotation.

Hãy xem khả năng đọc là một tiêu chí thiết kế. Nếu cần giải thích dài hơn vài câu để hiểu biểu thức đang quyết định điều gì, hãy cân nhắc đặt logic vào một method hoặc class có tên mô tả ý định.

## 2. Phân biệt placeholder với SpEL

Hai cơ chế thường xuất hiện cạnh nhau nhưng có trách nhiệm khác nhau:

| Cú pháp | Mục đích | Khi nên dùng |
|---|---|---|
| ${app.name} | Đọc giá trị property từ Environment | Cấu hình trực tiếp, có thể có giá trị mặc định |
| #{2 * 3} | Đánh giá một biểu thức SpEL | Cần tính toán hoặc kết hợp giá trị |
| #{${app.limit:10} * 2} | Dùng property làm đầu vào cho SpEL | Cần biến đổi một giá trị cấu hình đơn giản |

Ví dụ chỉ cần đọc cấu hình:

~~~java
@Value("${mail.host:localhost}")
private String mailHost;
~~~

Không cần viết lại bằng SpEL nếu không có xử lý bổ sung.

Khi cần phép tính:

~~~java
@Value("#{${retry.delay:500} * 2}")
private long nextDelay;
~~~

Placeholder được phân giải để lấy giá trị retry.delay, sau đó SpEL thực hiện phép nhân.

Đừng dùng SpEL chỉ để làm cú pháp cấu hình trông linh hoạt hơn. Nếu placeholder đã thể hiện đầy đủ ý định, hãy giữ cấu hình ở dạng placeholder.

## 3. Dùng @ConfigurationProperties cho nhóm cấu hình

Khi một bean cần nhiều property liên quan với nhau, nhiều annotation @Value riêng lẻ có thể làm cấu hình phân tán và khó quản lý.

Có thể gom chúng vào một class:

~~~java
@ConfigurationProperties(prefix = "app.mail")
public class MailProperties {

    private String host = "localhost";
    private int port = 25;
    private boolean enabled;

    public String getHost() {
        return host;
    }

    public void setHost(String host) {
        this.host = host;
    }

    public int getPort() {
        return port;
    }

    public void setPort(int port) {
        this.port = port;
    }

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
~~~

Sau đó đăng ký configuration properties theo cơ chế của ứng dụng, chẳng hạn dùng @ConfigurationPropertiesScan hoặc @EnableConfigurationProperties.

Cách này giúp gom default value, type conversion và validation vào một nơi. Nó cũng làm rõ cấu trúc cấu hình mà ứng dụng hỗ trợ.

Dùng @Value cho một vài giá trị đơn lẻ hoặc một phép tính nhỏ. Dùng @ConfigurationProperties khi cấu hình là một nhóm có cấu trúc, có nhiều field hoặc cần validation tập trung.

## 4. Chuyển logic tính toán ra khỏi annotation

Nếu một expression chứa nhiều phép tính hoặc quy tắc, hãy tạo một bean cấu hình chuyên trách.

Ví dụ, thay vì viết một biểu thức dài để tính thời gian chờ:

~~~java
@Value("#{${retry.base:500} * T(java.lang.Math).pow(2, ${retry.count:3})}")
private double delay;
~~~

Có thể dùng một class cấu hình:

~~~java
@Component
public class RetryPolicy {

    private final RetryProperties properties;

    public RetryPolicy(RetryProperties properties) {
        this.properties = properties;
    }

    public Duration delayForAttempt(int attempt) {
        long multiplier = 1L << Math.max(0, attempt);
        return Duration.ofMillis(
                properties.getBaseDelayMillis() * multiplier
        );
    }
}
~~~

Method có tên delayForAttempt mô tả ý nghĩa nghiệp vụ. Nó có thể được kiểm thử trực tiếp, kiểm soát giới hạn và xử lý trường hợp biên bằng Java.

Không nên đưa toàn bộ thuật toán vào một annotation chỉ vì SpEL có thể gọi method. Hãy để annotation tham chiếu một giá trị hoặc một API nhỏ, còn logic tính toán nằm trong code có cấu trúc.

## 5. Giữ điều kiện tạo bean đơn giản

Spring Boot có @ConditionalOnProperty cho điều kiện dựa trên một property:

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

Đây là cách diễn đạt rõ ràng khi chỉ cần bật hoặc tắt một cấu hình.

Nếu điều kiện thực sự cần biểu thức kết hợp, Spring Boot có @ConditionalOnExpression:

~~~java
@Configuration
@ConditionalOnExpression(
        "${feature.audit.enabled:false} and ${app.region:local} == 'prod'"
)
public class ProductionAuditConfiguration {
}
~~~

Hãy giữ expression ngắn và đảm bảo kết quả là Boolean. Nếu điều kiện có nhiều nhánh, nhiều giá trị hoặc quy tắc phức tạp, một class triển khai Condition có thể giúp logic có tên, có cấu trúc và dễ kiểm thử hơn.

@ConditionalOnExpression thuộc Spring Boot. Nếu chỉ cần điều kiện cấu hình cơ bản, hãy ưu tiên annotation điều kiện chuyên biệt thay vì dùng SpEL cho mọi trường hợp.

## 6. Khi nào nên tạo Condition riêng?

Condition riêng phù hợp khi quyết định đăng ký bean cần nhiều bước kiểm tra hoặc cần giải thích rõ lý do cấu hình được bật/tắt.

Ví dụ:

~~~java
public class ProductionRegionCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String region = context.getEnvironment()
                .getProperty("app.region", "local");

        boolean auditEnabled = context.getEnvironment()
                .getProperty(
                        "feature.audit.enabled",
                        Boolean.class,
                        false
                );

        return auditEnabled && "prod".equals(region);
    }
}
~~~

Dùng condition:

~~~java
@Configuration
@Conditional(ProductionRegionCondition.class)
public class ProductionAuditConfiguration {
}
~~~

Logic được đặt trong một class riêng, có thể kiểm thử bằng các bộ Environment khác nhau. Tên class cũng mô tả lý do cấu hình được áp dụng.

Không cần tạo Condition riêng cho một phép kiểm tra Boolean đơn giản. Hãy dùng cơ chế ít phức tạp nhất mà vẫn thể hiện rõ quy tắc.

## 7. Tránh giấu quy tắc nghiệp vụ trong SpEL

SpEL có thể gọi method, đọc bean, truy cập property và thực hiện phép toán. Điều đó không có nghĩa mọi logic nghiệp vụ đều nên được viết trong expression.

Ví dụ một biểu thức gọi nhiều service để quyết định mức giảm giá có thể khó hiểu:

~~~text
@pricingService.resolve(#customer, @promotionService.activeCampaign(), #order.total)
~~~

Người đọc phải biết các service làm gì, thứ tự gọi ra sao và có side effect hay không. Nếu method truy vấn dữ liệu hoặc thay đổi trạng thái, quá trình đánh giá cấu hình có thể gây hành động không mong muốn.

Thay vào đó, tạo một API có tên rõ ràng:

~~~java
@Component
public class CheckoutSettings {

    private final CheckoutPolicy policy;

    public CheckoutSettings(CheckoutPolicy policy) {
        this.policy = policy;
    }

    public boolean isPromotionEnabled() {
        return policy.isPromotionEnabled();
    }
}
~~~

Nếu cấu hình thực sự cần một Boolean được tính từ policy, hãy tính trong Java rồi expose giá trị đã xác định. Đừng dùng SpEL làm nơi điều phối nhiều service.

## 8. Hạn chế bean reference trong điều kiện cấu hình

SpEL có thể tham chiếu bean bằng cú pháp @beanName nếu evaluation context hỗ trợ. Tuy nhiên, tham chiếu bean trong @ConditionalOnExpression cần đặc biệt thận trọng.

Spring Boot đánh giá điều kiện trong giai đoạn xử lý cấu hình. Bean reference có thể khiến bean được khởi tạo sớm hơn vòng đời thông thường, trước khi một số post-processor hoặc proxy được áp dụng đầy đủ.

Điều này có thể gây ra hành vi khác với khi bean được sử dụng sau khi ApplicationContext đã khởi tạo xong.

Điều kiện tạo bean nên chủ yếu dựa trên Environment, property và metadata sẵn có. Nếu cần kiểm tra phức tạp, dùng Condition riêng hoặc tổ chức cấu hình để không phải khởi tạo bean nghiệp vụ chỉ nhằm quyết định có đăng ký bean khác hay không.

## 9. Không đặt side effect trong expression cấu hình

Một expression được đánh giá có thể gọi method. Nếu method gửi email, ghi database, gọi API, cập nhật trạng thái hoặc tạo tài nguyên, việc đánh giá expression có thể kích hoạt side effect.

Ví dụ không phù hợp:

~~~text
@notificationService.sendStartupMessage()
@databaseMaintenance.clearExpiredRows()
@paymentService.capture(#payment)
~~~

Các hành động này nên nằm trong lifecycle hook, application service hoặc quy trình nghiệp vụ có transaction và xử lý lỗi rõ ràng.

Expression cấu hình nên đọc dữ liệu hoặc tính giá trị. Nếu method được gọi, hãy ưu tiên method thuần, có kết quả xác định và không thay đổi trạng thái hệ thống.

Điều này đặc biệt quan trọng với điều kiện cấu hình vì điều kiện được đánh giá trong quá trình khởi tạo ApplicationContext. Không nên phụ thuộc vào số lần expression được đánh giá để đảm bảo một hành động chỉ chạy đúng một lần.

## 10. Giữ expression độc lập với chi tiết triển khai

Một expression dễ bảo trì thường phụ thuộc vào property hoặc API có tên ổn định. Nếu biểu thức truy cập sâu vào cấu trúc nội bộ của nhiều object, thay đổi nhỏ trong model có thể làm cấu hình hỏng.

Ví dụ:

~~~text
#application.account.owner.profile.preferences.locale
~~~

Đường dẫn dài phụ thuộc vào nhiều object trung gian. Nếu một property đổi tên hoặc có thể null, expression có thể thất bại.

Có thể tạo một property hoặc method chuyên biệt thể hiện dữ liệu mà cấu hình cần:

~~~java
public String getConfiguredLocale() {
    return account.getOwner()
            .getProfile()
            .getPreferences()
            .getLocale();
}
~~~

Sau đó expression chỉ cần đọc configuredLocale. Nếu đường dẫn có thể null, method Java có thể xử lý trường hợp đó theo một quy tắc thống nhất và có kiểm thử.

Không nên tạo hàng loạt getter chỉ để che giấu một model không phù hợp. Hãy chọn API theo nhu cầu cấu hình thực tế và giữ ranh giới dữ liệu rõ ràng.

## 11. Dùng tên property và biến có ý nghĩa

Expression thường được lưu trong annotation hoặc file cấu hình. Người đọc có thể không có ngữ cảnh của đoạn Java xung quanh, vì vậy tên biến và property nên mô tả ý nghĩa.

Ví dụ khó đọc:

~~~text
#{#x > #y and #z}
~~~

Ví dụ rõ hơn:

~~~text
#{#orderTotal > #minimumTotal and #customerActive}
~~~

Nếu expression sử dụng context variables do ứng dụng cung cấp, hãy đặt tên thể hiện đơn vị và mục đích. Ví dụ timeoutMillis rõ hơn timeout; minimumOrderAmount rõ hơn threshold.

Không dùng tên biến chung chung hoặc viết tắt nội bộ nếu expression được duy trì bởi nhiều nhóm. Cấu hình là một phần của giao diện vận hành và cần dễ đọc như code Java.

## 12. Kiểm soát độ sâu và số nhánh

Một expression có quá nhiều tầng truy cập hoặc nhiều điều kiện lồng nhau sẽ khó kiểm tra bằng mắt.

Ví dụ:

~~~text
#{#user != null and #user.account != null and #user.account.active and (#user.roles.?[name == 'ADMIN'].size() > 0 or #user.flags['override'] == true)}
~~~

Biểu thức này vừa kiểm tra null, đọc trạng thái account, lọc roles, truy cập Map và kết hợp nhiều nhánh.

Có thể chuyển thành method có tên mô tả ý định:

~~~java
public boolean canUseAdministrativeFeature(User user) {
    return user != null
            && user.getAccount() != null
            && user.getAccount().isActive()
            && (user.hasRole("ADMIN") || user.isOverrideEnabled());
}
~~~

Khi đó cấu hình chỉ cần tham chiếu một Boolean đã được xác định. Logic có thể được unit test với các trường hợp null, role, account và override riêng biệt.

Không có một giới hạn ký tự cố định cho expression dễ đọc. Hãy xem độ sâu truy cập, số nhánh và số phụ thuộc là dấu hiệu quan trọng hơn chiều dài chuỗi đơn thuần.

## 13. Xử lý null và default một cách tường minh

Property cấu hình có thể thiếu hoặc object có thể null. Hãy xác định rõ default nào hợp lệ cho ứng dụng.

Placeholder hỗ trợ default:

~~~java
@Value("${app.region:local}")
private String region;
~~~

SpEL có toán tử điều kiện:

~~~java
@Value("#{environment['app.region'] != null ? environment['app.region'] : 'local'}")
private String region;
~~~

Với cấu hình đơn giản, placeholder thường ngắn và dễ hiểu hơn. Nếu expression phải lặp lại cùng một đường dẫn để kiểm tra null và lấy giá trị, hãy cân nhắc chuyển logic vào bean cấu hình.

Đừng dùng default tùy tiện để che giấu property bắt buộc bị thiếu. Với cấu hình quan trọng, fail-fast cùng thông báo rõ ràng thường an toàn hơn việc âm thầm chạy với giá trị không đúng.

## 14. Chú ý kiểu dữ liệu và conversion

Giá trị placeholder thường được đọc dưới dạng text rồi chuyển đổi sang kiểu đích. Kết quả SpEL cũng cần tương thích với kiểu field, constructor parameter hoặc bean property nhận giá trị.

Ví dụ:

~~~java
@Value("${server.port:8080}")
private int port;

@Value("#{${worker.count:2} * 2}")
private long workerCount;
~~~

Nếu giá trị nguồn sai định dạng, quá trình tạo bean có thể thất bại. Nếu expression trả null nhưng đích là primitive, null không thể được gán.

Hãy xác định rõ kiểu đích và đơn vị của giá trị. Với thời gian, dùng tên như timeoutMillis hoặc một Duration property để tránh nhầm giữa millisecond và second. Với tiền tệ, tránh biểu thức số học dùng kiểu floating point khi cần độ chính xác decimal.

Conversion chỉ đổi kiểu. Nó không xác nhận giá trị có hợp lệ theo nghiệp vụ hay không. Validation cần được thực hiện riêng.

## 15. Bảo mật EvaluationContext và expression đầu vào

Nếu expression được viết cố định trong source code, tập biểu thức đã có thể được review trong quy trình phát triển. Nếu expression đến từ database, file cấu hình có thể chỉnh sửa hoặc người dùng, cần xem nó như đầu vào có thể thực thi.

SpEL có thể truy cập property, gọi method, tham chiếu type, bean và function tùy khả năng EvaluationContext cung cấp. Một context quá rộng có thể cho phép expression thực hiện hành động không nằm trong mục đích ban đầu.

Một số nguyên tắc:

1. Không đánh giá expression tùy ý do người dùng gửi trực tiếp.
2. Giới hạn root object vào DTO nhỏ, chỉ chứa dữ liệu cần thiết.
3. Chỉ đăng ký function hoặc bean thực sự cần dùng.
4. Hạn chế PropertyAccessor, MethodResolver, TypeLocator và BeanResolver theo use case.
5. Dùng context chỉ đọc nếu biểu thức không cần cập nhật dữ liệu.
6. Không expose repository, service ghi dữ liệu hoặc object chứa bí mật.
7. Thực hiện authorization trong application/service layer, không dựa vào expression để thay thế kiểm tra quyền.

Việc expression ngắn không tự động làm nó an toàn. Quyền truy cập phụ thuộc object và resolver được cấp trong context.

## 16. Tách cấu hình theo trách nhiệm

Một class cấu hình nên mô tả một nhóm bean hoặc một tính năng có liên quan. Tránh gom nhiều expression không liên quan vào một cấu hình lớn chỉ vì chúng cùng dùng SpEL.

Có thể tổ chức:

~~~java
@Configuration
@EnableConfigurationProperties(MailProperties.class)
public class MailConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.mail",
            name = "enabled",
            havingValue = "true"
    )
    public MailSender mailSender(MailProperties properties) {
        return new MailSender(
                properties.getHost(),
                properties.getPort()
        );
    }
}
~~~

Cấu hình thể hiện rõ property điều khiển việc tạo bean và dữ liệu được truyền vào constructor.

Khi một cấu hình cần nhiều nhánh theo môi trường, hãy cân nhắc tách thành các class cấu hình theo profile hoặc condition. Điều này giúp người đọc biết bean nào được đăng ký trong từng môi trường.

Không tạo quá nhiều class nhỏ nếu chúng không mang thêm ý nghĩa. Mục tiêu là đặt mỗi quyết định cấu hình ở nơi dễ tìm và có trách nhiệm rõ ràng.

## 17. Kiểm thử expression và cấu hình

Expression trong cấu hình cần được kiểm thử ở đúng ranh giới sử dụng.

Với một giá trị @Value, kiểm tra:

- Property có giá trị hợp lệ.
- Property bị thiếu và default được áp dụng.
- Property sai định dạng.
- SpEL trả đúng kiểu và giá trị.
- Giá trị null có được xử lý đúng.

Với điều kiện tạo bean, kiểm tra:

- Điều kiện true khiến bean tồn tại.
- Điều kiện false khiến bean không được đăng ký.
- Property bị thiếu có hành vi đúng.
- Nhiều tổ hợp property cho kết quả đúng.
- Context khởi tạo mà không tạo bean phụ thuộc quá sớm.

Với logic đã chuyển sang method hoặc Condition riêng, viết unit test cho từng nhánh và trường hợp biên. Kiểm thử class logic độc lập thường đơn giản hơn kiểm thử một expression dài ẩn trong annotation.

## 18. Chẩn đoán lỗi khi ứng dụng khởi động

Expression trong bean definition hoặc annotation thường được đánh giá trong quá trình Spring cấu hình bean hoặc xử lý điều kiện. Lỗi cú pháp, property thiếu, chuyển đổi kiểu hoặc tham chiếu bean sai có thể làm ApplicationContext khởi tạo thất bại.

Khi chẩn đoán:

1. Xác định bean hoặc configuration class đang được tạo.
2. Tách placeholder và phần SpEL để kiểm tra giá trị sau khi resolve.
3. Kiểm tra tên property và default.
4. Kiểm tra kiểu kết quả so với kiểu đích.
5. Kiểm tra bean reference hoặc method được gọi có tồn tại không.
6. Đọc cause gốc của exception thay vì chỉ dựa vào thông báo tổng quát.
7. Nếu điều kiện không bật bean, kiểm tra giá trị Boolean cuối cùng.

Không nên bắt exception rồi trả về null hoặc default chung để ứng dụng tiếp tục trong trạng thái sai. Với cấu hình bắt buộc, lỗi khởi động rõ ràng giúp phát hiện vấn đề sớm hơn.

## 19. Checklist quyết định dùng SpEL hay Java

Trước khi thêm một expression vào cấu hình, hãy tự xác định:

| Câu hỏi | Hướng lựa chọn |
|---|---|
| Chỉ đọc một property? | Placeholder ${...} |
| Cần một phép tính ngắn từ property? | Có thể dùng SpEL trong @Value |
| Có nhiều property cùng nhóm? | @ConfigurationProperties |
| Chỉ bật/tắt theo một property? | @ConditionalOnProperty |
| Điều kiện có nhiều nhánh hoặc quy tắc? | Condition implementation riêng |
| Cần gọi nhiều service hoặc xử lý nghiệp vụ? | Method/bean Java có tên rõ ràng |
| Cần thực hiện side effect? | Application service hoặc lifecycle hook |
| Expression đến từ nguồn không tin cậy? | Không đánh giá tùy ý; giới hạn context hoặc chuyển sang rule có cấu trúc |

Bảng này không phải quy tắc cứng. Nó giúp chọn cơ chế theo trách nhiệm và độ phức tạp thực tế.

## 20. Ghi nhớ

SpEL trong bean definition và annotation hữu ích cho phép tính hoặc điều kiện ngắn, rõ ràng. Dùng placeholder để đọc cấu hình trực tiếp, @ConfigurationProperties cho nhóm property, @ConditionalOnProperty cho điều kiện bật/tắt đơn giản và Condition riêng khi logic cần nhiều nhánh.

Khi expression bắt đầu gọi nhiều bean, truy cập object sâu, chứa quy tắc nghiệp vụ hoặc có side effect, hãy chuyển logic sang Java method, configuration class hoặc application service. Tránh tham chiếu bean nghiệp vụ trong @ConditionalOnExpression vì có thể kích hoạt khởi tạo sớm.

Giữ root object và EvaluationContext ở phạm vi nhỏ, dùng tên property có ý nghĩa, xử lý default và kiểu dữ liệu rõ ràng, kiểm thử cả trường hợp thành công lẫn lỗi. Một cấu hình tốt cho thấy bean nào được tạo, vì sao nó được tạo và dữ liệu nào được truyền vào mà không cần giải mã một expression dài.