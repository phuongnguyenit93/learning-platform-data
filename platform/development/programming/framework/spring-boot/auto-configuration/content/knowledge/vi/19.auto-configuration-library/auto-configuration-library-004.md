# Tạo bean mặc định với điều kiện nhường chỗ rõ ràng trong Spring Boot

## 1. Mục tiêu: cung cấp mặc định nhưng tôn trọng lựa chọn của ứng dụng

Một thư viện Spring Boot thường muốn cung cấp sẵn một bean để người dùng có thể bắt đầu nhanh. Ví dụ, thư viện báo cáo có thể cung cấp `DefaultReportService` để xử lý yêu cầu tạo báo cáo. Tuy nhiên, ứng dụng sử dụng thư viện có thể cần logic riêng: ghi audit, thêm cache, gọi dịch vụ khác hoặc áp dụng chính sách nghiệp vụ riêng.

Mong muốn là:

- Nếu ứng dụng **chưa cung cấp** dịch vụ báo cáo, thư viện đăng ký `DefaultReportService`.
- Nếu ứng dụng **đã cung cấp** một bean triển khai `ReportService`, thư viện nhường chỗ và giữ bean của ứng dụng.
- Việc nhường chỗ diễn ra ngay trong quá trình đăng ký bean definitions, không cần tạo hai bean rồi tự chọn một bean khi chạy.

Spring Boot cung cấp `@ConditionalOnMissingBean` để diễn tả quy tắc này. Đây là một bean condition quan trọng khi phát triển auto-configuration và starter.

## 2. Cách hoạt động cơ bản

Ví dụ:

```java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    DefaultReportService defaultReportService() {
        return new DefaultReportService();
    }
}
```

Đây là cấu hình mẫu. `ReportService` là interface do thư viện định nghĩa; `DefaultReportService` là implementation mặc định.

Spring Boot đánh giá `@ConditionalOnMissingBean(ReportService.class)` khi xử lý phương thức `@Bean`:

1. Kiểm tra các bean definitions đã được xử lý trong phạm vi tìm kiếm.
2. Tìm bean phù hợp với tiêu chí `ReportService`.
3. Nếu không có bean phù hợp, condition match và bean definition `defaultReportService` được đăng ký.
4. Nếu đã có bean phù hợp, condition không match và bean mặc định không được đăng ký.

Kết quả là **back-off**: thư viện tự rút khỏi vị trí cung cấp bean mặc định khi ứng dụng đã có lựa chọn của riêng mình.

Điều kiện không xóa bean người dùng, không thay đổi implementation của họ và không tự tạo một bean khác để thay thế. Nó chỉ quyết định có đăng ký bean mặc định hay không.

## 3. Tại sao nên kiểm tra interface thay vì chỉ kiểm tra class mặc định?

Giả sử thư viện có interface:

```java
public interface ReportService {
    String generate();
}
```

Implementation mặc định:

```java
public final class DefaultReportService implements ReportService {

    @Override
    public String generate() {
        return "default report";
    }
}
```

Ứng dụng có thể tự cung cấp implementation:

```java
public final class CustomReportService implements ReportService {

    @Override
    public String generate() {
        return "custom report";
    }
}
```

Nếu mục tiêu là **bất kỳ implementation nào của `ReportService` cũng phải thay thế mặc định**, hãy dùng:

```java
@Bean
@ConditionalOnMissingBean(ReportService.class)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

Nếu chỉ dùng:

```java
@Bean
@ConditionalOnMissingBean(DefaultReportService.class)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

thì `CustomReportService` không phải là `DefaultReportService`. Vì vậy điều kiện vẫn có thể match và thư viện đăng ký thêm bean mặc định. Context có thể có hai ứng viên cho `ReportService`, gây lỗi khi injection theo interface nếu không có qualifier hoặc primary thích hợp.

