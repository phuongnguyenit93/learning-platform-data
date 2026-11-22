# Kết hợp điều kiện môi trường, classpath và bean để auto-configuration không kích hoạt ngoài dự kiến

## 1. Bài toán: có thư viện chưa đủ để được phép tạo bean

Một thư viện tích hợp có thể mang theo class cần thiết, nhưng **không phải ứng dụng nào cũng cần bật tính năng**. Ví dụ một module cung cấp `AuditReporter` cho hệ thống web, chỉ nên tạo reporter mặc định khi đồng thời thỏa các yêu cầu:

1. **Môi trường ứng dụng:** đang chạy dưới dạng web ứng dụng **Servlet**, không phải CLI hoặc WebFlux.
2. **Classpath:** thư viện tích hợp tùy chọn (ví dụ Audit SDK) hiện diện.
3. **Cấu hình vận hành:** `demo.audit.enabled=true` được khai báo rõ ràng.
4. **Bean phụ thuộc:** ứng dụng đã cung cấp một `AuditTransport` để gửi dữ liệu đi.
5. **Quyền tùy biến:** chưa có bean `AuditReporter` do ứng dụng hoặc cấu hình khác tạo.

Nếu bỏ sót một “cổng”, có thể xảy ra hành vi không mong muốn: chỉ cần thêm một starter là reporter tự bật; bean được tạo dù người dùng chưa bật cờ; ứng dụng CLI bị kéo vào logic web; hoặc bean mặc định cạnh tranh với bean nghiệp vụ.

Thiết kế mong muốn có thể biểu diễn bằng biểu thức:

```text
CREATE_DEFAULT =
    SERVLET_WEB_CONTEXT
    AND OPTIONAL_SDK_ON_CLASSPATH
    AND demo.audit.enabled == "true"
    AND EXISTS(AuditTransport bean)
    AND NOT EXISTS(AuditReporter bean)
```

Các annotation `@Conditional...` đặt trên cùng một cấu hình hoặc phương thức bean đóng vai trò như các điều kiện **cùng phải thỏa**. Không nên phụ thuộc vào thứ tự kiểm tra cụ thể của framework để bảo vệ các phụ thuộc tùy chọn; cấu trúc lớp và vị trí đặt điều kiện mới là thiết kế quan trọng.

## 2. Bốn lớp kiểm tra khác nhau

| Nhóm | Annotation Spring Boot 3.3 | Câu hỏi thực sự được trả lời | Điều annotation **không** chứng minh |
|---|---|---|---|
| Loại môi trường | `@ConditionalOnWebApplication(type = SERVLET)`, `@ConditionalOnNotWebApplication` | Context đang thuộc loại web tương ứng hay không? | Có controller, route hay bean nghiệp vụ nào cụ thể? |
| Classpath | `@ConditionalOnClass`, `@ConditionalOnMissingClass` | Class có thể tìm thấy trong classpath bằng class loader hiện tại hay không? | Bean của class đó đã được đăng ký hoặc thư viện đã được cấu hình đúng? |
| Thuộc tính Environment | `@ConditionalOnProperty` | Một khóa cấu hình có mặt và đạt quy tắc giá trị không? | Class liên quan tồn tại, bean phụ thuộc đã có hoặc cấu hình phức tạp đã hợp lệ? |
| BeanFactory | `@ConditionalOnBean`, `@ConditionalOnMissingBean` | Tại thời điểm kiểm tra, đã có hoặc chưa có **định nghĩa bean** khớp điều kiện? | Sẽ không có bean được đăng ký sau đó, hoặc bean đã khởi tạo thành công? |

**Phân biệt “môi trường” ở đây:** `Environment` lưu thuộc tính từ YAML, `.properties`, biến môi trường, tham số chạy, profile...; `@ConditionalOnWebApplication` lại xét **kiểu ứng dụng web**. Hai ý nghĩa này liên quan nhưng không giống nhau. Dự án có `spring-webmvc` trên classpath vẫn có thể khởi chạy một ứng dụng `WebApplicationType.NONE`, và `@ConditionalOnClass` không biến context đó thành Servlet context.

Đối với điều kiện bean, cả `@ConditionalOnBean` và `@ConditionalOnMissingBean` xét những bean mà framework **đã xử lý**. Chúng không chờ các bean được khai báo trong auto-configuration xử lý muộn hơn. Spring Boot khuyến nghị dùng chúng trong auto-configuration, vốn được nạp sau bean definitions do ứng dụng khai báo.

