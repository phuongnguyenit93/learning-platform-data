# Spring Boot `@ConditionalOnMissingBean`: dùng `ignored` và `ignoredType` để loại kiểu bean khỏi phép kiểm tra thiếu bean

## 1. Vấn đề cần giải quyết

Giả sử ứng dụng có giao diện `MessageSender` với hai nhóm triển khai:

- `HealthCheckSender` là bean phục vụ kiểm tra hoặc giám sát kỹ thuật. Nó cũng triển khai `MessageSender`, nhưng **không được xem là lựa chọn nghiệp vụ**.
- `DefaultSender` là bean mặc định do auto-configuration cung cấp khi ứng dụng chưa có `MessageSender` nghiệp vụ.
- Ứng dụng cũng có thể tự đăng ký `BusinessSender`; khi đó cấu hình mặc định phải nhường chỗ.

Nếu chỉ dùng `@ConditionalOnMissingBean(MessageSender.class)`, sự có mặt của `HealthCheckSender` sẽ khiến Spring Boot xem như **đã có** `MessageSender` và không tạo `DefaultSender`. Đó là trường hợp dùng `ignored` hoặc `ignoredType`: cho phép một số **kiểu bean** không được tính là kết quả khớp trong phép kiểm tra thiếu bean.

> Ý chính: “bỏ qua” chỉ xảy ra **khi điều kiện `@ConditionalOnMissingBean` được đánh giá**. Bean bị bỏ qua vẫn tồn tại trong `ApplicationContext`, vẫn có thể được lấy hoặc inject, và vẫn có thể gây nhiều ứng viên khi autowire theo cùng giao diện.

## 2. Phân biệt kiểu *cần tìm* và kiểu *bỏ qua*

`@ConditionalOnMissingBean` thuộc `org.springframework.boot.autoconfigure.condition`. Một số thuộc tính dễ nhầm:

| Thuộc tính | Kiểu dữ liệu | Vai trò |
|---|---|---|
| `value` | `Class<?>[]` | Xác định kiểu bean cần kiểm tra xem **có thiếu** hay không; ví dụ `MessageSender.class`. |
| `type` | `String[]` | Như `value` nhưng khai báo **tên lớp đầy đủ** dưới dạng chuỗi. |
| `name` | `String[]` | Kiểm tra theo **tên bean**, không phải tên kiểu. |
| `ignored` | `Class<?>[]` | Các kiểu bean phải **bỏ qua khi tìm bean khớp**; ví dụ `HealthCheckSender.class`. |
| `ignoredType` | `String[]` | Như `ignored` nhưng dùng **tên lớp đầy đủ** dạng chuỗi; ví dụ `"com.example.notice.HealthCheckSender"`. |

Cả `ignored` lẫn `ignoredType` đều mặc định là mảng rỗng, có thể khai báo nhiều phần tử và có thể dùng cùng nhau. Chúng bổ sung vào danh sách kiểu bị bỏ qua; **không thay thế** `value`/`type` (mục tiêu của phép kiểm tra). Spring Boot tìm bean theo thông tin kiểu trong `BeanFactory`, sau đó loại các ứng viên thuộc kiểu bị bỏ qua ra khỏi kết quả khớp của điều kiện.

Ví dụ minh họa:

```java
@Bean
@ConditionalOnMissingBean(
    value = MessageSender.class,
    ignored = HealthCheckSender.class
)
DefaultSender defaultSender() {
    return new DefaultSender();
}
```

Giả sử mọi bean dưới đây đã được **đăng ký trước thời điểm** điều kiện chạy:

| Bean đã tồn tại thuộc `MessageSender` | Không đặt `ignored` | Đặt `ignored = HealthCheckSender.class` |
|---|---|---|
| Không có bean nào | Tạo `DefaultSender` | Tạo `DefaultSender` |
| Chỉ có `HealthCheckSender` | Không tạo | **Tạo** `DefaultSender` |
| Chỉ có `BusinessSender` | Không tạo | Không tạo |
| Có cả `HealthCheckSender` và `BusinessSender` | Không tạo | Không tạo |

Trong tình huống thứ hai, có **hai bean `MessageSender` trong context** sau khi điều kiện chạy; việc bỏ qua không xóa bean giám sát. Nếu code inject một `MessageSender` mà không chỉ rõ ứng viên, cần cân nhắc `@Qualifier` hoặc `@Primary` phù hợp.