| Tiêu chí kiểm tra | Ứng dụng có `CustomReportService` | Kết quả |
|---|---|---|
| `ReportService.class` | Có bean phù hợp | Bean mặc định nhường chỗ |
| `DefaultReportService.class` | Không có bean thuộc class mặc định | Bean mặc định vẫn có thể được đăng ký |
| Tên `customReportService` | Bean mặc định có tên khác | Điều kiện theo tên vẫn match |
| Tên `defaultReportService` | Đã có bean đúng tên | Bean mặc định nhường chỗ theo tên |

**Nguyên tắc thiết kế:** hãy kiểm tra abstraction mà người dùng được phép tùy biến. Với dịch vụ, đó thường là interface hoặc base class công khai của thư viện.

## 4. Các thuộc tính định danh bean cần kiểm tra

`@ConditionalOnMissingBean` hỗ trợ nhiều cách mô tả bean cần vắng mặt:

| Thuộc tính | Kiểu | Ý nghĩa |
|---|---|---|
| `value` | `Class<?>[]` | Kiểm tra theo kiểu Java |
| `type` | `String[]` | Kiểm tra theo tên lớp đầy đủ (FQCN) |
| `name` | `String[]` | Kiểm tra theo tên bean |
| `annotation` | `Class<? extends Annotation>[]` | Kiểm tra bean có được gắn annotation chỉ định hay không |
| `ignored` | `Class<?>[]` | Bỏ qua một số kiểu bean khi tìm ứng viên khớp |
| `ignoredType` | `String[]` | Bỏ qua kiểu bean theo tên lớp đầy đủ |
| `search` | `SearchStrategy` | Chọn phạm vi context hierarchy được tìm kiếm |
| `parameterizedContainer` | `Class<?>[]` | Nhận diện kiểu bean bên trong generic container |

### 4.1. Kiểm tra theo kiểu với `value`

```java
@ConditionalOnMissingBean(ReportService.class)
```

Đây là cách phổ biến nhất khi muốn ứng dụng tự cung cấp bất kỳ implementation nào của một abstraction.

Có thể kiểm tra nhiều kiểu:

```java
@ConditionalOnMissingBean({
    ReportService.class,
    ReportExporter.class
})
```

Condition chỉ match khi **không có bean phù hợp với từng yêu cầu được chỉ định**. Nếu ứng dụng đã cung cấp một bean phù hợp với một trong các tiêu chí, điều kiện thiếu bean không còn đúng và bean mặc định không được đăng ký.

### 4.2. Kiểm tra theo tên lớp với `type`

Khi không muốn tham chiếu trực tiếp tới một class ở compile time, có thể dùng tên lớp:

```java
@Bean
@ConditionalOnMissingBean(
    type = "com.example.report.ReportService"
)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

`type` nhận FQCN, không nhận tên bean. Tên chuỗi không được compiler kiểm tra; phải bảo đảm package và tên lớp chính xác. Cách này hữu ích khi viết auto-configuration tích hợp module tùy chọn.

### 4.3. Kiểm tra theo tên bean với `name`

```java
@Bean
@ConditionalOnMissingBean(name = "reportService")
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

Condition chỉ kiểm tra bean tên `reportService` có vắng mặt hay không. Một bean khác tên nhưng cùng kiểu `ReportService` không nhất thiết làm điều kiện này fail.

Dùng kiểm tra theo tên khi hợp đồng cấu hình thực sự phụ thuộc vào một bean name cụ thể. Nếu người dùng được quyền thay implementation theo kiểu, ưu tiên `value`.

### 4.4. Kiểm tra theo annotation

Có thể yêu cầu không có bean nào được gắn annotation cụ thể:

```java
@ConditionalOnMissingBean(annotation = InternalReportAdapter.class)
```

Đây là cách kiểm tra theo metadata annotation trên bean. Nó phù hợp khi thư viện định nghĩa một marker annotation để nhận diện nhóm component; không nên dùng thay kiểm tra type nếu hợp đồng thật sự là một interface.

