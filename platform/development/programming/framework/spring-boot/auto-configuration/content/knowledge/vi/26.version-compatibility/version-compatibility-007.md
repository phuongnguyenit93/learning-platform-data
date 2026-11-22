# AutoConfiguration.replacements ở phiên bản hỗ trợ và ánh xạ tên lớp cũ

## 1. Vấn đề khi đổi package hoặc tên auto-configuration

Một thư viện Spring Boot có thể cần di chuyển một auto-configuration class sang package mới, đổi tên để phản ánh đúng chức năng hoặc tách một cấu hình lớn thành các module nhỏ hơn.

Ví dụ, class cũ:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

được chuyển thành:

~~~text
com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

Nếu chỉ sửa tên class và cập nhật AutoConfiguration.imports, ứng dụng tiêu thụ có thể vẫn tham chiếu tên cũ ở nhiều nơi:

- @AutoConfigureBefore hoặc @AutoConfigureAfter.
- Các thuộc tính beforeName hoặc afterName của @AutoConfiguration.
- @SpringBootApplication(exclude = ...) hoặc excludeName.
- @EnableAutoConfiguration(exclude = ...) hoặc excludeName.

Những tham chiếu này có thể nằm trong chính thư viện, trong starter khác hoặc trong code của ứng dụng tiêu thụ. Người dùng phải tìm và sửa mọi tham chiếu tên cũ khi nâng thư viện.

Từ Spring Boot **3.4.0-M3**, Spring Boot hỗ trợ cơ chế thay thế tên auto-configuration class bằng file AutoConfiguration.replacements. Tính năng này có trong các bản phát hành ổn định Spring Boot 3.4.0 trở lên. Nó cho phép Spring Boot chuyển một số tham chiếu auto-configuration cũ sang class mới khi xử lý ordering và exclusions.

Bài dùng **Java 17 và Spring Boot 3.4.13** làm baseline minh họa. Đây là ví dụ của dòng Boot đã hỗ trợ tính năng; không áp dụng cú pháp này cho Boot 3.3.x.

## 2. Phiên bản nào hỗ trợ AutoConfiguration.replacements?

Đây là ranh giới tương thích cần xác định trước khi đổi tên class:

| Phiên bản Spring Boot | Hỗ trợ replacements | Cách xử lý |
| --- | --- | --- |
| Spring Boot 3.3.x trở xuống | Không có cơ chế này | Không dựa vào file replacements; giữ tên class cũ hoặc dùng artifact tương thích riêng |
| Spring Boot 3.4.0-M3 | Tính năng được giới thiệu | Có thể thử nghiệm trong milestone build |
| Spring Boot 3.4.0 trở lên | Có hỗ trợ | Dùng file replacements cùng AutoConfiguration.imports |
| Release line mới hơn | Kiểm tra reference docs của line đang hỗ trợ | Giữ test consumer để xác nhận hành vi sau nâng cấp |

Spring Boot 3.4.0-M3 release notes ghi rõ hỗ trợ deprecate và replace auto-configuration class được giới thiệu ở milestone này. Reference guide 3.4 mô tả file và cách sử dụng. Vì vậy, nếu ứng dụng vẫn chạy Spring Boot 3.3.x, không thể kỳ vọng nó tự hiểu file replacements được đóng gói trong JAR.

**Không chỉ kiểm tra version compile-time của thư viện.** Hãy kiểm tra version Spring Boot thực tế mà ứng dụng tiêu thụ resolve lúc runtime. Một JAR được build bằng Boot 3.4 nhưng chạy trong ứng dụng Boot 3.3 vẫn không có cơ chế remap của Boot 3.4.

### 2.1. Nếu thư viện hỗ trợ cả Boot 3.3 và Boot 3.4

Có hai lựa chọn an toàn:

1. Giữ nguyên FQCN cũ cho đến khi ngừng hỗ trợ Boot 3.3. Khi bỏ dòng Boot cũ, di chuyển class và phát hành mapping trong artifact dành cho Boot 3.4+.
2. Tách artifact hoặc module auto-configuration theo dòng Boot được hỗ trợ. Artifact cho Boot 3.3 giữ cơ chế/tên class tương thích cũ; artifact cho Boot 3.4+ dùng replacements.