## 3. Cơ chế đánh giá theo từng bước

1. Spring Boot xử lý `@Bean` hoặc lớp auto-configuration có `@ConditionalOnMissingBean`.
2. Nó xác định yêu cầu tìm kiếm từ `value`, `type`, `name`, `annotation`; nếu áp dụng trên phương thức `@Bean` và không chỉ định mục tiêu tìm theo kiểu/tên, kiểu trả về của phương thức thường là mục tiêu mặc định.
3. Nó thu thập các bean **đã có định nghĩa được xử lý tới thời điểm đó** trong phạm vi tìm kiếm, rồi xác định ứng viên khớp theo kiểu, tên và các ràng buộc liên quan.
4. Các bean có kiểu thuộc `ignored`/`ignoredType` bị loại khỏi tập ứng viên dùng để quyết định điều kiện.
5. Nếu không còn ứng viên đáp ứng yêu cầu kiểm tra, điều kiện **match** và bean cấu hình mặc định có thể được đăng ký; nếu còn ít nhất một ứng viên cần kiểm tra, điều kiện không match.

Lưu ý rằng điều kiện không chủ động đợi các bean đăng ký trong tương lai. Vì vậy nên đặt điều kiện này trong **auto-configuration**, được xử lý sau các định nghĩa bean của người dùng. Khi kết quả phụ thuộc bean từ một auto-configuration khác, phải bảo đảm thứ tự chạy phù hợp (chẳng hạn `@AutoConfiguration(after = ...)`).

## 4. Ví dụ kiểm chứng chạy được với Spring Boot 3.x và Java 17+

