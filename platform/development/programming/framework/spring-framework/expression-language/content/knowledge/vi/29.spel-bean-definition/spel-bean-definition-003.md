# SpEL trong Java configuration

## 1. SpEL được dùng ở đâu trong Java configuration?

Spring Java configuration dùng các class được đánh dấu bằng @Configuration và các method @Bean để khai báo object do IoC container quản lý.

SpEL có thể tham gia vào quá trình cấu hình bean khi Spring xử lý metadata hoặc một injection point có hỗ trợ expression. Trong Java configuration, cách thường gặp là đặt @Value trên field, setter, constructor parameter hoặc parameter của một method được Spring quản lý.

Ví dụ:

    @Configuration
    public class PricingConfiguration {

        @Bean
        public PricingPolicy pricingPolicy(
                @Value("#{systemProperties['pricing.region'] ?: 'VN'}")
                String region) {

            return new PricingPolicy(region);
        }
    }

Spring đánh giá biểu thức trong @Value, chuyển kết quả sang kiểu tham số nếu cần, rồi gọi method pricingPolicy để tạo bean.

SpEL được xử lý bởi Spring tại những vị trí mà container biết cần resolve giá trị. Một chuỗi Java bất kỳ hoặc thân method @Bean không tự động được quét để tìm #{...}.

## 2. @Configuration và @Bean làm nhiệm vụ gì?

@Configuration đánh dấu một class là nguồn khai báo bean definitions. @Bean đánh dấu một method tạo object mà Spring sẽ đăng ký và quản lý trong ApplicationContext.

Ví dụ:

    @Configuration
    public class AppConfiguration {

        @Bean
        public CurrencyFormatter currencyFormatter() {
            return new CurrencyFormatter();
        }

        @Bean
        public InvoiceService invoiceService(
                CurrencyFormatter formatter) {
            return new InvoiceService(formatter);
        }
    }

Ở ví dụ này, Spring gọi các factory method và quản lý object trả về. Parameter formatter được resolve như một dependency của bean invoiceService.

SpEL không thay thế cơ chế dependency injection này. Nếu một @Bean method cần một bean khác làm dependency, khai báo parameter theo kiểu bean thường rõ ràng và an toàn hơn việc viết expression để tra cứu bean theo tên.

SpEL phù hợp khi giá trị cần inject phải được tính toán từ property, system property, environment hoặc một bean khác.

## 3. Dùng @Value với SpEL trong @Bean method parameter

Một @Bean method có thể nhận parameter được đánh dấu @Value.

Ví dụ:

    @Configuration
    public class PricingConfiguration {

        @Bean
        public PricingPolicy pricingPolicy(
                @Value("#{systemProperties['pricing.region'] ?: 'VN'}")
                String region,
                @Value("#{T(java.lang.Math).max(1, 5)}")
                int minimumTier) {

            return new PricingPolicy(region, minimumTier);
        }
    }

Spring xử lý từng @Value parameter trước khi gọi method:

- region nhận system property pricing.region nếu có giá trị.
- Nếu property null hoặc chuỗi rỗng, Elvis chọn VN.
- minimumTier nhận kết quả của biểu thức Math.max.
- Các giá trị được chuyển sang kiểu parameter tương ứng nếu conversion được hỗ trợ.

Đây là cách kết hợp Java factory method với giá trị được tính bằng SpEL. Method body vẫn là Java code bình thường.

## 4. Dùng @Value trên field, setter và constructor

SpEL trong Java configuration không chỉ dùng ở @Bean method parameter. Annotation @Value cũng có thể được đặt trên field, setter, method parameter và constructor parameter của bean được Spring tạo.

Ví dụ field:

    @Component
    public class RegionSettings {

        @Value("#{systemProperties['user.region'] ?: 'VN'}")
        private String region;
    }

Ví dụ setter:

    @Component
    public class LocaleSettings {

        private String locale;

        @Value("#{systemProperties['user.language'] ?: 'en'}")
        public void setLocale(String locale) {
            this.locale = locale;
        }
    }

Ví dụ constructor parameter:

    @Component
    public class CatalogService {

        private final String catalogName;

        public CatalogService(
                @Value("#{environment.getProperty('catalog.name') ?: 'default'}")
                String catalogName) {
            this.catalogName = catalogName;
        }
    }

Spring cần quản lý object và có cơ chế xử lý annotation tương ứng thì @Value mới được áp dụng. Nếu tự tạo object bằng new trong Java, Spring không tự chạy quá trình inject annotation trên object đó.

