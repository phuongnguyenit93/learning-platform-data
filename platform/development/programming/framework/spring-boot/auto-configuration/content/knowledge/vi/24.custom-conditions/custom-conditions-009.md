# Chọn ConfigurationPhase phù hợp với dữ liệu cần quan sát

## 1. Vì sao custom Condition cần chọn đúng phase?

Spring Framework cho phép viết điều kiện riêng bằng interface `Condition`. Điều kiện quyết định một configuration class hoặc bean definition có được đăng ký hay không. Khi condition cần biết đang đọc cấu hình hay đang đăng ký bean, chỉ kiểm tra dữ liệu mà không xét thời điểm có thể tạo ra kết quả sai.

Ví dụ:

- Muốn quyết định có đưa cả một `@Configuration` class vào context hay không dựa trên active profile, property, classpath hoặc resource: dữ liệu này có sẵn từ môi trường, nên có thể đánh giá khi parse configuration.
- Muốn đăng ký một `@Bean` chỉ khi bean definition khác đã được đăng ký: phải đợi đến giai đoạn register bean. Nếu kiểm tra registry quá sớm, bean definition cần tìm có thể chưa tồn tại.
- Muốn đọc giá trị từ một bean instance: **không có phase nào phù hợp**. Condition không được lấy hoặc khởi tạo bean instance để quyết định cấu hình.

`ConfigurationCondition` mở rộng `Condition` và cho phép chỉ định một trong hai phase:

- `PARSE_CONFIGURATION`
- `REGISTER_BEAN`

Bài học dùng **Java 17+, Spring Framework 6.1.x và Spring Boot 3.3.x**. Trọng tâm là chọn phase theo loại dữ liệu cần quan sát, triển khai condition an toàn, kiểm soát thứ tự đăng ký và kiểm thử cả hai trường hợp.

## 2. Hai phase khác nhau ở đâu?

| Phase | Thời điểm đánh giá | Dữ liệu phù hợp | Kết quả nếu không match |
|---|---|---|---|
| `PARSE_CONFIGURATION` | Khi Spring đang parse một `@Configuration` class | Environment, profile, property, classpath, resource và annotation metadata | Configuration class không được đưa vào quá trình xử lý |
| `REGISTER_BEAN` | Khi Spring đăng ký một bean thông thường, ví dụ bean method | Bean definition registry và trạng thái cấu hình đã parse | Bean đang xét không được đăng ký; configuration class vẫn có thể tồn tại |

### 2.1. PARSE_CONFIGURATION: quyết định có đưa configuration class vào hay không

Spring đang đọc metadata của configuration class và xác định class đó có phù hợp để tiếp tục xử lý không. Nếu condition ở phase này trả về `false`, class đó không được thêm vào configuration model.

Dữ liệu phù hợp:

- `Environment`: property hiệu lực, active profile, system property và environment variable.
- `ClassLoader`: class tùy chọn có hiện diện hay không.
- `ResourceLoader`: resource cấu hình có tồn tại hay không.
- `AnnotatedTypeMetadata`: annotation và thuộc tính trên class đang được kiểm tra.

Không nên đọc bean definitions với giả định tất cả configuration khác đã được xử lý. Ở thời điểm parse, registry chưa phải là danh sách hoàn chỉnh của các bean definitions sẽ được tạo.

Ví dụ phù hợp: chỉ đưa cấu hình dành cho production vào context khi `app.mode=production`.

### 2.2. REGISTER_BEAN: quyết định có đăng ký bean cụ thể hay không

Đến phase này, các `@Configuration` class đã được parse. Spring đang đăng ký các bean definitions. Đây là thời điểm phù hợp khi condition cần xem một bean definition khác đã có trong registry hay chưa.

Dữ liệu phù hợp:

- `BeanDefinitionRegistry` qua `ConditionContext.getRegistry()`.
- `ConfigurableListableBeanFactory` qua `ConditionContext.getBeanFactory()` nếu có.
- Bean name, bean definition đã đăng ký, alias và metadata liên quan.

