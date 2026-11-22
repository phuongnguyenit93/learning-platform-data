# Đổi tên lớp tự cấu hình và ảnh hưởng đến exclude hoặc quan hệ thứ tự

## Mục tiêu học tập

Một lớp được đánh dấu `@AutoConfiguration` thường nằm trong thư viện dùng chung và được nhiều ứng dụng khác tham chiếu. Khi đổi package hoặc tên lớp, thay đổi đó có thể ảnh hưởng đến nhiều nơi ngoài source code của chính thư viện:

- Spring Boot tìm candidate qua file `AutoConfiguration.imports`.
- Ứng dụng có thể loại lớp bằng `@SpringBootApplication(exclude = ...)`, `excludeName` hoặc property `spring.autoconfigure.exclude`.
- Auto-configuration khác có thể khai báo thứ tự tương đối bằng `before`, `after`, `beforeName`, `afterName`, `@AutoConfigureBefore` hoặc `@AutoConfigureAfter`.
- Test, module tích hợp và tài liệu có thể lưu fully qualified class name (FQCN) cũ.

Vì vậy, FQCN của auto-configuration có một vai trò tương thích công khai. Spring Boot 3.4 bổ sung cơ chế replacement metadata để ánh xạ tên cũ sang tên mới trong các exclusion và quan hệ ordering. Cơ chế này **không có trong Spring Boot 3.3**; đây là ranh giới phiên bản quan trọng khi thiết kế migration.

Sau bài học, bạn có thể:

- Liệt kê các vị trí tham chiếu FQCN của auto-configuration.
- Dự đoán tác động của đổi package/tên class lên imports, exclusions và ordering.
- Dùng `AutoConfiguration.replacements` đúng cách trên Spring Boot 3.4+.
- Xây dựng kế hoạch tương thích nếu thư viện vẫn hỗ trợ Spring Boot 3.3.
- Viết test để xác nhận tên mới được phát hiện, tên cũ vẫn loại được cấu hình và quan hệ thứ tự được duy trì.
- Kiểm tra JAR đã publish thay vì chỉ kiểm tra source tree.

## 1. FQCN của auto-configuration là một phần của hợp đồng

Giả sử thư viện Acme có lớp:

~~~java
package com.acme.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
public class AcmeAutoConfiguration {
    // Các bean mặc định của thư viện.
}
~~~

Tên đầy đủ của lớp là:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Ứng dụng thường không gọi lớp này trực tiếp. Tuy nhiên, Spring Boot và các thư viện khác có thể lưu tên đầy đủ của nó trong metadata hoặc annotation.

Ví dụ, một ứng dụng có thể loại auto-configuration bằng chuỗi:

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Một thư viện khác có thể yêu cầu được áp dụng sau Acme:

~~~java
@AutoConfiguration(
        afterName = "com.acme.autoconfigure.AcmeAutoConfiguration")
public class AcmeMetricsAutoConfiguration {
}
~~~

Nếu đổi package thành `com.acme.autoconfigure.core`, tên mới trở thành:

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

Tên cũ và tên mới là hai chuỗi khác nhau. Trình biên dịch không thể tìm tất cả những chuỗi được lưu trong application.yml, file resource hoặc artifact đã phát hành để tự sửa chúng.

Spring Boot cũng nêu rõ tên lớp auto-configuration là khía cạnh công khai được dùng khi ứng dụng cần disable cấu hình. Vì thế, đổi FQCN nên được xem như một thay đổi có tác động tương thích, kể cả khi bean bên trong không thay đổi.

## 2. Những nơi có thể chứa tên lớp cũ

Trước khi đổi tên, hãy kiểm kê các tham chiếu sau.

