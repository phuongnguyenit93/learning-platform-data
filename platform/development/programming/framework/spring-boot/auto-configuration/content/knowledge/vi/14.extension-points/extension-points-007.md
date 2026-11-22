# Tách cấu hình cốt lõi khỏi tích hợp tùy chọn bằng nhiều lớp auto-configuration

## Mục tiêu học tập

Một thư viện Spring Boot có thể cung cấp chức năng cốt lõi mà mọi ứng dụng đều dùng, đồng thời hỗ trợ các tích hợp chỉ một số ứng dụng cần: SDK của nhà cung cấp, client cloud, broker, database driver hoặc một web framework cụ thể. Nếu tất cả được viết trong một lớp auto-configuration, lớp đó dễ vô tình phụ thuộc vào các thư viện tùy chọn. Khi ứng dụng không cài một SDK, quá trình khởi động có thể gặp `NoClassDefFoundError` dù người dùng không hề bật tính năng tích hợp.

Bài học này trình bày cách tách thành **nhiều lớp auto-configuration theo ranh giới chức năng và dependency**. Cấu hình cốt lõi chỉ biết API cốt lõi; mỗi tích hợp tùy chọn có cấu hình riêng và được bảo vệ bằng classpath condition. Qua đó, ứng dụng có thể sử dụng phần cốt lõi mà không phải kéo theo mọi thư viện đối tác.

Sau bài học, bạn có thể:

- Thiết kế ranh giới giữa core API, core auto-configuration và optional integration.
- Tách một auto-configuration lớn thành các lớp nhỏ, có điều kiện rõ ràng.
- Dùng `@ConditionalOnClass` đúng vị trí để tránh tải kiểu không có trên runtime classpath.
- Đăng ký nhiều auto-configuration qua `AutoConfiguration.imports`.
- Phối hợp thứ tự cấu hình, `@ConditionalOnBean` và `@ConditionalOnMissingBean`.
- Kiểm thử các tình huống: chỉ có core, có SDK tùy chọn, SDK có nhưng thiếu client bean, và ứng dụng tự override.

## 1. Bài toán: một thư viện, nhiều mức tích hợp

Giả sử thư viện `acme-notification` cung cấp API gửi thông báo. Mọi ứng dụng đều có thể cần API cốt lõi, nhưng chỉ một số ứng dụng dùng SDK SMS của nhà cung cấp Vendor.

Nếu gộp tất cả vào một lớp:

~~~java
@AutoConfiguration
class NotificationAutoConfiguration {

    @Bean
    NotificationRegistry notificationRegistry() {
        return new DefaultNotificationRegistry();
    }

    @Bean
    SmsSender smsSender(com.vendor.sms.SmsClient client) {
        return new VendorSmsSender(client);
    }
}
~~~

Ứng dụng chỉ dùng phần core vẫn phải giải quyết kiểu `com.vendor.sms.SmsClient` xuất hiện trong chữ ký phương thức. Nếu SDK không có trên runtime classpath, JVM hoặc quá trình xử lý cấu hình có thể thất bại trước khi người dùng có cơ hội sử dụng phần core.

Một `@ConditionalOnClass` đặt **chỉ trên phương thức `@Bean`** không phải lúc nào cũng đủ bảo vệ. Trước khi điều kiện trên phương thức được áp dụng, JVM có thể đã tải kiểu trả về hoặc kiểu tham số của phương thức. Đây là lý do Spring Boot khuyến nghị cô lập phần tham chiếu đến class tùy chọn trong một lớp cấu hình riêng có class-level condition.

Thiết kế rõ ràng hơn:

~~~text
Ứng dụng Spring Boot
       |
       +---- Core Auto-configuration
       |       |
       |       +---- Core API / Core beans
       |
       +---- Optional Vendor Auto-configuration
               |
               +---- Chỉ được xét khi Vendor SDK hiện diện
                       |
                       +---- Vendor client / adapter
