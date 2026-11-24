# Kiểm kê tính năng động và đánh giá khả năng chuyển một ứng dụng JVM hiện có

## 1. Không bắt đầu bằng việc đổi lệnh build

Một ứng dụng Spring Boot đang chạy ổn định trên JVM có thể đã tích lũy nhiều năm dependency, plugin, cấu hình và hành vi chỉ được quyết định khi runtime. Chuyển sang GraalVM Native Image thay đổi thời điểm mà một số quyết định được đưa ra: Spring AOT phân tích `ApplicationContext` ở build time, còn Native Image thực hiện static analysis để xác định class, method và resource cần đưa vào executable.

Vì vậy, đánh giá migration cần trả lời hai câu hỏi riêng:

1. **Ứng dụng có thể chạy đúng với một classpath và bean graph được xác định tại build time không?**
2. **Lợi ích về startup, memory, deployment hoặc chi phí vận hành có đủ lớn để bù cho native build, metadata, kiểm thử và bảo trì bổ sung không?**

Không phải mọi ứng dụng JVM đều cần Native Image. Một service chạy lâu, được JIT tối ưu tốt và không có yêu cầu cold start có thể không thu được lợi ích đủ lớn. Ngược lại, worker khởi động thường xuyên, workload scale-to-zero, CLI hoặc service có giới hạn memory chặt có thể hưởng lợi đáng kể.

Bài này giúp bạn kiểm kê ứng dụng hiện tại trước khi quyết định chuyển đổi. Kết quả cuối cùng là một hồ sơ migration có thể review: dependency nào đã tương thích, tính năng động nào cần metadata hoặc refactor, phần nào là blocker, cách kiểm thử và tiêu chí go/no-go.

Sau bài học, bạn có thể:

- Lập inventory module, dependency, profile và cấu hình runtime của ứng dụng JVM.
- Nhận diện reflection, resource loading, proxy, serialization, JNI, class loading và các tính năng động khác.
- Đánh giá giới hạn Spring AOT và mức hỗ trợ Native Image của dependency.
- Dùng JVM, AOT-on-JVM và native tests để đo mức sẵn sàng theo từng giai đoạn.
- Phân loại rủi ro thành tương thích sẵn, cần xử lý hoặc blocker.
- Lập kế hoạch chuyển đổi từng module/service và quyết định giữ hay loại Native Image.

## 2. Đánh giá lợi ích trước khi kiểm kê kỹ thuật

### 2.1. Những trường hợp Native Image thường đáng thử

| Đặc điểm workload | Lợi ích có thể đạt được |
|---|---|
| Service scale-to-zero hoặc tạo instance thường xuyên | Giảm thời gian từ lúc tạo process đến khi phục vụ request |
| CLI, batch worker ngắn hạn hoặc job theo lịch | Giảm chi phí khởi động cho mỗi lần chạy |
| Container có memory limit thấp | Có thể giảm RSS và cho phép tăng mật độ instance |
| Serverless hoặc môi trường tính phí theo thời gian/instance | Giảm cold-start và thời gian giữ tài nguyên nếu workload phù hợp |
| Service có startup latency là SLO quan trọng | Dễ đáp ứng mục tiêu readiness khi native startup nhanh hơn |

Đây là các động lực để đo thử, không phải cam kết rằng native luôn nhanh hơn hoặc dùng ít memory hơn trong mọi workload.

### 2.2. Những chi phí cần tính

- Native compilation thường lâu hơn JVM compilation và cần runner nhiều RAM/CPU/disk.
- Một số thư viện cần reachability metadata, runtime hints hoặc thay đổi code.
- Executable gắn với OS và kiến trúc build; thường cần build riêng cho từng target.
- Native runtime không có cùng mô hình JIT tối ưu dần như HotSpot. Throughput sau warm-up có thể khác.
- Debugging, profiling, heap analysis và một số agent/tooling có thể khác JVM.
- Nâng Spring Boot, JDK, GraalVM hoặc dependency có thể yêu cầu chạy lại native compatibility tests.

### 2.3. Đo baseline JVM trước khi chuyển

Ghi số liệu của ứng dụng hiện tại trong môi trường gần production:

| Chỉ số | Cách đo |
|---|---|
| Startup-to-ready | Từ lúc process bắt đầu đến khi health/readiness cho phép nhận traffic |
| RSS sau startup | Memory resident sau khi ứng dụng sẵn sàng |
| RSS sau warm-up | Memory sau workload đại diện và sau khi JIT ổn định |
| CPU và throughput | Request/second hoặc job throughput trong tải đại diện |
| p50/p95/p99 latency | Đo khi startup, sau warm-up và ở tải cao |
| Container image size | Kích thước image được registry lưu và kéo về node |
| Build duration | Thời gian compile, test, package và tạo image |
| Operational cost | CPU/RAM reservation, replica count, cold-start và thời gian triển khai |

So sánh native và JVM trên cùng CPU architecture, cùng database, cùng request mix, cùng memory limit và cùng cách đo readiness. Đừng chỉ so sánh thời gian `main()` với thời gian JVM startup; hãy đo đến thời điểm service thực sự nhận được traffic.

## 3. Lập inventory ứng dụng JVM hiện tại

### 3.1. Xác định phạm vi migration

Trước hết, liệt kê các đơn vị có thể build và triển khai độc lập:

- Spring Boot application/module.
- Shared library được nhiều service dùng.
- Adapter tích hợp database, message broker, HTTP client hoặc cloud SDK.
- Plugin, extension hoặc module được nạp theo cấu hình.
- Batch job, scheduler, CLI hoặc worker có entry point riêng.

Không nên đánh giá cả monorepo như một ứng dụng duy nhất nếu từng service có classpath và workload khác nhau. Một service có thể sẵn sàng cho Native Image trong khi service khác dùng plugin runtime hoặc thư viện chưa hỗ trợ.

