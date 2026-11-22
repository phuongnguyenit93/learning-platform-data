# Đọc cấu hình từ environment và system property

Trong Spring, cấu hình có thể đến từ nhiều nguồn như file cấu hình, biến môi trường của hệ điều hành, JVM system property hoặc dữ liệu do ứng dụng cung cấp. SpEL có thể đọc trực tiếp một số nguồn này trong ngữ cảnh biểu thức của Spring, đồng thời kết hợp giá trị cấu hình với điều kiện và phép tính.

Cần phân biệt hai cơ chế thường xuất hiện cạnh nhau: property placeholder dùng cú pháp ${app.region:local} để lấy giá trị cấu hình theo tên; SpEL dùng cú pháp #{...} để đánh giá một biểu thức. Khi chỉ cần đưa cấu hình vào bean, placeholder thường là lựa chọn đơn giản. Khi cần truy cập map system property, biến môi trường hoặc tính toán từ giá trị đó, SpEL có thể đảm nhiệm phần biểu thức.

## 1. Environment, system property và environment variable là gì?

Ba khái niệm có liên quan nhưng không đồng nghĩa.

**JVM system property** là cặp tên/giá trị được lưu trong hệ thống property của tiến trình Java. Ứng dụng đọc bằng System.getProperty() hoặc System.getProperties(). Ví dụ:

    java -Dapp.region=apac -jar application.jar

Trong chương trình:

    String region = System.getProperty("app.region");

**Environment variable** là biến môi trường do hệ điều hành hoặc môi trường triển khai cung cấp cho tiến trình. Java đọc bằng System.getenv():

    String path = System.getenv("PATH");

Một biến môi trường có thể được đặt trước khi khởi chạy ứng dụng, trong container, service manager hoặc pipeline triển khai.

**Spring Environment** là abstraction của Spring để truy cập các PropertySource. Nó có thể tổng hợp nhiều nguồn cấu hình như system properties, environment variables, file cấu hình và nguồn do ứng dụng đăng ký:

    String region = environment.getProperty("app.region");

Spring Environment giúp ứng dụng đọc cấu hình theo một tên logic mà không cần tự kiểm tra từng nguồn. Thứ tự ưu tiên giữa các nguồn phụ thuộc cấu hình Environment và nền tảng ứng dụng, chẳng hạn cách Spring Boot sắp xếp các PropertySource. Không nên giả định một thứ tự cố định cho mọi ứng dụng nếu chưa kiểm tra cấu hình thực tế.

## 2. Phân biệt placeholder và SpEL

Trong cấu hình Spring, hai cú pháp thường được dùng cạnh nhau:

- ${app.region:local} là property placeholder. Spring tìm property có tên app.region và dùng local nếu không tìm thấy giá trị.
- #{...} là SpEL expression. Spring phân tích và đánh giá nội dung bên trong như một biểu thức.

Ví dụ inject một cấu hình đơn giản:

    @Value("${app.region:local}")
    private String region;

Ví dụ đọc JVM system property bằng SpEL trong bean expression context:

    @Value("#{systemProperties['user.timezone']}")
    private String timeZone;

Ví dụ đọc environment variable:

    @Value("#{systemEnvironment['APP_REGION']}")
    private String regionFromProcess;

Ví dụ dùng fallback với Elvis:

    @Value("#{systemEnvironment['APP_REGION'] ?: 'local'}")
    private String region;

Placeholder thường phù hợp khi mục tiêu là lấy một giá trị cấu hình theo tên và có thể khai báo default. SpEL hữu ích khi cần truy cập map, gọi method được phép, kết hợp nhiều giá trị hoặc áp dụng logic trước khi inject.

Không đặt nhầm delimiter: ${...} không phải SpEL expression, còn #{...} không tự động là property placeholder.

## 3. Đọc JVM system property trong bean expression

Trong ngữ cảnh biểu thức của Spring bean definition, Spring cung cấp khả năng truy cập các giá trị system property. Cú pháp phổ biến là:

    #{systemProperties['user.timezone']}

