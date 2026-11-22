# Giới hạn cấu hình động trong chế độ AOT hoặc native image

**Ngữ cảnh:** Spring Framework Testing → Mở rộng và AOT.

Spring cho phép ứng dụng linh hoạt đăng ký bean, chọn cấu hình theo profile, đọc property, quét classpath và tạo proxy khi chạy. Sự linh hoạt này rất hữu ích trong môi trường JVM thông thường, nhưng có giới hạn khi ứng dụng được xử lý bằng **Ahead-of-Time (AOT)** hoặc đóng gói thành **native image**.

AOT chuyển một phần công việc mà Spring thường làm lúc khởi động sang giai đoạn build. Spring phân tích cấu hình, xác định bean và quan hệ phụ thuộc, sau đó sinh mã khởi tạo cùng các runtime hint cần thiết. Native image tiếp tục biên dịch ứng dụng thành executable với phạm vi class, reflection, resource và proxy được xác định trước.

Vì vậy, không phải mọi quyết định có thể thay đổi tùy ý lúc runtime trong JVM đều có thể thay đổi sau khi AOT processing hoặc native-image compilation đã hoàn tất. Điều quan trọng là phân biệt:

- **Cấu hình bean graph:** quyết định bean nào tồn tại, được tạo bằng cách nào và phụ thuộc vào bean nào.
- **Giá trị runtime:** dữ liệu cấu hình mà bean đã được đăng ký có thể đọc khi ứng dụng chạy.
- **Khả năng truy cập runtime:** class, constructor, method, resource hoặc proxy mà native image cần giữ lại để truy cập.

Một ứng dụng AOT vẫn có thể đọc cấu hình môi trường và xử lý dữ liệu thay đổi lúc chạy. Giới hạn chủ yếu xuất hiện khi dữ liệu runtime được dùng để thay đổi cấu trúc ApplicationContext hoặc yêu cầu truy cập những thành phần không được chuẩn bị trong quá trình build.

## 1. AOT và native image thay đổi điều gì?

### 1.1. Khởi tạo Spring theo cách JVM thông thường

Trong một ứng dụng Spring chạy trên JVM, container thường thực hiện nhiều bước khi khởi động:

1. Đọc cấu hình và environment.
2. Tìm các configuration class và component.
3. Đánh giá profile, condition và import.
4. Đăng ký bean definition.
5. Xử lý bean factory post-processor.
6. Tạo bean, inject dependency và tạo proxy.
7. Hoàn tất ApplicationContext.

Một phần công việc như quét classpath, phân tích annotation, suy luận constructor và tạo metadata có thể được thực hiện trong quá trình khởi động.

### 1.2. AOT chuyển công việc phù hợp sang build time

Spring AOT phân tích ApplicationContext trong giai đoạn build và sinh mã hỗ trợ khởi tạo. Mục tiêu là giảm công việc phải làm lúc startup và làm cho cấu trúc ứng dụng dễ được phân tích bởi native-image compiler.

~~~text
Build time
  |
  +--> Đọc cấu hình ứng dụng
  |
  +--> Phân tích component, @Bean, import và condition
  |
  +--> Xác định bean definitions và dependency graph
  |
  +--> Sinh mã khởi tạo / runtime hints
  |
  v
Generated AOT artifacts
  |
  +--> JVM chạy với AOT initializer
  |
  +--> Hoặc native-image compiler tạo executable
                         |
                         v
                    Runtime
~~~

AOT không đơn giản là lưu một ApplicationContext đã được tạo sẵn rồi khôi phục nguyên trạng. Spring tạo mã và metadata để khởi tạo context trong ứng dụng được build.

### 1.3. Native image giới hạn những gì có thể phát hiện lúc runtime

Native-image compiler phân tích đường đi có thể truy cập của chương trình để quyết định thành phần nào cần đưa vào executable. Các hoạt động dựa vào reflection, class loading, resource discovery hoặc dynamic proxy có thể cần hint rõ ràng.

Nếu một class chỉ được tìm thấy bằng tên lấy từ dữ liệu bên ngoài sau khi executable đã được build, compiler có thể không biết class đó cần được giữ lại. Tương tự, một file resource không được đưa vào image có thể không tồn tại ở runtime dù nó có trên máy build.

### 1.4. Phân biệt AOT mode và native image

Hai khái niệm liên quan nhưng không đồng nhất:

| Chế độ | Điều gì xảy ra |
|---|---|
| JVM thông thường | Spring thực hiện nhiều bước cấu hình và khởi tạo lúc startup trên JVM |
| JVM với AOT-generated code | Ứng dụng vẫn chạy trên JVM nhưng dùng mã khởi tạo được sinh trước |
| Native image | Native-image compiler tạo executable từ ứng dụng và các AOT artifacts |
| TestContext AOT | Spring phân tích test ApplicationContext và sinh initializer cho integration test |

Một ứng dụng có thể được kiểm tra với AOT-generated code trên JVM trước khi đầu tư thời gian build native image. Cách này giúp phát hiện nhiều vấn đề cấu hình AOT sớm hơn, nhưng không thay thế việc chạy native executable khi cần xác nhận reflection, resource, proxy và hành vi của runtime native.

## 2. Phân biệt cấu hình cấu trúc với giá trị runtime

Đây là nguyên tắc quan trọng nhất khi thiết kế ứng dụng AOT.

### 2.1. Cấu hình quyết định bean nào tồn tại

Các cơ chế sau thường ảnh hưởng đến bean graph:

- @Profile.
- @Conditional và các condition chuyên biệt.
- @ConditionalOnProperty trong Spring Boot.
- @Import và ImportSelector.
- Component scanning.
- Bean definition được đăng ký bằng API lập trình.
- Cấu hình được chọn dựa trên property hoặc environment.

Trong AOT, các quyết định này được đánh giá khi Spring phân tích context ở build time. Bean graph được sinh ra dựa trên cấu hình nhìn thấy tại thời điểm đó.

Ví dụ:

~~~java
@Configuration
class PaymentConfiguration {