## 5. Không chỉ định mục tiêu: Spring Boot suy ra từ kiểu trả về

Khi `@ConditionalOnMissingBean` được đặt trên phương thức `@Bean` và không khai báo tiêu chí `value`, `type` hoặc `name`, kiểu bean cần kiểm tra mặc định được suy ra từ **kiểu trả về của phương thức**.

Ví dụ:

```java
@Bean
@ConditionalOnMissingBean
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

Trong ví dụ này, Spring Boot kiểm tra bean kiểu `DefaultReportService`.

Điều này tiện lợi, nhưng có thể không thể hiện đúng hợp đồng mở rộng. Nếu ứng dụng cung cấp `CustomReportService` triển khai `ReportService`, kiểm tra mặc định theo `DefaultReportService` không nhận ra bean tùy chỉnh đó.

Để cho phép mọi implementation của interface thay thế bean mặc định, ghi rõ:

```java
@Bean
@ConditionalOnMissingBean(ReportService.class)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

### Khai báo kiểu trả về càng cụ thể càng tốt

Condition đánh giá dựa trên type metadata mà Spring biết được ở thời điểm xử lý bean definition. Vì vậy phương thức `@Bean` nên công khai kiểu trả về cụ thể nhất có thể:

```java
// Nên: Spring biết implementation cụ thể
@Bean
@ConditionalOnMissingBean(ReportService.class)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}

// Cần tránh nếu không có lý do: metadata chỉ cho thấy Object
@Bean
@ConditionalOnMissingBean(ReportService.class)
Object defaultReportService() {
    return new DefaultReportService();
}
```

Khi dùng tiêu chí tường minh `ReportService.class`, condition có mục tiêu rõ ràng; tuy nhiên kiểu trả về cụ thể vẫn giúp Spring dự đoán bean type tốt hơn trước khi instance được tạo và giúp công cụ, IDE hiểu bean.

## 6. Điều kiện chỉ nhìn thấy bean definitions đã được xử lý

Đây là giới hạn quan trọng nhất khi dùng `@ConditionalOnMissingBean`.

Condition chỉ đánh giá những bean definitions mà application context đã xử lý **tới thời điểm condition chạy**. Nó không chờ mọi cấu hình trong ứng dụng chạy xong rồi mới đánh giá lại.

Vì vậy Spring Boot khuyến nghị dùng `@ConditionalOnMissingBean` trong **auto-configuration**. Auto-configuration được xử lý sau các bean definitions do ứng dụng khai báo, nên nó có thể nhìn thấy bean tùy chỉnh của người dùng và nhường chỗ đúng lúc.

Nếu một bean thay thế có thể được tạo bởi một auto-configuration khác, cần bảo đảm auto-configuration cung cấp fallback chạy sau cấu hình tạo bean đó.

Ví dụ:

```java
@AutoConfiguration(after = CustomReportProviderAutoConfiguration.class)
public class ReportFallbackAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    DefaultReportService defaultReportService() {
        return new DefaultReportService();
    }
}
```

`CustomReportProviderAutoConfiguration` là tên lớp minh họa. Chỉ cần quan hệ `after` này nếu fallback phụ thuộc vào bean do auto-configuration đó cung cấp.

### Không nên đặt điều kiện bean tùy tiện trong cấu hình thông thường

Nếu một class `@Configuration` được component scan và condition của nó chạy trước cấu hình tạo bean tùy chỉnh, kết quả có thể khác mong đợi. Hãy chuyển bean mặc định vào auto-configuration và để Spring Boot áp dụng sau user configuration.

## 7. Đặt condition ở cấp class hay cấp phương thức `@Bean`?

Có thể đặt `@ConditionalOnMissingBean` ở cả cấp class và cấp phương thức.

### Ở cấp phương thức