### 3.2. Thu thập dependency tree và phiên bản

Với Maven:

```bash
./mvnw dependency:tree -Dverbose > dependency-tree.txt
./mvnw help:effective-pom -Doutput=effective-pom.xml
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath > runtime-dependencies.txt
./gradlew buildEnvironment > build-environment.txt
```

Ghi lại cả dependency trực tiếp và transitive. Một starter Spring Boot có thể kéo theo thư viện dùng reflection, JNI hoặc classpath scanning mà code ứng dụng không gọi trực tiếp.

Với mỗi dependency quan trọng, ghi:

- `groupId:artifactId:version` hoặc Gradle module coordinates.
- Phiên bản được quản lý bởi Spring Boot BOM hay bị override.
- Dependency là compile/runtime/optional hay chỉ dùng trong test.
- Có metadata native do thư viện cung cấp hay có trong GraalVM Reachability Metadata Repository không.
- Có phiên bản mới hơn đã sửa native compatibility không.
- Có cần native library hoặc toolchain riêng theo OS/architecture không.

Native Build Tools có thể tự sử dụng metadata từ Reachability Metadata Repository. Dù vậy, việc metadata tồn tại không chứng minh mọi code path hoặc mọi phiên bản thư viện đều tương thích; vẫn cần kiểm tra version và chạy test trên native executable.

### 3.3. Kiểm kê cấu hình theo môi trường

Liệt kê:

- Spring profiles đang dùng ở local, test, staging và production.
- Các property ảnh hưởng đến bean creation qua `@ConditionalOnProperty`.
- Các property chỉ thay đổi giá trị cấu hình nhưng không thay đổi bean graph.
- Các external service, endpoint, credential, certificate và DNS name.
- Các thư mục file được mount vào container.
- Các thư viện hoặc plugin chỉ được bật trong một số môi trường.

Phân biệt rõ property **quyết định bean có tồn tại hay không** với property chỉ thay đổi giá trị của một bean đã được tạo. Nhóm đầu có ảnh hưởng trực tiếp đến Spring AOT.

### 3.4. Mẫu inventory tổng quan

| Module/service | Runtime profile | Dependency quan trọng | Dynamic features | Kết quả sơ bộ |
|---|---|---|---|---|
| `order-api` | `production` | Web, Security, JPA, PostgreSQL | Hibernate, Jackson, proxy, Flyway | Cần kiểm tra metadata và native tests |
| `billing-worker` | `batch` | JDBC, messaging, PDF SDK | Reflection trong PDF SDK, resource templates | Rủi ro phụ thuộc SDK |
| `plugin-host` | `production` | Plugin API, scripting engine | Runtime class loading, script execution | Rủi ro cao, cần đánh giá kiến trúc |

Các tên module trong bảng chỉ là ví dụ. Thay bằng module thực tế và ghi bằng chứng cho mỗi kết luận.

## 4. Kiểm kê tính năng động trong code và dependency

Native Image không cấm mọi tính năng động. Nhiều tính năng vẫn hoạt động nếu tập class/member/resource có thể xác định tại build time và được cung cấp reachability metadata phù hợp. Rủi ro cao nhất là hành vi phụ thuộc vào dữ liệu runtime mà compiler không thể biết trước hoặc yêu cầu nạp code tùy ý sau khi executable đã được tạo.

### 4.1. Reflection và introspection

Tìm các mẫu:

- `Class.forName(...)`, `ClassLoader.loadClass(...)`.
- `getDeclaredMethod`, `getMethod`, `getDeclaredField`, `getConstructor`.
- `Method.invoke`, `Constructor.newInstance`, `Field.get/set`.
- `MethodHandles.Lookup` và `VarHandle`.
- Framework tự khám phá annotation, DTO hoặc model theo tên class.

Lệnh tìm sơ bộ trong source:

```bash
rg -n "Class\.forName|loadClass\(|getDeclaredMethod|getDeclaredField|getConstructor|Method\.invoke|newInstance\(" src
```

Tìm cả code trong shared libraries nếu repository có source. Với dependency binary, đọc tài liệu, source hoặc dùng tracing agent trên JVM để phát hiện các thao tác thực tế.

Phân loại từng trường hợp:

| Kiểu sử dụng | Đánh giá |
|---|---|
| Class/member cố định, tên biết trước | Thường xử lý được bằng Spring hints hoặc reachability metadata cụ thể |
| Framework có integration/AOT support | Có thể được tự động xử lý; xác nhận generated hints và test |
| Tên class lấy từ cấu hình nhưng tập class hữu hạn | Có thể đăng ký toàn bộ lựa chọn hợp lệ ở build time |
| Tên class do người dùng hoặc plugin cung cấp tùy ý sau deploy | Rủi ro cao; Native Image không thể tự đưa class tùy ý chưa biết vào executable |

Không phải mọi `Class.forName` đều là blocker. Vấn đề là class nào được nạp, có thể biết trước hay không và có metadata tương ứng hay không.

### 4.2. Resource loading

Tìm các thao tác:

- `ClassPathResource`, `ResourceLoader`, `getResourceAsStream`.
- `ClassLoader.getResource` hoặc `getResources`.
- `ResourceBundle.getBundle`.
- Quét `classpath*:` hoặc glob trong thư mục resource.
- Template engine, XML schema, JSON schema, certificate, locale bundle.

```bash
rg -n "getResourceAsStream|getResource\(|getResources\(|ResourceBundle|getResourceLoader|classpath\*?:" src
```

Resource đóng gói trong native image phải được nhận diện và giữ lại. Spring AOT hoặc thư viện có thể đã đăng ký resource hints; chỉ bổ sung pattern thủ công khi resource chưa được phát hiện. Resource nằm trên filesystem runtime cần được mount/copy vào container và kiểm tra quyền đọc, không giải quyết bằng classpath hint.

