# Phân biệt cơ chế đăng ký trong spring.factories và AutoConfiguration.imports

## 1. Vì sao cơ chế đăng ký thay đổi?

Spring Boot cần biết những auto-configuration nào có thể áp dụng khi ứng dụng khởi động. Trước Spring Boot 2.7, thư viện thường công bố các class này qua key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `META-INF/spring.factories`. Từ Spring Boot 2.7, một file riêng `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` được đưa vào để liệt kê auto-configuration.

Đây là thay đổi về **cách phát hiện auto-configuration**, không phải việc loại bỏ hoàn toàn `spring.factories`. Spring Boot 3 bỏ riêng key `EnableAutoConfiguration` khỏi cơ chế `spring.factories`, nhưng các extension point khác vẫn tiếp tục dùng file này. Spring Cloud cũng dùng `spring.factories` cho một số cấu hình bootstrap khi ứng dụng bật bootstrap context kiểu cũ.

Nếu nâng cấp thư viện mà xóa toàn bộ `spring.factories`, những extension point còn phụ thuộc vào nó có thể ngừng hoạt động. Ngược lại, nếu chỉ giữ key auto-configuration cũ, thư viện sẽ không được phát hiện trên Spring Boot 3 trở lên.

Bài học thuộc chương **Nâng cấp** của module **SPRING_CLOUD_CORE**. Module tập trung vào Spring Cloud Commons, Spring Cloud Context, cấu hình ngoài, tương thích Spring Boot, refresh scope, discovery, service registry, giao tiếp dịch vụ và cách kiểm thử/vận hành các abstraction chung.

Sau bài này, người học có thể:

- Giải thích vai trò của `META-INF/spring.factories` và `AutoConfiguration.imports`.
- Phân biệt factory/SPI registration với auto-configuration candidate registration.
- Mô tả mốc chuyển đổi từ Spring Boot 2.6 sang 2.7 và 3.x.
- Thiết kế dual registration khi thư viện cần hỗ trợ cả Boot 2.x và 3.x.
- Nhận diện các Spring Cloud bootstrap và Spring Boot extension point vẫn dùng `spring.factories`.
- Hiểu tác động của `@AutoConfiguration`, conditions, ordering và exclusions.
- Kiểm thử auto-configuration và kiểm tra resource trong JAR đã đóng gói.
- Phát hiện lỗi do shading, resource merging, duplicate registration hoặc class không tương thích.

## 2. Hai cơ chế đăng ký giải quyết hai nhu cầu khác nhau

### 2.1. META-INF/spring.factories

`spring.factories` là file properties trong JAR:

```text
META-INF/spring.factories
```

Mỗi key là tên đầy đủ của một factory interface hoặc extension point. Value là danh sách tên class triển khai, phân tách bằng dấu phẩy. Spring dùng `SpringFactoriesLoader` để đọc các resource này trên classpath và tải implementation tương ứng.

Ví dụ rút gọn:

```properties
com.acme.spi.PaymentProvider=\
com.acme.payment.CardPaymentProvider,\
com.acme.payment.BankTransferProvider
```

Ứng dụng hoặc framework có thể yêu cầu tất cả implementation của key `com.acme.spi.PaymentProvider`. File có thể chứa nhiều key cho nhiều extension point khác nhau:

```properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.acme.cloud.AcmeBootstrapConfiguration

org.springframework.boot.autoconfigure.AutoConfigurationImportFilter=\
com.acme.autoconfigure.AcmeImportFilter
```

Các key trong ví dụ có ý nghĩa riêng. Key bootstrap được Spring Cloud dùng khi tạo bootstrap context; key filter là SPI của Spring Boot dùng để lọc candidate auto-configuration. Chúng không phải danh sách auto-configuration mặc định của ứng dụng.

Đặc điểm của `spring.factories`:

- Một file có thể đăng ký nhiều extension point.
- Mỗi key ánh xạ đến một hoặc nhiều implementation.
- Danh sách value là dạng comma-separated, không phải một class trên mỗi dòng.
- Framework phải biết key nào cần đọc và quy tắc khởi tạo implementation.
- Nhiều JAR có thể cùng cung cấp resource `META-INF/spring.factories`; khi chạy trên classpath, loader có thể đọc các resource tương ứng từ nhiều JAR.

### 2.2. AutoConfiguration.imports

`AutoConfiguration.imports` là danh sách riêng dành cho auto-configuration của Spring Boot. Đường dẫn đầy đủ:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng là tên đầy đủ của một class auto-configuration:

```text
com.acme.autoconfigure.AcmeAutoConfiguration
com.acme.autoconfigure.AcmeWebAutoConfiguration
# Có thể thêm comment bắt đầu bằng dấu thăng
com.acme.autoconfigure.AcmeMetricsAutoConfiguration
```

