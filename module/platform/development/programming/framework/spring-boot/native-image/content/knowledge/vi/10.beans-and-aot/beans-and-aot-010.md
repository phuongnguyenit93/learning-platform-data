# Giữ mã khởi tạo an toàn, không phụ thuộc dịch vụ ngoài khi đang phân tích build

Spring AOT phân tích cấu trúc ứng dụng Spring ở **thời điểm build** để sinh mã khởi tạo và runtime hints cho GraalVM Native Image. Vì vậy, quá trình build cần có thể chạy lặp lại, dự đoán được và không bị phụ thuộc vào việc database, Kafka, Redis, Config Server hay API bên ngoài đang hoạt động.

Điều quan trọng là hiểu đúng **phần nào của Spring thực sự chạy trong AOT**. AOT refresh thông thường tạo và xử lý bean definitions chứ không tạo tất cả instance bean của ứng dụng. Tuy vậy, các callback phục vụ việc dựng cấu trúc context vẫn chạy; các bean đóng vai trò AOT processor cùng dependency của chúng cũng có thể được khởi tạo ngay trong quá trình phân tích. Nếu những đoạn mã này gọi dịch vụ ngoài, build có thể thất bại, chậm, không tái lập hoặc vô tình phụ thuộc credential của môi trường.

Bài học này giúp nhận diện ranh giới đó, thiết kế mã khởi tạo an toàn, trì hoãn hoạt động tích hợp đến runtime và kiểm chứng ứng dụng bằng các task Spring AOT.

## 1. AOT thực hiện gì ở thời điểm build?

Spring AOT kiểm tra một `ApplicationContext` trong build để chuẩn bị cấu trúc ứng dụng mà thông thường Spring sẽ khám phá khi chạy. Quá trình này có thể:

- Phân tích lớp cấu hình, component scan và các khai báo `@Bean`.
- Xử lý `ImportSelector`, `ImportBeanDefinitionRegistrar` và những callback liên quan đến đăng ký cấu hình.
- Gọi `BeanFactoryPostProcessor` và `BeanDefinitionRegistryPostProcessor` để hoàn thiện tập bean definitions.
- Đánh giá `@Profile` và các điều kiện `@Conditional` dựa trên classpath và `Environment` của lần build.
- Phân tích loại bean, các điểm injection, callback vòng đời và những thông tin cần thiết để sinh mã.
- Gọi các thành phần đóng góp AOT để tạo source code, bytecode và runtime hints.

Trong Spring Framework, `refreshForAotProcessing` có hành vi khác với một lần `ApplicationContext.refresh()` thông thường: nó chuẩn bị bean factory và bean definitions nhưng không thực hiện việc khởi tạo các bean ứng dụng thông thường. Những post-processor đặc biệt cần cho AOT vẫn được xử lý để xác định cấu trúc và loại bean.

~~~mermaid
flowchart TD
    A["processAot bắt đầu"] --> B["Đọc cấu hình và Environment"]
    B --> C["Phân tích @Configuration, imports, scan"]
    C --> D["Chạy điều kiện và BeanFactoryPostProcessor"]
    D --> E["Tập BeanDefinition hoàn chỉnh"]
    E --> F["AOT processors đóng góp mã và hints"]
    F --> G["Sinh source, bytecode, RuntimeHints"]
    G --> H["Native Image compiler"]
    H --> I["Executable native"]
    J["Database, Kafka, API ngoài"] -. "Không nên là điều kiện build" .-> D
~~~

**AOT là bước phân tích cấu trúc, không phải một lần chạy nghiệp vụ đầy đủ.** Đây là cơ sở để xác định đoạn mã nào cần an toàn khi build.

## 2. Phân biệt callback chạy trong AOT và vòng đời bean runtime

Không nên hiểu rằng mọi constructor, `@PostConstruct` hoặc `@Bean` factory method đều được gọi khi chạy `processAot`. Spring AOT thông thường không khởi tạo toàn bộ instance bean ứng dụng. Tuy nhiên, có những loại callback thực sự được gọi ở build time.

| Thành phần | Có thể chạy trong AOT? | Trách nhiệm |
|---|---|---|
| `BeanDefinitionRegistryPostProcessor` | Có | Đăng ký hoặc điều chỉnh bean definitions |
| `BeanFactoryPostProcessor` | Có | Điều chỉnh metadata của bean factory |
| `ImportSelector` / `DeferredImportSelector` | Có | Chọn cấu hình được import |
| `ImportBeanDefinitionRegistrar` | Có | Đăng ký bean definitions theo metadata |
| `Condition.matches()` | Có | Quyết định điều kiện cấu hình |
| `BeanFactoryInitializationAotProcessor` | Có; instance và dependency của processor được khởi tạo | Đóng góp mã khởi tạo cho bean factory |
| `BeanRegistrationAotProcessor` | Có; instance và dependency của processor được khởi tạo | Đóng góp cách đăng ký từng bean |
| Constructor của bean ứng dụng thông thường | Không phải trong AOT refresh thông thường | Tạo instance khi container runtime cần bean |
| `@PostConstruct`, `InitializingBean`, `initMethod` của bean thông thường | Không phải trong AOT refresh thông thường | Lifecycle callback khi bean thực sự được tạo ở runtime |
| `ApplicationRunner`, `CommandLineRunner` | Không phải callback của AOT refresh | Chạy khi ứng dụng Spring Boot khởi động ở runtime |