## 3. Đặt điều kiện theo tầng để tránh kích hoạt và lỗi nạp class

### 3.1. Đặt cổng chung ở cấu hình, điều kiện bean gần phương thức tạo bean

Một mẫu thiết kế dễ đọc:

```java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnWebApplication(type = ConditionalOnWebApplication.Type.SERVLET)
    @ConditionalOnClass(name = "com.example.optional.AuditClient")
    @ConditionalOnProperty(
            prefix = "demo.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    static class ServletAuditConfiguration {

        @Bean
        @ConditionalOnBean(AuditTransport.class)
        @ConditionalOnMissingBean(AuditReporter.class)
        DefaultAuditReporter defaultAuditReporter(AuditTransport transport) {
            return new DefaultAuditReporter(transport);
        }
    }
}
```

**Đây là đoạn minh họa cấu trúc**, không phải một tệp Java độc lập: `AuditTransport`, `AuditReporter`, `DefaultAuditReporter` và class tùy chọn `com.example.optional.AuditClient` là các kiểu giả định của ứng dụng. Ví dụ test chạy được ở mục 6 sẽ tự khai báo các kiểu tương ứng.

Ý nghĩa của vị trí annotation:

- `@ConditionalOnWebApplication(type=SERVLET)` hạn chế cấu hình vào một **Servlet web context**. Khi cùng có MVC và WebFlux trong classpath, kiểm tra loại web cụ thể giúp tránh vô tình kích hoạt cấu hình Servlet trong nhánh không tương ứng.
- `@ConditionalOnClass(name=...)` kiểm tra SDK có mặt. Dùng `name` khi muốn chỉ định tên class mà không bắt buộc nguồn auto-configuration tham chiếu trực tiếp đến class tùy chọn.
- `@ConditionalOnProperty(... havingValue="true", matchIfMissing=false)` yêu cầu **chính xác cờ bật** theo so sánh giá trị của Spring Boot; thiếu thuộc tính hoặc nhận `false` thì không tạo bean. Đừng dùng mỗi `name="enabled"` rồi giả định chỉ `true` mới match: theo mặc định, những chuỗi có mặt khác `false` cũng có thể match.
- `@ConditionalOnBean(AuditTransport.class)` ngăn tạo reporter khi ứng dụng chưa có đường gửi dữ liệu.
- `@ConditionalOnMissingBean(AuditReporter.class)` nhường chỗ cho bất kỳ triển khai `AuditReporter` đã được xử lý trước đó, kể cả triển khai do người dùng cung cấp. Nếu chỉ kiểm tra kiểu `DefaultAuditReporter.class`, ứng dụng có `CustomAuditReporter` vẫn có thể bị tạo thêm reporter mặc định.

**Cùng một điều kiện không phải là cấu hình tự hoàn chỉnh:** `@ConditionalOnBean` không tự tạo `AuditTransport`; `@ConditionalOnClass` không tự thêm dependency; `@ConditionalOnWebApplication` không tự cung cấp máy chủ web.

### 3.2. Vì sao dùng một lớp `@Configuration` tĩnh lồng trong auto-configuration?

Trường hợp rủi ro:

```java
@Bean
@ConditionalOnClass(name = "com.example.optional.AuditClient")
com.example.optional.AuditClient auditClient() {
    return new com.example.optional.AuditClient();
}
```

Đoạn này **chỉ minh họa lỗi thiết kế** (constructor/API thực tế của `AuditClient` có thể khác). JVM có thể cần nạp/phân tích chữ ký phương thức `@Bean` có kiểu trả về từ thư viện **trước khi** điều kiện đặt trên phương thức được áp dụng. Nếu class không có trên runtime classpath, ứng dụng có nguy cơ `NoClassDefFoundError` hoặc lỗi introspection.

Đặt kiểm tra classpath ở một **lớp cấu hình tách biệt** (thường là static nested `@Configuration`), và chỉ đặt các phương thức bean dùng API tùy chọn **bên trong** cấu hình ấy. Spring Boot có thể xét metadata annotation ở cấp lớp trước khi nạp các thành phần phụ thuộc. Với điều kiện trên meta-annotation do bạn tự tạo, tài liệu còn khuyến nghị khai báo class bằng `name` thay vì `value`.