```java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    DefaultReportService defaultReportService() {
        return new DefaultReportService();
    }

    @Bean
    ReportMetrics reportMetrics() {
        return new ReportMetrics();
    }
}
```

Nếu ứng dụng đã có `ReportService`, chỉ bean `defaultReportService` không được đăng ký. Bean `reportMetrics` vẫn có thể được đăng ký.

Đây là lựa chọn tốt khi mỗi bean có điều kiện riêng.

### Ở cấp class

```java
@AutoConfiguration
@ConditionalOnMissingBean(ReportService.class)
public class ReportAutoConfiguration {

    @Bean
    DefaultReportService defaultReportService() {
        return new DefaultReportService();
    }

    @Bean
    ReportMetrics reportMetrics() {
        return new ReportMetrics();
    }
}
```

Nếu condition không match, configuration class không được đăng ký như một bean cấu hình trong context. Điều kiện ở cấp class có phạm vi rộng hơn vì nó ảnh hưởng toàn bộ các bean method bên trong.

Lưu ý: `@ConditionalOnBean` và `@ConditionalOnMissingBean` không có nghĩa là JVM sẽ không bao giờ tạo/đọc configuration class. Khác biệt chính là condition ở cấp class ngăn đăng ký configuration class khi không match; condition ở cấp method chỉ điều khiển bean method tương ứng.

**Cách chọn:** đặt condition ở method khi chỉ bean mặc định cần back off; đặt ở class khi toàn bộ nhóm bean chỉ có ý nghĩa khi abstraction chưa được cung cấp.

## 8. Phạm vi tìm kiếm context hierarchy với `search`

Một ứng dụng có thể có parent context và child context. `@ConditionalOnMissingBean` có thuộc tính `search` để quyết định phạm vi tìm kiếm.

| Giá trị | Phạm vi |
|---|---|
| `SearchStrategy.ALL` | Tìm trong context hiện tại và các context cha; đây là mặc định |
| `SearchStrategy.CURRENT` | Chỉ tìm trong context hiện tại |
| `SearchStrategy.ANCESTORS` | Chỉ tìm trong các context cha |

Ví dụ:

```java
@Bean
@ConditionalOnMissingBean(
    value = ReportService.class,
    search = SearchStrategy.CURRENT
)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

Với `CURRENT`, một `ReportService` ở parent context không làm condition của child context fail. Child context có thể đăng ký fallback riêng.

Với mặc định `ALL`, bean ở parent context được tính khi tìm kiếm. Điều này thường phù hợp khi child context có thể sử dụng bean dùng chung từ parent.

Chọn phạm vi theo kiến trúc context thực tế. Đổi `search` có thể làm xuất hiện thêm bean trong child context và tạo nhiều ứng viên khi injection.

## 9. Bỏ qua một số kiểu bean với `ignored` và `ignoredType`

Hai thuộc tính này cho phép bỏ qua một số kiểu khi condition xác định bean phù hợp.

Ví dụ:

```java
@Bean
@ConditionalOnMissingBean(
    value = ReportService.class,
    ignored = HealthReportService.class
)
DefaultReportService defaultReportService() {
    return new DefaultReportService();
}
```

Giả sử `HealthReportService` cũng triển khai `ReportService` nhưng chỉ dùng cho health check và không được coi là implementation nghiệp vụ. Khi đó condition bỏ qua kiểu này trong phép tìm kiếm.

`ignoredType` làm cùng việc bằng tên lớp đầy đủ:

```java
@ConditionalOnMissingBean(
    value = ReportService.class,
    ignoredType = "com.example.health.HealthReportService"
)
```

Lưu ý quan trọng: **bỏ qua không xóa bean**. Nếu bean health vẫn tồn tại và fallback được tạo, context có thể có nhiều bean triển khai `ReportService`. Khi injection theo interface, ứng dụng cần qualifier hoặc thiết kế abstraction riêng để tránh ambiguity.

Chỉ dùng `ignored`/`ignoredType` khi thực sự có một loại bean không nên được tính là lựa chọn thay thế cho fallback.

## 10. Container có generic type với `parameterizedContainer`

Một số thư viện đăng ký bean thông qua wrapper generic. Ví dụ servlet filter có thể được đăng ký trực tiếp hoặc nằm trong `FilterRegistrationBean<Filter>`.

`parameterizedContainer` cho phép condition xét cả kiểu mục tiêu bên trong generic container:

```java
@ConditionalOnMissingBean(
    value = AuditFilter.class,
    parameterizedContainer = FilterRegistrationBean.class
)
```

Đây là cơ chế nâng cao. Spring Boot cũng cung cấp `@ConditionalOnMissingFilterBean` để nhận diện filter được đăng ký trực tiếp hoặc qua `FilterRegistrationBean`. Với bean thông thường không có wrapper generic, không cần khai báo thuộc tính này.

## 11. Phân biệt với các condition khác

| Annotation | Câu hỏi |
|---|---|
| `@ConditionalOnMissingBean` | Chỉ tạo bean khi chưa có bean phù hợp |
| `@ConditionalOnBean` | Chỉ tạo bean khi đã có bean phù hợp |
| `@ConditionalOnClass` | Chỉ áp dụng khi class có trên classpath |
| `@ConditionalOnMissingClass` | Chỉ áp dụng khi class không có trên classpath |
| `@ConditionalOnProperty` | Chỉ áp dụng khi property đạt điều kiện |
| `@ConditionalOnSingleCandidate` | Chỉ áp dụng khi có một bean candidate phù hợp có thể xác định |

`@ConditionalOnMissingBean` kiểm tra bean trong BeanFactory. Nó không thay thế `@ConditionalOnMissingClass`: class có thể tồn tại trên classpath mà chưa có bean, hoặc bean có thể được tạo từ một class đã có.

Một mẫu thực tế có thể kết hợp nhiều condition:

```java
@AutoConfiguration
@ConditionalOnClass(ReportClient.class)
@ConditionalOnProperty(
    prefix = "demo.report",
    name = "enabled",
    havingValue = "true"
)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    DefaultReportService defaultReportService(ReportClient client) {
        return new DefaultReportService(client);
    }
}
```

Ở đây classpath và property quyết định cấu hình có được áp dụng; bean condition quyết định có cần tạo fallback hay ứng dụng đã có service riêng.

## 12. Ví dụ kiểm thử với `ApplicationContextRunner` (Spring Boot 3.3 / Java 17+)

`ApplicationContextRunner` tạo context nhỏ để kiểm thử auto-configuration theo từng trường hợp. Ví dụ dưới đây xác nhận:

1. Không có service tùy chỉnh thì bean mặc định được tạo.
2. Có custom implementation của interface thì bean mặc định nhường chỗ.
3. Một bean không liên quan không ngăn fallback.
4. Condition theo tên bean nhường chỗ khi tên đó đã tồn tại.

Đặt tệp `src/test/java/demo/ConditionalDefaultBeanTest.java`:

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

class ConditionalDefaultBeanTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ReportAutoConfiguration.class)
                    );

    private final ApplicationContextRunner namedRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(NamedReportAutoConfiguration.class)
                    );

    @Test
    void createsDefaultWhenNoReportServiceExists() {
        runner.run(context -> {
            assertTrue(context.containsBean("defaultReportService"));
            assertEquals(
                    "default",
                    context.getBean(ReportService.class).generate()
            );
        });
    }

    @Test
    void backsOffWhenApplicationProvidesCustomImplementation() {
        runner.withUserConfiguration(UserReportConfiguration.class)
                .run(context -> {
                    assertTrue(context.containsBean("customReportService"));
                    assertFalse(context.containsBean("defaultReportService"));
                    assertEquals(
                            "custom",
                            context.getBean(ReportService.class).generate()
                    );
                });
    }

    @Test
    void unrelatedBeanDoesNotSuppressDefault() {
        runner.withUserConfiguration(UnrelatedConfiguration.class)
                .run(context -> {
                    assertTrue(context.containsBean("otherService"));
                    assertTrue(context.containsBean("defaultReportService"));
                });
    }

    @Test
    void namedConditionBacksOffWhenThatBeanNameExists() {
        namedRunner.withUserConfiguration(NamedUserReportConfiguration.class)
                .run(context -> {
                    assertTrue(context.containsBean("namedReportService"));
                    assertFalse(context.containsBean("namedFallbackReportService"));
                });
    }

    interface ReportService {
        String generate();
    }

    static final class DefaultReportService implements ReportService {
        @Override
        public String generate() {
            return "default";
        }
    }

    static final class CustomReportService implements ReportService {
        @Override
        public String generate() {
            return "custom";
        }
    }

    @AutoConfiguration
    static class ReportAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(ReportService.class)
        DefaultReportService defaultReportService() {
            return new DefaultReportService();
        }
    }

    @AutoConfiguration
    static class NamedReportAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(name = "namedReportService")
        DefaultReportService namedFallbackReportService() {
            return new DefaultReportService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserReportConfiguration {
        @Bean
        ReportService customReportService() {
            return new CustomReportService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UnrelatedConfiguration {
        @Bean
        String otherService() {
            return "unrelated";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class NamedUserReportConfiguration {
        @Bean("namedReportService")
        ReportService namedReportService() {
            return new CustomReportService();
        }
    }
}
```