~~~

Core và optional integration có thể được đóng gói cùng artifact hoặc thành các artifact/module riêng. Dù chọn cách nào, **ranh giới phụ thuộc trong mã nguồn** vẫn phải rõ ràng.

## 2. Phân chia trách nhiệm thành các lớp

Một thiết kế thư viện có thể có các phần:

| Thành phần | Trách nhiệm | Phụ thuộc nên có |
| --- | --- | --- |
| Core API | Interface, model, exception và contract chung | Java/Jakarta API cần thiết |
| Core implementation | Cài đặt mặc định không cần SDK đối tác | Core API |
| Core auto-configuration | Đăng ký các bean cốt lõi | Spring Boot và core implementation |
| Optional integration API/adapter | Chuyển đổi giữa API cốt lõi và API nhà cung cấp | Core API + SDK tương ứng |
| Optional auto-configuration | Chỉ đăng ký adapter khi SDK/client phù hợp hiện diện | Core API + SDK tùy chọn + Spring Boot |
| Optional starter | Tập hợp dependency để ứng dụng dễ bật tích hợp | Core starter + optional integration theo lựa chọn |

Ví dụ một cấu trúc module:

~~~text
acme-notification/
  acme-notification-api/
    NotificationRegistry.java
    SmsSender.java

  acme-notification-autoconfigure/
    CoreNotificationAutoConfiguration.java
    META-INF/spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports

  acme-notification-vendor-sms/
    VendorSmsAutoConfiguration.java
    VendorSmsSender.java
    META-INF/spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports

  acme-notification-spring-boot-starter/
    build.gradle
~~~

Đây là cấu trúc minh họa; tên artifact và số module tùy quy mô. Không nhất thiết phải tạo một module cho từng class. Chỉ tách khi ranh giới dependency, vòng đời hoặc chủ sở hữu chức năng thực sự khác nhau.

**Điểm cốt lõi:** core module không import, không kế thừa và không đưa kiểu SDK Vendor vào chữ ký method của mình. Optional integration module được phép phụ thuộc vào core API và SDK cần thiết.

## 3. Core auto-configuration: chỉ sử dụng kiểu cốt lõi

Ví dụ API của thư viện:

~~~java
package example.notification;

public interface NotificationRegistry {
    String implementation();
}
~~~

Core auto-configuration:

~~~java
package example.notification.autoconfigure;

import example.notification.NotificationRegistry;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class CoreNotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationRegistry.class)
    NotificationRegistry notificationRegistry() {
        return () -> "core-default";
    }
}
~~~

Đây là **tệp Java production hoàn chỉnh** nếu package/file tương ứng được tạo và dependency Spring Boot có sẵn. Cấu hình core chỉ đăng ký một implementation mặc định. Người dùng có thể cung cấp `NotificationRegistry` riêng; điều kiện `@ConditionalOnMissingBean` cho phép cấu hình mặc định nhường chỗ.

Không có tham chiếu nào đến `com.vendor.sms.SmsClient`. Vì vậy, class này vẫn có thể được tải và áp dụng khi SDK SMS hoàn toàn vắng mặt.

### Vì sao nên để core API độc lập với SDK?

Nếu interface cốt lõi khai báo tham số là `SmsClient`, thì mọi người dùng core API cũng phải có SDK. Ranh giới đã bị phá vỡ ngay ở tầng API.

Hãy để contract cốt lõi dùng kiểu do thư viện sở hữu:

~~~java
public interface NotificationSender {
    SendResult send(NotificationMessage message);
}
~~~

Adapter tùy chọn có thể nhận kiểu SDK Vendor bên trong implementation, nhưng không để kiểu đó rò rỉ vào core API. Cách này giúp ứng dụng có thể chọn một tích hợp khác mà không cần sửa code cốt lõi.

## 4. Optional auto-configuration: class-level condition bảo vệ dependency