Ví dụ inject vào bean:

    @Component
    public class RuntimeSettings {

        private final String timeZone;

        public RuntimeSettings(
                @Value("#{systemProperties['user.timezone']}")
                String timeZone) {
            this.timeZone = timeZone;
        }

        public String getTimeZone() {
            return timeZone;
        }
    }

Nếu ứng dụng được chạy với:

    java -Duser.timezone=Asia/Ho_Chi_Minh -jar application.jar

thì biểu thức đọc giá trị tương ứng từ JVM system properties.

Có thể truy cập một key khác:

    #{systemProperties['app.region']}

Dùng dấu ngoặc vuông giúp đọc key theo tên, đặc biệt khi key chứa dấu chấm hoặc ký tự không phù hợp với property path. Nếu key không tồn tại, kết quả tra cứu có thể là null; hãy xác định rõ fallback thay vì giả định key luôn được khai báo.

Ví dụ:

    #{systemProperties['app.region'] ?: 'local'}

## 4. Đọc environment variable trong bean expression

Biến môi trường của tiến trình được cung cấp dưới dạng map có thể đọc trong bean expression context:

    #{systemEnvironment['APP_REGION']}

Ví dụ:

    @Component
    public class DeploymentSettings {

        private final String region;

        public DeploymentSettings(
                @Value("#{systemEnvironment['APP_REGION'] ?: 'local'}")
                String region) {
            this.region = region;
        }

        public String getRegion() {
            return region;
        }
    }

Nếu môi trường triển khai đặt APP_REGION=apac, bean nhận giá trị apac. Nếu biến không tồn tại, Elvis chọn local.

Tên environment variable phải khớp với cách hệ điều hành và runtime cung cấp key. Trên một số hệ điều hành, quy tắc phân biệt chữ hoa/chữ thường khác nhau; hãy kiểm tra tên thực tế trong môi trường chạy. Với cấu hình Spring Boot, thường nên dùng property placeholder và cơ chế binding để tận dụng quy tắc ánh xạ cấu hình của nền tảng.

Không nên nhầm environment variable với property của đối tượng Spring Environment. systemEnvironment là map môi trường của tiến trình; environment là abstraction cấu hình của Spring nếu được cung cấp trong context tương ứng.

## 5. Dùng Spring Environment để đọc cấu hình theo property name

Nếu code Java cần truy cập cấu hình từ nhiều PropertySource, nên inject Environment:

    @Component
    public class ApplicationSettings {

        private final String region;
        private final int timeout;

        public ApplicationSettings(Environment environment) {
            this.region =
                    environment.getProperty(
                            "app.region", "local");

            this.timeout =
                    environment.getProperty(
                            "app.timeout", Integer.class, 30);
        }
    }

getProperty có thể nhận kiểu đích để Spring chuyển đổi giá trị từ nguồn cấu hình. Có thể cung cấp default nếu property không tồn tại.

Property placeholder cũng sử dụng cơ chế phân giải cấu hình của Spring:

    @Value("${app.timeout:30}")
    private int timeout;

Trong khi đó, SpEL có thể dùng trực tiếp systemProperties hoặc systemEnvironment trong bean expression context. Nếu mục tiêu là đọc cấu hình logic như app.timeout từ tất cả PropertySource theo quy tắc của Spring, hãy ưu tiên Environment hoặc placeholder thay vì tự đọc riêng một map hệ điều hành.

## 6. Kết hợp system property với fallback và chuyển đổi kiểu

System property và environment variable thường được biểu diễn dưới dạng String. Khi inject vào field hoặc constructor parameter có kiểu khác, Spring conversion service có thể chuyển đổi giá trị phù hợp.

Ví dụ dùng placeholder cho số nguyên:

    @Value("${app.retry-count:3}")
    private int retryCount;

Nếu muốn dùng SpEL để đọc trực tiếp system property và cung cấp fallback:

    @Value("#{systemProperties['app.retry-count'] ?: '3'}")
    private int retryCount;

Elvis xử lý trường hợp giá trị tra cứu là null hoặc chuỗi rỗng. Kết quả sau đó được Spring chuyển đổi sang int khi inject vào field.

Với boolean:

    @Value("#{systemProperties['feature.enabled'] ?: 'false'}")
    private boolean featureEnabled;

