# Mốc chuyển tiếp Spring Boot 2.7 và thay đổi cơ chế đăng ký trong Boot 3

> **Mục tiêu:** Hiểu vì sao Spring Boot 2.7 đưa vào resource `AutoConfiguration.imports`, vì sao Boot 3 bỏ cơ chế đăng ký auto-configuration qua khóa `EnableAutoConfiguration` trong `spring.factories`, và cách duy trì một thư viện chạy được trên nhiều thế hệ Boot. Bài học phân biệt trường hợp chỉ hỗ trợ Boot 2.7+/3.x với trường hợp còn phải hỗ trợ Boot 2.6 trở xuống.

Bài học thuộc nhóm **Tương thích phiên bản**, lấy Spring Boot 2.7 làm mốc chuyển tiếp và Spring Boot 3.0+ làm mốc loại bỏ đường đăng ký cũ. Trọng tâm là registration, annotation `@AutoConfiguration`, file imports, các extension key khác trong `spring.factories`, custom test slice, đóng gói JAR và chiến lược kiểm thử theo ma trận phiên bản.

## 1. Bối cảnh thay đổi

Trước Spring Boot 2.7, thư viện thường đăng ký auto-configuration trong resource:

~~~text
META-INF/spring.factories
~~~

File dùng định dạng properties. Khóa `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trỏ tới danh sách các lớp cấu hình tự động, thường là danh sách FQCN phân cách bằng dấu phẩy:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.audit.autoconfigure.AuditAutoConfiguration,\
com.acme.audit.autoconfigure.AuditWebAutoConfiguration
~~~

Cách này hoạt động trong các dòng Boot 2.x trước 2.7. Tuy nhiên, `spring.factories` được dùng cho nhiều extension point của Spring Boot, không riêng auto-configuration. Danh sách class trong một file properties lớn khiến việc tìm, hợp nhất và xử lý metadata của từng nhóm extension kém tường minh hơn.

Spring Boot 2.7 giới thiệu resource chuyên dụng:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng chứa một fully qualified class name (FQCN). Resource này tách danh sách auto-configuration khỏi các extension khác và là cơ chế đăng ký được khuyến nghị từ Boot 2.7.

Boot 2.7 vẫn đọc khóa cũ trong `spring.factories` để tương thích ngược. Boot 3.0 loại bỏ riêng đường đăng ký auto-configuration qua khóa đó. Đây là thay đổi có thời điểm chuyển tiếp rõ ràng, không phải việc xóa toàn bộ `spring.factories`.

## 2. Dòng thời gian và ma trận tương thích

| Dòng Spring Boot | Đọc khóa EnableAutoConfiguration trong spring.factories | Đọc AutoConfiguration.imports | Khuyến nghị |
| --- | --- | --- | --- |
| 2.0–2.6 | Có | Không | Dùng spring.factories |
| 2.7.x | Có, nhưng đã deprecated | Có | Chuyển sang imports; có thể khai báo cả hai |
| 3.0+ | Không | Có | Dùng imports; bỏ khóa auto-configuration cũ |

Hai trường hợp thư viện cần phân biệt:

- **Thư viện chỉ hỗ trợ Boot 2.7 trở lên:** chỉ cần `AutoConfiguration.imports`. Boot 2.7 và Boot 3 đều đọc được file này.
- **Thư viện hỗ trợ cả Boot 2.6 trở xuống lẫn Boot 3:** duy trì hai đường đăng ký trong cùng artifact: `spring.factories` cho Boot cũ và `AutoConfiguration.imports` cho Boot mới. Boot 2.7 đọc được cả hai và tự loại trùng nếu cùng một class được liệt kê trong cả hai.

Vì vậy, câu “thư viện hỗ trợ Boot 2.x và Boot 3 thì phải có cả hai file” chỉ đúng khi phạm vi Boot 2.x bao gồm các phiên bản trước 2.7. Nếu phiên bản thấp nhất là 2.7, imports file đã đủ cho cả hai dòng.

### 2.1. Những gì Boot 3 loại bỏ

Boot 3 loại bỏ hỗ trợ đăng ký auto-configuration trong `spring.factories` bằng khóa:

~~~text
org.springframework.boot.autoconfigure.EnableAutoConfiguration
~~~

Các khóa khác của `spring.factories` không bị ảnh hưởng bởi thay đổi này. Một thư viện có thể vẫn cần file đó cho extension point khác mà Boot tiếp tục hỗ trợ. Do đó:

- Không xóa toàn bộ `spring.factories` chỉ vì đã chuyển auto-configuration.
- Chỉ bỏ entry `EnableAutoConfiguration` khi thư viện không còn cần hỗ trợ các phiên bản Boot trước 2.7.
- Giữ các entry khác theo đúng contract của extension point tương ứng.
- Không nhầm việc Boot 3 bỏ khóa auto-configuration với việc `SpringFactoriesLoader` bị loại bỏ hoàn toàn.

## 3. Cấu trúc file mới trong Boot 2.7+

Tạo resource đúng tên và đường dẫn:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

Nội dung:

~~~text
com.acme.audit.autoconfigure.AuditAutoConfiguration
com.acme.audit.autoconfigure.AuditWebAutoConfiguration
~~~

Quy tắc định dạng:

1. Mỗi dòng là một FQCN của auto-configuration.
2. Không ghi tên class ngắn hoặc tên bean.
3. Không phân cách các class bằng dấu phẩy.
4. Có thể thêm comment bắt đầu bằng dấu `#`.
5. Đường dẫn và tên file phải đúng từng ký tự, bao gồm chữ hoa/chữ thường.
6. File phải nằm trong main resources và được đóng gói trong JAR mà ứng dụng tiêu thụ sử dụng.

