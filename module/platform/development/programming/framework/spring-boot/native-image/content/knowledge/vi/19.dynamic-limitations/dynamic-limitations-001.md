# Classpath cố định và hệ quả đối với plugin được tải sau khi triển khai

Một ứng dụng Java chạy trên JVM thường có thể mở rộng sau khi triển khai: đặt thêm một JAR vào thư mục plugin, thêm đường dẫn vào classpath, tạo `URLClassLoader` rồi nạp class mới. Mô hình này phù hợp với hệ thống cần cài plugin mà không build lại ứng dụng. Với **GraalVM Native Image**, cách tiếp cận đó thay đổi đáng kể.

Native Image phân tích và biên dịch ứng dụng ở build time theo **closed-world assumption**. Các class, dependency và bean definition cần thiết phải được biết khi tạo executable. Vì vậy, **classpath của ứng dụng native được cố định tại build time**; việc chép một JAR plugin mới vào thư mục sau khi triển khai không tự làm cho các class trong JAR xuất hiện trong executable.

Trong module **`SPRING_BOOT_NATIVE_IMAGE`**, bài học này giải thích giới hạn đó và hệ quả với plugin architecture của Spring Boot. Bạn sẽ phân biệt dynamic lookup của class đã được đóng gói với việc nạp class hoàn toàn mới, hiểu vai trò của `ServiceLoader` và Spring AOT, rồi chọn kiến trúc phù hợp khi sản phẩm cần mở rộng sau khi phát hành.

> **Phạm vi:** nội dung mô tả mô hình thông thường của Spring Boot AOT và Native Image. Một số bản GraalVM mới có tùy chọn thử nghiệm cho runtime class loading; đây là cơ chế nâng cao với giới hạn riêng, không đồng nghĩa Native Image có classpath mở như JVM. Hãy kiểm tra tài liệu đúng phiên bản GraalVM và Spring Boot trước khi dựa vào tính năng thử nghiệm trong production.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích closed-world assumption và lý do classpath native được cố định.
- Phân biệt class đã có trong image nhưng được tìm bằng tên với class bytecode chỉ xuất hiện sau deployment.
- Phân tích vì sao plugin JAR mới không thể được nạp như trên JVM thông thường.
- Hiểu giới hạn của `Class.forName`, `URLClassLoader`, `ServiceLoader` và Spring bean discovery.
- Thiết kế plugin được biết ở build time nhưng có thể được lựa chọn bằng cấu hình runtime.
- Chọn giữa native image variants, JVM host, process/container riêng hoặc extension DSL.
- Nhận biết các tính năng runtime class loading thử nghiệm và những rủi ro đi kèm.

## 2. Classpath cố định có nghĩa là gì?

Khi build Native Image, builder đọc bytecode của ứng dụng và các dependency trên classpath/module path. Static analysis bắt đầu từ entry point, theo dõi các đường gọi có thể đạt tới và quyết định class, method, field cùng tài nguyên nào cần đưa vào binary.

Kết quả là một executable độc lập chứa phần code/runtime cần thiết. Khi chạy, executable không khởi động một JVM đầy đủ để tiếp tục đọc một classpath JAR tùy ý như lệnh `java -cp`.

~~~mermaid
flowchart TD
    A["Mã ứng dụng + dependency JAR"] --> B["Classpath tại build time"]
    B --> C["Spring AOT phân tích ApplicationContext"]
    C --> D["Native Image reachability analysis"]
    D --> E["Native executable"]
    E --> F["Runtime: chạy code đã được đưa vào image"]
    G["Plugin.jar mới sau deployment"] --> H["Không tự được thêm vào executable"]
    H --> I["Không thể nạp như plugin JVM thông thường"]
~~~

Classpath cố định không có nghĩa mọi class trên build classpath đều được giữ lại. Native Image vẫn có thể loại bỏ phần không reachable. Để một class được gọi động theo tên, ứng dụng cần bảo đảm class đó nằm trong tập class đã biết và có metadata phù hợp cho thao tác dynamic access.