### 4.3. Proxy và AOP

Kiểm kê:

- Spring AOP, `@Transactional`, `@Async`, method security và caching.
- JDK dynamic proxy qua `Proxy.newProxyInstance`.
- CGLIB/Byte Buddy hoặc thư viện tạo subclass/proxy.
- Proxy được tạo theo interface list lấy từ cấu hình runtime.

Spring AOT có thể sinh bytecode proxy cho các trường hợp Spring nhận biết. Nếu code tự tạo JDK proxy, tổ hợp interface phải được xác định và đăng ký. Nếu thư viện sinh class tùy ý lúc runtime, kiểm tra khả năng hỗ trợ của thư viện; proxy hint không giải quyết mọi dạng bytecode generation.

### 4.4. Serialization và data binding

Tìm:

- Java serialization: `ObjectInputStream`, `ObjectOutputStream`, `Serializable`.
- Jackson/Gson hoặc serializer tự viết.
- XML binding, JAXB, YAML mapper.
- Polymorphic type handling, default typing hoặc class discriminator.
- Model được nạp từ tên class trong payload/configuration.

Framework có thể tự tạo hints cho một số model được phát hiện qua controller hoặc binding contracts. Tuy nhiên, model chỉ được tham chiếu gián tiếp, polymorphic subtype hoặc Java serialization có thể cần metadata riêng. Không bật reflection cho toàn bộ package chỉ để sửa một DTO; xác định class và member thực sự được serializer truy cập.

### 4.5. JNI, JNA và native libraries

Kiểm kê các dependency dùng:

- JNI/JNA hoặc Java Foreign Function and Memory API.
- Native library được load qua `System.loadLibrary` hoặc `System.load`.
- Driver, compression, cryptography, image processing hoặc database client có native component.
- File `.so`, `.dylib`, `.dll` và các binary theo OS/architecture.

Native Image hỗ trợ JNI với metadata thích hợp, nhưng thư viện native phải có binary tương thích với target OS/architecture/ABI và được đóng gói đúng cách. Một dependency chạy được trên HotSpot không tự động có nghĩa native library của nó tương thích với GraalVM.

### 4.6. Runtime class loading, plugin và scripting

Đây là nhóm cần đánh giá sớm:

- Plugin JAR được copy vào thư mục sau khi ứng dụng đã build.
- `URLClassLoader` hoặc custom class loader nạp class từ filesystem/network.
- Script engine chạy Groovy, JavaScript hoặc ngôn ngữ khác.
- OSGi/container plugin hoặc extension được phát hiện khi runtime.
- Runtime bytecode generation và dynamic compilation.

Native executable không có classpath JVM mở để nạp tùy ý một JAR mới như ứng dụng HotSpot thông thường. Nếu plugin set hữu hạn, có thể chuyển sang compile-time inclusion, registry tĩnh hoặc build một executable cho từng tập plugin. Nếu yêu cầu sản phẩm là nạp code mới sau deploy, hãy xem đây là blocker kiến trúc cho migration Native Image tiêu chuẩn hoặc giữ JVM cho service đó.

### 4.7. ServiceLoader, classpath scanning và framework discovery

Kiểm tra `ServiceLoader`, `META-INF/services`, component scanning tùy chỉnh, package scanning và registry được tạo từ file resource. Nhiều framework có thể xử lý các contract phổ biến trong AOT, nhưng code tự quét classpath khi runtime cần được chuyển sang build-time discovery hoặc registry tĩnh.

Spring AOT phân tích bean definitions ở build time. Nếu ứng dụng tự đăng ký bean sau context refresh hoặc dựa vào classpath scanning động để phát hiện plugin, phải xác định cách chuyển logic đó sang `BeanDefinitionRegistry`, `ImportBeanDefinitionRegistrar` hoặc cơ chế registry được tạo ở build time.

### 4.8. Class initialization và trạng thái phụ thuộc môi trường

Kiểm tra static initializer hoặc singleton tạo trong quá trình khởi tạo class:

- Đọc environment variable, system property hoặc file cấu hình.
- Resolve DNS, mở socket hoặc kết nối database.
- Tạo thread, executor, timer hoặc native handle.
- Đọc timezone, locale, random seed hoặc clock.
- Nạp certificate, secret hoặc đường dẫn riêng của máy build.

Nếu class được initialize tại build time, giá trị có thể bị capture vào image heap. Hãy tách việc đọc cấu hình môi trường và khởi tạo resource sang runtime lifecycle phù hợp; chỉ cấu hình runtime initialization cho class cụ thể sau khi có bằng chứng.

### 4.9. Security provider, instrumentation và tooling

Kiểm tra các thư viện phụ thuộc vào:

- Security provider được đăng ký động.
- Attach API, instrumentation agent, bytecode transformer.
- JMX hoặc management extension cần runtime discovery.
- Profiler/APM agent, coverage agent, hot reload hoặc dynamic attach.
- URL protocol handler hoặc charset/locale data được nạp động.

Không mặc định tất cả các tính năng này đều không được hỗ trợ. Ghi tên API, provider/agent, thời điểm kích hoạt và native support của version cụ thể. Một ứng dụng có thể chạy native nhưng cần thay đổi cách triển khai monitoring, profiling hoặc secret/certificate.

## 5. Kiểm tra giới hạn Spring AOT

Spring AOT không chỉ thêm metadata cho GraalVM. Nó phân tích `ApplicationContext` ở build time và tạo code để khôi phục bean definitions theo một cấu hình đã biết. Điều đó tạo ra một số ràng buộc cần kiểm kê trong ứng dụng JVM hiện tại.

### 5.1. Classpath phải cố định

Classpath được xác định đầy đủ ở build time. Ứng dụng không thể mong đợi thêm JAR mới vào classpath sau khi native executable đã được tạo và yêu cầu Spring phát hiện bean trong JAR đó.

