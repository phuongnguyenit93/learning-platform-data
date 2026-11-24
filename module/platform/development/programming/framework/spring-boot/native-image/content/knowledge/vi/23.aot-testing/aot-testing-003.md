# Phân biệt lỗi phân tích bean với lỗi chỉ xảy ra khi biên dịch native

Khi chuyển ứng dụng Spring Boot sang GraalVM Native Image, một lệnh build có thể chạy qua nhiều giai đoạn: biên dịch Java, phân tích ApplicationContext bằng Spring AOT, sinh và biên dịch mã AOT, phân tích/biên dịch bằng Native Image, rồi mới tạo executable. Một lỗi xuất hiện trong lệnh native build không nhất thiết là lỗi của cùng một giai đoạn.

Phân loại đúng lỗi giúp tiết kiệm thời gian: **lỗi phân tích bean** thường xuất hiện khi Spring chuẩn bị BeanFactory ở build time; **lỗi biên dịch native** xuất hiện sau khi Spring AOT đã tạo được đầu vào cho GraalVM; **lỗi native runtime** chỉ xuất hiện khi chạy executable. Ba nhóm này có nguyên nhân và cách xử lý khác nhau.

Bài này trình bày pipeline theo từng ranh giới, các dấu hiệu trong log, cách cô lập bằng Maven/Gradle, cách kiểm tra AOT-generated code trên JVM và cách thu thập diagnostics khi Native Image compiler thất bại.

## 1. Nhìn toàn bộ pipeline trước khi đọc lỗi

Một ứng dụng Spring Boot native thường đi qua các bước sau:

~~~mermaid
flowchart TD
    A["Source Java + dependencies"] --> B["Compile Java"]
    B --> C["Spring AOT: khởi tạo context và chuẩn bị BeanFactory"]
    C --> D["Sinh AOT source và runtime hints"]
    D --> E["Compile generated source"]
    E --> F["GraalVM Native Image analysis và compilation"]
    F --> G["Link native executable"]
    G --> H["Chạy native executable"]
    C --> X["Bean/configuration analysis error"]
    D --> Y["AOT contribution hoặc code generation error"]
    E --> Z["Generated source compilation error"]
    F --> N["Native Image analysis/compilation error"]
    H --> R["Native runtime error"]
~~~

Có thể nhóm các lỗi theo ranh giới:

| Giai đoạn | Công việc | Ví dụ lỗi |
| --- | --- | --- |
| Java compile | Compile source và annotation processing thông thường | Java syntax, type mismatch, dependency không resolve |
| Spring AOT bean analysis | Tạo context, xử lý configuration và chuẩn bị BeanFactory | Không tìm thấy bean, nhiều bean cùng candidate, condition/property sai, post-processor lỗi |
| AOT contribution/code generation | Framework và thư viện đóng góp mã/hints | AOT processor ném exception, runtime hints registrar lỗi, generated source không hợp lệ |
| Generated source compile | Compile Java source do AOT sinh | Import/type/method không hợp lệ trong generated source, API không tương thích |
| Native Image build | Reachability analysis, class initialization, native compilation và linking | Unsupported feature, analysis failure, build-time initializer lỗi, C compiler/linker lỗi |
| Native runtime | Chạy executable và thực hiện luồng nghiệp vụ | Thiếu metadata chỉ lộ ra khi truy cập động, resource thiếu, lỗi cấu hình runtime |

**Điểm phân biệt cốt lõi:** Spring AOT cần chuẩn bị một BeanFactory hợp lệ để sinh code; GraalVM cần phân tích và biên dịch code đã được chuẩn bị. Nếu Spring chưa tạo được mô hình bean, việc điều chỉnh compiler option của GraalVM thường không giải quyết đúng nguyên nhân.

## 2. Lỗi phân tích bean xảy ra ở đâu?

Spring AOT phân tích ứng dụng trong một tiến trình JVM tại build time. Spring Boot khởi tạo ApplicationContext theo cấu hình dành cho AOT, xử lý bean definitions và các post-processors cần thiết, rồi chuẩn bị mô hình để sinh mã khởi tạo.

Không nên hiểu rằng mọi bean nghiệp vụ đều được khởi tạo hoàn chỉnh như một lần chạy production. Tuy nhiên, các bước chuẩn bị BeanFactory và xử lý cấu hình có thể kích hoạt một số thành phần hạ tầng, factory method hoặc processor. Lỗi trong các bước đó có thể khiến AOT dừng trước khi Native Image compiler được gọi.