Hai trường hợp cần nhớ:

1. **Bean ứng dụng thông thường:** Spring AOT thường mô tả cách tạo bean và sinh instance supplier. Constructor và lifecycle callback được thực thi khi native executable khởi chạy và container tạo bean.
2. **Bean đóng vai trò AOT processor:** processor cần được gọi ngay ở build time. Nếu processor được khai báo như một bean, Spring phải khởi tạo processor và các dependency của nó để lấy đóng góp AOT.

Do đó, không cần loại bỏ `@PostConstruct` khỏi mọi bean chỉ vì dùng Native Image. Cần xác định đoạn mã đó được gọi ở pha nào và có phụ thuộc dịch vụ ngoài ở pha đó hay không.

## 3. Những đường đi có thể vô tình gọi dịch vụ ngoài

Một số đoạn mã nhìn giống cấu hình nhưng thực tế thực hiện I/O hoặc nghiệp vụ:

- `Condition.matches()` gửi HTTP request tới Config Server để quyết định có bật feature hay không.
- `ImportSelector.selectImports()` truy vấn database để tìm danh sách module cần import.
- `BeanFactoryPostProcessor` gọi `dataSource.getConnection()` để kiểm tra schema.
- `ImportBeanDefinitionRegistrar` đọc registry của dịch vụ bên ngoài để tạo bean definitions.
- AOT processor gọi API cloud để lấy danh sách bucket, queue hoặc secret.
- Constructor hoặc static initializer của một AOT processor tạo client và kết nối ngay.
- `EnvironmentPostProcessor` hoặc cơ chế nạp Config Data được cấu hình để truy cập nguồn cấu hình từ xa trong lúc chạy AOT.

Những đường đi này khiến build phụ thuộc vào trạng thái bên ngoài. Chỉ một lần endpoint chậm, DNS lỗi, credential hết hạn hoặc mạng CI bị chặn cũng có thể làm quá trình AOT thất bại.

### Ví dụ điều kiện cấu hình không an toàn

~~~java
public class RemoteFeatureCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        // Không an toàn: điều kiện build phụ thuộc HTTP service.
        try {
            URI uri = URI.create("https://feature.example.internal/enabled");
            HttpURLConnection connection =
                (HttpURLConnection) uri.toURL().openConnection();
            connection.setConnectTimeout(2_000);
            connection.setReadTimeout(2_000);

            return connection.getResponseCode() == 200;
        }
        catch (IOException ex) {
            throw new IllegalStateException(
                "Cannot determine feature availability", ex);
        }
    }
}
~~~

`Condition.matches()` được gọi trong lúc Spring phân tích cấu hình. Vì vậy đoạn mã trên có thể khiến `processAot` truy cập mạng. Nó còn làm kết quả build thay đổi theo trạng thái dịch vụ, khiến cùng một commit có thể sinh ra các tập bean khác nhau.

## 4. Điều kiện build nên dựa trên metadata ổn định

Điều kiện cấu hình nên dựa trên những dữ liệu có thể biết và kiểm soát ở build time, chẳng hạn:

- Property được cung cấp rõ trong môi trường AOT.
- Spring profile đã chọn cho artifact.
- Classpath có chứa thư viện hoặc class cần thiết.
- Bean definition khác đã được đăng ký.
- Metadata tĩnh trong source hoặc resource thuộc build input.

Ví dụ điều kiện an toàn hơn:

~~~java
public class RemoteFeatureCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Environment environment = context.getEnvironment();

        // Chỉ đọc property, không gọi dịch vụ bên ngoài.
        return environment.getProperty(
            "features.remote.enabled",
            Boolean.class,
            false
        );
    }
}
~~~

Khai báo cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(RemoteFeatureCondition.class)
class RemoteFeatureConfiguration {

    @Bean
    RemoteFeatureClient remoteFeatureClient(
            RemoteFeatureProperties properties) {
        return new RemoteFeatureClient(properties);
    }
}
~~~

Ví dụ giả định `RemoteFeatureProperties` đã được bind từ cấu hình. `RemoteFeatureClient` cũng cần được thiết kế để việc tạo đối tượng không tự mở kết nối. Điều kiện quyết định **có đăng ký bean hay không** bằng một giá trị build-time; client chỉ thực hiện I/O khi có yêu cầu ở runtime.

