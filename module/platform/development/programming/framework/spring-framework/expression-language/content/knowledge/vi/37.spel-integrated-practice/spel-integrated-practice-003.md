# Tham chiếu bean để tính giá trị cấu hình có kiểm soát trong SpEL

Spring Expression Language (SpEL) có thể tham chiếu một bean do Spring quản lý bằng cú pháp @beanName, sau đó đọc property hoặc gọi method để tạo giá trị cấu hình. Cách này hữu ích khi một giá trị cần được tính từ nhiều nguồn đã được cấu hình, chẳng hạn thời gian chờ theo môi trường, giới hạn kết nối theo profile hoặc kích thước batch theo tải dự kiến.

Để cấu hình dễ kiểm soát, bean được tham chiếu nên có API nhỏ, tên rõ ràng và method tính toán có kiểu đầu vào/đầu ra xác định. Method nên thuần, có validation và không thực hiện I/O hoặc thay đổi trạng thái hệ thống. Expression chỉ nên kết nối các giá trị đã được tin cậy; không để input tùy ý quyết định tên bean hoặc method được gọi.

## 1. Mục tiêu và kiến thức cần có

Sau bài học, bạn có thể:

- Tham chiếu bean bằng cú pháp @beanName trong SpEL.
- Gọi method trên bean để tính giá trị constructor hoặc property.
- Dùng bean reference trong @Value, XML bean definition và Java configuration.
- Phân biệt inject bean trực tiếp bằng ref/constructor injection với gọi method qua expression.
- Thiết kế calculator bean có API hẹp, deterministic và dễ kiểm thử.
- Kiểm soát kiểu tham số, kiểu kết quả, null, default và giới hạn nghiệp vụ.
- Hiểu thời điểm expression được đánh giá trong lifecycle của bean.
- Tránh dependency cycle và side effect khi khởi tạo bean.
- Kiểm thử giá trị cấu hình trong ApplicationContext.
- Giới hạn nguồn expression và quyền truy cập bean trong runtime.

Bạn nên biết Spring IoC container, bean name, dependency injection, @Value, SpelExpressionParser và cách truyền biến trong EvaluationContext.

## 2. Cú pháp tham chiếu bean

SpEL dùng ký hiệu @ để lấy bean theo tên:

~~~text
@configValueCalculator
~~~

Có thể đọc property:

~~~text
@deploymentDefaults.baseTimeoutMillis
~~~

Hoặc gọi method:

~~~text
@configValueCalculator.calculateTimeout(5000, 2)
~~~

Trong expression, @configValueCalculator được BeanResolver phân giải thành object do Spring container quản lý. Sau đó SpEL sử dụng cơ chế property hoặc method resolution để đọc property hoặc gọi method.

Trong các điểm tích hợp như @Value và bean definition do Spring quản lý, container cấu hình expression context để truy cập bean. Nếu tự tạo StandardEvaluationContext trong Java, cần cấu hình BeanResolver phù hợp, ví dụ BeanFactoryResolver.

Tên bean phải đúng với bean name hoặc alias đã đăng ký. Nên dùng tên ổn định, có ý nghĩa và không tạo tên bean động từ dữ liệu request.

## 3. Ví dụ: calculator bean tính timeout

Giả sử ứng dụng có các giá trị cấu hình cơ sở:

~~~java
@Component("deploymentDefaults")
public class DeploymentDefaults {

    public long getBaseTimeoutMillis() {
        return 5_000L;
    }

    public BigDecimal getTimeoutMultiplier() {
        return new BigDecimal("1.5");
    }
}
~~~

Tạo bean chuyên trách tính giá trị:

~~~java
@Component("configValueCalculator")
public class ConfigValueCalculator {

    public long calculateTimeout(
            long baseTimeoutMillis,
            BigDecimal multiplier) {

        if (baseTimeoutMillis <= 0) {
            throw new IllegalArgumentException(
                "baseTimeoutMillis must be positive");
        }

        if (multiplier == null
                || multiplier.compareTo(BigDecimal.ZERO) <= 0) {
            throw new IllegalArgumentException(
                "multiplier must be positive");
        }

        BigDecimal calculated =
            BigDecimal.valueOf(baseTimeoutMillis)
                .multiply(multiplier);

        return calculated.longValueExact();
    }
}
~~~

Bean đích có thể dùng kết quả:

