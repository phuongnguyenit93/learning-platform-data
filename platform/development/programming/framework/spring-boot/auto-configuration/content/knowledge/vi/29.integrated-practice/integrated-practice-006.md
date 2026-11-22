# Tạo hai lớp tự cấu hình có quan hệ trước sau và viết kiểm thử chứng minh

## Mục tiêu bài học

Khi một thư viện Spring Boot có nhiều auto-configuration, một cấu hình có thể cần được xử lý trước cấu hình khác. Ví dụ, cấu hình nền tạo bean hạ tầng; cấu hình tính năng chỉ đăng ký bean nếu bean hạ tầng đã được khai báo.

Spring Boot cung cấp các cách khai báo quan hệ thứ tự:

- `@AutoConfiguration(before = ...)`
- `@AutoConfiguration(after = ...)`
- `beforeName` và `afterName` khi muốn tham chiếu bằng fully qualified class name.
- Hai annotation chuyên biệt `@AutoConfigureBefore` và `@AutoConfigureAfter`.
- `@AutoConfigureOrder` khi cần thứ tự tổng quát mà không tạo quan hệ trực tiếp giữa hai lớp.

Bài thực hành này xây dựng hai lớp auto-configuration, trong đó `ZetaBaseAutoConfiguration` cung cấp một bean nền tảng và `AlphaFeatureAutoConfiguration` cần được xử lý sau lớp đó. Tên lớp được chọn có chủ đích: theo thứ tự tên, Alpha đứng trước Zeta. Kiểm thử sẽ đưa candidate vào runner theo thứ tự ngược và chứng minh rằng quan hệ `after` vẫn khiến bean phụ thuộc được đăng ký.

Sau bài học, bạn có thể:

- Giải thích mục đích của ordering giữa các auto-configuration.
- Phân biệt `before`, `after`, `beforeName` và `afterName`.
- Tạo hai lớp auto-configuration có dependency về thứ tự.
- Dùng `@ConditionalOnBean` để thể hiện một cấu hình phụ thuộc vào bean do cấu hình khác cung cấp.
- Viết test bằng `ApplicationContextRunner` và `AutoConfigurations.of(...)`.
- Phân biệt thứ tự đăng ký bean definitions với thứ tự khởi tạo bean instances.
- Đăng ký các lớp trong `AutoConfiguration.imports` và kiểm tra artifact sau khi build.

## 1. Bài toán: cấu hình tính năng cần cấu hình nền tảng

Giả sử thư viện Acme có hai phần:

1. Cấu hình nền tảng tạo `BaseMarker`, đại diện cho một dịch vụ nền hoặc hạ tầng đã sẵn sàng.
2. Cấu hình tính năng tạo `FeatureMarker`, nhưng chỉ khi `BaseMarker` đã có trong bean definitions.

Mối quan hệ mong muốn:

~~~text
ZetaBaseAutoConfiguration
          |
          | đăng ký BaseMarker
          v
AlphaFeatureAutoConfiguration
          |
          | @ConditionalOnBean(BaseMarker.class)
          v
FeatureMarker
~~~

Nếu cấu hình tính năng được xử lý trước, condition trên bean method có thể được đánh giá khi bean definition của `BaseMarker` chưa được đăng ký. Khi đó `FeatureMarker` không được tạo.

Ta cần khai báo rằng cấu hình tính năng phải được áp dụng sau cấu hình nền tảng. Đây là thứ tự xử lý auto-configuration, không phải một yêu cầu sắp xếp thủ công danh sách bean.

## 2. Ordering có ý nghĩa gì?

Spring Boot đọc các auto-configuration candidate rồi sắp xếp chúng dựa trên các metadata ordering. Các quan hệ trước/sau tạo thành một đồ thị phụ thuộc về thứ tự.

Với hai lớp:

~~~java
@AutoConfiguration
class ZetaBaseAutoConfiguration {
}

@AutoConfiguration(after = ZetaBaseAutoConfiguration.class)
class AlphaFeatureAutoConfiguration {
}
~~~