Ví dụ có comment:

~~~text
# Core audit integration
com.acme.audit.autoconfigure.AuditAutoConfiguration

# Optional servlet integration
com.acme.audit.autoconfigure.AuditWebAutoConfiguration
~~~

Đừng đặt file dưới `META-INF/` trực tiếp hoặc trong package Java. Đường dẫn bắt buộc có thư mục `META-INF/spring/`.

## 4. Annotation @AutoConfiguration được giới thiệu trong Boot 2.7

Spring Boot 2.7 giới thiệu `@AutoConfiguration` để đánh dấu các class top-level cung cấp auto-configuration:

~~~java
package com.acme.audit.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public AuditService auditService() {
        return new AuditService();
    }
}
~~~

`@AutoConfiguration` là annotation chuyên dụng cho auto-configuration. Nó là một dạng `@Configuration` với `proxyBeanMethods = false`, và được dùng cho các class top-level được liệt kê trong imports file.

Các cấu hình lồng nhau hoặc được import bởi auto-configuration tiếp tục dùng `@Configuration` như bình thường:

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class ServletConfiguration {
        // Các @Bean chỉ dành cho Servlet.
    }
}
~~~

Không cần đổi mọi class `@Configuration` trong thư viện thành `@AutoConfiguration`. Annotation mới dành cho class đóng vai trò auto-configuration entry point. Nested configuration và các cấu hình helper vẫn dùng `@Configuration`.

### 4.1. Thứ tự auto-configuration

`@AutoConfiguration` hỗ trợ khai báo thứ tự qua các thuộc tính `before`, `beforeName`, `after` và `afterName`. Ví dụ:

~~~java
@AutoConfiguration(after = CoreAutoConfiguration.class)
public class AuditAutoConfiguration {
}
~~~

Nếu không muốn phụ thuộc compile-time vào class của module khác, có thể tham chiếu tên class:

~~~java
@AutoConfiguration(
        afterName = "com.acme.core.autoconfigure.CoreAutoConfiguration")
public class AuditAutoConfiguration {
}
~~~

Các annotation cũ `@AutoConfigureBefore` và `@AutoConfigureAfter` vẫn là lựa chọn phù hợp, đặc biệt khi thư viện phải dùng chung source với các dòng Boot cũ hơn. Thứ tự auto-configuration chỉ ảnh hưởng thứ tự đăng ký bean definition; thứ tự tạo instance bean vẫn do dependency graph và `@DependsOn` quyết định.