~~~java
@Component
public class HttpClientSettings {

    private final long timeoutMillis;

    public HttpClientSettings(
            @Value("#{ @configValueCalculator.calculateTimeout(" +
                   "@deploymentDefaults.baseTimeoutMillis, " +
                   "@deploymentDefaults.timeoutMultiplier) }")
            long timeoutMillis) {
        this.timeoutMillis = timeoutMillis;
    }

    public long getTimeoutMillis() {
        return timeoutMillis;
    }
}
~~~

Với dữ liệu ví dụ, kết quả là 7500 milliseconds.

Luồng đánh giá:

1. Spring tạo expression context cho injection point.
2. BeanResolver tìm configValueCalculator và deploymentDefaults.
3. SpEL đọc hai property từ deploymentDefaults.
4. SpEL gọi calculateTimeout với các đối số đã resolve.
5. Method trả về long.
6. Spring inject kết quả vào constructor của HttpClientSettings.

Calculator không cần biết bean nào sẽ sử dụng kết quả. Nó chỉ nhận các giá trị có kiểu, thực hiện phép tính và trả kết quả.

## 4. Thiết kế calculator bean có phạm vi nhỏ

Bean được tham chiếu từ expression nên có một API đơn giản. Thay vì expose toàn bộ service nghiệp vụ, hãy tạo một component chuyên tính toán các giá trị cấu hình.

Một calculator tốt thường có các đặc điểm:

- Tên bean thể hiện mục đích, ví dụ configValueCalculator hoặc batchSizingPolicy.
- Method có tên mô tả kết quả, ví dụ calculateTimeout hoặc resolveBatchSize.
- Tham số có kiểu cụ thể, tránh Object hoặc Map không cần thiết.
- Kết quả có kiểu rõ ràng, phù hợp với property/constructor đích.
- Method deterministic: cùng input hợp lệ cho cùng output.
- Validation được thực hiện ngay tại ranh giới method.
- Không gọi database, HTTP, file system hoặc message broker.
- Không thay đổi bean state hoặc trạng thái ứng dụng.
- Không trả object có quyền rộng chỉ để expression tiếp tục gọi method khác.

Nếu cần nhiều phép tính, chia thành method nhỏ theo từng mục đích. Không biến calculator thành một service tổng hợp có thể thực hiện mọi thao tác.

## 5. Dùng bean method trong @Value

@Value hỗ trợ SpEL trong field, setter và constructor parameter của bean do Spring quản lý.

### 5.1. Constructor injection

~~~java
@Component
public class BatchSettings {

    private final int batchSize;

    public BatchSettings(
            @Value("#{ @batchSizingPolicy.resolveBatchSize(" +
                   "@deploymentDefaults.expectedRecordCount) }")
            int batchSize) {
        this.batchSize = batchSize;
    }

    public int getBatchSize() {
        return batchSize;
    }
}
~~~

Constructor injection giúp object được tạo với giá trị bắt buộc ngay từ đầu. Nếu expression không thể resolve hoặc method ném exception, quá trình tạo bean thất bại sớm.

### 5.2. Field injection

~~~java
@Component
public class RetrySettings {

    @Value("#{ @configValueCalculator.calculateRetryLimit(3, 2) }")
    private int retryLimit;

    public int getRetryLimit() {
        return retryLimit;
    }
}
~~~

Field injection có thể ngắn gọn, nhưng constructor injection thường thể hiện dependency rõ hơn và giúp test object dễ dàng hơn.

### 5.3. Setter injection

~~~java
@Component
public class MessageSettings {

    private String welcomeMessage;

    @Value("#{ @messageFactory.defaultWelcomeMessage }")
    public void setWelcomeMessage(String welcomeMessage) {
        this.welcomeMessage = welcomeMessage;
    }
}
~~~

Dùng setter khi property thực sự có thể cấu hình sau khi object được tạo hoặc khi framework yêu cầu setter. Với giá trị bắt buộc và bất biến, ưu tiên constructor.

## 6. Dùng bean reference trong XML bean definition

XML có thể gọi method của bean khác trong expression:

~~~xml
<bean id="clientSettings" class="com.example.ClientSettings">
    <property name="timeoutMillis"
              value="#{@configValueCalculator.calculateTimeout(
                  @deploymentDefaults.baseTimeoutMillis,
                  @deploymentDefaults.timeoutMultiplier)}" />