| Khái niệm | Ý nghĩa |
|---|---|
| Build classpath | Các thư mục/JAR/module mà builder nhìn thấy khi tạo executable |
| Reachability | Class/member nào có thể được gọi và cần được giữ trong binary |
| Runtime classpath | Với JVM truyền thống, danh sách vị trí class loader có thể tìm kiếm khi chạy; Native Image không cung cấp mô hình mở tương đương cho JAR tùy ý được thêm sau build |

## 3. Vì sao Native Image dùng mô hình này?

Native Image hướng đến executable có startup nhanh và mức dùng bộ nhớ thấp. Để tối ưu, builder cần biết trước phần lớn code có thể được thực thi. Nhờ đó, nó có thể:

- Phân tích call graph và loại bỏ code không reachable.
- Biên dịch Java bytecode thành mã máy trong quá trình build.
- Đưa runtime support và dữ liệu cần thiết vào executable.
- Chuẩn bị metadata cho những truy cập động đã được khai báo.

Nếu ứng dụng được phép nạp bất kỳ JAR nào sau khi chạy, builder không thể biết trước toàn bộ bytecode, dependency graph, reflection usage và class initialization của plugin đó. Nhiều tối ưu hóa dựa trên closed world sẽ mất hiệu lực hoặc cần cơ chế runtime phức tạp hơn.

Do đó, mô hình plugin phải được thiết kế quanh một trong hai giả định:

1. **Tập plugin được biết khi build:** các implementation và dependency được đưa vào classpath trước khi tạo image.
2. **Tập plugin thực sự mở sau deployment:** host phải hỗ trợ nạp code mới, hoặc plugin chạy ở một runtime/process khác có khả năng đó.

Chỉ thêm reflection metadata không biến giả định thứ hai thành giả định thứ nhất.

## 4. Phân biệt lookup class động và nạp class mới

Hai tình huống sau có vẻ tương tự nhưng khác nhau về yêu cầu đối với runtime.

### 4.1. Tìm class đã có trong image

~~~java
String className = "com.example.plugins.CsvExportPlugin";
Class<?> pluginType = Class.forName(className);
~~~

Nếu `CsvExportPlugin` đã có trên build classpath, được giữ trong image và được đăng ký metadata cần thiết, việc tìm class theo tên có thể hoạt động trong Native Image.

Tên class là chuỗi động không tự động làm class mới xuất hiện. Native Image cần biết trước kiểu được truy cập; nếu class không nằm trong image hoặc thiếu registration, runtime có thể báo `ClassNotFoundException` hoặc lỗi missing registration tùy đường truy cập và phiên bản.

### 4.2. Đọc bytecode từ JAR mới

~~~java
URL pluginJar = Path.of("plugins", "customer-plugin.jar")
        .toUri().toURL();

try (URLClassLoader loader = new URLClassLoader(
        new URL[]{pluginJar},
        Thread.currentThread().getContextClassLoader())) {
    Class<?> pluginType = loader.loadClass(
            "com.customer.plugin.CustomerPlugin");
}
~~~

Trong JVM truyền thống, class loader có thể tìm class trong JAR đó. Với Native Image theo cấu hình thông thường, việc thêm JAR sau build không làm bytecode của `CustomerPlugin` được tích hợp vào executable. Chỉ đăng ký reflection cho một tên class không cung cấp bytecode của class đó.

| Tình huống | JVM thông thường | Native Image thông thường |
|---|---|---|
| `Class.forName` cho class đã có trong ứng dụng | Có thể hoạt động | Có thể hoạt động nếu class được giữ và metadata phù hợp |
| Reflection gọi method/field của class đã biết | Có thể hoạt động theo quyền truy cập | Cần hints phù hợp nếu builder không suy ra được |
| Thêm JAR vào thư mục sau deployment | Có thể nạp qua class loader thích hợp | Không tự thêm JAR vào classpath của image |
| Nạp class mới từ bytecode tùy ý | Có thể qua custom class loader | Không có trong mô hình mặc định; có tùy chọn thử nghiệm riêng ở một số GraalVM |

## 5. Vì sao metadata reflection không giải quyết plugin JAR mới?

Reachability metadata mô tả những thành phần động của **code mà Native Image builder đã biết**. Metadata có thể khai báo:

- Class nào được truy cập qua reflection.
- Constructor, method hoặc field nào cần giữ.
- Resource nào cần được đọc từ classpath.
- Dynamic proxy, JNI hoặc serialization nào cần hỗ trợ.