    @Bean
    @Profile("sandbox")
    PaymentGateway sandboxGateway() {
        return new SandboxPaymentGateway();
    }

    @Bean
    @Profile("production")
    PaymentGateway productionGateway() {
        return new HttpPaymentGateway();
    }
}
~~~

Nếu AOT processing chạy với profile sandbox, cấu hình sandbox có thể được đưa vào bean graph được sinh. Không nên kỳ vọng chỉ cần bật profile production sau khi native executable đã được build là executable sẽ tự bổ sung bean production vốn không được đưa vào quá trình AOT.

Nếu cần hai bean graph khác nhau theo profile, hãy xử lý profile trong giai đoạn build và tạo artifact phù hợp cho từng cấu hình, hoặc thiết kế một bean có thể chọn hành vi bằng giá trị runtime mà không thay đổi cấu trúc context.

### 2.2. Giá trị được đọc bởi bean đã đăng ký có thể vẫn thay đổi lúc runtime

Ví dụ:

~~~java
@Component
class CatalogEndpoint {

    private final Environment environment;

    CatalogEndpoint(Environment environment) {
        this.environment = environment;
    }

    URI baseUrl() {
        return URI.create(
                environment.getRequiredProperty("catalog.base-url")
        );
    }
}
~~~

Bean CatalogEndpoint đã được đăng ký trong context. Khi phương thức baseUrl() chạy, nó đọc property từ Environment hiện tại. Giá trị property có thể được cung cấp từ biến môi trường hoặc nguồn cấu hình runtime, tùy cách ứng dụng được triển khai.

Điều này khác với việc dùng property để quyết định bean nào được đăng ký:

~~~java
@Bean
@ConditionalOnProperty(
        name = "catalog.mode",
        havingValue = "sandbox"
)
CatalogGateway sandboxGateway() {
    return new SandboxCatalogGateway();
}
~~~

Condition quyết định bean graph trong quá trình AOT. Vì vậy, không nên đánh đồng “AOT cố định mọi property” với “AOT cố định mọi cấu hình runtime”. Hãy xác định property đang điều khiển việc đăng ký bean hay chỉ cung cấp giá trị cho bean đã tồn tại.

### 2.3. Bảng nhận diện nhanh

| Nhu cầu | Tác động | Cách tiếp cận |
|---|---|---|
| Chọn bean theo @Profile | Thay đổi bean graph | Chọn profile khi AOT processing hoặc tạo artifact riêng |
| Dùng @ConditionalOnProperty để đăng ký bean | Thay đổi bean graph | Condition cần được xác định trong build |
| Đọc URL dịch vụ từ environment trong bean đã đăng ký | Giá trị runtime | Dùng externalized configuration phù hợp |
| Đọc feature flag trong method | Giá trị runtime nếu không làm thay đổi bean graph | Đọc qua configuration service/environment |
| Tải class tùy ý theo tên runtime | Dynamic class loading | Giới hạn danh sách class và cung cấp hints/đảm bảo class có trong image |
| Quét plugin từ thư mục được gắn sau khi build | Dynamic discovery | Dùng registry/plugin model có thiết kế riêng hoặc xử lý plugin ở service bên ngoài |
| Nạp file schema không có trong classpath image | Resource động | Đóng gói resource hoặc dùng filesystem/object storage được hỗ trợ |

## 3. Giới hạn của @Profile và cấu hình theo environment

### 3.1. Profile được đánh giá khi tạo bean definitions

Trong ứng dụng JVM thông thường, profile active được đọc khi Spring tạo context. Các bean có @Profile phù hợp mới được đăng ký.

Trong AOT, Spring cần biết profile nào được active khi phân tích context để sinh mã khởi tạo. Profile đó trở thành một phần của giả định build-time đối với bean graph.

~~~java
@Configuration
class StorageConfiguration {

    @Bean
    @Profile("local")
    StorageClient localStorageClient() {
        return new LocalStorageClient();
    }

    @Bean
    @Profile("cloud")
    StorageClient cloudStorageClient() {
        return new CloudStorageClient();
    }
}
~~~

Nếu AOT build được thực hiện với profile local, executable không nên được xem là một artifact có thể tùy ý chuyển sang profile cloud để có một bean graph hoàn toàn khác.

### 3.2. Nhiều môi trường cần nhiều cấu hình build

Nếu môi trường local, staging và production thực sự cần bean graph khác nhau, có thể:

- Tạo artifact riêng theo profile được dùng trong AOT processing.
- Giữ bean graph giống nhau và đưa khác biệt vào property runtime.
- Dùng một adapter thống nhất rồi cấu hình endpoint hoặc credential lúc chạy.
- Chuyển các thành phần cần thay đổi linh hoạt sang service hoặc plugin boundary riêng.

Chọn phương án theo yêu cầu triển khai. Tạo nhiều native executable có chi phí build và phát hành cao hơn, nhưng cho phép mỗi artifact có cấu hình cấu trúc rõ ràng. Một bean thống nhất với property runtime giảm số artifact nhưng cần kiểm soát tốt việc thay đổi hành vi.

### 3.3. Profile không phải cơ chế feature flag runtime

Không nên dùng @Profile để bật/tắt một chức năng liên tục trong khi native executable đang chạy. Profile chủ yếu chọn cấu hình context khi khởi tạo.

Với feature flag cần thay đổi mà không build lại, dùng một bean đã được đăng ký và đọc giá trị từ nguồn runtime:

~~~java
interface FeatureFlags {
    boolean isEnabled(String name);
}

@Service
class OrderFeature {

    private final FeatureFlags featureFlags;

    OrderFeature(FeatureFlags featureFlags) {
        this.featureFlags = featureFlags;
    }

    boolean supportsNewFlow() {
        return featureFlags.isEnabled("new-order-flow");
    }
}
~~~

Bean FeatureFlags có thể đọc từ property, configuration server hoặc feature flag service. Khi thiết kế như vậy, bean graph không cần thay đổi mỗi khi flag đổi.

## 4. Giới hạn của @Conditional và conditional bean registration

### 4.1. Condition tác động đến bean graph