`REGISTER_BEAN` không có nghĩa mọi bean instance đã được tạo. Đây vẫn là giai đoạn đăng ký definition; dependency injection và khởi tạo instance diễn ra sau đó theo quá trình refresh/lifecycle.

Ví dụ phù hợp: chỉ đăng ký `OptionalFeature` khi bean definition tên `acmePrerequisite` đã tồn tại.

### 2.3. Sơ đồ thời điểm

~~~text
Đọc Environment / profiles / classpath
                 |
                 v
       PARSE_CONFIGURATION
                 |
          @Configuration
          class có match?
             /       \
           Có         Không
           |            |
           v            v
    Parse cấu hình    Bỏ qua class
           |
           v
 Tất cả configuration classes
       được parse xong
           |
           v
       REGISTER_BEAN
           |
    Đánh giá condition
     trên bean method
           |
      Có match?
       /     \
     Có       Không
     |          |
     v          v
Đăng ký bean  Bỏ qua bean
definition    definition
     |
     v
Sau đó mới tạo bean instances
theo dependency và lifecycle
~~~

Sơ đồ là mô hình khái niệm. Các bước nội bộ có thể phức tạp hơn, nhưng điểm cần nhớ là **phase xác định thời điểm condition được đánh giá, không phải thứ tự khởi tạo bean instance**.

## 3. Các API condition cung cấp dữ liệu gì?

### 3.1. Condition và ConfigurationCondition

`Condition` yêu cầu một phương thức:

~~~java
boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
);
~~~

Trả về `true` nếu component được phép đăng ký; trả về `false` để veto việc đăng ký.

`ConfigurationCondition` bổ sung:

~~~java
ConfigurationCondition.ConfigurationPhase getConfigurationPhase();
~~~

Giá trị trả về cho biết Spring cần đánh giá condition trong phase nào. Nếu cần điều khiển phase rõ ràng, hãy implement `ConfigurationCondition` thay vì chỉ implement `Condition`.

### 3.2. ConditionContext

`ConditionContext` cung cấp các đối tượng cần thiết để đánh giá condition:

| Method | Dữ liệu trả về | Dùng khi |
|---|---|---|
| `getEnvironment()` | `Environment` | Đọc property, profile và cấu hình hiệu lực |
| `getRegistry()` | `BeanDefinitionRegistry` | Kiểm tra metadata bean definition |
| `getBeanFactory()` | `ConfigurableListableBeanFactory` hoặc `null` | Truy vấn metadata của factory khi factory có sẵn |
| `getResourceLoader()` | `ResourceLoader` | Kiểm tra resource theo cơ chế Spring |
| `getClassLoader()` | `ClassLoader` hoặc `null` | Kiểm tra sự hiện diện của class tùy chọn |

`getBeanFactory()` có thể trả về `null` nếu factory không sẵn có hoặc không thể chuyển về kiểu phù hợp. `getRegistry()` có thể ném `IllegalStateException` trong một số ngữ cảnh không có registry; trong quá trình xử lý configuration thông thường, registry thường có sẵn.

### 3.3. AnnotatedTypeMetadata

`AnnotatedTypeMetadata` mô tả element đang được kiểm tra, có thể là class hoặc method. Nó cho phép đọc annotation metadata mà không cần tự khởi tạo class hoặc method.

Các thao tác thường dùng:

~~~java
metadata.isAnnotated("com.example.ConditionalFeature")
~~~

Kiểm tra annotation trực tiếp hoặc meta-annotation có tồn tại.

~~~java
metadata.getAnnotationAttributes(
        "com.example.ConditionalFeature"
);
~~~

Đọc các thuộc tính của annotation, ví dụ giá trị cấu hình được khai báo trên annotation tùy chỉnh.

Nếu condition đặt trên configuration class, metadata mô tả class. Nếu condition đặt trên `@Bean` method, metadata mô tả method đó. Đừng giả định mọi metadata đều là `AnnotationMetadata` của class; method metadata có thể là `MethodMetadata`.

## 4. Quy tắc chọn phase theo dữ liệu cần quan sát