Lưu ý: property dùng trong điều kiện ảnh hưởng đến tập bean của image. Khi dùng AOT, cần cung cấp giá trị đó trong môi trường build. Thay property lúc chạy không tự thêm lại bean đã bị loại khỏi cấu trúc AOT.

## 5. Không thực hiện I/O trong BeanFactoryPostProcessor

`BeanFactoryPostProcessor` được gọi trong quá trình chuẩn bị bean factory, bao gồm AOT refresh. Vai trò của nó là điều chỉnh metadata và bean definitions, không phải khởi động nghiệp vụ hoặc kiểm tra sức khỏe của hệ thống bên ngoài.

Ví dụ không an toàn:

~~~java
@Component
class SchemaCheckingPostProcessor
        implements BeanFactoryPostProcessor {

    private final DataSource dataSource;

    SchemaCheckingPostProcessor(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {

        // Không an toàn: có thể mở kết nối trong lúc xử lý AOT.
        try (Connection connection = dataSource.getConnection()) {
            // Đọc schema để quyết định đăng ký bean.
        }
        catch (SQLException ex) {
            throw new IllegalStateException(ex);
        }
    }
}
~~~

Đoạn này còn tạo ra phụ thuộc vòng đời không rõ ràng: processor yêu cầu `DataSource` và mở kết nối trong lúc bean factory đang được chuẩn bị. Build không còn thuần túy là phân tích metadata.

Một post-processor được đăng ký như bean cũng được Spring khởi tạo sớm để thực hiện callback. Vì vậy, constructor và dependency của chính post-processor cũng cần nhẹ và an toàn; chỉ inject những thành phần hạ tầng cần thiết như `Environment`, `ResourceLoader` hoặc metadata đã chuẩn bị.

Cách thiết kế phù hợp hơn là dùng property hoặc metadata đã được cung cấp:

~~~java
@Component
class FeatureBeanDefinitions
        implements BeanDefinitionRegistryPostProcessor {

    private final Environment environment;

    FeatureBeanDefinitions(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {

        boolean enabled = environment.getProperty(
            "features.audit.enabled",
            Boolean.class,
            false
        );

        if (enabled && !registry.containsBeanDefinition("auditService")) {
            RootBeanDefinition definition =
                new RootBeanDefinition(AuditService.class);
            registry.registerBeanDefinition("auditService", definition);
        }
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Không kết nối database, broker hoặc API ngoài.
    }
}
~~~

Ví dụ trên minh họa nguyên tắc đăng ký bean definition dựa trên `Environment`. Với ứng dụng Spring thông thường, nên ưu tiên `@Configuration`, `@Bean`, `@ConditionalOnProperty` hoặc `ImportBeanDefinitionRegistrar` nếu cần đăng ký theo cấu hình; chỉ tự viết post-processor khi thật sự cần can thiệp ở tầng container.

## 6. AOT processor phải có dependency nhỏ và an toàn

Spring hỗ trợ các extension point như:

- `BeanFactoryInitializationAotProcessor`: đóng góp mã để khôi phục trạng thái bean factory.
- `BeanRegistrationAotProcessor`: đóng góp cách xử lý cho từng bean definition.

Nếu một bean implement các interface này, **processor và toàn bộ dependency của nó được khởi tạo trong quá trình AOT**. Đây là điểm dễ bị bỏ sót khi một service nghiệp vụ được inject vào processor.

Ví dụ cấu hình không nên dùng:

~~~java
@Configuration
class NativeConfiguration {

    @Bean
    BeanFactoryInitializationAotProcessor featureProcessor(
            RemoteFeatureAdminClient remoteClient) {

        // Việc tạo processor có thể kéo remoteClient vào build time.
        return beanFactory -> {
            remoteClient.fetchFeatureCatalog();
            return null;
        };
    }
}
~~~

Ví dụ chỉ minh họa đường phụ thuộc nguy hiểm, không phải một implementation hoàn chỉnh. Factory method tạo processor được gọi để có instance processor; dependency của processor cũng cần được khởi tạo. Nếu `RemoteFeatureAdminClient` kết nối trong constructor hoặc trong phương thức được gọi khi tạo đóng góp, build bị phụ thuộc mạng.

Nếu cần AOT processor, hãy giữ dependency của nó ở mức hạ tầng: đọc bean definitions, metadata, classpath hoặc property; sinh mã và runtime hints dựa trên dữ liệu đó. Không inject service nghiệp vụ có hành vi I/O.

Khi khai báo processor bằng `@Bean`, nên dùng factory method `static` nếu phù hợp để Spring không phải khởi tạo lớp `@Configuration` bao quanh chỉ để tạo processor:

~~~java
@Configuration(proxyBeanMethods = false)
class NativeAotConfiguration {

    @Bean
    static FeatureHintsProcessor featureHintsProcessor() {
        return new FeatureHintsProcessor();
    }
}
~~~

`FeatureHintsProcessor` trong ví dụ là một lớp hạ tầng do ứng dụng tự triển khai; bản thân nó và các dependency vẫn phải an toàn khi chạy trong AOT.

## 7. Tách việc tạo client khỏi việc kết nối dịch vụ

Một đối tượng client có thể được tạo mà chưa cần kết nối. Hãy giữ constructor ở mức gán cấu hình và chuẩn bị thành phần cục bộ; chỉ mở kết nối khi có thao tác thực sự cần.

Không nên:

~~~java
public class InventoryClient {

    private final InventoryApi api;

    public InventoryClient(URI endpoint) {
        this.api = createApi(endpoint);

        // Không nên: constructor tự gọi mạng.
        this.api.healthCheck();
    }
}
~~~

Có thể thiết kế:

~~~java
public class InventoryClient {

    private final InventoryApi api;

    public InventoryClient(URI endpoint) {
        // Chỉ tạo client/configuration cục bộ.
        this.api = createApi(endpoint);
    }

    public InventoryItem findItem(String itemId) {
        // Gọi mạng tại thời điểm nghiệp vụ thực sự cần.
        return this.api.findItem(itemId);
    }
}
~~~

Đăng ký bằng Spring:

~~~java
@Configuration(proxyBeanMethods = false)
class InventoryConfiguration {

    @Bean
    InventoryClient inventoryClient(InventoryProperties properties) {
        return new InventoryClient(properties.endpoint());
    }
}
~~~

AOT có thể mô tả bean và đường tạo instance. Khi ứng dụng native chạy và một bean cần `InventoryClient`, constructor chỉ tạo cấu trúc client cục bộ. Lời gọi mạng xảy ra khi `findItem()` được gọi trong runtime.

Với các thư viện HTTP, JDBC hoặc messaging, cần kiểm tra API cụ thể: một số factory có thể khởi tạo thread, DNS lookup, pool hoặc kết nối ngay khi tạo. Đừng chỉ nhìn tên phương thức `build()` hay `create()` rồi kết luận chắc chắn nó không I/O; hãy xác nhận hành vi thư viện.

## 8. Phân biệt constructor, @PostConstruct và AOT callback

Một bean thông thường có thể dùng constructor injection, `@PostConstruct`, `InitializingBean` hoặc `initMethod`. Những lifecycle callback này thuộc quá trình **tạo bean thực tế**. Vì AOT refresh không khởi tạo các bean ứng dụng thông thường, chúng không phải nơi mặc định để Spring chạy toàn bộ nghiệp vụ trong lúc `processAot`.

Tuy nhiên, cần tránh hai cách suy luận sai:

- Không nên kết luận mọi đoạn mã constructor đều không thể chạy trong build. Constructor của AOT processor và dependency của nó có thể chạy; static initializer cũng có thể chạy khi lớp được khởi tạo trên đường đi build.
- Không nên kết luận `@PostConstruct` có thể tùy ý gọi dịch vụ ngoài mà không ảnh hưởng hệ thống. Khi native executable khởi động, callback đó vẫn chạy và có thể làm ứng dụng không sẵn sàng nếu dịch vụ ngoài tạm thời không hoạt động.

Ví dụ lifecycle callback runtime:

~~~java
@Component
class StartupReporter {

    @PostConstruct
    void initialize() {
        // Callback này thuộc lúc bean được tạo ở runtime.
        // Chỉ thực hiện công việc cục bộ, nhanh và xác định.
    }
}
~~~

Nếu nghiệp vụ cần kiểm tra dịch vụ ngoài, hãy tách thành một hoạt động runtime có timeout, retry, quan sát và chính sách lỗi rõ ràng. Với dịch vụ không bắt buộc phải có ngay lúc ứng dụng khởi động, nên kết nối theo nhu cầu thay vì chặn toàn bộ startup.

## 9. Tránh static initializer có side effect

Static initializer có thể được chạy khi lớp được khởi tạo. Nếu lớp đó được một điều kiện, registrar hoặc AOT processor sử dụng trong build, side effect sẽ xảy ra trong tiến trình build.

Không nên:

~~~java
final class RemoteSchemaRegistry {

    static final Map<String, String> SCHEMAS = loadFromRemoteRegistry();

    private static Map<String, String> loadFromRemoteRegistry() {
        // Không an toàn: static initialization có thể gọi mạng.
        return RemoteRegistryClient.fetchSchemas();
    }
}
~~~

Thay bằng dữ liệu cục bộ, hoặc tạo một bean/service và thực hiện truy cập tại runtime:

~~~java
final class LocalSchemaCatalog {

    static final Map<String, String> SCHEMAS = Map.of(
        "order-v1", "schemas/order-v1.json",
        "order-v2", "schemas/order-v2.json"
    );

    private LocalSchemaCatalog() {
    }
}
~~~

Static initializer phù hợp với hằng số và cấu trúc cục bộ, nhỏ, xác định. Không dùng nó để đọc secret, kết nối mạng, dò metadata cloud hoặc truy vấn database.

## 10. Xử lý cấu hình từ xa và secret

Một số ứng dụng nạp cấu hình từ Config Server, Vault hoặc hệ thống quản lý secret. Tùy cách bootstrap và phiên bản tích hợp, quá trình xử lý AOT có thể kích hoạt một phần logic nạp cấu hình đó. Nếu build cần gọi một dịch vụ từ xa để quyết định tập bean, kết quả sẽ phụ thuộc vào mạng và quyền truy cập của build agent.

Hãy phân loại dữ liệu:

| Dữ liệu | Cách sử dụng phù hợp |
|---|---|
| Feature flag quyết định có đăng ký bean hay không | Cung cấp giá trị build-time rõ ràng cho AOT |
| URL, timeout của dịch vụ đã đăng ký | Đọc từ runtime configuration khi ứng dụng chạy |
| Database password, API token, private key | Cấp qua secret manager/runtime platform, không nhúng vào generated source hoặc native image |
| Danh sách schema cần sinh mã | Đưa vào source/resource versioned hoặc artifact đầu vào có kiểm soát |
| Trạng thái dịch vụ hiện tại (healthy/unhealthy) | Kiểm tra ở runtime/health monitoring, không dùng để quyết định cấu trúc bean khi build |

Không ghi credential vào:

- Tham số command line được lưu trong log.
- File generated sources hoặc resource của AOT.
- Native Image build arguments hoặc file cấu hình được commit.
- Hằng số Java, static field hoặc metadata đóng gói trong executable.
- Build cache/artifact có thể được chia sẻ rộng.

Nếu cần dùng cấu hình từ xa để build, hãy tạo một **đầu vào build được version hóa và kiểm soát** (ví dụ file cấu hình không chứa secret, manifest tính năng hoặc schema snapshot) rồi để AOT phân tích dữ liệu đó. Việc truy cập dịch vụ và lấy snapshot nên là bước riêng, có xác thực, kiểm soát thay đổi và được thực hiện trước AOT; bản thân `processAot` không cần gọi dịch vụ.

## 11. Dùng profile và @Conditional có chủ đích

Spring AOT đánh giá điều kiện bean ở build time. Các điều kiện như `@Profile`, `@ConditionalOnProperty` và custom `Condition` ảnh hưởng đến tập bean được đưa vào cấu trúc AOT.

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
class PaymentConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "payment",
        name = "provider",
        havingValue = "remote"
    )
    PaymentGateway remoteGateway(PaymentProperties properties) {
        return new RemotePaymentGateway(properties.endpoint());
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "payment",
        name = "provider",
        havingValue = "local",
        matchIfMissing = true
    )
    PaymentGateway localGateway() {
        return new LocalPaymentGateway();
    }
}
~~~

