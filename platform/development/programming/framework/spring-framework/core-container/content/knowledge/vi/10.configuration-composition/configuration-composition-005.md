# Chọn cấu hình bằng `ImportSelector` trong Spring Framework Core Container

## 1. Bài toán: cùng một ứng dụng nhưng không phải lúc nào cũng dùng cùng một cấu hình

Một ứng dụng có thể dùng bộ lưu trữ in-memory khi chạy thử, kết nối thực khi chạy production, hoặc bật một nhóm bean riêng theo thuộc tính cấu hình. Nếu luôn `@Import` tất cả các configuration classes, Spring có thể phải đăng ký nhiều bean cùng interface, gây mơ hồ khi inject, hoặc khởi tạo thành phần không cần thiết.

Giả sử hai configuration classes:

```java
@Configuration(proxyBeanMethods = false)
class LocalShippingConfig {
    @Bean
    ShippingClient shippingClient() {
        return new LocalShippingClient();
    }
}

@Configuration(proxyBeanMethods = false)
class RemoteShippingConfig {
    @Bean
    ShippingClient shippingClient() {
        return new RemoteShippingClient();
    }
}
```

Đây là **đoạn minh họa**: các kiểu `ShippingClient`, `LocalShippingClient` và `RemoteShippingClient` cần được khai báo trong ứng dụng. Cả hai factory methods đều tạo bean kiểu `ShippingClient`, nhưng ứng dụng muốn **chọn một cấu hình phù hợp** thay vì nhập cả hai.

`org.springframework.context.annotation.ImportSelector` chính là một extension point dùng cho việc này. Một selector phân tích metadata của class khai báo `@Import`, chọn danh sách class cần nhập và trả về tên class đầy đủ. Spring tiếp tục xử lý những class được chọn như import candidates.

Cách sử dụng trực tiếp:

```java
@Configuration
@Import(ShippingConfigSelector.class)
class AppConfig {
}
```

Trong ví dụ này, `ShippingConfigSelector` là một class **implement `ImportSelector`** và có nhiệm vụ chọn `LocalShippingConfig` hoặc `RemoteShippingConfig`. Spring không tự biết chọn cái nào chỉ vì hai class cùng tồn tại trên classpath.

Mục tiêu của bài học:

- Nắm chính xác contract của `ImportSelector` và `selectImports(AnnotationMetadata)`.
- Đọc metadata annotation, annotation attributes và `Environment` để quyết định import.
- Tạo custom `@Enable...` annotation phối hợp với `@Import(Selector.class)`.
- Phân biệt selector với `@Import` tĩnh, `@Conditional`, `@Profile`, `@ComponentScan`, `DeferredImportSelector` và `ImportBeanDefinitionRegistrar`.
- Hiểu thời điểm lựa chọn class so với thời điểm khởi tạo bean và cách tránh xung đột.
- Chạy một ví dụ hoàn chỉnh Java 17+ với Spring Framework 6.2, gồm cả trường hợp property override.
- Biết cách kiểm thử, debug, xử lý trường hợp thiếu cấu hình và những lỗi dễ gặp khi viết selector.

## 2. `ImportSelector` là gì và Spring gọi nó khi nào?

`ImportSelector` là interface thuộc package `org.springframework.context.annotation`. Chữ ký trung tâm:

```java
public interface ImportSelector {
    String[] selectImports(AnnotationMetadata importingClassMetadata);
}
```

Đây là chữ ký **rút gọn**, interface thực còn có extension method như `getExclusionFilter()`. `AnnotationMetadata` thuộc `org.springframework.core.type`. Một implementation hợp lệ phải trả mảng **tên class đầy đủ** (fully qualified class names) của các import candidates.

Ví dụ tối thiểu:

```java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class FixedShippingSelector implements ImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] { LocalShippingConfig.class.getName() };
    }
}
```

Đoạn này là **minh họa riêng** (cần class `LocalShippingConfig`). Nó tương đương về kết quả chọn class với `@Import(LocalShippingConfig.class)` nhưng tạo điểm mở rộng để logic phức tạp hơn được thêm sau này.

### 2.1. Chu trình xử lý

```text
@Configuration / custom @Enable... được đăng ký
                         |
                         v
               ConfigurationClassParser
                         |
                         v
          Phát hiện @Import(Selector.class)
                         |
                         v
            Tạo instance ImportSelector
                         |
                         v
         Cung cấp các Aware dependencies
          (ví dụ EnvironmentAware)
                         |
                         v
     selectImports(AnnotationMetadata)
                         |
                  String[] FQCN
                         |
                         v
           Spring xử lý các class được chọn
                         |
            +------------+-------------+
            |                          |
            v                          v
   @Configuration classes       Regular component classes
            |                          |
            +------------+-------------+
                         |
                         v
                 Bean definitions
                         |
                         v
                 BeanFactory tạo beans
              theo DI, scope và lifecycle
```

**Điểm phân biệt quan trọng:** selector chọn **class definitions tham gia cấu hình**, không trực tiếp trả object bean. Logic trong `selectImports` diễn ra ở giai đoạn phân tích configuration, thường trước khi các singleton nghiệp vụ được tạo.

Không gọi `new ShippingClient()` trong `selectImports` với kỳ vọng đó là bean được quản lý. Việc đăng ký bean definitions và tạo instances phải do Spring thực hiện qua các class được import hoặc một extension point thích hợp.

### 2.2. Kết quả trả về phải là class name

Đúng:

```java
return new String[] {
    LocalShippingConfig.class.getName(),
    MetricsConfig.class.getName()
};
```

Sai:

```java
return new String[] { "shippingClient", "localShippingConfig" };
```

Hai đoạn là **mã minh họa**; `MetricsConfig` cần tồn tại để đoạn đầu compile. Phần tử của mảng cần là tên class hợp lệ, ví dụ `com.example.config.LocalShippingConfig`, không phải Spring bean name hoặc đường dẫn resource XML. Đối với nested class, dùng `Class.getName()` đáng tin hơn việc tự ghép tên theo ký hiệu dấu chấm, vì tên nhị phân của nested class trong Java có ký tự `$`.