### Các nguyên nhân phổ biến

**Thiếu bean hoặc dependency không thể phân giải**

~~~java
@Service
public class InvoiceService {

    public InvoiceService(PaymentGateway paymentGateway) {
        // ...
    }
}
~~~

Nếu không có bean nào cung cấp PaymentGateway, context có thể báo NoSuchBeanDefinitionException hoặc một UnsatisfiedDependencyException bao quanh lỗi gốc.

**Có nhiều bean cùng phù hợp**

~~~java
public interface PaymentGateway {
}

@Component
class CardPaymentGateway implements PaymentGateway {
}

@Component
class BankPaymentGateway implements PaymentGateway {
}
~~~

Nếu một service inject PaymentGateway mà không có @Primary, @Qualifier hoặc quy tắc lựa chọn rõ ràng, Spring có thể báo NoUniqueBeanDefinitionException.

**Condition được đánh giá ở build time**

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "billing.audit",
        name = "enabled",
        havingValue = "true"
)
class AuditConfiguration {

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
~~~

Spring AOT đánh giá điều kiện khi xử lý context. Nếu property không có trong môi trường AOT, bean AuditService có thể không được đưa vào mô hình đã sinh. Sau đó, nếu code runtime kỳ vọng bean đó luôn tồn tại, ứng dụng có thể gặp lỗi khi chạy AOT/native.

Điều kiện bean không phải lúc nào cũng là lỗi. Vấn đề là **cấu hình dùng để phân tích AOT phải đại diện cho bean graph mà binary cần hỗ trợ**.

**BeanFactoryPostProcessor hoặc BeanDefinitionRegistryPostProcessor có lỗi**

Các processor có thể thêm, sửa hoặc loại bean definitions. Nếu logic phụ thuộc database, HTTP, biến môi trường chỉ có trong container hoặc dữ liệu chỉ tồn tại lúc runtime, quá trình AOT có thể không tái hiện được cấu trúc bean mong đợi.

**Cấu hình properties không hợp lệ**

Các lỗi conversion, validation hoặc constructor binding có thể làm context không khởi tạo được. Ví dụ, một Duration nhận giá trị không đúng định dạng hoặc một property bắt buộc bị thiếu.

**Static initializer hoặc factory method có side effect**

Một cấu hình gọi hệ thống ngoài trong lúc AOT phân tích có thể thất bại do môi trường build không có database, secret hoặc network tương tự production. Hãy xem stack trace để xác định code đó chạy trong quá trình tạo context hay ở Native Image compiler.

## 3. Dấu hiệu nhận biết lỗi Spring AOT bean analysis

Log có thể chứa các class/exception thuộc Spring Framework và Spring Boot, ví dụ:

- BeanCreationException
- UnsatisfiedDependencyException
- NoSuchBeanDefinitionException
- NoUniqueBeanDefinitionException
- BeanDefinitionStoreException
- ConfigurationPropertiesBindException
- BindException
- IllegalStateException phát sinh từ configuration class hoặc post-processor

Tên exception chỉ là dấu hiệu ban đầu. Hãy đọc **exception gốc (root cause)** và stack frame đầu tiên thuộc code ứng dụng.

Ví dụ log rút gọn:

~~~text
Error processing application context
org.springframework.beans.factory.UnsatisfiedDependencyException:
  Error creating bean with name 'invoiceService'
Caused by: org.springframework.beans.factory.NoSuchBeanDefinitionException:
  No qualifying bean of type 'PaymentGateway' available
~~~

Đây là lỗi BeanFactory analysis. GraalVM chưa cần tham gia để giải quyết việc thiếu PaymentGateway.

Một dấu hiệu khác là log dừng ở task processAot hoặc Maven goal spring-boot:process-aot. Nếu task này thất bại trước khi gọi native-image, chưa có bằng chứng cho thấy native compiler là nguyên nhân.

### Condition evaluation report

Khi nghi ngờ auto-configuration hoặc @Conditional..., bật debug cho tiến trình AOT để xem condition evaluation report:

Với Maven, cấu hình application arguments cho goal AOT trong Spring Boot Maven Plugin, sau đó chạy lại goal. Ví dụ phần cấu hình plugin:

~~~xml
<configuration>
    <arguments>
        <argument>--debug</argument>
    </arguments>
</configuration>
~~~

Có thể dùng systemPropertyVariables hoặc profiles của goal để đặt giá trị cần cho AOT. Với Gradle, thêm application argument hoặc system property cho task processAot.

Tìm các mục Positive matches, Negative matches và lý do condition không match. Đừng vội thêm bean thủ công trước khi biết auto-configuration bị tắt bởi property, classpath hay profile nào.

## 4. Vì sao cấu hình build time có thể khác runtime?

Spring AOT tạo một mô hình bean đã được chuẩn bị ở build time. Các điều kiện như @Profile, @ConditionalOnProperty, @ConditionalOnClass và một số điều kiện auto-configuration được đánh giá trong môi trường đó.

Vì vậy, các giá trị sau có thể ảnh hưởng trực tiếp đến tập bean được sinh:

- Active profiles.
- Environment variables.
- System properties.
- Application arguments.
- Property sources được nạp trong lúc AOT.
- Classpath và dependencies của build.

Ví dụ, nếu build AOT với billing.audit.enabled=false, nhưng production chạy với billing.audit.enabled=true, không nên kỳ vọng binary tự tạo thêm một bean mà AOT không đưa vào mô hình.

### Đặt cấu hình cho tiến trình AOT

Với Maven, goal spring-boot:process-aot có thể được cấu hình để nhận environment variables, system properties và application arguments. Ví dụ minh họa trong cấu hình plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <profiles>
            <profile>native</profile>
        </profiles>
        <arguments>
            <argument>--debug</argument>
        </arguments>
        <systemPropertyVariables>
            <billing.audit.enabled>true</billing.audit.enabled>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

Trong cấu hình này, profiles là Spring profile được áp dụng khi AOT xử lý context; arguments là application arguments; systemPropertyVariables truyền JVM system properties cho tiến trình AOT. Nếu dự án dùng spring-boot-starter-parent, Maven profile tên native có thể tự bind process-aot vào lifecycle; đừng nhầm Maven profile đó với Spring profile được truyền cho ứng dụng. Kiểm tra đúng execution và log của tiến trình AOT.

Với Gradle, processAot là một JavaExec task, do đó có thể cấu hình environment, system properties và arguments của task. Ví dụ Groovy DSL:

~~~groovy
tasks.named("processAot") {
    systemProperty("billing.audit.enabled", "true")
    environment("SPRING_PROFILES_ACTIVE", "native")
}
~~~

Không cần khai báo đồng thời cùng một profile qua nhiều cơ chế nếu chúng có thể mâu thuẫn. Chọn một nguồn cấu hình nhất quán và xác nhận trong log AOT.

### Cấu hình runtime vẫn có thể thay đổi giá trị, nhưng không tùy ý đổi bean graph

Một số giá trị như endpoint, timeout, credentials hoặc feature parameters có thể được đọc lúc runtime nếu chúng không quyết định cấu trúc bean đã đóng gói. Cần phân biệt:

- **Giá trị cấu hình của một bean đã tồn tại:** có thể lấy từ runtime property source.
- **Quyết định bean có tồn tại hay không:** đã được đánh giá khi AOT tạo mô hình context.

Đây là lý do nên dùng constructor injection/@ConfigurationProperties cho giá trị runtime và giới hạn condition tạo bean ở những lựa chọn được quyết định rõ khi build.

## 5. Lỗi AOT contribution và generated source khác lỗi phân tích bean

Ngay cả khi BeanFactory đã được chuẩn bị, Spring AOT vẫn còn công việc sinh code và thu thập runtime hints.

Framework hoặc thư viện có thể đóng góp thông tin AOT thông qua các SPI như:

- BeanFactoryInitializationAotProcessor
- BeanRegistrationAotProcessor
- RuntimeHintsRegistrar
- RuntimeHints

Nếu một custom processor hoặc registrar ném exception, lỗi có thể xảy ra sau khi phần lớn bean analysis đã hoàn thành nhưng trước khi native compiler bắt đầu.

Ví dụ một registrar có lỗi:

~~~java
public final class FeatureHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        // Lỗi ví dụ: code tự viết ném exception khi đọc file cấu hình build.
        throw new IllegalStateException("Cannot load feature metadata");
    }
}
~~~