## 5. Phân biệt property placeholder ${...} với SpEL #{...}

Trong Java configuration, hai dạng thường cùng xuất hiện trong @Value nhưng có trách nhiệm khác nhau.

| Cú pháp | Cơ chế | Mục đích |
| --- | --- | --- |
| ${app.currency} | Property placeholder resolution | Đọc giá trị cấu hình theo key |
| ${app.currency:VND} | Placeholder có default | Dùng VND nếu property không được khai báo |
| #{systemProperties['user.region']} | SpEL evaluation | Đọc system property bằng biểu thức |
| #{T(java.lang.Math).max(1, 5)} | SpEL evaluation | Tính giá trị bằng biểu thức |
| #{pricingPolicy.defaultCurrency} | SpEL trong bean-definition context | Đọc property của bean khác |

Ví dụ placeholder:

    @Value("${app.currency:VND}")
    private String currency;

Spring tra cứu property app.currency. Nếu không có giá trị, placeholder dùng default VND.

Ví dụ SpEL:

    @Value("#{systemProperties['user.region'] ?: 'VN'}")
    private String region;

Spring đánh giá expression, đọc system property rồi chọn default bằng Elvis.

Placeholder resolution và SpEL evaluation là hai bước riêng. Placeholder dùng để lấy giá trị cấu hình; SpEL dùng để tính toán hoặc truy cập object theo ngôn ngữ biểu thức.

## 6. Kết hợp placeholder và SpEL đúng mục đích

Một injection point có thể dùng @Value với SpEL để tạo giá trị động, trong khi property placeholder vẫn được dùng ở những injection point khác.

Ví dụ:

    @Configuration
    public class CheckoutConfiguration {

        @Bean
        public CheckoutPolicy checkoutPolicy(
                @Value("${checkout.currency:VND}")
                String currency,
                @Value("#{T(java.lang.Math).max(0, 3)}")
                int retryLimit) {

            return new CheckoutPolicy(currency, retryLimit);
        }
    }

Ở đây currency đến từ property source, còn retryLimit là kết quả expression.

Không nên đặt toàn bộ cấu hình vào một biểu thức dài chỉ vì SpEL có thể tính toán được. Dùng placeholder cho giá trị cấu hình đơn giản và dùng SpEL khi thực sự cần biểu thức.

Nếu expression cần sử dụng một property đã được resolve, hãy xác định rõ thứ tự và cơ chế xử lý của injection point. Tránh lồng nhiều tầng placeholder và expression nếu một parameter Java riêng có thể làm logic rõ hơn.

## 7. Truy cập system properties và environment

Trong Spring bean-definition expression context, một số object được cung cấp sẵn dưới tên quen thuộc, gồm environment, systemProperties và systemEnvironment.

Ví dụ đọc system property:

    @Value("#{systemProperties['user.region']}")
    private String region;

Ví dụ đọc environment:

    @Value("#{environment.getProperty('app.region') ?: 'VN'}")
    private String region;

Ví dụ đọc biến môi trường:

    @Value("#{systemEnvironment['APP_REGION'] ?: 'VN'}")
    private String region;

Các biểu thức này được Spring đánh giá trong context của container. Không cần tự tạo StandardEvaluationContext chỉ để dùng các predefined variables này trong @Value.

Nếu tự tạo SpelExpressionParser và StandardEvaluationContext trong Java code, các predefined variables của bean-definition context không tự động xuất hiện. Khi đó phải tự cung cấp root object, variables hoặc resolver cần thiết.

## 8. Tham chiếu bean khác trong Java configuration

Spring cho phép expression trong bean-definition context tham chiếu property của bean khác theo bean name.

Ví dụ:

    @Component
    public class NumberGuess {
        public double getRandomNumber() {
            return 42.0;
        }
    }

    @Component
    public class ShapeGuess {

        private double initialShapeSeed;

        @Value("#{numberGuess.randomNumber}")
        public void setInitialShapeSeed(double value) {
            this.initialShapeSeed = value;
        }
    }

Trong context xử lý bean definition, các bean trong ApplicationContext được cung cấp như predefined variables theo tên bean. Vì vậy, expression dùng numberGuess.randomNumber.

Đây là cú pháp của Spring bean-definition evaluation context. Không nên nhầm nó với mọi EvaluationContext độc lập.

