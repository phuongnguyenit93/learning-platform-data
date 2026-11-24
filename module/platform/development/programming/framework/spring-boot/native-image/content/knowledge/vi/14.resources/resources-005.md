# ServiceLoader, provider và tài nguyên META-INF/services

## 1. Java SPI giải quyết vấn đề gì?

Một ứng dụng có thể cần chọn implementation theo cấu hình hoặc theo thư viện được cài đặt: driver, bộ chuyển đổi thanh toán, bộ mã hóa, chiến lược định dạng, bộ phân tích tệp hay plugin mở rộng. Nếu lớp gọi phụ thuộc trực tiếp vào từng implementation, việc thêm provider thường kéo theo sửa code và biên dịch lại phần sử dụng.

Java cung cấp **Service Provider Interface (SPI)** thông qua `java.util.ServiceLoader`. Ứng dụng định nghĩa một interface hoặc abstract service type; các thư viện cung cấp những lớp triển khai interface đó. ServiceLoader tìm provider đã đăng ký và cho phép ứng dụng duyệt chúng mà không cần biết trước từng implementation cụ thể.

Trong ứng dụng Spring Boot được biên dịch bằng **Spring AOT và GraalVM Native Image**, SPI cần được kiểm tra ở build time và runtime. Provider phải hiện diện trong dependency/classpath hoặc module path khi tạo native executable. GraalVM có hỗ trợ nhận diện cấu hình ServiceLoader, nhưng cách nạp provider tùy biến, đọc descriptor trực tiếp hoặc tạo class động có thể cần cấu hình bổ sung.

Bài này thuộc chương **Tài nguyên** của module **SPRING_BOOT_NATIVE_IMAGE**, tập trung vào:

- Quan hệ giữa service interface, provider implementation và descriptor.
- Cấu trúc, tên file và nội dung của `META-INF/services`.
- Cách ServiceLoader tìm và khởi tạo provider.
- ClassLoader, Java Module System và đóng gói dependency.
- Khả năng tương thích với GraalVM Native Image, Runtime Hints và kiểm thử.

## 2. Ba thành phần của Java SPI

Một SPI đơn giản có ba phần:

1. **Service interface:** hợp đồng mà ứng dụng sử dụng.
2. **Provider:** lớp cụ thể hiện thực service interface.
3. **Provider configuration:** thông tin đăng ký provider để ServiceLoader có thể tìm thấy.

Ví dụ ứng dụng cần nhiều cách tính phí giao dịch. Service interface:

```java
package com.example.payment.spi;

import java.math.BigDecimal;

public interface PaymentFeeProvider {
    String code();

    BigDecimal calculateFee(BigDecimal amount);
}
```

Provider thứ nhất:

```java
package com.example.payment.provider;

import com.example.payment.spi.PaymentFeeProvider;
import java.math.BigDecimal;

public final class StandardFeeProvider implements PaymentFeeProvider {

    public StandardFeeProvider() {
    }

    @Override
    public String code() {
        return "standard";
    }

    @Override
    public BigDecimal calculateFee(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.015"));
    }
}
```

Provider thứ hai:

```java
package com.example.payment.provider;

import com.example.payment.spi.PaymentFeeProvider;
import java.math.BigDecimal;

public final class PremiumFeeProvider implements PaymentFeeProvider {

    public PremiumFeeProvider() {
    }

    @Override
    public String code() {
        return "premium";
    }

    @Override
    public BigDecimal calculateFee(BigDecimal amount) {
        return amount.multiply(new BigDecimal("0.008"));
    }
}
```

Ứng dụng gọi service interface:

```java
PaymentFeeProvider provider = ...;
BigDecimal fee = provider.calculateFee(new BigDecimal("100000"));
```

Code nghiệp vụ chỉ cần biết `PaymentFeeProvider`. Cách tìm provider sẽ do ServiceLoader thực hiện.

## 3. Cấu trúc file META-INF/services

Với ứng dụng chạy trên classpath, provider được đăng ký bằng một tệp văn bản có đường dẫn:

```text
META-INF/services/<fully-qualified-service-interface>
```

Trong ví dụ trên, service interface là `com.example.payment.spi.PaymentFeeProvider`, nên tên file phải chính xác là:

```text
META-INF/services/com.example.payment.spi.PaymentFeeProvider
```

Cấu trúc trong project Maven hoặc Gradle:

```text
src/main/
  java/
    com/example/payment/spi/PaymentFeeProvider.java
    com/example/payment/provider/StandardFeeProvider.java
    com/example/payment/provider/PremiumFeeProvider.java
  resources/
    META-INF/
      services/
        com.example.payment.spi.PaymentFeeProvider
```

Nội dung descriptor:

```text
com.example.payment.provider.StandardFeeProvider
com.example.payment.provider.PremiumFeeProvider
```

Mỗi dòng chứa **tên lớp provider đầy đủ (fully qualified class name)**, không có phần mở rộng `.class`. Có thể có khoảng trắng quanh tên và dòng chú thích bắt đầu bằng `#`. Không ghi tên interface vào nội dung file; tên interface được dùng để đặt tên descriptor.

Ví dụ có chú thích:

```text
# Các provider hỗ trợ tính phí giao dịch
com.example.payment.provider.StandardFeeProvider
com.example.payment.provider.PremiumFeeProvider
```

Các lỗi về tên thường gặp:

- Đặt file thành `PaymentFeeProvider` mà thiếu package trong tên.
- Dùng `META-INF/service/` thay vì `META-INF/services/`.
- Ghi tên file có đuôi `.txt` hoặc `.properties`.
- Ghi `StandardFeeProvider.class` thay vì tên lớp.
- Dùng tên package sai hoặc khác chữ hoa/chữ thường.
- Đặt descriptor trong source Java thay vì thư mục resources để đóng gói.

### 3.1. Quy tắc provider trên classpath

Với dạng provider configuration file truyền thống, mỗi provider class cần triển khai service interface và đáp ứng yêu cầu khởi tạo của ServiceLoader: lớp provider phải có constructor không tham số truy cập được (thường là public), và lớp phải truy cập được từ classloader đang dùng. Nếu provider không đáp ứng quy tắc này, ServiceLoader có thể ném `ServiceConfigurationError` khi duyệt hoặc khởi tạo provider.

Provider constructor nên nhẹ, tránh mở kết nối mạng, tạo thread hoặc thực hiện side effect khó kiểm soát. ServiceLoader có thể khởi tạo provider khi iterator/stream được tiêu thụ; không nên giả định chỉ gọi `ServiceLoader.load` là mọi provider đã được tạo.

## 4. Tìm và sử dụng provider bằng ServiceLoader

Cách dùng cơ bản:

```java
import com.example.payment.spi.PaymentFeeProvider;
import java.util.ServiceLoader;

public class PaymentFeeService {

    public PaymentFeeProvider findProvider(String code) {
        return ServiceLoader
            .load(PaymentFeeProvider.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .filter(provider -> provider.code().equals(code))
            .findFirst()
            .orElseThrow(() ->
                new IllegalArgumentException("Unknown fee provider: " + code)
            );
    }
}
```

Hoặc duyệt trực tiếp bằng iterator:

```java
ServiceLoader<PaymentFeeProvider> loader =
    ServiceLoader.load(PaymentFeeProvider.class);

for (PaymentFeeProvider provider : loader) {
    System.out.println(provider.code());
}
```

`ServiceLoader.load(PaymentFeeProvider.class)` sử dụng thread context class loader (TCCL) của thread hiện tại theo quy tắc API. Nếu ứng dụng chạy trong môi trường có nhiều classloader hoặc plugin framework, cần xác định classloader phù hợp. Có overload cho phép truyền classloader tường minh:

```java
ClassLoader providerClassLoader =
    Thread.currentThread().getContextClassLoader();

ServiceLoader<PaymentFeeProvider> loader =
    ServiceLoader.load(PaymentFeeProvider.class, providerClassLoader);
```

Không truyền classloader tùy tiện. Classloader phải nhìn thấy cả service interface lẫn provider classes và descriptor tương ứng. Nếu descriptor tồn tại nhưng provider class nằm trong một classloader khác, việc tìm kiếm hoặc khởi tạo vẫn có thể thất bại.

### 4.1. Lazy loading và stream API