Với giá trị ngày, thời gian hoặc kiểu domain, nên dùng Environment#getProperty với kiểu đích, configuration properties hoặc một bộ chuyển đổi được cấu hình rõ. Không nên nhồi logic parse phức tạp vào chuỗi SpEL nếu nó có thể được đặt trong một lớp cấu hình Java có kiểm thử.

Nếu giá trị tồn tại nhưng sai định dạng, việc chuyển đổi có thể thất bại lúc khởi tạo bean. Hãy kiểm tra định dạng cấu hình và cung cấp thông báo lỗi đủ rõ để người vận hành biết property nào cần sửa.

## 7. So sánh nhiều nguồn cấu hình

Một ứng dụng có thể cần ưu tiên property cấu hình logic, sau đó dùng system property hoặc environment variable làm fallback. Có thể viết logic đó trong Java thông qua Environment:

    String region = environment.getProperty("app.region");

    if (region == null || region.isBlank()) {
        region = System.getProperty("app.region");
    }

    if (region == null || region.isBlank()) {
        region = System.getenv("APP_REGION");
    }

    if (region == null || region.isBlank()) {
        region = "local";
    }

Cách này biểu đạt rõ thứ tự fallback do ứng dụng định nghĩa. Tuy nhiên, nếu Spring Environment đã tổng hợp các nguồn và thứ tự ưu tiên mong muốn, chỉ cần:

    String region =
            environment.getProperty("app.region", "local");

Không nên tự viết lại thứ tự nguồn trong từng bean vì dễ tạo ra hành vi không nhất quán giữa các thành phần. Hãy cấu hình PropertySource tập trung hoặc dùng cơ chế cấu hình chuẩn của ứng dụng.

Trong SpEL, có thể kết hợp nhiều map nếu thật sự cần:

    #{systemProperties['app.region']
        ?: systemEnvironment['APP_REGION']
        ?: 'local'}

Biểu thức trên ưu tiên system property, sau đó environment variable, cuối cùng là local. Đây là thứ tự do chính biểu thức định nghĩa; nó có thể khác thứ tự ưu tiên trong Spring Environment hoặc Spring Boot. Chỉ dùng cách này khi thứ tự đó là quy tắc có chủ đích.

## 8. Đọc cấu hình trong XML bean definition

SpEL có thể được dùng trực tiếp trong XML bean definition:

    <bean id="runtimeSettings"
          class="com.example.RuntimeSettings">
        <property name="timeZone"
                  value="#{systemProperties['user.timezone']}"/>
        <property name="region"
                  value="#{systemEnvironment['APP_REGION'] ?: 'local'}"/>
    </bean>

Ở đây, Spring đánh giá expression trong giá trị thuộc tính khi tạo bean. Nội dung nằm trong #{...} được xử lý như SpEL; nếu chỉ muốn lấy property cấu hình theo tên, có thể dùng placeholder:

    <property name="region" value="${app.region:local}"/>

Đối với XML, cần giữ đúng quy tắc escape của XML nếu giá trị chứa các ký tự đặc biệt. Ngoài ra, cần bảo đảm bean expression resolver và cơ chế placeholder của ApplicationContext được cấu hình phù hợp với cách ứng dụng khởi tạo container.

## 9. Đánh giá độc lập bằng ExpressionParser

Khi dùng SpEL ngoài bean definition, không nên giả định các tên systemProperties và systemEnvironment tự động có sẵn như trong bean expression context của Spring. Một StandardEvaluationContext độc lập cần được cung cấp dữ liệu rõ ràng.

Ví dụ:

    ExpressionParser parser = new SpelExpressionParser();

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    context.setVariable(
            "systemProperties", System.getProperties());

    context.setVariable(
            "systemEnvironment", System.getenv());

    Expression expression =
            parser.parseExpression(
                    "#systemProperties['user.timezone']");

    String timeZone =
            expression.getValue(context, String.class);

Ở đây, ứng dụng chủ động đăng ký hai map dưới dạng biến. Vì vậy, cú pháp trong biểu thức có tiền tố #:

    #systemProperties['user.timezone']
    #systemEnvironment['APP_REGION']