Ví dụ, metadata reflection có thể giúp giữ constructor của class `CsvExportPlugin` đã có trong dependency. Nhưng metadata không chứa toàn bộ bytecode và dependency mới của một plugin chỉ được cài sau deployment.

~~~text
Plugin có trên build classpath
    + class reachable hoặc được đăng ký
    + reflection metadata phù hợp
    -> có thể dùng trong native executable

Plugin JAR chỉ được chép vào sau deployment
    + reflection metadata cho tên class
    -> vẫn thiếu bytecode/dependency của plugin
~~~

Nếu plugin không được đưa vào build, thêm `reflect-config.json`, `RuntimeHints` hoặc `@RegisterReflectionForBinding` cho tên class không thể thay thế bước đưa plugin code vào image.

## 6. Hệ quả với Spring AOT và bean definitions

Spring Boot thường tạo ApplicationContext linh hoạt ở runtime: component scan, auto-configuration, `@Profile`, `@ConditionalOnProperty` và các registry callback có thể ảnh hưởng bean nào được đăng ký.

Khi chạy AOT/native, Spring phân tích ApplicationContext ở **build time** và sinh code/metadata để khởi tạo context. Những quyết định về bean definition phải ổn định theo classpath và Environment dùng khi AOT.

Điều đó kéo theo:

- Classpath và các auto-configuration module phải có mặt khi AOT/build.
- Bean definitions không thể tùy ý thay đổi theo một plugin JAR được thêm sau deployment.
- Điều kiện ảnh hưởng sự hiện diện của bean, như `@Profile` và `@ConditionalOnProperty`, được đánh giá trong quá trình AOT.
- Plugin cần được Spring quản lý phải có registration path mà AOT nhận diện.

### Profile và conditional không phải công tắc plugin runtime

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "plugins.csv",
        name = "enabled",
        havingValue = "true")
class CsvPluginConfiguration {

    @Bean
    CsvExportPlugin csvExportPlugin() {
        return new CsvExportPlugin();
    }
}
~~~

Trong ứng dụng JVM thông thường, property có thể được đánh giá khi ApplicationContext khởi động. Với Spring AOT, điều kiện được đánh giá trong quá trình build AOT; không nên kỳ vọng thay `plugins.csv.enabled` sau deployment sẽ làm một bean definition mới xuất hiện trong native context.

Nếu muốn bật/tắt plugin đã đóng gói bằng cấu hình runtime, hãy đăng ký các plugin đã biết trong context rồi để một registry/service lựa chọn implementation được phép chạy. Cách đó thay đổi **lựa chọn nghiệp vụ**, không thay đổi tập bean definitions.

### Các cách đăng ký bean cần kiểm tra riêng

Spring Framework AOT không thể chuyển mọi thao tác thay đổi container thành mã khởi tạo tĩnh. Tài liệu AOT nêu một số trường hợp cần chú ý:

- Bean definition có instance supplier do ứng dụng tự gắn (lambda hoặc method reference) không thể được chuyển đổi ahead-of-time theo cách thông thường.
- Singleton được thêm trực tiếp bằng `registerSingleton` không thể được AOT chuyển đổi thành bean definition generated.
- Nếu bean được đăng ký programmatically, cần dùng extension point và AOT contribution phù hợp để Spring có thể xử lý cả ở build time.

Vì vậy, một plugin JAR đã có trong classpath vẫn có thể không hoạt động đúng nếu cách đăng ký bean của nó chỉ diễn ra bằng callback động mà AOT không xử lý. Hãy kiểm tra cả **plugin bytecode có trong build** lẫn **cách Spring đăng ký plugin bean**.

## 7. Plugin có sẵn từ build time: dùng ServiceLoader

`ServiceLoader` là cơ chế Java tiêu chuẩn để tìm implementation của một service interface. Nó hữu ích khi tập provider được đóng gói cùng ứng dụng.

Định nghĩa extension point:

~~~java
package com.example.export;

public interface ExportPlugin {
    String id();
    byte[] export(ExportRequest request);
}
~~~

Một implementation:

~~~java
package com.example.export.csv;