Giả sử SDK Vendor có:

- `com.vendor.sms.SmsClient`: client do SDK cung cấp.
- `com.vendor.sms.autoconfigure.SmsClientAutoConfiguration`: auto-configuration của SDK đăng ký client bean.

Optional auto-configuration của thư viện:

~~~java
package example.notification.vendor;

import com.vendor.sms.SmsClient;
import example.notification.NotificationRegistry;
import example.notification.SmsSender;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(
        afterName = "com.vendor.sms.autoconfigure.SmsClientAutoConfiguration"
)
@ConditionalOnClass(name = "com.vendor.sms.SmsClient")
public class VendorSmsAutoConfiguration {

    @Bean
    @ConditionalOnBean(type = "com.vendor.sms.SmsClient")
    @ConditionalOnMissingBean(SmsSender.class)
    SmsSender vendorSmsSender(
            SmsClient client,
            NotificationRegistry registry) {
        return new VendorSmsSender(client, registry);
    }
}
~~~

Đây là **đoạn production minh họa**; `SmsSender` và `VendorSmsSender` là API/adapter do thư viện sở hữu, còn `SmsClient` là kiểu từ SDK Vendor. Cần có dependency SDK trên **compile classpath của module integration** để biên dịch đoạn code này.

Ba điều kiện có vai trò khác nhau:

1. `@ConditionalOnClass(name = "com.vendor.sms.SmsClient")` ở cấp **class** bảo vệ toàn bộ cấu hình nếu SDK không có trên runtime classpath.
2. `@ConditionalOnBean(type = "com.vendor.sms.SmsClient")` yêu cầu client bean thực sự có trong context; SDK hiện diện trên classpath không có nghĩa client đã được tạo.
3. `@ConditionalOnMissingBean(SmsSender.class)` cho phép ứng dụng tự cung cấp `SmsSender` và thay thế adapter mặc định.

`afterName` sắp xếp cấu hình tích hợp sau auto-configuration của SDK. Tên đầy đủ được dùng dưới dạng chuỗi nên **khai báo thứ tự** không cần import class auto-configuration của SDK. Nó không tự đăng ký SDK configuration hoặc tạo `SmsClient`; SDK phải được đưa vào ứng dụng và cấu hình của nó phải được chọn.

### Có thể dùng `value = SmsClient.class` không?

Nếu module integration đã có SDK trên compile classpath, class-level condition cũng có thể viết:

~~~java
@ConditionalOnClass(SmsClient.class)
~~~

Dạng `name = "..."` hữu ích khi muốn thể hiện điều kiện bằng tên và tránh thêm một class literal trong metadata annotation. Tuy nhiên, nếu chữ ký `@Bean` vẫn dùng `SmsClient`, module integration vẫn phải biên dịch được với SDK. Dùng `name` **không xóa dependency compile-time khỏi một file Java đang trực tiếp tham chiếu kiểu đó**.

## 5. Vì sao class-level condition an toàn hơn method-level condition?

Xét ví dụ không an toàn khi SDK có thể vắng mặt:

~~~java
@AutoConfiguration
class VendorSmsAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.vendor.sms.SmsClient")
    SmsSender smsSender(com.vendor.sms.SmsClient client) {
        return new VendorSmsSender(client);
    }
}
~~~

Condition nằm trên method, nhưng để xử lý method metadata, JVM có thể cần resolve kiểu `SmsClient` ở tham số hoặc kiểu trả về trước khi condition được đánh giá. Khi SDK vắng mặt, việc bảo vệ có thể đến quá muộn.

Cách sửa là chuyển condition lên **lớp cấu hình riêng**:

~~~java
@AutoConfiguration
class NotificationAutoConfiguration {

    // Core beans không tham chiếu SDK tùy chọn.

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sms.SmsClient")
    static class VendorSmsConfiguration {