Nếu không cần import gì, trả về mảng rỗng:

```java
return new String[0];
```

Đừng trả `null` để diễn đạt “không có import”: contract của method là mảng. Mảng rỗng là cách biểu đạt rõ ràng và tránh lỗi xử lý bất ngờ.

### 2.3. ImportSelector có thể chọn loại class nào?

Các class selector trả về tiếp tục được Spring xử lý theo semantics của `@Import`:

- `@Configuration` class có các factory methods `@Bean`;
- regular component class có constructor thích hợp;
- các loại class được Spring import parser hỗ trợ trong các tình huống nâng cao.

Trong hầu hết mã ứng dụng, selector nên trả **configuration class names**, để lựa chọn một gói bean definitions có thể được kiểm thử và quản lý theo module. Một selector quá phức tạp, trả rất nhiều implementation classes mà không có contract rõ, thường khó bảo trì hơn các configuration entry points.

## 3. `AnnotationMetadata`: đọc dữ liệu mà không instantiate class cấu hình

Tham số `importingClassMetadata` cho biết metadata của **class đang khai báo hoặc mang gián tiếp `@Import`**, không phải object configuration bean đã khởi tạo.

Ví dụ:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Import(ShippingConfigSelector.class)
public @interface EnableShipping {
    String mode() default "local";
}
```

Và ứng dụng:

```java
@Configuration
@EnableShipping(mode = "remote")
class AppConfig {
}
```

Đây là các đoạn minh họa; cần imports từ `java.lang.annotation` và Spring, cũng như implementation của selector. Với `AnnotationMetadata` được truyền vào selector, Spring có thể truy xuất attribute `mode` mà không tạo instance của `AppConfig`.

### 3.1. Đọc attributes của custom annotation

```java
@Override
public String[] selectImports(AnnotationMetadata metadata) {
    Map<String, Object> attributes =
            metadata.getAnnotationAttributes(EnableShipping.class.getName());

    if (attributes == null) {
        throw new IllegalStateException("@EnableShipping is missing");
    }

    String mode = (String) attributes.get("mode");
    return switch (mode) {
        case "local" -> new String[] { LocalShippingConfig.class.getName() };
        case "remote" -> new String[] { RemoteShippingConfig.class.getName() };
        default -> throw new IllegalArgumentException("Unsupported mode: " + mode);
    };
}
```

Đây là **trích đoạn minh họa**, không độc lập. `Map` cần import `java.util.Map` và các class config phải tồn tại.

Hãy phân biệt:

- `metadata.getClassName()`: class name của **importing configuration class**.
- `metadata.hasAnnotation(...)` / `metadata.hasMetaAnnotation(...)`: kiểm tra annotation metadata theo API tương ứng.
- `metadata.getAnnotationAttributes(...)`: lấy các attributes của annotation được chỉ định.
- Tên class trả về từ `selectImports`: **imported configuration/component classes**, có thể hoàn toàn khác class name của metadata đầu vào.

Khi `@EnableShipping` là một composed annotation mang `@Import`, metadata đọc attributes của `@EnableShipping` trên class sử dụng annotation. Có thể dùng `AnnotationAttributes` khi muốn các accessor có kiểm tra kiểu hoặc xử lý metadata phức tạp; ví dụ runnable ở mục 8 dùng enum và cast rõ kiểu để tránh nhập nhằng.

### 3.2. Tham số class metadata không phải bean factory

Không thể mặc nhiên dùng `importingClassMetadata` như một `ApplicationContext` để lấy `@Bean` instances. Giai đoạn này vẫn đang chọn những classes tạo nên configuration graph. Nếu cần thông tin cấu hình, ưu tiên environment/properties và annotation metadata thay vì lookup các singleton nghiệp vụ chưa chắc tồn tại.

**Không dựa vào việc gọi constructor một configuration class** từ selector để “đọc annotation attributes”: constructor có thể có dependency injection, side effects hoặc lifecycle cần container. Metadata giúp tránh điều đó.

## 4. Nhận `Environment`, `BeanFactory` và những dependency hạ tầng khác

Theo Javadoc Spring Framework 6.2, `ImportSelector` có thể nhận một số hạ tầng của container **trước khi** `selectImports(...)` được gọi, chẳng hạn thông qua những Aware interfaces:

- `EnvironmentAware`;
- `BeanFactoryAware`;
- `BeanClassLoaderAware`;
- `ResourceLoaderAware`.

Spring cũng hỗ trợ constructor injection với một constructor duy nhất có những parameter types hạ tầng thích hợp, ví dụ `Environment`, `BeanFactory`, `ClassLoader` hoặc `ResourceLoader`, theo API được tài liệu hóa.

### 4.1. `EnvironmentAware` chọn theo property

```java
public final class ShippingConfigSelector
        implements ImportSelector, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        String mode = environment.getProperty(
                "shipping.provider", "local");

        return switch (mode) {
            case "local" ->
                    new String[] { LocalShippingConfig.class.getName() };
            case "remote" ->
                    new String[] { RemoteShippingConfig.class.getName() };
            default ->
                    throw new IllegalArgumentException("Invalid provider: " + mode);
        };
    }
}
```

Đây là **đoạn minh họa** (imports `EnvironmentAware` và `Environment` ở packages `org.springframework.context` / `org.springframework.core.env`). Property có thể đến từ system properties, environment variables hoặc `PropertySource` được đăng ký phù hợp trước quá trình parsing. Logic trên sẽ ném lỗi rõ nếu giá trị không hợp lệ, thay vì âm thầm dùng provider khác với yêu cầu.

**Nên tránh dùng `BeanFactory.getBean(...)` trong selector** chỉ để phân nhánh theo một bean nghiệp vụ. Configuration đang được xây dựng; eager lookup có thể gây circular dependency, thiếu bean definitions hoặc khởi tạo quá sớm. Nếu dữ kiện chỉ là `dev/prod`, feature flag cấu hình hoặc một annotation attribute, `Environment`/metadata thích hợp hơn.

### 4.2. Chọn nguồn nào làm ưu tiên?

Khi hỗ trợ cả annotation attribute và property môi trường, hãy định nghĩa chính sách rõ ràng. Ví dụ chính sách:

1. Attribute trong `@EnableShipping(channel=STANDARD)` cung cấp giá trị mặc định.
2. Property `lesson.shipping.channel` nếu là `standard` hoặc `express` sẽ **ghi đè** attribute.
3. Property `annotation` có nghĩa giữ nguyên giá trị annotation.
4. Giá trị khác được báo lỗi cấu hình, không lặng lẽ rơi sang STANDARD.

Chính sách này được minh họa bằng chương trình hoàn chỉnh ở mục 8. Một ứng dụng khác có thể quyết định annotation luôn thắng property; điều quan trọng là quy tắc phải được tài liệu hóa, kiểm thử và ổn định giữa môi trường.

## 5. Custom `@Enable...` annotation: tổ hợp cấu hình có khả năng tái sử dụng

Nhiều API của Spring tổ chức dưới dạng `@EnableXxx`: người dùng chỉ gắn annotation ở một configuration class, còn thư viện cài đặt một selector/registrar để thêm những bean definitions cần thiết.

Ví dụ:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(ShippingConfigSelector.class)
public @interface EnableShipping {
    Channel channel() default Channel.STANDARD;
}
```