| Câu hỏi mà condition cần trả lời | Phase phù hợp | Lý do |
|---|---|---|
| Profile hiện tại có phải production? | `PARSE_CONFIGURATION` | Đọc từ Environment trước khi parse class |
| Property `app.feature.enabled` có bật không? | `PARSE_CONFIGURATION` | Property đã có trong Environment |
| Class SDK tùy chọn có trên classpath không? | `PARSE_CONFIGURATION` | Classloader có thể kiểm tra trước khi nạp cấu hình |
| Resource bắt buộc có tồn tại không? | `PARSE_CONFIGURATION` | ResourceLoader có thể kiểm tra resource |
| Một bean definition cụ thể đã được đăng ký chưa? | `REGISTER_BEAN` | Cần đợi đến giai đoạn đăng ký bean |
| Một bean definition có thuộc tính/role nhất định không? | `REGISTER_BEAN` | Cần đọc BeanDefinitionRegistry/BeanFactory |
| Một bean instance đã được khởi tạo và có trạng thái runtime gì? | **Không dùng condition** | Condition không được tương tác với bean instances |

Nguyên tắc:

- **Chỉ cần dữ liệu tĩnh/môi trường:** ưu tiên `PARSE_CONFIGURATION`.
- **Cần quan sát bean definitions:** chọn `REGISTER_BEAN`.
- **Cần dữ liệu từ bean instance hoặc gọi service:** chuyển logic sang một thành phần runtime phù hợp, không đưa vào condition.

Đừng chọn `REGISTER_BEAN` chỉ vì nghĩ phase muộn hơn sẽ an toàn hơn. Phase phải phản ánh thời điểm dữ liệu cần thiết đã sẵn sàng.

## 5. Ví dụ 1: PARSE_CONFIGURATION dựa trên property

Giả sử một cấu hình chỉ được nạp trong môi trường production. Tạo condition đọc property `app.mode`.

### 5.1. ProductionModeCondition

Tệp `src/main/java/com/example/condition/ProductionModeCondition.java`:

~~~java
package com.example.condition;

import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class ProductionModeCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String mode = context.getEnvironment()
                .getProperty("app.mode", "");

        return "production".equalsIgnoreCase(mode);
    }
}
~~~

Condition chọn `PARSE_CONFIGURATION` vì chỉ đọc property từ Environment. Nó không cần biết bean nào đã được đăng ký.

### 5.2. Configuration sử dụng condition

Tệp `src/main/java/com/example/condition/ProductionOnlyConfiguration.java`:

~~~java
package com.example.condition;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@Conditional(ProductionModeCondition.class)
public class ProductionOnlyConfiguration {

    @Bean
    ProductionMarker productionMarker() {
        return new ProductionMarker();
    }

    static class ProductionMarker {
    }
}
~~~

Khi `app.mode=production`, configuration class được parse và bean `productionMarker` có thể được đăng ký. Khi property thiếu hoặc có giá trị khác, configuration class bị bỏ qua.

### 5.3. Kiểm thử hai trường hợp

Tệp `src/test/java/com/example/condition/ProductionModeConditionTests.java`:

~~~java
package com.example.condition;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ProductionModeConditionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(
                            ProductionOnlyConfiguration.class
                    );

    @Test
    void includesConfigurationInProductionMode() {
        this.runner
                .withPropertyValues("app.mode=production")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .hasSingleBean(
                                    ProductionOnlyConfiguration
                                            .ProductionMarker.class
                            );
                });
    }

    @Test
    void skipsConfigurationOutsideProductionMode() {
        this.runner
                .withPropertyValues("app.mode=development")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(
                                    ProductionOnlyConfiguration
                                            .ProductionMarker.class
                            );
                });
    }
}
~~~

Kết quả mong đợi:

| Property | Configuration class | Bean |
|---|---|---|
| `app.mode=production` | Được parse | Có `ProductionMarker` |
| `app.mode=development` | Bị bỏ qua | Không có `ProductionMarker` |
| Property thiếu | Bị bỏ qua | Không có `ProductionMarker` |