| Vị trí | Cách tham chiếu | Hậu quả nếu tên cũ không được xử lý |
| --- | --- | --- |
| `AutoConfiguration.imports` | Một dòng FQCN | Boot không tìm thấy candidate mới nếu resource vẫn liệt kê tên cũ |
| `@SpringBootApplication(exclude = ...)` | Class literal | Source có thể không biên dịch khi class cũ bị xóa |
| `@SpringBootApplication(excludeName = ...)` | Chuỗi FQCN | Tên cũ không còn trỏ đến candidate mới |
| `spring.autoconfigure.exclude` | Chuỗi FQCN | Cấu hình mới có thể vẫn được áp dụng |
| `@AutoConfiguration(before/after = ...)` | Class literal | Source tham chiếu class cũ có thể không biên dịch |
| `@AutoConfiguration(beforeName/afterName = ...)` | Chuỗi FQCN | Cạnh ordering cũ không còn khớp tên mới |
| `@AutoConfigureBefore` / `@AutoConfigureAfter` | Class hoặc name | Quan hệ thứ tự có thể bị mất |
| `@ImportAutoConfiguration` | Class literal và exclude | Import/exclude tường minh cần được rà soát |
| Test và module tích hợp | FQCN trong annotation hoặc resource | Test không còn đại diện cho hành vi mới |
| Tài liệu và ví dụ cấu hình | FQCN dạng text | Người dùng sao chép cấu hình cũ |

Ngoài các vị trí trên, hãy tìm tên lớp trong:
- Source code của các module trong cùng repository.
- File `META-INF/spring`.
- Test fixture và sample application.
- Script build, plugin hoặc code dùng `Class.forName`.
- Release note, migration guide và tài liệu API.

Không phải mọi chuỗi đều được Spring Boot tự ánh xạ. Replacement metadata được thiết kế cho tên auto-configuration được dùng trong **exclusions và before/after ordering**. Những API tham chiếu class trực tiếp, reflection tùy chỉnh hoặc resource riêng vẫn cần được kiểm tra theo contract của chúng.

## 3. Tác động lên AutoConfiguration.imports

Spring Boot tìm candidate trong file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng chứa một FQCN. Ví dụ trước khi đổi tên:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

Sau khi đổi package của AcmeAutoConfiguration:

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

Imports file phải liệt kê đúng class hiện tại được phát hành. Với cơ chế replacement của Boot 3.4+, file này chỉ liệt kê **lớp thay thế**; không giữ đồng thời tên cũ và tên mới như hai candidate độc lập.

Nếu source code đã đổi tên nhưng JAR vẫn chứa imports file cũ, ứng dụng có thể gặp lỗi không tải được configuration class. Nếu file liệt kê cả hai tên mà hai class cùng đăng ký bean, có thể phát sinh cấu hình trùng lặp hoặc condition được đánh giá hai lần.

Auto-configuration được phát hiện qua imports file, không phải component scan. Vì vậy, việc đổi package không có nghĩa chỉ cần sửa package scan của ứng dụng; phải sửa resource candidate của artifact.

## 4. Exclude: vì sao tên cũ có thể làm ứng dụng lỗi hoặc không còn loại được cấu hình?

Spring Boot hỗ trợ nhiều cách disable một auto-configuration.

### 4.1. Exclude bằng class literal

~~~java
import com.acme.autoconfigure.AcmeAutoConfiguration;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(exclude = AcmeAutoConfiguration.class)
public class BillingApplication {
}
~~~

Đây là tham chiếu kiểu Java. Khi đổi package, người dùng cần cập nhật import và class literal khi biên dịch lại source.

### 4.2. Exclude bằng tên class

~~~java
@SpringBootApplication(
        excludeName = "com.acme.autoconfigure.AcmeAutoConfiguration")
public class BillingApplication {
}
~~~

Cách này hữu ích khi muốn khai báo tên mà không cần import class. Tuy nhiên, chuỗi vẫn là FQCN. Nếu thư viện đổi tên mà không cung cấp mapping tương thích, chuỗi cũ không tự biến thành tên mới.

### 4.3. Exclude bằng property

~~~yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Property `spring.autoconfigure.exclude` cũng lưu tên lớp. Các môi trường khác nhau có thể đặt property trong YAML, properties file, biến môi trường hoặc command line; cần rà soát các cấu hình triển khai và chart/deployment template.

### 4.4. Hành vi cụ thể trên Spring Boot 3.3

Trong Spring Boot 3.3, `AutoConfigurationImportSelector` kiểm tra danh sách exclude so với các candidate được đọc từ `AutoConfiguration.imports`.