ServiceLoader hỗ trợ duyệt provider theo cách lazy. Với `stream()`, ta có thể xem loại provider trước khi khởi tạo instance:

```java
ServiceLoader<PaymentFeeProvider> loader =
    ServiceLoader.load(PaymentFeeProvider.class);

loader.stream()
    .map(ServiceLoader.Provider::type)
    .forEach(providerType ->
        System.out.println(providerType.getName())
    );
```

Gọi `Provider.get()` mới yêu cầu instance của provider tương ứng. Điều này hữu ích nếu ứng dụng muốn lọc provider theo annotation hoặc metadata trước khi khởi tạo, nhưng việc truy cập type và metadata vẫn phải tương thích với cách GraalVM phân tích ứng dụng.

### 4.2. Xử lý không có provider và lỗi cấu hình

Nếu không có provider phù hợp, iterator có thể không có phần tử; `findFirst().orElseThrow` giúp đưa ra lỗi nghiệp vụ rõ ràng. Nếu descriptor sai hoặc provider không thể khởi tạo, ServiceLoader có thể ném `ServiceConfigurationError`. Không nên bắt mọi exception rồi trả về provider mặc định một cách im lặng, vì điều đó có thể khiến cấu hình production sai mà không được phát hiện.

Có thể kiểm tra rõ danh sách provider lúc khởi động:

```java
List<String> providerNames = ServiceLoader
    .load(PaymentFeeProvider.class)
    .stream()
    .map(provider -> provider.type().getName())
    .toList();

if (providerNames.isEmpty()) {
    throw new IllegalStateException("No PaymentFeeProvider found");
}
```

Với ứng dụng Spring Boot, có thể đưa bước kiểm tra này vào startup validation hoặc integration test thay vì để lỗi chỉ xuất hiện ở request hiếm gặp.

## 5. META-INF/services trong dependency và quá trình đóng gói

Provider descriptor có thể nằm trong JAR của thư viện, không chỉ trong project ứng dụng. Ví dụ:

```text
payment-spi.jar
  com/example/payment/spi/PaymentFeeProvider.class

payment-provider-standard.jar
  com/example/payment/provider/StandardFeeProvider.class
  META-INF/services/com.example.payment.spi.PaymentFeeProvider

payment-provider-premium.jar
  com/example/payment/provider/PremiumFeeProvider.class
  META-INF/services/com.example.payment.spi.PaymentFeeProvider
```

Nếu cả hai provider JAR nằm trên classpath, ServiceLoader có thể tìm thấy các descriptor của chúng theo cơ chế classloader. Tuy nhiên, **đóng gói thành uber/fat JAR** có thể làm các file cùng đường dẫn bị ghi đè nếu công cụ đóng gói không hợp nhất nội dung service descriptor.

### 5.1. Maven Shade Plugin

Khi dùng Maven Shade Plugin để tạo một uber JAR, cần cấu hình transformer hợp nhất service files thay vì để một descriptor ghi đè descriptor khác:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-shade-plugin</artifactId>
    <version>3.6.0</version>
    <executions>
        <execution>
            <phase>package</phase>
            <goals>
                <goal>shade</goal>
            </goals>
            <configuration>
                <transformers>
                    <transformer implementation=
                        "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
                </transformers>
            </configuration>
        </execution>
    </executions>
</plugin>
```

Cấu hình này dành cho trường hợp thật sự tạo shaded/uber JAR. Spring Boot executable JAR dùng cơ chế nested JAR riêng; không tự thêm Shade Plugin vào mọi dự án Spring Boot. Nếu dùng nhiều công cụ đóng gói, kiểm tra nội dung cuối cùng thay vì giả định mọi công cụ đều hợp nhất service descriptor giống nhau.

### 5.2. Gradle Shadow Plugin

Nếu dự án Gradle sử dụng Shadow Plugin để tạo uber JAR, có thể yêu cầu hợp nhất service files:

```groovy
tasks.shadowJar {
    mergeServiceFiles()
}
```

Đây là cấu hình của Shadow Plugin, không phải cấu hình mặc định của Gradle Java plugin hay Spring Boot plugin. Với Spring Boot executable JAR, kiểm tra nested dependency JAR và nội dung descriptor theo cách đóng gói của Spring Boot trước khi thêm một plugin khác.

### 5.3. Kiểm tra descriptor trong JAR

Dùng công cụ JDK:

```bash
jar tf target/payment-app.jar
```

Tìm đường dẫn `META-INF/services/com.example.payment.spi.PaymentFeeProvider`. Với Spring Boot executable JAR, descriptor có thể nằm trong `BOOT-INF/classes/META-INF/services/` hoặc bên trong một dependency JAR ở `BOOT-INF/lib/`. Dùng `jar tf` trên từng dependency khi cần kiểm tra provider do thư viện đóng góp.

Nếu cần xem nội dung một file bên trong JAR:

```bash
unzip -p target/payment-app.jar \
  BOOT-INF/classes/META-INF/services/com.example.payment.spi.PaymentFeeProvider