Nếu hiện tại deploy bằng cách mount plugin JAR hoặc thêm extension directory, cần chuyển sang một trong các mô hình:

- Đưa plugin vào dependency graph trước khi build.
- Build artifact riêng cho từng tập plugin đã biết.
- Thay plugin bằng registry/configuration tĩnh.
- Tiếp tục chạy module đó trên JVM nếu nạp code tùy ý là yêu cầu cốt lõi.

### 5.2. `@Profile` và `@Conditional` được quyết định lúc build

Profile cần thiết phải được chọn khi AOT processing chạy. Các environment properties quyết định bean có tồn tại qua `@Conditional` cũng được đánh giá ở build time.

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
@Profile("production")
class ProductionGatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new ProductionPaymentGateway();
    }
}
```

Nếu native artifact được AOT xử lý với profile `production`, không thể kỳ vọng đổi sang profile `sandbox` khi chạy executable sẽ làm Spring tạo bean `SandboxPaymentGateway` vốn không được đưa vào bean graph khi build.

Nếu cần nhiều cấu hình bean graph, có thể build nhiều artifact theo profile hoặc thiết kế bean graph ổn định và chỉ thay giá trị cấu hình runtime. Không dùng profile runtime để cố gắng bật một bean đã bị loại trong AOT.

### 5.3. Bean registration phải được AOT nhận biết

Các bean đăng ký bằng `registerSingleton` hoặc callback chỉ chạy sau AOT processing có thể không được chuyển đổi thành generated bean definitions. Với registration động, Spring khuyến nghị dùng `BeanDefinitionRegistry` và các extension point phù hợp như `ImportBeanDefinitionRegistrar`.

Kiểm kê:

- `BeanFactoryPostProcessor` và `BeanDefinitionRegistryPostProcessor` tùy chỉnh.
- `ImportBeanDefinitionRegistrar`.
- Bean đăng ký bằng `registerBeanDefinition` hoặc `registerSingleton`.
- `FactoryBean` và custom instance supplier.
- Bean được tạo từ lambda/method reference không có type rõ ràng.

Không phải mọi programmatic registration đều không tương thích. Vấn đề là registration có diễn ra trong giai đoạn AOT có thể quan sát và tạo bean definition rõ ràng hay không.

### 5.4. Khai báo bean type càng cụ thể càng tốt

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class GatewayConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return new StripePaymentGateway();
    }
}
```

Khai báo return type là `PaymentGateway` có thể khiến AOT không thấy các annotation hoặc callback chỉ có trên `StripePaymentGateway`. Nếu bean thực tế có type cụ thể và AOT cần phân tích type đó, khai báo return type cụ thể hơn:

```java
@Bean
StripePaymentGateway paymentGateway() {
    return new StripePaymentGateway();
}
```

Chỉ thay đổi khi type cụ thể là một phần hợp đồng bean phù hợp. Không đổi API public tùy tiện nếu điều đó phá vỡ abstraction của ứng dụng.

### 5.5. Custom arguments và constructor selection

Spring AOT có thể không suy ra các constructor/factory method được chọn từ custom arguments truyền động khi tạo bean. Nhiều constructor không có constructor ưu tiên rõ ràng cũng làm việc chọn constructor khó dự đoán.

Kiểm kê các bean được tạo bằng custom arguments, prototype factory và constructor selection. Cân nhắc:

- Đánh dấu constructor ưu tiên bằng `@Autowired` khi phù hợp.
- Dùng factory bean có type rõ ràng để tạo instance.
- Tránh cấu trúc tham số bean quá phức tạp được tạo thủ công qua `RootBeanDefinition`.
- Cung cấp hints tối thiểu nếu một thư viện thực sự cần introspection/invocation động.

### 5.6. Nested configuration properties

Spring Boot tự tạo reflection hints cho configuration properties mà AOT nhận diện. Với nested property type là class riêng, kiểm tra yêu cầu `@NestedConfigurationProperty` theo kiểu khai báo và version Spring Boot. Thiếu annotation có thể khiến nested property không bind được trong native image dù JVM runtime hoạt động.

### 5.7. BeanPostProcessor và extension point tùy chỉnh

Spring AOT không thực hiện một lần refresh đầy đủ như runtime thông thường. Các `BeanPostProcessor` thông thường không được gọi trong AOT processing, ngoại trừ những biến thể được Spring hỗ trợ cho AOT. Nếu custom processor thay đổi bean definitions hoặc behavior theo instance thực, cần xác định cách cung cấp AOT contribution hoặc chuyển logic sang giai đoạn đăng ký bean definitions.

Không giả định mọi callback được gọi trong JVM startup cũng được gọi trong AOT processing. Hãy kiểm tra lifecycle thực tế và generated code.

## 6. Đánh giá hỗ trợ Native Image của dependency

### 6.1. Kiểm tra Reachability Metadata Repository

Tra cứu từng dependency quan trọng trong [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata). Repository chứa metadata cộng đồng cho nhiều thư viện để chúng hoạt động với Native Image. GraalVM Native Build Tools có thể tự động dùng metadata này trong build.

Đánh giá theo các câu hỏi:

- Metadata có cho đúng artifact/version không?
- Có chỉ hỗ trợ một GraalVM/JDK range cụ thể không?
- Có metadata cho tất cả module của thư viện hay chỉ core module?
- Dependency có thay đổi behavior giữa các version không?
- Native tests của dự án có chạy các feature mà metadata hỗ trợ không?

Nếu thư viện chưa có metadata, không nhất thiết phải loại bỏ ngay. Có thể tự cung cấp RuntimeHints/JSON metadata và đóng góp ngược lại nếu phù hợp. Tuy nhiên, nếu thư viện yêu cầu runtime class loading hoặc dynamic code generation không thể giới hạn, đó có thể là blocker thực sự.