Ở đây:

- `@Target(ElementType.TYPE)` cho phép gắn trên class;
- `@Retention(RetentionPolicy.RUNTIME)` giữ metadata annotation khi chương trình chạy;
- `@Documented` làm annotation xuất hiện trong tài liệu Javadoc của class sử dụng nó;
- `@Import(ShippingConfigSelector.class)` cung cấp điểm mở rộng xử lý import;
- `channel` là thuộc tính công khai để cấu hình application.

Caller chỉ cần:

```java
@Configuration(proxyBeanMethods = false)
@EnableShipping(channel = Channel.EXPRESS)
class CheckoutConfig {
}
```

Cách này cung cấp **API cấu hình ngắn gọn**: client module không cần nhớ tên của các class `ExpressShippingConfig` và `StandardShippingConfig` nội bộ.

### 5.1. Tránh lộ details của implementation ra annotation

Một annotation như `@EnableShipping(channel=EXPRESS)` mô tả quyết định nghiệp vụ/cấu hình rõ hơn việc yêu cầu caller tự nhập `@Import(ExpressShippingConfig.class)` từ package internal. Khi implementation đổi, thư viện có thể thay cách selector map enum → class mà không buộc application refactor nhiều imports.

Tuy nhiên, không nên bọc mọi cặp configuration classes bằng custom annotation. Nếu một ứng dụng chỉ nhập một cấu hình cố định ở một nơi, `@Import(MyConfig.class)` đơn giản và dễ hiểu hơn.

### 5.2. Tên enum và đổi phiên bản

Nếu annotation công khai định nghĩa enum `Channel.STANDARD`, `Channel.EXPRESS`, việc thêm/xóa/đổi các giá trị có thể ảnh hưởng source compatibility và chính sách runtime. Đừng tự động chọn fallback “gần đúng” khi nhận giá trị enum/property lạ; thay vào đó báo lỗi rõ và cung cấp migration path phù hợp.

## 6. `ImportSelector` khác các lựa chọn cấu hình phổ biến như thế nào?

| Cơ chế | Điều kiện chọn | Tạo ra điều gì? | Khi phù hợp |
| --- | --- | --- | --- |
| `@Import(AConfig.class)` | Cố định trong source | Nhập class cấu hình cụ thể | Tổ hợp cấu hình tĩnh, ít nhánh |
| `ImportSelector` | Code chọn theo annotation metadata, environment, v.v. | Tên classes để Spring tiếp tục import | Custom `@Enable...`, chọn module/config |
| `@Profile` | Active profiles | Bật/tắt config hoặc bean definition | Cấu hình khác nhau theo môi trường |
| `@Conditional` | `Condition.matches(...)` | Bật/tắt config/bean theo điều kiện | Quy tắc điều kiện cục bộ |
| `@ComponentScan` | Package roots và filters | Phát hiện các component candidates | Tập component thuộc vùng ứng dụng |
| `ImportBeanDefinitionRegistrar` | Logic ở registry level | Đăng ký bean definitions trực tiếp | Framework extension phức tạp |
| `DeferredImportSelector` | Chọn ở giai đoạn deferred processing | Classes nhập sau khi configs thường được xử lý | Auto-configuration/nhóm selectors nâng cao |

### 6.1. Khi nào chỉ cần `@Profile`?

Nếu một ứng dụng chỉ muốn bean A trong `dev` và bean B trong `prod`, hai `@Configuration` classes gắn `@Profile("dev")` và `@Profile("prod")` có thể đơn giản hơn viết selector. Tuy nhiên, hãy bảo đảm đúng một cấu hình được kích hoạt khi dependency là bắt buộc.

`ImportSelector` phù hợp hơn khi việc chọn không chỉ phụ thuộc một profile: ví dụ một annotation có nhiều attributes, cần chọn một trong nhiều implementation modules, hoặc library xây public `@Enable...` API.

### 6.2. Khi nào `@Conditional` đơn giản hơn?

`@Conditional(SomeCondition.class)` đánh giá một điều kiện để bỏ qua hoặc giữ một bean/configuration. Nó không cần trả tên class khác. Nếu nhiệm vụ là “đăng ký bean X khi điều kiện đúng”, conditional thường ngắn gọn hơn selector. Nếu nhiệm vụ là “theo lựa chọn, import **toàn bộ một configuration class** tương ứng”, selector có thể rõ ràng hơn.

### 6.3. `@Import` không tự quét package

`@Import(ShippingConfigSelector.class)` không khiến mọi class cùng package với selector thành bean. Spring chỉ xử lý những class được trả về và những registrations/imports phụ thuộc từ các class đó. Nếu một configuration được chọn có `@ComponentScan`, chính scan đó có thể đưa nhiều component vào registry; phạm vi thực tế vì vậy phụ thuộc cấu hình được chọn.

### 6.4. ImportSelector chọn class, không giải quyết tất cả bean candidates