Nếu stack trace dừng ở registerHints, hãy kiểm tra code registrar, file nó đọc, class loader và dữ liệu build-time. Không nên xử lý lỗi đó bằng cách thêm --initialize-at-run-time cho một class không liên quan.

### Generated source compile failure

Spring AOT có thể sinh Java source để đăng ký bean và khởi tạo context. Nếu source được sinh không compile được, lỗi sẽ thuộc bước compile generated source.

Dấu hiệu thường gặp:

- Compilation failure hoặc cannot find symbol.
- Package/class không tồn tại trong compile classpath.
- Generated method gọi API không có trong version dependency hiện tại.
- AOT contribution sinh code không tương thích với phiên bản Spring Framework đang dùng.

Mở file generated source được chỉ ra trong compiler output. Kiểm tra API được gọi, dependency version và custom AOT contribution. **Không sửa trực tiếp generated source** vì lần build sau sẽ ghi đè; sửa source processor, configuration hoặc dependency tạo ra code đó.

## 6. Dấu hiệu nhận biết lỗi Native Image compilation

Khi Spring AOT đã hoàn tất và generated code đã compile, GraalVM Native Image mới thực hiện phân tích và biên dịch native.

Log thường cho thấy compiler bắt đầu các giai đoạn như:

- Initializing Native Image build.
- Performing analysis.
- Reachability/points-to analysis.
- Compiling methods.
- Creating image.
- Linking hoặc tạo executable.

