# Nhường chỗ theo từng bean thay vì tắt toàn bộ một nhóm cấu hình

> **Nguyên tắc thiết kế:** Khi một Spring Boot auto-configuration cung cấp nhiều bean mặc định, ứng dụng chỉ cần thay thế bean nào thì **bean mặc định tương ứng** nên nhường chỗ; các bean mặc định khác vẫn được giữ nếu chưa có phiên bản do ứng dụng cung cấp. Hãy cân nhắc đặt `@ConditionalOnMissingBean` trên **từng phương thức `@Bean`** để đạt mức thay thế này, thay vì đặt một điều kiện thiếu bean ở cấp toàn bộ auto-configuration rồi vô tình loại cả nhóm.

Bài học thuộc **Spring Boot Auto Configuration → Thay thế và loại trừ**. Nó giải thích sự khác nhau giữa *back-off theo từng bean*, *điều kiện cấp lớp* và *loại trừ toàn bộ auto-configuration*; cách tổ chức một thư viện có các mặc định độc lập; cách kiểm thử bằng `ApplicationContextRunner` trên Spring Boot 3.3, Java 17+.

## 1. Bài toán: một nhóm cấu hình cung cấp nhiều chức năng

Giả sử một thư viện báo cáo cung cấp sẵn ba thành phần:

1. `Encoder`: chuyển nội dung sang biểu diễn phù hợp.
2. `Exporter`: xuất dữ liệu đã mã hóa.
3. `ReportPipeline`: phối hợp `Encoder` và `Exporter`.

Ứng dụng A muốn dùng cả ba bean mặc định. Ứng dụng B chỉ muốn thay `Encoder` để hỗ trợ định dạng riêng nhưng vẫn sử dụng `Exporter` và `ReportPipeline` do thư viện tạo. Ứng dụng C muốn thay `Exporter` mà không đụng đến `Encoder`.

Nếu chỉ cần một `Encoder` do người dùng khai báo đã làm **cả auto-configuration biến mất**, ứng dụng B sẽ mất `Exporter` và `ReportPipeline` không liên quan tới việc thay thế. Hậu quả có thể là thiếu bean, lỗi dependency injection, hoặc người dùng phải tự cấu hình lại toàn bộ thư viện.

Mong muốn đúng ở đây là **thay thế có chọn lọc**:

| Bean do ứng dụng khai báo | Default `Encoder` của thư viện | Default `Exporter` của thư viện | Default `ReportPipeline` của thư viện |
| --- | --- | --- | --- |
| Không có bean riêng | Đăng ký | Đăng ký | Đăng ký |
| Có `Encoder` riêng | Nhường chỗ | Vẫn đăng ký | Vẫn đăng ký, dùng `Encoder` riêng |
| Có `Exporter` riêng | Vẫn đăng ký | Nhường chỗ | Vẫn đăng ký, dùng `Exporter` riêng |
| Có cả `Encoder` và `Exporter` riêng | Nhường chỗ | Nhường chỗ | Vẫn đăng ký, dùng cả hai bean riêng |
| Có `ReportPipeline` riêng | Vẫn đăng ký nếu còn thiếu | Vẫn đăng ký nếu còn thiếu | Nhường chỗ |

Bảng giả định các bean thỏa điều kiện tìm kiếm thông thường, chỉ có một bean phù hợp cho mỗi dependency, và không có điều kiện cấp lớp nào chặn cả cấu hình. Nếu có nhiều ứng viên cùng kiểu, quá trình tiêm dependency còn phụ thuộc `@Primary`, `@Qualifier` hoặc cơ chế chọn bean khác.

**Phân biệt các bước:** “Nhường chỗ” ở đây nghĩa là **không đăng ký bean definition mặc định** khi condition phát hiện bean phù hợp đã được đăng ký; nó không phải xóa một object bean đã tạo trước đó hay tự thay đổi object lúc runtime.

## 2. Vì sao điều kiện cấp lớp thường quá rộng?

Ví dụ sau là **mẫu thiết kế không phù hợp với yêu cầu thay thế riêng từng bean**:

~~~java
// Mã minh họa cấu trúc; Encoder, Exporter và ReportPipeline
// là các kiểu do thư viện tự định nghĩa ở các phần dưới.
@AutoConfiguration
@ConditionalOnMissingBean(Encoder.class)
class ReportAutoConfiguration {
    @Bean
    Encoder encoder() {
        return new DefaultEncoder();
    }