Ý nghĩa là `ZetaBaseAutoConfiguration` phải được áp dụng trước `AlphaFeatureAutoConfiguration`.

Có thể diễn đạt cùng một quan hệ theo chiều ngược lại:

~~~java
@AutoConfiguration(before = AlphaFeatureAutoConfiguration.class)
class ZetaBaseAutoConfiguration {
}
~~~

Hai cách trên biểu diễn cùng một cạnh ordering. Trong một cặp cấu hình, hãy chọn một phía để khai báo quan hệ rõ ràng; không cần khai báo lặp cả `before` lẫn `after` nếu chúng mô tả cùng một yêu cầu.

### 2.1. Các thuộc tính trên @AutoConfiguration

| Thuộc tính | Ý nghĩa |
| --- | --- |
| `before` | Lớp hiện tại phải được áp dụng trước các lớp được chỉ định |
| `beforeName` | Giống `before`, nhưng nhận FQCN dạng chuỗi |
| `after` | Lớp hiện tại phải được áp dụng sau các lớp được chỉ định |
| `afterName` | Giống `after`, nhưng nhận FQCN dạng chuỗi |

Ví dụ:

~~~java
@AutoConfiguration(
        before = MetricsAutoConfiguration.class,
        after = FoundationAutoConfiguration.class)
public class AcmeFeatureAutoConfiguration {
}
~~~

Có thể khai báo nhiều lớp trong một thuộc tính:

~~~java
@AutoConfiguration(
        after = {
                FoundationAutoConfiguration.class,
                ClientAutoConfiguration.class
        })
public class AcmeFeatureAutoConfiguration {
}
~~~

Lớp hiện tại chỉ được áp dụng sau các auto-configuration được liệt kê.

### 2.2. Khi nào dùng beforeName hoặc afterName?

Dùng thuộc tính dạng tên khi không muốn tạo compile-time dependency trực tiếp tới auto-configuration được tham chiếu, ví dụ hai module được phát hành độc lập hoặc dependency là optional.

~~~java
@AutoConfiguration(
        afterName = "com.vendor.foundation.FoundationAutoConfiguration")
public class AcmeVendorIntegrationAutoConfiguration {
}
~~~

Tên phải là FQCN chính xác. Nếu package hoặc class được đổi tên, cần rà soát các chuỗi ordering và migration metadata tương ứng.

### 2.3. Annotation chuyên biệt

Có thể dùng `@AutoConfigureBefore` và `@AutoConfigureAfter` thay cho thuộc tính trên `@AutoConfiguration`:

~~~java
@AutoConfigureAfter(FoundationAutoConfiguration.class)
@AutoConfiguration
public class AcmeFeatureAutoConfiguration {
}
~~~

~~~java
@AutoConfigureBefore(AcmeFeatureAutoConfiguration.class)
@AutoConfiguration
public class FoundationAutoConfiguration {
}
~~~

Đây là cách khai báo tương đương về mục đích. Với code mới, dùng thuộc tính `before`/`after` trên `@AutoConfiguration` thường gọn và dễ đọc.

### 2.4. @AutoConfigureOrder dùng cho trường hợp nào?

`@AutoConfigureOrder` cung cấp thứ tự tổng quát cho auto-configuration, tương tự cơ chế `@Order`. Dùng nó khi cần đặt vị trí tương đối rộng mà không có một class cụ thể làm dependency.

Nếu cấu hình B cần được xử lý sau đúng cấu hình A, `after = A.class` mô tả hợp đồng rõ hơn một con số order. Không dùng `@AutoConfigureOrder` như cách thay thế tùy tiện cho một quan hệ trực tiếp.

## 3. Ordering không sắp xếp thời điểm tạo mọi bean instance

Đây là điểm quan trọng nhất khi thiết kế auto-configuration.

Ordering chỉ ảnh hưởng thứ tự **các configuration được áp dụng và bean definitions được đăng ký**. Nó không điều khiển thứ tự khởi tạo tất cả singleton bean sau đó.

Ví dụ, nếu `FeatureService` cần `BaseService`, hãy thể hiện dependency bằng constructor injection hoặc tham số của `@Bean` method:

~~~java
@Bean
FeatureService featureService(BaseService baseService) {
    return new FeatureService(baseService);
}
~~~

Spring sẽ tạo dependency cần thiết theo bean dependency graph.

`@DependsOn` có thể biểu đạt thứ tự khởi tạo giữa các bean khi có yêu cầu lifecycle cụ thể, nhưng không thay thế ordering giữa auto-configuration. Đặc biệt, `@DependsOn` không làm cho bean definition xuất hiện sớm hơn để một `@ConditionalOnBean` được đánh giá trước đó có thể nhìn thấy nó.

Tóm lại:

| Cơ chế | Điều khiển |
| --- | --- |
| `@AutoConfiguration(after = ...)` | Thứ tự áp dụng auto-configuration và đăng ký bean definitions |
| Constructor injection / tham số `@Bean` | Quan hệ dependency khi tạo bean instances |
| `@DependsOn` | Thứ tự khởi tạo bean instances trong trường hợp cần chỉ định tường minh |
| `@ConditionalOnBean` | Có đăng ký thành phần hay không dựa trên bean definitions đã được xử lý |

## 4. Vì sao thứ tự quan trọng với @ConditionalOnBean?

`@ConditionalOnBean` kiểm tra các bean definitions đã được xử lý tại thời điểm condition được đánh giá. Nó không đợi đến khi mọi auto-configuration trong ứng dụng được xử lý xong rồi đánh giá lại.

Ví dụ:

~~~java
@Bean
@ConditionalOnBean(BaseMarker.class)
FeatureMarker featureMarker(BaseMarker baseMarker) {
    return new FeatureMarker(baseMarker.value());
}
~~~

Nếu cấu hình nền đã được xử lý trước, bean definition của `BaseMarker` có thể được condition nhìn thấy và `FeatureMarker` được đăng ký.

Nếu cấu hình nền chưa được xử lý, condition có thể không khớp. Việc sau đó có một `BaseMarker` xuất hiện không khiến Spring tự quay lại đăng ký bean method đã bị bỏ qua.

Spring Boot khuyến nghị dùng `@ConditionalOnBean` và `@ConditionalOnMissingBean` trong auto-configuration vì auto-configuration được xử lý sau các bean definitions do người dùng khai báo. Khi một auto-configuration phụ thuộc vào bean do một auto-configuration khác cung cấp, hãy khai báo ordering tương ứng.

## 5. Xây dựng ví dụ hoàn chỉnh

Ta dùng Java 17+, Spring Boot 3.3.x, Gradle và JUnit 5. Ví dụ gồm hai auto-configuration và hai marker record.

### 5.1. Cấu trúc thư mục

~~~text
acme-autoconfigure/
  build.gradle
  src/
    main/
      java/
        com/acme/autoconfigure/
          OrderingTypes.java
          ZetaBaseAutoConfiguration.java
          AlphaFeatureAutoConfiguration.java
      resources/
        META-INF/spring/
          org.springframework.boot.autoconfigure.AutoConfiguration.imports
    test/
      java/
        com/acme/autoconfigure/
          AutoConfigurationOrderingTests.java
~~~

Hai lớp auto-configuration là top-level classes. Chúng được đăng ký qua imports file, không dựa vào component scan.

### 5.2. Các kiểu dữ liệu dùng chung

**Tệp:** `src/main/java/com/acme/autoconfigure/OrderingTypes.java`

~~~java
package com.acme.autoconfigure;

public final class OrderingTypes {

    private OrderingTypes() {
    }

    public record BaseMarker(String value) {
    }

    public record FeatureMarker(String baseValue) {
    }
}
~~~

Hai record chỉ đóng vai trò marker để test có thể kiểm tra bean registration và dữ liệu được truyền qua dependency injection.

### 5.3. Auto-configuration nền tảng

**Tệp:** `src/main/java/com/acme/autoconfigure/ZetaBaseAutoConfiguration.java`

~~~java
package com.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ZetaBaseAutoConfiguration {

    @Bean
    public OrderingTypes.BaseMarker baseMarker() {
        return new OrderingTypes.BaseMarker("zeta-base");
    }
}
~~~