Khi AOT xử lý với `payment.provider=remote`, tập bean được sinh theo điều kiện đó. Nếu chạy executable với `payment.provider=local`, không nên mong bean local tự xuất hiện nếu nó đã bị loại khỏi cấu trúc AOT.

Vì vậy:

1. Chọn profile/property ảnh hưởng bean definitions ở bước build.
2. Ghi lại giá trị môi trường AOT cùng artifact.
3. Dùng runtime properties cho những giá trị không làm thay đổi tập bean.
4. Nếu cần nhiều cấu trúc bean, cân nhắc tạo artifact riêng theo từng cấu hình hoặc thiết kế các implementation đều có mặt và chỉ chọn dữ liệu/chiến lược lúc runtime.

**Không dùng trạng thái dịch vụ bên ngoài làm điều kiện `@Conditional`.** Trạng thái có thể thay đổi ngay sau khi build và khiến artifact được sinh ra không phản ánh môi trường lúc vận hành.

## 12. Đăng ký bean động bằng metadata thay vì truy vấn dịch vụ

Nếu ứng dụng cần tạo bean theo một danh sách plugin hoặc loại tích hợp, hãy đưa danh sách đó thành metadata đầu vào có thể phân tích ở build time.

Ví dụ một registrar chỉ dựa trên property và đăng ký bean definitions:

~~~java
public class ConnectorRegistrar
        implements ImportBeanDefinitionRegistrar, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {

        boolean enabled = environment.getProperty(
            "connectors.http.enabled",
            Boolean.class,
            false
        );
        if (!enabled) {
            return;
        }

        RootBeanDefinition definition =
            new RootBeanDefinition(HttpConnector.class);
        definition.setAutowireMode(
            AbstractBeanDefinition.AUTOWIRE_CONSTRUCTOR
        );
        registry.registerBeanDefinition("httpConnector", definition);
    }
}
~~~

Trong ví dụ, registrar chỉ đọc property build-time để quyết định có đăng ký bean hay không. `HttpConnector` có thể nhận `ConnectorProperties` qua constructor injection; endpoint và timeout được bind từ cấu hình runtime. Constructor của client không nên tự gọi API. Registrar không truy vấn registry bên ngoài để quyết định có bao nhiêu connector.

Nếu danh sách connector thay đổi theo tenant hoặc registry bên ngoài lúc runtime, hãy cân nhắc mô hình registry nghiệp vụ riêng: một bean quản lý metadata runtime và tạo client theo nhu cầu. Không biến mỗi connector runtime thành một bean definition phải khám phá trong AOT nếu tập đó không cố định tại build.

## 13. Giữ build có thể chạy khi dịch vụ ngoài không khả dụng