    @Bean
    Exporter exporter() {
        return new DefaultExporter();
    }

    @Bean
    ReportPipeline reportPipeline(Encoder encoder, Exporter exporter) {
        return new ReportPipeline(encoder, exporter);
    }
}
~~~

Nếu ứng dụng đã đăng ký **một** bean `Encoder`:

- Điều kiện `@ConditionalOnMissingBean(Encoder.class)` **ở cấp lớp** không khớp.
- Toàn bộ lớp `ReportAutoConfiguration` không được đăng ký theo nhánh này.
- Các phương thức `exporter()` và `reportPipeline()` cũng không được dùng để cung cấp default.
- Những bean đó **có thể vẫn tồn tại** nếu được cấu hình ở nơi khác, nhưng auto-configuration này không còn cung cấp chúng.

Điều kiện cấp lớp không sai về cú pháp. Nó chỉ sai **mức độ giới hạn** nếu ý định là cho phép thay thế `Encoder` một cách độc lập. Điều kiện cấp lớp hợp lý khi **toàn bộ** cấu hình thực sự chỉ có nghĩa nếu điều kiện đó đúng, ví dụ một integration chỉ nên được tải khi dependency bắt buộc hiện diện trên classpath.

Chính xác hơn, hai cách đặt condition có ý nghĩa khác nhau:

| Vị trí | Khi điều kiện không khớp | Phạm vi ảnh hưởng |
| --- | --- | --- |
| `@ConditionalOnMissingBean(Encoder.class)` trên class `@AutoConfiguration` | Bỏ qua class cấu hình đó | Các bean từ cả lớp không được đóng góp theo đường này |
| `@ConditionalOnMissingBean(Encoder.class)` trên method `@Bean Encoder ...` | Không đăng ký bean từ riêng method đó | Các method khác vẫn được xét nếu cấu hình cấp lớp hợp lệ |
| `@ConditionalOnProperty` trên class | Nếu flag không đạt, cả cấu hình bị bỏ qua | Thích hợp nếu cố ý bật/tắt **cả tính năng** |
| `spring.autoconfigure.exclude` hoặc `@SpringBootApplication(exclude=...)` | Auto-configuration được nêu tên bị loại khỏi tập áp dụng | Chỉ dùng khi chủ ý vô hiệu hóa **toàn bộ auto-configuration** |

**Lưu ý:** `@ConditionalOnMissingBean` là condition trong hệ thống đăng ký bean. Nó không hoàn toàn tương đương với việc “nếu khởi động bị lỗi thì tạo bean khác” và cũng không tự quay lại đánh giá nếu một bean khác được đăng ký sau.

## 3. Thiết kế đúng: mỗi bean mặc định tự kiểm tra điều kiện nhường chỗ

Viết mỗi `@Bean` với điều kiện tương ứng:

~~~java
@AutoConfiguration
class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Encoder.class)
    Encoder defaultEncoder() {
        return value -> "encoded(" + value + ")";
    }

    @Bean
    @ConditionalOnMissingBean(Exporter.class)
    Exporter defaultExporter() {
        return value -> "out[" + value + "]";
    }

    @Bean
    @ConditionalOnMissingBean(ReportPipeline.class)
    ReportPipeline defaultPipeline(Encoder encoder, Exporter exporter) {
        return new ReportPipeline("auto", encoder, exporter);
    }
}
~~~

Đoạn trên minh họa logic cấu hình; các kiểu `Encoder`, `Exporter`, `ReportPipeline` được định nghĩa đầy đủ trong test chạy được ở phần 5. Điều kiện được ghi rõ kiểu để người đọc không nhầm kiểu bean mà condition đang kiểm tra.

Ba điểm quan trọng:

**(1) Các fallback độc lập.** Có `Encoder` do người dùng đăng ký thì chỉ method `defaultEncoder()` lùi lại. Method `defaultExporter()` vẫn có thể đóng góp `Exporter` nếu chưa có bean kiểu đó. Tương tự với `ReportPipeline`.

**(2) Đăng ký definition khác với tạo object.** Khi Spring xử lý phương thức `defaultPipeline(Encoder, Exporter)`, nó có thể đăng ký definition của pipeline; các dependency `Encoder`/`Exporter` sẽ được giải quyết khi đối tượng pipeline được tạo. Spring sẽ chọn bean phù hợp hiện diện trong container (từ ứng dụng hoặc default).