Giả sử selector chọn `RemoteShippingConfig` nhưng application còn có một `@Bean ShippingClient localClient()` từ nguồn khác. Khi một service inject đơn `ShippingClient`, vẫn có thể có hai candidates và phát sinh `NoUniqueBeanDefinitionException` nếu không có lựa chọn rõ.

Selector giúp giảm import dư, **không thay thế** các cơ chế `@Qualifier`, `@Primary`, bean naming hay thiết kế dependency hợp lệ.

## 7. `DeferredImportSelector` và những extension points nâng cao

`DeferredImportSelector` kế thừa `ImportSelector` nhưng được xử lý ở giai đoạn **sau** khi các `@Configuration` classes thông thường đã được parser xem xét, thay vì ngay theo trình tự xử lý selector thường. Nó hữu ích khi các imported configurations cần được chọn sau khi đã có thông tin đầy đủ hơn về tập cấu hình.

Một ví dụ tối thiểu:

```java
public class LateShippingSelector implements DeferredImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] { StandardShippingConfig.class.getName() };
    }
}
```

Đây là **trích đoạn minh họa** (cần import `DeferredImportSelector` và `AnnotationMetadata` cùng class config). Để sử dụng, gắn `@Import(LateShippingSelector.class)` lên một configuration class. Deferred không có nghĩa “chờ tới khi ứng dụng đang chạy mới tự thêm bean” hoặc “tạo bean bất đồng bộ”; nó chỉ thay đổi **giai đoạn xử lý imports trong quá trình bootstrap**.

### 7.1. `DeferredImportSelector.Group`

Các deferred selectors có thể được gom nhóm để phối hợp thứ tự/chính sách xử lý thông qua interface `DeferredImportSelector.Group`. Một nhóm nhận selectors và metadata, rồi cung cấp các import entries. Đây là công cụ framework-level; không cần tự viết group chỉ để chọn STANDARD/EXPRESS ở một ứng dụng nhỏ.

**Đặc biệt:** thứ tự xử lý import selectors **khác** thứ tự khởi tạo singleton beans. Nếu bean B cần bean A, hãy khai báo dependency qua constructor/factory-method parameters; `@Order` trên selectors hoặc import order không thay thế dependency graph.

### 7.2. `getExclusionFilter()`

`ImportSelector` có default method `getExclusionFilter()` trả một predicate dùng để loại những class candidates khỏi tập import theo quy tắc Spring, có thể được áp dụng bắc cầu cho các classes tìm qua imports của selector. Đây là tính năng nâng cao để một selector loại class names trong import processing; nó **không phải** global component-scan exclude filter cho toàn ứng dụng.

Nếu chỉ cần chọn một trong hai configs, trả mảng chứa đúng một class name sẽ dễ kiểm chứng hơn dùng exclusion filter để nhập rất rộng rồi loại dần.

### 7.3. `ImportBeanDefinitionRegistrar` làm gì khác?

Một registrar thao tác trực tiếp với `BeanDefinitionRegistry` để đăng ký definitions, thường dùng trong library xây infrastructure bean động. Trong khi đó, selector chỉ trả class names để Spring tiếp tục xử lý theo `@Import`.

Nếu yêu cầu là “dựa vào `channel` để chọn một `@Configuration` chứa các `@Bean` methods”, selector là công cụ phù hợp. Nếu yêu cầu là “đăng ký số lượng bean definitions với types, bean names và metadata tùy biến cao theo annotation attributes”, registrar có thể phù hợp hơn nhưng khó triển khai/kiểm thử hơn.

## 8. Ví dụ Java 17+ hoàn chỉnh: chọn cấu hình shipping

Chương trình này chạy trên **Spring Framework 6.2.19**, không cần Spring Boot hoặc server. Nó thể hiện:

1. `@EnableShipping(channel=STANDARD)` chọn `StandardShippingConfig`.
2. `@EnableShipping(channel=EXPRESS)` chọn `ExpressShippingConfig`.
3. Property `lesson.shipping.channel=express` ưu tiên hơn attribute STANDARD, nên chọn EXPRESS.
4. Không dùng `@EnableShipping` thì không có bean `Carrier` nếu không đăng ký bằng cách khác.
5. Mỗi context có đúng **một** bean `Carrier`; `CheckoutService` lấy bean đó từ phương thức `@Bean` có tham số.

### 8.1. Cấu trúc

```text
spring-import-selector-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── ImportSelectorDemo.java
```

File `settings.gradle`:

```groovy
rootProject.name = 'spring-import-selector-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
}

application {
    mainClass = 'ImportSelectorDemo'
}
```

Dùng JDK 17+ và phiên bản Gradle tương thích. `spring-context` mang theo `spring-beans` và `spring-core` cần cho `ImportSelector`, metadata, `EnvironmentAware` và `AnnotationConfigApplicationContext`.

### 8.2. Mã Java đầy đủ

Tạo file `src/main/java/ImportSelectorDemo.java`:

```java
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Locale;
import java.util.Map;

import org.springframework.context.EnvironmentAware;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.env.Environment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.type.AnnotationMetadata;

public class ImportSelectorDemo {

    public enum Channel {
        STANDARD, EXPRESS
    }

    public interface Carrier {
        String code();
        int surcharge();
    }

    public record StandardCarrier() implements Carrier {
        @Override
        public String code() {
            return "standard";
        }

        @Override
        public int surcharge() {
            return 5;
        }
    }

    public record ExpressCarrier() implements Carrier {
        @Override
        public String code() {
            return "express";
        }

        @Override
        public int surcharge() {
            return 20;
        }
    }

    public record CheckoutService(Carrier carrier) {
        public int total(int subtotal) {
            return subtotal + carrier.surcharge();
        }
    }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @Import(ShippingSelector.class)
    public @interface EnableShipping {
        Channel channel() default Channel.STANDARD;
    }

    public static class ShippingSelector
            implements ImportSelector, EnvironmentAware {

        private Environment environment;

        @Override
        public void setEnvironment(Environment environment) {
            this.environment = environment;
        }

        @Override
        public String[] selectImports(
                AnnotationMetadata importingClassMetadata) {

            Map<String, Object> attributes =
                    importingClassMetadata.getAnnotationAttributes(
                            EnableShipping.class.getName());

            if (attributes == null) {
                throw new IllegalStateException(
                        "@EnableShipping is required");
            }

            Channel channel = (Channel) attributes.get("channel");

            String configured = environment.getProperty(
                    "lesson.shipping.channel", "annotation");
            switch (configured.toLowerCase(Locale.ROOT)) {
                case "annotation" -> {
                    // Giữ giá trị từ @EnableShipping.
                }
                case "standard" -> channel = Channel.STANDARD;
                case "express" -> channel = Channel.EXPRESS;
                default -> throw new IllegalArgumentException(
                        "Unsupported shipping channel: " + configured);
            }

            Class<?> selected = channel == Channel.EXPRESS
                    ? ExpressShippingConfig.class
                    : StandardShippingConfig.class;
            return new String[] { selected.getName() };
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class StandardShippingConfig {
        @Bean
        Carrier carrier() {
            return new StandardCarrier();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ExpressShippingConfig {
        @Bean
        Carrier carrier() {
            return new ExpressCarrier();
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableShipping(channel = Channel.STANDARD)
    public static class StandardAppConfig {
        @Bean
        CheckoutService checkoutService(Carrier carrier) {
            return new CheckoutService(carrier);
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableShipping(channel = Channel.EXPRESS)
    public static class ExpressAppConfig {
        @Bean
        CheckoutService checkoutService(Carrier carrier) {
            return new CheckoutService(carrier);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PlainAppConfig {
        // Không có @Import hay @EnableShipping.
    }

    private static void run(
            String name, Class<?> appConfig, String selectedProperty) {

        try (var context = new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(
                    new MapPropertySource(
                            "lesson-case",
                            Map.of("lesson.shipping.channel",
                                    selectedProperty)));

            context.register(appConfig);
            context.refresh();

            CheckoutService checkout =
                    context.getBean(CheckoutService.class);
            System.out.println(name + ": carrier=" +
                    checkout.carrier().code() +
                    ", total=" + checkout.total(100));
            System.out.println(name + ": carrierCount=" +
                    context.getBeanNamesForType(Carrier.class).length);
        }
    }

    public static void main(String[] args) {
        run("STANDARD", StandardAppConfig.class, "annotation");
        run("EXPRESS", ExpressAppConfig.class, "annotation");
        run("OVERRIDE", StandardAppConfig.class, "express");

        try (var plain =
                new AnnotationConfigApplicationContext(PlainAppConfig.class)) {
            System.out.println("PLAIN: carrierCount=" +
                    plain.getBeanNamesForType(Carrier.class).length);
        }
    }
}
```

Đây là một file Java hoàn chỉnh: `ImportSelectorDemo` là top-level public class; các interfaces, enum, records, annotation, selector và configuration classes được khai báo nested. `Class.getName()` trả đúng tên JVM của nested configs, vì vậy selector không cần tự ghép tên class.

`ShippingSelector` không tạo `Carrier` bằng `new`; nó chỉ quyết định **configuration class** cần import. Sau đó Spring xử lý `@Bean Carrier carrier()` của config được chọn. `CheckoutService` nhận `Carrier` từ container nhờ method parameter injection.

### 8.3. Chạy chương trình

Trong thư mục `spring-import-selector-demo`:

```bash
gradle run --quiet
```

Nếu có Gradle Wrapper, dùng `./gradlew run --quiet` trên Linux/macOS hoặc `.\gradlew.bat run --quiet` trên Windows PowerShell.

**Stdout do chính chương trình in ra:**

```text
STANDARD: carrier=standard, total=105
STANDARD: carrierCount=1
EXPRESS: carrier=express, total=120
EXPRESS: carrierCount=1
OVERRIDE: carrier=express, total=120
OVERRIDE: carrierCount=1
PLAIN: carrierCount=0
```

Các dòng trên là kết quả của `System.out.println`; nếu môi trường cấu hình thêm logging thì Gradle/Spring có thể hiển thị thông tin khác.

### 8.4. Phân tích từng case

**STANDARD:** `StandardAppConfig` mang `@EnableShipping(channel=STANDARD)`. Property `lesson.shipping.channel=annotation` giữ nguyên giá trị annotation, nên selector trả tên `StandardShippingConfig`. Spring đăng ký bean `Carrier` từ factory method của config ấy. Phí thêm là 5, tổng 100 + 5 = 105.

**EXPRESS:** `ExpressAppConfig` mang `@EnableShipping(channel=EXPRESS)` và property vẫn là `annotation`. Selector trả `ExpressShippingConfig`, đăng ký `ExpressCarrier` có phí 20. Tổng bằng 120.

**OVERRIDE:** Cùng class `StandardAppConfig` như STANDARD, nhưng property được đặt thành `express` trước `register` và `refresh`. Selector nhận `Environment`, đọc property và chọn EXPRESS thay cho annotation STANDARD. Cấu hình và bean phụ thuộc được quyết định trong quá trình xây context, không đợi đến lúc gọi `checkout.total(...)`.

**PLAIN:** `PlainAppConfig` không mang `@EnableShipping`, không import hay scan `Carrier`. Vì thế `getBeanNamesForType(Carrier.class)` trả mảng rỗng. Nó cũng không khai báo `CheckoutService`, tránh tạo một consumer bắt buộc phải có Carrier.

**carrierCount = 1:** Trong từng context có selector, chỉ một trong hai configurations shipping được import. Đó là lý do không có ambiguity kiểu `Carrier` ở ví dụ. Nếu ứng dụng còn nguồn khai báo `Carrier` khác, count có thể lớn hơn; selector không tự loại các bean definitions độc lập ấy.

### 8.5. Vì sao dùng `MapPropertySource` thay vì sửa system property toàn JVM?

`MapPropertySource` được thêm vào `Environment` **của từng context** trước khi parsing. Điều này giúp ví dụ có output ổn định, không thay đổi `System.setProperty` chung có thể ảnh hưởng test khác. `addFirst(...)` đưa property source lên đầu thứ tự ưu tiên tìm property trong context được tạo.