        @Bean
        SmsSender smsSender(com.vendor.sms.SmsClient client) {
            return new VendorSmsSender(client);
        }
    }
}
~~~

Spring Boot đọc metadata của cấu hình và class-level condition trước khi tải phần cấu hình tùy chọn. Cấu hình lồng nhau phải là `static` để không cần instance của lớp bao ngoài.

Trong dự án lớn, một **top-level auto-configuration class riêng** thường dễ tổ chức, test và phân phối hơn. Cấu hình lồng nhau hữu ích khi phần tích hợp nhỏ và có quan hệ sở hữu rõ với cấu hình cha.

**Quy tắc thực hành:** khi một lớp hoặc method signature chứa kiểu có thể không tồn tại, hãy đặt classpath condition ở cấp một configuration class có thể được bỏ qua hoàn toàn. Không dựa vào method-level condition để che một return type hoặc parameter type vắng mặt.

## 6. Hai cách đóng gói: cùng artifact hay tách artifact?

### Cùng một auto-configuration artifact

Có thể đặt cả core config và optional config trong một artifact:

~~~text
acme-notification-autoconfigure/
  CoreNotificationAutoConfiguration.java
  VendorSmsAutoConfiguration.java
  AutoConfiguration.imports
~~~

Artifact được biên dịch với dependency cần thiết để build phần integration. Ở runtime, nếu ứng dụng không đưa SDK Vendor vào classpath, class-level condition loại optional configuration; core config vẫn hoạt động.

Cách này phù hợp khi:
- Tích hợp nhỏ, được phát hành cùng nhịp với core.
- Chấp nhận module compile-time có biết SDK.
- Người dùng chỉ cần chọn có thêm SDK runtime hay không.

### Tách module/artifact tùy chọn

Nếu cần **cô lập dependency ngay từ build graph**, tách integration thành artifact riêng:

~~~text
acme-notification-autoconfigure
    -> acme-notification-api
    -> spring-boot-autoconfigure

acme-notification-vendor-sms
    -> acme-notification-api
    -> vendor-sms-sdk
    -> spring-boot-autoconfigure
~~~

Ứng dụng chỉ dùng core thì không thêm artifact `acme-notification-vendor-sms`. Ứng dụng muốn tích hợp SMS thì thêm artifact này và SDK tương ứng.

Cách này có lợi khi:
- SDK lớn hoặc có license/phiên bản riêng.
- Tích hợp do team khác sở hữu.
- Không muốn build core module phụ thuộc SDK.
- Cần phát hành/versioning integration độc lập.

Nếu artifact integration được thêm nhưng SDK bị loại khỏi runtime classpath, `@ConditionalOnClass` vẫn bảo vệ optional configuration. Nếu artifact integration hoàn toàn không được thêm, auto-configuration của nó cũng không phải candidate.

**Lưu ý:** dependency scope và cách publish (Gradle/Maven) cần được thiết kế đúng. Một dependency chỉ có trong compile classpath của module integration không tự bảo đảm nó được đóng gói hoặc cung cấp ở runtime cho ứng dụng; hãy kiểm tra dependency graph và runtime classpath của starter thực tế.

## 7. Đăng ký nhiều auto-configuration bằng AutoConfiguration.imports

Spring Boot 3.x tìm auto-configuration của thư viện qua resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nếu core và optional config cùng nằm trong một artifact, file có thể liệt kê:

~~~text
example.notification.autoconfigure.CoreNotificationAutoConfiguration
example.notification.vendor.VendorSmsAutoConfiguration
~~~

Mỗi dòng là tên đầy đủ của một auto-configuration. Spring Boot sẽ xét classpath conditions để quyết định cấu hình nào có thể áp dụng.

Nếu tách thành hai artifact:
- File imports trong artifact core chỉ liệt kê `CoreNotificationAutoConfiguration`.
- File imports trong artifact integration liệt kê `VendorSmsAutoConfiguration`.