Điều quan trọng không chỉ là “đặt nhiều annotation”; phải cô lập tham chiếu kiểu tùy chọn ở nơi chỉ được xử lý khi class có mặt.

### 3.3. Không dùng component scan để tự tìm auto-configuration

Đối với starter/library Spring Boot 3.x, auto-configuration top-level được khai báo trong file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ nội dung file trong JAR đã phát hành:

```text
com.example.audit.autoconfigure.AuditAutoConfiguration
```

Tài liệu Spring Boot yêu cầu auto-configuration được nạp qua danh sách imports, không để component scanning thông thường vô tình tìm và kích hoạt chúng. Mục đích là kiểm soát thời điểm nạp và thứ tự tương đối với user configuration. Trong test ở dưới, `AutoConfigurations.of(...)` đăng ký trực tiếp lớp mô phỏng, nên không cần tạo file imports.

## 4. Bảng chân trị: bất kỳ cổng nào không đạt đều phải chặn

Giả sử `AuditTransport` và `AuditReporter` là hai interface độc lập, SDK tùy chọn có trên classpath nếu không ghi khác, và “reporter mặc định” nghĩa là `DefaultAuditReporter` do auto-configuration tạo:

| Servlet context | SDK có mặt | `enabled=true` | Có `AuditTransport` | Đã có `AuditReporter` | Kết quả |
|---|---|---|---|---|---|
| Có | Có | Có | Có | Chưa | **Tạo** reporter mặc định |
| **Không**, chạy CLI | Có | Có | Có | Chưa | Không tạo |
| **Không**, chạy Reactive | Có | Có | Có | Chưa | Không tạo với cấu hình `type=SERVLET` |
| Có | **Không** | Có | Có | Chưa | Không tạo |
| Có | Có | **Không khai báo** | Có | Chưa | Không tạo |
| Có | Có | **false** | Có | Chưa | Không tạo |
| Có | Có | Có | **Không** | Chưa | Không tạo |
| Có | Có | Có | Có | **Đã có** | Không tạo mặc định; giữ reporter của người dùng |

Bảng này thể hiện một phép **AND logic**. Nó không nói rằng Spring Boot sẽ đánh giá các annotation theo đúng thứ tự các cột, hoặc rằng toàn bộ SDK và bean có mặt thì ứng dụng chắc chắn chạy thành công: việc khởi tạo bean và kiểm tra logic runtime là các bước tiếp theo.

**Một lỗi phổ biến về logic:** sử dụng `@ConditionalOnBean(AuditTransport.class)` nhưng quên `@ConditionalOnMissingBean(AuditReporter.class)`. Kết quả là nếu người dùng đã khai báo reporter tùy chỉnh, context vẫn có thể chứa thêm reporter mặc định. Ngược lại, nếu chỉ dùng `@ConditionalOnMissingBean` mà bỏ `@ConditionalOnBean`, phương thức bean có tham số `AuditTransport` có thể được đăng ký khi chưa có dependency tương ứng; sau đó quá trình tạo bean có thể thất bại.

## 5. Điều kiện cấu hình rõ ràng để tránh bật nhầm theo môi trường

Ví dụ `application.yml` mặc định:

```yaml
demo:
  audit:
    enabled: false
```

Và trong môi trường cần bật:

```yaml
demo:
  audit:
    enabled: true
```

Để yêu cầu người vận hành **chủ động bật**, khai báo:

```java
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
```

Không nên dùng `matchIfMissing=true` nếu yêu cầu là tính năng mặc định tắt. Cũng không nên chỉ kiểm tra `@ConditionalOnProperty(name="enabled")` rồi coi mọi giá trị khác `false` là hợp lệ theo nghiệp vụ; `havingValue="true"` diễn tả ý định tốt hơn.

Cấu hình thực tế có thể đến từ nhiều `PropertySource` với thứ tự ưu tiên khác nhau. Một giá trị trong `application.yml` có thể bị override bởi profile, biến môi trường hoặc tham số lệnh. Điều kiện luôn xét `Environment` mà ứng dụng đang nhận, vì vậy kiểm tra file cấu hình duy nhất không đủ để kết luận lý do bật/tắt. Tạo các test cho cả cờ không tồn tại, `false`, `true` và giá trị ngoài mong đợi.

Nếu hệ thống thật cần bật theo profile cụ thể, `@Profile("production")` có thể là một điều kiện bổ sung, nhưng phải hiểu rằng **tên profile không thay cho** cờ bật, kiểu web, điều kiện classpath hoặc sự có mặt của bean. Tránh gắn nhầm `@Profile` vào một shared starter làm nó tự bật khi deploy chỉ vì tên profile phổ biến.