Nếu tự tạo StandardEvaluationContext và muốn dùng bean reference theo cú pháp @beanName, cần đăng ký BeanResolver phù hợp, ví dụ BeanFactoryResolver. Context độc lập không tự biết ApplicationContext của ứng dụng.

Khi chỉ cần dependency giữa hai bean, ưu tiên khai báo dependency qua constructor hoặc @Bean method parameter. Dùng SpEL bean reference khi cần lấy một giá trị hoặc tính toán trong metadata.

## 9. Tạo giá trị bằng phép toán và static method

SpEL có thể thực hiện phép toán hoặc gọi static method để tạo giá trị inject.

Ví dụ:

    @Value("#{T(java.lang.Math).max(10, 20)}")
    private int threshold;

Ví dụ số ngẫu nhiên:

    @Value("#{T(java.lang.Math).random() * 100.0}")
    private double initialSeed;

Ví dụ nối chuỗi:

    @Value("#{systemProperties['user.name'] + '-service'}")
    private String serviceLabel;

Biểu thức được đánh giá khi Spring xử lý injection point. Với bean singleton, giá trị đã inject thường được giữ trên instance đó; nó không tự tính lại mỗi khi field được đọc.

Nếu cần giá trị thay đổi theo từng request hoặc mỗi lần gọi, hãy đặt phép tính trong method/service có vòng đời phù hợp thay vì kỳ vọng @Value tự refresh liên tục.

## 10. Inject collection và cấu trúc dữ liệu inline

SpEL có thể tạo List hoặc Map inline để inject vào field hoặc parameter.

Ví dụ Map:

    @Component
    public class CatalogSettings {

        private final Map<String, Integer> counts;

        public CatalogSettings(
                @Value("#{{'Thriller': 100, 'Comedy': 300}}")
                Map<String, Integer> counts) {
            this.counts = counts;
        }
    }

Biểu thức tạo Map gồm hai entry. Spring chuyển kết quả sang kiểu parameter Map<String, Integer> theo conversion phù hợp.

Ví dụ List:

    @Bean
    public FeaturePolicy featurePolicy(
            @Value("#{{'search', 'checkout', 'profile'}}")
            List<String> enabledFeatures) {

        return new FeaturePolicy(enabledFeatures);
    }

Cú pháp inline collection bên trong @Value có thể có nhiều cặp ngoặc nhọn: một cặp ngoài dành cho delimiter SpEL trong annotation, phần bên trong là cú pháp collection của SpEL.

Hãy kiểm tra kiểu đích và generic type khi inject collection. Không dùng List rỗng thay cho Map rỗng hoặc ngược lại.

## 11. SpEL trong Java configuration khác với thân method Java

Một nhầm lẫn phổ biến là nghĩ rằng bất kỳ chuỗi nào chứa #{...} trong class @Configuration đều tự động được đánh giá.

Ví dụ:

    @Configuration
    public class AppConfiguration {

        @Bean
        public String greeting() {
            String value = "#{systemProperties['user.name']}";
            return value;
        }
    }

Method trên trả về nguyên văn chuỗi #{systemProperties['user.name']}. Spring không tự parse mọi String được tạo trong method body.

Muốn dùng SpEL tại injection point, hãy dùng @Value:

    @Bean
    public Greeting greeting(
            @Value("#{systemProperties['user.name']}")
            String userName) {

        return new Greeting(userName);
    }

Hoặc nếu cần đánh giá expression một cách chủ động trong Java code, hãy gọi ExpressionParser và cung cấp EvaluationContext phù hợp:

    ExpressionParser parser =
        new SpelExpressionParser();

    Expression expression =
        parser.parseExpression(
            "T(java.lang.Math).max(10, 20)"
        );

    Integer result =
        expression.getValue(Integer.class);

Đây là việc ứng dụng chủ động gọi SpEL API, khác với quá trình Spring xử lý @Value.

## 12. Bean definition expression và cú pháp @beanName

Trong bean-definition evaluation context của Spring, các bean được cung cấp như predefined variables theo tên bean. Vì vậy, tài liệu Spring dùng dạng:

    #{numberGuess.randomNumber}

Đây không phải cùng ngữ cảnh với expression được đánh giá bằng một StandardEvaluationContext độc lập.

Trong SpEL context có BeanResolver, cú pháp bean reference tổng quát là:

    @numberGuess.randomNumber

Ví dụ cấu hình context độc lập:

    StandardEvaluationContext context =
        new StandardEvaluationContext();

    context.setBeanResolver(
        new BeanFactoryResolver(applicationContext)
    );

    Expression expression =
        parser.parseExpression(
            "@numberGuess.randomNumber"
        );