public class CsvExportPlugin implements ExportPlugin {

    @Override
    public String id() {
        return "csv";
    }

    @Override
    public byte[] export(ExportRequest request) {
        // Tạo nội dung CSV.
        return new byte[0];
    }
}
~~~

Provider có thể được khai báo bằng file `META-INF/services/com.example.export.ExportPlugin` trong JAR:

~~~text
com.example.export.csv.CsvExportPlugin
com.example.export.pdf.PdfExportPlugin
~~~

Ứng dụng:

~~~java
ServiceLoader<ExportPlugin> plugins =
        ServiceLoader.load(ExportPlugin.class);

for (ExportPlugin plugin : plugins) {
    System.out.println(plugin.id());
}
~~~

Để dùng trong Native Image:

1. Đưa tất cả provider JAR cần thiết vào build classpath.
2. Đảm bảo file service descriptor và provider được Native Image nhận diện.
3. Kiểm tra reachability metadata của thư viện hoặc cấu hình service registration theo phiên bản Native Image.
4. Chạy test trong native executable để xác nhận provider thật sự được phát hiện.

`ServiceLoader` có thể phát hiện provider đã được đóng gói và đăng ký khi build. Nó **không** làm cho provider trong một JAR mới chép vào thư mục sau deployment tự xuất hiện. Service descriptor là metadata discovery; nó không thể bổ sung bytecode vào một native executable đã được tạo.

## 8. Plugin Spring đã biết: đăng ký trước, lựa chọn sau

Nếu số lượng plugin được xác định ở release time nhưng người vận hành cần bật/tắt từng plugin, có thể đưa tất cả implementation vào image và đăng ký bean definitions ổn định.

Interface:

~~~java
public interface PaymentPlugin {
    String providerId();
    PaymentResult pay(PaymentRequest request);
}
~~~

Hai implementation đã biết:

~~~java
@Component
class CardPaymentPlugin implements PaymentPlugin {
    @Override
    public String providerId() {
        return "card";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        // Xử lý thanh toán thẻ.
        return PaymentResult.approved();
    }
}
~~~

~~~java
@Component
class BankTransferPlugin implements PaymentPlugin {
    @Override
    public String providerId() {
        return "bank-transfer";
    }

    @Override
    public PaymentResult pay(PaymentRequest request) {
        // Xử lý chuyển khoản.
        return PaymentResult.pending();
    }
}
~~~

Registry chọn implementation từ cấu hình runtime:

~~~java
@Service
public class PaymentPluginRegistry {

    private final Map<String, PaymentPlugin> plugins;
    private final Set<String> enabledProviders;

    public PaymentPluginRegistry(
            List<PaymentPlugin> availablePlugins,
            PluginSettings settings) {
        this.plugins = availablePlugins.stream()
                .collect(Collectors.toUnmodifiableMap(
                        PaymentPlugin::providerId,
                        Function.identity()));
        this.enabledProviders = Set.copyOf(settings.enabledProviders());
    }

    public PaymentPlugin get(String providerId) {
        if (!enabledProviders.contains(providerId)) {
            throw new IllegalArgumentException("Provider is disabled");
        }
        PaymentPlugin plugin = plugins.get(providerId);
        if (plugin == null) {
            throw new IllegalArgumentException("Unknown provider");
        }
        return plugin;
    }
}
~~~

Trong ví dụ này, tập class/bean đã cố định ở build time. Cấu hình `enabledProviders` chỉ quyết định implementation nào được sử dụng. Không cần thêm bean definition sau khi native executable chạy.

Nếu cấu hình thay đổi sau khi context đã khởi tạo, registry có thể cần cơ chế refresh/reload dữ liệu cấu hình; nhưng việc đó vẫn không thể tạo implementation class mới không có trong image.

## 9. Khi plugin JAR phải được cài sau deployment

Nếu yêu cầu sản phẩm là khách hàng có thể tải plugin JAR mới lên server và host phải nạp nó mà không build lại, cần xem xét lại kiến trúc runtime. Có một số lựa chọn.

### 9.1. Chạy host bằng JVM

Giữ host/plugin manager trên JVM để tận dụng class loader, `URLClassLoader`, module layer hoặc plugin framework tương thích. Đây là lựa chọn trực tiếp khi hệ sinh thái plugin cần nạp class/JAR tùy ý sau deployment.