Chi tiết tên stage thay đổi theo GraalVM version và build mode.

Các lỗi thường gặp ở giai đoạn này:

| Nhóm lỗi | Ví dụ dấu hiệu | Ý nghĩa |
| --- | --- | --- |
| Unsupported feature | UnsupportedFeatureError hoặc thông báo một API không được hỗ trợ | Code reachable sử dụng tính năng Native Image không hỗ trợ theo cách đó |
| Analysis/reachability | Analysis error, unresolved type hoặc method | Static analysis không thể hoàn tất việc xác định code cần đưa vào image |
| Class initialization | Lỗi initializer trong hosted/build-time context | Static initializer thực hiện thao tác không phù hợp lúc build |
| Metadata/build configuration | Warning hoặc error về reflection/resource/JNI/proxy/serialization registration | Metadata hoặc cấu hình cho dynamic access chưa phù hợp; tùy trường hợp lỗi có thể chỉ lộ ra ở runtime |
| Native toolchain | Compiler, linker, header hoặc system library không tìm thấy | Môi trường build native thiếu công cụ/thư viện hoặc target không tương thích |
| Resource/build capacity | Hết RAM, disk hoặc thời gian build | Tài nguyên môi trường build không đủ |

Ví dụ, một lỗi linker như không tìm thấy system library không liên quan đến việc Spring có đăng ký PaymentGateway hay không. Ngược lại, lỗi bean analysis không thể sửa bằng cách cài thêm C compiler.

### Không phải thiếu metadata nào cũng làm build thất bại

Một số truy cập động có thể không được static analysis phát hiện nhưng cũng không bị thực thi trong lúc build. Native executable vẫn có thể được tạo thành công rồi mới lỗi khi đi vào nhánh reflection, resource, serialization hoặc proxy tương ứng.

Do đó cần phân biệt:

- **Build-time metadata/analysis error:** compiler báo không thể phân tích hoặc xử lý cấu hình.
- **Runtime missing metadata:** executable được tạo nhưng một dynamic access thất bại khi chạy.

Không nên kết luận rằng native compilation thành công đồng nghĩa mọi reflection/resource đã được khai báo đầy đủ.

## 7. Dùng AOT-processed JVM để cô lập lỗi

Spring Boot cho phép chạy ứng dụng trên JVM nhưng dùng mã khởi tạo do Spring AOT sinh, thông qua system property:

~~~bash
java -Dspring.aot.enabled=true -jar target/myapplication.jar
~~~

Điều kiện là JAR đã chứa AOT-generated code. Với Maven, thường cần build bằng profile native; với Gradle, cần cấu hình AOT plugin tương ứng.

Phép thử này hữu ích vì nó tách hai câu hỏi:

1. Spring AOT có sinh được context initialization code và code đó có chạy được trên JVM không?
2. GraalVM có biên dịch code đó thành native executable được không?

### Cách diễn giải kết quả