Hai cách viết phục vụ hai môi trường resolution khác nhau. Khi viết @Value trong Java configuration, hãy dùng cú pháp bean-definition expression theo tài liệu Spring, chẳng hạn #{numberGuess.randomNumber}.

## 13. Cấu hình PropertySourcesPlaceholderConfigurer

Property placeholder được dùng để resolve các giá trị dạng ${...}. Khi ứng dụng cần kiểm soát chặt việc placeholder không tồn tại, có thể đăng ký PropertySourcesPlaceholderConfigurer.

Ví dụ:

    @Configuration
    @PropertySource("classpath:application.properties")
    public class AppConfiguration {

        @Bean
        public static PropertySourcesPlaceholderConfigurer
                propertySourcesPlaceholderConfigurer() {

            return new PropertySourcesPlaceholderConfigurer();
        }
    }

Trong Java configuration, method tạo PropertySourcesPlaceholderConfigurer nên là static để bean factory post-processor được đăng ký đúng thời điểm trong quá trình khởi tạo container.

Configurer này giúp Spring xử lý property placeholders từ các property sources đã đăng ký và có thể làm quá trình khởi tạo thất bại khi placeholder bắt buộc không resolve được.

Cấu hình placeholder và SpEL là hai phần phối hợp nhưng riêng biệt. PropertySourcesPlaceholderConfigurer xử lý placeholder; BeanExpressionResolver xử lý SpEL expression trong bean metadata.

## 14. @Value và @ConfigurationProperties

@Value phù hợp khi cần inject một giá trị hoặc một expression vào field, setter hoặc parameter.

Khi có một nhóm cấu hình lớn, có cấu trúc và cần binding theo kiểu dữ liệu, @ConfigurationProperties thường phù hợp hơn.

| Nhu cầu | Cách phù hợp |
| --- | --- |
| Một giá trị đơn | @Value |
| Một giá trị được tính bằng SpEL | @Value với #{...} |
| Đọc property có default | @Value với ${key:default} |
| Nhóm cấu hình nhiều field | @ConfigurationProperties |
| Binding cấu hình theo kiểu dữ liệu | @ConfigurationProperties |
| Truy cập bean khác để tính một giá trị | SpEL trong injection point nếu thực sự cần |

Không nên dùng SpEL để thay thế toàn bộ cơ chế externalized configuration. SpEL là ngôn ngữ biểu thức; @ConfigurationProperties và Environment là các cơ chế quản lý cấu hình có mục đích riêng.

Ngoài ra, giá trị lưu trong application.properties không tự động được đánh giá như SpEL chỉ vì nó chứa chuỗi #{...}. SpEL được xử lý tại injection point hoặc nơi ứng dụng chủ động gọi expression engine.

## 15. Thời điểm đánh giá và vòng đời bean

Spring đánh giá expression tại thời điểm xử lý bean metadata hoặc injection point trong quá trình tạo bean.

Ví dụ:

    @Component
    public class FeatureSettings {

        @Value("#{systemProperties['feature.mode'] ?: 'safe'}")
        private String mode;
    }

Khi Spring tạo FeatureSettings và xử lý @Value, expression được đánh giá rồi giá trị được gán vào field.

Với singleton bean, field giữ giá trị đã inject trong suốt vòng đời instance. Thay đổi system property sau đó không tự động cập nhật field.

Nếu cần đọc giá trị mới theo thời gian, hãy cân nhắc đọc từ Environment trong method, dùng cơ chế refresh phù hợp hoặc thiết kế bean với scope/vòng đời đáp ứng yêu cầu.

Không nên đặt biểu thức có side effect hoặc kết quả không ổn định vào @Value nếu ứng dụng kỳ vọng một giá trị cố định, dễ dự đoán.