</bean>
~~~

Expression trả về giá trị được dùng để gán property timeoutMillis.

Nếu chỉ cần inject bean calculator làm dependency của một object, dùng ref trực tiếp:

~~~xml
<property name="calculator" ref="configValueCalculator" />
~~~

Phân biệt hai nhu cầu:

- ref truyền chính object bean vào constructor/property.
- value với @beanName gọi method hoặc đọc property rồi truyền kết quả.

Không dùng SpEL chỉ để thay thế một bean reference đơn giản. Khai báo dependency trực tiếp rõ ràng hơn và giúp Spring theo dõi bean graph.

## 7. Dùng bean reference trong Java configuration

Với Java configuration, có thể dùng @Value cho tham số của phương thức @Bean:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean
    public ClientSettings clientSettings(
            @Value("#{ @configValueCalculator.calculateTimeout(" +
                   "@deploymentDefaults.baseTimeoutMillis, 2) }")
            long timeoutMillis) {

        return new ClientSettings(timeoutMillis);
    }
}
~~~

Cách khác là inject calculator trực tiếp và tính giá trị trong Java:

~~~java
@Configuration
public class ClientConfiguration {

    @Bean
    public ClientSettings clientSettings(
            ConfigValueCalculator calculator,
            DeploymentDefaults defaults) {

        long timeout = calculator.calculateTimeout(
            defaults.getBaseTimeoutMillis(),
            defaults.getTimeoutMultiplier()
        );

        return new ClientSettings(timeout);
    }
}
~~~

Cách thứ hai thường dễ refactor và kiểm tra bằng compiler hơn. SpEL phù hợp khi cấu hình cần một biểu thức ngắn; nếu logic bắt đầu có nhiều nhánh hoặc nhiều dependency, Java configuration có kiểu thường rõ ràng hơn.

## 8. Bean reference và property placeholder

Placeholder và SpEL giải quyết hai nhu cầu khác nhau:

- Property placeholder lấy giá trị cấu hình từ property source.
- SpEL đánh giá biểu thức, có thể tham chiếu bean và gọi method.

Ví dụ placeholder cung cấp giá trị cơ sở:

~~~properties
app.client.base-timeout-millis=5000
~~~

Có thể inject giá trị đó vào bean defaults, sau đó dùng calculator để tính:

~~~java
@Component
public class DeploymentDefaults {

    private final long baseTimeoutMillis;

    public DeploymentDefaults(
            @Value("$" + "{app.client.base-timeout-millis:5000}")
            long baseTimeoutMillis) {
        this.baseTimeoutMillis = baseTimeoutMillis;
    }

    public long getBaseTimeoutMillis() {
        return baseTimeoutMillis;
    }
}
~~~

SpEL:

~~~text
#{ @configValueCalculator.calculateTimeout(
    @deploymentDefaults.baseTimeoutMillis, 2) }
~~~

Giữ property placeholder cho việc lấy cấu hình thô và dùng SpEL cho phép tính nhỏ. Không cần bọc một placeholder đơn giản trong expression nếu không có phép biến đổi nào cần thực hiện.

## 9. Kiểm soát kiểu đầu vào và đầu ra

Expression truyền đối số vào method theo kiểu runtime của giá trị nguồn. SpEL có thể dùng TypeConverter để chuyển đổi nếu method signature và conversion service cho phép.

Để tránh kết quả khó dự đoán:

- Dùng property có kiểu rõ như long, int, BigDecimal hoặc Duration.
- Tránh truyền chuỗi số nếu Java có thể parse và validate trước.
- Tránh overload nhiều method cùng tên với kiểu tham số gần nhau.
- Trả đúng kiểu mà constructor/property đích cần.
- Không dựa vào conversion để quyết định rounding hoặc đơn vị.
- Kiểm tra overflow và giới hạn miền giá trị trong calculator.
- Với tiền tệ, xác định currency, scale và rounding rõ ràng.
- Với thời gian, xác định đơn vị milliseconds/seconds hoặc dùng Duration.

Ví dụ nếu method trả long nhưng property đích là Integer, conversion có thể thất bại hoặc mất khả năng biểu diễn khi giá trị vượt giới hạn. Tốt hơn nên để kiểu đầu ra khớp với hợp đồng của consumer.