Lớp này cung cấp bean `BaseMarker`. Nó không cần biết cấu hình tính năng nào sẽ sử dụng bean đó.

Việc tách cấu hình nền tảng khỏi cấu hình tính năng giúp mỗi lớp có một trách nhiệm rõ ràng.

### 5.4. Auto-configuration tính năng phụ thuộc vào cấu hình nền

**Tệp:** `src/main/java/com/acme/autoconfigure/AlphaFeatureAutoConfiguration.java`

~~~java
package com.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = ZetaBaseAutoConfiguration.class)
public class AlphaFeatureAutoConfiguration {

    @Bean
    @ConditionalOnBean(OrderingTypes.BaseMarker.class)
    public OrderingTypes.FeatureMarker featureMarker(
            OrderingTypes.BaseMarker baseMarker) {

        return new OrderingTypes.FeatureMarker(baseMarker.value());
    }
}
~~~

Có hai chi tiết cần chú ý:

1. `after = ZetaBaseAutoConfiguration.class` yêu cầu cấu hình nền được áp dụng trước cấu hình tính năng.
2. `@ConditionalOnBean(BaseMarker.class)` chỉ đăng ký bean tính năng khi bean nền đã có trong các bean definitions được xử lý.

Tham số `BaseMarker` của bean method còn thể hiện dependency thực tế. Sau khi bean definition được đăng ký, Spring inject instance nền khi tạo `FeatureMarker`.

### 5.5. Đăng ký cả hai lớp trong imports file