Nếu tên cũ vẫn là một class có thể tải được nhưng không còn nằm trong candidate list, exclusion cũ có thể bị báo là class không phải auto-configuration. Nếu class cũ đã bị xóa, tên cũ không còn loại được candidate mới; ứng dụng có thể tiếp tục áp dụng cấu hình mới.

Vì thế, khi hỗ trợ Boot 3.3, không thể chỉ thêm một file replacement rồi kỳ vọng framework hiểu mapping. Boot 3.3 chưa có cơ chế đó.

## 5. Ordering: before, after, beforeName và afterName

Auto-configuration có thể khai báo thứ tự tương đối:

~~~java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class AcmeJdbcAutoConfiguration {
}
~~~

Hoặc dùng tên:

~~~java
@AutoConfiguration(
        afterName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration")
public class AcmeJdbcAutoConfiguration {
}
~~~

Các thuộc tính:

- `before`: áp dụng auto-configuration hiện tại trước class được chỉ định.
- `beforeName`: tương tự nhưng tham chiếu bằng FQCN dạng chuỗi.
- `after`: áp dụng auto-configuration hiện tại sau class được chỉ định.
- `afterName`: tương tự nhưng tham chiếu bằng FQCN dạng chuỗi.

Các annotation riêng `@AutoConfigureBefore` và `@AutoConfigureAfter` cung cấp cùng kiểu quan hệ ordering. Nếu hai auto-configuration không cần biết trực tiếp kiểu của nhau, thuộc tính `name` là lựa chọn giảm coupling.

### 5.1. Khi tên được tham chiếu bị đổi

Giả sử một integration bên ngoài có:

~~~java
@AutoConfiguration(
        afterName = "com.acme.autoconfigure.AcmeAutoConfiguration")
public class PartnerMetricsAutoConfiguration {
}
~~~

Sau khi Acme chuyển class sang package `com.acme.autoconfigure.core`, tên cũ không còn trùng FQCN candidate mới. Nếu không có mapping tương thích, quan hệ ordering này có thể không còn tác dụng.

Nếu dùng class literal:

~~~java
@AutoConfiguration(after = AcmeAutoConfiguration.class)
~~~

source code của integration phải được biên dịch lại với kiểu mới nếu class cũ không còn được cung cấp.

### 5.2. Ordering chỉ sắp xếp bean definitions

Ordering của auto-configuration quyết định thứ tự các configuration được xử lý và bean definitions được đăng ký. Nó **không quyết định thứ tự khởi tạo mọi bean instance**.

Bean instance được tạo theo dependency graph, constructor/method injection và các quan hệ như `@DependsOn`. Nếu một bean thực sự cần bean khác, hãy khai báo dependency qua tham số constructor hoặc `@Bean` method. Không dùng `@AutoConfigureAfter` để thay cho dependency injection.

### 5.3. @AutoConfigureOrder không thay thế quan hệ tương đối

`@AutoConfigureOrder` đặt thứ tự ưu tiên tổng quát cho auto-configuration. Nó hữu ích khi muốn điều chỉnh thứ tự mà không tạo liên kết trực tiếp giữa hai lớp.

Tuy nhiên, nếu contract yêu cầu “sau AcmeAutoConfiguration”, một số thứ tự tuyệt đối không biểu đạt rõ quan hệ đó. Khi rename, hãy cập nhật hoặc ánh xạ quan hệ before/after thay vì chỉ thêm một số order tùy ý.

## 6. Spring Boot 3.4+: dùng AutoConfiguration.replacements

Spring Boot 3.4 bổ sung cơ chế khai báo class auto-configuration thay thế. Cơ chế này hỗ trợ việc đổi package hoặc tên class mà vẫn giữ khả năng xử lý các tham chiếu cũ trong exclusions và before/after ordering.

Tạo resource:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Nội dung:

~~~properties
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

Ý nghĩa:

- Vế trái là FQCN cũ.
- Vế phải là FQCN mới.
- Spring Boot dùng mapping để xử lý các tham chiếu auto-configuration cũ thuộc những trường hợp được hỗ trợ.

Đồng thời cập nhật `AutoConfiguration.imports`:

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

Imports chỉ liệt kê class thay thế. Replacement file là metadata ánh xạ tên; nó không phải file đăng ký candidate.

### 6.1. Cấu trúc resource sau khi đổi tên

~~~text
src/main/resources/
  META-INF/
    spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports
      org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Nội dung hai file:

~~~text
# AutoConfiguration.imports
com.acme.autoconfigure.core.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
~~~

~~~properties
# AutoConfiguration.replacements
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

Nếu có nhiều lớp đổi tên, mỗi lớp có một mapping riêng:

~~~properties
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeWebAutoConfiguration=com.acme.autoconfigure.web.AcmeWebAutoConfiguration
com.acme.autoconfigure.AcmeMetricsAutoConfiguration=com.acme.autoconfigure.observation.AcmeMetricsAutoConfiguration
~~~

Chỉ thêm các mapping thực sự cần. Không tạo mapping cho một class không phải auto-configuration hoặc cho một class mới không có tiền nhiệm.

### 6.2. Replacement metadata hỗ trợ những gì?

Theo tài liệu Spring Boot 3.4, replacement được dùng để xử lý các tham chiếu cũ trong:
- Quan hệ `before` / `after` ordering.
- Exclusions của auto-configuration.

Điều đó giúp ứng dụng hoặc thư viện tích hợp chưa cập nhật tên vẫn có thể được xử lý theo tên thay thế trong những trường hợp trên.

Không xem file này như một công cụ đổi tên tổng quát cho Java. Nó không sửa source code, import statement, reflection string tùy chỉnh, tên bean, tên property, URL, package scan hoặc bất kỳ chuỗi tùy ý nào trong ứng dụng.

Với `@ImportAutoConfiguration` hoặc code gọi class trực tiếp, hãy rà soát các class reference cụ thể và cập nhật theo API mà consumer biên dịch. Đừng giả định replacement metadata thay thế mọi tham chiếu Java.

### 6.3. Có cần giữ class cũ trong AutoConfiguration.imports không?

Không. Với cơ chế replacement, imports file chỉ liệt kê class mới. Nếu cả class cũ và mới đều được đăng ký như hai candidate độc lập, cả hai có thể tham gia xử lý và tạo bean trùng lặp.

Nếu cần giữ một Java type cũ để hỗ trợ source compatibility, phải thiết kế riêng vai trò của type đó. Không thêm nó trở lại imports chỉ để giữ tên cũ cho exclusions hoặc ordering; replacement metadata đã đảm nhiệm phạm vi tương thích mà Boot hỗ trợ.

## 7. Ranh giới phiên bản: Boot 3.3 và Boot 3.4+

Replacement metadata được giới thiệu trong Spring Boot 3.4.0-M3 và có trong Spring Boot 3.4.0 trở đi.

| Phiên bản | Có đọc AutoConfiguration.replacements? | Cách xử lý tên cũ |
| --- | --- | --- |
| Spring Boot 3.3.x | Không | Người dùng cần cập nhật exclusion/ordering references sang FQCN mới; giữ FQCN ổn định nếu không thể phối hợp migration |
| Spring Boot 3.4+ | Có | Mapping cũ → mới được dùng cho exclusions và before/after ordering được hỗ trợ |
| Artifact dùng chung cho 3.3 và 3.4+ | 3.3 bỏ qua file, 3.4+ đọc file | Mapping chỉ bảo vệ consumer ở 3.4+; tài liệu migration cho 3.3 vẫn phải nêu thay đổi |

### 7.1. Nếu thư viện vẫn hỗ trợ Spring Boot 3.3

Có hai lựa chọn thực tế:

**Lựa chọn A — Giữ FQCN cũ trong dòng phát hành còn hỗ trợ Boot 3.3.**

Nếu việc đổi tên chỉ là refactor package hoặc tổ chức source, giữ class auto-configuration ở package cũ và chuyển phần implementation sang class/helper khác. Đây là cách tránh buộc mọi consumer 3.3 cập nhật cấu hình cùng lúc.

**Lựa chọn B — Đổi FQCN và công bố migration bắt buộc cho consumer 3.3.**

Cập nhật:
- `exclude` và `excludeName`.
- `spring.autoconfigure.exclude`.
- `before`, `after`, `beforeName`, `afterName`.
- `@AutoConfigureBefore` và `@AutoConfigureAfter`.
- Các test và module tham chiếu trực tiếp.

Trong artifact có hỗ trợ Boot 3.4+, thêm replacement metadata để consumer trên 3.4+ vẫn được hỗ trợ khi họ còn dùng tên cũ trong các trường hợp framework ánh xạ.

Không nên quảng bá rằng một artifact có replacement file sẽ tự bảo vệ mọi consumer Boot 3.3. Boot 3.3 không đọc file đó.

## 8. Ví dụ migration hoàn chỉnh

Giả sử ban đầu thư viện có:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Lớp mới:

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

### 8.1. Class mới

**Tệp:** `src/main/java/com/acme/autoconfigure/core/AcmeAutoConfiguration.java`

~~~java
package com.acme.autoconfigure.core;

import com.acme.api.AcmeClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeClient.class)
    AcmeClient acmeClient() {
        return new DefaultAcmeClient();
    }
}
~~~

