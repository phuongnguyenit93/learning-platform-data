# @Profile trong cấu hình có điều kiện và mối quan hệ với nhóm annotation của Boot

> **Mục tiêu:** Hiểu `@Profile` quyết định có đăng ký cấu hình/bean theo **profile đang hoạt động** như thế nào, phân biệt nó với các annotation điều kiện của **Spring Boot Auto Configuration**, và biết cách kết hợp nhiều điều kiện mà không vô tình mở hoặc tắt tính năng ở một môi trường.

Trong hệ sinh thái Spring, **profile** là nhãn logic của môi trường hoặc biến thể triển khai (ví dụ `dev`, `staging`, `prod`). `@Profile` thuộc **Spring Framework**, không phải annotation do Spring Boot tạo riêng. Nó là một dạng `@Conditional`, còn Spring Boot cung cấp thêm nhiều annotation điều kiện chuyên dụng, như `@ConditionalOnProperty`, `@ConditionalOnClass` và `@ConditionalOnMissingBean`. Các cơ chế này có thể cùng xuất hiện trong một lớp `@Configuration` hoặc một phương thức `@Bean`.

Bài học dùng Java 17+ với API của Spring Boot 3.3 / Spring Framework 6.1. Các ví dụ không giả định rằng chỉ cần đặt tên profile là ứng dụng có thể tự kết nối database hay bật/tắt mọi chức năng: profile là **một điều kiện đăng ký bean**, không phải một bộ tính năng hoàn chỉnh.

## 1. Từ @Conditional đến @Profile và điều kiện của Boot

Ở mức nền tảng, Spring kiểm tra `Condition` trong lúc xử lý metadata cấu hình và quyết định có đăng ký bean definition hay không. `@Profile` được định nghĩa với meta-annotation `@Conditional(ProfileCondition.class)`; điều kiện của nó hỏi `Environment` rằng biểu thức profile yêu cầu có khớp hay không.

Spring Boot xây trên nền tảng đó:

- `@AutoConfiguration` là lớp cấu hình tự động được Boot tìm và áp dụng; bản chất nó là cấu hình Spring.
- `@ConditionalOnProperty` kiểm tra thuộc tính trong `Environment`.
- `@ConditionalOnClass` hoặc `@ConditionalOnMissingClass` kiểm tra sự hiện diện của lớp.
- `@ConditionalOnBean` hoặc `@ConditionalOnMissingBean` kiểm tra bean definition phù hợp đã được xử lý tới thời điểm đánh giá.
- `@ConditionalOnResource` kiểm tra tài nguyên.
- `@ConditionalOnWebApplication`, `@ConditionalOnNotWebApplication` kiểm tra kiểu ứng dụng web.
- `@ConditionalOnExpression` kiểm tra biểu thức SpEL; khi biểu thức trực tiếp tham chiếu một bean, nó có thể khiến bean đó được tạo quá sớm, nên cần thận trọng.

**Sự khác biệt về câu hỏi:** `@Profile("prod")` hỏi “có profile `prod` đang hiệu lực không?”, còn `@ConditionalOnProperty(prefix="demo.audit", name="enabled", havingValue="true")` hỏi “giá trị hiệu lực của `demo.audit.enabled` có bằng `true` không?”. Một ứng dụng có thể chạy profile `prod` nhưng thuộc tính `demo.audit.enabled=false`, hoặc profile `dev` nhưng tính năng được bật. Hai điều kiện không tự suy ra nhau.

**Thời điểm quan trọng:** Kết quả điều kiện tác động tới việc đăng ký cấu hình/bean khi context được xây dựng. Sau khi context đã khởi tạo, đổi một biến môi trường hoặc chỉnh file YAML không tự đăng ký lại bean từng bị loại. Nếu yêu cầu chuyển trạng thái ngay trong runtime, cần một cơ chế quản lý tính năng động phù hợp; đừng coi `@Profile` là một runtime feature flag.

## 2. @Profile có thể đặt ở đâu?

### Đặt trên lớp @Configuration

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("dev")
class DevelopmentConfiguration {
    @Bean
    String debugBanner() {
        return "Debug mode";
    }
}
~~~

Khi `dev` khớp, lớp cấu hình đủ điều kiện để được xử lý và bean `debugBanner` có thể được đăng ký; khi không khớp, các `@Bean` trong lớp và những `@Import` gắn với cấu hình đó bị bỏ qua. Việc annotation nằm trên lớp giúp giới hạn cả nhóm bean cùng lúc.