## 16. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| @Value inject nguyên văn #{...} | Annotation processing không hoạt động hoặc object không do Spring quản lý | Kiểm tra ApplicationContext và annotation config processing |
| Placeholder ${...} không resolve | Property source thiếu hoặc placeholder configurer chưa phù hợp | Kiểm tra @PropertySource, Environment và configurer |
| SpEL không tìm thấy bean | Bean name sai hoặc expression đang chạy trong context khác | Kiểm tra bean-definition context hoặc BeanResolver |
| Dùng @beanName trong @Value nhưng không hoạt động như dự kiến | Nhầm bean-definition expression với StandardEvaluationContext độc lập | Dùng bean name như predefined variable trong bean-definition expression |
| Không chuyển được kiểu parameter | Kết quả expression không tương thích kiểu đích | Kiểm tra giá trị và ConversionService |
| Expression trả null | Property hoặc system/environment key không tồn tại | Dùng default có chủ đích và kiểm tra property source |
| Method @Bean trả chuỗi #{...} nguyên văn | Java method body không tự được parse | Dùng @Value hoặc gọi SpEL API tường minh |
| Circular dependency khi tham chiếu bean khác | Expression tạo phụ thuộc ngược trong quá trình khởi tạo | Ưu tiên constructor/method injection rõ ràng và xem lại graph phụ thuộc |
| Giá trị không đổi sau khi cấu hình thay đổi | @Value đã được inject khi bean tạo | Dùng cơ chế refresh hoặc đọc Environment theo nhu cầu |

Khi debug, xác định lỗi xảy ra ở placeholder resolution, SpEL parsing, expression evaluation, type conversion hay bean creation. Các bước này có thông báo lỗi và nguyên nhân khác nhau.

## 17. Bảo mật và khả năng bảo trì

Expression trong Java configuration thường nằm trong source code do ứng dụng kiểm soát. Tuy nhiên, SpEL có thể đọc bean, property và gọi method theo quyền của evaluation context.

Một số nguyên tắc:

- Không ghép input không tin cậy vào @Value expression.
- Không đưa dữ liệu bí mật vào expression literal.
- Giữ expression ngắn và tập trung vào tính toán giá trị cấu hình.
- Ưu tiên dependency injection qua constructor hoặc @Bean method parameter cho quan hệ bean thông thường.
- Không tạo vòng phụ thuộc giữa các bean thông qua expression.
- Không gọi method có side effect trong expression cấu hình nếu có thể xử lý bằng Java code rõ ràng.
- Dùng @ConfigurationProperties cho nhóm cấu hình phức tạp thay vì tạo một expression lớn.
- Khi tự đánh giá SpEL trong Java, cấu hình EvaluationContext theo least privilege.

Nếu rule hoặc expression có thể được người dùng chỉnh sửa, không nên đánh giá nó bằng một context có quyền truy cập rộng chỉ vì ứng dụng vốn dùng SpEL trong @Value.

## 18. Những điểm cần nhớ

- Java configuration dùng @Configuration và @Bean để khai báo bean do Spring quản lý.
- SpEL thường được dùng trong Java configuration thông qua @Value trên field, setter, method hoặc constructor parameter.
- @Value cũng có thể được dùng trên parameter của @Bean method.
- #{...} là cú pháp SpEL trong bean-definition expression.
- ${...} là property placeholder; hai cơ chế có trách nhiệm khác nhau.
- Spring bean-definition context cung cấp bean theo tên như predefined variables, ví dụ #{numberGuess.randomNumber}.
- StandardEvaluationContext độc lập cần BeanResolver nếu muốn dùng cú pháp @beanName.
- System properties, system environment và Environment có thể được truy cập trong bean-definition expression context.
- Có thể dùng phép toán, static method, Elvis, List và Map inline để tạo giá trị inject.
- Thân method @Bean và Java String thông thường không tự động được parse thành SpEL.
- Spring xử lý @Value trong quá trình tạo bean; giá trị inject không tự refresh mỗi lần đọc.
- Dùng @ConfigurationProperties cho nhóm cấu hình lớn và dependency injection rõ ràng cho quan hệ bean thông thường.
- Không đánh giá expression không tin cậy trong context có quyền rộng.

Khi dùng SpEL trong Java configuration, hãy đặt expression tại đúng injection point mà Spring hỗ trợ, phân biệt placeholder với expression và giữ phần tạo bean trong Java code dễ đọc. SpEL nên bổ sung cho dependency injection và externalized configuration, không thay thế chúng.

## Tài liệu tham khảo

- Spring Framework Reference — Expressions in Bean Definitions: https://docs.spring.io/spring-framework/reference/core/expressions/beandef.html
- Spring Framework Reference — Using @Value: https://docs.spring.io/spring-framework/reference/core/beans/annotation-config/value-annotations.html
- Spring Framework Reference — Java-based Container Configuration: https://docs.spring.io/spring-framework/reference/core/beans/java.html
- Spring Framework Reference — Externalized Configuration: https://docs.spring.io/spring-framework/reference/core/beans/environment.html