### 4.2. Khi nào chưa thể dùng @AutoConfiguration?

`@AutoConfiguration` chỉ có từ Boot 2.7. Nếu một thư viện vẫn phải chạy với Boot 2.6 hoặc cũ hơn, không nên đưa annotation chỉ có trong Boot 2.7 vào bytecode chung mà runtime cũ phải nạp.

Có hai hướng:

- Giữ class dùng `@Configuration(proxyBeanMethods = false)` và các annotation ordering đã tồn tại ở dòng Boot cũ; đăng ký class qua file phù hợp cho từng phiên bản.
- Tách artifact hoặc build variant theo baseline nếu thư viện muốn dùng `@AutoConfiguration` và API mới trong bản dành riêng cho Boot 2.7+/3.x.

Với thư viện có baseline tối thiểu là Boot 2.7, dùng `@AutoConfiguration` là cách rõ ràng và phù hợp với convention hiện hành.

## 5. Mẫu đăng ký theo chiến lược hỗ trợ

Giả sử thư viện có class:

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditService;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public AuditService auditService() {
        return new AuditService();
    }
}
~~~

Đây là biến thể dùng `@Configuration` để giữ khả năng nạp trên baseline cũ hơn. Với baseline Boot 2.7+, có thể thay annotation trên class bằng `@AutoConfiguration`.

### 5.1. Chỉ hỗ trợ Boot 2.6 trở xuống

Chỉ đăng ký trong `spring.factories`:

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

Không có imports resource ở chiến lược này vì các dòng Boot cũ không đọc resource mới.

### 5.2. Hỗ trợ Boot 2.7 và Boot 3

Chỉ cần imports resource:

~~~text
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

Boot 2.7 đã hiểu resource này; Boot 3 tiếp tục dùng nó. Không cần giữ entry cũ chỉ để hỗ trợ Boot 2.7.

### 5.3. Hỗ trợ cả Boot 2.6 trở xuống và Boot 3

Duy trì cả hai file:

**`META-INF/spring.factories`**

~~~properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