Spring Boot thường dùng @ConditionalOnProperty, @ConditionalOnClass, @ConditionalOnMissingBean và nhiều condition khác để chọn cấu hình.

~~~java
@Configuration
class ReportConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "reports.export.enabled",
            havingValue = "true"
    )
    ReportExporter reportExporter() {
        return new PdfReportExporter();
    }
}
~~~

Trong quá trình AOT, condition được đánh giá khi context được phân tích. Nếu reports.export.enabled là false ở build time, bean có thể không nằm trong context được sinh.

Đổi property đó thành true sau khi executable đã được tạo không đồng nghĩa Spring có thể tạo lại mọi bean definition đã bị loại khỏi AOT output.

### 4.2. @ConditionalOnClass và classpath là đầu vào build-time

Một condition dựa trên classpath có ý nghĩa ở giai đoạn build:

~~~java
@Configuration
@ConditionalOnClass(name = "com.example.pdf.PdfEngine")
class PdfEngineConfiguration {
    // Bean phụ thuộc PdfEngine.
}
~~~

Nếu thư viện không có trong classpath khi build, cấu hình có thể bị loại. Thêm một JAR vào thư mục runtime sau khi native image đã được tạo không làm class đó tự xuất hiện trong executable.

Với native image, các class cần thiết phải có mặt trong classpath của quá trình native compilation và phải được giữ lại theo reachability/hints.

### 4.3. @ConditionalOnMissingBean và thứ tự cấu hình

Condition dựa trên bean definitions hiện có có thể phụ thuộc vào những cấu hình được import và thứ tự xử lý. AOT phân tích context với tập cấu hình xác định trong build.

Không nên dựa vào việc runtime sẽ thêm một bean bên ngoài AOT output để làm thay đổi kết quả condition. Nếu cần thay thế dependency, hãy chọn cấu hình rõ ràng cho build hoặc dùng một abstraction runtime có bean graph cố định.

## 5. Giới hạn của component scanning và classpath discovery

### 5.1. Component scan được phân tích trước

Trong JVM thông thường, component scanning tìm class theo package và annotation trong classpath. AOT xử lý kết quả scan trong quá trình build và sinh thông tin đăng ký bean.

Vì thế, không nên kỳ vọng một class được copy vào classpath sau khi AOT build sẽ tự được component scan tìm thấy khi ứng dụng chạy. Native image thường không chứa class mới được thêm sau khi biên dịch.

### 5.2. Classpath không phải thư mục plugin runtime tùy ý

Một thiết kế plugin có thể dùng ServiceLoader, reflection hoặc quét package để tìm implementation. Trong JVM thông thường, điều đó có thể hoạt động nếu JAR plugin nằm trong classpath.

Với native image:

- Plugin class cần có mặt trong quá trình native compilation.
- Service provider metadata cần được nhận diện và đóng gói.
- Class được tạo hoặc gọi bằng reflection cần runtime hints phù hợp.
- Resource của plugin phải được đưa vào image hoặc được cung cấp từ nguồn runtime được hỗ trợ.
- Không thể giả định có thể thêm JAR mới vào native executable sau khi build.

Nếu yêu cầu thật sự là tải plugin mới mà không build lại, cân nhắc tách plugin thành process/service riêng hoặc dùng một runtime JVM có khả năng quản lý classpath phù hợp. Native image phù hợp hơn với tập class đã biết trước.

### 5.3. ServiceLoader và resource metadata

Một số thư viện dùng META-INF/services để đăng ký implementation. Native-image toolchain có thể hỗ trợ nhiều pattern discovery phổ biến, nhưng không nên giả định mọi cơ chế discovery tùy chỉnh tự hoạt động.

Khi cần, khai báo resource hints hoặc dùng API runtime hints mà Spring cung cấp. Kiểm tra native executable thực tế để xác nhận service provider được tìm thấy.

## 6. Đăng ký bean bằng API lập trình

### 6.1. BeanDefinitionRegistryPostProcessor và đăng ký động

Một số ứng dụng tạo bean definitions bằng code:

~~~java
class PluginRegistryPostProcessor
        implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {

        // Đọc danh sách plugin rồi đăng ký BeanDefinition.
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
    }
}
~~~

Trong JVM thông thường, post-processor có thể đọc dữ liệu runtime và đăng ký bean theo điều kiện. Nhưng nếu danh sách plugin chỉ có sau khi native executable đã được build, AOT-generated bean graph không thể tự suy ra các bean mới đó.

AOT có các extension point để đóng góp mã khởi tạo và runtime hints. Nếu ứng dụng có logic đăng ký bean tùy chỉnh, cần bảo đảm logic đó được xử lý trong AOT analysis hoặc có AOT contribution phù hợp. Không nên giả định mọi BeanDefinitionRegistryPostProcessor tùy ý đều có thể thay đổi bean graph sau khi native image đã được tạo.

### 6.2. BeanFactoryPostProcessor và thay đổi bean definitions

BeanFactoryPostProcessor có thể sửa bean definitions trước khi bean được tạo. Khi các thay đổi đó ảnh hưởng cấu trúc context, AOT cần nhìn thấy chúng trong quá trình phân tích.

Một post-processor dựa vào thời gian, network response hoặc file xuất hiện sau build để quyết định bean definitions có thể tạo khác biệt giữa AOT context và runtime context. Đây là dấu hiệu thiết kế cần xem lại.

Nếu chỉ cần một giá trị runtime, giữ bean definition ổn định rồi inject một abstraction đọc giá trị đó khi cần. Nếu thật sự cần tạo bean theo plugin list, danh sách plugin phải được biết lúc build hoặc cần một cơ chế AOT integration được thiết kế và kiểm thử riêng.

### 6.3. ApplicationContextInitializer và context customizer

ApplicationContextInitializer, ContextCustomizer và các extension của TestContext có thể thay đổi Environment hoặc cấu hình context. Một số cơ chế có thể được tích hợp vào AOT processing, nhưng không nên mặc định mọi logic tùy chỉnh được gọi theo cùng thời điểm hoặc với cùng dữ liệu trong AOT và runtime.