### Đặt trên một phương thức @Bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
class TransportConfiguration {
    @Bean
    @Profile("dev")
    String localTransport() {
        return "in-memory";
    }

    @Bean
    @Profile("prod")
    Integer productionPort() {
        return 443;
    }
}
~~~

Đây là ví dụ minh họa **hai bean độc lập, khác kiểu và khác tên**, mỗi bean có điều kiện riêng; nó không mô phỏng một interface transport thật. Nếu `dev` hoạt động, `localTransport` có thể được đăng ký; nếu `prod` hoạt động, `productionPort` có thể được đăng ký. Nếu đồng thời bật cả `dev` và `prod`, **cả hai** có thể được đăng ký: profile không mặc định là nhóm loại trừ lẫn nhau.

`@Profile` còn dùng trên các lớp `@Component`/stereotype, hoặc làm meta-annotation cho annotation do ứng dụng tự định nghĩa.

**Lưu ý với `@ConfigurationProperties`:** Khi class properties được phát hiện bằng scanning, có thể đặt `@Profile` trên class properties. Khi properties bean được đăng ký qua `@EnableConfigurationProperties`, đặt `@Profile` trên lớp `@Configuration` chứa `@EnableConfigurationProperties`. Đây là hai đường đăng ký khác nhau; đừng giả định annotation trên class properties luôn được xét hệt nhau trong mọi đường.

## 3. Cú pháp biểu thức profile: OR, AND, NOT

Spring Framework hỗ trợ biểu thức profile với toán tử `!` (phủ định), `&` (và), `|` (hoặc), dấu ngoặc và nhiều chuỗi biểu thức.

| Cú pháp | Điều kiện khớp | Điểm cần lưu ý |
| --- | --- | --- |
| `@Profile("dev")` | `dev` hiệu lực | Chọn một profile cụ thể. |
| `@Profile({"dev", "staging"})` | `dev` **hoặc** `staging` hiệu lực | Nhiều phần tử của mảng có nghĩa **OR**, không phải AND. |
| `@Profile("dev & cloud")` | Cả `dev` và `cloud` hiệu lực | Dùng một biểu thức chứa `&` khi cần đồng thời. |
| `@Profile("dev | staging")` | `dev` hoặc `staging` hiệu lực | Một biểu thức OR, tương tự mảng hai phần tử. |
| `@Profile("!prod")` | `prod` không hiệu lực | Có thể đúng cả khi **không khai báo** active profile. |
| `@Profile("dev & !cloud")` | `dev` hiệu lực và `cloud` không hiệu lực | Điều kiện kết hợp có phủ định. |
| `@Profile("(dev & cloud) | staging")` | (`dev` và `cloud`) hoặc `staging` | Khi trộn `&` với `|` phải **dùng ngoặc**. |
| `@Profile("default")` | Profile mặc định `default` được sử dụng | Thường xảy ra khi không có active profile được chỉ định. |

Không viết `@Profile("dev & cloud | staging")` vì trộn `&` và `|` mà không có ngoặc là biểu thức không hợp lệ. Viết `@Profile("(dev & cloud) | staging")` hoặc `@Profile("dev & (cloud | staging)")` theo đúng logic mong muốn.

Cạm bẫy hay gặp là `@Profile({"dev", "!prod"})`. Dấu phẩy ở đây là **OR**: trong môi trường `staging` (không phải `prod`), nhánh `!prod` đã đúng, vì thế bean có thể được đăng ký dù profile `dev` không hiện diện. Nếu mong muốn “dev và không prod”, dùng `@Profile("dev & !prod")`.

**Profile mặc định:** Khi không chỉ định active profile, Spring dùng tập default profile, mặc định gồm `default`. Có thể thay bằng `spring.profiles.default`. `@Profile("!prod")` khi đó thường vẫn khớp, trong khi `@Profile("prod")` không khớp. Phân biệt `getActiveProfiles()` (có thể là mảng rỗng) với tập default profile được sử dụng khi active profile trống.

## 4. Spring Boot xác định profile đang hiệu lực bằng cách nào?

Spring Boot dùng `Environment` để quản lý active/default profiles. Những cách cấu hình phổ biến:

~~~properties
# application.properties ở tài liệu không gắn profile cụ thể
spring.profiles.active=dev
~~~

~~~bash
# Cấu hình qua tham số dòng lệnh
java -jar app.jar --spring.profiles.active=staging
~~~

Hoặc dùng biến môi trường `SPRING_PROFILES_ACTIVE=prod` do hệ điều hành, IDE hoặc container cung cấp. Thứ tự ưu tiên `PropertySource` quyết định giá trị `spring.profiles.active` có hiệu lực nếu nhiều nguồn cùng khai báo: ví dụ command line thường ghi đè giá trị trong file cấu hình. Không suy ra active profile chỉ từ file đang mở; khi debug phải xem trạng thái thực của tiến trình.

Spring Boot còn hỗ trợ:

- `spring.profiles.include` để **bổ sung** profile, thay vì thay thế danh sách profile đang active.
- `spring.profiles.group.production=proddb,prodmq` để kích hoạt nhóm logic: bật `production` sẽ kích hoạt cả những profile thành viên.
- `spring.config.activate.on-profile=prod` để điều kiện hóa **một tài liệu config data**; đây là quy tắc nạp tài liệu properties/YAML, khác với `@Profile` điều kiện hóa bean definition.
- Các file `application-dev.yml`, `application-prod.properties` được nạp theo profile đã kích hoạt và theo thứ tự config data.

Ví dụ YAML nhiều tài liệu:

~~~yaml
# application.yml - tài liệu chung
sample:
  audit:
    enabled: false
---
spring:
  config:
    activate:
      on-profile: "dev"
sample:
  audit:
    enabled: true
~~~

Với `dev`, tài liệu thứ hai cung cấp giá trị `sample.audit.enabled=true`; với `prod`, tài liệu thứ hai không được kích hoạt. Đây là **hai tầng điều kiện liên quan nhưng độc lập**: profile quyết định tải tài liệu nào, rồi property cuối cùng được resolve qua các `PropertySource` và có thể chi phối `@ConditionalOnProperty`. Biến môi trường hay command-line có thể ghi đè giá trị trong YAML.

**Quy tắc giới hạn:** `spring.profiles.active`, `spring.profiles.default`, `spring.profiles.include` và `spring.profiles.group` phải được khai báo trong tài liệu **không gắn riêng một profile**, không đặt trong `application-dev.yml` hoặc tài liệu có `spring.config.activate.on-profile`. Nếu đưa sai vị trí, Boot có thể báo lỗi config data thay vì áp dụng profile như mong muốn.

## 5. Mối quan hệ với nhóm annotation điều kiện của Boot

Các điều kiện **trên cùng một đối tượng cấu hình/bean** phải cùng thỏa để thành phần được đăng ký. Ví dụ:

~~~java
@AutoConfiguration
@Profile("dev | staging")
@ConditionalOnClass(name = "com.example.vendor.AuditClient")
class AuditAutoConfiguration {
    @Bean
    @ConditionalOnProperty(
            prefix = "sample.audit",
            name = "enabled",
            havingValue = "true")
    @ConditionalOnMissingBean(AuditService.class)
    AuditService auditService() {
        // Minh họa phương thức bên trong một thư viện có sẵn AuditService.
        return new AuditService();
    }
}
~~~

*Đây là mã **minh họa cấu trúc**, chưa phải tệp Java độc lập chạy được:* `AuditService` và lớp thư viện `com.example.vendor.AuditClient` chưa được định nghĩa trong đoạn này. Ví dụ kiểm thử hoàn chỉnh ở phần 6 sử dụng các kiểu sẵn có và tự định nghĩa.

Với cấu trúc trên, xét theo thứ tự logic:

1. **Cấp lớp:** Profile phải là `dev` hoặc `staging` **và** dependency `AuditClient` có trên classpath. Nếu một trong hai sai, lớp auto-configuration không được áp dụng.
2. **Cấp method:** Khi lớp đã đủ điều kiện, thuộc tính `sample.audit.enabled` phải có giá trị `true` **và** chưa có bean `AuditService` phù hợp đã được xử lý để đăng ký fallback.
3. **Khi tạo object:** Sau khi bean definition đã được đăng ký, Spring mới tạo đối tượng theo phụ thuộc. Điều kiện bean definition không nhất thiết buộc object phải được khởi tạo trước.

Có thể ký hiệu điều kiện tổng hợp:

~~~text
register(auditService) =
    (profile = dev OR profile = staging)
AND (class com.example.vendor.AuditClient is present)
AND (sample.audit.enabled = true)
AND (matching AuditService bean is missing at evaluation time)
~~~

Điều này **không** có nghĩa bốn annotation có thể thay thế cho nhau:

| Annotation | “Câu hỏi” mà điều kiện trả lời | Dùng khi |
| --- | --- | --- |
| Spring `@Profile` | Profile/biểu thức nào đang hiệu lực? | Phân nhánh cấu hình theo môi trường hoặc biến thể triển khai. |
| Boot `@ConditionalOnProperty` | Khóa `Environment` có giá trị được yêu cầu không? | Bật/tắt tính năng qua config và override khi triển khai. |
| Boot `@ConditionalOnClass` | Dependency/class có mặt trên classpath không? | Chỉ cấu hình integration khi thư viện tồn tại. |
| Boot `@ConditionalOnMissingBean` | Có bean phù hợp được khai báo trước đó chưa? | Cung cấp mặc định và nhường quyền cho bean do ứng dụng tự định nghĩa. |
| Boot `@ConditionalOnBean` | Đã có bean dependency phù hợp chưa? | Chỉ cấu hình phần bổ sung khi dependency bean đã xuất hiện. |
| Boot `@ConditionalOnResource` | Resource được chỉ định có hiện diện không? | Chỉ mở cấu hình khi có tệp/tài nguyên bắt buộc. |
| Boot `@ConditionalOnWebApplication` | Đây là web application đúng loại không? | Điều kiện hóa cấu hình Servlet/Reactive. |
| Boot `@ConditionalOnExpression` | Biểu thức SpEL có trả về true không? | Điều kiện khó diễn đạt bằng nhóm có sẵn; tránh tham chiếu bean trong expression nếu có thể. |

Hai điểm thiết kế quan trọng:

- **Ưu tiên mục đích, không “nhét” mọi điều kiện vào một bean.** Nếu thư viện có chức năng tùy chọn, `@ConditionalOnClass` + `@ConditionalOnProperty` + `@ConditionalOnMissingBean` thường thể hiện rõ hợp đồng hơn ràng buộc cứng vào một profile `dev`/`prod` của người dùng. `@Profile` hợp lý khi thành phần về bản chất chỉ thuộc một môi trường cụ thể.
- **Thứ tự bean vẫn quan trọng.** `@ConditionalOnBean` và `@ConditionalOnMissingBean` chỉ quan sát những bean definition đã xử lý tại thời điểm xét. Boot khuyến nghị các điều kiện này trong auto-configuration (được xử lý sau cấu hình người dùng) và yêu cầu sắp thứ tự auto-configurations khi phụ thuộc lẫn nhau. `@Profile` không thay thế thứ tự đăng ký; `@DependsOn` lại liên quan giai đoạn khởi tạo object.

### Cấp lớp và cấp @Bean tạo ra phép “AND” ở hai tầng

Nếu lớp có `@Profile("dev")` mà method có `@ConditionalOnProperty(... havingValue="true")`, **cả hai** phải khớp. Nếu lớp không khớp, method không có cơ hội đăng ký bean, kể cả property bằng `true`. Nếu lớp khớp nhưng method không khớp, có thể vẫn có class cấu hình, nhưng không có bean từ method đó.

Không nên coi `@Profile({"dev", "staging"})` là phép AND rồi cho rằng phải bật đồng thời cả hai; nó là OR ở **bên trong một annotation**. Ngược lại, hai annotation điều kiện khác nhau trên cùng class là nhiều cổng kiểm tra phải cùng đạt.

## 6. Bài kiểm thử Java 17+ chạy được: profile + class + property + bean

Để quan sát đúng cơ chế mà không phải chạy cả ứng dụng web, sử dụng `ApplicationContextRunner` của Spring Boot. Đây là **một tệp test Java độc lập về mặt mã nguồn**, cần dự án có Spring Boot 3.3 và dependency test `spring-boot-starter-test` (JUnit Jupiter + AssertJ).

**Tệp:** `src/test/java/example/conditions/ProfileConditionTest.java`

~~~java
package example.conditions;

import java.time.Clock;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

import static org.assertj.core.api.Assertions.assertThat;

class ProfileConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(AuditAutoConfiguration.class));

    private ApplicationContextRunner profile(String profileName) {
        return runner.withInitializer(context ->
                context.getEnvironment().setActiveProfiles(profileName));
    }

    @Test
    void devWithEnabledFlagRegistersAutoBean() {
        profile("dev")
                .withPropertyValues("sample.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditSink.class);
                    assertThat(context.getBean(AuditSink.class).source())
                            .isEqualTo("auto");
                });
    }

    @Test
    void stagingWithEnabledFlagRegistersAutoBean() {
        profile("staging")
                .withPropertyValues("sample.audit.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(AuditSink.class));
    }

    @Test
    void productionProfileRejectsAutoConfiguration() {
        profile("prod")
                .withPropertyValues("sample.audit.enabled=true")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    @Test
    void devWithDisabledFlagRejectsBeanMethod() {
        profile("dev")
                .withPropertyValues("sample.audit.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    @Test
    void devWithoutFlagRejectsBeanMethod() {
        profile("dev")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    @Test
    void userBeanOverridesAutoDefault() {
        profile("dev")
                .withPropertyValues("sample.audit.enabled=true")
                .withUserConfiguration(UserAuditConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditSink.class);
                    assertThat(context.getBean(AuditSink.class).source())
                            .isEqualTo("user");
                    assertThat(context).doesNotHaveBean("auditSink");
                });
    }

    record AuditSink(String source) {}

    @AutoConfiguration
    @Profile("dev | staging")
    @ConditionalOnClass(Clock.class)
    static class AuditAutoConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "sample.audit",
                name = "enabled",
                havingValue = "true")
        @ConditionalOnMissingBean(AuditSink.class)
        AuditSink auditSink() {
            return new AuditSink("auto");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserAuditConfiguration {
        @Bean
        AuditSink customAuditSink() {
            return new AuditSink("user");
        }
    }
}
~~~

**Cách chạy** trong một dự án Maven hoặc Gradle có JUnit 5:

~~~bash
mvn -Dtest=ProfileConditionTest test
# Hoặc với Gradle wrapper trên Linux/macOS:
./gradlew test --tests example.conditions.ProfileConditionTest
~~~

**Kết quả mong đợi:** **6 bài test PASS**, không có stdout chương trình được bảo đảm vì các method chỉ chứa assertion. Test đã kiểm tra đủ các nhánh quan trọng:

- Profile `dev` hoặc `staging` + flag `true` → auto bean được đăng ký.
- Profile `prod` + flag `true` → lớp `@AutoConfiguration` bị chặn bởi `@Profile`.
- Profile `dev` + flag `false` hoặc thiếu flag → phương thức `@Bean` bị chặn bởi `@ConditionalOnProperty`.
- Profile `dev` + flag `true` + user bean → `@ConditionalOnMissingBean` cho auto bean mặc định nhường chỗ; bean `customAuditSink` do người dùng cấu hình được giữ lại.

`@ConditionalOnClass(Clock.class)` trong ví dụ luôn khớp trên Java 17+, do `java.time.Clock` có sẵn trong JDK; mục đích là minh họa thêm **một cổng phụ thuộc classpath** ở cấp lớp. Để thử nhánh class vắng mặt, thay dependency mô phỏng bằng một lớp của thư viện tùy chọn và kiểm tra với `FilteredClassLoader` của Boot.

Các class trong test được truyền **trực tiếp** vào `AutoConfigurations.of(...)`, vì vậy không cần file `AutoConfiguration.imports`. Khi đóng gói thành starter để Boot tự phát hiện, các class auto-configuration nên đặt ở package riêng, không bị component scan, và liệt kê tên lớp trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Với nested class, tên nhị phân chứa dấu `$`; trong thư viện thực tế nên cân nhắc cấu hình top-level để dễ duy trì.

### Đọc “bảng chân trị” của ví dụ

| Profile | `sample.audit.enabled` | Đã có user `AuditSink`? | Kết quả |
| --- | --- | --- | --- |
| `dev` | `true` | Chưa | Tạo `auditSink` từ auto-configuration |
| `staging` | `true` | Chưa | Tạo `auditSink` từ auto-configuration |
| `prod` | `true` | Chưa | Không tạo `auditSink` (profile không khớp) |
| `dev` | `false` | Chưa | Không tạo `auditSink` (property không khớp) |
| `dev` | Không có khóa | Chưa | Không tạo `auditSink` (mặc định `matchIfMissing=false`) |
| `dev` | `true` | Có | Giữ user bean; auto bean mặc định không đăng ký |

Nếu dùng `@ConditionalOnProperty` **mà không đặt `havingValue="true"`**, mọi giá trị có mặt và khác chuỗi `false` đều có thể khớp (ví dụ `custom`). Do đó với cờ bật/tắt hãy ghi rõ `havingValue` để tránh diễn giải sai.

## 7. Cách debug khi @Profile và condition của Boot cho kết quả bất ngờ

Một case điển hình: bean chỉ cần thiết trên `staging` nhưng môi trường staging lại không có bean, dù `sample.audit.enabled=true` trong file.

**Kiểm tra theo thứ tự:**

1. **Xác nhận active/default profiles thực của process.** `spring.profiles.active` trong file có thể bị override bởi command line hoặc biến môi trường; Boot cũng có `include` và `group`.
2. **Đối chiếu biểu thức `@Profile`.** Nếu viết `"dev & staging"`, phải bật đồng thời hai profile; `{"dev","staging"}` hoặc `"dev | staging"` mới là lựa chọn OR.
3. **Xem vị trí annotation.** Điều kiện trên class loại cả nhóm; điều kiện trên method chỉ quyết định bean tương ứng. Nếu class đã bị loại, mọi điều kiện method bên trong đều không cứu được nó.
4. **Kiểm tra điều kiện Boot còn lại.** Classpath có dependency yêu cầu không? Giá trị hiệu lực của property có thật là `true` không? Có user bean khiến `@ConditionalOnMissingBean` không khớp không? Đã sắp thứ tự auto-configuration cung cấp dependency trước consumer chưa?
5. **Kiểm thử theo ma trận profile × property × user bean** bằng `ApplicationContextRunner` như ở phần 6. Đây là cách phân lập nguyên nhân nhanh khi production có nhiều property source.

Đoạn mã sau là **minh họa bên trong một bean đã được inject `Environment`**, dùng để quan sát:

~~~java
import java.util.Arrays;
import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;

static void describe(Environment env) {
    System.out.println("active=" +
            Arrays.toString(env.getActiveProfiles()));
    System.out.println("default=" +
            Arrays.toString(env.getDefaultProfiles()));
    System.out.println("dev matches=" +
            env.acceptsProfiles(Profiles.of("dev")));
    System.out.println("audit flag=" +
            env.getProperty("sample.audit.enabled"));
}
~~~

Đoạn này là method minh họa, **chưa có main method và chưa tạo Spring context**. Giá trị in ra phụ thuộc môi trường đang chạy. Nhớ rằng `getActiveProfiles()` có thể rỗng dù `@Profile("default")` vẫn khớp do default profile.

Trong Spring Boot, có thể khởi động với `--debug` để xem báo cáo đánh giá điều kiện, hoặc dùng Actuator `/actuator/conditions` nếu đã thêm Actuator và cấu hình bảo vệ/expose endpoint. **Giới hạn cần nhớ:** báo cáo conditions của Boot tập trung vào các Boot condition được theo dõi; không nên giả định mọi lần đánh giá `@Profile` của Spring Framework sẽ hiện thành một mục riêng. Hãy đối chiếu thêm active profiles và bean thực sự có trong context. Các endpoint chẩn đoán không nên được công khai trên production.

## 8. Lỗi phổ biến và cách thiết kế tốt hơn

**Lỗi 1 — Dùng @Profile thay cho property flag.** Muốn tính năng dùng chung ở mọi môi trường nhưng cho phép bật/tắt từ cấu hình, thường `@ConditionalOnProperty` phù hợp hơn. Profile dành cho lựa chọn theo nhóm môi trường, không phải cho mọi tùy chọn boolean của một tính năng.

**Lỗi 2 — Xem profile là các nhãn loại trừ nhau.** Spring có thể có nhiều active profiles. `@Profile("dev")` và `@Profile("prod")` đều khớp nếu cả hai nhãn cùng active. Không đặt giả định “chỉ có một” nếu phần khởi động không bảo đảm điều đó.

**Lỗi 3 — Dùng @Profile("!prod") để mô tả an toàn.** Phủ định `prod` cũng cho phép `default`, `test` hoặc `staging`; biểu thức này khá rộng. Khi yêu cầu rõ “chỉ dev”, `@Profile("dev")` chặt chẽ hơn.

**Lỗi 4 — Trộn AND/OR sai.** Mảng `@Profile({"dev", "test"})` là OR, trong khi `@Profile("dev & test")` mới là AND. Viết dấu ngoặc khi có cả `&` và `|` trong một biểu thức.

**Lỗi 5 — Dùng @Profile để chọn method @Bean overload.** Spring Framework có lưu ý đặc biệt: với các method `@Bean` overload **trùng tên Java method**, điều kiện `@Profile` không được dùng như cơ chế chọn overload dựa trên signature; nếu muốn hai phương thức thay thế nhau theo profile, đặt **tên Java method khác nhau** và dùng tên bean chung khi thiết kế phù hợp, đồng thời bảo đảm điều kiện profile loại trừ nhau để tránh xung đột.

**Lỗi 6 — Nhầm @Profile với @ActiveProfiles.** `@Profile` gắn trên cấu hình/bean để điều kiện hóa đăng ký. `@ActiveProfiles` thuộc Spring Test, dùng để cấu hình active profiles cho **test context**; nó không phải annotation cần gắn lên business bean trong production.

**Lỗi 7 — Không chú ý bean-condition timing.** `@ConditionalOnMissingBean` nhìn những bean definition đã có khi điều kiện chạy; nếu một auto-configuration khác cung cấp bean sau đó, có thể có hai ứng viên. Sắp thứ tự bằng `@AutoConfiguration(after = ...)` hoặc `@AutoConfigureAfter` khi cần; không dùng `@DependsOn` như cách chữa thứ tự condition.

**Lỗi 8 — Nhét spring.profiles.active vào tài liệu đã active theo profile.** Spring Boot 3.3 không cho cấu hình `spring.profiles.active` trong profile-specific document. Đặt ở tài liệu không gắn profile, hoặc cung cấp tại lúc chạy từ môi trường/command line.

## 9. Bài tập tự kiểm tra

1. Có active profile duy nhất `staging`. `@Profile({"dev", "!prod"})` có khớp không? **Có**, vì `!prod` đúng; nhiều phần tử của mảng là OR.
2. Có `dev` và `cloud`. `@Profile("dev & !cloud")` có khớp không? **Không**, do `!cloud` sai.
3. Có `dev`, property `sample.audit.enabled=false`, bean được đánh dấu cả `@Profile("dev")` lẫn `@ConditionalOnProperty(... havingValue="true")`. Có đăng ký không? **Không**, vì property-condition không khớp.
4. Property có giá trị `true`, nhưng class ở cấp trên có `@Profile("prod")` và active profile là `dev`. Method `@Bean` có được xét để đăng ký không? **Không**, lớp cấu hình đã bị bỏ qua.
5. Không khai báo profile nào và không thay default profile. `@Profile("default")` có thể khớp không? **Có**, vì `default` là profile mặc định.
6. Khi phát triển starter, cần bỏ mặc định nếu ứng dụng có bean riêng. Dùng gì? **`@ConditionalOnMissingBean` trên auto-configuration**, kết hợp với các cổng profile/property/class chỉ khi có yêu cầu nghiệp vụ tương ứng.

## Tài liệu chính thức để đối chiếu

- [Spring Framework 6.1 — @Profile Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/context/annotation/Profile.html): phạm vi áp dụng, cấu hình method/class, OR trong mảng, chú ý overload của `@Bean`.
- [Spring Framework 6.1 — Profiles API](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/core/env/Profiles.html): biểu thức profile với `!`, `&`, `|` và dấu ngoặc.
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html): active/default profiles, `include`, profile group, file cấu hình theo profile và giới hạn vị trí cấu hình.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): nhóm annotation điều kiện, thứ tự auto-configuration và `ApplicationContextRunner`.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): endpoint chẩn đoán `conditions` và cách kiểm soát exposure.

**Ghi nhớ:** `@Profile` là một **điều kiện của Spring Framework dựa trên profile**, có thể ghép với các điều kiện Boot như những cổng **AND**. Chọn đúng annotation theo câu hỏi đang muốn kiểm tra, phân biệt rõ cấp lớp với cấp `@Bean` và kiểm chứng bằng các tổ hợp profile, property, classpath và bean thực tế.