### 6.2. Kiểm tra native support do nhà cung cấp công bố

Ưu tiên tài liệu chính thức của dependency vendor:

- Có hỗ trợ GraalVM Native Image không?
- Có starter/module hoặc artifact riêng cho native không?
- Có yêu cầu feature, native library hoặc build argument đặc biệt không?
- Có giới hạn API, protocol, driver hoặc OS nào không?
- Có CI test native image cho version đó không?

Badge “GraalVM compatible” hoặc metadata repository entry là tín hiệu ban đầu, không thay thế test trong ứng dụng thực tế.

### 6.3. Phân loại dependency

| Trạng thái | Tiêu chí | Hành động |
|---|---|---|
| Green | Có native support chính thức hoặc metadata đúng version; test đại diện pass | Giữ dependency và đưa vào native regression suite |
| Amber | Có thể hỗ trợ bằng hints/refactor/cấu hình; chưa được kiểm chứng đầy đủ | Tạo MRE, bổ sung test và ước lượng effort |
| Red | Cần classpath/plugin tùy ý lúc runtime, API/tooling không được hỗ trợ hoặc vendor xác nhận không tương thích | Tìm kiến trúc thay thế, giữ module JVM hoặc dừng migration |
| Unknown | Chưa có tài liệu hoặc chưa chạy thử | Không coi là Green; tạo spike có phạm vi và deadline rõ ràng |

## 7. Dùng Tracing Agent để khám phá, không dùng làm kết luận cuối

Tracing Agent chạy trên JVM và ghi nhận reflection, resource, proxy, JNI cùng các thao tác động khác mà kịch bản đã thực thi. Nó hữu ích khi không biết thư viện nào đang truy cập class/member/resource theo cách động.

Ví dụ:

```bash
java \
  -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent/ \
  -jar target/order-service.jar
```

Sau đó thực hiện các luồng nghiệp vụ đại diện: login, tạo đơn, xuất báo cáo, xử lý message, gọi external API, upload/download file và các chức năng chỉ bật trong production. Khi process dừng, agent ghi metadata vào thư mục output.

Có thể chạy agent qua test suite, nhưng output có thể chứa metadata của test framework, mock, assertion library hoặc test-only code. Cần dùng filter và review trước khi đưa vào artifact production.

Tracing Agent chỉ ghi những đường code được chạy. Nếu không thực hiện chức năng export, agent không thể biết reflection/resource mà chức năng đó cần. Do đó:

- Dùng nhiều kịch bản test và input đại diện.
- Bao phủ feature flags và profile cần hỗ trợ.
- So sánh output agent với hints do Spring AOT và dependency cung cấp.
- Loại entry chỉ thuộc test harness sau khi có bằng chứng.
- Chạy `--exact-reachability-metadata` và native integration tests sau khi tổng hợp.

## 8. Thử AOT trên JVM trước khi compile native

### 8.1. Maven

Với Spring Boot Maven Parent, tạo JAR có AOT assets bằng profile `native`:

```bash
./mvnw -Pnative package
```

Sau đó chạy trên JVM với AOT-generated code:

```bash
java -Dspring.aot.enabled=true -jar target/order-service.jar
```

Đảm bảo JAR thực sự chứa generated AOT assets. Khi ứng dụng startup, log có thể xác nhận AOT-processed context được sử dụng. Nếu chỉ bật property trên một JAR không được AOT xử lý, phép thử không có ý nghĩa.

### 8.2. Gradle

Với Gradle, bảo đảm build áp dụng Spring Boot Gradle plugin và GraalVM Native Image plugin:

```groovy
plugins {
    id 'org.springframework.boot'
    id 'org.graalvm.buildtools.native'
}
```

Ví dụ giả định plugin versions đã được quản lý trong `pluginManagement` hoặc version catalog của dự án. Khi áp dụng Spring Boot Gradle plugin cùng GraalVM Native Image plugin, Spring Boot cấu hình các task AOT cần thiết. Sau khi build executable JAR có AOT assets:

```bash
./gradlew bootJar
java -Dspring.aot.enabled=true -jar build/libs/order-service.jar
```

Version trong ví dụ chỉ minh họa. Dùng version Spring Boot, Gradle và Native Build Tools tương thích với dự án.

### 8.3. Những điều AOT-on-JVM có thể phát hiện

- Profile/conditional bean graph không đúng.
- Generated initializer hoặc bean registration bị lỗi.
- Configuration properties không bind đúng.
- Proxy hoặc custom AOT contribution không được tạo như kỳ vọng.
- Startup path có hành vi phụ thuộc runtime classpath/bean discovery.

AOT-on-JVM chưa chứng minh reflection/resource metadata đầy đủ cho Native Image. Đây là một cổng kiểm tra trung gian, không thay thế native build và native runtime tests.

## 9. Lộ trình kiểm thử migration theo tầng

Spring Boot khuyến nghị giữ phần lớn unit/integration tests trên JVM để feedback nhanh. Chỉ tập trung native tests vào những hành vi có thể khác biệt trong AOT/Native Image.

### 9.1. Tầng 1 — JVM regression suite

Chạy toàn bộ test hiện tại để bảo đảm migration không làm thay đổi behavior nghiệp vụ. Giữ lại test cho:

- API contract và serialization.
- Database transactions và migration.
- Messaging, retry và scheduling.
- Security, authentication và authorization.
- File upload/download, resource loading và encoding.
- Feature flags, profile và conditional configuration.

### 9.2. Tầng 2 — AOT-on-JVM smoke tests

Chạy application hoặc integration tests với generated AOT code. Ưu tiên startup, bean graph, custom registration, proxy và configuration.

### 9.3. Tầng 3 — Native build

Build native executable với exact reachability metadata khi GraalVM version hỗ trợ:

```bash
./mvnw -Pnative native:compile
```