### Kết quả mong đợi

| Test | Kết quả |
|---|---|
| `createsDefaultWhenNoReportServiceExists` | Có bean `defaultReportService`; `generate()` trả `default` |
| `backsOffWhenApplicationProvidesCustomImplementation` | Có `customReportService`; không có `defaultReportService`; kết quả là `custom` |
| `unrelatedBeanDoesNotSuppressDefault` | Có `otherService` và vẫn có fallback |
| `namedConditionBacksOffWhenThatBeanNameExists` | Có `namedReportService`; không có `namedFallbackReportService` |

Test dùng tên bean và kết quả phương thức để chứng minh hành vi. Nó không cần chạy server HTTP hay kết nối database.

### Dependency và lệnh chạy

Với Gradle đã cấu hình Spring Boot 3.3.x và Java 17+:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Chạy:

```bash
./gradlew test --tests demo.ConditionalDefaultBeanTest
```

Trên Windows PowerShell:

```powershell
.\\gradlew.bat test --tests demo.ConditionalDefaultBeanTest
```

**Kết quả kỳ vọng:** 4 test pass. Đây là kết quả dự kiến theo code; chưa phải log chạy thực tế. Hãy chạy trong project với dependency và phiên bản Spring Boot thực tế để xác nhận.

## 13. Lỗi thường gặp và cách xử lý