| Kết quả | Kết luận sơ bộ | Bước tiếp theo |
| --- | --- | --- |
| processAot thất bại | Lỗi Spring AOT/BeanFactory analysis hoặc AOT contribution | Đọc root cause và sửa cấu hình/processor |
| processAot thành công, generated source compile thất bại | Lỗi compile code được sinh hoặc dependency/API mismatch | Mở source và compiler diagnostic |
| AOT JAR chạy trên JVM với spring.aot.enabled=true thất bại | Generated initialization code hoặc cấu hình AOT có vấn đề | Xem stack trace khi khởi tạo AOT context |
| AOT JAR chạy được trên JVM, native compile thất bại | Lỗi ở GraalVM analysis/compiler/toolchain hoặc khác biệt Native Image | Bật diagnostics và phân tích native build log |
| Native compile thành công, executable chạy lỗi | Lỗi native runtime, metadata hoặc khác biệt runtime | Tái hiện trên binary, xem exception và missing metadata |

Đây là cách khoanh vùng rất hiệu quả: **AOT-processed JVM chạy được không chứng minh native chắc chắn thành công, nhưng nó loại trừ được một số lỗi ở tầng generated Spring context**.

## 8. Quy trình cô lập từng giai đoạn bằng Maven và Gradle

Không nên bắt đầu bằng một lệnh build dài rồi chỉ nhìn dòng BUILD FAILURE. Chạy từng bước để biết giai đoạn đầu tiên thất bại.

### Maven

Với dự án đã cấu hình Spring Boot Maven plugin và Native Build Tools:

~~~bash
# 1. Compile source Java.
./mvnw clean compile

# 2. Chạy Spring AOT application processing.
./mvnw -Pnative spring-boot:process-aot

# 3. Đóng gói JAR có AOT-generated code.
./mvnw -Pnative package -DskipTests

# 4. Chạy JAR trên JVM nhưng dùng AOT-generated initialization.
java -Dspring.aot.enabled=true -jar target/myapplication.jar

# 5. Chạy native compilation.
./mvnw -Pnative native:compile -DskipTests
~~~

Goal và profile phụ thuộc cấu hình plugin của project. Nếu spring-boot:process-aot không được resolve, kiểm tra Spring Boot Maven plugin version và execution đã khai báo; nếu native:compile không tồn tại, kiểm tra native-maven-plugin và profile tương ứng.

### Gradle

Với Spring Boot Gradle plugin và GraalVM Native Build Tools:

~~~bash
# 1. Compile source Java.
./gradlew clean compileJava

# 2. Chạy Spring AOT processing.
./gradlew processAot

# 3. Chạy test JVM.
./gradlew test

# 4. Build JAR chứa AOT output.
./gradlew bootJar

# 5. Chạy JAR trên JVM với AOT-generated code.
java -Dspring.aot.enabled=true -jar build/libs/myapplication.jar

# 6. Build native executable.
./gradlew nativeCompile
~~~

Nếu build cần AOT test processing, kiểm tra task processTestAot. Plugin Native Build Tools có thể cấu hình nativeTest để dùng output từ application/test AOT processing khi project đáp ứng điều kiện hỗ trợ.

### Dừng tại bước đầu tiên thất bại

Ví dụ:

- compileJava thành công.
- processAot thất bại với NoSuchBeanDefinitionException.

Kết luận: lỗi nằm trong bean analysis; không cần tiếp tục thử đổi GraalVM compiler flags cho đến khi context AOT hợp lệ.

Ngược lại:

- processAot thành công.
- Generated sources compile thành công.
- nativeCompile thất bại ở Performing analysis với UnsupportedFeatureError.

Kết luận: tập trung vào class/feature mà GraalVM báo lỗi, không quay lại thay đổi bean graph nếu chưa có bằng chứng liên quan.

## 9. Kiểm tra test AOT và native test

Spring Boot có thể xử lý cả application context của test bằng AOT. Với JUnit 5 và Spring TestContext Framework, các test phù hợp có thể được xử lý qua processTestAot; Native Build Tools có thể cung cấp task nativeTest.

Cần phân biệt ba loại test:

| Loại test | Kiểm tra điều gì? | Hạn chế |
| --- | --- | --- |
| Unit/integration test trên JVM | Logic nghiệp vụ, dependency injection và phần lớn context behavior | Không chứng minh Native Image metadata đầy đủ |
| AOT-processed test trên JVM | Test context dùng code initializer được sinh ở build time | Chưa chạy trong native executable |
| Native test/native integration test | Hành vi trên executable native hoặc native test binary | Build chậm hơn; nên tập trung vào các khác biệt native |