Hoặc Gradle:

```bash
./gradlew nativeCompile
```

Ghi build duration, peak RAM, executable size và mọi warning/error. Nếu build fail, phân loại lỗi là unsupported API, metadata, class initialization, toolchain hay resource constraint.

### 9.4. Tầng 4 — Native runtime smoke tests

Chạy executable và kiểm tra:

- Startup-to-ready.
- Health/readiness endpoint.
- Một luồng API quan trọng.
- Database connection và migration.
- Outbound TLS/DNS.
- Resource/template/serialization.
- Graceful shutdown và signal handling.

Chạy trong container có base image, libc, user, filesystem permissions và network policy gần production.

### 9.5. Tầng 5 — Native integration tests

Chọn test cho các feature có dynamic behavior hoặc thư viện có native integration. Có thể chạy Native Build Tools native tests trong CI/nightly thay vì bắt mọi developer build native image cho mỗi thay đổi.

### 9.6. Tầng 6 — Performance và soak tests

Đo startup-to-ready, RSS, throughput, latency percentiles và CPU ở workload đại diện. Kiểm tra cả thời gian warm-up của JVM baseline và hành vi steady-state của native. Chạy soak test để phát hiện leak hoặc khác biệt resource lifecycle.

## 10. Xử lý metadata và các điểm chưa tương thích

### 10.1. Bổ sung hints theo đúng feature

Nếu Spring AOT không thể suy ra reflection/resource/proxy/serialization cần thiết, cung cấp `RuntimeHintsRegistrar` hoặc reachability metadata JSON. Gắn hints gần component sở hữu để metadata không trở thành một tập cấu hình toàn cục khó bảo trì.

Ví dụ đăng ký một resource cụ thể:

```java
public class InvoiceRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("templates/invoice.html");
    }
}
```

Không thêm wildcard toàn classpath để làm build pass. Mỗi hint nên có test predicate và native test chứng minh đường code cần nó.

### 10.2. Bật exact reachability metadata

Với GraalVM JDK 23 trở lên, bật exact reachability metadata trong cấu hình Native Build Tools. Ví dụ Maven:

```xml
<plugin>
    <groupId>org.graalvm.buildtools</groupId>
    <artifactId>native-maven-plugin</artifactId>
    <configuration>
        <buildArgs>
            <buildArg>--exact-reachability-metadata</buildArg>
        </buildArgs>
    </configuration>
</plugin>
```

Với Gradle:

```groovy
graalvmNative {
    binaries {
        main {
            buildArgs.add('--exact-reachability-metadata')
        }
    }
}
```

Sau đó build bằng plugin tương ứng, ví dụ `./mvnw -Pnative native:compile` hoặc `./gradlew nativeCompile`.

Chạy native executable với:

```bash
./order-service -XX:MissingRegistrationReportingMode=Warn
```

Sau khi xử lý warning, chạy test với `Exit` để phát hiện lỗi metadata bị code bắt và bỏ qua:

```bash
./order-service -XX:MissingRegistrationReportingMode=Exit
```

Tên option và hành vi có thể khác trên GraalVM/JDK cũ. Kiểm tra tài liệu đúng version trước khi đưa vào CI.

### 10.3. Tạo metadata từ Tracing Agent

Metadata do agent thu thập có thể dùng làm đầu vào, nhưng phải review và loại test-only entries. Nếu dependency là thư viện dùng chung, cân nhắc cung cấp metadata trong chính artifact hoặc đóng góp vào Reachability Metadata Repository thay vì để mỗi ứng dụng phải duy trì bản sao.

### 10.4. Refactor dynamic behavior thành contract tĩnh

Một số thay đổi thường có thể giảm rủi ro:

| Mẫu hiện tại | Hướng chuyển đổi |
|---|---|
| `Class.forName` từ property bất kỳ | Registry map tên hợp lệ sang class/bean được biết ở build time |
| Plugin JAR mount sau deploy | Đưa plugin vào dependency graph hoặc build artifact theo plugin set |
| Classpath scan khi runtime | Thực hiện discovery khi AOT/build và sinh registry |
| Bean đăng ký qua `registerSingleton` | Đăng ký `BeanDefinition` trong AOT-visible extension point |
| Resource path tùy ý từ request | Allowlist resource và đăng ký các pattern hợp lệ |
| Constructor/method được chọn động | Factory rõ ràng hoặc hints cho tập member hữu hạn |
| Static initializer đọc DNS/file/secret | Đưa thao tác sang runtime lifecycle và external configuration |

Không refactor chỉ để thỏa Native Image nếu điều đó làm mất yêu cầu sản phẩm quan trọng. Khi runtime extensibility là đặc tính cốt lõi, giữ JVM cho service đó có thể là quyết định tốt hơn.

## 11. Chọn chiến lược migration

### 11.1. Không cần chuyển toàn bộ hệ thống cùng lúc

Một hệ thống microservices có thể dùng cả JVM và native executable. Chọn service theo workload và rủi ro:

- Native trước cho worker hoặc service có cold-start/memory pressure rõ rệt.
- Giữ JVM cho plugin host hoặc service dùng dynamic class loading tùy ý.
- Chia shared library và service owner để metadata được quản lý tại đúng module.
- Chỉ chuyển service có dependency và runtime behavior đã được kiểm chứng.

### 11.2. Hai artifact song song

Trong giai đoạn chuyển đổi, có thể tiếp tục phát hành JVM artifact và native artifact từ cùng source revision. Dùng pipeline riêng để build/test, gắn tag rõ ràng và triển khai vào môi trường thử nghiệm. Điều này giúp so sánh behavior/performance và rollback mà không buộc toàn tổ chức chuyển đổi cùng lúc.