Không phát hành một migration chỉ hoạt động trên Boot 3.4 rồi ghi trong tài liệu rằng nó tương thích với Boot 3.3. Ở Boot 3.3, exclusion theo tên cũ sẽ không được remap sang class mới.

## 3. Hai file cần phối hợp

Khi thay một auto-configuration class, Spring Boot sử dụng hai file riêng biệt.

### 3.1. AutoConfiguration.imports

File này liệt kê các auto-configuration class hiện đang được công bố trong JAR:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ sau khi di chuyển:

~~~text
com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
com.acme.reports.autoconfigure.metrics.ReportsMetricsAutoConfiguration
~~~

Mỗi dòng là một fully qualified class name. Sau khi thay thế, file imports phải chỉ tham chiếu class mới. Không tiếp tục liệt kê class cũ như một candidate thứ hai.

### 3.2. AutoConfiguration.replacements

Tạo file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Nội dung dùng định dạng Java Properties: tên class cũ ở bên trái dấu bằng, tên class thay thế ở bên phải:

~~~properties
com.acme.reports.autoconfigure.ReportsAutoConfiguration=com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

Hai vế đều là **fully qualified class name**, bao gồm package và tên class. Không ghi tên bean, tên module Maven, đường dẫn file Java hay chỉ tên class rút gọn.

Có thể khai báo nhiều mapping trong cùng file:

~~~properties
com.acme.reports.autoconfigure.ReportsAutoConfiguration=com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
com.acme.reports.autoconfigure.ReportsWebAutoConfiguration=com.acme.reports.autoconfigure.web.ReportsWebAutoConfiguration
com.acme.reports.autoconfigure.ReportsMetricsAutoConfiguration=com.acme.reports.autoconfigure.observability.ReportsMetricsAutoConfiguration
~~~

Mỗi dòng là một cặp cũ → mới độc lập. Nếu một class đổi package nhiều lần qua nhiều release, hãy ánh xạ tên cũ mà người dùng thực sự có thể đang tham chiếu trực tiếp đến class cuối cùng mà artifact hiện tại công bố. Đừng dựa vào một chuỗi alias nhiều bước.

### 3.3. Vai trò của từng file

| File | Vai trò |
| --- | --- |
| AutoConfiguration.imports | Khai báo class mới mà Spring Boot có thể import |
| AutoConfiguration.replacements | Ánh xạ tên class cũ sang tên class mới khi Spring Boot xử lý các tham chiếu được hỗ trợ |

File replacements không thay thế imports. Nó cũng không tự đăng ký class mới nếu class mới không có trong imports.

## 4. Spring Boot dùng mapping ở những đâu?

Tài liệu Spring Boot mô tả hai nhóm tham chiếu quan trọng: ordering và exclusions.

### 4.1. Ordering: before và after

Một auto-configuration khác có thể cần chạy sau cấu hình Reports:

~~~java
@AutoConfiguration(afterName =
        "com.acme.reports.autoconfigure.ReportsAutoConfiguration")
public class ReportsMetricsAutoConfiguration {
}
~~~

Đây là tham chiếu bằng tên cũ. Khi Spring Boot 3.4+ đọc metadata replacements, tên được ánh xạ sang:

~~~text
com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

Các trường hợp liên quan gồm:

- @AutoConfigureBefore.
- @AutoConfigureAfter.
- @AutoConfiguration(beforeName = ...).
- @AutoConfiguration(afterName = ...).

Nếu dùng Class<?> trong before hoặc after, code Java cần class tương ứng có thể compile. Khi class cũ đã bị xóa, dùng thuộc tính beforeName/afterName với tên chuỗi hoặc giữ một compatibility type phù hợp.

Ordering chỉ xác định thứ tự áp dụng auto-configuration và đăng ký bean definition. Nó không bảo đảm bean instance được tạo theo thứ tự đó; việc tạo instance vẫn phụ thuộc dependency và @DependsOn.

### 4.2. Exclusion: loại cấu hình cũ khỏi ứng dụng

Một ứng dụng có thể đã loại auto-configuration cũ bằng tên:

~~~java
@SpringBootApplication(
        excludeName =
                "com.acme.reports.autoconfigure.ReportsAutoConfiguration"
)
public class Application {
}
~~~

Với Spring Boot 3.4+, mapping trong AutoConfiguration.replacements cho phép tên cũ được chuyển thành tên class mới khi xử lý exclusion. Vì thế ứng dụng vẫn loại đúng auto-configuration sau khi thư viện đổi package.