Khi initializer thay đổi bean definitions, property source hoặc đăng ký component dựa trên dữ liệu động, cần xác định rõ:

- Nó được gọi trong AOT processing, runtime hay cả hai?
- Giá trị đầu vào có giống nhau ở build và runtime không?
- Thay đổi có được ghi vào generated initializer không?
- Có runtime hint cho class/resource mà initializer cần không?
- Có tạo hai lần đăng ký hoặc hai bean khác nhau không?

Nếu không thể chứng minh hành vi ổn định, hãy đơn giản hóa initializer hoặc tách phần quyết định cấu trúc khỏi phần đọc giá trị runtime.

## 7. Reflection và dynamic class loading

### 7.1. Vì sao reflection cần được khai báo?

Native-image compiler phân tích call graph và các đường truy cập tĩnh. Một class được gọi trực tiếp trong code thường dễ được nhận diện hơn một class chỉ được tải bằng tên chuỗi.

Ví dụ:

~~~java
Class<?> type = Class.forName(configuredClassName);
Object instance = type.getDeclaredConstructor().newInstance();
~~~

Nếu configuredClassName chỉ có giá trị khi ứng dụng chạy, compiler có thể không biết class nào cần được giữ lại và constructor nào cần truy cập. Khi chạy native executable, thao tác reflection có thể thất bại nếu thiếu metadata.

### 7.2. Dùng RuntimeHintsRegistrar

Spring cung cấp API runtime hints để khai báo khả năng truy cập cần thiết:

~~~java
class PluginRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.reflection().registerType(
                CsvReportPlugin.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
~~~

Đăng ký hints với cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PluginRuntimeHints.class)
class PluginConfiguration {
}
~~~

Ví dụ trên khai báo quyền truy cập reflection cho class đã biết tại build time. RuntimeHintsRegistrar không làm cho một class bất kỳ được tải từ bên ngoài tự động trở thành một phần của native image. Class vẫn cần có mặt trong build input và được native-image compiler giữ lại.

### 7.3. Đăng ký hint theo nhu cầu tối thiểu

Không nên cấp quyền reflection rộng cho mọi class nếu chỉ cần constructor hoặc một nhóm method. Hãy khai báo đúng member mà thư viện thực sự sử dụng.

Các nhóm hint thường gặp:

- Reflection: constructor, method, field và type metadata.
- Resource: file hoặc pattern resource cần đọc.
- Proxy: interface cần tạo JDK dynamic proxy.
- Serialization: type cần serialize/deserialize theo cơ chế tương ứng.
- JNI: thành phần cần truy cập native interface.

Hạn chế hint quá rộng giúp giảm rủi ro đưa nhiều metadata không cần thiết vào image và làm rõ phụ thuộc runtime của ứng dụng.

### 7.4. Không dùng tên class runtime tùy ý nếu không cần

Nếu số implementation hữu hạn, có thể dùng registry tường minh:

~~~java
Map<String, Supplier<ReportPlugin>> plugins = Map.of(
        "csv", CsvReportPlugin::new,
        "pdf", PdfReportPlugin::new
);

ReportPlugin plugin = plugins.get(pluginName).get();
~~~

Các tham chiếu class và constructor xuất hiện trực tiếp trong code giúp compiler nhận diện reachability tốt hơn so với tải class từ tên tùy ý. Vẫn cần kiểm tra các thư viện và API reflection mà implementation sử dụng.

## 8. Resource hints và file cấu hình

### 8.1. Resource trên classpath không tự động luôn có trong native image

Native image chỉ đóng gói các resource mà quá trình build nhận diện hoặc được khai báo. Một ứng dụng đọc file bằng ClassPathResource có thể hoạt động trên JVM nhưng thất bại trong native executable nếu resource không được đưa vào image.

Ví dụ:

~~~java
Resource schema = new ClassPathResource("schemas/order-v1.json");
~~~

Nếu resource cần thiết không được phát hiện tự động, khai báo hint:

~~~java
class SchemaRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern("schemas/*.json");
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(SchemaRuntimeHints.class)
class SchemaConfiguration {
}
~~~

Pattern cần phù hợp với đường dẫn resource trong classpath. Nếu ứng dụng đọc nhiều loại file, khai báo pattern có phạm vi vừa đủ và xác nhận file thực sự có trong native image.

### 8.2. Phân biệt classpath resource và file system resource

Classpath resource được đóng gói cùng ứng dụng và phù hợp với dữ liệu tĩnh đi kèm artifact.

File system resource là file bên ngoài executable, ví dụ:

- /etc/myapp/application-extra.yml
- File certificate được mount từ secret volume.
- File upload hoặc dữ liệu người dùng.
- File được cập nhật trong runtime.

Native image vẫn có thể đọc file hệ thống nếu môi trường triển khai cung cấp quyền và đường dẫn phù hợp. Runtime hints không đóng gói file ngoài vào image; chúng chủ yếu giúp native executable biết các resource được truy cập theo cơ chế cần hint.

Nếu cấu hình cần thay đổi sau khi build, dùng externalized configuration hoặc file mount có đường dẫn được hỗ trợ, thay vì kỳ vọng thay classpath resource bên trong native image.

### 8.3. Đọc file theo tên động

Ví dụ:

~~~java
Path schemaPath = Path.of(
        environment.getRequiredProperty("schema.path")
);
String schema = Files.readString(schemaPath);
~~~

Đây là truy cập filesystem runtime. File cần tồn tại trong container hoặc host tại thời điểm chạy và process phải có quyền đọc. Nó không nhất thiết cần resource hint vì không phải classpath resource được đóng gói trong image.

Tuy nhiên, nếu path trỏ đến resource bên trong image hoặc được xử lý qua classloader, cần xem lại loại resource và cách truy cập thực tế.

## 9. Dynamic proxy, AOP và proxy hints

### 9.1. Spring tạo proxy cho nhiều cơ chế

Spring có thể dùng proxy cho:

- AOP advice.
- Transaction management.
- Method security.
- Scoped proxy.
- Lazy injection.
- Interface-based client hoặc decorator.
- Một số thư viện tạo proxy qua reflection.