Không cần core config `@Import(VendorSmsAutoConfiguration.class)`. Việc import trực tiếp sẽ tạo phụ thuộc giữa hai lớp và làm mất lợi ích của ranh giới độc lập. Mỗi artifact tự công bố auto-configuration của mình bằng resource chuẩn.

**Không component-scan package auto-configuration** để tìm các lớp này. Hãy đăng ký chúng qua imports file; dùng `@Import` cho các cấu hình hỗ trợ cụ thể khi có chủ đích, không dùng để thay thế discovery của auto-configuration.

Nếu build một uber/fat JAR và nhiều dependency cùng chứa resource imports có cùng tên, hãy bảo đảm công cụ đóng gói **merge nội dung resource** thay vì ghi đè file của artifact khác. Nếu bị ghi đè, auto-configuration của một thư viện có thể biến mất dù class vẫn nằm trong JAR.

## 8. Phối hợp thứ tự và điều kiện bean

Ba loại điều kiện thường xuất hiện cùng nhau nhưng giải quyết ba câu hỏi khác nhau:

| Annotation | Câu hỏi |
| --- | --- |
| `@ConditionalOnClass` | Kiểu/API cần thiết có trên classpath không? |
| `@ConditionalOnBean` | Bean cần dùng đã được đăng ký trong context chưa? |
| `@ConditionalOnMissingBean` | Đã có bean thay thế phù hợp chưa? |

Thứ tự auto-configuration có thể cần thiết nếu optional config phụ thuộc bean được SDK auto-configuration đăng ký. Ví dụ:

~~~java
@AutoConfiguration(
    afterName = "com.vendor.sms.autoconfigure.SmsClientAutoConfiguration"
)
@ConditionalOnClass(name = "com.vendor.sms.SmsClient")
class VendorSmsAutoConfiguration {
}
~~~

`afterName` chỉ sắp xếp auto-configuration nếu cấu hình SDK là một candidate được chọn. Nó không tự thêm SDK hoặc đảm bảo bean client tồn tại. Vì vậy, `@ConditionalOnBean(type = "com.vendor.sms.SmsClient")` có thể cần thiết ở bean method.

Khi optional integration cần bean core, có thể đặt:

~~~java
@AutoConfiguration(after = CoreNotificationAutoConfiguration.class)
class VendorSmsAutoConfiguration {
}
~~~

Cách này biểu đạt rằng core auto-configuration được áp dụng trước integration. Thứ tự áp dụng ảnh hưởng **thứ tự đăng ký bean definitions**, không quyết định thứ tự constructor của các đối tượng bean. Spring tạo bean theo dependency graph; nếu một bean cần bean khác, hãy khai báo dependency trong constructor/method parameter.

## 9. Ví dụ kiểm chứng: core chạy khi SDK thiếu, integration chỉ bật khi đủ điều kiện

Ví dụ test sau mô phỏng một SDK tùy chọn bằng class `OptionalSmsClient`. `FilteredClassLoader` giúp kiểm tra trường hợp class SDK không có trên classpath của application context.

**Tệp:** `src/test/java/example/notification/OptionalIntegrationAutoConfigurationTest.java`