## 6. Ví dụ Java 17+ kiểm thử được bằng Spring Boot 3.3

Để kiểm chứng cả bốn lớp điều kiện và quyền override của ứng dụng, đặt tệp **`src/test/java/demo/CombinedAutoConfigurationConditionsTest.java`** sau vào dự án dùng Spring Boot 3.3, Java 17+ và `spring-boot-starter-test`. Dùng `WebApplicationContextRunner` để giả lập Servlet context, `ApplicationContextRunner` để giả lập non-web, `FilteredClassLoader` để giấu class SDK mô phỏng.

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionalOnWebApplication;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.context.runner.WebApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CombinedAutoConfigurationConditionsTest {

    // Đại diện cho SDK tùy chọn. Class lồng nhau vẫn có file .class riêng.
    static final class OptionalSdkMarker {
    }

    interface AuditTransport {
        String destination();
    }

    interface AuditReporter {
        String mode();
    }

    static final class DefaultAuditReporter implements AuditReporter {
        private final AuditTransport transport;

        DefaultAuditReporter(AuditTransport transport) {
            this.transport = transport;
        }

        @Override
        public String mode() {
            return "default:" + transport.destination();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TransportConfiguration {
        @Bean
        AuditTransport auditTransport() {
            return () -> "user-transport";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomReporterConfiguration {
        @Bean
        AuditReporter customAuditReporter() {
            return () -> "custom";
        }
    }

    @AutoConfiguration
    static class AuditAutoConfiguration {
        @Configuration(proxyBeanMethods = false)
        @ConditionalOnClass(OptionalSdkMarker.class)
        @ConditionalOnWebApplication(
                type = ConditionalOnWebApplication.Type.SERVLET
        )
        @ConditionalOnProperty(
                prefix = "demo.audit",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = false
        )
        static class ServletAuditConfiguration {

            @Bean
            @ConditionalOnBean(AuditTransport.class)
            @ConditionalOnMissingBean(AuditReporter.class)
            DefaultAuditReporter defaultAuditReporter(
                    AuditTransport transport) {
                return new DefaultAuditReporter(transport);
            }
        }
    }

    private final WebApplicationContextRunner webRunner =
            new WebApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AuditAutoConfiguration.class));

    @Test
    void createsDefaultOnlyWhenAllGatesPass() {
        webRunner
                .withUserConfiguration(TransportConfiguration.class)
                .withPropertyValues("demo.audit.enabled=true")
                .run(context -> {
                    assertTrue(context.containsBean("defaultAuditReporter"));
                    assertEquals(
                            "default:user-transport",
                            context.getBean(AuditReporter.class).mode()
                    );
                });
    }

    @Test
    void missingFlagDoesNotEnableFeature() {
        webRunner
                .withUserConfiguration(TransportConfiguration.class)
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }

    @Test
    void falseFlagDoesNotEnableFeature() {
        webRunner
                .withUserConfiguration(TransportConfiguration.class)
                .withPropertyValues("demo.audit.enabled=false")
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }

    @Test
    void arbitraryStringIsNotTrue() {
        webRunner
                .withUserConfiguration(TransportConfiguration.class)
                .withPropertyValues("demo.audit.enabled=enabled")
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }

    @Test
    void noTransportMeansNoReporter() {
        webRunner
                .withPropertyValues("demo.audit.enabled=true")
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }

    @Test
    void customReporterMakesDefaultBackOff() {
        webRunner
                .withUserConfiguration(
                        TransportConfiguration.class,
                        CustomReporterConfiguration.class
                )
                .withPropertyValues("demo.audit.enabled=true")
                .run(context -> {
                    assertFalse(context.containsBean("defaultAuditReporter"));
                    assertTrue(context.containsBean("customAuditReporter"));
                    assertEquals(
                            "custom",
                            context.getBean(AuditReporter.class).mode()
                    );
                });
    }

    @Test
    void missingOptionalSdkDoesNotActivateAutoConfiguration() {
        webRunner
                .withUserConfiguration(TransportConfiguration.class)
                .withPropertyValues("demo.audit.enabled=true")
                .withClassLoader(new FilteredClassLoader(OptionalSdkMarker.class))
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }

    @Test
    void nonWebContextDoesNotActivateServletConfiguration() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(AuditAutoConfiguration.class)
                )
                .withUserConfiguration(TransportConfiguration.class)
                .withPropertyValues("demo.audit.enabled=true")
                .run(context ->
                        assertFalse(context.containsBean("defaultAuditReporter"))
                );
    }
}
```

### Vì sao test này có ý nghĩa?

- Test đầu thỏa **toàn bộ** điều kiện và kiểm tra `AuditReporter#mode()` thực sự dùng `AuditTransport` do người dùng cấp.
- Ba test về property phân biệt **thiếu cờ**, `false` và chuỗi tùy ý. Chúng chặn tình huống bật ngoài ý định.
- Test không có `AuditTransport` chứng minh phép kiểm tra bean phụ thuộc; có class SDK và flag vẫn chưa đủ.
- Test custom reporter xác nhận **back-off** đúng theo **interface `AuditReporter`** và bean do ứng dụng cung cấp tiếp tục được sử dụng.
- `FilteredClassLoader(OptionalSdkMarker.class)` mô phỏng trường hợp SDK vắng mặt. Marker là loại tối giản chỉ dùng cho test, tránh phụ thuộc vào thư viện bên ngoài.
- `ApplicationContextRunner` tạo **non-web context** dù test class vẫn có các thư viện Spring Web trong test classpath; chính xác để kiểm tra điều kiện môi trường. `WebApplicationContextRunner` mô phỏng Servlet web context và không yêu cầu chạy một máy chủ thật.