Spring Boot tìm file này trong các JAR đã publish, đọc các class được liệt kê và xử lý chúng như auto-configuration candidates. Với class lồng nhau, tên class dùng dấu `$` để phân tách class ngoài và class trong.

Đặc điểm của imports file:

- Chỉ liệt kê auto-configuration class, không phải danh sách mọi loại SPI.
- Mỗi dòng là một fully qualified class name.
- Có thể có comment bắt đầu bằng `#`.
- Không có key-value hoặc dấu phẩy phân tách class.
- Auto-configuration phải được công bố qua file này; không dựa vào component scan để phát hiện.

### 2.3. So sánh trực tiếp

| Tiêu chí | `spring.factories` | `AutoConfiguration.imports` |
| --- | --- | --- |
| Định dạng | Java properties | Danh sách dòng |
| Cấu trúc | Key → danh sách implementation | Một class auto-configuration trên mỗi dòng |
| Phạm vi | Nhiều factory/SPI extension point | Auto-configuration candidates của Boot |
| Cách tải | `SpringFactoriesLoader` theo key | Boot đọc imports trong quá trình chọn auto-configuration |
| Comment | Theo cú pháp properties | Dòng bắt đầu bằng `#` |
| Dùng cho auto-configuration từ Boot 3 | Không dùng key `EnableAutoConfiguration` cũ | Cơ chế chuẩn |
| Dùng cho Spring Cloud Bootstrap | Có, với key `BootstrapConfiguration` | Không thay thế key bootstrap |

Hai file có thể cùng tồn tại trong một JAR vì chúng phục vụ những mục đích khác nhau. Việc một class xuất hiện trong `spring.factories` không có nghĩa Spring Boot tự coi nó là auto-configuration; điều đó phụ thuộc key mà framework đang đọc.

## 3. Mốc thay đổi theo phiên bản Spring Boot

### 3.1. Spring Boot 2.6 và các phiên bản cũ hơn