~~~java
package example.notification;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalIntegrationAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            CoreAutoConfiguration.class,
                            OptionalSmsAutoConfiguration.class));

    @Test
    void coreWorksWhenOptionalSdkIsMissing() {
        runner.withClassLoader(new FilteredClassLoader(OptionalSmsClient.class))
                .run(context -> {
                    assertThat(context).hasSingleBean(NotificationRegistry.class);
                    assertThat(context).doesNotHaveBean(SmsSender.class);
                    assertThat(context.getBean(NotificationRegistry.class).name())
                            .isEqualTo("core");
                });
    }

    @Test
    void optionalIntegrationLoadsWhenSdkAndClientBeanExist() {
        runner.withUserConfiguration(OptionalSdkConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(NotificationRegistry.class);
                    assertThat(context).hasSingleBean(SmsSender.class);
                    assertThat(context.getBean(SmsSender.class).provider())
                            .isEqualTo("vendor");
                });
    }

    @Test
    void sdkClassAloneDoesNotCreateIntegrationWithoutClientBean() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(NotificationRegistry.class);
            assertThat(context).doesNotHaveBean(SmsSender.class);
        });
    }

    @Test
    void userImplementationOverridesOptionalAdapter() {
        runner.withUserConfiguration(
                        OptionalSdkConfiguration.class,
                        CustomSmsSenderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(SmsSender.class);
                    assertThat(context.getBean(SmsSender.class).provider())
                            .isEqualTo("custom");
                });
    }

    interface NotificationRegistry {
        String name();
    }

    interface SmsSender {
        String provider();
    }

    // Đại diện cho kiểu SDK; trong production kiểu này đến từ vendor artifact.
    static class OptionalSmsClient {
        String provider() {
            return "vendor";
        }
    }

    @AutoConfiguration
    static class CoreAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(NotificationRegistry.class)
        NotificationRegistry notificationRegistry() {
            return () -> "core";
        }
    }

    @AutoConfiguration(after = CoreAutoConfiguration.class)
    @ConditionalOnClass(OptionalSmsClient.class)
    static class OptionalSmsAutoConfiguration {

        @Bean
        @ConditionalOnBean(OptionalSmsClient.class)
        @ConditionalOnMissingBean(SmsSender.class)
        SmsSender vendorSmsSender(
                OptionalSmsClient client,
                NotificationRegistry registry) {
            return () -> client.provider();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class OptionalSdkConfiguration {

        @Bean
        OptionalSmsClient optionalSmsClient() {
            return new OptionalSmsClient();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomSmsSenderConfiguration {

        @Bean
        SmsSender customSmsSender() {
            return () -> "custom";
        }
    }
}
~~~

Trong test harness, các cấu hình được lồng trong một class để ví dụ gọn. Trong production nên dùng top-level classes và các package riêng như phần kiến trúc đã mô tả. `OptionalSmsClient` trong test là class giả lập; nó không phải SDK thật.

### Dependency và lệnh chạy

Dự án test cần Java 17+ và Spring Boot 3.3.x. Với Gradle Groovy DSL (dự án đã quản lý version bằng Spring Boot plugin/BOM):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy test trong module chứa tệp:

~~~bash
# Linux/macOS
./gradlew test --tests "example.notification.OptionalIntegrationAutoConfigurationTest"

# Windows
gradlew.bat test --tests "example.notification.OptionalIntegrationAutoConfigurationTest"
~~~

**Kết quả kỳ vọng:** bốn test PASS.

| Test | Kết quả cần xác nhận |
| --- | --- |
| `coreWorksWhenOptionalSdkIsMissing` | Core bean tồn tại, `SmsSender` không tồn tại |
| `optionalIntegrationLoadsWhenSdkAndClientBeanExist` | Core và optional integration đều tồn tại |
| `sdkClassAloneDoesNotCreateIntegrationWithoutClientBean` | SDK class có nhưng chưa có client bean, integration không đăng ký |
| `userImplementationOverridesOptionalAdapter` | Bean do ứng dụng khai báo thắng adapter mặc định |

Test dùng assertion, không gọi `System.out.println`, nên không có stdout ứng dụng cố định. Kết quả console phụ thuộc cấu hình logging của Gradle/JUnit. Đây là kết quả kỳ vọng theo code; cần chạy lệnh trong dự án thật để xác nhận build, version và classpath cụ thể.

## 10. Những lỗi thường gặp khi tách cấu hình

1. **Core class vẫn tham chiếu optional SDK trong method signature.** Dù có classpath condition ở một nơi khác, JVM có thể phải resolve kiểu trước. Chuyển method sang optional configuration riêng.
2. **Chỉ đặt `@ConditionalOnClass` trên `@Bean` method có kiểu trả về tùy chọn.** Condition có thể được đánh giá quá muộn; đặt ở class-level của một configuration riêng.
3. **Dùng `@ConditionalOnClass` nhưng quên SDK client bean.** Classpath có SDK không đồng nghĩa có bean client; cân nhắc `@ConditionalOnBean` hoặc phụ thuộc rõ ràng vào auto-configuration cung cấp client.
4. **Optional config được import trực tiếp từ core config.** Điều đó tạo liên kết cứng; công bố mỗi auto-configuration qua `AutoConfiguration.imports`.
5. **Tách class nhưng không tách dependency graph.** Nếu core module vẫn khai báo `implementation vendor-sdk`, ứng dụng core có thể vẫn nhận SDK theo dependency transitives. Đặt dependency ở integration module.
6. **Đặt optional API trong core interface.** Khi đó mọi consumer core phải hiểu SDK. Giữ API trung lập và viết adapter ở module tích hợp.
7. **Nhầm `@ConditionalOnClass` với `@ConditionalOnBean`.** Classpath presence và bean registration là hai điều kiện khác nhau.
8. **Cho rằng `after = CoreAutoConfiguration.class` tạo bean core.** Thứ tự không tạo bean; class core phải được chọn và điều kiện của nó phải khớp.
9. **Dùng component scan để tự tìm tất cả configuration.** Auto-configuration cần được đăng ký qua imports file; không mở rộng component scan toàn package thư viện.
10. **Resource imports bị ghi đè khi đóng gói.** Kiểm tra nội dung resource trong JAR cuối cùng, nhất là khi build fat JAR hoặc shade nhiều dependency.
11. **Không kiểm tra cả bốn trạng thái.** Chỉ test “SDK có” chưa chứng minh core hoạt động khi SDK thiếu, client bean vắng mặt hoặc người dùng override.
12. **Tạo quá nhiều lớp nhỏ không có ranh giới thật.** Chỉ tách theo dependency/lifecycle/ownership; không biến mỗi bean thành một auto-configuration riêng.

## 11. Cách chẩn đoán khi ứng dụng vẫn lỗi lúc SDK vắng mặt

Nếu người dùng chỉ thêm core starter nhưng gặp `NoClassDefFoundError`, hãy lần lượt:

1. Xác định class bị thiếu trong stack trace.
2. Tìm class đó trong các field, superclass, interface, annotation, return type và parameter type của core auto-configuration.
3. Kiểm tra class-level condition có nằm trên **đúng lớp chứa toàn bộ tham chiếu tùy chọn** hay không.
4. Kiểm tra optional config có bị import trực tiếp bởi core config hoặc component scan hay không.
5. Xem dependency tree để biết SDK có bị kéo vào core artifact hoặc một starter khác hay không.
6. Bật `--debug` để xem Condition Evaluation Report; kiểm tra `OnClassCondition` và lý do cấu hình bị loại/được chọn.
7. Kiểm tra file `AutoConfiguration.imports` bên trong JAR được publish, không chỉ file trong source tree.

Khi cần xác nhận classpath condition, viết test với `FilteredClassLoader` như ví dụ. Test này có giá trị vì nó làm cho class thật sự không thể được tìm thấy qua classloader của application context.

## 12. Kiểm tra artifact sau khi build

Khi phát hành thư viện, hãy kiểm tra **JAR thực tế**:

~~~bash
# Liệt kê auto-configuration imports trong artifact
jar tf build/libs/acme-notification-autoconfigure.jar

# Xem nội dung file imports (tùy môi trường có thể giải nén JAR trước)
jar xf build/libs/acme-notification-autoconfigure.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Trên Windows cũng có thể dùng PowerShell `jar tf ...` và `jar xf ...` nếu JDK nằm trong PATH. Sau khi trích xuất, mở đúng file imports để xác nhận các lớp core/optional được liệt kê theo thiết kế.

Đối với artifact integration riêng, xác nhận:
- JAR integration chứa optional auto-configuration.
- JAR core không chứa tham chiếu trực tiếp đến SDK tùy chọn.
- Dependency graph core không kéo SDK Vendor nếu người dùng không chọn integration.
- Resource imports của từng artifact được merge đúng khi tạo ứng dụng cuối.
- Một smoke test khởi động context với core-only classpath vẫn thành công.

Không cần khởi động hệ thống bên ngoài để kiểm tra classpath condition; dùng test context nhỏ trước, sau đó bổ sung integration test cho SDK thật khi cần.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Core auto-configuration có một method nhận `com.vendor.sdk.Client`. Đặt `@ConditionalOnClass(name="com.vendor.sdk.Client")` trên method đó đã đủ an toàn khi SDK có thể thiếu chưa?

**Đáp án:** Không nên dựa vào cách đó. JVM có thể phải resolve method signature trước khi condition trên method được áp dụng. Tách method vào configuration riêng có class-level condition.

**Câu 2.** SDK có trên classpath nhưng chưa có bean client. `@ConditionalOnClass` có bảo đảm adapter được tạo không?

**Đáp án:** Không. Nó chỉ kiểm tra classpath. Cần bean client thực tế; dùng `@ConditionalOnBean` hoặc một dependency bắt buộc rõ ràng.

**Câu 3.** Nếu core config `@Import(VendorSmsAutoConfiguration.class)`, việc tách thành nhiều lớp đã loại được phụ thuộc chưa?

**Đáp án:** Chưa chắc. Core vẫn tham chiếu trực tiếp lớp optional. Hãy để mỗi auto-configuration được đăng ký độc lập qua `AutoConfiguration.imports`.

**Câu 4.** Có nên đặt `SmsClient` trong interface core `SmsSender` không?

**Đáp án:** Không nếu muốn core độc lập với SDK. Giữ contract trung lập; implementation ở integration module mới biết kiểu vendor.

**Câu 5.** Khi SDK vắng mặt, điều gì phải tiếp tục hoạt động?

**Đáp án:** Các core bean không tham chiếu SDK phải được đăng ký và context phải khởi động bình thường; optional adapter không được tạo.

## 14. Ghi nhớ khi thiết kế thư viện

Tách auto-configuration theo **ranh giới dependency**:

- Core auto-configuration chỉ tham chiếu API và implementation cốt lõi.
- Mỗi integration tùy chọn có configuration riêng, được bảo vệ bằng `@ConditionalOnClass` ở **cấp class**.
- Nếu class có trên classpath nhưng bean client chưa được tạo, dùng `@ConditionalOnBean` để kiểm tra bean.
- Dùng `@ConditionalOnMissingBean` để ứng dụng thay thế adapter mặc định.
- Dùng `@AutoConfiguration(after = ...)` hoặc `afterName = ...` khi thực sự cần thứ tự đăng ký definitions.
- Đăng ký từng auto-configuration bằng `AutoConfiguration.imports`; không để core import cứng các lớp optional.
- Khi cần cô lập dependency ở build graph, tách artifact/module riêng. Classpath condition vẫn hữu ích khi SDK có thể vắng mặt ở runtime.

Một thư viện tốt cho phép người dùng chỉ thêm đúng phần họ cần. Ranh giới module, kiểu API trung lập và class-level condition giúp phần core giữ được tính độc lập khi các tích hợp tùy chọn thay đổi hoặc không được cài đặt.

### Tài liệu Spring Boot chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration: Class Conditions and Bean Conditions](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 Javadoc — @ConditionalOnClass](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot 3.3 Javadoc — @AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 Javadoc — @ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html)
- [Spring Boot 3.3 Javadoc — @ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