Ưu điểm:

- Mô hình classpath và class loader quen thuộc.
- Có thể cài hoặc cập nhật plugin mà không build lại host binary.
- Nhiều thư viện plugin JVM đã được thiết kế quanh cơ chế này.

Đổi lại, ứng dụng không còn nhận đầy đủ lợi ích startup/memory của native executable cho host process. Nếu workload chính phù hợp native nhưng plugin manager cần JVM, có thể tách riêng hai thành phần.

### 9.2. Chạy plugin trong process/container riêng

Đóng gói host thành native executable, còn mỗi plugin chạy trong JVM hoặc runtime phù hợp riêng. Host gọi plugin qua một protocol ổn định:

- HTTP/REST.
- gRPC.
- Message broker.
- IPC hoặc protocol nội bộ.

~~~mermaid
flowchart LR
    A["Native Spring Boot host"] --> B["Plugin API / protocol"]
    B --> C["Plugin A: JVM process"]
    B --> D["Plugin B: JVM process"]
    B --> E["Plugin C: container riêng"]
~~~

Ưu điểm:

- Host vẫn có thể hưởng lợi từ Native Image.
- Plugin có vòng đời deploy/rollback độc lập.
- Có thể dùng ngôn ngữ/runtime khác cho plugin.
- Lỗi hoặc rò rỉ bộ nhớ của plugin có thể được cô lập ở process boundary.

Đổi lại, cần thiết kế API, authentication, timeout, retry, observability và xử lý lỗi mạng. Không nên dùng Java object serialization nội bộ làm protocol công khai giữa các phiên bản plugin; hãy định nghĩa schema/API có version.

### 9.3. Tạo native image variant cho từng tập plugin

Nếu plugin set chỉ thay đổi khi phát hành, tạo các build variant:

~~~text
application-base + plugin-csv  -> app-csv-native
application-base + plugin-pdf  -> app-pdf-native
application-base + plugin-all  -> app-full-native
~~~

Mỗi variant có classpath/AOT output/metadata tương ứng. Có thể xây dựng pipeline tự động để chọn dependencies theo profile build, nhưng phải nhớ profile native/AOT được quyết định lúc build.

Ưu điểm là mỗi executable chỉ mang plugin cần thiết. Nhược điểm là số artifact cần build, kiểm thử, lưu trữ và phát hành tăng lên.

### 9.4. Dùng DSL hoặc scripting engine

Nếu nhu cầu mở rộng chủ yếu là **quy tắc nghiệp vụ** (công thức giá, mapping, workflow, điều kiện), không nhất thiết phải cho phép plugin viết Java tùy ý. Có thể định nghĩa:

- JSON/YAML schema cho rule.
- Expression language với tập toán tử giới hạn.
- Workflow definition.
- Template hoặc mapping specification.
- Script trong một interpreter đã được đóng gói và kiểm thử với Native Image.

Trong mô hình này, file rule/script mới là dữ liệu được đọc lúc runtime; interpreter là code đã có trong image. Tuy nhiên, khả năng thực thi script phụ thuộc interpreter và runtime cụ thể. Không phải mọi JavaScript/Groovy/Kotlin scripting engine đều tự động tương thích Native Image.

Hãy xác định giới hạn ngôn ngữ, quyền truy cập file/network, timeout, quota và validation của script. Không coi DSL là cách an toàn để chạy bytecode Java tùy ý.

## 10. Runtime class loading thử nghiệm của GraalVM

Tài liệu GraalVM mới có mô tả **experimental support for run-time class loading**. Ở các bản hỗ trợ tính năng này, có thể bật bằng tùy chọn build:

~~~bash
native-image \
  -H:+UnlockExperimentalVMOptions \
  -H:+RuntimeClassLoading \
  -H:-UnlockExperimentalVMOptions \
  -jar app.jar app
~~~

Khi bật, class loader có thể định nghĩa class từ bytecode qua `ClassLoader.defineClass`. Tính năng này hướng đến trường hợp ứng dụng/thư viện tạo bytecode sau khi executable khởi động, ví dụ generated proxy có bytecode chỉ có lúc runtime.