Ở các phiên bản trước 2.7, auto-configuration được đăng ký bằng key:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.autoconfigure.AcmeAutoConfiguration,\
com.acme.autoconfigure.AcmeWebAutoConfiguration
```

Spring Boot đọc danh sách này để tìm candidate. Nếu thư viện chỉ hỗ trợ Boot 2.6 hoặc cũ hơn, đây là cơ chế cần có.

### 3.2. Spring Boot 2.7

Spring Boot 2.7 giới thiệu:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Release notes khuyến nghị chuyển auto-configuration sang imports file. Tuy nhiên, Boot 2.7 vẫn đọc key cũ trong `spring.factories` để tương thích ngược. Nếu cùng class được liệt kê trong cả hai file, Boot 2.7 loại bỏ bản trùng.

Điều này tạo ra một cửa sổ chuyển tiếp hữu ích: một thư viện có thể cung cấp cả file cũ và file mới để hỗ trợ ứng dụng chạy trên Boot trước 2.7 và Boot 2.7.

### 3.3. Spring Boot 3.x

Spring Boot 3 loại bỏ hỗ trợ đăng ký auto-configuration qua key:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

trong `spring.factories`. Thư viện cần imports file để auto-configuration được phát hiện trên Boot 3.

Điểm quan trọng trong migration guide: các key khác của `spring.factories` không bị ảnh hưởng. Ví dụ `EnvironmentPostProcessor`, `AutoConfigurationImportFilter`, `AutoConfigurationImportListener` hoặc Spring Cloud `BootstrapConfiguration` vẫn có thể cần resource này theo API tương ứng.

### 3.4. Spring Boot 4.x

Spring Boot 4 tiếp tục dùng `AutoConfiguration.imports` làm cơ chế phát hiện auto-configuration. Tài liệu tạo auto-configuration hiện hành mô tả chính xác resource này và cách khai báo một class trên mỗi dòng.

Các SPI như `EnvironmentPostProcessor` và `AutoConfigurationImportFilter` vẫn có API yêu cầu đăng ký qua `META-INF/spring.factories`. Vì vậy, khi nâng thư viện lên Boot 4, hãy phân loại từng key thay vì xóa file theo một quy tắc tổng quát.

### 3.5. Ma trận tương thích

| Phiên bản Spring Boot | Đọc auto-config từ `spring.factories` key cũ | Đọc `AutoConfiguration.imports` | Hướng đóng gói |
| --- | --- | --- | --- |
| 2.6 trở xuống | Có | Chưa hỗ trợ cơ chế mới | Cần key cũ |
| 2.7 | Có, để tương thích ngược | Có | Có thể liệt kê ở cả hai; Boot 2.7 deduplicate |
| 3.x | Không | Có | Dùng imports file |
| 4.x | Không | Có | Dùng imports file; giữ spring.factories cho SPI còn sử dụng |

Ma trận trên nói về **đăng ký auto-configuration**. Nó không nói rằng Boot 3/4 ngừng đọc mọi `spring.factories` resource.

## 4. Dual registration khi thư viện hỗ trợ nhiều dòng Boot

### 4.1. Khi nào cần giữ cả hai file?

Nếu một thư viện cần hỗ trợ:

- Ứng dụng còn chạy Spring Boot 2.6 hoặc thấp hơn.
- Ứng dụng chạy Spring Boot 2.7.
- Ứng dụng chạy Spring Boot 3.x hoặc 4.x.

thì một chiến lược phổ biến là đăng ký cùng auto-configuration class trong cả hai vị trí:

```properties
# META-INF/spring.factories
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.autoconfigure.AcmeAutoConfiguration
```

```text
# META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
com.acme.autoconfigure.AcmeAutoConfiguration
```

Kết quả theo phiên bản:

- Boot 2.6 đọc key cũ và bỏ qua imports file mà nó chưa hỗ trợ.
- Boot 2.7 đọc cả hai và khử trùng lặp cùng class.
- Boot 3/4 dùng imports file; key auto-configuration cũ trong spring.factories không còn được xử lý.

Đây là dual registration có chủ đích. Không cần tạo hai class auto-configuration khác nhau chỉ để đăng ký ở hai vị trí.

### 4.2. Chú ý annotation @AutoConfiguration

`@AutoConfiguration` được giới thiệu trong Spring Boot 2.7. Nó là annotation chuyên biệt cho class auto-configuration và được meta-annotate bằng `@Configuration`. Nó cũng cung cấp thuộc tính ordering như `before`, `after`, `beforeNames` và `afterNames`.

Nếu artifact phải chạy trên Boot 2.6, cần chú ý binary compatibility: Boot 2.6 không có class annotation `@AutoConfiguration`. Một class đã được biên dịch với annotation này có thể không tương thích khi nạp trên runtime 2.6, ngay cả khi file spring.factories cũ đã được giữ lại.

Với một binary duy nhất cần chạy trên Boot 2.6 đến 4.x, lựa chọn thận trọng là:

- Biên dịch với baseline API thấp nhất được hỗ trợ.
- Dùng `@Configuration(proxyBeanMethods = false)` cho class đăng ký chung.
- Đăng ký class đó trong cả hai resource.
- Dùng các API condition/ordering có mặt ở baseline thấp nhất.
- Kiểm thử artifact trên từng dòng Boot được công bố hỗ trợ.

Nếu chỉ hỗ trợ Boot 2.7 trở lên, dùng `@AutoConfiguration` cho top-level auto-configuration theo hướng dẫn hiện hành. Nếu cần tận dụng API mới nhưng vẫn hỗ trợ Boot 2.6, cân nhắc phát hành artifact/variant riêng thay vì để một binary tham chiếu đến class không có trên runtime cũ.

### 4.3. Ví dụ class tương thích nhiều phiên bản

Ví dụ class dùng `@Configuration` để tránh tham chiếu annotation chỉ có từ Boot 2.7:

```java
package com.acme.autoconfigure;