**Tệp:** `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

~~~text
com.acme.autoconfigure.AlphaFeatureAutoConfiguration
com.acme.autoconfigure.ZetaBaseAutoConfiguration
~~~

File được cố ý ghi Alpha trước Zeta. Thứ tự dòng trong file không phải hợp đồng ordering. Spring Boot sử dụng metadata `before`/`after` để sắp xếp candidate.

Không đăng ký cùng một auto-configuration bằng component scan hoặc bằng một cơ chế import trùng lặp khác. Auto-configuration cần được phát hiện qua imports file theo convention của Spring Boot.

## 6. Viết kiểm thử chứng minh quan hệ trước sau

Dùng `ApplicationContextRunner` để tạo context nhỏ và chỉ nạp hai auto-configuration cần kiểm tra.

Điểm quan trọng của test:

- Candidate được truyền vào `AutoConfigurations.of(...)` theo thứ tự Alpha rồi Zeta.
- Tên lớp cũng khiến Alpha đứng trước Zeta theo thứ tự tên thông thường.
- Metadata `after = ZetaBaseAutoConfiguration.class` yêu cầu Boot xử lý Zeta trước Alpha.
- Alpha chỉ tạo `FeatureMarker` khi `BaseMarker` đã được đăng ký.

**Tệp:** `src/test/java/com/acme/autoconfigure/AutoConfigurationOrderingTests.java`

~~~java
package com.acme.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderingTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            AlphaFeatureAutoConfiguration.class,
                            ZetaBaseAutoConfiguration.class));

    @Test
    void baseConfigurationIsAppliedBeforeDependentFeature() {
        this.contextRunner.run(context -> {
            assertThat(context)
                    .hasSingleBean(OrderingTypes.BaseMarker.class);

            assertThat(context)
                    .hasSingleBean(OrderingTypes.FeatureMarker.class);

            assertThat(context.getBean(OrderingTypes.FeatureMarker.class)
                    .baseValue())
                    .isEqualTo("zeta-base");
        });
    }

    @Test
    void featureIsNotCreatedWhenBaseConfigurationIsAbsent() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        AlphaFeatureAutoConfiguration.class))
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(OrderingTypes.BaseMarker.class);

                    assertThat(context)
                            .doesNotHaveBean(OrderingTypes.FeatureMarker.class);
                });
    }
}
~~~

### 6.1. Test thứ nhất chứng minh điều gì?

Test nạp hai candidate theo thứ tự:

~~~java
AutoConfigurations.of(
        AlphaFeatureAutoConfiguration.class,
        ZetaBaseAutoConfiguration.class)
~~~

Nhưng cấu hình Alpha khai báo:

~~~java
@AutoConfiguration(after = ZetaBaseAutoConfiguration.class)
~~~

Khi runner áp dụng các auto-configuration, Spring Boot sắp xếp chúng theo metadata ordering. Zeta được áp dụng trước Alpha dù candidate được truyền theo thứ tự ngược.

Khi Alpha được xử lý:
- Bean definition `BaseMarker` đã được đăng ký.
- `@ConditionalOnBean(BaseMarker.class)` khớp.
- Bean definition `FeatureMarker` được đăng ký.
- Khi context tạo bean, tham số `BaseMarker` được inject vào bean method.
- Giá trị `zeta-base` được truyền vào `FeatureMarker`.

Assertion kiểm tra cả hai bean và dữ liệu được truyền, nên test chứng minh condition đã khớp và dependency injection hoạt động.

### 6.2. Test thứ hai chứng minh điều gì?

Test thứ hai chỉ nạp `AlphaFeatureAutoConfiguration`, không nạp cấu hình nền.

Khi đó:
- Không có `BaseMarker`.
- `@ConditionalOnBean(BaseMarker.class)` không khớp.
- `FeatureMarker` không được đăng ký.

Test này chứng minh condition thực sự bảo vệ bean tính năng; nó không được tạo chỉ vì auto-configuration class đã được nạp.

### 6.3. Vì sao không chỉ assert annotation có mặt?

Một test reflection kiểu:

~~~java
assertThat(AlphaFeatureAutoConfiguration.class)
        .hasAnnotation(AutoConfiguration.class);
~~~

chỉ xác nhận class có annotation. Nó không chứng minh:
- Spring Boot đã đọc ordering metadata.
- Candidate được sắp xếp đúng.
- Bean condition được đánh giá sau cấu hình nền.
- Bean definition được đăng ký.
- Dependency injection tạo ra kết quả đúng.

Dùng ApplicationContextRunner giúp kiểm tra hành vi thật của auto-configuration trong Spring container.

## 7. Chạy test với Gradle

Ví dụ cấu hình cho module dùng Spring Boot 3.3.x. Version có thể được quản lý bằng Spring Boot plugin hoặc BOM của dự án.

**Tệp:** `build.gradle`

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy riêng test:

~~~bash
# Linux/macOS
./gradlew test --tests "com.acme.autoconfigure.AutoConfigurationOrderingTests"

# Windows
gradlew.bat test --tests "com.acme.autoconfigure.AutoConfigurationOrderingTests"
~~~

**Kết quả mong đợi:** hai test hoàn tất và pass:
- Cấu hình nền được áp dụng trước cấu hình tính năng dù candidate được truyền theo thứ tự ngược.
- Tính năng không được tạo khi cấu hình nền không được nạp.

Test không in nội dung ra stdout. Gradle/JUnit báo cáo số test pass/fail theo cấu hình logging của dự án.

## 8. Biến thể dùng before thay cho after

Ví dụ chính đặt ordering ở lớp phụ thuộc:

~~~java
@AutoConfiguration(after = ZetaBaseAutoConfiguration.class)
public class AlphaFeatureAutoConfiguration {
}
~~~

Có thể đặt cùng quan hệ ở lớp nền:

~~~java
@AutoConfiguration(before = AlphaFeatureAutoConfiguration.class)
public class ZetaBaseAutoConfiguration {
}
~~~

Chỉ cần một trong hai khai báo để biểu đạt cùng quan hệ. Nếu đặt cả hai, hãy chắc chắn chúng nhất quán và không tạo chu trình ordering.

Khi lớp tham chiếu không nên là compile-time dependency, dùng tên:

~~~java
@AutoConfiguration(
        beforeName = "com.acme.feature.AlphaFeatureAutoConfiguration")
public class ZetaBaseAutoConfiguration {
}
~~~

Hoặc:

~~~java
@AutoConfiguration(
        afterName = "com.acme.foundation.ZetaBaseAutoConfiguration")
public class AlphaFeatureAutoConfiguration {
}
~~~

Dùng tên chuỗi cần cẩn thận hơn vì trình biên dịch không kiểm tra package/class name. Hãy có test hoặc kiểm tra metadata để phát hiện lỗi chính tả và rename.

## 9. Những lưu ý khi có nhiều auto-configuration

### 9.1. Ordering là quan hệ tương đối

Nếu A cần trước B và B cần trước C, khai báo các cạnh cần thiết:

~~~text
A -> B -> C
~~~

Không cần gán số order riêng cho từng lớp nếu các quan hệ trực tiếp đã mô tả đầy đủ dependency.

### 9.2. Tránh chu trình

Không khai báo đồng thời:
- A before B.
- B before C.
- C before A.

Các quan hệ này tạo chu trình và không thể thỏa mãn cùng lúc. Thiết kế lại trách nhiệm hoặc tách phần dùng chung thành một auto-configuration nền.

### 9.3. Không phụ thuộc thứ tự tình cờ của imports file

Danh sách trong `AutoConfiguration.imports` dùng để xác định candidate. Đừng dùng vị trí dòng để biểu đạt thứ tự cần thiết. Hãy khai báo `before`/`after` rõ ràng và kiểm thử.

### 9.4. Conditions chỉ thấy những bean definitions đã được xử lý

`@ConditionalOnBean` và `@ConditionalOnMissingBean` không chờ tất cả configuration được xử lý xong. Chúng dựa trên thông tin có tại thời điểm đánh giá. Đây là lý do ordering có thể quan trọng khi một auto-configuration phụ thuộc bean do auto-configuration khác cung cấp.

### 9.5. User configuration thường được xử lý trước auto-configuration

Một lợi ích của auto-configuration là user có thể cung cấp bean tùy chỉnh và để default bean back off:

~~~java
@Bean
@ConditionalOnMissingBean(BaseClient.class)
BaseClient baseClient() {
    return new DefaultBaseClient();
}
~~~

Spring Boot bảo đảm auto-configuration được áp dụng sau các user-defined bean definitions. Vì vậy, missing-bean condition trong auto-configuration là một extension mechanism phù hợp.

### 9.6. Ordering không phải component scanning

Auto-configuration phải được liệt kê trong imports file. Không dùng `@ComponentScan` để tìm các auto-configuration class. Với cấu hình hỗ trợ bổ sung, dùng `@Import` tường minh khi cần.

## 10. Chẩn đoán khi test không pass

Nếu test thứ nhất không có `FeatureMarker`, kiểm tra:

1. `AlphaFeatureAutoConfiguration` có khai báo `after = ZetaBaseAutoConfiguration.class` không?
2. Hai class có thực sự được đưa vào `AutoConfigurations.of(...)` không?
3. `ZetaBaseAutoConfiguration` có bean method trả về đúng kiểu `OrderingTypes.BaseMarker` không?
4. Condition có kiểm tra đúng kiểu đó không?
5. Bean method có bị condition khác loại không?
6. Có dependency version không tương thích làm annotation/runner không hoạt động như dự kiến không?
7. Test có đang dùng `AutoConfigurations.of` để áp dụng candidate như một auto-configuration không?

Có thể bật Condition Evaluation Report trong runner:

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .withConfiguration(AutoConfigurations.of(
                AlphaFeatureAutoConfiguration.class,
                ZetaBaseAutoConfiguration.class))
        .run(context -> {
            // Assertions.
        });
~~~

Report giúp xem `@ConditionalOnBean` khớp hay không và lý do. Trong ví dụ thực tế, thêm import cho `ConditionEvaluationReportLoggingListener` và `LogLevel`:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

Nếu bean nền không xuất hiện, kiểm tra condition và bean definitions của lớp nền trước khi điều tra phần phụ thuộc.

## 11. Kiểm tra imports file trong JAR

ApplicationContextRunner với `AutoConfigurations.of(...)` kiểm tra ordering của các class được cung cấp trực tiếp. Nó không tự chứng minh JAR đã đóng gói imports file chính xác.

Sau khi build:

~~~bash
jar tf build/libs/acme-autoconfigure-1.0.0.jar
~~~

Xác nhận có resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Đọc nội dung và xác nhận cả hai FQCN đều có:

~~~text
com.acme.autoconfigure.AlphaFeatureAutoConfiguration
com.acme.autoconfigure.ZetaBaseAutoConfiguration
~~~

Để kiểm tra discovery từ imports file, bổ sung một smoke test chạy qua `@EnableAutoConfiguration` trong sample application hoặc test integration của artifact. Đây là lớp kiểm tra khác với unit-style runner test:
- Runner test kiểm tra behavior và ordering của các candidate được nạp.
- Smoke test kiểm tra resource discovery trong classpath/JAR thực tế.

## 12. Lỗi thường gặp

1. **Dựa vào thứ tự dòng trong imports file.** Candidate có thể được sắp xếp lại; khai báo before/after rõ ràng.
2. **Cho rằng thứ tự truyền vào AutoConfigurations.of là hợp đồng ordering.** Dùng metadata ordering để mô tả quan hệ.
3. **Dùng @Order trên bean thay cho @AutoConfiguration(after=...).** @Order không biểu đạt thứ tự xử lý auto-configuration.
4. **Dùng @DependsOn để sửa @ConditionalOnBean không khớp.** DependsOn điều khiển bean initialization, không làm bean definition xuất hiện sớm hơn trong lúc condition được đánh giá.
5. **Nhầm ordering với dependency injection.** Ordering sắp xếp cấu hình; constructor/bean method parameter biểu đạt dependency giữa instance.
6. **Đặt @ConditionalOnBean ở cấu hình thường được xử lý quá sớm.** Bean definitions cần tìm có thể chưa được xử lý; ưu tiên đặt bean conditions trong auto-configuration.
7. **Thiếu return type cụ thể trên @Bean method.** Condition dựa vào type information có sẵn; khai báo return type đủ cụ thể.
8. **Dùng class literal cho dependency tùy chọn không phù hợp.** Cân nhắc beforeName/afterName nếu không muốn compile-time dependency.
9. **Gõ sai FQCN trong beforeName/afterName.** Chuỗi không được compiler kiểm tra; thêm test.
10. **Khai báo ordering hai chiều mâu thuẫn.** Tránh chu trình hoặc cạnh ngược nhau.
11. **Dùng @AutoConfigureOrder cho một dependency trực tiếp.** Dùng before/after để thể hiện quan hệ giữa hai class cụ thể.
12. **Chỉ kiểm tra annotation bằng reflection.** Test context mới chứng minh bean condition và ordering thực tế.
13. **Dùng AutoConfigurations.of rồi kết luận imports file đúng.** Kiểm tra JAR resource riêng hoặc smoke test qua @EnableAutoConfiguration.
14. **Đưa auto-configuration vào component scan.** Đăng ký candidate qua imports file theo convention.
15. **Cho rằng ordering quyết định thứ tự tạo singleton.** Bean dependency graph và lifecycle mới quyết định thời điểm tạo instance.

## 13. Checklist review hai lớp auto-configuration

### Thiết kế

- [ ] Mỗi auto-configuration có một trách nhiệm rõ.
- [ ] Bean nền được khai báo trong lớp nền.
- [ ] Bean phụ thuộc có condition phù hợp.
- [ ] Quan hệ before/after được khai báo ở một phía rõ ràng.
- [ ] Không tạo chu trình ordering.
- [ ] Bean method có return type và parameter type đủ cụ thể.

### Registration

- [ ] Cả hai class có `@AutoConfiguration`.
- [ ] Cả hai FQCN được liệt kê trong imports file.
- [ ] Không dựa vào thứ tự dòng trong resource.
- [ ] Không dùng component scan để phát hiện auto-configuration.

### Kiểm thử

- [ ] Runner nạp cả hai candidate.
- [ ] Candidate được truyền theo thứ tự ngược để tránh phụ thuộc input order.
- [ ] Test xác nhận bean nền xuất hiện.
- [ ] Test xác nhận bean phụ thuộc xuất hiện khi ordering đúng.
- [ ] Test xác nhận bean phụ thuộc vắng mặt khi không có bean nền.
- [ ] Test kiểm tra dữ liệu dependency được inject.
- [ ] JAR chứa imports file đúng.
- [ ] Có smoke test discovery nếu cần xác minh artifact end-to-end.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** `@AutoConfiguration(after = BaseAutoConfiguration.class)` có nghĩa gì?

**Đáp án:** Auto-configuration hiện tại phải được áp dụng sau BaseAutoConfiguration; các bean definitions của cấu hình nền được xử lý trước cấu hình hiện tại.

**Câu 2.** `before` và `after` có thể biểu diễn cùng một quan hệ không?

**Đáp án:** Có. A before B tương đương B after A. Chọn một phía để khai báo rõ và tránh tạo quan hệ lặp hoặc mâu thuẫn.

**Câu 3.** Vì sao `@ConditionalOnBean` có thể phụ thuộc vào thứ tự auto-configuration?

**Đáp án:** Condition được đánh giá dựa trên bean definitions đã được xử lý tới thời điểm đó. Nếu bean cần tìm chưa được đăng ký, condition có thể không khớp.

**Câu 4.** Ordering có quyết định thứ tự tạo mọi bean instance không?

**Đáp án:** Không. Nó ảnh hưởng thứ tự áp dụng configuration và đăng ký bean definitions. Dependency injection và các quan hệ lifecycle quyết định thứ tự tạo instance.

**Câu 5.** Khi không muốn tạo compile-time dependency tới lớp được tham chiếu, dùng thuộc tính nào?

**Đáp án:** `beforeName` hoặc `afterName`, với FQCN dạng chuỗi.

**Câu 6.** Vì sao test truyền Alpha trước Zeta nhưng vẫn mong Zeta được xử lý trước?

**Đáp án:** Vì metadata `after = ZetaBaseAutoConfiguration.class` yêu cầu Boot sắp xếp Zeta trước Alpha. Thứ tự khai báo candidate trong test không phải hợp đồng ordering.

**Câu 7.** Test dùng AutoConfigurations.of có chứng minh imports file đã nằm trong JAR không?

**Đáp án:** Không. Runner nạp class trực tiếp. Cần kiểm tra JAR resource hoặc chạy smoke test qua `@EnableAutoConfiguration`.

## 15. Ghi nhớ

Khi một auto-configuration phụ thuộc bean do auto-configuration khác cung cấp, hãy mô tả quan hệ trước/sau bằng `before` hoặc `after`. Spring Boot dùng ordering metadata để sắp xếp quá trình áp dụng configuration và đăng ký bean definitions. Điều này đặc biệt quan trọng với `@ConditionalOnBean` và `@ConditionalOnMissingBean`, vì chúng chỉ xét những bean definitions đã được xử lý.

Bài thực hành dùng `ZetaBaseAutoConfiguration` cung cấp `BaseMarker`, còn `AlphaFeatureAutoConfiguration` khai báo `after = ZetaBaseAutoConfiguration.class` và chỉ tạo `FeatureMarker` khi bean nền tồn tại. Test truyền candidate theo thứ tự ngược, sau đó xác nhận cả hai bean và giá trị được inject. Một test riêng xác nhận feature không xuất hiện nếu cấu hình nền vắng mặt.

Luôn phân biệt thứ tự đăng ký bean definitions với thứ tự khởi tạo bean instances. Dùng dependency injection để thể hiện quan hệ sử dụng bean, dùng ordering để sắp xếp auto-configuration, và kiểm tra imports file trong artifact để bảo đảm các class thực sự được Spring Boot phát hiện.

### Tài liệu Spring Boot 3.3 chính thức

- [Creating Your Own Auto-configuration — Ordering and Testing](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [@AutoConfiguration Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [@AutoConfigureBefore Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureBefore.html)
- [@AutoConfigureAfter Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html)
- [ApplicationContextRunner Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [AutoConfigurations Javadoc — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html)