Một pipeline tốt nên có thể chạy AOT mà không cần database, message broker hay API nghiệp vụ đang hoạt động. Điều này không có nghĩa build không cần mạng để tải dependency; Maven/Gradle có thể cần repository và cache. Ý cần đạt là **AOT không cần gọi các dịch vụ nghiệp vụ của ứng dụng để phân tích cấu trúc bean**.

Các biện pháp thực tế:

- Cache dependency Maven/Gradle và pin phiên bản để giảm phụ thuộc mạng trong lần build lặp lại.
- Dùng cấu hình AOT riêng, chứa profile/property quyết định bean một cách rõ ràng.
- Mock hoặc thay thế tích hợp bên ngoài trong test; không để custom condition hoặc processor truy vấn thật.
- Cung cấp schema, OpenAPI spec hoặc feature manifest dưới dạng file/artifact versioned.
- Không yêu cầu database phải chạy chỉ để khởi tạo `ApplicationContext` cho AOT.
- Tách bước tạo artifact cấu hình từ hệ thống bên ngoài thành job riêng có đầu ra rõ ràng.
- Kiểm tra build log để nhận diện request HTTP, DNS lookup hoặc kết nối JDBC không mong muốn.

Nếu cần kiểm tra database schema, thực hiện ở migration job, integration test hoặc runtime health check. Không dùng `processAot` như một migration runner hay một bước kiểm tra trạng thái môi trường production.

## 14. Chạy AOT để phát hiện side effect trong build

Với Gradle, Spring Boot AOT plugin cung cấp task `processAot`. Khi GraalVM Native Image plugin được áp dụng theo cấu hình Spring Boot thông dụng, AOT plugin có thể được áp dụng tự động.

~~~bash
# Xử lý AOT của ứng dụng
./gradlew processAot

# Sau khi AOT thành công, biên dịch native executable
./gradlew nativeCompile
~~~

Nếu muốn chọn profile ảnh hưởng cấu trúc bean cho AOT:

~~~groovy
import org.springframework.boot.gradle.tasks.aot.ProcessAot

tasks.withType(ProcessAot).configureEach {
    args("--spring.profiles.active=local,native")
}
~~~

Cấu hình trên minh họa việc truyền arguments cho task `ProcessAot`. Chọn đúng profile thực sự tồn tại trong dự án.

Với Maven, Spring Boot Maven plugin có goal `process-aot`. Nếu dùng native profile do Spring Boot parent cung cấp, execution AOT thường được cấu hình trong profile đó:

~~~bash
# Gọi trực tiếp goal AOT của Spring Boot Maven plugin
./mvnw spring-boot:process-aot

# Hoặc chạy native profile đã cấu hình trong dự án
./mvnw -Pnative package
~~~

Nếu dự án cần profile Spring cụ thể, cấu hình `profiles` cho execution `process-aot` trong `pom.xml`:

~~~xml
<execution>
    <id>process-aot</id>
    <goals>
        <goal>process-aot</goal>
    </goals>
    <configuration>
        <profiles>local,native</profiles>
    </configuration>
</execution>
~~~

Các ví dụ cần được điều chỉnh theo phiên bản Spring Boot và cấu hình plugin hiện tại. Không phải dự án nào cũng có sẵn native Maven profile; hãy kiểm tra `pom.xml` và plugin management.

### Quan sát output AOT

Generated sources thường nằm trong:

| Build tool | Vị trí thường gặp |
|---|---|
| Gradle | `build/generated/aotSources` hoặc thư mục generated AOT tương ứng của plugin |
| Maven | `target/spring-aot/main/sources` |