import com.acme.client.AcmeClient;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(AcmeClient.class)
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient() {
        return new AcmeClient();
    }
}
```

Ví dụ chỉ minh họa class được đăng ký ở hai resource. Trong thư viện thực tế, hãy thêm property binding, condition phù hợp và cô lập kiểu của dependency tùy chọn vào nested configuration để tránh lỗi class loading khi dependency không có trên classpath.

### 4.4. Không để hai danh sách lệch nhau

Khi duy trì dual registration, hai file phải công bố cùng tập auto-configuration tương ứng cho các phiên bản hỗ trợ.

Ví dụ lỗi:

- Class A chỉ có trong `spring.factories`: Boot 2.6 tìm thấy nhưng Boot 3/4 không thấy.
- Class B chỉ có trong imports file: Boot 3/4 tìm thấy nhưng Boot 2.6 không thấy.
- Class đã đổi package nhưng resource vẫn giữ tên cũ: Boot cố nạp class không tồn tại.
- Class bị xóa khỏi source nhưng vẫn còn trong resource: ứng dụng có thể lỗi khi import.

Nên duy trì danh sách auto-configuration như một phần của kiểm thử artifact, không cập nhật thủ công ở nhiều nơi mà không có kiểm tra đối chiếu.

## 5. Những extension point vẫn dùng spring.factories

### 5.1. SpringFactoriesLoader là cơ chế rộng hơn auto-configuration

`spring.factories` không đồng nghĩa với “danh sách auto-configuration”. Nó là một registry cho nhiều factory interface. Boot 3 chỉ loại bỏ việc dùng key `EnableAutoConfiguration` để tìm auto-configuration; các key khác vẫn có thể được framework đọc.

Một số ví dụ:

| Extension point | Key trong spring.factories | Vai trò |
| --- | --- | --- |
| Spring Cloud bootstrap | `org.springframework.cloud.bootstrap.BootstrapConfiguration` | Công bố cấu hình cho bootstrap context |
| Environment post-processing | Tên đầy đủ của `EnvironmentPostProcessor` theo dòng Boot đang dùng | Chỉnh Environment trước khi context được refresh |
| Auto-configuration import filter | `org.springframework.boot.autoconfigure.AutoConfigurationImportFilter` | Lọc candidate trước khi xử lý sâu |
| Auto-configuration import listener | `org.springframework.boot.autoconfigure.AutoConfigurationImportListener` | Nhận thông tin về danh sách candidate được import |

Tên interface và package có thể thay đổi giữa major version. Khi nâng cấp, lấy FQCN từ API của dòng Boot mục tiêu và kiểm tra tài liệu extension point tương ứng.

### 5.2. Ví dụ Spring Cloud BootstrapConfiguration

Khi ứng dụng sử dụng legacy bootstrap context, Spring Cloud cho phép thêm cấu hình qua key:

```properties
org.springframework.cloud.bootstrap.BootstrapConfiguration=\
com.acme.cloud.AcmeBootstrapConfiguration
```

Class được liệt kê là cấu hình Spring:

```java
package com.acme.cloud;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AcmeBootstrapConfiguration {

    @Bean
    AcmePropertySourceLocator acmePropertySourceLocator() {
        return new AcmePropertySourceLocator();
    }
}
```

Bootstrap configuration được tải vào bootstrap context để chuẩn bị property source và initializer trước khi main application context khởi động. Nó không phải auto-configuration candidate của Boot, do đó không được chuyển sang `AutoConfiguration.imports`.

Khi dùng bootstrap configuration, đặt class trong package riêng để component scan của ứng dụng không vô tình nạp nó vào main context. Tài liệu Spring Cloud cũng khuyến nghị tránh package bootstrap bị bao phủ bởi `@SpringBootApplication` hoặc `@ComponentScan`.

### 5.3. Bootstrap context không phải lựa chọn mặc định cho mọi ứng dụng

Spring Cloud Config hiện hỗ trợ Config Data API, ví dụ:

```yaml
spring:
  config:
    import: "optional:configserver:"
```

Với mô hình Config Data này, ứng dụng không nhất thiết phải bật legacy bootstrap context. Chỉ giữ `BootstrapConfiguration` khi ứng dụng thực sự dùng bootstrap mechanism và có extension point phụ thuộc vào nó.

Khi migration, hãy xác định ứng dụng đang dùng:

- Config Data import như `spring.config.import=configserver:`.
- Legacy bootstrap context, thường được bật qua bootstrap starter hoặc property tương ứng.
- Cả hai trong một giai đoạn chuyển tiếp.

Không chuyển mọi `BootstrapConfiguration` sang auto-configuration chỉ vì đang di chuyển key đăng ký auto-configuration. Hai loại context có thời điểm và mục đích khác nhau.

### 5.4. AutoConfigurationImportFilter cũng không phải auto-configuration

Một thư viện có thể cần lọc danh sách auto-configuration trước khi Boot xử lý điều kiện đầy đủ. Khi đó, implementation `AutoConfigurationImportFilter` được đăng ký trong `spring.factories` bằng key SPI tương ứng.

Filter này không được liệt kê trong `AutoConfiguration.imports`, vì nó không phải bean auto-configuration thông thường. Nó tham gia vào quá trình chọn candidate trước khi các configuration class được xử lý.

## 6. Annotation, conditions và ordering sau khi chuyển imports

### 6.1. @AutoConfiguration

Spring Boot 2.7 giới thiệu `@AutoConfiguration` để đánh dấu top-level auto-configuration class:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;

@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
public class AcmeAutoConfiguration {
    // Bean definitions
}
```

Annotation này là dạng chuyên biệt của `@Configuration`. Các configuration lồng bên trong hoặc được import bởi class auto-configuration vẫn có thể dùng `@Configuration`.

Khi dùng Boot 2.7+, `@AutoConfiguration` giúp thể hiện rõ vai trò của class và hỗ trợ khai báo thứ tự trực tiếp. Nếu thư viện còn hỗ trợ Boot 2.6, cần cân nhắc binary compatibility như phần dual registration: runtime 2.6 không có annotation class này.

### 6.2. Conditions vẫn quyết định bean có được tạo hay không

Imports file chỉ giúp Boot phát hiện candidate. Nó không có nghĩa mọi class được liệt kê đều tạo bean trong mọi ứng dụng.