1. **Chỉ kiểm tra class implementation mặc định.** Ứng dụng có implementation khác của interface nhưng fallback vẫn được tạo. Kiểm tra interface hoặc abstraction công khai.
2. **Không ghi rõ mục tiêu khi kiểu trả về quá rộng.** Nếu phương thức trả về `Object` hoặc interface không đúng mục tiêu, condition có thể không diễn đạt ý định. Cung cấp return type cụ thể và chỉ định `value` khi cần.
3. **Đặt condition trong cấu hình không đúng thứ tự.** Condition chỉ nhìn bean definitions đã xử lý. Dùng auto-configuration và khai báo `after` khi phụ thuộc bean từ auto-configuration khác.
4. **Nhầm tên bean với kiểu bean.** `name` kiểm tra tên; `value`/`type` kiểm tra kiểu. Chọn theo hợp đồng muốn bảo vệ.
5. **Đặt condition ở cấp class trong khi chỉ muốn một bean nhường chỗ.** Các bean method khác trong class cũng bị ảnh hưởng. Chuyển condition xuống phương thức fallback.
6. **Dùng `ignored` mà quên bean bị bỏ qua vẫn tồn tại.** Có thể tạo nhiều ứng viên cùng interface và gây lỗi injection.
7. **Hiểu sai context hierarchy.** Mặc định `SearchStrategy.ALL` có thể thấy bean từ parent context. Dùng `CURRENT` hoặc `ANCESTORS` khi thực sự cần phạm vi khác.
8. **Cho rằng `@Primary` thay thế điều kiện missing.** `@Primary` ảnh hưởng chọn candidate khi injection; `@ConditionalOnMissingBean` quyết định có đăng ký fallback dựa trên bean phù hợp. Hai cơ chế giải quyết hai vấn đề khác nhau.
9. **Kỳ vọng condition tự đánh giá lại khi ứng dụng đang chạy.** Bean conditions được xét trong quá trình tạo context. Thêm bean hoặc thay đổi property sau startup không tự động tạo/gỡ fallback.
10. **Xem back-off là lỗi.** Khi user bean đã tồn tại và fallback không được tạo, đó thường chính là hành vi thiết kế mong muốn.

## 14. Quy trình thiết kế một bean mặc định có thể tùy biến

1. Xác định **abstraction công khai** mà ứng dụng được quyền thay thế, thường là interface.
2. Viết implementation mặc định với kiểu trả về cụ thể.
3. Đặt `@ConditionalOnMissingBean(Abstraction.class)` ngay trên phương thức bean mặc định.
4. Đưa phương thức vào auto-configuration để user bean definitions được xử lý trước.
5. Nếu một auto-configuration khác cung cấp bean thay thế, khai báo thứ tự `after` phù hợp.
6. Kiểm tra context hierarchy và quyết định có cần thay đổi `search` khỏi mặc định `ALL` hay không.
7. Dùng `ApplicationContextRunner` kiểm tra tối thiểu: không có bean, có custom implementation, có bean không liên quan, và trường hợp tên bean nếu dùng `name`.
8. Xác nhận bean mặc định không xuất hiện khi custom bean đã có và custom bean vẫn được sử dụng.

## 15. Ghi nhớ

- `@ConditionalOnMissingBean` là cơ chế **back-off** để auto-configuration nhường chỗ cho bean do ứng dụng cung cấp.
- `value`/`type` kiểm tra kiểu; `name` kiểm tra tên bean; `annotation` kiểm tra annotation trên bean.
- Khi không chỉ định mục tiêu trên `@Bean` method, Spring Boot suy ra kiểu cần kiểm tra từ kiểu trả về của method.
- Nếu mọi implementation của interface đều phải thay thế mặc định, hãy kiểm tra **interface**, không chỉ class mặc định.
- Condition chỉ thấy bean definitions đã được xử lý; đặt bean conditions trong auto-configuration và khai báo ordering nếu cần.
- `search` mặc định là `ALL`; bean ở parent context có thể khiến fallback trong child context nhường chỗ.
- `ignored`/`ignoredType` chỉ loại bean khỏi phép kiểm tra; chúng không xóa bean.
- Condition ở cấp class có phạm vi rộng hơn condition trên từng bean method.
- `@Primary` điều khiển lựa chọn injection; `@ConditionalOnMissingBean` điều khiển việc đăng ký bean mặc định.

### Tài liệu chính thức

- Spring Boot 3.3 Javadoc — `ConditionalOnMissingBean`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html
- Spring Boot 3.3 Reference — Creating Your Own Auto-configuration, Bean Conditions: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 Javadoc — `SearchStrategy`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SearchStrategy.html
- Spring Boot 3.3 Javadoc — `ConditionalOnBean` (đối chiếu điều kiện bean hiện diện): https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html