**(3) Type là hợp đồng thay thế.** `@ConditionalOnMissingBean(Encoder.class)` tìm bean phù hợp theo **kiểu**, không theo tên method `defaultEncoder`. Vì vậy `@Bean Encoder preferredEncoder()` cũng khiến default encoder lùi lại. Đây thường là điều người dùng mong đợi khi cung cấp implementation tùy chỉnh.

Nếu đặt annotation `@ConditionalOnMissingBean` lên `@Bean` mà không chỉ định `value`/`type`/`name`, Spring Boot có thể suy kiểu kiểm tra từ kiểu trả về của method đó. Tuy nhiên trong thư viện công khai, viết rõ kiểu mục tiêu giúp hợp đồng dễ đọc; hãy tránh kiểu trả về quá chung như `Object` vì metadata kiểu khi đánh giá condition có thể không đủ để nhận diện các ứng viên.

### Vì sao không chỉ dùng @Primary?

`@Primary` cho Spring biết bean nào được ưu tiên chọn khi cần tiêm một bean theo type và có nhiều ứng viên. Nó **không ngăn** bean default được đăng ký.

Ví dụ một ứng dụng cung cấp `Encoder` riêng có `@Primary`, nhưng thư viện vẫn đăng ký `Encoder` default không điều kiện. Container có thể hoạt động với bean primary, song vẫn có hai bean; những chỗ inject collection `List<Encoder>`, tra bean theo tên hoặc dùng bean post-processor vẫn thấy cả hai. Khi hợp đồng mong muốn là **nhường chỗ**, điều kiện `@ConditionalOnMissingBean(Encoder.class)` thể hiện rõ hơn.

Tương tự, bật `spring.main.allow-bean-definition-overriding=true` chỉ cho phép ghi đè definition trùng **tên** theo cơ chế của container; nó không giải quyết bài toán nhường chỗ theo **kiểu** và có thể che mất cấu hình sai. Không dùng nó như cách mặc định để thiết kế một starter.

## 4. Đường đi của bean: ai tạo trước, ai phụ thuộc ai?

Spring Boot xử lý cấu hình do ứng dụng khai báo trước các auto-configuration thông thường. Vì vậy thư viện có thể dùng `@ConditionalOnMissingBean` để nhường chỗ cho bean do người dùng định nghĩa.

Giả sử app có:

~~~java
@Configuration(proxyBeanMethods = false)
class UserReportConfiguration {
    @Bean
    Encoder customEncoder() {
        return value -> "custom(" + value + ")";
    }
}
~~~

Tại thời điểm auto-configuration được xử lý:

1. Bean definition `customEncoder` đã được khai báo, với type `Encoder`.
2. `@ConditionalOnMissingBean(Encoder.class)` ở `defaultEncoder()` không khớp.
3. `@ConditionalOnMissingBean(Exporter.class)` ở `defaultExporter()` vẫn khớp nếu không có exporter khác.
4. `@ConditionalOnMissingBean(ReportPipeline.class)` vẫn khớp nếu không có pipeline khác.
5. Khi pipeline được tạo, Spring inject `customEncoder` và `defaultExporter`.

Không cần xóa auto-configuration hoặc chép lại tất cả bean mặc định. Ứng dụng thay đúng thành phần mà nó sở hữu.

**Trường hợp có nhiều auto-configuration:** Điều kiện bean chỉ nhìn những definition đã được xử lý **tại thời điểm xét**. Nếu auto-configuration A cần nhường chỗ cho bean do auto-configuration B cung cấp, phải khai báo thứ tự thích hợp, chẳng hạn `@AutoConfiguration(after = B.class)` trên A. Quan hệ `after` quyết định thứ tự **đăng ký bean definition**, không bảo đảm thứ tự tạo đối tượng. `@DependsOn` lại chủ yếu ảnh hưởng thứ tự khởi tạo, nên không sửa được lỗi condition nhìn thấy bean quá muộn.

Ví dụ quan hệ thứ tự:

~~~java
// Mã minh họa metadata; OtherProviderAutoConfiguration
// là auto-configuration khác trong cùng thư viện hoặc dependency.
@AutoConfiguration(after = OtherProviderAutoConfiguration.class)
class ReportAutoConfiguration {
    // Các @Bean riêng lẻ với @ConditionalOnMissingBean(...)
}
~~~