Các proxy được Spring AOT nhận diện trong những pattern được hỗ trợ có thể được chuẩn bị tự động. Nhưng proxy được tạo động bằng thư viện bên ngoài hoặc danh sách interface runtime không thể biết trước có thể cần hint.

### 9.2. JDK dynamic proxy

JDK proxy được tạo từ một tập interface:

~~~java
Object proxy = Proxy.newProxyInstance(
        classLoader,
        new Class<?>[] { PaymentGateway.class },
        invocationHandler
);
~~~

Trong native image, các interface cần proxy phải được nhận diện. Có thể khai báo bằng runtime hints:

~~~java
class PaymentProxyHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.proxies().registerJdkProxy(
                PaymentGateway.class
        );
    }
}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentProxyHints.class)
class PaymentProxyConfiguration {
}
~~~

Hãy khai báo đúng interface combination mà ứng dụng sử dụng. Nếu proxy có nhiều interface, truyền đầy đủ các interface theo API runtime hints của phiên bản Spring đang dùng.

### 9.3. CGLIB và class-based proxy

Class-based proxy có cách tạo khác JDK dynamic proxy. Spring AOT có thể xử lý nhiều trường hợp proxy do Spring quản lý, nhưng thư viện tự tạo subclass hoặc dùng bytecode generation tùy ý có thể không hoạt động như JVM mode.

Nếu một thư viện cần sinh subclass tại runtime, cần kiểm tra khả năng hỗ trợ của native-image toolchain và framework. Không nên giả định thêm JDK proxy hint sẽ giải quyết vấn đề class-based proxy.

### 9.4. Hạn chế tạo proxy theo tập interface runtime tùy ý

Nếu interface list đến từ plugin metadata hoặc cấu hình bên ngoài sau build, native image không thể mặc định chuẩn bị mọi tổ hợp proxy có thể xảy ra.

Giới hạn tập interface, khai báo các tổ hợp cần thiết khi build hoặc thay dynamic proxy bằng registry/adapter tường minh nếu có thể.

## 10. Serialization và dữ liệu được xử lý qua reflection

Một số thư viện serialize/deserialize object dựa vào reflection, constructor, field hoặc annotation. JSON codec, XML binding, object mapper và framework persistence có thể cần metadata tùy trường hợp.

Spring và các integration phổ biến có thể đóng góp runtime hints tự động cho nhiều type đã biết trong bean graph. Nhưng type được tải từ cấu hình hoặc dữ liệu runtime có thể cần hint bổ sung.

Ví dụ nếu một thư viện serialize một DTO theo reflection, hãy xác định:

- Type nào được serialize/deserialize?
- Constructor nào được gọi?
- Field hoặc method nào được truy cập?
- Có generic type hoặc subtype polymorphic nào không?
- Có class được chọn từ discriminator runtime không?
- Hints có được đăng ký ở build time không?

Không nên thêm reflection hint cho toàn bộ package chỉ để làm lỗi biến mất nếu chỉ một số DTO thực sự cần truy cập đặc biệt.

## 11. Cấu hình property và externalized configuration

### 11.1. Property dùng cho bean graph

Property có thể quyết định cấu hình nào được đăng ký:

~~~java
@Configuration
class SearchConfiguration {

    @Bean
    @ConditionalOnProperty(
            name = "search.backend",
            havingValue = "remote"
    )
    SearchClient remoteSearchClient() {
        return new RemoteSearchClient();
    }
}
~~~

Với AOT, giá trị của search.backend tại thời điểm phân tích context ảnh hưởng bean graph được sinh. Nếu deployment muốn thay remote thành local sau build, cần một thiết kế khác hoặc build artifact riêng với điều kiện tương ứng.

### 11.2. Property chỉ cung cấp giá trị cho bean

~~~java
@ConfigurationProperties(prefix = "catalog")
record CatalogProperties(URI baseUrl, Duration timeout) {}

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(CatalogProperties.class)
class CatalogClientConfiguration {

    @Bean
    RestClient catalogRestClient(CatalogProperties properties) {
        return RestClient.builder()
                .baseUrl(properties.baseUrl().toString())
                .build();
    }
}
~~~

Trong ví dụ này, bean configuration được đăng ký trước. Giá trị properties được bind theo environment khi ứng dụng khởi tạo. Cấu hình externalized có thể cung cấp URL và timeout khác nhau cho từng deployment mà không cần thay đổi danh sách bean.

Cần kiểm tra cách AOT processing và runtime environment được thiết lập trong build pipeline của dự án. Không đưa secret production vào build artifact; credential nên được cấp từ secret store hoặc environment runtime phù hợp.

### 11.3. Property source xuất hiện sau build

Nếu ứng dụng cần đọc file cấu hình được mount ở runtime, hãy bảo đảm file đó được nạp bằng cơ chế externalized configuration hỗ trợ của framework/boot và có mặt trong môi trường triển khai.

Không nhầm file property ngoài filesystem với resource classpath. Một file external có thể thay đổi sau build; một classpath resource trong native image thường đã được đóng gói vào executable.

## 12. AOT và Spring TestContext Framework

### 12.1. TestContext cũng có thể được xử lý AOT

Spring TestContext Framework hỗ trợ AOT processing cho integration test. Spring phân tích cấu hình test context và sinh initializer để có thể sử dụng trong AOT test execution hoặc native test scenario tùy toolchain.

Các thành phần có thể ảnh hưởng context test gồm:

- @ContextConfiguration và configuration classes.
- @SpringBootTest và test slice của Spring Boot.
- Active profiles và test properties.
- @Import và nested test configuration.
- Bean overrides và test customizers.
- Context initializer, listener và dynamic property registration.

Những test phụ thuộc vào runtime discovery hoặc trạng thái chỉ có sau khi build cần được xem xét kỹ. TestContext AOT cũng cần một cấu hình có thể phân tích được khi chạy AOT processing.

### 12.2. Cấu hình test phải ổn định giữa AOT processing và test runtime

Giả sử một test context dùng:

~~~java
@SpringBootTest
@ActiveProfiles("integration")
@Import(IntegrationTestConfiguration.class)
class OrderIntegrationTest {
    // ...
}
~~~

Profile và test configuration cần được xác định khi Spring tạo AOT test context. Nếu test runtime cố thay đổi profile hoặc bean graph theo dữ liệu mới không có trong quá trình AOT processing, generated initializer có thể không đại diện cho context mà test kỳ vọng.

Hãy giữ cấu hình test rõ ràng và ổn định. Nếu cần nhiều context khác nhau, khai báo chúng như các test configuration riêng được AOT processing nhận diện.

### 12.3. DynamicPropertySource và dữ liệu chỉ có khi runtime

@DynamicPropertySource thường được dùng để đăng ký property từ Testcontainers, mock server hoặc tài nguyên có endpoint động.

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
}
~~~

Giá trị như mapped port có thể chỉ tồn tại sau khi container khởi động. Khi dùng test AOT, cần kiểm tra phiên bản Spring Boot/Spring Test và cách toolchain hỗ trợ dynamic property source trong quá trình sinh context.

Không nên giả định mọi supplier được đánh giá đúng thời điểm runtime hoặc build time mà không kiểm chứng. Với test dùng Testcontainers, ưu tiên cơ chế tích hợp được hỗ trợ trong phiên bản đang dùng, chẳng hạn service connection nếu phù hợp, hoặc cấu hình tài nguyên theo cách mà AOT test processing có thể nhận diện.

Nếu một property ảnh hưởng bean graph, giá trị của nó cần nhất quán với cấu hình đã được xử lý AOT. Nếu chỉ cung cấp endpoint runtime cho bean đã đăng ký, hãy xác nhận supplier và resource lifecycle hoạt động đúng trong test mode mục tiêu.

### 12.4. Test dùng dynamic classpath hoặc context mutation

Một số test tự đăng ký bean, thay đổi bean definition, tạo class proxy hoặc quét plugin sau khi context đã được khởi tạo. Những test này có thể không tương thích với TestContext AOT nếu generated initializer không mô tả được hành vi đó.

Không nhất thiết phải loại bỏ chúng khỏi toàn bộ suite. Có thể giữ chúng chạy trong JVM test mode thông thường và tách riêng nhóm test tương thích AOT.

### 12.5. @DisabledInAotMode

Spring Test cung cấp **@DisabledInAotMode** để đánh dấu test hoặc test class không chạy trong AOT mode:

~~~java
@DisabledInAotMode("Test requires runtime-generated plugin classes")
class DynamicPluginDiscoveryTests {
    // Chỉ chạy trong mode phù hợp.
}
~~~

Annotation này phù hợp khi test kiểm tra một hành vi runtime động mà AOT mode không hỗ trợ hoặc không phải mục tiêu của test đó. Nó không sửa cấu hình AOT và không biến một ứng dụng không tương thích thành tương thích.

Chỉ dùng khi có lý do cụ thể. Nếu một test là bằng chứng quan trọng cho hành vi production native, nên tìm cách hỗ trợ AOT hoặc viết một test native phù hợp thay vì vô hiệu hóa nó.

@DisabledInAotMode có trong các phiên bản Spring Framework hỗ trợ annotation này; kiểm tra phiên bản Spring Test của dự án trước khi sử dụng. Với framework cũ, cần dùng cơ chế điều kiện test hoặc cấu hình task tương ứng.

## 13. Kiểm tra ứng dụng qua các chế độ khác nhau

Một quy trình kiểm thử AOT nên phân biệt ba mục tiêu.

### 13.1. Test JVM thông thường

Chạy test suite trong JVM mode để xác nhận logic và cấu hình cơ bản:

- Bean được đăng ký đúng.
- Profile và property có hiệu lực như mong đợi.
- Reflection, resource và proxy hoạt động trong JVM.
- Test fixture và external dependency được cô lập.

Đây là nền tảng nhưng chưa chứng minh AOT-generated code hoạt động.

### 13.2. Test với AOT-generated code trên JVM

Chạy AOT processing và thực thi test hoặc ứng dụng bằng generated initializer theo cấu hình build của dự án.

Mục tiêu:

- Phát hiện cấu hình động không được phản ánh trong generated context.
- Xác nhận condition và profile đúng với build-time assumptions.
- Xác nhận test context AOT có thể được tạo.
- Phát hiện những extension point không có AOT contribution cần thiết.

Nếu build tool có task riêng cho application AOT hoặc test AOT, dùng task phù hợp với plugin và phiên bản đang dùng. Không nhầm task xử lý application AOT với task xử lý TestContext AOT.

### 13.3. Test native executable

Khi ứng dụng cần triển khai dưới dạng native image, cần chạy native build và kiểm tra executable trong môi trường gần triển khai.

Tập trung vào:

- Reflection và runtime hints.
- Class reachability.
- Resource đóng gói.
- JDK proxy và AOP.
- Serialization/codec.
- TLS, filesystem và environment.
- Startup, memory và các hành vi runtime quan trọng.

AOT JVM test có thể phát hiện vấn đề cấu hình context nhưng không thay thế native executable test. Native-image compiler có các quy tắc reachability và runtime khác JVM.

## 14. Thiết kế lại cấu hình động để tương thích AOT

### 14.1. Giữ bean graph ổn định, chuyển khác biệt sang strategy

Thay vì đăng ký bean khác nhau theo một property thay đổi lúc runtime, có thể đăng ký một bean facade và chọn strategy dựa trên giá trị runtime.

~~~java
interface StorageStrategy {
    StoredObject store(byte[] content);
}

@Component
class StorageService {

    private final StorageProperties properties;
    private final LocalStorage localStorage;
    private final CloudStorage cloudStorage;

    StorageService(
            StorageProperties properties,
            LocalStorage localStorage,
            CloudStorage cloudStorage) {
        this.properties = properties;
        this.localStorage = localStorage;
        this.cloudStorage = cloudStorage;
    }