Nếu muốn đọc Spring Environment trong một biểu thức độc lập, có thể đăng ký Environment thành biến:

    context.setVariable("environment", environment);

    Expression expression =
            parser.parseExpression(
                    "#environment.getProperty('app.region')");

Cách này làm rõ rằng Environment được ứng dụng cung cấp vào context. Nó cũng giúp biểu thức dùng cùng cơ chế PropertySource như phần Java còn lại.

## 10. Khi nào nên dùng systemProperties, systemEnvironment hay Environment?

| Nhu cầu | Cách phù hợp |
|---|---|
| Đọc đúng một JVM system property | systemProperties trong bean expression hoặc System.getProperty() |
| Đọc đúng một environment variable của tiến trình | systemEnvironment trong bean expression hoặc System.getenv() |
| Đọc property logic qua nhiều nguồn cấu hình Spring | Environment.getProperty() hoặc ${...} |
| Inject giá trị cấu hình đơn giản vào bean | @Value("${key:default}") |
| Tính toán hoặc chọn fallback bằng biểu thức | SpEL #{...} |
| Bind nhóm cấu hình có cấu trúc và nhiều trường | @ConfigurationProperties |

Ưu tiên cơ chế cấu hình chuẩn của Spring cho các property nghiệp vụ như app.region, app.timeout hoặc feature flags. Đọc trực tiếp systemProperties/systemEnvironment phù hợp khi thực sự cần truy cập nguồn JVM hoặc hệ điều hành cụ thể.

## 11. Thời điểm đọc giá trị và thay đổi cấu hình

Khi dùng @Value trong constructor hoặc field, giá trị thường được phân giải trong quá trình tạo bean. Bean nhận một giá trị tại thời điểm inject; nếu process system property hoặc environment thay đổi sau đó, field đã inject không tự cập nhật.

System property có thể được thay đổi trong JVM bằng System.setProperty(), nhưng việc thay đổi property toàn cục lúc runtime dễ tạo ra trạng thái không nhất quán giữa các bean. Environment variable của tiến trình cũng không phải một kênh cấu hình động đáng tin cậy để ứng dụng tự cập nhật sau khi khởi động.

Nếu ứng dụng cần cấu hình thay đổi lúc chạy, hãy dùng cơ chế refresh/configuration phù hợp với kiến trúc, hoặc truy vấn Environment tại thời điểm cần thiết nếu nguồn PropertySource hỗ trợ cập nhật. Đừng giả định một giá trị đã inject bằng @Value luôn phản ánh cấu hình mới nhất.

Với giá trị được dùng thường xuyên, có thể bind vào một object cấu hình có vòng đời rõ ràng và cập nhật object đó theo cơ chế quản lý cấu hình của ứng dụng.

## 12. Lỗi thường gặp khi đọc cấu hình

| Biểu thức hoặc tình huống | Nguyên nhân | Hướng xử lý |
|---|---|---|
| Dùng #{app.region} để đọc property | Đây là identifier/property expression, không phải placeholder | Dùng ${app.region} hoặc truy cập qua Environment |
| Dùng ${...} khi cần tính toán | Placeholder chỉ phân giải giá trị, không đánh giá logic SpEL | Dùng #{...} cho phần biểu thức |
| systemProperties không tìm thấy trong context độc lập | Không có Spring bean expression context tự cấu hình | Đăng ký map bằng setVariable và dùng #systemProperties |
| Giá trị nhận null | Key không tồn tại hoặc nguồn chưa được cấu hình | Kiểm tra key và đặt fallback |
| Sai kiểu khi inject | Giá trị chuỗi không chuyển đổi được | Kiểm tra định dạng hoặc dùng kiểu đích phù hợp |
| Environment variable không khớp tên | Khác biệt quy tắc tên theo hệ điều hành/runtime | Kiểm tra key thực tế của tiến trình |
| Giá trị @Value không đổi sau khi sửa cấu hình | Bean đã nhận giá trị tại thời điểm khởi tạo | Dùng cơ chế refresh hoặc đọc Environment khi cần |
| SpEL dùng thứ tự nguồn khác dự kiến | Biểu thức tự chọn map thay vì Spring PropertySource precedence | Dùng Environment hoặc định nghĩa fallback rõ ràng |