## 10. Xử lý null và giá trị mặc định

Bean method có thể nhận null từ property nguồn hoặc trả null. Với cấu hình bắt buộc, thường nên fail fast thay vì âm thầm tạo giá trị mặc định không rõ ràng.

Ví dụ dùng Elvis nếu null có nghĩa là chọn default:

~~~text
#{ @deploymentDefaults.optionalMultiplier ?: 1 }
~~~

Hoặc xử lý mặc định bên trong calculator:

~~~java
public long calculateTimeout(
        Long baseTimeoutMillis,
        BigDecimal multiplier) {

    if (baseTimeoutMillis == null) {
        throw new IllegalArgumentException(
            "baseTimeoutMillis is required");
    }

    BigDecimal effectiveMultiplier =
        multiplier == null
            ? BigDecimal.ONE
            : multiplier;

    // Validate range and calculate.
}
~~~

Chọn một nơi chịu trách nhiệm cho default để quy tắc không bị lặp giữa expression và Java method.

Không dùng default cho secret, endpoint bắt buộc hoặc giá trị bảo mật nếu việc thiếu cấu hình phải làm ứng dụng dừng khởi động. Một cấu hình sai nên được phát hiện sớm với thông báo rõ ràng.

## 11. Thời điểm expression được đánh giá

Trong @Value và bean definition, Spring đánh giá expression khi xử lý injection point hoặc resolve giá trị bean definition trong quá trình tạo bean.

Với singleton bean, giá trị thường được resolve khi singleton được tạo. Nếu giá trị cấu hình thay đổi sau đó, field hoặc constructor value đã inject không tự cập nhật chỉ vì một property source thay đổi.

Với prototype bean, quá trình tạo instance diễn ra nhiều lần nên expression có thể được đánh giá lại trong mỗi lần tạo instance, tùy điểm tích hợp và scope cụ thể.

Không coi @Value như cơ chế cấu hình động tự refresh. Nếu ứng dụng cần thay đổi cấu hình trong lúc chạy, hãy dùng cơ chế refresh/configuration chuyên biệt, một provider được truy vấn tại thời điểm sử dụng hoặc thiết kế lại lifecycle của component.

Cũng cần phân biệt thời điểm tạo bean calculator với thời điểm gọi method. Method được gọi khi expression được evaluate; bean được resolve theo quy tắc lifecycle và scope của container.

## 12. Tránh dependency cycle khi gọi bean method

Một expression có thể tạo dependency gián tiếp mà bean definition không thể hiện rõ như constructor injection thông thường.

Ví dụ:

- ClientSettings cần kết quả từ configValueCalculator.
- ConfigValueCalculator lại inject ClientSettings.
- Khi Spring tạo ClientSettings, expression yêu cầu calculator.
- Calculator cần ClientSettings chưa hoàn tất khởi tạo.

Đây là dependency cycle và có thể làm ApplicationContext không khởi động được.

Cách thiết kế tốt hơn:

- Calculator chỉ phụ thuộc các giá trị cấu hình cơ sở hoặc một interface nhỏ.
- Bean cung cấp defaults không phụ thuộc consumer đang cần kết quả.
- Consumer nhận kết quả tính toán mà không bị calculator tham chiếu ngược.
- Không gọi method trên bean đang trong quá trình khởi tạo nếu method phụ thuộc trạng thái chưa hoàn chỉnh.
- Dùng constructor dependency injection để làm rõ bean graph khi có thể.

Nếu cần logic tính toán phức tạp, tính trong một @Bean factory method sau khi các dependency đã được inject thường dễ theo dõi hơn expression lồng nhau.

## 13. Giữ calculator thuần và tránh side effect

Method được gọi trong expression có thể chạy trong lúc Spring tạo bean. Nếu method gửi HTTP request, đọc database, ghi file hoặc thay đổi trạng thái, việc khởi động ứng dụng có thể phát sinh hành động khó kiểm soát.

Một method phù hợp:

~~~java
public int resolveBatchSize(int expectedRecords, int maxBatchSize) {
    if (expectedRecords < 0 || maxBatchSize <= 0) {
        throw new IllegalArgumentException("Invalid batch limits");
    }

    return Math.min(expectedRecords, maxBatchSize);
}
~~~

Method này chỉ tính toán từ đầu vào và trả kết quả.

Tránh method như:

~~~java
public int calculateAndPersistSettings() {
    // Đọc database, ghi cấu hình hoặc gọi dịch vụ ngoài.
}
~~~

Nếu cần I/O để lấy dữ liệu cấu hình, thực hiện việc đó ở tầng configuration loading hoặc service orchestration có lifecycle rõ ràng. Sau đó truyền kết quả đã có kiểu vào calculator thuần.

## 14. Giới hạn bean và expression được phép dùng

Bean reference trong SpEL là một capability. Nếu expression có nguồn không tin cậy và context có thể truy cập nhiều bean, nó có thể gọi method vượt ra ngoài mục tiêu tính cấu hình.

Nguyên tắc:

- Chỉ tham chiếu bean chuyên biệt, có tên rõ ràng.
- Không expose ApplicationContext hoặc BeanFactory cho expression không tin cậy.
- Không cho client tự gửi tên bean hoặc method.
- Không đánh giá expression tùy ý bằng context rộng.
- Giới hạn method được expose bằng facade nhỏ và resolver phù hợp khi cần.
- Không expose repository, process runner, file service hoặc service quản trị.
- Chỉ dùng template/configuration expression từ nguồn được phê duyệt.
- Review thay đổi expression cùng thay đổi bean API.
- Ghi nhận version của cấu hình nếu expression được lưu ngoài source code.

Bean name cố định trong expression giúp reviewer biết chính xác dependency nào được sử dụng. Tên bean động lấy từ request khiến phạm vi quyền khó xác định và không nên được dùng cho cấu hình thông thường.

## 15. Kiểm thử calculator độc lập

Vì calculator là Java bean có API rõ, hãy kiểm thử method trực tiếp trước khi kiểm thử tích hợp SpEL.

Ví dụ:

~~~java
class ConfigValueCalculatorTest {

    private final ConfigValueCalculator calculator =
        new ConfigValueCalculator();

    @Test
    void calculatesTimeoutUsingMultiplier() {
        long result = calculator.calculateTimeout(
            5_000L,
            new BigDecimal("1.5")
        );

        assertThat(result).isEqualTo(7_500L);
    }