```

Đường dẫn ví dụ trên chỉ đúng khi descriptor nằm trong phần classes của ứng dụng. Nếu descriptor nằm trong dependency nested JAR, trích xuất dependency đó rồi kiểm tra riêng. Không dùng một đường dẫn giả định để kết luận provider đã mất.

## 6. Java Module System: uses và provides

Ngoài classpath descriptor, Java Platform Module System (JPMS) có cơ chế khai báo service trong `module-info.java`. Trong module sử dụng service, khai báo `uses`; trong module cung cấp implementation, khai báo `provides ... with ...`.

Module ứng dụng tiêu thụ service:

```java
module com.example.payment.app {
    requires com.example.payment.spi;
    uses com.example.payment.spi.PaymentFeeProvider;
}
```

Module cung cấp provider:

```java
module com.example.payment.provider.standard {
    requires com.example.payment.spi;

    provides com.example.payment.spi.PaymentFeeProvider
        with com.example.payment.provider.StandardFeeProvider;
}
```

Khi chạy trên module path, ServiceLoader sử dụng thông tin service trong module descriptor. Với provider trong named module, provider class có thể cung cấp public static method tên `provider` trả về service type, theo quy tắc của ServiceLoader; khi dùng dạng provider method, không nhất thiết phải có public no-argument constructor như provider class truyền thống trên classpath.

Phân biệt:

| Cách triển khai | Nơi khai báo provider | Môi trường |
| --- | --- | --- |
| Classpath SPI | `META-INF/services/<service-FQCN>` | Classpath, JAR thông thường |
| Modular SPI | `module-info.java` với `provides` | Module path, named module |
| Module tiêu thụ | `module-info.java` với `uses` | Named module cần service |

Không khai báo đồng thời cả hai cách một cách tùy tiện. Xác định ứng dụng đang chạy trên classpath hay module path, rồi kiểm tra cấu trúc artifact và cách khởi chạy tương ứng.

## 7. ServiceLoader và Spring dependency injection

SPI và Spring DI đều có thể cung cấp nhiều implementation, nhưng mục đích và vòng đời khác nhau.

| Tiêu chí | Java ServiceLoader | Spring dependency injection |
| --- | --- | --- |
| Cách đăng ký | Descriptor hoặc module `provides` | Bean definition, component scan, `@Bean` |
| Cách tìm | ClassLoader/module layer | ApplicationContext |
| Vòng đời | ServiceLoader quản lý discovery/cache của provider instance | Spring quản lý scope, lifecycle và post-processors |
| AOP/transaction | Không tự tạo Spring proxy | Bean có thể được áp dụng proxy/advice |
| Thư viện độc lập Spring | Phù hợp | Cần phụ thuộc Spring |
| Mở rộng bằng dependency | Có thể thêm provider JAR trên classpath lúc build | Thêm bean/configuration vào context |

Nếu tất cả implementation là Spring bean và ứng dụng muốn dùng transaction, security advice, configuration binding hoặc lifecycle của Spring, thường nên inject collection bean:

```java
@Service
class PaymentFeeRegistry {

    private final Map<String, PaymentFeeProvider> providers;

    PaymentFeeRegistry(List<PaymentFeeProvider> providerList) {
        this.providers = providerList.stream()
            .collect(Collectors.toUnmodifiableMap(
                PaymentFeeProvider::code,
                Function.identity()
            ));
    }