### Đây không phải classpath mở như JVM

Tùy chọn thử nghiệm này có các giới hạn quan trọng theo tài liệu GraalVM:

- Không hỗ trợ parallel class loading.
- `URLClassLoader` và việc nạp class từ JDK hoặc application class loader có thể cần cấu hình bổ sung.
- Class được nạp lúc runtime có thể liên kết tới class đã có trong image, nhưng static analysis có thể loại bỏ method/static field của class build-time mà plugin cần; có thể cần `-H:Preserve=package=...`.
- Bật runtime class loading có thể tăng image size và memory usage.
- Không thể kết hợp với predefined classes.
- Việc bật `-H:+RuntimeClassLoading` không tự giải quyết mọi dependency, resource, reflection hoặc classloader isolation của plugin framework.

Vì đây là tính năng **experimental**, không nên xem nó là mặc định được Spring Boot AOT bảo đảm cho plugin JAR tùy ý. Trước khi sử dụng, hãy làm prototype trên đúng GraalVM version, kiểm tra classloader topology, dependency linking, parallelism và memory; sau đó mới quyết định có phù hợp với production hay không.

### Predefined classes là một cơ chế khác

GraalVM còn có cơ chế **predefined classes** dựa trên tracing agent: agent ghi nhận bytecode của class được định nghĩa trong lần chạy JVM, rồi Native Image có thể cung cấp class đã ghi nhận khi runtime yêu cầu class có cùng tên và bytecode.

Cơ chế này là best-effort cho một số ứng dụng legacy, metadata không được thiết kế để viết thủ công và không bảo đảm hoạt động cho mọi plugin. Nó không phải cơ chế để cài một plugin có bytecode khác sau khi image đã build. Tính năng predefined classes cũng không thể kết hợp với tùy chọn runtime class loading nêu trên.

## 11. Vì sao chỉ thêm plugin JAR vào Docker image cũng chưa đủ?

Giả sử Dockerfile copy thêm plugin:

~~~dockerfile
FROM eclipse-temurin:21-jre
COPY app-native /app/app
COPY plugins/ /app/plugins/
ENTRYPOINT ["/app/app"]
~~~

Thư mục `/app/plugins/` có thể tồn tại trong container, nhưng điều đó **không tự thêm bytecode của các JAR vào native executable**. Nếu executable được build khi các plugin chưa có trong classpath, việc copy JAR sau đó không làm Native Image phân tích lại hoặc mở classpath.

Tương tự, các cách sau không biến native executable thành JVM:

- Thay biến môi trường `CLASSPATH`.
- Đặt `-Djava.class.path=/app/plugins/*`.
- Thêm JAR vào thư mục hiện có.
- Đặt file `META-INF/services` mới cạnh executable.
- Thêm reflection JSON sau khi binary đã được tạo.

Các file này có thể có ý nghĩa với một JVM hoặc một quy trình build mới; chúng không thay đổi code đã biên dịch bên trong native executable hiện có.

## 12. Quy trình thiết kế plugin native có kiểm soát

Nếu chọn mô hình plugin được biết ở build time, hãy quản lý plugin như dependency của release.

### Bước 1: định nghĩa SPI ổn định

Tạo interface plugin nhỏ, không phụ thuộc vào implementation:

~~~java
public interface ReportPlugin {
    String id();
    ReportResult generate(ReportRequest request);
}
~~~

Giữ API và DTO trao đổi ổn định. Tránh để plugin truy cập trực tiếp bean nội bộ hoặc class implementation riêng của host.

### Bước 2: chọn plugin dependencies khi build

Khai báo plugin JAR trong Maven/Gradle dependency graph của application variant. Mỗi plugin phải có dependencies và reachability metadata phù hợp với Native Image.

### Bước 3: đăng ký provider/bean theo cách AOT nhận diện

Dùng `ServiceLoader` với provider có trong build classpath hoặc đăng ký bean thông qua configuration/auto-configuration được Spring AOT xử lý. Tránh đăng ký singleton động sau khi AOT đã phân tích.

### Bước 4: quyết định plugin selection bằng dữ liệu runtime

Cho phép operator bật/tắt hoặc chọn plugin đã đóng gói bằng cấu hình. Không dùng runtime profile/conditional để cố tạo bean definition mới ngoài tập đã được AOT xử lý.