Đây là ví dụ để hiểu phase. Trong ứng dụng thực tế, nếu chỉ cần kích hoạt theo profile, hãy cân nhắc `@Profile`; nếu chỉ cần bật/tắt bằng property, ưu tiên `@ConditionalOnProperty`. Chỉ viết custom condition khi logic có thêm quy tắc domain mà annotation có sẵn không diễn đạt đủ.

## 6. Ví dụ 2: REGISTER_BEAN dựa trên bean definition

Giả sử starter có hai auto-configuration:

- `PrerequisiteAutoConfiguration` cung cấp bean definition tên `acmePrerequisite`.
- `OptionalFeatureAutoConfiguration` chỉ đăng ký `OptionalFeature` nếu prerequisite đã được đăng ký.

Condition phải kiểm tra **bean definition**, không gọi `getBean()` để khởi tạo prerequisite.

### 6.1. PrerequisiteBeanDefinitionCondition

Tệp `src/main/java/com/example/condition/PrerequisiteBeanDefinitionCondition.java`:

~~~java
package com.example.condition;

import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class PrerequisiteBeanDefinitionCondition
        implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        return context.getRegistry()
                .containsBeanDefinition("acmePrerequisite");
    }
}
~~~

Condition chọn `REGISTER_BEAN` vì câu hỏi cần trả lời là: bean definition có tên `acmePrerequisite` đã được đăng ký chưa?

`containsBeanDefinition` chỉ kiểm tra definition trong registry. Nó không khởi tạo bean và không chứng minh instance đã được tạo thành công. Đây là đúng loại dữ liệu condition cần quan sát.

### 6.2. Auto-configuration cung cấp prerequisite

Tệp `src/main/java/com/example/condition/PrerequisiteAutoConfiguration.java`:

~~~java
package com.example.condition;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class PrerequisiteAutoConfiguration {

    @Bean(name = "acmePrerequisite")
    Prerequisite prerequisite() {
        return new Prerequisite();
    }

    static class Prerequisite {
    }
}
~~~

### 6.3. Auto-configuration cung cấp feature tùy chọn

Tệp `src/main/java/com/example/condition/OptionalFeatureAutoConfiguration.java`:

~~~java
package com.example.condition;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration(after = PrerequisiteAutoConfiguration.class)
public class OptionalFeatureAutoConfiguration {

    @Bean
    @Conditional(PrerequisiteBeanDefinitionCondition.class)
    OptionalFeature optionalFeature() {
        return new OptionalFeature();
    }

    static class OptionalFeature {
    }
}
~~~

`@AutoConfiguration(after = PrerequisiteAutoConfiguration.class)` khai báo thứ tự xử lý auto-configuration. Khi feature được xét, prerequisite auto-configuration đã được xử lý trước theo thứ tự đã khai báo, giúp bean definition cần kiểm tra có mặt trong registry.

Ordering ở đây là ordering của auto-configuration/bean definition. Nó **không** yêu cầu instance prerequisite phải được khởi tạo trước. Khi ứng dụng thực sự lấy bean, dependency graph và lifecycle mới quyết định thứ tự tạo instance.

### 6.4. Kiểm thử có và không có prerequisite

Tệp `src/test/java/com/example/condition/PrerequisiteConditionTests.java`:

~~~java
package com.example.condition;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PrerequisiteConditionTests {

    private final ApplicationContextRunner withPrerequisite =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    OptionalFeatureAutoConfiguration.class,
                                    PrerequisiteAutoConfiguration.class
                            )
                    );

    @Test
    void registersFeatureWhenPrerequisiteDefinitionExists() {
        this.withPrerequisite.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .hasSingleBean(
                            OptionalFeatureAutoConfiguration
                                    .OptionalFeature.class
                    );
        });
    }

    @Test
    void skipsFeatureWhenPrerequisiteDefinitionIsAbsent() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                OptionalFeatureAutoConfiguration.class
                        )
                )
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context)
                            .doesNotHaveBean(
                                    OptionalFeatureAutoConfiguration
                                            .OptionalFeature.class
                            );
                });
    }
}
~~~