### Dependency và cách chạy

Dự án kiểm thử cần các dependency tương thích Boot 3.3. Ví dụ Gradle Groovy DSL, với plugin/phiên bản Spring Boot đã được cấu hình trước đó:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Từ thư mục gốc dự án:

```bash
./gradlew test --tests demo.CombinedAutoConfigurationConditionsTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.CombinedAutoConfigurationConditionsTest
```

**Kỳ vọng:** cả **8 test pass**. Test đầu tạo bean `defaultAuditReporter`; bảy test còn lại xác nhận từng cổng bị thiếu hoặc user override làm bean mặc định không xuất hiện. Đây là kết quả **dự đoán từ code và API Spring Boot 3.3**, không phải log của một lần chạy thực tế. Nếu dự án đang áp dụng dependency/auto-configuration bổ sung, cần kiểm tra báo cáo test thực tế của dự án đó.

## 7. Thứ tự bean và auto-configuration: cổng quan trọng thường bị quên

Cả `@ConditionalOnBean` lẫn `@ConditionalOnMissingBean` dựa trên các bean definition **đã xử lý tại thời điểm điều kiện được tính**. Hãy phân biệt ba thứ tự:

1. **Nguồn bean người dùng và auto-configuration:** Spring Boot thiết kế để bean definitions của người dùng được xử lý trước auto-configuration. Vì vậy các điều kiện back-off dựa trên bean người dùng hoạt động đúng nếu đặt trong auto-configuration.
2. **Thứ tự giữa nhiều auto-configuration:** nếu reporter phụ thuộc bean `AuditTransport` do **auto-configuration khác** tạo, phải đảm bảo cấu hình transport được xử lý trước reporter. Có thể khai báo `@AutoConfiguration(after = TransportAutoConfiguration.class)` hoặc `afterName` khi cần tránh tham chiếu trực tiếp. Không giả định thứ tự tên file hoặc vị trí các dòng trong `AutoConfiguration.imports` là giải pháp ổn định.
3. **Thứ tự khởi tạo object:** `after`/`before` của auto-configuration ảnh hưởng **thứ tự đăng ký định nghĩa bean**, không trực tiếp bảo đảm object A được khởi tạo trước object B. Quá trình khởi tạo vẫn phụ thuộc bean injection và cơ chế dependency của Spring.

Ví dụ hướng dẫn thứ tự giữa hai auto-configuration (tên lớp giả định):

```java
@AutoConfiguration(afterName =
        "com.example.transport.autoconfigure.TransportAutoConfiguration")
public class AuditAutoConfiguration {
    // Các lớp cấu hình điều kiện riêng...
}
```

Đây là **mảnh cấu hình minh họa**, không phải một tệp runnable. Chỉ cần thứ tự này nếu reporter thực sự cần nhận biết `AuditTransport` được tạo bởi một auto-configuration khác. Trong ví dụ test, `TransportConfiguration` là cấu hình người dùng, được đăng ký trước, nên không cần `afterName`.