Các API/annotation liên quan:

~~~java
@SpringBootApplication(exclude = SomeAutoConfiguration.class)
@SpringBootApplication(excludeName = "com.example.OldAutoConfiguration")
@EnableAutoConfiguration(exclude = SomeAutoConfiguration.class)
@EnableAutoConfiguration(excludeName = "com.example.OldAutoConfiguration")
~~~

Nếu dùng exclude = OldAutoConfiguration.class, code tiêu thụ cần class cũ tồn tại để biên dịch. Nếu class cũ đã bị xóa hoàn toàn, excludeName là cách tham chiếu bằng chuỗi không cần import class cũ.

### 4.3. Những gì replacements không làm

Đây là mapping tên class dành cho xử lý auto-configuration của Spring Boot, không phải alias class tổng quát của Java.

Nó không tự:

- Tạo class cũ hoặc làm cho import OldAutoConfiguration biên dịch được.
- Làm cho Class.forName("old.FQCN") trả về class mới.
- Chuyển mọi chuỗi class name tùy ý trong ứng dụng sang tên mới.
- Thay thế @Import(OldAutoConfiguration.class) trong code ứng dụng.
- Đổi tên bean, qualifier, bean name hoặc property.
- Di chuyển component được đăng ký bằng component scan.
- Chuyển một dependency Maven/Gradle cũ sang dependency mới.

Nếu consumer trực tiếp dùng class cũ trong source code, hãy cập nhật source hoặc giữ một compatibility class riêng. Không dựa vào file replacements để thay thế mọi API Java đã công bố.

## 5. Ví dụ di chuyển class hoàn chỉnh

Giả sử thư viện Acme có cấu trúc trước khi di chuyển:

~~~text
acme-reports-autoconfigure/
└── src/
    └── main/
        ├── java/com/acme/reports/autoconfigure/
        │   └── ReportsAutoConfiguration.java
        └── resources/META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Class cũ:

~~~java
package com.acme.reports.autoconfigure;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

Sau khi tách core auto-configuration sang package mới:

~~~text
acme-reports-autoconfigure/
└── src/
    └── main/
        ├── java/com/acme/reports/
        │   ├── ReportClient.java
        │   └── autoconfigure/
        │       ├── core/ReportsAutoConfiguration.java
        │       └── metrics/ReportsMetricsAutoConfiguration.java
        └── resources/META-INF/spring/
            ├── org.springframework.boot.autoconfigure.AutoConfiguration.imports
            └── org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

### 5.1. Class mới

**src/main/java/com/acme/reports/autoconfigure/core/ReportsAutoConfiguration.java**

~~~java
package com.acme.reports.autoconfigure.core;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

### 5.2. Cấu hình metrics tham chiếu tên cũ

**src/main/java/com/acme/reports/autoconfigure/metrics/ReportsMetricsAutoConfiguration.java**

~~~java
package com.acme.reports.autoconfigure.metrics;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(afterName =
        "com.acme.reports.autoconfigure.ReportsAutoConfiguration")
public class ReportsMetricsAutoConfiguration {

    @Bean
    @ConditionalOnBean(ReportClient.class)
    ReportsMetrics reportsMetrics(ReportClient client) {
        return new ReportsMetrics(client.endpoint());
    }

    public record ReportsMetrics(String endpoint) {
    }
}
~~~

Ví dụ giữ afterName cũ để minh họa việc mapping hỗ trợ tham chiếu ordering đã tồn tại. Trong code mới do chính thư viện kiểm soát, bạn cũng có thể cập nhật thẳng sang tên class mới để dễ đọc.

### 5.3. AutoConfiguration.imports sau migration

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
com.acme.reports.autoconfigure.metrics.ReportsMetricsAutoConfiguration
~~~

Chỉ có class mới. Không thêm dòng cho com.acme.reports.autoconfigure.ReportsAutoConfiguration.

### 5.4. AutoConfiguration.replacements

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements**

~~~properties
com.acme.reports.autoconfigure.ReportsAutoConfiguration=com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

Khi ứng dụng loại tên cũ hoặc một auto-configuration khác khai báo ordering theo tên cũ, Spring Boot 3.4+ có thể ánh xạ sang class mới.

## 6. Giữ compatibility cho code Java đang tham chiếu class cũ