Native executable thường gắn với OS/architecture. Nếu deploy nhiều nền tảng, pipeline cần build artifact riêng hoặc dùng cách đóng gói phù hợp cho từng target. Không giả định một binary Linux x64 có thể chạy trên Linux ARM64 hoặc Windows.

### 11.3. Rollout theo traffic và khả năng rollback

Khi native artifact đã pass tests:

1. Triển khai vào môi trường integration/staging với traffic và external dependencies tương đương production.
2. Chạy smoke, contract, performance và soak tests.
3. Rollout một tỷ lệ nhỏ instance hoặc một service canary.
4. Theo dõi startup failure, readiness, error rate, latency, RSS và restart count.
5. Mở rộng rollout khi metric đạt ngưỡng đã định.
6. Giữ JVM artifact và quy trình rollback sẵn sàng trong thời gian quan sát.

Không dùng startup time tốt hơn làm tiêu chí duy nhất. Native artifact vẫn phải đạt correctness, throughput, latency và operational SLO.

## 12. Ma trận rủi ro và tiêu chí go/no-go

### 12.1. Ma trận đánh giá

| Hạng mục | Green | Amber | Red |
|---|---|---|---|
| Spring AOT | AOT-on-JVM pass trên mọi profile artifact cần hỗ trợ | Một số configuration cần refactor | Bean graph phải thay đổi tùy ý sau runtime hoặc không thể tạo AOT context |
| Dependencies | Tất cả dependency quan trọng có native support/metadata đã test | Có dependency cần hints hoặc version upgrade | Dependency bắt buộc dựa vào dynamic code loading không thể thay đổi |
| Reflection/resource | Tập truy cập hữu hạn và có metadata | Chưa bao phủ hết feature paths | Cần nạp class/resource tùy ý không thể biết khi build |
| JNI/native library | Có binary đúng target và test pass | Cần build/đóng gói thêm | Không có binary hoặc vendor không hỗ trợ target bắt buộc |
| Runtime config | Bean graph ổn định, config thay đổi ở runtime trong phạm vi hỗ trợ | Cần nhiều artifact theo profile | Phải tạo bean/plugin tùy ý theo cấu hình sau deploy |
| Testing | JVM, AOT, native smoke/integration đều pass | Một số feature chưa có native test | Không thể kiểm thử hoặc lỗi native chưa giải thích được |
| Performance | Có lợi ích đo được theo mục tiêu | Lợi ích nhỏ hoặc chưa ổn định | Không có lợi ích bù chi phí build/vận hành |
| CI/CD | Runner/toolchain đủ tài nguyên và tái lập | Cần nâng runner hoặc tách pipeline | Không thể build target trong thời gian/chi phí cho phép |

### 12.2. Quyết định

**Go** khi các dependency quan trọng được hỗ trợ, bean graph có thể cố định ở build time, dynamic features có metadata/test đầy đủ, native runtime pass và số đo cho thấy lợi ích phù hợp mục tiêu.

**Go có điều kiện** khi còn một số dependency hoặc feature cần xử lý nhưng đã xác định rõ owner, effort, test và thời hạn. Chỉ mở rộng rollout sau khi các mục amber được đóng.

**No-go hoặc giữ JVM** khi ứng dụng bắt buộc nạp plugin/class tùy ý sau deploy, dependency thiết yếu không có giải pháp native, hoặc lợi ích không bù chi phí và rủi ro vận hành.

Không coi `native-image` build thành công là bằng chứng migration hoàn tất. Chỉ native runtime tests và workload measurements mới xác nhận artifact phù hợp.

## 13. Mẫu hồ sơ đánh giá migration

### 13.1. Thông tin ứng dụng

| Trường | Giá trị |
|---|---|
| Service/module | _(ghi)_ |
| Spring Boot / Framework | _(ghi)_ |
| JDK vendor/version | _(ghi)_ |
| Build tool/version | Maven / Gradle / _(ghi)_ |
| Deployment target | Linux x64 / ARM64 / Windows / _(ghi)_ |
| Runtime profiles | _(ghi)_ |
| SLO startup-to-ready | _(ghi)_ |
| Memory limit | _(ghi)_ |
| Current JVM baseline | _(ghi)_ |

### 13.2. Dependency inventory

| Dependency | Version | Native metadata/support | Dynamic feature | Risk | Owner/action |
|---|---|---|---|---|---|
| _(artifact)_ | _(version)_ | Green/Unknown/No | Reflection/JNI/Resource/... | Green/Amber/Red | _(ghi)_ |

### 13.3. Dynamic feature inventory

| Feature | Vị trí code/dependency | Tập class/resource hữu hạn? | Metadata/refactor | Test cần có | Trạng thái |
|---|---|---|---|---|---|
| Reflection | _(ghi)_ | Có/Không | _(ghi)_ | _(ghi)_ | Green/Amber/Red |
| Resource loading | _(ghi)_ | Có/Không | _(ghi)_ | _(ghi)_ | Green/Amber/Red |
| Proxy/AOP | _(ghi)_ | Có/Không | _(ghi)_ | _(ghi)_ | Green/Amber/Red |
| Serialization | _(ghi)_ | Có/Không | _(ghi)_ | _(ghi)_ | Green/Amber/Red |
| JNI/JNA/FFM | _(ghi)_ | Có/Không | _(ghi)_ | _(ghi)_ | Green/Amber/Red |
| Class loading/plugin | _(ghi)_ | Có/Không | _(ghi)_ | _(ghi)_ | Green/Amber/Red |
| Class initialization | _(ghi)_ | Build/runtime | _(ghi)_ | _(ghi)_ | Green/Amber/Red |

### 13.4. Kết quả kiểm thử và hiệu năng