Đặt tệp `src/test/java/demo/IgnoredBeanConditionTest.java` trong dự án Spring Boot có `spring-boot-starter-test`. Ví dụ dùng `ApplicationContextRunner` để tạo các context độc lập, cho bean người dùng được xử lý trước auto-configuration. Đây là test, không cần chạy máy chủ HTTP.

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class IgnoredBeanConditionTest {

    interface MessageSender {
        String kind();
    }

    static final class HealthCheckSender implements MessageSender {
        @Override
        public String kind() {
            return "health";
        }
    }

    static final class BusinessSender implements MessageSender {
        @Override
        public String kind() {
            return "business";
        }
    }

    static final class DefaultSender implements MessageSender {
        @Override
        public String kind() {
            return "default";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class HealthConfiguration {
        @Bean
        HealthCheckSender healthCheckSender() {
            return new HealthCheckSender();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BusinessConfiguration {
        @Bean
        BusinessSender businessSender() {
            return new BusinessSender();
        }
    }

    @AutoConfiguration
    static class SenderAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(
                value = MessageSender.class,
                ignored = HealthCheckSender.class
        )
        DefaultSender defaultSender() {
            return new DefaultSender();
        }
    }

    @AutoConfiguration
    static class WithoutIgnoredAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(MessageSender.class)
        DefaultSender defaultSender() {
            return new DefaultSender();
        }
    }

    private final ApplicationContextRunner runner = new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(SenderAutoConfiguration.class));

    @Test
    void createsDefaultWhenNoSenderExists() {
        runner.run(context -> {
            assertTrue(context.containsBean("defaultSender"));
            assertEquals("default", context.getBean(DefaultSender.class).kind());
        });
    }

    @Test
    void ignoresHealthBeanAndCreatesDefault() {
        runner.withUserConfiguration(HealthConfiguration.class)
                .run(context -> {
                    assertTrue(context.containsBean("healthCheckSender"));
                    assertTrue(context.containsBean("defaultSender"));
                });
    }

    @Test
    void businessBeanStillPreventsDefault() {
        runner.withUserConfiguration(
                        HealthConfiguration.class,
                        BusinessConfiguration.class
                )
                .run(context -> {
                    assertTrue(context.containsBean("healthCheckSender"));
                    assertTrue(context.containsBean("businessSender"));
                    assertFalse(context.containsBean("defaultSender"));
                });
    }

    @Test
    void withoutIgnoredHealthBeanPreventsDefault() {
        new ApplicationContextRunner()
                .withUserConfiguration(HealthConfiguration.class)
                .withConfiguration(
                        AutoConfigurations.of(WithoutIgnoredAutoConfiguration.class)
                )
                .run(context ->
                        assertFalse(context.containsBean("defaultSender"))
                );
    }
}
```

Chạy trong dự án Gradle Spring Boot đã có dependency test:

```bash
./gradlew test --tests demo.IgnoredBeanConditionTest
```

Trên Windows có thể thay `./gradlew` bằng `.\gradlew.bat`. Kết quả mong đợi: **4 test pass**; mỗi test kiểm tra sự hiện diện của bean bằng tên, và test đầu kiểm tra kết quả `kind()`. Đây là kỳ vọng từ code; nếu dự án có custom configuration hoặc version khác, hãy xem báo cáo test thực tế.

**Vì sao ví dụ khai báo kiểu trả về cụ thể?** `@Bean HealthCheckSender healthCheckSender()` công khai kiểu thực tế cho Spring Boot khi nó kiểm tra điều kiện. Nếu phương thức khai báo kiểu trả về chung `MessageSender`, hệ thống có thể chưa suy ra được `HealthCheckSender` ở giai đoạn đánh giá điều kiện, khiến `ignored` không có hiệu quả như dự kiến. Tương tự, `@Bean DefaultSender defaultSender()` có kiểu trả về cụ thể nhưng chú thích **chỉ định rõ** `value = MessageSender.class` để kiểm tra toàn bộ giao diện, không chỉ `DefaultSender`.

## 5. Đổi sang `ignoredType` khi chỉ có tên kiểu

Khi mã auto-configuration muốn tránh tham chiếu trực tiếp một lớp được cung cấp bởi module tùy chọn, có thể dùng tên lớp đầy đủ:

```java
@Bean
@ConditionalOnMissingBean(
        value = MessageSender.class,
        ignoredType = "com.example.notice.HealthCheckSender"
)
DefaultSender defaultSender() {
    return new DefaultSender();
}
```

Đoạn này minh họa phương thức bên trong một cấu hình đã có các kiểu `MessageSender` và `DefaultSender`; `com.example.notice.HealthCheckSender` là **tên lớp ví dụ**, cần thay đúng package thực tế trong ứng dụng. `ignoredType` nhận **tên Java class**, không nhận tên bean như `"healthCheckSender"` và không phải một đoạn biểu thức hay wildcard. Đối với lớp lồng nhau, tên nhị phân có thể dùng ký tự `$`; đừng đoán tên, hãy kiểm tra `SomeClass.class.getName()`.

Hai cách khai báo tương ứng:

```java
ignored = HealthCheckSender.class

ignoredType = "com.example.notice.HealthCheckSender"
```

- Chọn `ignored` khi lớp có sẵn trên compile classpath: rõ ràng, được trình biên dịch kiểm tra và hỗ trợ đổi tên.
- Chọn `ignoredType` khi cần khai báo bằng tên lớp, đặc biệt khi xây dựng auto-configuration tích hợp module tùy chọn mà không muốn mã annotation phụ thuộc trực tiếp vào class đó.
- Nếu dùng annotation tự tạo bao bọc `@ConditionalOnMissingBean` (meta-annotation), cần cẩn trọng với class reference khi Spring đọc annotation metadata; Javadoc hướng dẫn ưu tiên thuộc tính dạng tên `ignoredType` cho kiểu bị bỏ qua trong trường hợp này.

Dùng chuỗi không khiến một lớp không tồn tại tự xuất hiện. Nếu runtime không có kiểu đã ghi, không có bean thuộc kiểu đó để bỏ qua; các mục tiêu và điều kiện khác vẫn được kiểm tra bình thường.

## 6. Những nhầm lẫn thường gặp

**Nhầm 1 — “`ignored` xóa bean khỏi Spring”.** Sai: nó chỉ loại bean khỏi tập kết quả phù hợp với **lần đánh giá điều kiện**. Bean vẫn có thể được lấy qua tên, `getBeansOfType`, hoặc inject. Nếu bạn tạo thêm fallback bean cùng giao diện, việc inject theo giao diện có thể cần giải quyết ambiguity bằng `@Qualifier`, `@Primary` hoặc thiết kế rõ ràng hơn.

**Nhầm 2 — “`ignoredType` là tên bean”.** Sai: phải dùng kiểu `"com.example.notice.HealthCheckSender"`. Tên bean thuộc về thuộc tính `name` và chỉ là một tiêu chí kiểm tra riêng.

**Nhầm 3 — Bỏ qua chính giao diện cần kiểm tra.** Nếu đặt `value = MessageSender.class, ignored = MessageSender.class`, mọi ứng viên `MessageSender` phù hợp kiểu bị bỏ qua có thể không còn được tính; fallback có thể được tạo dù ứng dụng đã cung cấp bean nghiệp vụ. Chỉ định **loại triển khai kỹ thuật cụ thể**, có lý do bỏ qua rõ ràng.

**Nhầm 4 — Không khai báo `value` khi trả về kiểu triển khai.** Với `@Bean DefaultSender defaultSender()` và `@ConditionalOnMissingBean(ignored = HealthCheckSender.class)`, mặc định có thể chỉ kiểm tra sự thiếu `DefaultSender`, không phải sự thiếu `MessageSender`. Khi mục tiêu là giao diện hoặc một abstraction, hãy ghi `value = MessageSender.class` rõ ràng.

**Nhầm 5 — Cấu hình chạy sai thứ tự.** Một bean chưa có định nghĩa khi condition được đánh giá sẽ không được tính, dù sau đó bean xuất hiện. Đặt bean fallback trong auto-configuration, xác định thứ tự sau các auto-configuration liên quan, và test bằng `ApplicationContextRunner`.

**Nhầm 6 — Bean bị bỏ qua không có type metadata nhận diện được.** Khi `@Bean` trả về một interface chung, hoặc có `FactoryBean`, proxy, cấu hình tạo bean động, kiểu triển khai cụ thể có thể không hiển thị tại thời điểm điều kiện chạy. Công khai kiểu trả về đủ cụ thể, hoặc thiết kế điều kiện theo kiểu/tên thực sự được Spring biết tới; không mặc định việc so khớp sẽ dựa trên runtime instance sau khi bean được khởi tạo.

**Nhầm 7 — Dùng `ignored` để thay điều kiện trên classpath.** `ignored`/`ignoredType` kiểm tra **bean đã đăng ký**, không kiểm tra thư viện có trên classpath. Để bật cấu hình khi dependency hiện diện hoặc vắng mặt, dùng `@ConditionalOnClass`/`@ConditionalOnMissingClass` thích hợp.

## 7. Cách kiểm tra và chẩn đoán

1. Xác nhận mục tiêu kiểm tra là kiểu nào (`value`/`type`), và kiểu muốn bỏ qua là kiểu **triển khai cụ thể** nào.
2. Xác nhận `@Bean` của ứng viên công khai type metadata phù hợp, đặc biệt khi các bean chưa được tạo thành object.
3. Dùng `ApplicationContextRunner` viết các kịch bản **không có bean**, **chỉ có bean bị bỏ qua**, **có bean nghiệp vụ**, **có cả hai**. Chỉ dựa vào số lượng bean khi test phù hợp; ở ví dụ trên test tên bean để kết quả không bị nhầm với những loại sender khác.
4. Khi chạy ứng dụng, bật báo cáo condition bằng tham số `--debug` hoặc xem `/actuator/conditions` nếu dự án đã cài và cấu hình Spring Boot Actuator phù hợp. Tìm kết quả của `OnBeanCondition` và tên auto-configuration, phân biệt condition đã match với việc tạo bean thực tế.
5. Nếu có nhiều bean cho cùng interface sau khi fallback tạo ra, kiểm tra các injection point để áp dụng qualifier/primary hợp lý.

## 8. Ghi nhớ để áp dụng

- `value`/`type` trả lời: **“Đang kiểm tra thiếu bean thuộc kiểu nào?”**
- `ignored`/`ignoredType` trả lời: **“Khi kiểm tra ấy, những kiểu bean nào không được tính?”**
- `ignored` dùng `Class<?>[]`; `ignoredType` dùng `String[]` chứa tên class đầy đủ.
- Bỏ qua trong condition **không xóa bean**, không vô hiệu hóa autowire và không thay đổi scope tìm kiếm.
- Đánh giá condition dựa trên định nghĩa bean đã được xử lý; auto-configuration và thứ tự xử lý rất quan trọng.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 Javadoc — `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot Reference — Developing Auto-configuration, Bean Conditions: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