**Không nên dùng:** đặt `@ConditionalOnBean` một cách tùy tiện trên `@Configuration` người dùng rồi mong nó luôn thấy bean chưa được xử lý. Hãy kiểm tra thời điểm đánh giá, hoặc tổ chức lại điều kiện vào đúng auto-configuration.

## 8. Lỗi phổ biến và cách sửa

### 8.1. Nhầm classpath với bean

Có class `OptionalSdkMarker` trong runtime không chứng minh có `AuditTransport` bean. `@ConditionalOnClass` chỉ kiểm tra class. Khi cần bean, thêm `@ConditionalOnBean`; khi cần tránh tạo trùng, thêm `@ConditionalOnMissingBean`. Nếu bean phụ thuộc có thể tồn tại ở parent context, cân nhắc thuộc tính `search` của điều kiện bean và xác định rõ phạm vi cần tìm.

### 8.2. Dùng mỗi `@ConditionalOnWebApplication`

Annotation này kiểm tra **loại context**, không biết người dùng có muốn bật tính năng audit hay không. Nếu môi trường production mặc định không được bật feature, hãy thêm cờ rõ ràng trong `Environment` và test trường hợp không khai báo. Đặc biệt, khi cả MVC và WebFlux cùng có dependency, `type = SERVLET` hoặc `type = REACTIVE` diễn đạt ý định chặt chẽ hơn kiểu `ANY`.

### 8.3. Đặt class tùy chọn trực tiếp vào kiểu trả về của phương thức `@Bean`

Điều kiện `@ConditionalOnClass` gắn trên **chính phương thức đó** có thể đến quá muộn để tránh JVM nạp chữ ký phương thức. Cô lập phương thức trong một lớp `@Configuration` có `@ConditionalOnClass` ở **cấp lớp**. Ưu tiên `name` khi viết meta-annotation hoặc tránh tham chiếu trực tiếp class tùy chọn.

### 8.4. Dùng `@ConditionalOnMissingBean` nhầm kiểu

Nếu có interface `AuditReporter`, còn bean mặc định trả về `DefaultAuditReporter`, việc đặt `@ConditionalOnMissingBean` mà không xác định mục tiêu có thể chỉ dựa vào **kiểu trả về** của phương thức. Khi muốn tôn trọng mọi implementor, nên khai báo `@ConditionalOnMissingBean(AuditReporter.class)`. Đồng thời giữ chữ ký phương thức có kiểu trả về cụ thể nhất có thể để Spring xác định bean type chính xác.

### 8.5. Bật mặc định khi cấu hình chưa có

`@ConditionalOnProperty(matchIfMissing = true)` làm một property bị thiếu vẫn match. Đây là hành vi phù hợp cho một số tính năng mặc định bật, nhưng trái yêu cầu **opt-in**. Đối với tính năng có side effect (ghi audit, gọi dịch vụ ngoài, khởi tạo client...), hãy quyết định default rõ ràng và dùng `havingValue="true", matchIfMissing=false` nếu muốn chỉ bật khi người dùng cho phép.

### 8.6. Tham chiếu bean bằng biểu thức SpEL

`@ConditionalOnExpression` có thể đọc biểu thức SpEL, nhưng tham chiếu bean trực tiếp trong biểu thức có nguy cơ **khởi tạo bean quá sớm**, khiến bean chưa đi qua đầy đủ các bước post-processing và binding. Với các câu hỏi về sự tồn tại bean, hãy dùng `@ConditionalOnBean`/`@ConditionalOnMissingBean`; với giá trị thuộc tính, dùng `@ConditionalOnProperty`. Tránh trộn quá nhiều tác vụ logic thành một biểu thức khó test.

### 8.7. Tưởng rằng thay property trong lúc chạy sẽ tự tạo bean

Các điều kiện trên được đánh giá trong quá trình xây dựng context, chủ yếu ở lúc đăng ký bean definitions. Đổi biến môi trường hoặc file cấu hình sau khi context đã khởi động **không tự động** chạy lại mọi điều kiện để thêm hoặc xóa bean. Nếu cần bật/tắt live, thiết kế cơ chế runtime riêng; annotation auto-configuration giải quyết **quyết định khởi động**.

### 8.8. Cho rằng “classpath đúng” bảo đảm startup thành công