`AutoConfigurations.of(...)` nhận các auto-configuration class và áp dụng ordering metadata như `after`. Test thứ nhất cố ý truyền feature trước prerequisite trong danh sách để chứng minh thứ tự annotation được áp dụng. Test thứ hai chỉ đưa feature vào context, nên condition không tìm thấy prerequisite definition và không đăng ký feature.

Kết quả mong đợi:

| Auto-configuration được nạp | Bean definition `acmePrerequisite` | Bean `OptionalFeature` |
|---|---|---|
| Prerequisite + OptionalFeature | Có | Có |
| Chỉ OptionalFeature | Không | Không |

Test này kiểm tra condition và ordering trong một context độc lập. Nó không cần khởi tạo server hoặc chạy toàn bộ ứng dụng.

## 7. Tại sao không được lấy bean instance trong Condition?

`Condition` được đánh giá trong giai đoạn xử lý cấu hình, trước khi toàn bộ singleton beans được khởi tạo. Spring yêu cầu condition tuân theo các giới hạn tương tự `BeanFactoryPostProcessor` và không tương tác với bean instances.

Không làm như sau:

~~~java
@Override
public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata) {

    // Sai: cố lấy bean instance trong lúc condition đang chạy.
    FeatureSettings settings =
            context.getBeanFactory().getBean(FeatureSettings.class);

    return settings.isEnabled();
}
~~~

Lý do:

- Bean có thể chưa được đăng ký hoặc chưa khởi tạo.
- Gọi `getBean()` có thể kích hoạt tạo bean quá sớm.
- Bean có thể phụ thuộc configuration hoặc post-processing chưa hoàn tất.
- Có thể tạo vòng phụ thuộc giữa condition và bean mà condition đang quyết định.
- Kết quả phụ thuộc thứ tự khởi tạo thay vì metadata/cấu hình có thể kiểm tra sớm.

Nếu cần giá trị cấu hình, đọc `Environment` hoặc metadata của annotation. Nếu cần biết bean đã được đăng ký, đọc `BeanDefinitionRegistry` ở `REGISTER_BEAN`. Nếu cần gọi service hoặc đọc trạng thái runtime, thực hiện trong bean, application event listener hoặc logic nghiệp vụ sau khi context đã khởi tạo.

## 8. Thứ tự đăng ký và giới hạn của REGISTER_BEAN

`REGISTER_BEAN` bảo đảm các configuration classes đã được parse, nhưng không có nghĩa mọi bean definition của mọi configuration đã được đăng ký trước khi condition của bạn chạy.

Vì vậy, nếu condition phụ thuộc một auto-configuration cụ thể:

1. Dùng `@AutoConfiguration(after = ...)` hoặc `before` để khai báo thứ tự phù hợp.
2. Kiểm tra đúng bean name hoặc bean type trong registry.
3. Tránh dựa vào thứ tự tình cờ của component scan hay thứ tự khai báo method.
4. Viết test có prerequisite và test không có prerequisite.
5. Nếu có thể, dùng condition có sẵn của Spring Boot như `@ConditionalOnBean` thay vì tự viết registry condition.

Không nên dùng `@DependsOn` để giải quyết vấn đề này. `@DependsOn` điều khiển thứ tự khởi tạo bean instances, còn condition cần xác định bean definition có được đăng ký hay không. Hai khái niệm thuộc hai giai đoạn khác nhau.

### 8.1. User configuration và auto-configuration

Spring Boot thường xử lý user bean definitions trước auto-configuration. Vì vậy các bean conditions trong auto-configuration có thể nhường chỗ cho bean do ứng dụng cung cấp.

Tuy nhiên, một custom condition kiểm tra tên bean cụ thể cần xác định rõ:

- Bean có thể được khai báo bằng nhiều tên/alias không?
- Có cần kiểm tra bean definition theo type thay vì tên không?
- Có cần xét parent context không?
- Có cần loại trừ một số bean definition không?
- Auto-configuration cung cấp prerequisite có được order trước không?