    StoredObject store(byte[] content) {
        return switch (properties.mode()) {
            case "local" -> localStorage.store(content);
            case "cloud" -> cloudStorage.store(content);
            default -> throw new IllegalStateException(
                    "Unsupported storage mode");
        };
    }
}
~~~

Cả hai implementation được đăng ký trong bean graph. Giá trị mode quyết định strategy được gọi khi runtime.

Cách này phù hợp khi cả hai implementation đều có mặt trong artifact và native image. Nếu một implementation phụ thuộc thư viện hoặc native feature không thể đóng gói chung, cần artifact riêng hoặc ranh giới service khác.

### 14.2. Dùng registry tường minh thay classpath scan động

Nếu số plugin biết trước, khai báo registry:

~~~java
@Configuration(proxyBeanMethods = false)
class ExporterConfiguration {

    @Bean
    Map<String, Exporter> exporters(
            CsvExporter csv,
            PdfExporter pdf) {

        return Map.of(
                "csv", csv,
                "pdf", pdf
        );
    }
}
~~~

Runtime chỉ chọn key từ registry. Các implementation và dependency đã được biết ở build time.

### 14.3. Tách plugin thành service khi cần mở rộng độc lập

Nếu khách hàng có thể cài plugin mới sau khi ứng dụng được phát hành, native image có thể không phải mô hình triển khai phù hợp cho plugin class động. Có thể tách plugin thành process/service, cung cấp một HTTP/gRPC contract ổn định và để host gọi qua client.

Khi đó, plugin có vòng đời triển khai độc lập; host native image chỉ cần biết client contract. Đổi lại, hệ thống phải xử lý network failure, authentication, versioning và observability.

### 14.4. Đưa cấu hình thay đổi vào Environment hoặc configuration service

Nếu chỉ cần đổi URL, timeout, feature flag hoặc tenant policy, dùng property runtime hoặc service chuyên trách. Không tạo lại ApplicationContext mỗi khi giá trị thay đổi trừ khi thật sự cần.

Một bean có thể đọc property lúc sử dụng hoặc nhận một configuration abstraction có khả năng refresh. Nếu dùng cơ chế refresh động, kiểm tra thư viện và khả năng AOT/native của nó riêng; không phải mọi dynamic refresh extension đều được hỗ trợ tự động.

## 15. Các dấu hiệu cấu hình động có thể gây vấn đề

| Dấu hiệu | Rủi ro trong AOT/native | Hướng xử lý |
|---|---|---|
| @Profile đổi theo môi trường sau build | Bean graph không thay đổi theo profile runtime | Chọn profile khi build hoặc dùng strategy runtime |
| @ConditionalOnProperty phụ thuộc giá trị chỉ có sau deploy | Condition đã được đánh giá khi AOT | Đưa khác biệt vào bean đã đăng ký |
| Class.forName nhận tên class từ database | Class/constructor không được compiler nhận diện | Registry tường minh và reflection hints |
| Quét plugin từ thư mục runtime | Plugin class không có trong native image | Đóng gói plugin trước build hoặc tách service |
| Resource classpath được chọn bằng tên động | Resource không được đóng gói | Resource hints hoặc external filesystem |
| Tạo JDK proxy từ interface list tùy ý | Proxy combination không có metadata | Khai báo proxy hints cho tập interface đã biết |
| BeanDefinitionRegistryPostProcessor đọc dữ liệu runtime | Generated bean graph thiếu bean | AOT contribution hoặc thiết kế lại registry |
| Test thay đổi context sau khi AOT initializer được tạo | Test runtime khác context đã phân tích | Test config tường minh hoặc tách test khỏi AOT mode |
| @DynamicPropertySource lấy port động | Timing/lifecycle có thể khác trong test AOT | Dùng integration được hỗ trợ và xác nhận trong AOT test |
| Thêm JAR sau khi native executable đã build | Class không nằm trong image | Build lại image hoặc dùng process/service riêng |

## 16. Các lỗi thường gặp và cách chẩn đoán

### Bean không tồn tại trong native executable

Kiểm tra condition, active profile và property được dùng khi AOT processing. Xem bean có được đăng ký trong JVM context thông thường nhưng bị loại trong generated context không.

Nếu bean cần có trong mọi deployment, tránh dùng condition build-time để loại nó khỏi bean graph.

### Đổi SPRING_PROFILES_ACTIVE nhưng bean không đổi

Profile dùng để lựa chọn bean definitions đã được đánh giá khi AOT processing. Chọn profile phù hợp trước khi build hoặc thiết kế bean graph ổn định với runtime strategy.

### ClassNotFoundException hoặc reflection failure

Xác định class có nằm trong build classpath không, có được reachability analysis giữ lại không và constructor/method cần reflection có hint chưa. Runtime hint không thể đưa một JAR chưa có trong native build vào executable.

### Không tìm thấy resource

Phân biệt classpath resource với file system resource. Nếu resource nằm trong classpath, thêm resource hint khi cần và xác nhận pattern đúng. Nếu file là external, kiểm tra mount, path và quyền truy cập trong container.

### Proxy tạo được trên JVM nhưng lỗi trong native image

Xác định proxy là JDK dynamic proxy, class-based proxy hay proxy do thư viện ngoài Spring tạo. Kiểm tra Spring AOT có xử lý pattern đó không và khai báo proxy hints nếu cần. Với CGLIB/bytecode generation tùy ý, xác nhận khả năng hỗ trợ của native-image toolchain.

### TestContext AOT không dùng được test configuration

Kiểm tra cấu hình test được import rõ ràng, bean definitions có được nhìn thấy trong AOT processing và test có dùng dynamic registration không được hỗ trợ. Không giả định một test chạy tốt ở JVM mode sẽ tự động chạy được trong TestContext AOT.

### Giá trị DynamicPropertySource không đúng

Kiểm tra thời điểm container/mock server khởi động, thời điểm supplier được đánh giá và vòng đời của context. Không lưu một mapped port cũ trong generated initializer rồi kỳ vọng nó vẫn đúng sau khi tài nguyên được tạo lại.

### Test bị bỏ qua trong AOT mode

