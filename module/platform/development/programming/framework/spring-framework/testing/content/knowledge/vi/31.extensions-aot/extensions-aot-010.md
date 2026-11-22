# Chỉ mở rộng hạ tầng khi cấu hình có sẵn không đáp ứng

Spring TestContext Framework đã cung cấp nhiều cơ chế để cấu hình test: `@ContextConfiguration`, `@SpringBootTest`, `@TestPropertySource`, `@DynamicPropertySource`, `@ActiveProfiles`, `@Import`, `@TestConfiguration`, `ApplicationContextInitializer` và các annotation liên quan. Trong phần lớn dự án, các cơ chế khai báo này đã đủ để tạo application context đúng với kịch bản kiểm thử.

Chỉ nên viết extension riêng khi một yêu cầu lặp lại hoặc một quy tắc hạ tầng không thể biểu đạt rõ ràng bằng cơ chế có sẵn. Khi cần mở rộng, hãy chọn extension point hẹp nhất đáp ứng nhu cầu. Một custom initializer cho một thay đổi nhỏ thường dễ hiểu và ít ảnh hưởng hơn một custom `TestContextBootstrapper` thay đổi cách toàn bộ test được khởi tạo.

## 1. Bắt đầu từ cấu hình có sẵn

Trước khi tạo extension, hãy xác định chính xác điều test cần thay đổi: bean nào được nạp, property nào cần đặt, profile nào cần kích hoạt, resource nào cần khởi tạo hoặc lifecycle nào cần quan sát.

| Nhu cầu | Cơ chế có sẵn nên thử trước |
|---|---|
| Chọn cấu hình hoặc resource context | `@ContextConfiguration(classes = ...)`, `locations = ...` |
| Nạp toàn bộ cấu hình Spring Boot | `@SpringBootTest` |
| Thêm cấu hình chỉ dùng trong test | `@TestConfiguration`, `@Import` |
| Đặt property tĩnh cho test | `@TestPropertySource`, `@SpringBootTest(properties = ...)` |
| Đưa URL hoặc port của resource đang chạy vào context | `@DynamicPropertySource` |
| Chọn profile | `@ActiveProfiles` |
| Chọn profile bằng quy tắc riêng | `ActiveProfilesResolver` |
| Chạy logic trước khi context refresh | `ApplicationContextInitializer` |
| Thêm hành vi quanh lifecycle test của Spring | `TestExecutionListener` |
| Tùy chỉnh context theo annotation hoặc metadata của test | `ContextCustomizerFactory` |
| Nạp context từ nguồn hoặc môi trường đặc biệt | Custom `SmartContextLoader` |
| Thay đổi cách Spring TestContext tổng hợp cấu hình và bootstrap | Custom `TestContextBootstrapper` |

Ví dụ, nếu chỉ cần bật một feature flag trong test, dùng property trực tiếp thường là đủ:

```java
@SpringBootTest(properties = "feature.catalog.enabled=true")
class CatalogFeatureTests {
    // Kiểm thử feature khi được bật.
}
```

Nếu nhiều test cần cùng một profile hoặc property, hãy gom cấu hình vào annotation hoặc lớp cấu hình dùng chung trước khi tạo SPI riêng. Mục tiêu là làm rõ cấu hình test, không tạo thêm một tầng hạ tầng chỉ để thay thế vài dòng annotation.

## 2. Chọn extension point hẹp nhất

Spring TestContext có các extension point ở nhiều mức:

```text
Test class và annotation
        |
        v
TestContextBootstrapper
  Tổng hợp metadata, loader, listeners và customizers
        |
        v
ContextLoader / SmartContextLoader
  Tạo hoặc nạp ApplicationContext
        |
        v
ContextCustomizerFactory -> ContextCustomizer
  Điều chỉnh context theo metadata của test
        |
        v
ApplicationContextInitializer
  Khởi tạo context trước khi refresh
        |
        v
ApplicationContext được refresh
        |
        v
TestExecutionListener
  Theo dõi lifecycle của test class/method
```

Sơ đồ mô tả các vai trò chính, không phải mọi callback đều được gọi trực tiếp theo đúng thứ tự hiển thị trong mọi cấu hình. Thứ tự thực tế phụ thuộc bootstrapper, context loader và lifecycle của TestContext.

Chọn theo phạm vi:

- Thay đổi property hoặc đăng ký cấu hình trước khi refresh: initializer.
- Áp dụng một tùy chỉnh dựa trên annotation cho nhiều test: context customizer factory.
- Thực hiện hành vi ở các mốc Spring Test lifecycle: test execution listener.
- Thay cách đọc resource hoặc tạo context: context loader.
- Thay thuật toán bootstrap tổng thể: test context bootstrapper.

Không chọn extension có phạm vi rộng hơn nhu cầu. Càng can thiệp ở tầng bootstrap, càng nhiều hành vi mặc định của Spring Test có thể bị ảnh hưởng.

## 3. ApplicationContextInitializer cho khởi tạo context

`ApplicationContextInitializer` được gọi trong quá trình chuẩn bị context, trước khi context được refresh. Nó phù hợp khi cần thêm một property source, đăng ký cấu hình khởi tạo hoặc áp dụng một thay đổi có kiểm soát lên `ConfigurableApplicationContext`.

Ví dụ tạo initializer để thêm property source dành cho test:

```java
import java.util.Map;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;

public class TestFeatureInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(ConfigurableApplicationContext context) {
        Map<String, Object> properties = Map.of(
            "feature.catalog.enabled", "true",
            "feature.catalog.source", "test"
        );

        context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource("catalogTestProperties", properties)
        );
    }
}
```

Đăng ký initializer trên test:

```java
import org.springframework.test.context.ContextConfiguration;

@ContextConfiguration(
    classes = CatalogConfiguration.class,
    initializers = TestFeatureInitializer.class
)
class CatalogFeatureTests {
}
```

`addFirst(...)` đặt property source ở độ ưu tiên cao hơn các property source phía sau. Vì vậy, chỉ dùng cách này khi test thật sự cần override giá trị. Nếu chỉ có một test cần property, `@TestPropertySource` hoặc thuộc tính `properties` trên `@SpringBootTest` thường đơn giản hơn.

### Khi nào dùng DynamicPropertySource?

Nếu giá trị chỉ có sau khi một resource test được khởi động, chẳng hạn URL của Testcontainers hoặc mock server, `@DynamicPropertySource` thường diễn đạt ý định rõ hơn initializer:

```java
import org.junit.jupiter.api.Test;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class ExternalServiceTests {

    @DynamicPropertySource
    static void registerProperties(DynamicPropertyRegistry registry) {
        registry.add("catalog.base-url", () -> mockServerUrl());
    }
}
```

`DynamicPropertyRegistry` nhận supplier để lấy giá trị khi property được truy cập. Trong test thực tế, `mockServerUrl()` phải trả về URL từ resource đã được khởi động và có vòng đời phù hợp với context. Đừng tự viết initializer chỉ để đưa một URL động vào environment khi `@DynamicPropertySource` đã đáp ứng nhu cầu.

## 4. ContextCustomizerFactory cho tùy chỉnh theo annotation

Một `ApplicationContextInitializer` được khai báo trực tiếp trên test phù hợp với một vài test đã biết. Khi cần áp dụng một quy tắc dựa trên annotation cho nhiều test mà không lặp khai báo initializer, có thể tạo `ContextCustomizerFactory`.

Ví dụ, định nghĩa annotation đánh dấu test cần bật một property:

```java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
public @interface EnableCatalogTestMode {
}
```

Factory kiểm tra annotation trên test class và trả về customizer nếu cần:

```java
import java.util.List;

import org.springframework.test.context.ContextConfigurationAttributes;
import org.springframework.test.context.ContextCustomizer;
import org.springframework.test.context.ContextCustomizerFactory;

public class CatalogTestContextCustomizerFactory
        implements ContextCustomizerFactory {

    @Override
    public ContextCustomizer createContextCustomizer(
            Class<?> testClass,
            List<ContextConfigurationAttributes> configAttributes) {

        if (testClass.isAnnotationPresent(EnableCatalogTestMode.class)) {
            return new CatalogTestContextCustomizer();
        }
        return null;
    }
}
```

Customizer thay đổi environment trước khi context refresh:

```java
import java.util.Map;

import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.MapPropertySource;
import org.springframework.test.context.ContextCustomizer;
import org.springframework.test.context.MergedContextConfiguration;

public final class CatalogTestContextCustomizer implements ContextCustomizer {

    @Override
    public void customizeContext(
            ConfigurableApplicationContext context,
            MergedContextConfiguration mergedConfig) {

        context.getEnvironment().getPropertySources().addFirst(
            new MapPropertySource(
                "catalogTestMode",
                Map.of("feature.catalog.mode", "test")
            )
        );
    }

    @Override
    public boolean equals(Object other) {
        return other != null && other.getClass() == getClass();
    }

    @Override
    public int hashCode() {
        return getClass().hashCode();
    }
}
```

Để Spring TestContext phát hiện factory, đăng ký trong file `META-INF/spring.factories` của module test hoặc thư viện test dùng chung:

```properties
org.springframework.test.context.ContextCustomizerFactory=\
com.example.testing.CatalogTestContextCustomizerFactory
```

Sau đó, test có thể khai báo:

```java
@EnableCatalogTestMode
@SpringBootTest
class CatalogFeatureTests {
}
```

`ContextCustomizer` là một phần của cấu hình context đã được merge. `equals()` và `hashCode()` cần phản ánh trạng thái cấu hình có ảnh hưởng đến context. Ví dụ trên customizer không có tham số nên hai instance cùng class tương đương. Nếu customizer chứa giá trị khác nhau theo test, các giá trị đó phải tham gia vào `equals()` và `hashCode()` để Spring không tái sử dụng nhầm context được tạo với cấu hình khác.

Factory được phát hiện theo classpath nên có thể ảnh hưởng rộng đến các test trong module. Chỉ đăng ký SPI này khi quy tắc thật sự dùng chung; với một test đơn lẻ, khai báo `initializers` hoặc cấu hình property trực tiếp sẽ dễ đọc hơn.

## 5. TestExecutionListener cho lifecycle của Spring Test

`TestExecutionListener` nhận callback ở các giai đoạn của Spring TestContext, ví dụ chuẩn bị test instance, trước và sau test method hoặc trước và sau test class. Nó phù hợp với hành vi hạ tầng cần chạy nhất quán tại những mốc lifecycle của Spring Test.

Spring cung cấp `AbstractTestExecutionListener` để chỉ override callback cần thiết:

```java
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public class TestAuditListener extends AbstractTestExecutionListener {

    @Override
    public void beforeTestMethod(TestContext testContext) {
        String methodName = testContext.getTestMethod().getName();
        System.out.println("Starting Spring test: " + methodName);
    }

    @Override
    public void afterTestMethod(TestContext testContext) {
        String methodName = testContext.getTestMethod().getName();
        System.out.println("Finished Spring test: " + methodName);
    }
}
```

Đăng ký listener trên test và giữ các listener mặc định:

```java
import org.springframework.test.context.TestExecutionListeners;

@TestExecutionListeners(
    listeners = TestAuditListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS
)
class CatalogServiceTests {
}
```

`MERGE_WITH_DEFAULTS` rất quan trọng khi chỉ muốn thêm listener. Nếu thay thế danh sách mặc định ngoài ý muốn, những listener Spring cung cấp cho dependency injection, transaction hoặc các tính năng test khác có thể không còn hoạt động như trước.

Nếu nhu cầu chỉ liên quan đến lifecycle riêng của JUnit Jupiter, một JUnit extension như `BeforeEachCallback` hoặc `AfterEachCallback` có thể phù hợp hơn. Dùng `TestExecutionListener` khi cần tích hợp với `TestContext`, `ApplicationContext` hoặc lifecycle mà Spring Test quản lý.

## 6. ActiveProfilesResolver cho quy tắc chọn profile

Nếu profile được chọn theo một quy tắc riêng, `ActiveProfilesResolver` cho phép tính danh sách profile dựa trên test class:

```java
import org.springframework.core.env.Profiles;
import org.springframework.test.context.ActiveProfilesResolver;

public class EnvironmentProfileResolver implements ActiveProfilesResolver {

    @Override
    public String[] resolve(Class<?> testClass) {
        if (testClass.isAnnotationPresent(UseExternalSystemProfile.class)) {
            return new String[] {"test", "external"};
        }
        return new String[] {"test"};
    }
}
```

Khai báo resolver:

```java
@ActiveProfiles(resolver = EnvironmentProfileResolver.class)
class ExternalCatalogTests {
}
```

Đây là extension hẹp dành riêng cho việc chọn profile. Nếu chỉ cần bật profile cố định, `@ActiveProfiles("test")` đơn giản và dễ hiểu hơn. Không nên để resolver phụ thuộc vào biến môi trường thay đổi ngẫu nhiên giữa lúc AOT processing và lúc chạy test.