Đường dẫn chính xác phụ thuộc phiên bản plugin và cấu hình dự án. Có thể xem log `processAot`/`process-aot`, tìm các lớp `__BeanDefinitions`, mã initializer và file runtime hints.

**Không chỉnh sửa trực tiếp file sinh ra.** Hãy sửa source configuration, condition hoặc AOT processor rồi chạy lại task.

## 15. Kiểm thử tính độc lập với dịch vụ ngoài

Một bài kiểm tra có ích là chạy AOT trong môi trường không có quyền truy cập tới các dịch vụ nghiệp vụ. Có thể dùng CI network policy, môi trường container cô lập hoặc mock service.

Quy trình gợi ý:

1. Dùng một commit và toolchain cố định.
2. Chuẩn bị dependency cache để tránh nhầm việc tải dependency với kết nối nghiệp vụ.
3. Tắt hoặc chặn truy cập tới database, Kafka, Redis, Config Server và API nghiệp vụ.
4. Chạy `processAot`.
5. Nếu thất bại, xác định callback hoặc processor nào đã cố gọi mạng.
6. Sau khi AOT thành công, chạy native compilation.
7. Khởi chạy executable trong môi trường integration test có các service giả lập hoặc test container cần thiết.
8. Kiểm thử các luồng thực sự cần kết nối ở runtime.

Kết quả mong muốn: **AOT và native compilation không cần dịch vụ nghiệp vụ đang hoạt động; integration test/runtime mới kiểm tra hành vi kết nối**.

Có thể ghi nhận kết quả:

| Hạng mục | Môi trường | Kết quả mong đợi |
|---|---|---|
| `processAot` | Không truy cập dịch vụ nghiệp vụ | Thành công |
| `nativeCompile` | Toolchain và dependency đã sẵn sàng | Thành công |
| Khởi động native app | Không có dịch vụ tùy chọn | App vẫn khởi động nếu kiến trúc cho phép |
| Gọi chức năng cần database | Database test có sẵn | Trả kết quả nghiệp vụ đúng |
| Gọi chức năng cần API ngoài | Mock/test service có sẵn | Timeout, lỗi và retry đúng chính sách |

Không dùng `--offline` của Maven/Gradle một cách máy móc nếu dependency chưa được cache; chế độ offline của build tool kiểm soát việc tải dependency, không phải chính sách tắt mọi kết nối do code ứng dụng tạo ra.

## 16. Dấu hiệu và cách xử lý lỗi phụ thuộc dịch vụ

| Dấu hiệu khi AOT | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| `Connection refused` tới database trong `processAot` | Processor, condition hoặc post-processor mở kết nối | Tìm stack trace, loại bỏ I/O khỏi callback build |
| Timeout HTTP tới Config Server | Cấu hình bootstrap/AOT đang tải remote config | Cung cấp cấu hình build-time cục bộ, tách secret/runtime config |
| `BeanCreationException` cho AOT processor | Processor hoặc dependency không khởi tạo được | Giảm dependency, loại bỏ logic kết nối trong constructor |
| `Condition` trả kết quả khác giữa CI và máy dev | Điều kiện dựa vào trạng thái bên ngoài hoặc env không cố định | Dựa vào property/classpath tường minh và ghi lại AOT environment |
| Thiếu bean khi chạy native | Condition/profile đã loại bean trong build | Build với profile/property phù hợp và kiểm tra generated bean definitions |
| Static initializer thất bại do DNS | Class được khởi tạo trong đường đi AOT | Chuyển I/O khỏi static initializer |
| AOT thành công nhưng app runtime không kết nối được | Runtime service/credential/network chưa sẵn sàng | Kiểm tra runtime config, secret, DNS, timeout và policy |
| Build thành công nhưng startup chậm hoặc thất bại | Công việc ngoài đang diễn ra trong lifecycle runtime | Đo startup riêng, chuyển kết nối sang lazy/on-demand hoặc background |

Đừng sửa lỗi bằng cách tăng timeout vô hạn hoặc mở quyền mạng rộng cho build runner trước khi xác định đoạn mã nào cần kết nối. Nếu callback build đang làm công việc nghiệp vụ, đó thường là vấn đề phân chia trách nhiệm cần sửa trong code.

## 17. Thực hành: loại bỏ truy vấn HTTP khỏi điều kiện AOT

Giả sử một ứng dụng có tính năng `remote-catalog`. Ban đầu, custom condition gửi HTTP request để hỏi catalog service có hoạt động hay không. Khi chạy `processAot` trên CI, service chưa được khởi động và build thất bại.

### Bước 1 — Nhận diện đường gọi

Tìm các đoạn:

- `Condition.matches()`
- `ImportSelector.selectImports()`
- `ImportBeanDefinitionRegistrar`
- `BeanFactoryPostProcessor`
- `BeanFactoryInitializationAotProcessor`
- `BeanRegistrationAotProcessor`
- Constructor/static initializer của các lớp trên