Trong dự án thực tế, bạn có thể dùng environment variables, system properties hoặc config files đã được Spring/Boot tải đúng thời điểm. Điều cần nhớ là selector phải đọc giá trị **khi configuration đang được phân tích**: thay đổi một property sau khi context refresh thường **không tự chạy lại `selectImports`** và không thay thế bean definitions hiện có.

## 9. Thiết kế lựa chọn cấu hình an toàn

### 9.1. Chỉ chọn đúng những imports cần thiết

Nếu các cấu hình có factory methods trùng bean name `carrier`, nhập cả `StandardShippingConfig` và `ExpressShippingConfig` vào cùng một context là một thiết kế khác với việc chọn một trong hai. Tùy bean definition overriding policy, có thể xảy ra xung đột hoặc một bean bị ghi đè.

Selector ở mục 8 trả **duy nhất một** tên config để diễn đạt “một channel đang hoạt động”. Không dùng thứ tự imports làm cơ chế mặc định chọn provider.

### 9.2. Fail fast với cấu hình không hợp lệ

Nếu property nhận một giá trị ngoài `annotation`, `standard`, `express`, ví dụ `slow`, ví dụ sẽ ném `IllegalArgumentException` trong quá trình phân tích cấu hình. Điều này được chủ đích: typo trong configuration là lỗi nên báo rõ thay vì âm thầm đổi sang một provider.

```java
default -> throw new IllegalArgumentException(
        "Unsupported shipping channel: " + configured);
```

Đây là trích đoạn của selector ở mục 8, không phải file độc lập.

Nếu tính năng thật sự tùy chọn, bạn có thể cho selector trả mảng rỗng khi flag disable. Nhưng hãy kiểm tra các consumers: một bean `CheckoutService` bắt buộc phải có `Carrier` sẽ vẫn tạo lỗi dependency nếu selector không đăng ký carrier nào. Để module tùy chọn hoạt động trọn vẹn, cần conditional consumer configuration hoặc optional dependency policy tương ứng.

### 9.3. Ưu tiên lựa chọn có thể dự đoán

Viết tài liệu rõ attribute nào và property nào thắng. Trong code mục 8, property override được xét **sau** annotation. Nếu user chỉ đọc annotation và không biết property override tồn tại, kết quả runtime dễ gây bất ngờ. Có thể cân nhắc ghi thông tin lựa chọn vào structured logs ở startup hoặc metrics cấu hình, nhưng không ghi thông tin bí mật như credentials.

### 9.4. Hạn chế side effects trong selector

Tránh thực hiện các việc sau trong `selectImports(...)`:

- gọi HTTP API để quyết định class;
- truy vấn database hoặc các bean nghiệp vụ chưa được khởi tạo;
- ghi file hoặc thay đổi trạng thái global;
- tạo thread/timer để chọn configuration;
- tự khởi tạo bean rồi cache trong field selector;
- chọn class ngẫu nhiên theo thời gian mà không có config ổn định.

Selection nên **nhẹ, xác định được, đọc metadata/environment** để ứng dụng khởi động nhanh, test tái hiện được và không có dependency cycle do bootstrap quá sớm.

### 9.5. Classpath và module dependencies

Selector trả tên class có nghĩa class đó phải có trên runtime classpath và load được theo class loader đang sử dụng. Nếu cấu hình trả `com.vendor.OptionalStorageConfig` nhưng module/JAR tương ứng không có, context có thể thất bại trong import processing. Với optional integrations, trước khi chọn hãy dùng thông tin classpath/environment có chủ đích hoặc dùng `@ConditionalOnClass` trong Spring Boot auto-configuration theo quy ước phù hợp.

Đừng dùng `Class.forName(...)` bừa bãi để khởi tạo mọi class rồi quyết định: nạp class có thể có side effects. Với ứng dụng đơn giản, dependency tường minh và enum → config class là đủ.

### 9.6. Bean names, scopes và qualifiers vẫn quan trọng

`@ImportSelector` không tạo quy tắc singleton mới, không mặc định biến bean thành lazy và không gắn `@Primary` cho cấu hình được chọn. Sau khi class được import, `@Bean`, `@Scope`, `@Lazy`, `@Qualifier`, `@Profile` và các conditions liên quan vận hành như thông thường.

Nếu hai configurations độc lập có cùng interface nhưng chỉ một được chọn, injection theo type thường đơn giản. Nhưng nếu có một bean `Carrier` nữa được đăng ký bằng component scan, selector không tự bảo đảm uniqueness. Hãy kiểm tra toàn bộ registry.

## 10. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách sửa |
| --- | --- | --- |
| `selectImports` trả `"shippingClient"` | Nhầm Spring bean name với fully qualified class name | Trả `ShippingConfig.class.getName()` |
| Selector không được gọi | Class chứa `@Import`/`@Enable...` không được đăng ký hoặc annotation sai target | Xác nhận configuration entry point và meta-annotations |
| `attributes == null` | Selector gắn ở class không có `@EnableShipping` cần đọc | Kiểm tra metadata và khai báo annotation |
| Cast attribute enum sai kiểu | Giả định attribute là String trong khi khai báo enum | Dùng enum type chính xác hoặc `AnnotationAttributes` |
| Property đổi sau `refresh()` nhưng bean không thay | Selector chọn class khi parsing/bootstrap, không chạy lại tự động | Khởi tạo context mới hoặc cơ chế runtime switching riêng |
| Có hai `Carrier` dù selector chọn một | Một đường registration khác cũng tạo Carrier | Tìm tất cả `@Bean`/`@ComponentScan`/`@Import` liên quan |
| `NoSuchBeanDefinitionException` khi selector trả empty array | Consumer vẫn đòi dependency bắt buộc | Dùng optional dependency/conditional consumer config |
| Class được trả về không tồn tại | Sai tên binary/FQCN hoặc thiếu JAR | Dùng `SelectedConfig.class.getName()` và kiểm tra runtime classpath |
| Selector lấy business bean quá sớm | Import processing xảy ra trước khi context khởi tạo xong | Chỉ đọc metadata/environment hoặc hạ tầng bootstrap được hỗ trợ |
| Bật cả `@Profile` và selector, bean biến mất | Configuration được chọn tiếp tục bị profile/conditional loại | Kiểm tra active profiles và conditions |
| Lẫn `@ImportSelector` với `@ComponentScan` | Selector chỉ chọn class, không scan package | Sử dụng đúng cơ chế cần thiết |
| Nhầm selector với registrar | Selector không trực tiếp đăng ký bean definition tùy ý | Dùng `ImportBeanDefinitionRegistrar` nếu thật sự cần API registry |
| Dùng `DeferredImportSelector` cho nhu cầu đơn giản | Tăng độ phức tạp về ordering/group mà không có lợi ích | Bắt đầu với `ImportSelector` thường |
| Hard-code tên nested class bằng dấu chấm | JVM binary name của nested class chứa dấu `$` | Dùng `Class.getName()` |
| Dùng `@Order` rồi tưởng thứ tự bean init được quyết định | Import selection order không thay dependency graph | Khai báo DI/`@DependsOn` phù hợp |
| Chọn cấu hình theo random/time | Context khó tái hiện, test flaky | Chọn theo input config ổn định |
| Imported config bị scan/import thêm lần nữa | Nguồn bean definitions chồng chéo | Kiểm tra import graph, scanner, bean naming và overriding policy |