Ví dụ giả định `AcmeClient` và `DefaultAcmeClient` là API/implementation có sẵn trong thư viện. Nội dung bean không phải trọng tâm của migration; điều cần xác minh là FQCN mới được đăng ký và các tham chiếu cũ được ánh xạ đúng.

### 8.2. Imports file

**Tệp:** `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

### 8.3. Replacement file

**Tệp:** `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements`

~~~properties
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

### 8.4. Ordering của integration bên ngoài

Một integration được biên dịch trước đó có thể vẫn khai báo tên cũ:

~~~java
package example.partner;

import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration(
        afterName = "com.acme.autoconfigure.AcmeAutoConfiguration")
public class PartnerMetricsAutoConfiguration {
}
~~~

Trên Spring Boot 3.4+, replacement metadata cho phép Boot liên kết tên cũ với class mới khi xử lý ordering. Khi có thể phát hành phiên bản mới của integration, vẫn nên cập nhật source sang tên mới để code dễ đọc và không phụ thuộc compatibility mapping lâu dài.

## 9. Kiểm thử migration bằng ApplicationContextRunner

Cần kiểm thử ít nhất ba hợp đồng:

1. Candidate mới được phát hiện qua imports file.
2. Exclusion bằng tên cũ vẫn loại candidate mới trên Boot 3.4+.
3. Quan hệ ordering tham chiếu tên cũ vẫn được giải quyết trên Boot 3.4+.

Ví dụ sau dành cho **Spring Boot 3.4+** vì nó kiểm tra replacement metadata.

### 9.1. Auto-configuration mới cung cấp marker bean

~~~java
package com.acme.autoconfigure.core;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Bean
    public AcmeMarker acmeMarker() {
        return new AcmeMarker();
    }
}
~~~

~~~java
package com.acme.autoconfigure.core;

public class AcmeMarker {
}
~~~

### 9.2. Downstream configuration vẫn tham chiếu tên cũ

**Tệp test:** `src/test/java/example/consumer/AardvarkDownstreamAutoConfiguration.java`

~~~java
package example.consumer;

import com.acme.autoconfigure.core.AcmeMarker;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(
        afterName = "com.acme.autoconfigure.AcmeAutoConfiguration")
public class AardvarkDownstreamAutoConfiguration {

    @Bean
    @ConditionalOnBean(AcmeMarker.class)
    public DownstreamFeature downstreamFeature() {
        return new DownstreamFeature();
    }
}
~~~

~~~java
package example.consumer;

public class DownstreamFeature {
}
~~~

Đưa downstream test configuration vào candidate list của test bằng resource:

**Tệp:** `src/test/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