Nếu chỉ cần kiểm tra sự hiện diện của bean theo type hoặc name, `@ConditionalOnBean`/`@ConditionalOnMissingBean` thường là lựa chọn dễ đọc và ít code hơn. Custom registry condition phù hợp khi quy tắc domain phức tạp hơn hoặc cần kiểm tra metadata của definition.

## 9. Dữ liệu nào an toàn để quan sát trong từng phase?

| Dữ liệu | PARSE_CONFIGURATION | REGISTER_BEAN | Lưu ý |
|---|---|---|---|
| Environment property | Có | Có | Giá trị hiệu lực đã được chuẩn bị trong Environment |
| Active profile | Có | Có | Dùng Environment |
| Classpath | Có | Có | Dùng ClassLoader; tránh nạp class tùy chọn bằng chữ ký không được bảo vệ |
| Resource | Có | Có | Dùng ResourceLoader |
| Annotation metadata | Có | Có | Metadata mô tả class hoặc method đang được xét |
| Bean definition registry | Có thể truy cập nhưng chưa hoàn chỉnh | Phù hợp hơn | Chỉ dựa vào definition đã được đăng ký |
| BeanFactory metadata | Có thể chưa đầy đủ | Có thể hữu ích | getBeanFactory() có thể null |
| Bean instance | Không | Không | Condition không được lấy hoặc khởi tạo bean |
| Database/network/service response | Không | Không | Không thực hiện I/O hoặc gọi service trong condition |

Bảng “Có” chỉ nói API có thể được truy cập; không có nghĩa dữ liệu đã đầy đủ hoặc có thể dùng để kết luận mọi thứ ở phase đó. Chọn phase theo thời điểm dữ liệu cần thiết thực sự sẵn sàng.

## 10. Những sai lầm phổ biến

- **Chọn PARSE_CONFIGURATION để kiểm tra bean definition:** registry có thể chưa chứa bean mà condition đang tìm. Chuyển sang REGISTER_BEAN nếu quy tắc thật sự dựa trên definition.
- **Chọn REGISTER_BEAN cho điều kiện profile đơn giản:** không cần đợi đến phase muộn; dùng PARSE_CONFIGURATION hoặc annotation có sẵn như `@Profile`.
- **Nghĩ REGISTER_BEAN nghĩa là bean instance đã tồn tại:** phase này liên quan đăng ký definition, không phải khởi tạo instance.
- **Gọi `getBean()` trong `matches()`:** có thể tạo bean quá sớm và gây vòng phụ thuộc.
- **Dùng `BeanFactoryPostProcessor` để lấy dữ liệu runtime:** condition và post-processor không phải nơi gọi service nghiệp vụ.
- **Cho rằng mọi bean definition đều có sẵn khi REGISTER_BEAN:** thứ tự xử lý vẫn có ý nghĩa; khai báo auto-configuration ordering nếu cần.
- **Dùng thứ tự method làm hợp đồng:** không dựa vào việc một `@Bean` method tình cờ được xử lý trước method khác.
- **Không phân biệt metadata class và method:** `AnnotatedTypeMetadata` có thể đại diện cho configuration class hoặc bean method.
- **Dùng custom Condition cho quy tắc đơn giản:** ưu tiên `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnResource` hoặc `@Profile` khi phù hợp.
- **Condition có side effect:** không ghi file, gọi API, kết nối database, thay đổi registry hoặc log dữ liệu nhạy cảm trong `matches()`.
- **Trả về kết quả dựa trên dữ liệu không ổn định:** condition nên nhanh, xác định và có thể lặp lại; không dựa trên thời gian, random hoặc trạng thái bên ngoài biến động.
- **Không test cả hai phía:** cần có test match và no-match để chứng minh phase được chọn đúng.

## 11. Quy trình chọn và triển khai phase