File replacements giúp Spring Boot xử lý các tham chiếu class name trong ordering và exclusions. Nếu thư viện muốn giữ khả năng biên dịch cho code Java của consumer đang dùng OldAutoConfiguration.class, có thể cân nhắc giữ một compatibility type công khai trong package cũ.

Ví dụ shim tối giản:

~~~java
package com.acme.reports.autoconfigure;

@Deprecated(since = "3.4.0", forRemoval = true)
public final class ReportsAutoConfiguration {

    private ReportsAutoConfiguration() {
    }
}
~~~

Shim này chỉ giữ tên type để code cũ có thể compile trong giai đoạn chuyển tiếp. Nó **không** được đánh dấu @AutoConfiguration, không chứa bean method và không được liệt kê trong AutoConfiguration.imports. Class mới là cấu hình duy nhất được Spring Boot import.

Cần quyết định riêng việc giữ shim:

- Nếu chỉ cần tương thích với excludeName hoặc afterName, mapping có thể hoạt động mà không cần class cũ tồn tại.
- Nếu consumer dùng OldAutoConfiguration.class, class cũ phải còn trên compile classpath hoặc consumer phải đổi sang cách tham chiếu bằng tên.
- Nếu consumer dùng @Import(OldAutoConfiguration.class) hoặc gọi trực tiếp API của class cũ, replacements không thay thế được hành vi đó. Cần migration code hoặc compatibility facade có triển khai phù hợp.
- Không giữ shim có bean method hoặc được import như auto-configuration thứ hai, vì có thể đăng ký bean trùng hoặc tạo hai nhánh cấu hình.

Chỉ giữ shim khi có nhu cầu tương thích source thực tế và có kế hoạch loại bỏ rõ ràng.

## 7. Project Maven mẫu để kiểm thử replacement

Ví dụ sau kiểm tra hai hành vi quan trọng:

1. Không có exclusion: class mới được phát hiện từ AutoConfiguration.imports và đăng ký ReportClient.
2. Ứng dụng vẫn exclude bằng FQCN cũ: Spring Boot 3.4+ ánh xạ exclusion sang class mới và không đăng ký ReportClient.

### 7.1. Cấu trúc

~~~text
autoconfiguration-replacement-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/reports/
    │   │   ├── ReportClient.java
    │   │   └── autoconfigure/core/
    │   │       └── ReportsAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       ├── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.replacements
    └── test/
        └── java/com/acme/reports/
            └── AutoConfigurationReplacementTests.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>autoconfiguration-replacement-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

### 7.3. ReportClient.java

**src/main/java/com/acme/reports/ReportClient.java**

~~~java
package com.acme.reports;

public record ReportClient(String endpoint) {
}
~~~

### 7.4. ReportsAutoConfiguration.java

**src/main/java/com/acme/reports/autoconfigure/core/ReportsAutoConfiguration.java**

~~~java
package com.acme.reports.autoconfigure.core;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

### 7.5. AutoConfiguration.imports

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

### 7.6. AutoConfiguration.replacements

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements**

~~~properties
com.acme.reports.autoconfigure.ReportsAutoConfiguration=com.acme.reports.autoconfigure.core.ReportsAutoConfiguration
~~~

### 7.7. AutoConfigurationReplacementTests.java

**src/test/java/com/acme/reports/AutoConfigurationReplacementTests.java**

~~~java
package com.acme.reports;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationReplacementTests {

    private static final String OLD_AUTO_CONFIGURATION =
            "com.acme.reports.autoconfigure.ReportsAutoConfiguration";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner();

    @Test
    void discoversReplacementClassFromImports() {
        runner.withUserConfiguration(ApplicationWithAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://reports.example.test");
                });
    }

    @Test
    void oldExclusionNameExcludesReplacementClass() {
        runner.withUserConfiguration(ApplicationExcludingOldName.class)
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class ApplicationWithAutoConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(excludeName = OLD_AUTO_CONFIGURATION)
    static class ApplicationExcludingOldName {
    }
}
~~~

Điểm quan trọng trong test thứ hai là OLD_AUTO_CONFIGURATION chỉ là chuỗi FQCN. Test không import class cũ và class cũ không cần tồn tại trong project. Spring Boot đọc file replacements, chuyển exclusion sang class mới rồi loại class đó khỏi danh sách auto-configuration được áp dụng.