Nếu dùng @DisabledInAotMode, đọc reason và xác định test đang kiểm tra hành vi nào. Annotation chỉ bỏ qua test trong AOT mode; nó không chứng minh ứng dụng native không có lỗi ở hành vi đó.

## 17. Chiến lược kiểm thử cấu hình động

Có thể chia test theo mục tiêu thay vì cố chạy cùng một kịch bản ở mọi mode.

| Nhóm test | Mục tiêu | Môi trường |
|---|---|---|
| Unit test cấu hình/strategy | Kiểm tra logic chọn strategy và giá trị runtime | JVM |
| Context test thông thường | Kiểm tra bean graph theo profile/property | JVM Spring Test |
| AOT context test | Kiểm tra generated initializer và cấu hình đã phân tích | JVM với AOT artifacts |
| Native integration test | Kiểm tra reflection, resource, proxy và codec trong executable | Native image |
| Deployment smoke test | Kiểm tra environment, secret, filesystem và network thực tế | Môi trường gần production |

Ví dụ, nếu ứng dụng hỗ trợ cả profile local và cloud, cần test từng bean graph trong JVM context thông thường. Nếu chỉ build một native artifact cho profile cloud, AOT/native test cần xác nhận artifact cloud có đầy đủ bean và runtime hints. Không nên kỳ vọng một executable cloud cũng tự có bean local nếu bean đó bị loại khi AOT processing.

## 18. Quy trình làm việc khi chuyển ứng dụng sang AOT/native

### Bước 1: Liệt kê các điểm cấu hình động

Tìm các cơ chế:

- @Profile và @Conditional.
- @ConditionalOnProperty, @ConditionalOnClass.
- ImportSelector và ImportBeanDefinitionRegistrar.
- BeanDefinitionRegistryPostProcessor.
- Class.forName, reflection và ServiceLoader.
- Classpath/resource scanning.
- Proxy creation và bytecode generation.
- @DynamicPropertySource trong integration test.
- Runtime property source và external config.

Phân loại mỗi cơ chế là build-time structural decision hay runtime value.

### Bước 2: Xác định giả định build-time

Ghi lại profile, property và dependency có ảnh hưởng bean graph. Đảm bảo CI AOT build dùng đúng tập đầu vào mà deployment artifact yêu cầu.

Không đưa credential production hoặc secret vào AOT build. Chỉ những giá trị cần thiết cho cấu trúc bean mới nên tham gia quyết định build-time.

### Bước 3: Chạy AOT processing và xem lỗi

Dùng task AOT phù hợp với build tool/plugin. Đọc lỗi để xác định cấu hình nào không thể phân tích, extension nào cần AOT contribution hoặc type nào cần hint.

Không giải quyết mọi lỗi bằng cách thêm reflection hint rộng. Có lỗi thuộc bean registration, condition hoặc runtime value chứ không phải reflection.

### Bước 4: Bổ sung runtime hints

Đăng ký reflection, resource, proxy hoặc serialization hints cho các thành phần cần truy cập động nhưng đã biết tại build time. Giữ hint ở cấu hình/module sở hữu type đó để dễ bảo trì.

### Bước 5: Chạy test AOT trên JVM

Xác nhận generated context có cùng bean graph và hành vi mong đợi. Test các profile/property đã chọn cho artifact.

### Bước 6: Build và chạy native executable

Kiểm tra startup, request quan trọng, serialization, resource loading, proxy, filesystem và network trong native executable. Dùng môi trường gần deployment để phát hiện khác biệt thực tế.

### Bước 7: Kiểm tra test bị loại hoặc tách khỏi AOT mode

Nếu có test dùng dynamic runtime behavior không phù hợp AOT, ghi rõ lý do và giữ test đó chạy trong JVM mode phù hợp. Bảo đảm hành vi production quan trọng vẫn có test thay thế ở mức phù hợp.

## 19. Nguyên tắc thực hành

1. Phân biệt AOT-generated code trên JVM với native image; hai chế độ liên quan nhưng không giống nhau.
2. Xác định property đang thay đổi bean graph hay chỉ cung cấp giá trị cho bean đã tồn tại.
3. Xem @Profile và conditional bean registration là quyết định cần được biết trong AOT processing.
4. Không kỳ vọng đổi profile runtime sẽ tạo thêm bean đã bị loại khỏi generated context.
5. Giữ classpath và tập plugin cần thiết ổn định trước native compilation.
6. Dùng registry tường minh khi tập implementation hữu hạn.
7. Dùng RuntimeHintsRegistrar và @ImportRuntimeHints cho reflection, resource hoặc proxy cần khai báo.
8. Không nhầm runtime hints với cơ chế đưa JAR hoặc class mới vào native executable.
9. Phân biệt classpath resource được đóng gói với file system resource được mount lúc runtime.
10. Kiểm tra bean registration post-processor và context initializer có AOT integration phù hợp.
11. Kiểm tra @DynamicPropertySource theo phiên bản và vòng đời test resource thực tế.
12. Dùng @DisabledInAotMode có lý do cụ thể khi một test không phù hợp AOT mode.
13. Chạy test JVM, AOT context và native executable theo các mục tiêu riêng.
14. Giữ secret và cấu hình nhạy cảm ở runtime, không đóng gói vào artifact.
15. Khi cần thay đổi cấu trúc ứng dụng sau deploy, cân nhắc một ranh giới plugin/service riêng thay vì phụ thuộc dynamic class loading trong native image.

AOT và native image không loại bỏ khả năng cấu hình runtime; chúng yêu cầu cấu trúc ứng dụng và những khả năng truy cập cần thiết được biết rõ hơn trong giai đoạn build. Bean graph, profile và condition cần ổn định theo artifact được tạo. Giá trị environment, endpoint, timeout và feature flag vẫn có thể thay đổi khi chạy nếu chúng chỉ điều khiển hành vi của các bean đã được đăng ký. Phân biệt hai nhóm này, khai báo runtime hints đúng chỗ và kiểm thử riêng AOT context với native executable sẽ giúp ứng dụng giữ được tính linh hoạt cần thiết mà vẫn tương thích với mô hình build-time analysis.