**`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

Hành vi theo phiên bản:

- Boot 2.6: chỉ đọc entry trong `spring.factories`.
- Boot 2.7: đọc cả hai; nếu class xuất hiện hai lần, Boot loại trùng.
- Boot 3: đọc imports; entry `EnableAutoConfiguration` trong `spring.factories` không còn được dùng.

Không tạo hai class cấu hình khác nhau chỉ để phục vụ hai file đăng ký nếu cùng một implementation có thể chạy an toàn trên cả hai dòng. Nếu API/annotation thực sự khác nhau giữa các baseline, dùng build variant hoặc artifact riêng thay vì che giấu khác biệt bằng đăng ký trùng.

## 6. Vì sao Boot 2.7 giữ cả hai đường đăng ký?

Boot 2.7 là phiên bản chuyển tiếp. Nó hỗ trợ cả cách cũ lẫn cách mới để thư viện có thể phát hành một artifact dùng trong giai đoạn nâng cấp.

Ví dụ một thư viện có hai file cùng liệt kê `AuditAutoConfiguration`. Khi chạy trên Boot 2.7, hai nguồn được tổng hợp và các entry trùng được de-duplicate. Điều này giúp một artifact duy trì tương thích với Boot trước 2.7 và Boot 3 mà không khiến auto-configuration bị áp dụng hai lần chỉ vì đăng ký hai nơi.

Việc de-duplicate này là hành vi được Boot 2.7 công bố cho các entry trùng giữa hai vị trí. Không nên dựa vào nó như một cách xử lý mọi loại duplicate bean do hai class khác nhau hoặc hai configuration path khác nhau tạo ra.

## 7. Không xóa nhầm các extension khác trong spring.factories

`spring.factories` vẫn có thể chứa các extension point khác. Ví dụ cấu trúc minh họa:

~~~properties
# Legacy auto-configuration registration for Boot <= 2.6
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.audit.autoconfigure.AuditAutoConfiguration

# Other Spring Boot extension points may still use spring.factories
com.acme.audit.SomeOtherExtension=\
com.acme.audit.internal.SomeOtherExtensionImpl
~~~

Khi thư viện bỏ hỗ trợ Boot trước 2.7, có thể xóa riêng phần `EnableAutoConfiguration`. Giữ các key khác nếu chúng vẫn thuộc cơ chế được hỗ trợ ở dòng Boot đang nhắm tới.

Đừng thay thế mọi nội dung `spring.factories` bằng imports file. Imports file chỉ dành cho danh sách auto-configuration; nó không phải file đăng ký chung cho mọi Spring Boot extension.

## 8. Custom test slice cũng có thay đổi registration

Boot 2.7 thay đổi cách đăng ký custom test slice. Nếu thư viện định nghĩa annotation test riêng, registration cũ trong `spring.factories` cần được chuyển sang resource:

~~~text
META-INF/spring/<fully-qualified-name-of-test-slice-annotation>.imports
~~~

Ví dụ annotation:

~~~java
package com.acme.audit.test;

public @interface AcmeDataTest {
}
~~~

Resource tương ứng:

**`src/main/resources/META-INF/spring/com.acme.audit.test.AcmeDataTest.imports`**

~~~text
com.acme.audit.autoconfigure.AuditTestAutoConfiguration
com.acme.audit.test.AcmeDataTestImportSelector
~~~

Danh sách trên chỉ là ví dụ cấu trúc; class được liệt kê phải đúng với contract test slice mà thư viện triển khai. Tên file được tạo từ FQCN của annotation slice, không dùng tên `AutoConfiguration.imports` chung.

Khi nâng cấp test slice, kiểm tra riêng:

- Entry cũ trong `spring.factories`.
- Tên annotation đầy đủ dùng trong tên file `.imports`.
- Danh sách cấu hình test được import.
- Test slice thực sự khởi động được trong phiên bản Boot mục tiêu.

Đừng nhầm file test-slice imports với file auto-configuration imports; chúng có cùng kiểu nội dung theo dòng nhưng tên resource khác nhau.

## 9. ManagementContextConfiguration có resource riêng

Boot 2.7 cũng chuyển registration của management context configuration sang resource riêng:

~~~text
META-INF/spring/org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports
~~~

Nếu thư viện cung cấp management context configuration cho Actuator, hãy kiểm tra resource này riêng. Đừng ghi các class đó vào `AutoConfiguration.imports` chỉ vì chúng cũng liên quan đến cấu hình tự động.

Với thư viện chỉ cung cấp auto-configuration thông thường, chỉ cần tập trung vào `org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

## 10. Đóng gói JAR và vấn đề trùng resource

Một lỗi thường gặp xuất hiện khi thư viện build thành uber-JAR hoặc shaded JAR. Nhiều dependency có thể cùng chứa một resource tên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nếu công cụ đóng gói chỉ giữ một file cùng tên thay vì nối nội dung, danh sách auto-configuration từ một số dependency có thể biến mất. JAR vẫn build thành công nhưng một phần cấu hình không được phát hiện.

### 10.1. Maven Shade Plugin

Khi dùng `maven-shade-plugin` và resource imports đến từ nhiều dependency, cấu hình `AppendingTransformer` cho đúng resource:

~~~xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
~~~

Nếu artifact còn chứa management context imports, cấu hình transformer tương ứng cho resource đó:

~~~xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports</resource>
</transformer>
~~~

### 10.2. Gradle Shadow Plugin

Với Gradle Shadow Plugin, nối nội dung các file imports:

~~~groovy
tasks.withType(ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
    append("META-INF/spring/org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports")
}
~~~

Cấu hình này áp dụng khi dùng Shadow để hợp nhất dependency vào một JAR. Nếu phát hành JAR thư viện thông thường mà không hợp nhất dependency, không cần cấu hình append chỉ để tạo imports file đơn lẻ.