## 7. Custom ContextLoader và TestContextBootstrapper

`ContextLoader` hoặc `SmartContextLoader` chịu trách nhiệm nạp hoặc tạo `ApplicationContext` từ cấu hình test. Spring đã có loader cho các trường hợp thông dụng như cấu hình Java, XML và web context. Chỉ viết loader riêng khi test phải tạo context từ một nguồn hoặc môi trường đặc biệt mà loader có sẵn không hỗ trợ.

Có thể chỉ định loader trên `@ContextConfiguration`:

```java
@ContextConfiguration(
    classes = CatalogConfiguration.class,
    loader = CustomCatalogContextLoader.class
)
class CatalogContextTests {
}
```

`TestContextBootstrapper` ở mức cao hơn: nó quyết định cách Spring Test tổng hợp metadata, chọn context loader, listeners và các thành phần bootstrap khác. `@BootstrapWith` cho phép chỉ định bootstrapper riêng:

```java
@BootstrapWith(CustomCatalogTestBootstrapper.class)
class CatalogInfrastructureTests {
}
```

Đây là lựa chọn có ảnh hưởng lớn đến toàn bộ quá trình khởi tạo test. Chỉ dùng khi extension point hẹp hơn không thể đáp ứng. Khi thay bootstrapper, phải hiểu rõ các mặc định mà Spring cung cấp và bảo đảm các annotation như `@ContextConfiguration`, `@WebAppConfiguration`, `@ActiveProfiles` và `@TestPropertySource` vẫn được xử lý theo hợp đồng mong muốn.

## 8. Giữ context cache hoạt động đúng

Spring TestContext cache `ApplicationContext` dựa trên cấu hình đã được merge. Việc thêm customizer hoặc thay đổi cách bootstrap có thể làm thay đổi cache key và số context được tạo.

Khi viết customizer:

- Cấu hình có ảnh hưởng đến context phải được biểu diễn trong `equals()` và `hashCode()`.
- Không đưa object có identity ngẫu nhiên vào customizer nếu hai test có cấu hình tương đương cần dùng chung context.
- Tránh tạo resource có vòng đời riêng cho mỗi test method bên trong singleton context mà không có cơ chế quản lý rõ ràng.
- Không đọc trạng thái toàn cục thay đổi liên tục để quyết định context trong lúc factory được gọi.
- Dùng `@DirtiesContext` khi test thật sự làm hỏng context và cần loại context khỏi cache, không dùng nó như khóa đồng bộ hoặc cách dọn mọi tài nguyên ngoài context.

Ví dụ, nếu customizer nhận `tenantId`, hai tenant khác nhau có thể cần context khác nhau khi tenant được dùng để cấu hình bean. Khi đó, `tenantId` phải tham gia vào equality. Nếu tenant chỉ là dữ liệu của từng request, đưa nó vào request hoặc Reactor Context sẽ phù hợp hơn việc tạo một application context cho mỗi tenant.

## 9. Tương thích với TestContext AOT

Spring Framework hỗ trợ xử lý ahead-of-time cho test context. Trong giai đoạn build, Spring có thể phân tích cấu hình test và tạo mã khởi tạo context để giảm công việc cần làm lúc chạy test. Điều này đặc biệt quan trọng với ứng dụng dùng Spring AOT hoặc native image.

Khi viết extension, cần phân biệt hai giai đoạn:

- **AOT processing:** Spring phân tích test class, cấu hình và application context để tạo metadata hoặc mã khởi tạo.
- **Runtime:** test sử dụng context đã được chuẩn bị theo kết quả AOT hoặc context được tạo theo cơ chế runtime thông thường.

Một extension hoạt động trong runtime thông thường chưa chắc tương thích với AOT. Ví dụ, extension dựa vào quét classpath tùy ý, đọc file chỉ tồn tại trên máy phát triển, tạo class động hoặc suy luận cấu hình từ trạng thái môi trường tại thời điểm chạy có thể không được phản ánh đầy đủ trong mã AOT.

Khi cần hỗ trợ AOT:

1. Ưu tiên annotation và cấu hình tĩnh mà Spring có thể phân tích.
2. Giữ customizer và initializer xác định, lặp lại được với cùng metadata đầu vào.
3. Tránh phụ thuộc vào filesystem hoặc biến môi trường thay đổi giữa build và runtime.
4. Nếu code cần reflection, resource hoặc proxy không được nhận diện tĩnh, khai báo runtime hints phù hợp bằng cơ chế Spring AOT như `RuntimeHintsRegistrar`.
5. Kiểm tra extension trong cả chế độ test thông thường và chế độ AOT mà dự án sử dụng.

Nếu một test không thể chạy ở chế độ AOT vì phụ thuộc vào hành vi runtime không thể mô tả trước, Spring Framework cung cấp `@DisabledInAotMode` trong các phiên bản hỗ trợ (Spring Framework 6.2 trở lên). Chỉ dùng annotation này khi test thực sự không tương thích với AOT; không dùng để che giấu extension có thể được thiết kế lại.

## 10. Runtime hints khi extension dùng reflection hoặc resource

Trong môi trường native image, những thao tác dựa vào reflection, resource loading hoặc dynamic proxy có thể cần metadata được cung cấp trước. Spring AOT cung cấp API runtime hints để khai báo các nhu cầu đó.

Ví dụ một registrar:

```java
import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class CatalogTestRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.reflection().registerType(
            CatalogPayload.class,
            MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
            MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
```

Đăng ký registrar bằng `@ImportRuntimeHints` trên cấu hình liên quan:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ImportRuntimeHints;

@Configuration
@ImportRuntimeHints(CatalogTestRuntimeHints.class)
class CatalogTestConfiguration {
}
```

Đây là ví dụ minh họa cách khai báo reflection hint; danh mục member cần đăng ký phải khớp thao tác thực tế. Không thêm hints rộng cho mọi class hoặc mọi method nếu ứng dụng chỉ cần một constructor hay method cụ thể. Nếu extension không dùng reflection, resource hoặc proxy động, không cần thêm registrar chỉ vì dự án có bật AOT.

## 11. Những dấu hiệu cho thấy extension đang quá phức tạp

Hãy xem lại thiết kế nếu:

- Một extension chỉ thay một property mà annotation có sẵn đã làm được.
- Một custom bootstrapper được viết chỉ để thêm một listener.
- Factory toàn cục thay đổi context cho mọi test dù chỉ một nhóm test cần hành vi đó.
- Customizer đọc trạng thái ngẫu nhiên, làm cache key khó dự đoán.
- Extension tạo resource nhưng không có lifecycle cleanup rõ ràng.
- Test chỉ chạy được khi chạy riêng vì extension dùng static mutable state.
- AOT processing và runtime tạo ra cấu hình khác nhau.
- `@DirtiesContext` được thêm vào hàng loạt test để né xung đột do extension tạo ra.

Trong các trường hợp này, hãy quay lại xác định yêu cầu thực sự và thử cơ chế cấu hình hẹp hơn.

## 12. Quy trình quyết định có cần mở rộng hạ tầng không

1. Mô tả điều test cần: property, profile, bean, context, resource hay lifecycle.
2. Kiểm tra annotation và hook sẵn có như `@TestPropertySource`, `@DynamicPropertySource`, `@Import`, initializer hoặc resolver.
3. Nếu cần logic trước refresh, chọn `ApplicationContextInitializer`.
4. Nếu cần áp dụng tùy chỉnh dựa trên metadata hoặc annotation cho nhiều test, cân nhắc `ContextCustomizerFactory`.
5. Nếu cần callback ở lifecycle của Spring Test, chọn `TestExecutionListener` và merge listener mặc định.
6. Chỉ chọn custom loader hoặc bootstrapper khi cần thay cách tạo context hoặc thuật toán bootstrap tổng thể.
7. Xác định cache key, vòng đời resource và phạm vi ảnh hưởng của extension.
8. Kiểm tra khả năng tương thích AOT; bổ sung runtime hints chỉ khi reflection, resource hoặc proxy thực sự cần.

Mở rộng Spring TestContext nên là quyết định có căn cứ từ một giới hạn cụ thể của cấu hình hiện tại. Dùng cơ chế khai báo sẵn cho nhu cầu phổ biến, chọn extension point nhỏ nhất khi cần logic riêng và giữ extension xác định, có vòng đời rõ ràng, tương thích với context cache và AOT. Cách tiếp cận này giúp test infrastructure dễ đọc, dễ nâng cấp và không làm phức tạp các test không liên quan.