Các condition thường dùng:

- `@ConditionalOnClass`: dependency hoặc class cần thiết có trên classpath.
- `@ConditionalOnMissingBean`: ứng dụng chưa cung cấp bean thay thế.
- `@ConditionalOnBean`: bean phụ thuộc đã tồn tại.
- `@ConditionalOnProperty`: property bật/tắt tính năng thỏa điều kiện.
- `@ConditionalOnResource`: resource cần thiết tồn tại.
- `@ConditionalOnWebApplication`: loại application context phù hợp.

Ví dụ:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AcmeClient.class)
    static class AcmeClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AcmeClient acmeClient() {
            return new AcmeClient();
        }
    }
}
```

Nếu ứng dụng tự cung cấp bean `AcmeClient`, auto-configuration nên lùi lại. Điều kiện giúp thư viện tích hợp mà vẫn cho phép ứng dụng kiểm soát implementation.

Với dependency tùy chọn, cô lập các method signature tham chiếu đến class đó trong nested configuration có `@ConditionalOnClass`. Nếu class tùy chọn bị thiếu nhưng xuất hiện trong return type của method thuộc configuration ngoài, JVM có thể phải nạp kiểu trước khi condition được đánh giá.

### 6.3. Ordering không thay thế registration

Auto-configuration có thể khai báo thứ tự tương đối:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class AcmeDatabaseAutoConfiguration {
}
```

Hoặc dùng `@AutoConfigureBefore`, `@AutoConfigureAfter`, `@AutoConfigureOrder` tùy baseline Boot và kiểu cấu hình.

Ordering chỉ điều khiển thứ tự các bean definition/configuration được áp dụng. Nó không thay đổi cách class được tìm thấy. Một class có `@AutoConfigureAfter` nhưng không được đăng ký trong imports file vẫn không tự xuất hiện như auto-configuration candidate.

### 6.4. Exclude auto-configuration

Các cách loại trừ auto-configuration vẫn áp dụng với class được khai báo trong imports:

```java
@SpringBootApplication(exclude = AcmeAutoConfiguration.class)
public class Application {
}
```

Hoặc qua property:

```yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeAutoConfiguration
```

Nếu đổi package hoặc tên class trong một bản nâng cấp, kiểm tra các nơi tham chiếu tên cũ:

- `exclude` và `excludeName` trong annotation.
- `spring.autoconfigure.exclude`.
- `before` / `after` ordering của auto-configuration khác.
- Test và tài liệu vận hành có nhắc tên class.

Từ các phiên bản Boot hiện hành, khi đổi tên class auto-configuration đã public, có thể dùng file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements` để ánh xạ class cũ sang class mới cho ordering và exclusions:

```text
com.acme.autoconfigure.LegacyAcmeAutoConfiguration=com.acme.autoconfigure.core.AcmeAutoConfiguration
```

Imports file chỉ nên liệt kê class thay thế sau khi migration hoàn tất. Không giữ cả class cũ và mới như hai candidate độc lập nếu chúng đại diện cùng một cấu hình.

## 7. Test-slice imports là một cơ chế riêng

Spring Boot 2.7 cũng thay đổi cách mở rộng các test slice. Nếu thư viện cung cấp custom test slice hoặc annotation meta-annotated bằng `@ImportAutoConfiguration`, các auto-configuration bổ sung có thể được liệt kê trong file riêng:

```text
META-INF/spring/org.springframework.boot.test.autoconfigure.jdbc.JdbcTest.imports
```

Nội dung:

```text
com.acme.testing.AcmeJdbcTestAutoConfiguration
```

Đây không phải file `AutoConfiguration.imports` chung. Tên file gắn với fully qualified name của test slice annotation. Nó cho phép bổ sung cấu hình cho slice cụ thể mà không đưa test-only configuration vào mọi ứng dụng production.

Nếu đang nâng cấp custom test slice, hãy đọc release notes và tài liệu test của đúng dòng Boot. Không chuyển tất cả key trong `spring.factories` sang một imports file chung.

## 8. Đóng gói JAR và xử lý resource khi shading

### 8.1. Kiểm tra resource trong artifact

Source tree có thể đúng nhưng resource không được đóng gói hoặc bị plugin ghi đè. Sau khi build, kiểm tra JAR:

```bash
jar tf acme-spring-boot-autoconfigure.jar
```

Tối thiểu, nếu thư viện hỗ trợ Boot 2.6 đến 4.x, kiểm tra các file cần thiết:

```text
META-INF/spring.factories
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nếu artifact chỉ hỗ trợ Boot 3/4 và không dùng SPI nào khác qua `spring.factories`, file này có thể không cần chứa key auto-configuration cũ. Nhưng nếu có Spring Cloud bootstrap hoặc SPI khác, vẫn giữ resource với đúng key đó.