Khi điều kiện match, bean vẫn có thể thất bại trong lúc khởi tạo vì cấu hình không hợp lệ, service ngoài không phản hồi hoặc lỗi dependency. Annotation điều kiện chỉ quyết định **có đăng ký hay không**, không thay thế kiểm tra cấu hình, xử lý lỗi và integration test.

## 9. Chẩn đoán khi bean xuất hiện hoặc biến mất bất ngờ

Làm theo thứ tự câu hỏi:

1. **Environment:** giá trị cuối cùng của `demo.audit.enabled` là gì? Có profile, environment variable hoặc CLI argument nào override không?
2. **Loại context:** ứng dụng thực sự là Servlet, Reactive hay non-web? Đừng kết luận từ việc tìm thấy class MVC trên classpath.
3. **Classpath:** class SDK cần thiết có ở runtime classpath? Có bị khai báo `compileOnly` hoặc bị loại khỏi dependency khi đóng gói không?
4. **Bean definitions:** lúc condition chạy, `AuditTransport` đã được đăng ký chưa? `AuditReporter` của người dùng đã có chưa? Đang tìm trong current hay cả parent context?
5. **Thứ tự:** nếu các bean đến từ nhiều auto-configuration, `after`/`afterName` có đủ để điều kiện của reporter thấy định nghĩa bean liên quan chưa?
6. **Chữ ký và class loading:** một phương thức `@Bean` hoặc class khác có tham chiếu trực tiếp kiểu tùy chọn trước khi class-level guard được đánh giá không?
7. **Kết quả thực tế:** bean definition có tồn tại nhưng khởi tạo lỗi, hay điều kiện thực sự không match?

Spring Boot cung cấp **Condition Evaluation Report**. Khi khởi chạy ứng dụng, có thể dùng `--debug` để xem báo cáo điều kiện trong log; khi đã cài và cấu hình Actuator, endpoint `/actuator/conditions` cũng có thể giúp xem positive/negative matches. Trong test, có thể yêu cầu in report bằng initializer:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)
        )
        .withConfiguration(AutoConfigurations.of(AuditAutoConfiguration.class))
        .run(context -> {
            // Kiểm tra điều kiện trong một test thực tế.
        });
```

Đoạn này là **mẫu chẩn đoán**, cần đặt trong tệp có import `ConditionEvaluationReportLoggingListener`, `LogLevel` và các class khác. Không dùng nó thay thế các assertion: report cho biết **lý do match**, còn test xác minh **bean nào được tạo**.

Một ma trận test nên có ít nhất: toàn bộ điều kiện đạt; thiếu từng cổng; cờ `false`/thiếu cờ; user override; non-web và, nếu sản phẩm hỗ trợ, Reactive; class SDK không có. Với integration thật, thêm trường hợp auto-configuration thứ hai đăng ký dependency và kiểm tra thứ tự.

## 10. Nguyên tắc thiết kế cần nhớ

- Xem **environment, classpath, bean và property** là những cổng độc lập. Nếu phải đồng thời thỏa, viết rõ nhiều điều kiện để biểu đạt AND.
- **Chỉ có thư viện không có nghĩa phải bật tính năng**; chỉ có bean không có nghĩa được bật ngoài ý muốn của người dùng.
- Dùng cờ opt-in explicit khi tính năng có side effect, cùng `havingValue="true"` và `matchIfMissing=false`.
- Đặt `@ConditionalOnClass` ở **lớp cấu hình độc lập** khi mã bên trong dùng class tùy chọn; tránh chữ ký `@Bean` làm class loading xảy ra sớm.
- Dùng `@ConditionalOnBean` cho dependency bắt buộc và `@ConditionalOnMissingBean` theo **kiểu abstraction đúng** để back off.
- Giữ bean conditions trong auto-configuration và định rõ thứ tự nếu phụ thuộc bean từ auto-configuration khác.
- Test **ma trận các trường hợp âm** để chứng minh bean không bị kích hoạt ngoài dự kiến, thay vì chỉ test một trường hợp dương.
- Báo cáo condition giúp chẩn đoán **vì sao** match; integration test và runtime checks xác minh **hệ thống hoạt động đúng**.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 Reference, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 Javadoc, `ConditionalOnClass`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3 Javadoc, `ConditionalOnBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
- Spring Boot 3.3 Javadoc, `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3 Javadoc, `ConditionalOnProperty`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 Javadoc, `ConditionalOnWebApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnWebApplication.html