### 10.3. Kiểm tra artifact sau khi đóng gói

Liệt kê nội dung JAR:

~~~bash
jar tf target/acme-audit-autoconfigure-1.0.0.jar
~~~

Kiểm tra resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring.factories
~~~

Đọc imports file trong JAR bằng công cụ unzip phù hợp:

~~~bash
unzip -p target/acme-audit-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Với JAR được tạo bằng Shade/Shadow, kiểm tra nội dung thực tế của resource sau khi merge. Chỉ thấy tên file tồn tại chưa chứng minh tất cả dòng FQCN đã được giữ lại.

## 11. Kiểm thử discovery theo ma trận phiên bản

Test trực tiếp bằng `AutoConfigurations.of(AuditAutoConfiguration.class)` chỉ kiểm tra behavior của class được nạp trực tiếp. Nó không chứng minh file registration đã được đóng gói hoặc discovery hoạt động.

Để kiểm tra registration, dùng một context có `@EnableAutoConfiguration` và để Boot tự tìm candidate trên classpath:

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AuditRegistrationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(DiscoveryApplication.class);

    @Test
    void auditAutoConfigurationIsDiscoveredFromJarResources() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AuditService.class);
        });
    }

    @SpringBootConfiguration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class DiscoveryApplication {
    }
}
~~~

Test trên phải chạy trong module/artifact test có resource registration thật trên classpath. Nó không được nạp auto-configuration bằng `AutoConfigurations.of(...)`, vì mục tiêu là xác nhận discovery.

### 11.1. Ma trận cần chạy

| Runtime test | Resource cần có trong artifact | Điều cần xác nhận |
| --- | --- | --- |
| Boot 2.6.x | spring.factories | Discovery qua khóa cũ |
| Boot 2.7.x | Imports, và spring.factories nếu còn hỗ trợ Boot cũ | Discovery qua imports; nếu có cả hai thì không gây đăng ký trùng |
| Boot 3.x | AutoConfiguration.imports | Discovery không phụ thuộc khóa cũ |
| Boot 2.7+/3.x custom test slice | Slice-specific .imports | Test slice được tìm thấy và cấu hình đúng |
| Shaded/uber-JAR | Imports resource sau khi merge | Không mất entry từ dependency |

Nên dùng build profile, module test hoặc CI matrix để chạy cùng bộ discovery test trên từng baseline. Không chỉ compile trên một version rồi kết luận artifact tương thích với mọi version.

## 12. Các bước chuyển đổi từ Boot 2.6 lên Boot 2.7

Với thư viện đang dùng `spring.factories`:

1. Xác định class nào đang nằm dưới khóa `org.springframework.boot.autoconfigure.EnableAutoConfiguration`.
2. Tạo `AutoConfiguration.imports` trong `src/main/resources/META-INF/spring/`.
3. Chuyển mỗi FQCN thành một dòng riêng, không dùng dấu phẩy.
4. Dùng `@AutoConfiguration` cho top-level auto-configuration nếu baseline tối thiểu là 2.7; nếu vẫn hỗ trợ Boot cũ hơn, giữ lựa chọn annotation tương thích.
5. Giữ entry cũ trong `spring.factories` nếu artifact còn phải chạy trên Boot 2.6 hoặc cũ hơn.
6. Chạy test trên Boot 2.7 để xác nhận imports hoạt động và entry trùng được xử lý.
7. Kiểm tra Shade/Shadow nếu thư viện đóng gói dependency thành một JAR.

Boot 2.7 vẫn đọc khóa cũ, nhưng đã đánh dấu việc nạp auto-configuration từ `spring.factories` là deprecated. Không nên coi khả năng tương thích này là lý do để trì hoãn migration vô thời hạn.

## 13. Các bước chuyển đổi từ Boot 2.7 lên Boot 3

Khi nâng thư viện hoặc ứng dụng lên Boot 3:

1. Đảm bảo auto-configuration được đăng ký trong `AutoConfiguration.imports`.
2. Nếu không còn hỗ trợ Boot trước 2.7, bỏ riêng entry `EnableAutoConfiguration` khỏi `spring.factories`.
3. Giữ những key `spring.factories` khác mà extension point còn cần.
4. Kiểm tra class auto-configuration dùng API phù hợp với baseline Boot 3.
5. Kiểm tra các class ordering, exclusions và package name được tham chiếu từ cấu hình khác.
6. Xác nhận resource imports có trong JAR cuối cùng.
7. Chạy discovery test với runtime Boot 3 thực tế.

### 13.1. Đừng nhầm thay đổi registration với toàn bộ migration Boot 3

Thay đổi `spring.factories` chỉ là một phần của nâng cấp. Spring Boot 3.0 còn yêu cầu Java 17 trở lên và Spring Framework 6.0. Các API Jakarta EE chuyển từ namespace `javax.*` sang `jakarta.*`; dependency và import liên quan cần được nâng cấp tương ứng.

Nên nâng ứng dụng lên bản 2.7.x mới nhất trước khi chuyển sang Boot 3, rà soát dependency không do Boot quản lý và xử lý các API deprecated đã bị loại bỏ. Việc đổi imports resource không tự làm ứng dụng tương thích Java 17, Spring Framework 6 hoặc Jakarta namespace.

## 14. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| Boot 3 không tìm thấy auto-configuration | Chỉ còn entry trong spring.factories dưới EnableAutoConfiguration | Thêm FQCN vào AutoConfiguration.imports |
| Boot 2.6 không tìm thấy class sau khi migration | Chỉ phát hành imports resource | Giữ entry cũ trong spring.factories nếu còn hỗ trợ Boot 2.6 |
| Boot 2.7 ghi nhận cấu hình deprecated | Vẫn dựa vào spring.factories cho auto-configuration | Chuyển sang imports; chỉ giữ entry cũ khi cần baseline trước 2.7 |
| Một số auto-configuration biến mất trong uber-JAR | Công cụ đóng gói ghi đè resource trùng tên | Dùng AppendingTransformer hoặc Shadow append |
| spring.factories bị mất extension khác | Xóa toàn bộ file khi chỉ cần bỏ một key | Giữ các key khác và chỉ thay đổi entry liên quan |
| Test slice không được phát hiện | Vẫn đăng ký custom slice bằng đường cũ | Tạo resource META-INF/spring/FQCN-của-annotation.imports |
| Configuration lồng nhau không hoạt động như mong đợi | Gắn @AutoConfiguration cho mọi helper class | Chỉ dùng annotation này cho top-level entry point; nested config dùng @Configuration |
| Build trên Boot 3 pass nhưng Boot 2.6 lỗi | Bytecode tham chiếu annotation/API chỉ có từ Boot 2.7 | Giữ source/API tương thích hoặc tách artifact theo baseline |
| File imports có nhưng class không load được | Sai FQCN, class bị loại khỏi JAR hoặc dependency thiếu | Kiểm tra nội dung file và classpath của artifact |
| Test pass nhưng ứng dụng tiêu thụ không nhận cấu hình | Test dùng AutoConfigurations.of(...) để nạp trực tiếp | Thêm discovery test bằng @EnableAutoConfiguration |

## 15. Checklist phát hành thư viện hỗ trợ nhiều dòng Boot

- [ ] Xác định rõ baseline thấp nhất: Boot 2.6, 2.7 hay 3.x.
- [ ] Nếu baseline từ 2.7 trở lên, đăng ký qua AutoConfiguration.imports.
- [ ] Nếu còn hỗ trợ trước 2.7, duy trì thêm entry EnableAutoConfiguration trong spring.factories.
- [ ] Mỗi imports entry là một FQCN trên một dòng.
- [ ] @AutoConfiguration chỉ dùng khi baseline runtime có Boot 2.7 trở lên.
- [ ] Nested/imported configuration vẫn dùng @Configuration.
- [ ] Giữ các extension key khác trong spring.factories.
- [ ] Chuyển custom test slice sang resource .imports riêng.
- [ ] Nếu có management context configuration, kiểm tra resource riêng.
- [ ] Cấu hình merge resource cho Maven Shade hoặc Gradle Shadow khi tạo uber-JAR.
- [ ] Kiểm tra nội dung imports thực tế trong artifact phát hành.
- [ ] Chạy discovery test trên từng dòng Boot mà thư viện cam kết hỗ trợ.
- [ ] Với Boot 3, rà soát thêm Java 17, Spring Framework 6 và Jakarta namespace.