### 8.2. Nhiều JAR trên classpath và uber-JAR là hai trường hợp khác nhau

Khi chạy với nhiều JAR riêng trên classpath, framework có thể đọc resource cùng tên từ nhiều JAR.

Khi tạo uber-JAR bằng Maven Shade hoặc Gradle Shadow, plugin phải hợp nhất resource. Nếu plugin chỉ giữ file đầu tiên hoặc ghi đè file trước bằng file sau, các entry từ dependency khác có thể biến mất.

Cần phân biệt quy tắc hợp nhất:

- `AutoConfiguration.imports` là danh sách dòng, nên cần append nội dung từ tất cả JAR.
- `spring.factories` là file properties, nên cần merge theo key và nối các implementation value tương ứng; không nên nối văn bản tùy tiện hoặc để một file ghi đè file còn lại.
- Các file `META-INF/services/*` có quy tắc ServiceLoader riêng; không nhầm chúng với hai file đang học.

### 8.3. Maven Shade

Spring Boot 2.7 release notes chỉ rõ cần append imports file khi dùng Maven Shade mà không dựa vào cấu hình parent/plugin phù hợp:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
```

Nếu uber-JAR còn chứa `spring.factories`, dùng properties-aware transformer để merge key/value. Spring Boot Maven Plugin cung cấp `PropertiesMergingResourceTransformer` cho mục đích này:

```xml
<transformer implementation="org.springframework.boot.maven.PropertiesMergingResourceTransformer">
    <resource>META-INF/spring.factories</resource>