Khuyến nghị là tiếp tục chạy phần lớn unit/integration tests trên JVM để giữ feedback nhanh. Dành native tests cho các khu vực dễ khác biệt:

- Reflection và dynamic access.
- Serialization và JSON binding.
- Resource, resource bundle và file đọc từ classpath.
- Dynamic proxy, class generation hoặc JNI.
- Class initialization và static state.
- Các điều kiện bean được chốt ở AOT build time.

Một test AOT có thể thất bại vì test context có bean graph khác application context. Hãy xác định task đang chạy processAot hay processTestAot trước khi kết luận lỗi thuộc ứng dụng production.

## 10. Thu thập diagnostics khi Native Image compiler thất bại

Nếu AOT processing và generated source compile đều thành công nhưng native build vẫn thất bại, bật diagnostics cho GraalVM.

Native Image hỗ trợ --diagnostics-mode để tạo thêm thông tin về các hoạt động như class initialization và substitutions. Tùy version, có thể bổ sung các option chi tiết hơn.

Ví dụ chạy trực tiếp compiler với option minh họa:

~~~bash
native-image --diagnostics-mode -jar target/myapplication.jar
~~~

Với Maven/Gradle Native Build Tools, truyền option qua cấu hình buildArgs của plugin:

~~~groovy
graalvmNative {
    binaries {
        named("main") {
            buildArgs.add("--diagnostics-mode")
        }
    }
}
~~~

Tên binary và DSL phụ thuộc plugin version. Với Maven, thêm build argument vào native-maven-plugin đang được project sử dụng.

Khi đọc diagnostics:

1. Tìm stage đầu tiên báo lỗi, không chỉ dòng tổng kết cuối.
2. Đọc exception và toàn bộ Caused by.
3. Ghi class, method hoặc feature mà compiler chỉ ra.
4. Nếu lỗi class initialization, kiểm tra static initializer và build-time/runtime policy.
5. Nếu lỗi unsupported feature, xác định API/library gây ra và kiểm tra compatibility guide.
6. Nếu lỗi linker, kiểm tra OS, architecture, compiler, linker và native system libraries.
7. Ghi chính xác JDK/GraalVM version, Spring Boot version, plugin version và command build.

Không bật hàng loạt option tối ưu hoặc ép class initialization ở build time để thử vận may. Mỗi thay đổi phải gắn với lỗi và được kiểm chứng bằng native executable.

## 11. Bảng chẩn đoán nhanh theo thông báo lỗi

| Thông báo hoặc dấu hiệu | Giai đoạn có khả năng | Câu hỏi cần trả lời trước |
| --- | --- | --- |
| No qualifying bean of type ... | Spring AOT bean analysis | Bean có được đăng ký, condition có match và profile có đúng không? |
| NoUniqueBeanDefinitionException | Spring AOT bean analysis | Có nhiều implementation và thiếu @Primary/@Qualifier không? |
| ConfigurationPropertiesBindException | Context/configuration binding | Property source của AOT có giá trị và đúng format không? |
| Exception trong BeanFactoryPostProcessor | BeanFactory preparation | Processor có phụ thuộc hệ thống ngoài hoặc giả định runtime không? |
| Exception trong RuntimeHintsRegistrar | AOT contribution | Registrar có đọc class/resource hợp lệ và chạy an toàn ở build time không? |
| cannot find symbol trong generated source | Generated source compilation | API/dependency version hoặc AOT contribution có tương thích không? |
| UnsupportedFeatureError | Native Image analysis/build | Library có dùng API chưa được hỗ trợ trong native không? |
| Error khi initialize class trong image build | Native Image class initialization | Static initializer có đọc environment, mở file/network hoặc tạo thread không? |
| C compiler/linker error | Native linking | Toolchain và system libraries của target có sẵn không? |
| MissingReflectionRegistrationError hoặc lỗi reflection tương tự khi chạy | Native runtime | Hints có được đăng ký cho đúng type/member không? |
| Resource không tìm thấy chỉ trên native | Native runtime/resource metadata | Resource pattern hoặc resource bundle có được đưa vào image không? |
| Native executable khởi động nhưng bean bị thiếu | Native runtime/AOT configuration mismatch | Build-time condition/profile có khác cấu hình runtime không? |