### Bước 5: kiểm thử native theo từng plugin

Chạy native tests cho từng implementation, bao gồm:

- Plugin được phát hiện.
- Reflection/resource/serialization hoạt động.
- Plugin được chọn theo cấu hình.
- Plugin lỗi được xử lý đúng.
- Không có dependency hoặc class chỉ tồn tại trong JVM test classpath.

### Bước 6: version và phát hành cùng nhau

Ghi nhận host version, plugin version, GraalVM version và native build metadata. Khi thay plugin code hoặc dependency, build lại image và chạy lại compatibility tests.

## 13. Kiểm tra một hệ thống hiện tại có phụ thuộc classpath động không

Tìm các dấu hiệu sau trong source/dependency:

| Dấu hiệu | Điều cần hỏi |
|---|---|
| `URLClassLoader` / custom `ClassLoader` | Có đọc JAR/bytecode được cài sau deployment không? |
| `Class.forName(name)` | Tên class có thể trỏ tới class không có trong build classpath không? |
| `ServiceLoader.load` | Provider có nằm trong dependency graph lúc build không? |
| Plugin folder scan | Có mong đợi quét thư mục JAR lúc runtime không? |
| Spring `registerSingleton` / registry callback | Bean definition có được thêm sau AOT processing không? |
| `@Profile` / `@ConditionalOnProperty` | Có mong đợi runtime property thay đổi tập bean definitions không? |
| Bytecode generation / proxy generator | Bytecode được tạo lúc build hay lúc runtime; Native Image version có hỗ trợ use case đó không? |

Tìm kiếm nhanh bằng ripgrep:

~~~bash
rg -n "URLClassLoader|ClassLoader|Class\\.forName|ServiceLoader|registerSingleton|registerBeanDefinition|plugins/" src
~~~

Lệnh này chỉ là bước rà soát. Một class loader xuất hiện trong code không tự động chứng minh ứng dụng không tương thích; cần xem bytecode được tải từ đâu, class đã có trong image chưa và use case có được GraalVM hỗ trợ không.

### Phân loại phát hiện

1. **Dynamic lookup của class đã biết:** có thể phù hợp với Native Image sau khi kiểm tra reachability metadata.
2. **Provider/bean đã có từ build:** có thể dùng nếu service/bean registration được AOT xử lý và test native pass.
3. **Plugin JAR mới sau deployment:** không phù hợp với classpath cố định thông thường.
4. **Generated bytecode lúc runtime:** cần kiểm tra tùy chọn hỗ trợ riêng, bao gồm experimental runtime class loading nếu phiên bản GraalVM có.

## 14. Ví dụ quyết định kiến trúc

Một nền tảng báo cáo có ba loại extension:

- Bộ xuất CSV/PDF được phát hành cùng ứng dụng.
- Bộ tính phí được đối tác cập nhật hàng tháng.
- Script điều chỉnh mẫu báo cáo do người vận hành thay đổi hàng ngày.

Có thể phân chia:

| Extension | Cách triển khai phù hợp |
|---|---|
| CSV/PDF đã biết | Đóng gói plugin vào native image; chọn bằng cấu hình runtime |
| Bộ tính phí cần cập nhật độc lập | Chạy thành service/process riêng, giao tiếp qua API versioned |
| Script mẫu báo cáo | Dùng template/DSL/interpreter đã được đóng gói và giới hạn chức năng |

Nếu tất cả extension đều là Java JAR cần nạp tự do, chạy host trên JVM có thể đơn giản và ít rủi ro hơn so với cố mô phỏng classpath mở trong Native Image.

## 15. Bài tập thực hành

**Bài 1 — JAR mới không được nhận diện:** Một container native có thư mục `/app/plugins/customer.jar`, nhưng `Class.forName("com.customer.Plugin")` báo không tìm thấy class. Vì sao?

**Gợi ý:** JAR được copy sau khi image build nên bytecode không có trong executable. Reflection metadata chỉ hỗ trợ truy cập class đã biết, không bổ sung plugin code.

**Bài 2 — ServiceLoader chỉ tìm thấy plugin mặc định:** Provider mới được chép vào `plugins/` sau deployment. Có nên thêm `META-INF/services` cạnh binary?