Đây là minh họa, không phải class độc lập vì nó chưa định nghĩa `OtherProviderAutoConfiguration`. Không sắp thứ tự bằng vị trí dòng trong file `AutoConfiguration.imports`; Boot dùng metadata `before`/`after`.

## 5. Ví dụ chạy được: thay một phần mà giữ các default khác

Tệp test sau tự định nghĩa `Encoder`, `Exporter`, `ReportPipeline` và ba user configuration khác nhau. Nó chạy với **Java 17+, Spring Boot 3.3.x, JUnit Jupiter và AssertJ**, thông qua dependency `spring-boot-starter-test`. Không yêu cầu ứng dụng web hoặc database.

**Tệp:** `src/test/java/example/autoconfig/PerBeanBackoffTest.java`

~~~java
package example.autoconfig;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class PerBeanBackoffTest {

    interface Encoder {
        String encode(String value);
    }

    interface Exporter {
        String export(String value);
    }

    record ReportPipeline(String source, Encoder encoder, Exporter exporter) {
        String run(String input) {
            return source + "|" + exporter.export(encoder.encode(input));
        }
    }

    @AutoConfiguration
    static class ReportAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(Encoder.class)
        Encoder defaultEncoder() {
            return value -> "encoded(" + value + ")";
        }

        @Bean
        @ConditionalOnMissingBean(Exporter.class)
        Exporter defaultExporter() {
            return value -> "out[" + value + "]";
        }

        @Bean
        @ConditionalOnMissingBean(ReportPipeline.class)
        ReportPipeline defaultPipeline(Encoder encoder, Exporter exporter) {
            return new ReportPipeline("auto", encoder, exporter);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserEncoderConfiguration {
        @Bean
        Encoder userEncoder() {
            return value -> "custom(" + value + ")";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserExporterConfiguration {
        @Bean
        Exporter userExporter() {
            return value -> "user-out[" + value + "]";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserPipelineConfiguration {
        @Bean
        ReportPipeline userPipeline(Encoder encoder, Exporter exporter) {
            return new ReportPipeline("user", encoder, exporter);
        }
    }

    // Mô hình cố tình sai: một Encoder của người dùng làm
    // CẢ lớp cấu hình này mất hiệu lực, kể cả defaultExporter.
    @AutoConfiguration
    @ConditionalOnMissingBean(Encoder.class)
    static class IncorrectReportAutoConfiguration {

        @Bean
        Encoder defaultEncoder() {
            return value -> "encoded(" + value + ")";
        }

        @Bean
        Exporter defaultExporter() {
            return value -> "out[" + value + "]";
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(ReportAutoConfiguration.class));

    @Test
    void withoutUserBeansRegistersAllDefaults() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Encoder.class);
            assertThat(context).hasSingleBean(Exporter.class);
            assertThat(context).hasSingleBean(ReportPipeline.class);
            assertThat(context).hasBean("defaultEncoder");
            assertThat(context).hasBean("defaultExporter");
            assertThat(context).hasBean("defaultPipeline");
            assertThat(context.getBean(ReportPipeline.class).run("hello"))
                    .isEqualTo("auto|out[encoded(hello)]");
        });
    }

    @Test
    void customEncoderOnlyReplacesEncoder() {
        runner.withUserConfiguration(UserEncoderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Encoder.class);
                    assertThat(context).hasBean("userEncoder");
                    assertThat(context).doesNotHaveBean("defaultEncoder");
                    assertThat(context).hasBean("defaultExporter");
                    assertThat(context).hasBean("defaultPipeline");
                    assertThat(context.getBean(ReportPipeline.class).run("hello"))
                            .isEqualTo("auto|out[custom(hello)]");
                });
    }

    @Test
    void customExporterOnlyReplacesExporter() {
        runner.withUserConfiguration(UserExporterConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Exporter.class);
                    assertThat(context).doesNotHaveBean("defaultExporter");
                    assertThat(context).hasBean("defaultEncoder");
                    assertThat(context).hasBean("defaultPipeline");
                    assertThat(context.getBean(ReportPipeline.class).run("hello"))
                            .isEqualTo("auto|user-out[encoded(hello)]");
                });
    }

    @Test
    void twoCustomComponentsKeepDefaultPipeline() {
        runner.withUserConfiguration(
                    UserEncoderConfiguration.class,
                    UserExporterConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Encoder.class);
                    assertThat(context).hasSingleBean(Exporter.class);
                    assertThat(context).hasSingleBean(ReportPipeline.class);
                    assertThat(context).doesNotHaveBean("defaultEncoder");
                    assertThat(context).doesNotHaveBean("defaultExporter");
                    assertThat(context).hasBean("defaultPipeline");
                    assertThat(context.getBean(ReportPipeline.class).run("hello"))
                            .isEqualTo("auto|user-out[custom(hello)]");
                });
    }

    @Test
    void customPipelineKeepsOtherDefaults() {
        runner.withUserConfiguration(UserPipelineConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("userPipeline");
                    assertThat(context).doesNotHaveBean("defaultPipeline");
                    assertThat(context).hasBean("defaultEncoder");
                    assertThat(context).hasBean("defaultExporter");
                    assertThat(context).hasSingleBean(ReportPipeline.class);
                    assertThat(context.getBean(ReportPipeline.class).run("hello"))
                            .isEqualTo("user|out[encoded(hello)]");
                });
    }

    @Test
    void classLevelConditionIncorrectlyRemovesExporter() {
        new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(
                        IncorrectReportAutoConfiguration.class))
                .withUserConfiguration(UserEncoderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(Encoder.class);
                    assertThat(context).hasBean("userEncoder");
                    assertThat(context).doesNotHaveBean("defaultEncoder");
                    assertThat(context).doesNotHaveBean(Exporter.class);
                });
    }
}
~~~