Tên exception và cách hiển thị phụ thuộc Spring/GraalVM version. Dùng bảng này để khoanh vùng, sau đó xác nhận bằng task log và root cause.

## 12. Bài thực hành: phân loại ba lỗi trong cùng một ứng dụng

Tạo một ứng dụng Spring Boot có prefix billing, một PaymentService, một PaymentGateway và cấu hình audit tùy chọn.

**Tình huống A — lỗi phân tích bean**

Xóa bean cung cấp PaymentGateway, sau đó chạy:

~~~bash
./mvnw -Pnative spring-boot:process-aot
~~~

Quan sát NoSuchBeanDefinitionException hoặc lỗi dependency tương ứng. Khôi phục bean và chạy lại. Ghi nhận Native Image compiler chưa phải thành phần cần điều tra ở lần thất bại này.

**Tình huống B — condition bị chốt sai ở build time**

Thêm cấu hình:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "billing.audit",
        name = "enabled",
        havingValue = "true"
)
class AuditConfiguration {

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
~~~

Chạy AOT với billing.audit.enabled=false, sau đó chạy AOT-processed JAR với giá trị runtime là true. Quan sát sự khác nhau giữa bean graph đã sinh và kỳ vọng runtime. Sửa cấu hình môi trường AOT để bean cần thiết được đưa vào mô hình.

**Tình huống C — lỗi native-specific**

Tạo một nhánh code dùng reflection để tìm một class theo tên chỉ có ở runtime, sau đó kiểm thử trên native. Nếu native build hoặc runtime báo thiếu metadata, xác định chính xác lỗi xuất hiện ở compiler analysis hay khi executable gọi reflection. Thêm hints đúng loại, build lại và chạy cùng kịch bản.

### Thực hiện và ghi kết quả

1. Chạy compile và processAot riêng biệt.
2. Chạy JAR bằng -Dspring.aot.enabled=true.
3. Chạy native compilation.
4. Ghi task đầu tiên thất bại, exception gốc, class/method liên quan và pha build.
5. Sửa từng tình huống riêng rồi chạy lại đúng bước đã thất bại.
6. Cuối cùng chạy native integration test cho luồng thanh toán và audit.

### Câu hỏi tự kiểm tra

1. Vì sao NoSuchBeanDefinitionException trong processAot không phải lỗi GraalVM compiler?
2. Spring AOT đánh giá @ConditionalOnProperty vào thời điểm nào?
3. Vì sao environment dùng cho AOT processing có thể làm thay đổi bean graph?
4. Generated source compile error khác Native Image analysis error như thế nào?
5. Vì sao native compilation thành công chưa chứng minh mọi dynamic access đã có metadata?
6. AOT-processed JVM với spring.aot.enabled=true giúp cô lập lỗi nào?
7. Khi nào cần kiểm tra processTestAot thay vì processAot?
8. --diagnostics-mode hữu ích ở giai đoạn nào?
9. Một lỗi linker có liên quan trực tiếp đến Spring BeanFactory không?
10. Vì sao cần kiểm thử cuối cùng trên native executable?

**Tiêu chí đạt:** phân loại được lỗi Java compile, Spring AOT bean analysis, AOT contribution/generated source, Native Image compilation và native runtime; biết cô lập bằng processAot, AOT-processed JVM và nativeCompile; hiểu điều kiện bean được đánh giá ở build time; đọc được root cause và diagnostics; đồng thời chọn đúng hướng xử lý mà không nhầm lỗi cấu hình BeanFactory với lỗi GraalVM compiler.

## Tài liệu chính thức

- Spring Boot — Ahead-of-Time Processing with the JVM: https://docs.spring.io/spring-boot/reference/packaging/aot.html
- Spring Boot — Testing GraalVM Native Images: https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html
- Spring Boot Maven Plugin — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/maven-plugin/aot.html
- Spring Boot Gradle Plugin — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/gradle-plugin/aot.html
- GraalVM — Native Image Build Output: https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOutput/
- GraalVM — Troubleshoot Native Image Run-Time Errors: https://www.graalvm.org/latest/reference-manual/native-image/guides/troubleshoot-run-time-errors/
- GraalVM — Native Image Build Options: https://www.graalvm.org/latest/reference-manual/native-image/overview/BuildOptions/