### 7.8. Chạy test và kiểm tra JAR

Chạy:

~~~bash
mvn clean test
~~~

Kỳ vọng hai test pass:

| Test | Kết quả |
| --- | --- |
| Không exclude | Có đúng một ReportClient, endpoint đúng |
| Exclude bằng tên cũ | Không có ReportClient |

Sau khi đóng gói:

~~~bash
mvn clean package
~~~

Kiểm tra JAR:

~~~bash
jar tf target/autoconfiguration-replacement-demo-1.0.0.jar
~~~

Trong JAR phải có cả hai resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Đồng thời xác nhận AutoConfiguration.imports chỉ có class mới và AutoConfiguration.replacements có đúng cặp FQCN cũ → mới. Test trong cùng module xác nhận resource ở classpath build; kiểm thử thêm một ứng dụng consumer độc lập với JAR đã publish/stage nếu thư viện được phát hành cho bên ngoài.

## 8. Lộ trình migration theo từng bước

Khi cần đổi package hoặc tên auto-configuration, thực hiện theo trình tự:

1. **Xác định version support.** Xác nhận ứng dụng tiêu thụ dùng Spring Boot 3.4.0-M3 hoặc bản ổn định 3.4.0+.
2. **Chọn FQCN mới.** Tên package và class phản ánh đúng trách nhiệm mới, tránh di chuyển nhiều lần không cần thiết.
3. **Di chuyển implementation.** Chuyển bean methods, condition và imports Java sang class mới; giữ nguyên hành vi bean nếu migration chỉ nhằm đổi package.
4. **Cập nhật AutoConfiguration.imports.** Xóa tên cũ, chỉ liệt kê class mới.
5. **Thêm AutoConfiguration.replacements.** Mỗi class cũ có một mapping trực tiếp đến class mới.
6. **Rà soát ordering.** Tìm @AutoConfigureBefore, @AutoConfigureAfter, beforeName, afterName trong thư viện và module tích hợp.
7. **Rà soát exclusions.** Kiểm tra ví dụ, tài liệu, starter khác và code tiêu thụ có loại class bằng tên cũ không.
8. **Quyết định compatibility shim.** Chỉ giữ type cũ nếu cần tương thích source hoặc class literal.
9. **Viết consumer test.** Xác nhận exclusion tên cũ thực sự loại class mới trong Spring Boot version mục tiêu.
10. **Kiểm tra artifact.** Xác nhận cả hai resource được đóng gói và nội dung đúng trong JAR phát hành.
11. **Cập nhật tài liệu.** Công bố FQCN mới, thời điểm chuyển đổi, version tối thiểu và cách thay thế tham chiếu cũ.
12. **Phát hành theo compatibility matrix.** Không đưa tính năng 3.4+ vào một release tuyên bố hỗ trợ 3.3.x nếu không có phương án tương thích riêng.

## 9. Các tình huống cần chú ý

### 9.1. Đổi package nhưng giữ nguyên simple class name

Ví dụ:

~~~text
com.acme.old.ReportsAutoConfiguration
    ->
com.acme.new.autoconfigure.ReportsAutoConfiguration
~~~

Dù simple name không đổi, FQCN đã đổi. Mapping vẫn phải ghi đầy đủ cả package cũ và mới.

### 9.2. Đổi cả package lẫn class name

~~~text
com.acme.old.ReportsAutoConfiguration
    ->
com.acme.reports.autoconfigure.core.ReportCoreAutoConfiguration
~~~

Đây vẫn là một mapping đơn. Các tham chiếu cũ trong ordering và exclusions cần dùng đúng FQCN cũ.

### 9.3. Tách một auto-configuration thành nhiều class mới

Giả sử class cũ chứa cả core và metrics, sau migration tách thành:

~~~text
OldReportsAutoConfiguration
    ->
ReportsCoreAutoConfiguration
ReportsMetricsAutoConfiguration
~~~

Một mapping cũ → mới không thể tự diễn tả việc một class cũ được chia thành hai class mới. AutoConfiguration.replacements ánh xạ một tên cũ tới một tên thay thế. Hãy chọn class đại diện phù hợp với ý nghĩa tương thích của tên cũ, còn việc đăng ký các cấu hình bổ sung phải được thiết kế rõ trong imports và code.