## 16. Câu hỏi tự kiểm tra

1. Phiên bản nào giới thiệu `AutoConfiguration.imports`?  
   **Đáp án:** Spring Boot 2.7.

2. Boot 2.7 còn đọc khóa `EnableAutoConfiguration` trong `spring.factories` không?  
   **Đáp án:** Có, để tương thích ngược; việc nạp theo cách cũ đã deprecated.

3. Boot 3 có còn dùng khóa `EnableAutoConfiguration` trong `spring.factories` không?  
   **Đáp án:** Không. Boot 3 dùng imports file cho auto-configuration.

4. Boot 3 có loại bỏ mọi key trong `spring.factories` không?  
   **Đáp án:** Không. Thay đổi này chỉ loại bỏ key đăng ký auto-configuration; các key khác không bị ảnh hưởng bởi thay đổi đó.

5. Một thư viện hỗ trợ Boot 2.6 và Boot 3 cần những file nào?  
   **Đáp án:** Cả `spring.factories` và `AutoConfiguration.imports`. Boot 2.7 có thể đọc cả hai và de-duplicate entry trùng.

6. Thư viện chỉ hỗ trợ Boot 2.7 và Boot 3 có cần hai file không?  
   **Đáp án:** Không. Imports file được cả hai dòng hỗ trợ.

7. `@AutoConfiguration` xuất hiện từ phiên bản nào?  
   **Đáp án:** Spring Boot 2.7. Đây là annotation chuyên dụng cho top-level auto-configuration.

8. Có nên đổi nested configuration thành `@AutoConfiguration` không?  
   **Đáp án:** Không. Nested/imported configuration tiếp tục dùng `@Configuration`.

9. Vì sao shaded JAR cần append imports resource?  
   **Đáp án:** Nhiều dependency có thể cùng cung cấp file cùng tên; append giúp giữ các entry thay vì một file ghi đè file khác.

10. Test dùng `AutoConfigurations.of(...)` có chứng minh file imports hoạt động không?  
    **Đáp án:** Không. Cần test discovery qua `@EnableAutoConfiguration` trên classpath artifact.

## Tài liệu chính thức

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes): file imports mới, tương thích ngược, de-duplicate, `@AutoConfiguration`, custom test slices và Shade/Shadow.
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): loại bỏ khóa `EnableAutoConfiguration` trong `spring.factories` và cách hỗ trợ cả Boot 2.x/3.x.
- [Spring Boot 2.7 API — AutoConfiguration](https://docs.spring.io/spring-boot/docs/2.7.1/api/org/springframework/boot/autoconfigure/AutoConfiguration.html): annotation mới từ 2.7 và các thuộc tính ordering.
- [Spring Boot 3.3 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): semantics của annotation và ordering attributes trong dòng 3.3.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): discovery qua imports, cấu trúc package và testing.
- [Spring Boot 3.0 Migration Guide — System Requirements and Jakarta EE](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java 17, Spring Framework 6 và chuyển đổi namespace Jakarta.

**Ghi nhớ:** Boot 2.7 là cầu nối: nó hiểu cả `spring.factories` và `AutoConfiguration.imports`, đồng thời loại trùng entry. Boot 3 bỏ riêng đường đăng ký auto-configuration cũ. Hãy chọn số file theo baseline thấp nhất của thư viện, giữ các extension key khác, merge resource đúng cách và kiểm thử discovery trên từng dòng Boot được hỗ trợ.