    PaymentFeeProvider get(String code) {
        PaymentFeeProvider provider = providers.get(code);
        if (provider == null) {
            throw new IllegalArgumentException("Unknown provider: " + code);
        }
        return provider;
    }
}
```

Nếu muốn giữ SPI để thư viện không phụ thuộc Spring, có thể tạo adapter Spring đọc ServiceLoader rồi đăng ký kết quả theo thiết kế rõ ràng. Không trộn hai cơ chế mà không xác định provider nào được quản lý bởi container. Một provider tạo bởi ServiceLoader không tự động trở thành Spring bean và không mặc nhiên nhận dependency injection, AOP hay lifecycle callbacks.

## 8. GraalVM Native Image nhận diện ServiceLoader như thế nào?

Native Image thực hiện reachability analysis ở build time. Một số hành vi động của Java có thể không được suy ra chỉ từ call graph tĩnh. ServiceLoader là trường hợp GraalVM có hỗ trợ chuyên biệt: Native Image có thể phân tích provider configuration files trên classpath và service declarations của module để nhận diện service providers trong quá trình build.

Điều đó có nghĩa **ứng dụng dùng ServiceLoader chuẩn không mặc nhiên phải tự đăng ký reflection hint cho mọi provider**. Trước tiên hãy dùng đúng ServiceLoader API, đặt descriptor đúng chỗ, bảo đảm provider classes và dependency có mặt trong build classpath/module path, rồi kiểm thử native executable.

Tuy nhiên, cần phân biệt các tình huống:

- **ServiceLoader chuẩn:** descriptor và provider hiện diện trong classpath/module path khi native image được build. GraalVM có cơ chế nhận diện riêng; xác minh bằng build và runtime test.
- **Đọc descriptor như một resource thông thường:** nếu code tự gọi `getResourceAsStream("META-INF/services/...")` để đọc nội dung, đây là đường truy cập resource riêng. Khi metadata không tự nhận diện, có thể cần ResourceHints cho đúng descriptor.
- **Tự tạo provider qua reflection:** nếu code dùng `Class.forName`, `getDeclaredConstructor().newInstance()` hoặc cơ chế reflection riêng, khai báo reflection hints tương ứng khi phân tích không nhận ra.
- **Plugin được cài sau khi native executable đã build:** provider class và descriptor mới không tự xuất hiện trong binary đã tạo. Cần có provider lúc build hoặc chọn một kiến trúc mở rộng khác phù hợp native.
- **Custom ClassLoader/ModuleLayer:** cơ chế discovery khác với classpath mặc định; phải kiểm tra khả năng hỗ trợ của phiên bản GraalVM và cách đóng gói.

Không đăng ký toàn bộ `META-INF/**` hoặc reflection cho toàn bộ package chỉ để làm build qua. Hãy xác định đúng đường discovery và thêm metadata tối thiểu khi có bằng chứng thiếu.

### 8.1. Khi cần đăng ký resource hint cho descriptor

Nếu ứng dụng thực sự đọc descriptor như file resource, có thể khai báo một pattern chính xác qua RuntimeHints:

```java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

final class PaymentSpiResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints, ClassLoader classLoader) {

        hints.resources().registerPattern(
            "META-INF/services/com.example.payment.spi.PaymentFeeProvider"
        );
    }
}
```

Liên kết registrar với Spring AOT:

```java
@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(PaymentSpiResourceHints.class)
class NativeSpiConfiguration {
}
```

Đây là ví dụ cho trường hợp resource descriptor cần được truy cập như resource thông thường hoặc metadata tự động không bao phủ cách đọc cụ thể của ứng dụng. Nếu chỉ dùng ServiceLoader chuẩn và GraalVM đã tự nhận diện provider, không cần thêm hint này một cách máy móc.

### 8.2. Khi cần reflection hint cho provider

Nếu ứng dụng tự tạo provider bằng reflection thay vì gọi ServiceLoader, có thể cần khai báo constructor/method phù hợp:

```java
hints.reflection().registerType(
    StandardFeeProvider.class,
    MemberCategory.INVOKE_PUBLIC_CONSTRUCTORS
);
```

Không suy ra rằng mọi provider đều cần khai báo như vậy. ServiceLoader support của GraalVM và metadata của thư viện có thể đã xử lý việc discovery/instantiation. Reflection hint chỉ giải quyết truy cập reflection được mô tả; nó không sửa descriptor sai, thiếu dependency hoặc custom classloader không tương thích.

## 9. Kiểm thử SPI trên JVM và Native Image

### 9.1. Unit test kiểm tra provider discovery

Một test đơn giản xác nhận các provider mong đợi được phát hiện:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ServiceLoader;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class PaymentFeeProviderTests {

    @Test
    void discoversExpectedProviders() {
        Set<String> providerCodes = ServiceLoader
            .load(PaymentFeeProvider.class)
            .stream()
            .map(ServiceLoader.Provider::get)
            .map(PaymentFeeProvider::code)
            .collect(Collectors.toSet());

        assertTrue(providerCodes.contains("standard"));
        assertTrue(providerCodes.contains("premium"));
    }
}
```

Test này phải chạy với đúng provider JAR/dependency trên test runtime classpath. Nếu test chỉ chạy trong module SPI mà không có provider dependency, kết quả rỗng là đúng với classpath đó; hãy cấu hình test module phù hợp.

### 9.2. Kiểm tra descriptor và provider constructor

Ngoài unit test, xác minh:

1. Tên descriptor trùng fully qualified name của service interface.
2. Nội dung descriptor trỏ tới provider class đúng package.
3. Provider class có constructor và visibility phù hợp với kiểu đăng ký.
4. Provider class nằm trong dependency/classpath khi build native.
5. Nếu dùng uber JAR, các descriptor từ dependency được hợp nhất.
6. Nếu dùng JPMS, module consumer có `uses` và module provider có `provides`.

Có thể tạo test kiểm tra provider count hoặc danh sách provider class names để phát hiện descriptor bị ghi đè, thiếu dependency hoặc trùng khai báo.

### 9.3. Build và chạy native executable

Với Maven đã cấu hình Spring AOT và Native Build Tools:

```bash
./mvnw -Pnative native:compile
./target/payment-app
```

Với Gradle:

```bash
./gradlew nativeCompile
./build/native/nativeCompile/payment-app
```

Đường dẫn executable tùy artifact name và cấu hình plugin. Gọi endpoint/job thật sự sử dụng service provider, rồi xác nhận kết quả giống JVM. Nếu provider được khởi tạo lười, test phải kích hoạt nhánh đó; chỉ khởi động context thành công chưa chứng minh discovery hoạt động.

### 9.4. Bộ test tương thích cần có

| Kiểm tra | Điều cần chứng minh |
| --- | --- |
| JVM discovery | ServiceLoader tìm thấy các provider dự kiến |
| Descriptor | File nằm đúng path, tên interface và provider class hợp lệ |
| Dependency packaging | Provider JAR và descriptor không bị loại hoặc ghi đè |
| ClassLoader | ServiceLoader dùng classloader nhìn thấy interface và provider |
| Provider construction | Constructor/provider method hoạt động, không ném ServiceConfigurationError |
| Native discovery | Native executable phát hiện cùng provider set như JVM |
| Business behavior | Provider thực hiện đúng nghiệp vụ và xử lý lỗi |
| Container target | Binary và dependency tương thích OS/CPU/runtime image |

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Không tìm thấy provider | Descriptor thiếu/sai tên hoặc provider dependency không có trên classpath | Kiểm tra `META-INF/services/<service-FQCN>` và dependency |
| `ServiceConfigurationError` | Provider class không tồn tại, không assignable hoặc không khởi tạo được | Kiểm tra tên lớp, interface, constructor và lỗi khởi tạo |
| JVM tìm thấy nhưng native không tìm thấy | Provider không hiện diện lúc build, metadata/build tool không nhận diện đường discovery | Xác minh classpath/build log; kiểm tra Native Image support và thêm metadata đúng trường hợp |
| Chỉ một provider xuất hiện sau khi đóng gói | Service descriptors bị ghi đè trong uber JAR | Dùng transformer/merge service files, kiểm tra artifact cuối |
| Provider có trong descriptor nhưng không load được | ClassLoader không nhìn thấy class hoặc provider constructor không phù hợp | Chỉ định classloader phù hợp, kiểm tra module/classpath |
| Resource descriptor đọc trực tiếp trả null | Descriptor không được đóng gói hoặc thiếu resource metadata | Kiểm tra JAR và thêm resource hint chính xác khi cần |
| `ClassNotFoundException` trong custom discovery | Tên provider được chọn từ cấu hình runtime hoặc classloader riêng | Kiểm tra tên class, dependency và khả năng dynamic loading trong native |
| Provider khởi tạo nhiều lần | Tạo ServiceLoader mới hoặc gọi provider factory ở nhiều nơi | Xác định scope/lifecycle mong muốn; quản lý registry rõ ràng |
| Thay provider JAR sau khi build nhưng native không đổi | Provider set đã được xác định khi tạo executable | Build lại native image hoặc thiết kế extension qua giao thức ngoài tiến trình |
| JPMS không tìm thấy provider | Thiếu `uses`/`provides`, module path không đúng | Kiểm tra module descriptors và cách khởi chạy module |

Không chữa lỗi discovery bằng cách đăng ký tất cả class trong package hoặc mở toàn bộ `META-INF`. Đầu tiên xác định lỗi nằm ở descriptor, dependency, classloader, constructor, module declaration hay native metadata.

## 11. Bài thực hành: đăng ký và chạy hai provider

**Bối cảnh:** Ứng dụng Spring Boot tính phí thanh toán thông qua `PaymentFeeProvider`. Có hai provider: `StandardFeeProvider` và `PremiumFeeProvider`.

**Các bước:**

1. Tạo service interface `PaymentFeeProvider`.
2. Tạo hai provider implementation với constructor không tham số phù hợp cho classpath SPI.
3. Tạo file `META-INF/services/com.example.payment.spi.PaymentFeeProvider`.
4. Đặt tên đầy đủ của hai provider, mỗi tên trên một dòng.
5. Viết service dùng `ServiceLoader.load(PaymentFeeProvider.class)` để tìm provider theo code.
6. Chạy unit test trên JVM và xác nhận cả hai provider được phát hiện.
7. Kiểm tra descriptor trong JAR và dependency JAR; nếu dùng shaded JAR, xác minh service descriptors đã được merge.
8. Build GraalVM Native Image và chạy endpoint thực tế để xác nhận provider discovery.
9. Nếu code đọc descriptor trực tiếp hoặc dùng reflection/custom classloader, xác định metadata cần bổ sung; không thêm hints dư thừa.
10. So sánh provider set và kết quả nghiệp vụ giữa JVM và native executable.

**Tiêu chí đạt:**

- Service interface không phụ thuộc vào implementation cụ thể.
- Descriptor có tên file và nội dung đúng quy tắc.
- Cả hai provider được phát hiện trên JVM.
- Dependency/descriptor không bị mất khi đóng gói.
- Native executable tìm được provider và trả kết quả nghiệp vụ đúng.
- Hiểu khi nào GraalVM tự hỗ trợ ServiceLoader và khi nào cần ResourceHints/reflection hints.
- Biết giới hạn của plugin động được thêm sau khi native image đã build.

## 12. Tổng kết

Java `ServiceLoader` triển khai SPI bằng cách tách **service interface**, **provider implementation** và **provider configuration**. Trên classpath, provider được khai báo trong file `META-INF/services/<fully-qualified-service-interface>`, mỗi dòng là tên đầy đủ của một provider. Trên Java Module System, consumer dùng `uses` và provider module khai báo `provides ... with ...`.

GraalVM Native Image có hỗ trợ chuyên biệt cho ServiceLoader và có thể nhận diện provider declarations trong quá trình phân tích build time. Vì vậy, hãy bắt đầu bằng descriptor, dependency và classloader đúng; chỉ bổ sung `ResourceHints` khi ứng dụng đọc descriptor như resource hoặc đường tự động không bao phủ trường hợp cụ thể, và chỉ thêm reflection hints khi code thật sự dùng reflection cần metadata. Kiểm thử trên **native executable thực tế** để chứng minh provider set và hành vi nghiệp vụ tương đương bản JVM.