Không tạo nhiều dòng cùng một key cũ để mong một exclusion cũ tự loại tất cả class mới. Nếu một cấu hình cũ đã bị tách, hãy thiết kế lại API exclusion và hướng dẫn consumer cập nhật theo từng tính năng.

### 9.4. Di chuyển class sang module JAR khác

Replacement file phải có mặt trên runtime classpath mà Spring Boot sử dụng để đọc auto-configuration. Nếu mapping nằm trong một module không được ứng dụng đưa vào runtime, Spring Boot không thể đọc nó.

Đặt file trong module auto-configure đang công bố class mới, đóng gói nó vào JAR và kiểm tra từ ứng dụng consumer. Không chỉ để file trong module parent hoặc module build-only.

### 9.5. Ứng dụng vẫn dùng Spring Boot 3.3.x

Boot 3.3 không có cơ chế replacements được giới thiệu ở Boot 3.4. Nếu JAR mới chỉ công bố class mới và consumer 3.3 vẫn exclude tên cũ, exclusion cũ không được tự ánh xạ.

Trong trường hợp đó:

- Giữ FQCN cũ trong artifact dành cho Boot 3.3.
- Hoặc phát hành artifact/module riêng cho Boot 3.3 và Boot 3.4+.
- Hoặc trì hoãn đổi package cho đến khi kết thúc hỗ trợ Boot 3.3.

Một class shim có thể giữ source compatibility, nhưng nó không làm Boot 3.3 tự hiểu file replacements. Nếu cần runtime behavior trên Boot 3.3, hãy bảo đảm auto-configuration cũ vẫn được đăng ký theo cơ chế mà release đó hỗ trợ.

## 10. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Exclusion tên cũ không còn tác dụng | Ứng dụng đang chạy Boot 3.3 hoặc file mapping không có trên runtime classpath | Kiểm tra version Boot và JAR chứa replacements |
| Class mới không được tự cấu hình | Imports vẫn liệt kê class cũ hoặc thiếu class mới | Chỉ liệt kê class mới trong AutoConfiguration.imports |
| Đã thêm replacements nhưng không remap | Sai tên file, sai thư mục hoặc sai FQCN | Dùng đúng path và mapping old FQCN = new FQCN |
| Exclusion cũ vẫn tạo bean mới | Runtime không đọc mapping hoặc artifact đang dùng không chứa resource | Kiểm tra JAR consumer thực sự resolve |
| Code Java không compile sau khi xóa class cũ | Consumer đang tham chiếu OldClass.class | Giữ compatibility type hoặc đổi sang excludeName/beforeName |
| @Import(OldClass.class) không được thay thế | Đây không phải phạm vi remapping của replacements | Cập nhật import hoặc viết facade tương thích |
| Bean bị đăng ký hai lần | Cả class cũ và mới vẫn được liệt kê như hai candidate | Chỉ liệt kê replacement class |
| Ordering thay đổi ngoài ý muốn | Tham chiếu before/after chưa được rà soát hoặc mapping sai | Kiểm tra FQCN cũ, mới và test thứ tự áp dụng |
| Một class cũ được tách thành nhiều class mới | Cố dùng một mapping như cơ chế one-to-many | Thiết kế API mới và hướng dẫn migration cho từng tính năng |
| File nằm trong module không được runtime dùng | Mapping không có trong JAR tiêu thụ | Đưa resource vào artifact autoconfigure được publish |
| Test trong IDE pass nhưng JAR thiếu resource | Resource không được đóng gói hoặc cấu hình build loại bỏ file | Kiểm tra jar tf trên artifact thực tế |
| Dùng replacements trong artifact tuyên bố hỗ trợ 3.3 | Version support của tính năng không được tôn trọng | Giữ class cũ hoặc tách artifact theo Boot line |

## 11. Checklist trước khi phát hành

### Version và tương thích

- [ ] Xác nhận tính năng chỉ được dùng với Spring Boot 3.4.0-M3 trở lên.
- [ ] Xác định rõ các Boot line mà artifact cam kết hỗ trợ.
- [ ] Có phương án cho consumer Boot 3.3.x nếu vẫn hỗ trợ line này.
- [ ] Không để một release tuyên bố hỗ trợ 3.3 nhưng phụ thuộc vào remapping chỉ có từ 3.4.

### Metadata và class