Xác định nơi gọi HTTP, JDBC hoặc đọc secret.

### Bước 2 — Đưa quyết định cấu trúc thành property

Thay truy vấn mạng bằng property `features.remote-catalog.enabled` được cung cấp trong môi trường AOT. Điều kiện chỉ đọc property, không kiểm tra health của service.

### Bước 3 — Tách client runtime

Đăng ký `RemoteCatalogClient` nhưng constructor chỉ chuẩn bị HTTP client cục bộ. Phương thức truy vấn mới thực hiện HTTP khi nghiệp vụ gọi.

### Bước 4 — Chạy AOT khi service bị chặn

~~~bash
./gradlew processAot
~~~

AOT cần thành công dù catalog service không thể truy cập. Sau đó có thể chạy integration test với mock server.

### Bước 5 — Kiểm thử native executable

~~~bash
./gradlew nativeCompile
~~~

Chạy native app và gọi endpoint cần catalog. Xác nhận request chỉ được gửi khi nghiệp vụ yêu cầu, timeout được áp dụng và lỗi service được xử lý theo chính sách.

### Bảng so sánh

| Trước khi sửa | Sau khi sửa |
|---|---|
| Condition gọi HTTP để quyết định bean | Condition đọc property build-time |
| AOT phụ thuộc catalog service | AOT không cần catalog service |
| Kết quả build thay đổi theo health service | Kết quả build tái lập theo source và config |
| Client kết nối ngay khi tạo | Client chỉ kết nối khi nghiệp vụ gọi |
| CI phải bật dịch vụ phụ trợ trước AOT | Chỉ integration test cần mock/test service |

## 18. Checklist thiết kế mã khởi tạo an toàn

Trước khi đưa một integration vào ứng dụng Native Image, hãy trả lời:

1. **Đoạn mã chạy ở pha nào?** AOT build, native compilation, runtime startup hay khi nghiệp vụ được gọi?
2. **Callback nào sẽ gọi đoạn mã đó?** Condition, registrar, post-processor, AOT processor hay lifecycle callback?
3. **Có I/O hoặc side effect không?** HTTP, JDBC, filesystem ngoài build input, DNS, cloud metadata, secret manager, broker?
4. **Kết quả có ổn định không?** Cùng source, toolchain và build configuration có cho cùng bean definitions không?
5. **Có thể thay bằng metadata không?** Property, classpath, manifest, schema snapshot hoặc file versioned?
6. **Dependency của AOT processor có nhẹ không?** Processor có kéo theo service nghiệp vụ hoặc client kết nối tự động không?
7. **Runtime có chính sách lỗi rõ không?** Timeout, retry, circuit breaker, readiness, logging và fallback?
8. **Đã chạy AOT trong môi trường bị chặn dịch vụ chưa?** Nếu chưa, chưa thể kết luận build độc lập với dịch vụ ngoài.

Một nguyên tắc thực dụng: **mã build quyết định cấu trúc từ dữ liệu đã biết; mã runtime tương tác với thế giới bên ngoài**.

## 19. Ghi nhớ

Spring AOT thông thường không khởi tạo toàn bộ bean ứng dụng trong lúc phân tích build. Tuy nhiên, quá trình xử lý cấu hình và đăng ký bean có chạy callback; các AOT processor và dependency của chúng cũng được khởi tạo để tạo đóng góp. Đó là những điểm cần kiểm tra khi build vô tình phụ thuộc database, broker, Config Server hoặc API bên ngoài.

Giữ `Condition`, registrar, `BeanFactoryPostProcessor` và AOT processor **nhanh, xác định, không có side effect và dựa trên metadata**. Tạo client không nên đồng nghĩa với kết nối; trì hoãn I/O đến lúc ứng dụng thực sự cần. Với `@PostConstruct` và lifecycle callback của bean thông thường, nhớ rằng chúng thuộc runtime startup và vẫn có thể ảnh hưởng độ sẵn sàng của native app.

Thiết kế như vậy giúp AOT chạy được trên CI hạn chế mạng, build dễ tái lập, và ứng dụng native chỉ phụ thuộc dịch vụ ngoài ở đúng thời điểm nghiệp vụ cần chúng.

### Tài liệu tham khảo

- Spring Framework — Ahead of Time Optimizations: https://docs.spring.io/spring-framework/reference/core/aot.html
- Spring Boot — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/how-to/aot.html
- Spring Boot Gradle Plugin — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/gradle-plugin/aot.html
- Spring Boot Maven Plugin — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/maven-plugin/aot.html

API, task và cấu hình có thể khác giữa các phiên bản Spring Boot/Spring Framework. Khi áp dụng, hãy đối chiếu tài liệu đúng phiên bản của dự án.