### 10.1. Quy trình chẩn đoán 6 bước

1. **Xác nhận selector chạy:** configuration class nào mang `@Import` hoặc `@EnableShipping`, class ấy đã thực sự được context đăng ký chưa?
2. **Xác định metadata:** tên annotation và kiểu attribute có đúng không? Có thể `metadata.getAnnotationAttributes(...)` trả `null` không?
3. **Xác định environment:** property sources đã được thêm **trước refresh** chưa, thứ tự ưu tiên ra sao?
4. **Kiểm tra class names trả về:** dùng `Class.getName()`, bảo đảm class có trên runtime classpath.
5. **Kiểm tra bean definitions cuối:** context thành công rồi thì dùng `getBeanNamesForType(...)` để xem bean của cấu hình được chọn; nếu context fail, đọc root cause thay vì truy vấn context chưa chạy được.
6. **Kiểm tra consumers:** các bean sử dụng dependency có phù hợp với số ứng viên thực tế không? Nếu không chọn provider nào, consumer bắt buộc không thể tự hoạt động.

## 11. Kiểm thử selector mà không dựng toàn bộ ứng dụng

Có hai cấp độ kiểm thử khác nhau.

### 11.1. Unit test selection logic

Nếu quy tắc chỉ phụ thuộc enum và property, trích logic chọn config sang một method thuần nhận input rõ ràng; unit test có thể kiểm tra:

| Annotation channel | Property | Class được chọn |
| --- | --- | --- |
| STANDARD | annotation | StandardShippingConfig |
| EXPRESS | annotation | ExpressShippingConfig |
| STANDARD | express | ExpressShippingConfig |
| EXPRESS | standard | StandardShippingConfig |
| STANDARD | giá trị lạ | Ném lỗi cấu hình |

Kiểm thử đơn vị không nhất thiết phải tạo Spring context. Tuy nhiên nó không chứng minh các `@Bean` definitions có thực sự được đăng ký; cần integration test cho phần đó.

### 11.2. Integration test với context nhỏ

Ví dụ mục 8 tạo ba contexts có lựa chọn khác nhau. Một test tương tự có thể dùng assertions:

```java
try (var context = new AnnotationConfigApplicationContext()) {
    context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource(
                    "test", Map.of("lesson.shipping.channel", "express")));
    context.register(StandardAppConfig.class);
    context.refresh();

    Carrier carrier = context.getBean(Carrier.class);
    if (!"express".equals(carrier.code())) {
        throw new AssertionError("Expected express carrier");
    }
    if (context.getBeanNamesForType(Carrier.class).length != 1) {
        throw new AssertionError("Expected exactly one Carrier");
    }
}
```

Đây là **trích đoạn** dùng các nested types `StandardAppConfig` và `Carrier` trong `ImportSelectorDemo`; khi đặt vào class khác, cần tên kiểu đầy đủ/import thích hợp. Assertion giúp phát hiện sai lệch thay vì chỉ quan sát stdout. Có thể mở rộng test cho nhánh property không hợp lệ, trường hợp thiếu provider và conflict với một `Carrier` khác.

### 11.3. Vì sao mỗi test nên có context riêng?

Một `ApplicationContext` xử lý bean definitions trong lúc khởi tạo. Nếu bạn muốn kiểm thử hai cấu hình khác nhau, nên tạo **hai context tách biệt**, không đổi property rồi mong cùng context tự gỡ bean cũ và import config mới. Điều này giúp test độc lập, tránh rò state và phản ánh đúng thời điểm chọn import.

## 12. Bài tập tự kiểm tra có đáp án

### Bài 1 — Tên class hay bean name?

Method `selectImports(...)` trả `new String[]{"expressCarrier"}`. Đây là bean name của `@Bean Carrier expressCarrier()`. Có đúng contract không?

**Đáp án:** Không. Nó cần trả tên class để import, ví dụ `ExpressShippingConfig.class.getName()`. Bean name chỉ được quyết định khi Spring xử lý class/config được chọn.

### Bài 2 — Lựa chọn bằng attribute

`@EnableShipping(channel=EXPRESS)` và property `lesson.shipping.channel=annotation`. Selector mục 8 trả class nào?

**Đáp án:** `ExpressShippingConfig`, vì property “annotation” nghĩa là giữ nguyên enum attribute EXPRESS.

### Bài 3 — Property ghi đè annotation

`@EnableShipping(channel=STANDARD)`, property `lesson.shipping.channel=express`. Kết quả nào?

**Đáp án:** `ExpressShippingConfig`. Property có ưu tiên cao hơn attribute trong ví dụ.

### Bài 4 — Vắng mặt tính năng

Selector trả mảng rỗng, nhưng `CheckoutService` có factory method yêu cầu tham số `Carrier carrier` bắt buộc. Context có luôn refresh thành công không?

**Đáp án:** Không. Nếu không có bean Carrier từ nguồn khác, tạo CheckoutService sẽ thất bại vì dependency thiếu. Phải thiết kế consumer optional/conditional tương ứng.