~~~text
example.consumer.AardvarkDownstreamAutoConfiguration
~~~

Tên `AardvarkDownstreamAutoConfiguration` được chọn để dễ thấy tác dụng của quan hệ `afterName`: khi ordering edge không được nhận diện, nó có thể được sắp trước class Acme theo tên. Khi replacement được nhận diện, nó được áp dụng sau Acme.

### 9.3. JUnit 5 kiểm tra exclusion và ordering

**Tệp:** `src/test/java/example/consumer/AutoConfigurationReplacementTests.java`

~~~java
package example.consumer;

import com.acme.autoconfigure.core.AcmeMarker;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationReplacementTests {

    private static final String OLD_CLASS =
            "com.acme.autoconfigure.AcmeAutoConfiguration";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void newCandidateIsDiscoveredAndDownstreamOrderingIsPreserved() {
        this.runner
                .withUserConfiguration(EnabledApplication.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeMarker.class);
                    assertThat(context).hasSingleBean(DownstreamFeature.class);
                });
    }

    @Test
    void exclusionUsingOldNameExcludesTheReplacement() {
        this.runner
                .withUserConfiguration(ExcludingApplication.class)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(AcmeMarker.class);
                    assertThat(context).doesNotHaveBean(DownstreamFeature.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class EnabledApplication {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(excludeName = OLD_CLASS)
    static class ExcludingApplication {
    }
}
~~~

Test này dựa vào các resource trong main/test classpath:

- Main `AutoConfiguration.imports` liệt kê AcmeAutoConfiguration mới.
- Main `AutoConfiguration.replacements` ánh xạ FQCN cũ sang FQCN mới.
- Test `AutoConfiguration.imports` thêm downstream candidate.
- Downstream candidate vẫn tham chiếu tên cũ bằng `afterName`.

**Kết quả kỳ vọng trên Boot 3.4+:**
- Test thứ nhất có cả `AcmeMarker` và `DownstreamFeature`; điều đó xác nhận candidate mới được phát hiện và quan hệ ordering cũ được ánh xạ.
- Test thứ hai không có `AcmeMarker`; tên cũ trong `excludeName` đã loại class thay thế. Vì downstream bean cần `AcmeMarker`, `DownstreamFeature` cũng không xuất hiện.

Đây là test tích hợp cho auto-configuration discovery, exclusion và ordering. Nó không chỉ gọi trực tiếp `AutoConfigurations.of(NewClass.class)`, vì cách gọi trực tiếp sẽ bỏ qua quá trình đọc candidate/replacement metadata của `@EnableAutoConfiguration`.

### 9.4. Dependency và lệnh chạy

Yêu cầu Java 17+, Spring Boot 3.4+ và JUnit 5. Trong module Gradle đã quản lý version Spring Boot bằng plugin hoặc BOM:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Chạy:

~~~bash
# Linux/macOS
./gradlew test --tests "example.consumer.AutoConfigurationReplacementTests"

# Windows
gradlew.bat test --tests "example.consumer.AutoConfigurationReplacementTests"
~~~

**Kết quả kỳ vọng:** hai test PASS. Ví dụ kiểm thử được thiết kế cho Boot 3.4+; nếu chạy bằng Boot 3.3, replacement metadata không được xử lý và test tương thích tên cũ không thể được kỳ vọng pass.

## 10. Kiểm tra JAR sau khi build

Test source chưa đủ nếu resource bị thiếu khỏi artifact. Sau khi build module autoconfigure:

~~~bash
jar tf build/libs/acme-spring-boot-autoconfigure-1.2.0.jar
~~~

Kiểm tra có hai resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Đọc imports file và xác nhận chỉ có tên mới:

~~~text
com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

Đọc replacements file và xác nhận mapping:

~~~properties
com.acme.autoconfigure.AcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
~~~

Nếu module dùng `spring-boot-autoconfigure-processor`, hãy build lại để generated metadata phản ánh class mới. Không chỉnh tay file metadata do annotation processor tạo; sửa source/annotation rồi build lại.

Một kiểm tra hữu ích trong CI là giải nén JAR và so sánh resource với giá trị mong đợi. Điều này bắt được trường hợp source đúng nhưng artifact phát hành vẫn đóng gói imports hoặc replacements cũ.

## 11. Kế hoạch migration an toàn

Thực hiện theo trình tự:

1. **Xác định lý do đổi tên.** Nếu chỉ muốn sắp xếp lại package nội bộ, cân nhắc giữ FQCN và chuyển implementation sang helper/delegate.
2. **Tìm mọi tham chiếu cũ.** Tìm FQCN trong source, resources, tests, sample app, YAML, deployment chart và tài liệu.
3. **Chọn dải Spring Boot được hỗ trợ.** Xác định có cần hỗ trợ 3.3 hay chỉ 3.4+.
4. **Tạo class mới.** Giữ nguyên behavior, conditions và bean contract trong lần rename nếu có thể.
5. **Cập nhật AutoConfiguration.imports.** Chỉ liệt kê class mới.
6. **Thêm AutoConfiguration.replacements nếu hỗ trợ 3.4+.** Ánh xạ old FQCN sang new FQCN.
7. **Sửa ordering nội bộ.** Cập nhật `before`, `after`, `beforeName`, `afterName` và các annotation ordering do chính thư viện sở hữu.
8. **Xử lý consumer 3.3.** Cập nhật migration guide để người dùng đổi exclusion/ordering references, hoặc giữ FQCN cũ trong nhánh phát hành còn hỗ trợ 3.3.
9. **Kiểm thử hai hướng.** Kiểm tra default discovery, exclusion bằng tên cũ, ordering bằng tên cũ và cấu hình sau khi cập nhật sang tên mới.
10. **Kiểm tra JAR.** Xác minh imports, replacements và generated metadata.
11. **Phát hành migration note.** Nêu FQCN cũ, FQCN mới, phiên bản hỗ trợ replacement và các bước dành riêng cho Boot 3.3.

Không nên kết hợp rename class với việc thay đổi bean behavior, property defaults hoặc dependency graph nếu không cần. Tách thay đổi giúp xác định rõ lỗi đến từ rename hay từ behavior mới.

## 12. Lỗi thường gặp

1. **Chỉ đổi tên file Java.** Package/FQCN trong source và imports file vẫn có thể cũ; kiểm tra toàn bộ resource.
2. **Quên AutoConfiguration.imports.** Boot không tìm thấy class mới hoặc cố load class cũ.
3. **Giữ cả tên cũ và mới trong imports khi dùng replacement.** Hai candidate có thể cùng được xử lý và tạo cấu hình trùng lặp.
4. **Đặt replacement mapping ngược chiều.** Vế trái phải là FQCN cũ, vế phải là FQCN thay thế.
5. **Đặt sai tên resource.** Tên file phải chính xác là `org.springframework.boot.autoconfigure.AutoConfiguration.replacements` dưới `META-INF/spring`.
6. **Giả định Boot 3.3 đọc replacement file.** Tính năng được giới thiệu ở Boot 3.4; Boot 3.3 cần migration riêng.
7. **Quên property spring.autoconfigure.exclude.** Exclusion có thể nằm trong cấu hình môi trường, không xuất hiện trong repository source.
8. **Chỉ cập nhật exclude mà quên ordering.** `afterName` hoặc `beforeName` ở thư viện khác có thể vẫn trỏ tên cũ.
9. **Dùng @AutoConfigureOrder để chữa mọi quan hệ cũ.** Thứ tự tuyệt đối không thay thế đầy đủ một quan hệ before/after.
10. **Nghĩ replacement metadata đổi mọi chuỗi.** Nó chỉ hỗ trợ những tham chiếu auto-configuration mà Boot quy định; reflection, direct import và chuỗi tùy chỉnh cần cập nhật riêng.
11. **Không kiểm tra source compatibility.** Consumer biên dịch lại với class literal cũ có thể không tìm thấy type cũ.
12. **Test bằng AutoConfigurations.of rồi kết luận replacement hoạt động.** Cách này nạp class trực tiếp và không kiểm tra selector/imports/replacements như `@EnableAutoConfiguration`.
13. **Chỉ test ứng dụng JVM nhưng không test artifact.** JAR có thể thiếu resource dù test trong IDE chạy được.
14. **Không phân biệt ordering và bean creation.** Auto-configuration order điều khiển bean definition processing; dependency injection mới biểu đạt quan hệ sử dụng bean.
15. **Không công bố giới hạn phiên bản.** Người dùng Boot 3.3 có thể nghĩ mapping cũ được bảo vệ trong khi framework không đọc resource đó.

## 13. Checklist trước khi phát hành

### Tên và registration

- [ ] FQCN mới đã được chốt.
- [ ] `AutoConfiguration.imports` chỉ liệt kê class mới.
- [ ] Không có resource khác còn đăng ký class cũ ngoài chủ đích.
- [ ] Generated auto-configuration metadata được tạo lại.

### Exclusions và ordering

- [ ] Đã tìm `exclude`, `excludeName` và `spring.autoconfigure.exclude`.
- [ ] Đã tìm `before`, `after`, `beforeName`, `afterName`.
- [ ] Đã kiểm tra `@AutoConfigureBefore` và `@AutoConfigureAfter`.
- [ ] Đã rà soát `@ImportAutoConfiguration` và tham chiếu class trực tiếp.
- [ ] Replacement mapping đúng chiều old → new nếu dùng Boot 3.4+.

### Tương thích và test

- [ ] Dải Spring Boot được hỗ trợ được ghi rõ.
- [ ] Migration cho Boot 3.3 được công bố nếu còn hỗ trợ phiên bản này.
- [ ] Test discovery của class mới.
- [ ] Test exclusion bằng tên cũ trên Boot 3.4+.
- [ ] Test ordering tham chiếu tên cũ trên Boot 3.4+.
- [ ] Test exclusion/order với tên mới.
- [ ] JAR đã publish chứa imports và replacements đúng.
- [ ] Migration note liệt kê các cấu hình consumer cần cập nhật.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Đổi package của `AcmeAutoConfiguration` có thể ảnh hưởng những nơi nào?

**Đáp án:** Imports file, exclusions, before/after ordering, class references trong source, test, resource, sample app và tài liệu.

**Câu 2.** File nào ánh xạ tên auto-configuration cũ sang mới trên Spring Boot 3.4+?

**Đáp án:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements`, với mỗi dòng có dạng `old.FQCN=new.FQCN`.

**Câu 3.** Sau khi thêm replacement mapping, imports file nên chứa cả hai tên không?

**Đáp án:** Không. Imports file chỉ liệt kê class thay thế; replacement file lưu mapping tương thích.

**Câu 4.** Spring Boot 3.3 có sử dụng replacement metadata không?

**Đáp án:** Không. Tính năng được giới thiệu trong Spring Boot 3.4.0; consumer 3.3 cần cập nhật các tham chiếu cũ hoặc giữ FQCN ổn định.

**Câu 5.** `@AutoConfiguration(afterName = "...")` điều khiển điều gì?

**Đáp án:** Nó yêu cầu auto-configuration hiện tại được áp dụng sau class có FQCN được chỉ định. Nó ảnh hưởng thứ tự xử lý bean definitions, không quyết định thứ tự tạo mọi bean instance.

**Câu 6.** Test nào xác minh replacement metadata thực sự được Spring Boot sử dụng?

**Đáp án:** Integration test chạy qua `@EnableAutoConfiguration`, giữ exclusion/ordering tham chiếu tên cũ và xác nhận class mới bị loại hoặc quan hệ thứ tự vẫn được áp dụng. Nạp trực tiếp bằng `AutoConfigurations.of` không đủ để kiểm tra cơ chế replacement.

## 15. Ghi nhớ

FQCN của auto-configuration là một phần của contract tương thích vì ứng dụng và thư viện khác có thể dùng tên đó để disable hoặc sắp xếp auto-configuration. Khi rename, phải cập nhật imports file và rà soát exclusions cùng ordering references.

Với Spring Boot 3.4+, dùng `AutoConfiguration.replacements` để ánh xạ tên cũ sang tên mới cho exclusions và before/after ordering; imports file chỉ liệt kê class mới. Với Spring Boot 3.3, replacement metadata chưa được hỗ trợ, nên cần cập nhật consumer references hoặc giữ FQCN cũ trong dòng phát hành tương thích.

Cuối cùng, kiểm thử qua `@EnableAutoConfiguration` và kiểm tra JAR đã phát hành. Một rename chỉ hoàn tất khi class mới được phát hiện, các tham chiếu tương thích hoạt động theo đúng phiên bản Boot và không còn resource cũ ngoài chủ đích.

### Tài liệu Spring Boot chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — AutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 — AutoConfigurationImportSelector Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html)
- [Spring Boot 3.4 — Deprecating and Replacing Auto-configuration Classes](https://docs.spring.io/spring-boot/3.4/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.deprecating)
- [Spring Boot 3.4.0-M3 Release Notes — Auto-configuration replacements](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4.0-M3-Release-Notes)