</transformer>
```

Cấu hình plugin thực tế còn phụ thuộc phiên bản Maven Shade và cách khai báo dependency của transformer. Sau khi package, phải kiểm tra nội dung resource trong JAR cuối cùng, không chỉ kiểm tra JAR module ban đầu.

### 8.4. Gradle Shadow

Với Gradle Shadow, append imports file trong cấu hình task:

```groovy
tasks.withType(com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
}
```

Nếu artifact cũng cần `spring.factories`, cấu hình merge properties theo API của phiên bản Shadow đang dùng. Không giả định thao tác append file text thông thường sẽ hợp nhất đúng các key properties trùng nhau.

## 9. Kiểm thử migration và artifact

### 9.1. ApplicationContextRunner kiểm tra condition

`ApplicationContextRunner` giúp kiểm tra auto-configuration với tổ hợp classpath, property và user bean xác định:

```java
class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeAutoConfiguration.class)
                    );

    @Test
    void createsDefaultClient() {
        contextRunner.run(context -> {
            assertThat(context).hasSingleBean(AcmeClient.class);
        });
    }
}
```

Test này kiểm tra condition và bean behavior của class đã chỉ định. Nó không tự chứng minh Boot có tìm thấy imports file trong JAR đã publish.

### 9.2. Kiểm tra bean back-off và dependency tùy chọn

Nên có các test:

- Class dependency có mặt: auto-configuration được áp dụng.
- Class dependency bị loại bằng `FilteredClassLoader`: cấu hình lùi lại, context không lỗi.
- Property tắt tính năng: không tạo bean.
- Ứng dụng cung cấp bean riêng: `@ConditionalOnMissingBean` khiến default bean không được tạo.
- Thiếu property bắt buộc: lỗi binding/validation có thông báo phù hợp.
- Web-only configuration: dùng `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` nếu cần.

Dùng `ConditionEvaluationReport` khi cần giải thích vì sao condition không khớp. Điều này giúp phân biệt lỗi registration với lỗi điều kiện.

### 9.3. Kiểm tra resource discovery trong JAR đã đóng gói

Cần có smoke test ở mức artifact:

1. Build module auto-configuration và starter.
2. Đóng gói JAR theo đúng quy trình phát hành.
3. Dùng JAR đó làm dependency của một ứng dụng mẫu bên ngoài module.
4. Khởi động ứng dụng bằng dòng Boot mục tiêu.
5. Xác nhận bean mặc định xuất hiện và user bean override hoạt động.
6. Lặp lại trên các phiên bản Boot mà thư viện công bố hỗ trợ.
7. Nếu dùng shaded JAR, kiểm tra imports và spring.factories sau khi hợp nhất resource.

Không chỉ gọi `AutoConfigurations.of(AcmeAutoConfiguration.class)` trong test nội bộ rồi kết luận file imports đã đúng. Cách gọi đó đưa class trực tiếp vào runner và bỏ qua bước phát hiện resource.

### 9.4. Ma trận CI theo phiên bản Boot

Với thư viện có dual registration, một ma trận tối thiểu có thể là:

| Runtime test | Điều cần xác nhận |
| --- | --- |
| Boot 2.6.x | Key cũ trong spring.factories phát hiện auto-configuration |
| Boot 2.7.x | Cả hai file được đọc, class trùng chỉ áp dụng một lần |
| Boot 3.x | Imports file phát hiện class; key EnableAutoConfiguration cũ không còn là đường đăng ký |
| Boot 4.x | Imports file và các SPI spring.factories còn dùng đều hoạt động |

Dùng đúng Spring Cloud release train tương thích với từng dòng Boot. Nếu thư viện chỉ hỗ trợ một số patch/minor cụ thể, ma trận CI và tài liệu phát hành phải ghi rõ phạm vi đó.

## 10. Lỗi thường gặp khi nâng cấp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Auto-configuration hoạt động trên Boot 2.6 nhưng biến mất trên Boot 3 | Chỉ đăng ký qua key `EnableAutoConfiguration` trong `spring.factories` | Thêm class vào `AutoConfiguration.imports` |
| Auto-configuration hoạt động trên Boot 3 nhưng mất trên Boot 2.6 | Chỉ có imports file, runtime cũ không đọc file này | Giữ key cũ trong `spring.factories` nếu còn hỗ trợ Boot 2.6 |
| Một class được cấu hình hai lần trên Boot 2.7 | Danh sách ở hai file không cùng tên hoặc có class wrapper khác nhau | Dùng cùng FQCN; kiểm tra duplicate và context condition |
| Boot 3 không còn chạy BootstrapConfiguration | Đã xóa toàn bộ `spring.factories` khi chuyển auto-configuration | Giữ key `BootstrapConfiguration` nếu vẫn dùng legacy bootstrap context |
| EnvironmentPostProcessor không chạy sau migration | Xóa key SPI khác cùng lúc với key auto-configuration | Đăng ký lại đúng SPI trong `spring.factories` và dùng FQCN của Boot mục tiêu |
| Boot 2.6 không áp dụng class gắn @AutoConfiguration | Annotation chỉ có từ Boot 2.7; class không được nhận diện như configuration trên baseline cũ | Dùng `@Configuration` cho source tương thích cũ hoặc phát hành variant riêng |
| JAR module chạy nhưng uber-JAR không có bean | Shade/Shadow ghi đè hoặc không hợp nhất imports resource | Append imports file và kiểm tra artifact sau package |
| Một số SPI biến mất sau shading | `spring.factories` bị ghi đè hoặc merge sai theo key | Dùng properties-aware transformer |
| Auto-configuration có trong file nhưng không tạo bean | Condition không khớp hoặc user bean khiến back-off | Xem ConditionEvaluationReport, classpath và property |
| Exclude cũ không còn hiệu lực sau khi đổi package | Tên class cũ vẫn nằm trong exclusion hoặc ordering | Cập nhật exclusion và cân nhắc AutoConfiguration.replacements |
| Test nội bộ pass nhưng ứng dụng tiêu thụ không thấy cấu hình | Test import class trực tiếp, không kiểm tra resource trong JAR | Thêm smoke test với artifact đã đóng gói |
| Test slice kéo nhầm cấu hình production | Dùng chung imports file thay vì file riêng cho slice | Đăng ký theo tên annotation test slice |

## 11. Quy trình migration đề xuất

### 11.1. Kiểm kê trước khi sửa

Trước tiên, tìm tất cả resource registration trong từng module:

- `META-INF/spring.factories`.
- `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- Các file `META-INF/spring/*.imports` dành cho test slice hoặc extension point khác.
- Các file `AutoConfiguration.replacements` nếu đã từng đổi package/class.

Với mỗi key trong `spring.factories`, xác định framework nào đọc nó, phiên bản nào đọc và class nào được đăng ký. Không kết luận chỉ từ tên class.

### 11.2. Chia danh sách theo mục đích

Tạo bảng kiểm kê:

| Entry hiện tại | Loại | Vị trí sau migration |
| --- | --- | --- |
| `EnableAutoConfiguration` | Auto-configuration candidate | `AutoConfiguration.imports`; giữ key cũ nếu cần Boot 2.6 |
| `BootstrapConfiguration` | Spring Cloud legacy bootstrap | Giữ trong `spring.factories` khi còn dùng |
| `EnvironmentPostProcessor` | Boot environment SPI | Giữ trong `spring.factories` |
| `AutoConfigurationImportFilter` | Boot candidate filter SPI | Giữ trong `spring.factories` |
| Test slice annotation key | Test-slice registration | Dùng file `META-INF/spring/<annotation FQCN>.imports` theo dòng Boot mục tiêu |

### 11.3. Thực hiện chuyển đổi