- [ ] File nằm đúng tại META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements.
- [ ] Mapping dùng FQCN đầy đủ và đúng thứ tự cũ = mới.
- [ ] AutoConfiguration.imports chỉ liệt kê class mới.
- [ ] Class mới có @AutoConfiguration và các condition cần thiết.
- [ ] Các tham chiếu before/after đã được rà soát.
- [ ] Các exclusion cũ đã được kiểm thử.
- [ ] Compatibility shim (nếu có) không được import như một auto-configuration thứ hai.

### Kiểm thử và phát hành

- [ ] Test không exclusion để xác nhận class mới được phát hiện.
- [ ] Test exclusion bằng tên cũ để xác nhận mapping.
- [ ] Test ordering nếu thứ tự giữa các auto-configuration là contract quan trọng.
- [ ] Kiểm tra hai resource trong JAR cuối cùng.
- [ ] Test từ một consumer độc lập với đúng version Spring Boot mục tiêu.
- [ ] Release notes nêu FQCN mới, version tối thiểu và hướng dẫn cho consumer.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** AutoConfiguration.replacements được hỗ trợ từ phiên bản nào?  
**Đáp án:** Tính năng được giới thiệu trong Spring Boot 3.4.0-M3 và có trong các bản ổn định 3.4.0 trở lên.

**Câu 2.** File replacements nằm ở đâu?  
**Đáp án:** META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements.

**Câu 3.** Giá trị của mỗi dòng mapping có định dạng gì?  
**Đáp án:** Fully qualified class name cũ ở bên trái dấu bằng, class thay thế ở bên phải.

**Câu 4.** Sau khi di chuyển class, AutoConfiguration.imports cần thay đổi ra sao?  
**Đáp án:** Chỉ liệt kê class thay thế. Không tiếp tục liệt kê class cũ như candidate thứ hai.

**Câu 5.** Những tham chiếu nào được Spring Boot xử lý qua replacements?  
**Đáp án:** Các tham chiếu auto-configuration trong ordering before/after và exclusions.

**Câu 6.** Replacements có làm import OldAutoConfiguration trong Java tự trỏ sang class mới không?  
**Đáp án:** Không. Đây không phải alias ở cấp JVM hoặc Java compiler. Cần cập nhật source hoặc giữ compatibility type.

**Câu 7.** Một ứng dụng Boot 3.3 có tự remap exclusion cũ khi JAR chứa file replacements không?  
**Đáp án:** Không. Cơ chế được giới thiệu ở Boot 3.4.0-M3; Boot 3.3 không xử lý mapping đó.

**Câu 8.** Có thể dùng một dòng mapping cũ → mới để thay một class cũ bằng ba auto-configuration mới không?  
**Đáp án:** Không. Mapping là một tên thay thế cho một tên cũ. One-to-many cần thiết kế migration riêng.

**Câu 9.** Có cần giữ class cũ trong AutoConfiguration.imports sau khi thay thế không?  
**Đáp án:** Không. Imports chỉ liệt kê class mới; file replacements xử lý các tham chiếu cũ trong phạm vi Spring Boot hỗ trợ.

**Câu 10.** Làm sao kiểm tra mapping đã hoạt động?  
**Đáp án:** Dùng một consumer test với @EnableAutoConfiguration(excludeName = "FQCN-cũ"), xác nhận bean của class mới không xuất hiện, sau đó kiểm tra cả hai resource trong JAR phát hành.

## 13. Tài liệu tham khảo chính thức

- [Spring Boot 3.4 — Creating Your Own Auto-configuration, phần Deprecating and Replacing Auto-configuration Classes](https://docs.spring.io/spring-boot/3.4/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.4.0-M3 Release Notes — Deprecating and Replacing Auto-configuration Classes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4.0-M3-Release-Notes)
- [Spring Boot 3.4 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.4-Release-Notes)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)

**Ghi nhớ:** AutoConfiguration.replacements là metadata tương thích dành cho Spring Boot, không phải alias class Java. Từ Spring Boot 3.4.0-M3, file này ánh xạ FQCN cũ sang FQCN mới để giữ các tham chiếu ordering và exclusions. Khi di chuyển class, cập nhật AutoConfiguration.imports để chỉ công bố class mới, thêm mapping cũ → mới, kiểm thử exclusion bằng tên cũ và xác nhận resource có trong JAR. Nếu còn hỗ trợ Boot 3.3.x, phải giữ phương án tương thích riêng vì dòng này không xử lý replacements.