### Bài 5 — Một context, hai modules khác nhau

Selector chỉ import StandardShippingConfig, nhưng `AppConfig` cũng `@Import(ExpressShippingConfig.class)`. Có bảo đảm đúng một Carrier không?

**Đáp án:** Không. Import khác vẫn bổ sung bean definitions. Hai configs có thể có bean names trùng hoặc cùng type, dẫn tới conflict/ambiguity tùy thiết kế.

### Bài 6 — ImportSelector hay @Profile?

Một ứng dụng có hai cấu hình `DevConfig` và `ProdConfig` chỉ khác môi trường dev/prod, không có custom annotation attributes. Có bắt buộc tự viết ImportSelector không?

**Đáp án:** Không. `@Profile` hoặc conditional configuration có thể đơn giản hơn. Dùng ImportSelector khi cần lựa chọn class dựa trên logic/metadata mang tính extension.

### Bài 7 — Metadata

`metadata.getClassName()` bên trong ShippingSelector trả tên `ExpressShippingConfig` có đúng không?

**Đáp án:** Không nhất thiết, và không phải semantics của method này. Nó mô tả **importing class**, ví dụ `ExpressAppConfig`; class được chọn nằm trong mảng trả về từ `selectImports`.

### Bài 8 — Static inner config

Trong ví dụ mục 8, `StandardShippingConfig` là nested class. Tại sao dùng `StandardShippingConfig.class.getName()` tốt hơn tự gõ `"ImportSelectorDemo.StandardShippingConfig"`?

**Đáp án:** Vì JVM binary name của nested class chứa `$`; `Class.getName()` trả đúng định danh để Spring load, tránh sai class name khi refactor.

### Bài 9 — DeferredImportSelector

Có cần `DeferredImportSelector` để bắt Spring đợi đến lần HTTP request đầu tiên mới quyết định provider không?

**Đáp án:** Không. Deferred chỉ trì hoãn giai đoạn xử lý imports trong bootstrap; nó không chọn bean động theo request. Runtime switching cần một abstraction/service routing khác.

### Bài 10 — EnvironmentAware

`ShippingSelector` implement `EnvironmentAware`. Khi nào Spring gọi `setEnvironment(...)` so với `selectImports(...)`?

**Đáp án:** Theo contract, Aware callback được thực hiện trước khi selector đưa ra lựa chọn. Nhờ đó selector có thể đọc property trong `Environment`.

### Bài 11 — Chọn nhiều configurations

Có được trả mảng gồm `MetricsConfig.class.getName()` và `ShippingConfig.class.getName()` không?

**Đáp án:** Có, miễn cả hai class tồn tại và không gây xung đột bean definitions ngoài ý muốn. `ImportSelector` không bị giới hạn một class; ví dụ shipping chỉ chọn một để bảo đảm exactly one Carrier.

### Bài 12 — Kiểm thử hai chế độ trong cùng container

Một test tạo context với STANDARD, gọi `context.getEnvironment().getPropertySources().addFirst(...)` để đổi EXPRESS **sau refresh** rồi kiểm tra Carrier. Có chắc Spring tự thay Carrier hiện có không?

**Đáp án:** Không. Import selection đã diễn ra trong configuration processing; thay property sau refresh không tự cập nhật import graph. Tạo context khác nếu muốn so sánh behavior bootstrap.

## 13. Checklist thiết kế một ImportSelector

- Annotation/`@Import` đặt trên class được Spring biết đến chưa?
- `selectImports` trả **tên class đầy đủ** và mảng rỗng khi không cần nhập, không trả bean name?
- Input lựa chọn đến từ metadata/`Environment` rõ ràng, đã khai báo chính sách ưu tiên chưa?
- Selector có tránh side effects, I/O và eager lookup vào business beans không?
- Mọi classes có thể được chọn đều có trên runtime classpath hoặc được kiểm tra trước đúng cách chưa?
- Có đảm bảo không vô tình nhập hai configuration implementations cho một dependency đơn?
- Các beans được import có constructor/factory dependencies và qualifiers phù hợp không?
- Conditional/profile trên imported configs có thể làm một bean biến mất không?
- Đã phân biệt normal `ImportSelector` với `DeferredImportSelector` và registrar chưa?
- Có integration test cho mỗi nhánh và một test cho giá trị cấu hình bất hợp lệ chưa?
- Thay property sau context refresh có bị nhầm là cơ chế reload cấu hình không?
- Đã kiểm tra bean definitions của context thật thay vì chỉ unit test selector method chưa?

## 14. Tổng kết

`ImportSelector` cho phép **chọn danh sách class cần đưa vào Spring configuration graph** dựa trên `AnnotationMetadata` và những dữ kiện hạ tầng như `Environment`. Phương thức `selectImports(...)` trả **mảng tên class đầy đủ**, không trả bean instances và không trả bean names. Spring sau đó xử lý các class được chọn để đăng ký bean definitions và tạo managed beans theo dependency graph/scope/lifecycle bình thường.

Dùng `@Import(Selector.class)` trực tiếp hoặc bọc trong một custom `@Enable...` annotation sẽ tạo được API cấu hình module rõ ràng. `@Conditional`/`@Profile` thích hợp cho điều kiện bật/tắt đơn giản; `DeferredImportSelector` phục vụ lựa chọn ở giai đoạn parsing muộn hơn, không phải thay cấu hình theo request. **Đưa ra quyết định tại bootstrap** khác với **runtime routing**: nếu cần thay provider khi ứng dụng đang chạy, thiết kế một service abstraction có chính sách thay đổi rõ ràng thay vì mong selector tự chạy lại.

### Tài liệu chính thức

- [Spring Framework 6.2 — `ImportSelector` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportSelector.html).
- [Spring Framework 6.2 — `DeferredImportSelector` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html).
- [Spring Framework 6.2 — `@Import` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Import.html).
- [Spring Framework 6.2 — `ImportBeanDefinitionRegistrar` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportBeanDefinitionRegistrar.html).
- [Spring Framework 6.2 — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html).
- [Spring Framework 6.2 — Conditional Bean Definitions](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html#beans-java-conditional).