1. Viết thành câu hỏi mà condition phải trả lời, ví dụ “property app.mode có phải production?” hoặc “bean definition acmePrerequisite đã tồn tại?”.
2. Xác định dữ liệu cần đọc: Environment, ClassLoader, ResourceLoader, annotation metadata hay bean registry.
3. Xác định thời điểm dữ liệu đó có sẵn. Environment/classpath/resource thường phù hợp với PARSE_CONFIGURATION; bean definition cần REGISTER_BEAN.
4. Nếu chỉ cần logic tiêu chuẩn, tìm annotation condition có sẵn trước khi viết class mới.
5. Implement `ConfigurationCondition` và trả về phase phù hợp.
6. Trong `matches()`, chỉ đọc context và metadata; không lấy bean instance, không thực hiện I/O.
7. Nếu dựa vào bean definition của auto-configuration khác, khai báo ordering rõ ràng.
8. Viết test match/no-match với `ApplicationContextRunner`.
9. Xác nhận context khởi động, bean definition xuất hiện đúng hoặc bị bỏ qua đúng như dự kiến.
10. Khi điều tra, phân biệt condition không match với lỗi khởi tạo bean: một condition trả false thường chỉ bỏ qua component, không tự nó làm context thất bại.

## 12. Câu hỏi tự kiểm tra

1. `PARSE_CONFIGURATION` được đánh giá khi nào? **Khi Spring parse một `@Configuration` class.**
2. Nếu condition class-level không match ở PARSE_CONFIGURATION thì sao? **Configuration class không được thêm vào quá trình xử lý.**
3. `REGISTER_BEAN` phù hợp khi cần kiểm tra điều gì? **Bean definition đã được đăng ký trong registry hay chưa, thường ở condition trên bean method.**
4. REGISTER_BEAN có nghĩa mọi bean instance đã được tạo không? **Không.** Đây là giai đoạn đăng ký bean definitions.
5. `ConditionContext` lấy Environment bằng method nào? **`getEnvironment()`.**
6. Muốn kiểm tra bean definition theo tên dùng API nào? **`context.getRegistry().containsBeanDefinition(name)`.**
7. Vì sao không được gọi `getBean()` trong `matches()`? **Condition chạy trước khi bean instances được khởi tạo; lấy bean có thể kích hoạt tạo bean quá sớm và gây vòng phụ thuộc.**
8. Khi auto-configuration B cần bean definition từ auto-configuration A, cần làm gì? **Khai báo ordering như `@AutoConfiguration(after = A.class)` và kiểm thử.**
9. Nếu chỉ kiểm tra property boolean, có cần custom Condition không? **Thường không.** Dùng `@ConditionalOnProperty` phù hợp hơn.
10. `AnnotatedTypeMetadata` đại diện cho những loại element nào? **Configuration class hoặc method đang được kiểm tra.**
11. Nếu cần kiểm tra trạng thái của một service sau khi khởi tạo, chọn phase nào? **Không phase nào.** Chuyển kiểm tra sang bean/event/runtime logic.
12. `@DependsOn` có thay thế `@AutoConfiguration(after=...)` khi condition cần bean definition không? **Không.** `@DependsOn` điều khiển khởi tạo instance; `after` điều khiển thứ tự auto-configuration/definition processing.

## 13. Tài liệu tham khảo chính thức

- [Spring Framework 6.1 — ConfigurationCondition API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html): hợp đồng getConfigurationPhase() và hai phase.
- [Spring Framework 6.1 — ConfigurationPhase API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html): ý nghĩa của PARSE_CONFIGURATION và REGISTER_BEAN.
- [Spring Framework 6.1 — Condition API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html): matches(), điều kiện đăng ký và giới hạn không tương tác với bean instances.
- [Spring Framework 6.1 — ConditionContext API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html): Environment, BeanDefinitionRegistry, BeanFactory, ResourceLoader và ClassLoader.
- [Spring Framework 6.1 — AnnotatedTypeMetadata API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/type/AnnotatedTypeMetadata.html): đọc annotation metadata của class và method.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): điều kiện auto-configuration, bean conditions và ordering.
- [Spring Boot 3.3 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): dựng context độc lập để kiểm thử condition và bean registration.