    @Test
    void rejectsNonPositiveBaseTimeout() {
        assertThatThrownBy(() ->
            calculator.calculateTimeout(
                0L,
                BigDecimal.ONE
            )
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

Các test calculator nên bao gồm:

- Giá trị bình thường.
- Giá trị nhỏ nhất và lớn nhất được hỗ trợ.
- Null nếu kiểu đầu vào cho phép null.
- Số âm hoặc zero không hợp lệ.
- Overflow và phép làm tròn.
- Giá trị multiplier ngoài giới hạn.
- Kết quả đúng đơn vị.

Unit test giúp xác nhận logic Java độc lập với Spring container và SpEL.

## 16. Kiểm thử tích hợp expression trong ApplicationContext

Sau unit test, kiểm tra Spring có phân giải bean name, gọi method và inject đúng kết quả hay không.

Ví dụ test tích hợp:

~~~java
class ClientSettingsContextTest {

    @Test
    void injectsCalculatedTimeoutFromBeanReference() {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(TestConfig.class)) {

            HttpClientSettings settings =
                context.getBean(HttpClientSettings.class);

            assertThat(settings.getTimeoutMillis())
                .isEqualTo(7_500L);
        }
    }
}
~~~

TestConfig cần đăng ký deploymentDefaults, configValueCalculator và HttpClientSettings. Nên dùng cấu hình nhỏ chỉ chứa các bean cần thiết để test không phụ thuộc database hoặc dịch vụ bên ngoài.

Các trường hợp tích hợp nên kiểm tra:

- Bean name đúng và bean tồn tại.
- Expression gọi đúng method và truyền đúng đối số.
- Giá trị kết quả có đúng kiểu property/constructor.
- Bean method ném exception làm khởi tạo thất bại theo mong đợi.
- Bean name sai được phát hiện sớm.
- Dependency cycle được phát hiện trong context test.
- Cấu hình profile khác nhau tạo kết quả phù hợp.
- Không có I/O hoặc side effect ngoài dự kiến khi context khởi động.

## 17. Chẩn đoán lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy @beanName | Bean name sai hoặc expression context không có BeanResolver | Kiểm tra tên bean và ApplicationContext |
| Bean tồn tại nhưng method không gọi được | Sai method name, chữ ký hoặc resolver không phân giải được | Kiểm tra method public, tham số và kiểu đầu vào |
| Method nhận giá trị sai | Property nguồn hoặc conversion không đúng kiểu | Kiểm tra kiểu runtime và TypeConverter |
| Constructor/property không nhận kết quả | Kiểu trả về không tương thích | Trả đúng kiểu hoặc cấu hình conversion rõ ràng |
| ApplicationContext không khởi động | Calculator ném exception hoặc expression sai | Kiểm tra cause chain và test calculator riêng |
| Bean bị circular reference | Calculator phụ thuộc ngược vào consumer | Tách calculator khỏi consumer và làm rõ dependency graph |
| Giá trị không cập nhật khi property đổi | @Value đã resolve trong lúc tạo bean | Dùng cơ chế refresh/provider phù hợp |
| Startup phát sinh I/O ngoài dự kiến | Calculator method có side effect | Chuyển I/O ra configuration loading/service orchestration |
| Cấu hình gọi được bean không mong muốn | Context expose quá nhiều bean hoặc expression không tin cậy | Thu hẹp bean access và nguồn expression |
| Giá trị sai theo profile | Defaults hoặc profile property không được resolve như dự kiến | Kiểm tra active profile và nguồn cấu hình |

Khi debug, kiểm tra theo thứ tự: expression source, bean name, bean lifecycle, method signature, đối số runtime, kiểu kết quả, conversion và dependency graph.

## 18. Bài tập thực hành

1. Tạo bean DeploymentDefaults cung cấp timeout cơ sở và multiplier.
2. Tạo ConfigValueCalculator có method thuần tính timeout.
3. Dùng @Value với @configValueCalculator.calculateTimeout(...) để inject constructor parameter.
4. Tạo XML bean definition gọi cùng method qua value expression.
5. Viết một Java @Bean factory method tương đương và so sánh độ rõ ràng.
6. Thêm validation cho timeout âm, multiplier null và overflow.
7. Tạo một calculator method trả Duration thay vì long và inject vào property có kiểu Duration.
8. Tạo bean calculator phụ thuộc ngược consumer để quan sát dependency cycle, sau đó tái cấu trúc.
9. Viết unit test cho calculator và integration test cho ApplicationContext.
10. Thử đổi profile/configuration property và xác nhận thời điểm giá trị được resolve.
11. Kiểm tra calculator không thực hiện database/network/file I/O.
12. Review expression để bảo đảm chỉ tham chiếu bean đã được phê duyệt.

## 19. Checklist trước khi tham chiếu bean để tính cấu hình

- [ ] Bean name có ổn định và rõ mục đích không?
- [ ] Method có API nhỏ, kiểu đầu vào/đầu ra cụ thể không?
- [ ] Method có deterministic và không tạo side effect không?
- [ ] Các tham số đã được validate và có đơn vị rõ ràng chưa?
- [ ] Kết quả có khớp kiểu constructor/property đích không?
- [ ] Null và default có được xử lý theo nghiệp vụ không?
- [ ] Có thể dùng ref hoặc constructor injection trực tiếp thay cho expression không?
- [ ] Expression có quá dài hoặc có quá nhiều tầng bean reference không?
- [ ] Bean graph có tránh dependency cycle không?
- [ ] Đã xác định thời điểm expression được đánh giá chưa?
- [ ] Có hiểu rằng @Value không tự refresh khi property source thay đổi không?
- [ ] Expression và bean được tham chiếu có nguồn tin cậy không?
- [ ] Context có expose đúng phạm vi bean cần thiết không?
- [ ] Đã unit test calculator và integration test ApplicationContext chưa?

## 20. Kết luận

SpEL có thể tham chiếu bean bằng @beanName để đọc property hoặc gọi method và dùng kết quả làm giá trị cấu hình. Thiết kế an toàn là expose một calculator bean chuyên biệt với method có kiểu rõ, deterministic, được validate và không có side effect. Dùng @Value hoặc XML value expression khi phép tính ngắn; dùng ref/constructor injection cho dependency trực tiếp và Java configuration khi logic cần nhiều bước. Hãy kiểm soát lifecycle, conversion, null, dependency cycle và nguồn expression, rồi kiểm thử cả calculator lẫn quá trình tạo ApplicationContext.