**Cách chạy** trong dự án Maven/Gradle có Spring Boot 3.3 và cấu hình chạy JUnit 5:

~~~bash
mvn -Dtest=PerBeanBackoffTest test
# Hoặc trên Linux/macOS với Gradle wrapper:
./gradlew test --tests example.autoconfig.PerBeanBackoffTest
~~~

**Kết quả mong đợi:** **6 test PASS**; không có dòng stdout cố định bởi các test chỉ dùng assertion. Kết quả quan trọng nằm ở tên bean và giá trị trả về của `run("hello")`:

| Test | Bean phải còn | Bean mặc định phải nhường | Kết quả `ReportPipeline.run("hello")` |
| --- | --- | --- | --- |
| Không có bean người dùng | 3 default | Không | `auto\|out[encoded(hello)]` |
| Thay `Encoder` | `userEncoder`, `defaultExporter`, `defaultPipeline` | `defaultEncoder` | `auto\|out[custom(hello)]` |
| Thay `Exporter` | `defaultEncoder`, `userExporter`, `defaultPipeline` | `defaultExporter` | `auto\|user-out[encoded(hello)]` |
| Thay cả hai | 2 user bean, `defaultPipeline` | `defaultEncoder`, `defaultExporter` | `auto\|user-out[custom(hello)]` |
| Thay `ReportPipeline` | `userPipeline`, hai default thành phần | `defaultPipeline` | `user\|out[encoded(hello)]` |
| Condition sai ở cấp class | Chỉ `userEncoder` | Cả class auto-config bị loại | Không có `Exporter` |

Các dấu `\|` trong cột cuối biểu diễn ký tự `|` có thật trong kết quả chuỗi Java; dấu gạch chéo ngược chỉ dùng để escape ký tự này khi viết trong bảng Markdown.

Hai lưu ý để hiểu test chính xác:

- `AutoConfigurations.of(...)` nạp lớp auto-configuration trực tiếp để kiểm thử, nên **không cần** file đăng ký `AutoConfiguration.imports` trong test. Khi đóng gói thành starter, auto-configuration thực tế cần được Boot phát hiện qua `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- Test cuối **cố ý mô phỏng thiết kế sai** và xác nhận hậu quả: có user `Encoder` thì cả `Exporter` mặc định cũng biến mất. “PASS” của test có nghĩa assertion mô tả lỗi thiết kế được tái hiện đúng, **không** có nghĩa cách cấu hình đó nên được áp dụng.

### Vì sao phần test này đáng dùng?

Nó kiểm tra hợp đồng quan trọng nhất của auto-configuration: **một thay thế cục bộ không làm mất default ở nhánh khác**. Chỉ kiểm thử “context khởi động thành công” là chưa đủ; khi xuất hiện một user bean, context có thể vẫn khởi động nhưng chức năng phụ trợ lại biến mất. Các assertion `hasBean`/`doesNotHaveBean` và output pipeline cho thấy cả **cấu trúc bean** lẫn **hành vi tích hợp**.

## 6. Chọn phạm vi điều kiện theo kiến trúc

Quy tắc “từng bean tự nhường chỗ” không có nghĩa cấm toàn bộ class-level condition. Hãy phân biệt điều kiện nào **bắt buộc cho cả nhóm** và điều kiện nào **chỉ áp dụng cho một bean cụ thể**.

Ví dụ thiết kế nhiều tầng:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.ClientLibrary")
@ConditionalOnProperty(
        prefix = "demo.integration",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
class IntegrationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Transport.class)
    Transport defaultTransport() {
        return new DefaultTransport();
    }

    @Bean
    @ConditionalOnMissingBean(Codec.class)
    Codec defaultCodec() {
        return new DefaultCodec();
    }
}
~~~

*Đây là đoạn **minh họa cấu trúc**, không độc lập biên dịch vì các kiểu `Transport`/`Codec`/`DefaultTransport`/`DefaultCodec` và lớp thư viện tùy chọn chưa được khai báo.*

- `@ConditionalOnClass` ở cấp lớp là **cổng chung**: nếu thiếu thư viện tích hợp bắt buộc thì không nên đăng ký bất kỳ default nào của integration.
- `@ConditionalOnProperty` ở cấp lớp là **cổng bật/tắt cả integration**, nếu đó đúng là ý nghĩa của flag `demo.integration.enabled`.
- `@ConditionalOnMissingBean(Transport.class)` và `@ConditionalOnMissingBean(Codec.class)` ở các method là **các cổng thay thế độc lập**.

Nếu chỉ một thành phần hỗ trợ flag riêng, đặt `@ConditionalOnProperty` trên method của thành phần ấy; không đặt flag đó trên cả lớp. Nếu một bean thực sự yêu cầu một bean khác, có thể dùng `@ConditionalOnBean` hoặc dependency injection phù hợp, nhưng phải xét rõ thứ tự đăng ký và trường hợp thiếu dependency.

Một nguyên tắc phân vùng hữu ích: **mỗi nhóm nên đại diện cho một khả năng bật/tắt độc lập**, còn các default có thể thay thế được phải có condition ở đúng phạm vi. Nếu một class trở nên quá lớn và chứa nhiều điều kiện phụ thuộc khác nhau, chia thành các nested `@Configuration(proxyBeanMethods = false)` hoặc các auto-configuration riêng là cách làm rõ ràng; nó vẫn cho phép mỗi bean default tự lùi lại.

## 7. Khi nào mới loại trừ toàn bộ auto-configuration?

Spring Boot cho phép ứng dụng loại trừ auto-configuration bằng tên class, ví dụ:

~~~properties
spring.autoconfigure.exclude=com.example.library.ReportAutoConfiguration
~~~

Hoặc bằng Java:

~~~java
@SpringBootApplication(
        exclude = ReportAutoConfiguration.class
)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Đây là **mã minh họa**: phải import `SpringBootApplication` và `SpringApplication`, và `ReportAutoConfiguration` phải là auto-configuration thực sự, có trên classpath và có thể tham chiếu từ ứng dụng. Cơ chế exclude dành cho các lớp auto-configuration được Boot phát hiện, không phải cách chung để loại mọi lớp `@Configuration` do người dùng `@Import`.

Chỉ nên dùng exclude khi có lý do ở **cấp toàn bộ module tích hợp**: ví dụ thư viện không tương thích, tất cả bean của nhánh auto-configuration phải tắt, hoặc ứng dụng muốn sở hữu hoàn toàn toàn bộ nhánh cấu hình. Khi cần thay **một** serializer/encoder/exporter, exclude toàn nhóm khiến các default hữu ích còn lại cũng bị loại và làm tăng chi phí cấu hình thủ công.

**Không nhầm ba lựa chọn:**

1. `@ConditionalOnMissingBean` ở method: *cho phép người dùng thay thế một bean mà vẫn giữ phần còn lại*.
2. `@ConditionalOnProperty` ở class: *một công tắc có chủ đích cho toàn nhóm*.
3. `spring.autoconfigure.exclude`: *bỏ hẳn auto-configuration được nêu tên khỏi tập áp dụng*.

Cùng một ứng dụng có thể sử dụng cả ba cơ chế, nhưng mỗi cơ chế giải quyết một ý định khác nhau.

## 8. Những rủi ro cần kiểm tra khi thiết kế fallback

### 8.1. Kiểm tra đúng type, không đoán theo tên

`@ConditionalOnMissingBean(Encoder.class)` phản ứng với một bean kiểu `Encoder` bất kể bean tên `userEncoder` hay `preferredEncoder`. Điều kiện theo tên như `@ConditionalOnMissingBean(name = "reportEncoder")` chỉ phù hợp nếu tên bean chính là hợp đồng mà thư viện muốn hỗ trợ. Nếu người dùng khai báo cùng kiểu nhưng khác tên, condition theo tên có thể không nhận diện được sự thay thế.

Nếu viết method trả về `Object` nhưng thực tế tạo `Encoder`, Spring Boot có thể không có đủ metadata type ở lúc condition được đánh giá. Dùng kiểu trả về cụ thể và điều kiện type rõ ràng, đặc biệt khi viết starter có nhiều bean.

### 8.2. Nhiều ứng viên không biến mất nhờ back-off

`@ConditionalOnMissingBean(Encoder.class)` tránh tạo thêm default khi **đã có** một `Encoder` phù hợp. Nó không bảo đảm user chỉ đăng ký một `Encoder`. Nếu ứng dụng khai báo hai encoder và pipeline inject một `Encoder` không có qualifier, có thể phát sinh `NoUniqueBeanDefinitionException`. Giải quyết bằng hợp đồng rõ ràng: `@Primary`, `@Qualifier`, condition `@ConditionalOnSingleCandidate` trong trường hợp thích hợp, hoặc map/collection nếu cố ý hỗ trợ nhiều implementation.

### 8.3. Không tự đặt điều kiện thiếu bean trên cấu hình người dùng

Spring Boot khuyến nghị dùng `@ConditionalOnBean` và `@ConditionalOnMissingBean` trong **auto-configuration**, vì auto-configuration được xử lý sau phần cấu hình do người dùng khai báo. Trong cấu hình người dùng hoặc component scan, thứ tự có thể không bảo đảm như ý; condition có thể chỉ thấy một phần bean definition. Với dependency đến từ auto-configuration khác, khai báo quan hệ `before`/`after` rõ ràng.

### 8.4. Tránh dùng exclusion để giải quyết một lỗi tiêm dependency

Nếu một bean auto-config mặc định dùng dependency không phù hợp, hãy kiểm tra hợp đồng của dependency đó và khả năng người dùng tự khai báo bean thay thế. Exclude toàn auto-configuration có thể xóa luôn bean phục vụ health checks, metrics hoặc infrastructure. Điều kiện cần giới hạn vừa đủ theo lý do có hoặc không có từng bean.

### 8.5. Một class-level gate có thể đúng, nhưng phải có chủ đích

Không phải mọi nhóm default đều hợp lệ ở mọi môi trường. Một số group có điều kiện thực sự chung như “chỉ chạy với Servlet”, “có JDBC driver”, “feature X được bật”. Khi đó dùng class-level `@ConditionalOnWebApplication`, `@ConditionalOnClass` hoặc `@ConditionalOnProperty` là hợp lý, kết hợp với method-level `@ConditionalOnMissingBean` cho các phần có thể thay thế.

## 9. Quan sát Condition Evaluation Report để tìm bean bị bỏ qua

Khi thấy thiếu `Exporter` sau khi khai báo `Encoder` riêng, hãy chẩn đoán theo từng lớp nguyên nhân:

1. **Xác định type và tên bean** đang tìm: gọi `applicationContext.getBeansOfType(Exporter.class)` trong test, hoặc dùng assertions của `ApplicationContextRunner`.
2. **Xem điều kiện trên class auto-configuration**: `@ConditionalOnMissingBean` đã đặt ở class chưa? Có `@ConditionalOnClass`/`@ConditionalOnProperty`/`@Profile` cấp lớp chặn toàn nhóm không?
3. **Kiểm tra condition trên method**: có đúng `@ConditionalOnMissingBean(Exporter.class)` ở `defaultExporter()` hay kiểm tra nhầm `Encoder.class`?
4. **Xem bean của người dùng**: user đã đăng ký đúng type? Return type của method `@Bean` có đủ cụ thể? Có nhiều candidate dẫn đến injection ambiguity không?
5. **Kiểm tra thứ tự auto-configuration**: dependency khác được khai báo trước hay sau? Condition bean chỉ nhìn phần đã xử lý vào thời điểm đánh giá.

Trong Spring Boot có thể khởi động với `--debug` để xem Condition Evaluation Report. Nếu có Spring Boot Actuator và được cấu hình truy cập an toàn, endpoint `/actuator/conditions` cho biết các positive/negative matches của auto-configuration. `ApplicationContextRunner` còn cho phép so sánh hai context gần như giống nhau, khác nhau đúng một user bean, để biết bean nào bị thay thế ngoài ý muốn.

Khi chỉ thay một bean, đánh giá phải chứng minh **cả hai mặt**: default tương ứng đã nhường chỗ **và** các default không liên quan vẫn còn. Đó là lý do phần test phía trên kiểm tra bean names và output phối hợp thay vì chỉ kiểm tra context chạy thành công.

## 10. Bảng quyết định nhanh

| Ý định | Điểm đặt điều kiện khuyến nghị | Lý do |
| --- | --- | --- |
| User được phép cung cấp `Encoder` riêng, vẫn cần `Exporter` mặc định | `@ConditionalOnMissingBean(Encoder.class)` ở method default encoder | Lùi riêng bean cần thay |
| User được phép thay toàn bộ `ReportPipeline`, nhưng encoder/exporter vẫn dùng được riêng | `@ConditionalOnMissingBean(ReportPipeline.class)` trên method pipeline | Pipeline độc lập với các bean còn lại |
| Chỉ kích hoạt integration khi vendor library hiện diện | `@ConditionalOnClass` trên class/group integration | Điều kiện chung thật sự cho cả group |
| Tắt **cả** integration khi property `enabled=false` | `@ConditionalOnProperty` ở class/group | Công tắc cấp nhóm |
| Tắt hẳn một auto-configuration đã đăng ký | `spring.autoconfigure.exclude` hoặc `@SpringBootApplication(exclude=...)` | Loại toàn bộ auto-configuration, có chủ đích |
| Bean A chỉ nên tạo nếu bean B đã có | `@ConditionalOnBean(B.class)` tại phạm vi bean A, cùng thứ tự auto-config phù hợp | Phụ thuộc tồn tại ở thời điểm đánh giá |

## 11. Câu hỏi tự kiểm tra

1. Auto-configuration tạo `Encoder` và `Exporter`. Người dùng chỉ khai báo `Encoder` riêng. Điều kiện `@ConditionalOnMissingBean(Encoder.class)` nên ở class hay method nào? **Trên method tạo default `Encoder`**; `Exporter` cần condition riêng của nó.
2. Vì sao `@Primary` không thay thế được cơ chế back-off? **Vì nó giúp chọn bean khi tiêm nhưng không ngăn đăng ký bean default**, nên vẫn có thể tồn tại hai bean.
3. Người dùng đã có `ReportPipeline` riêng. Có cần bỏ cả `Encoder` và `Exporter` mặc định không? **Không bắt buộc**; nếu chúng có giá trị sử dụng độc lập và không vi phạm điều kiện chung, vẫn nên được cung cấp khi còn thiếu.
4. Vì sao một `@ConditionalOnMissingBean(Encoder.class)` ở cấp class có thể làm mất exporter? **Vì condition không khớp sẽ loại cả class auto-configuration**, bao gồm các method không liên quan.
5. Tại sao thứ tự auto-configuration quan trọng? **Vì điều kiện bean chỉ thấy bean definition đã xử lý vào thời điểm xét**; provider đến sau không tự khiến condition đã thất bại được xét lại.
6. Khi nào exclude toàn bộ auto-configuration là đúng? **Khi ứng dụng chủ ý loại toàn bộ nhánh đó**, không đơn thuần muốn thay một implementation.

## Tài liệu chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): condition trên lớp/method, bean back-off, thứ tự xử lý, return type và `ApplicationContextRunner`.
- [Spring Boot 3.3 API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): phạm vi tìm kiếm theo type/name, suy type từ `@Bean` và giới hạn “processed so far”.
- [Spring Boot 3.3 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): metadata `before`/`after` và cách định nghĩa auto-configuration.
- [Spring Boot 3.3 — Using Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html): override auto-config bằng bean và cách loại trừ toàn bộ auto-configuration.

**Ghi nhớ:** Đặt **điều kiện nhường chỗ tại đúng bean cần thay thế**. Chỉ đặt điều kiện ở cấp toàn bộ cấu hình khi điều kiện đó thật sự là điều kiện chung cho cả nhóm. Kiểm chứng bằng tình huống người dùng chỉ thay **một** bean để bảo đảm những default còn lại vẫn xuất hiện.