| Kiểm tra | Kết quả | Evidence/link |
|---|---|---|
| JVM regression tests | PASS/FAIL | _(ghi)_ |
| Spring AOT processing | PASS/FAIL | _(ghi)_ |
| AOT-on-JVM | PASS/FAIL | _(ghi)_ |
| Native compilation | PASS/FAIL | _(ghi)_ |
| Native smoke tests | PASS/FAIL | _(ghi)_ |
| Native integration tests | PASS/FAIL | _(ghi)_ |
| Native runtime in container | PASS/FAIL | _(ghi)_ |
| Exact reachability metadata | PASS/FAIL/N/A | _(ghi)_ |
| Startup-to-ready | _(ghi)_ | _(ghi)_ |
| RSS steady state | _(ghi)_ | _(ghi)_ |
| Throughput/p95 latency | _(ghi)_ | _(ghi)_ |
| Build duration/runner peak | _(ghi)_ | _(ghi)_ |

### 13.5. Kết luận migration

| Câu hỏi | Kết luận |
|---|---|
| Có thể cố định classpath và bean graph không? | Yes / No / Conditional |
| Có dynamic feature không thể thay đổi không? | Yes / No |
| Có dependency blocker không? | Yes / No |
| Có giải pháp metadata/refactor cho phần Amber không? | _(ghi)_ |
| Native runtime đạt functional requirements? | Yes / No |
| Native đạt SLO/performance target? | Yes / No |
| Chi phí CI/maintenance chấp nhận được? | Yes / No |
| Quyết định | GO / CONDITIONAL GO / NO-GO |
| Owner và mốc xử lý | _(ghi)_ |

## 14. Bài thực hành: đánh giá một service JVM trước khi chuyển

**Bối cảnh:** `order-service` là Spring Boot application đang chạy trên JVM. Service dùng Web, Security, JPA, PostgreSQL, Flyway, Jackson, một PDF library và một plugin export được chọn qua property.

### Bước 1 — Chụp baseline

Ghi startup-to-ready, RSS, throughput, p95/p99 latency, image size và build duration của JVM artifact trong môi trường đại diện.

### Bước 2 — Lập dependency inventory

Chạy `dependency:tree` hoặc Gradle `dependencies`. Tra cứu metadata/native support cho PostgreSQL driver, Flyway, PDF library và các dependency quan trọng. Ghi version và owner.

### Bước 3 — Kiểm kê dynamic features

Tìm reflection, resource loading, proxy, serialization, JNI, ServiceLoader và plugin class loading. Xác định plugin export là tập hữu hạn trong build hay có thể thêm JAR tùy ý sau deploy.

### Bước 4 — Kiểm tra Spring AOT constraints

Kiểm tra profile `production`, các `@Conditional`, programmatic bean registration, `registerSingleton`, custom suppliers và `@Bean` return types. Ghi những cấu hình phải cố định khi build.

### Bước 5 — Chạy AOT-on-JVM

Build JAR có AOT assets và chạy với `-Dspring.aot.enabled=true`. Chạy regression tests cho API, database, security và export.

### Bước 6 — Build native spike

Tạo native executable cho đúng target OS/architecture. Dùng exact reachability metadata và chạy luồng export, database, TLS và resource. Ghi warnings, metadata cần bổ sung và thời gian build.

### Bước 7 — Đo native runtime

Chạy container native với cùng memory limit và workload như JVM. So sánh startup-to-ready, RSS, throughput, latency và chi phí CI.

### Bước 8 — Quyết định

Nếu plugin export chỉ là một tập hữu hạn, đăng ký ở build time hoặc tạo artifact theo plugin set. Nếu plugin JAR phải được thêm tùy ý sau deploy, đánh dấu đây là blocker cho service đó hoặc giữ JVM. Ghi GO/CONDITIONAL GO/NO-GO cùng owner và effort.

### Phiếu kết quả

| Hạng mục | Kết quả cần ghi |
|---|---|
| Dependency inventory hoàn tất | PASS/FAIL |
| Dynamic feature inventory hoàn tất | PASS/FAIL |
| Spring AOT constraints được đánh giá | PASS/FAIL |
| Metadata gaps được xác định | PASS/FAIL |
| AOT-on-JVM | PASS/FAIL |
| Native build | PASS/FAIL |
| Native runtime tests | PASS/FAIL |
| Performance comparison | PASS/FAIL |
| Migration decision | GO / CONDITIONAL GO / NO-GO |

## 15. Ghi nhớ

Đánh giá migration Native Image bắt đầu bằng inventory ứng dụng, không bắt đầu bằng cách thay lệnh build. Hãy ghi dependency và version, profile/conditional bean, dynamic features, native libraries, class initialization và runtime environment. Phân biệt tính năng động có thể mô tả bằng metadata với yêu cầu nạp code tùy ý sau deploy.

Spring AOT yêu cầu classpath và bean graph được xác định ở build time; các profile và condition ảnh hưởng bean creation cũng được quyết định lúc đó. Native Image cần reachability metadata cho các truy cập động mà static analysis không thể suy ra. Hãy dùng AOT-on-JVM, native build, native integration tests và workload measurements theo từng tầng. Chỉ chuyển khi ứng dụng đạt correctness, vận hành và lợi ích kinh tế; giữ JVM cho module có yêu cầu dynamic runtime không phù hợp là một lựa chọn hợp lệ.

### Tài liệu tham khảo chính thức

- [Spring Framework — Ahead-of-Time Optimizations and Restrictions](https://docs.spring.io/spring-framework/reference/core/aot.html)
- [Spring Boot — Advanced Native Images Topics and Known Limitations](https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html)
- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html)
- [Spring Boot — GraalVM Native Image Support](https://docs.spring.io/spring-boot/reference/packaging/native-image/index.html)
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/)
- [GraalVM — Collect Metadata with the Tracing Agent](https://www.graalvm.org/latest/reference-manual/native-image/metadata/AutomaticMetadataCollection/)
- [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata)
- [Spring AOT Smoke Tests](https://github.com/spring-projects/spring-aot-smoke-tests)