1. Tạo imports file trong module chứa auto-configuration.
2. Mỗi class ghi trên một dòng bằng FQCN chính xác.
3. Nếu hỗ trợ Boot 2.6, giữ danh sách tương ứng dưới key cũ trong `spring.factories`.
4. Nếu hỗ trợ Boot 2.6, tránh compile class auto-configuration chung với annotation/API chỉ có từ Boot 2.7 trở lên.
5. Giữ các key SPI khác trong `spring.factories`.
6. Cập nhật test slice vào imports file riêng nếu thư viện cung cấp custom slice.
7. Kiểm tra exclusions, ordering, replacements và package scan.
8. Cấu hình resource merging cho uber-JAR nếu có.

### 11.4. Xác minh theo từng runtime

- Chạy CI với Boot 2.6 nếu còn công bố hỗ trợ.
- Chạy Boot 2.7 để xác minh dual registration và deduplication.
- Chạy Boot 3.x để bảo đảm auto-configuration không phụ thuộc key cũ.
- Chạy Boot 4.x nếu thư viện tuyên bố tương thích dòng này.
- Kiểm tra ứng dụng tiêu thụ thật bằng JAR đã publish, không chỉ test trong module nguồn.
- Ghi rõ phiên bản Spring Cloud release train tương thích trong ma trận hỗ trợ của thư viện.

## 12. Checklist trước khi phát hành

1. Đã phân loại mọi key trong `spring.factories` theo extension point thực tế chưa?
2. Auto-configuration đã được liệt kê trong imports file chưa?
3. Nếu hỗ trợ Boot 2.6, key `EnableAutoConfiguration` cũ còn được giữ chưa?
4. Nếu hỗ trợ Boot 2.6, source có tránh tham chiếu `@AutoConfiguration` hoặc API chỉ có từ Boot 2.7 không?
5. Hai danh sách dual registration có cùng FQCN không?
6. Có test trên Boot 2.7 để xác nhận duplicate được deduplicate không?
7. Các key Spring Cloud `BootstrapConfiguration` còn được giữ nếu ứng dụng dùng legacy bootstrap không?
8. Các SPI như `EnvironmentPostProcessor` và `AutoConfigurationImportFilter` còn được đăng ký đúng không?
9. Test-slice registration có file riêng theo annotation không?
10. Conditions, bean back-off và ordering có được kiểm thử không?
11. Exclusions và class replacement có được cập nhật khi đổi package không?
12. Resource trong JAR đã đóng gói có đầy đủ và không bị ghi đè không?
13. Nếu dùng Maven Shade/Gradle Shadow, imports và spring.factories có merge đúng không?
14. Có smoke test dùng artifact như một dependency bên ngoài không?
15. Ma trận Boot và Spring Cloud release train có ghi rõ phạm vi hỗ trợ không?

## 13. Tài liệu tham khảo chính thức

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes#changes-to-auto-configuration): giới thiệu imports file, giữ tương thích với spring.factories và deduplicate class được liệt kê ở cả hai nơi.
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide#auto-configuration-files): loại bỏ key EnableAutoConfiguration khỏi spring.factories và xác nhận các key khác không bị ảnh hưởng.
- [Spring Boot 4.1.2 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): imports format, conditions, ordering, replacements, ApplicationContextRunner, FilteredClassLoader và starter.
- [Spring Boot 4.1.2 — EnvironmentPostProcessor API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/EnvironmentPostProcessor.html): xác nhận SPI này vẫn được đăng ký trong META-INF/spring.factories.
- [Spring Boot 4.1.1 — AutoConfigurationImportFilter API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html): xác nhận filter vẫn được đăng ký qua spring.factories.
- [Spring Cloud — Customizing the Bootstrap Configuration](https://docs.spring.io/spring-cloud/docs/current/reference/htmlsingle/#customizing-the-bootstrap-configuration): key BootstrapConfiguration và cách tạo bootstrap context.
- [Spring Boot Maven Plugin — PropertiesMergingResourceTransformer](https://docs.spring.io/spring-boot/maven-plugin/api/java/org/springframework/boot/maven/PropertiesMergingResourceTransformer.html): merge file properties như spring.factories khi tạo shaded JAR.
- [Spring Boot 2.7 Reference — Additional Auto-configuration and Slicing](https://docs.spring.io/spring-boot/docs/2.7.15/reference/html/features.html): imports file riêng cho test slice.

**Ghi nhớ:** `AutoConfiguration.imports` là nơi công bố auto-configuration cho Spring Boot 2.7 trở lên. `spring.factories` vẫn là registry cho nhiều SPI khác, trong đó có Spring Cloud `BootstrapConfiguration` khi dùng legacy bootstrap. Với thư viện hỗ trợ Boot 2.6 và Boot 3/4, hãy dual-register đúng class, giữ các key SPI còn dùng và kiểm thử resource trong JAR đã phát hành.