Khi debug, hãy xác định biểu thức chạy ở đâu: trong bean definition của Spring hay trong StandardEvaluationContext do ứng dụng tự tạo. Sau đó kiểm tra nguồn dữ liệu, key, kiểu kết quả và thời điểm giá trị được phân giải.

## 13. Bảo mật và vận hành cấu hình

System properties và environment variables thường chứa thông tin triển khai, endpoint, feature flag hoặc secret. Việc một giá trị có thể đọc được trong SpEL không có nghĩa mọi rule đều nên được phép truy cập nó.

Một số nguyên tắc:

- Chỉ đưa vào context những nguồn cấu hình mà biểu thức cần sử dụng.
- Không đưa password, access token hoặc secret vào template/rule có thể được chỉnh sửa bởi người không đáng tin cậy.
- Không ghi log toàn bộ System.getProperties() hoặc System.getenv(); chúng có thể chứa dữ liệu nhạy cảm.
- Đặt default hợp lý cho cấu hình tùy chọn và fail fast với cấu hình bắt buộc.
- Xác thực giá trị cấu hình trước khi dùng trong logic nghiệp vụ.
- Không dùng system property mutable như một kho cấu hình đồng bộ giữa các request.
- Dùng secret manager hoặc cơ chế quản lý secret của nền tảng thay vì hard-code secret trong expression.

Nếu biểu thức đến từ người dùng hoặc cấu hình bên ngoài, hãy giới hạn EvaluationContext và các property/method mà biểu thức có thể truy cập. Một expression đọc system property vẫn có thể làm lộ thông tin vận hành nếu context cho phép truy cập quá rộng.

## 14. Kiểm thử cấu hình và fallback

Nên kiểm thử cả trường hợp có giá trị và trường hợp thiếu giá trị:

- System property được đặt: xác nhận biểu thức đọc đúng key.
- Environment variable có mặt: xác nhận đúng tên và giá trị.
- Cả hai nguồn đều thiếu: xác nhận fallback được dùng.
- Giá trị rỗng: xác nhận có được coi như thiếu theo quy tắc hay không.
- Giá trị sai định dạng: xác nhận ứng dụng báo lỗi rõ ràng.
- PropertySource có nhiều nguồn cùng khai báo một key: xác nhận thứ tự ưu tiên đúng với cấu hình Environment.
- Giá trị được inject lúc khởi tạo: xác nhận thời điểm và vòng đời bean.
- Biểu thức chạy trong context độc lập: xác nhận map hoặc Environment đã được đăng ký rõ ràng.

Ví dụ kiểm thử một biểu thức fallback với system property map được cung cấp trực tiếp:

    StandardEvaluationContext context =
            new StandardEvaluationContext();

    Properties properties = new Properties();
    properties.setProperty("app.region", "apac");

    context.setVariable("systemProperties", properties);

    ExpressionParser parser = new SpelExpressionParser();

    Expression expression = parser.parseExpression(
            "#systemProperties['app.region'] ?: 'local'");

    String region = expression.getValue(context, String.class);

Kết quả là apac. Nếu xóa key app.region, kết quả là local. Kiểm thử này không thay đổi system properties toàn cục của JVM, nên có thể chạy độc lập và lặp lại ổn định.

## Kết luận

SpEL có thể đọc JVM system property và environment variable trong ngữ cảnh bean expression của Spring thông qua systemProperties và systemEnvironment. Với một StandardEvaluationContext độc lập, ứng dụng cần đăng ký các map này thành biến và tham chiếu bằng tiền tố #. Spring Environment cung cấp abstraction thống nhất để đọc property từ nhiều PropertySource.

Hãy dùng ${...} khi chỉ cần phân giải cấu hình theo tên, dùng #{...} khi cần logic biểu thức, và dùng Environment hoặc configuration properties cho cấu hình nghiệp vụ có nhiều nguồn. Xác định rõ thứ tự fallback, thời điểm đọc, kiểu dữ liệu và quyền truy cập; tránh để biểu thức hoặc log làm lộ secret từ môi trường triển khai.