**Gợi ý:** không đủ. Provider class và service metadata cần được đưa vào build classpath/image. File descriptor runtime không bổ sung bytecode.

**Bài 3 — Chọn plugin theo config:** Ứng dụng có hai provider đã đóng gói. Operator cần chọn provider A hoặc B khi chạy. Có thể làm thế nào?

**Gợi ý:** đăng ký cả hai implementation trong bean context ổn định, sau đó dùng runtime configuration để registry chọn implementation. Không dùng conditional để tạo bean mới sau AOT.

**Bài 4 — Plugin cần deploy độc lập:** Khách hàng cần upload Java JAR mới mà không build lại host. Hãy đề xuất kiến trúc.

**Gợi ý:** giữ host/plugin manager trên JVM hoặc chạy plugin trong process/container riêng qua HTTP/gRPC/message protocol. Đánh giá chi phí vận hành và isolation.

**Bài 5 — Runtime class loading thử nghiệm:** Vì sao bật `-H:+RuntimeClassLoading` không có nghĩa mọi plugin framework JVM sẽ hoạt động?

**Gợi ý:** tính năng thử nghiệm chỉ mở một số khả năng define bytecode; còn hạn chế URLClassLoader, parallel loading, linking, preserved members, dependency/resource và memory.

## 16. Checklist trước khi chọn Native Image cho hệ thống plugin

- [ ] Xác định plugin có được biết ở build time hay phải cài mới sau deployment.
- [ ] Phân biệt dynamic lookup class đã đóng gói với việc nạp bytecode/JAR mới.
- [ ] Kiểm tra mọi plugin dependency có mặt trên build classpath.
- [ ] Kiểm tra `ServiceLoader` provider và service descriptor được đưa vào image.
- [ ] Đảm bảo Spring AOT nhìn thấy bean definitions và auto-configuration cần thiết.
- [ ] Không dựa vào runtime profile/conditional để thêm bean definition mới.
- [ ] Nếu cần bật/tắt plugin, dùng registry lựa chọn trong tập implementation đã biết.
- [ ] Nếu cần plugin mới độc lập, cân nhắc JVM host hoặc process/container riêng.
- [ ] Nếu dùng DSL/script, kiểm tra interpreter và giới hạn runtime cụ thể.
- [ ] Chỉ xem runtime class loading là lựa chọn nâng cao khi GraalVM version hỗ trợ và prototype đã qua kiểm thử.
- [ ] Kiểm thử native image với từng plugin, dependency và đường code thực tế.
- [ ] Ghi nhận host/plugin/GraalVM versions để tái tạo build và chẩn đoán lỗi.

## 17. Tài liệu tham khảo

- [Spring Boot Reference — Introducing GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/introducing-graalvm-native-images.html): classpath cố định, closed-world assumption và giới hạn Spring AOT.
- [Spring Framework Reference — Ahead of Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html): classpath/Environment cố định và bean definitions được xử lý ở build time.
- [GraalVM Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): closed-world assumption, metadata và giới hạn defining classes at runtime.
- [GraalVM Run-Time Class Loading](https://www.graalvm.org/dev/reference-manual/native-image/runtime-class-loading/): tính năng thử nghiệm, cách bật và các giới hạn của runtime class loading.
- [GraalVM Native Image Compatibility Guide](https://www.graalvm.org/latest/reference-manual/native-image/metadata/Compatibility/): các đặc điểm Java cần metadata hoặc không phù hợp với closed-world assumption.

**Ghi nhớ:** Native Image cố định classpath và tập bean definitions tại build time để phân tích, loại bỏ code không cần và biên dịch executable gọn. Reflection hints có thể cho phép truy cập động tới class đã được đóng gói; chúng không cài thêm bytecode của plugin JAR sau deployment. Nếu plugin set đã biết, đóng gói chúng trước và lựa chọn bằng cấu hình runtime. Nếu phải nạp Java plugin mới sau khi phát hành, cân nhắc JVM host hoặc process/container riêng; chỉ dùng runtime class loading thử nghiệm sau khi đã kiểm tra đầy đủ giới hạn của GraalVM version đang triển khai.
