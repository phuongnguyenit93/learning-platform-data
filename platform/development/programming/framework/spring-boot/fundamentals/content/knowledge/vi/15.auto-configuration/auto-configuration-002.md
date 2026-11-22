# `@EnableAutoConfiguration` và cơ chế import cấu hình

Một trong những điểm tiện lợi của Spring Boot là bạn có thể thêm dependency phù hợp vào dự án rồi bắt đầu sử dụng nhiều tính năng mà không phải tự khai báo từng bean hạ tầng. Ví dụ, khi ứng dụng có thư viện Spring MVC, Spring Boot có thể cấu hình các thành phần web cần thiết; khi có thư viện truy cập dữ liệu và datasource phù hợp, framework có thể cung cấp những bean hỗ trợ làm việc với database.

Khả năng này đến từ **auto-configuration**. Annotation `@EnableAutoConfiguration` bật cơ chế đó. Phía sau annotation, Spring sử dụng cơ chế import cấu hình để tìm và đưa những lớp auto-configuration phù hợp vào quá trình xử lý của application context.

Để hiểu luồng này, cần nắm ba ý:

- `@Import` là cơ chế Spring Framework đưa cấu hình hoặc registrar vào application context.
- `@EnableAutoConfiguration` sử dụng một import selector để chọn các cấu hình tự động có thể áp dụng.
- Những auto-configuration được chọn vẫn phải vượt qua các condition như classpath, property và bean hiện có trước khi bean definitions được đăng ký.

## 1. Auto-configuration giải quyết vấn đề gì?

Trong một ứng dụng Spring truyền thống, developer thường phải tự khai báo nhiều thành phần hạ tầng:

- `DataSource` và transaction manager cho truy cập dữ liệu.
- MVC infrastructure, message converters và web server cho ứng dụng HTTP.
- Các bean hỗ trợ JSON, validation, cache hoặc security.
- Những cấu hình kết nối và tích hợp thư viện.

Spring Boot cung cấp cấu hình mặc định theo những quy ước phổ biến. Khi điều kiện phù hợp, framework có thể tự đăng ký các bean cần thiết. Bạn vẫn có thể tùy chỉnh bằng property hoặc tự khai báo bean thay thế.

Ví dụ, với ứng dụng có Spring Web trên classpath:

```text
Thêm dependency web
        |
        v
Spring Boot phát hiện class liên quan đến web
        |
        v
Các web auto-configuration phù hợp được chọn
        |
        v
Kiểm tra điều kiện và cấu hình môi trường
        |
        v
Đăng ký các bean hạ tầng phù hợp
        |
        v
Ứng dụng có thể xử lý HTTP request
```

Auto-configuration không phải phép thuật tạo mọi thứ bất kể cấu hình. Nó là tập hợp những configuration class có điều kiện, được import và xử lý theo quy tắc của Spring.

## 2. `@EnableAutoConfiguration` là gì?

`@EnableAutoConfiguration` nằm trong package:

```java
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

Annotation này yêu cầu Spring Boot xem xét và áp dụng những auto-configuration phù hợp dựa trên classpath, `Environment`, bean definitions và những điều kiện liên quan.

Một lớp khởi động tối giản có thể viết:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.ComponentScan;

@ComponentScan
@EnableAutoConfiguration
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Trong ứng dụng thông thường, bạn ít khi viết hai annotation trên riêng lẻ vì `@SpringBootApplication` đã kết hợp chúng.

### 2.1. `@SpringBootApplication` bao gồm `@EnableAutoConfiguration`

Khai báo phổ biến:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Ở mức khái niệm, `@SpringBootApplication` kết hợp:

```text
@SpringBootApplication
    |
    +-- @SpringBootConfiguration
    |
    +-- @EnableAutoConfiguration
    |
    +-- @ComponentScan
```

Ba phần có trách nhiệm khác nhau:

| Annotation | Vai trò |
| --- | --- |
| `@SpringBootConfiguration` | Đánh dấu lớp cấu hình chính của ứng dụng, dựa trên `@Configuration` |
| `@EnableAutoConfiguration` | Bật cơ chế lựa chọn và import auto-configuration |
| `@ComponentScan` | Tìm component của ứng dụng trong phạm vi package được quét |

Do đó, `@SpringBootApplication` vừa hỗ trợ component scanning, vừa bật auto-configuration. Hai cơ chế này phối hợp nhưng không phải một.

## 3. Cơ chế import cấu hình của Spring Framework

Trước khi đi sâu vào `@EnableAutoConfiguration`, hãy hiểu `@Import`.

`@Import` là annotation của Spring Framework:

```java
org.springframework.context.annotation.Import
```

Nó cho phép một configuration class đưa thêm cấu hình hoặc thành phần đăng ký bean vào context.

Ví dụ:

```java
@Configuration
@Import(FeatureConfiguration.class)
public class ApplicationConfiguration {
}
```

Spring sẽ xử lý `FeatureConfiguration` như một configuration được import, ngay cả khi nó không được phát hiện qua component scan.

### 3.1. Import một configuration class

```java
@Configuration
public class FeatureConfiguration {

    @Bean
    public FeatureService featureService() {
        return new FeatureService();
    }
}
```

Lớp khác import nó:

```java
@Configuration
@Import(FeatureConfiguration.class)
public class MainConfiguration {
}
```

Bean `featureService` có thể được đăng ký từ configuration được import. Đây là cách chia cấu hình thành các module nhỏ và tái sử dụng.

### 3.2. Import bằng `ImportSelector`

Spring còn cho phép import động thông qua `ImportSelector`. Interface này có phương thức:

```java
String[] selectImports(AnnotationMetadata importingClassMetadata);
```

Selector nhận metadata của configuration class đang import nó và trả về tên đầy đủ của các class cần import.

Ví dụ:

```java
public class FeatureImportSelector implements ImportSelector {

    @Override
    public String[] selectImports(
            AnnotationMetadata importingClassMetadata) {
        return new String[] {
            "com.example.demo.feature.FeatureConfiguration"
        };
    }
}
```

Sử dụng:

```java
@Configuration
@Import(FeatureImportSelector.class)
public class ApplicationConfiguration {
}
```

Selector giúp quyết định class cấu hình nào được import tại thời điểm Spring xử lý metadata, thay vì ghi cứng mọi cấu hình trong annotation `@Import`.

### 3.3. Import bằng `ImportBeanDefinitionRegistrar`

Một cơ chế khác là `ImportBeanDefinitionRegistrar`. Nó cho phép đăng ký bean definitions trực tiếp vào registry trong quá trình xử lý import.

Khác biệt ở mức khái niệm:

| Cơ chế | Công việc |
| --- | --- |
| `@Import(SomeConfiguration.class)` | Import configuration class cụ thể |
| `ImportSelector` | Chọn danh sách class để import |
| `DeferredImportSelector` | Chọn class import ở giai đoạn deferred sau khi xử lý các configuration thông thường |
| `ImportBeanDefinitionRegistrar` | Tự đăng ký bean definitions vào registry |

`@EnableAutoConfiguration` dựa trên import selector để lựa chọn auto-configuration; một phần quan trọng của thiết kế này là xử lý import theo cơ chế deferred.

## 4. `@EnableAutoConfiguration` sử dụng `@Import` như thế nào?

Trong Spring Boot, `@EnableAutoConfiguration` được kết nối với `AutoConfigurationImportSelector` thông qua `@Import`.

Có thể hình dung cấu trúc annotation như sau:

```java
@AutoConfigurationPackage
@Import(AutoConfigurationImportSelector.class)
public @interface EnableAutoConfiguration {
    // Các thuộc tính exclude...
}
```

Đây là sơ đồ rút gọn để minh họa quan hệ chính. Source code thực tế còn có metadata, alias và các annotation liên quan.

`AutoConfigurationImportSelector` là một `DeferredImportSelector`. Nó tìm các ứng viên auto-configuration, lọc những cấu hình bị loại trừ hoặc không phù hợp, rồi trả về danh sách cấu hình cần import.

Luồng tổng quát:

```text
@SpringBootApplication
        |
        v
@EnableAutoConfiguration
        |
        v
@Import(AutoConfigurationImportSelector.class)
        |
        v
AutoConfigurationImportSelector
        |
        v
Tìm danh sách auto-configuration candidates
        |
        v
Áp dụng exclusions và condition filters
        |
        v
Sắp xếp theo quy tắc auto-configuration
        |
        v
Import các configuration class phù hợp
        |
        v
Spring xử lý @Bean và đăng ký BeanDefinition
        |
        v
Bean instances được tạo theo lifecycle
```

Điểm quan trọng: `@EnableAutoConfiguration` không trực tiếp tạo `DataSource`, `DispatcherServlet` hoặc `ObjectMapper`. Nó bật cơ chế tìm và import cấu hình; các configuration class được import mới khai báo những bean tương ứng.

## 5. Vì sao dùng `DeferredImportSelector`?

`ImportSelector` thông thường chọn các class cần import trong quá trình xử lý configuration. `DeferredImportSelector` trì hoãn việc xử lý import cho đến sau khi các configuration class thông thường đã được phân tích.

Điều này rất hữu ích cho auto-configuration vì Spring Boot cần xét cả cấu hình do người dùng khai báo.

Ví dụ, thư viện cung cấp bean mặc định:

```java
@Configuration(proxyBeanMethods = false)
public class DefaultClockAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Clock.class)
    public Clock appClock() {
        return Clock.systemUTC();
    }
}
```

Ứng dụng tự định nghĩa:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationClockConfiguration {

    @Bean
    public Clock businessClock() {
        return Clock.systemDefaultZone();
    }
}
```

Khi auto-configuration được xử lý sau cấu hình ứng dụng, điều kiện `@ConditionalOnMissingBean(Clock.class)` có thể nhìn thấy bean `Clock` do ứng dụng cung cấp và khiến cấu hình mặc định “back off”.

Nếu auto-configuration được xử lý quá sớm, nó có thể chưa thấy các bean definitions mà người dùng sắp đăng ký. Deferred import giúp Spring Boot tổ chức quá trình này phù hợp với mục tiêu ưu tiên cấu hình của người dùng.

**Không nên hiểu deferred là đợi mọi bean instance được tạo xong.** Đây là việc trì hoãn xử lý import trong giai đoạn phân tích/đăng ký cấu hình, trước khi toàn bộ singleton beans được khởi tạo.

## 6. Auto-configuration candidates đến từ đâu?

Spring Boot cần một cơ chế để biết thư viện nào cung cấp các auto-configuration class. Cách đăng ký đã thay đổi theo các thế hệ Spring Boot.

### 6.1. Cơ chế metadata trong các phiên bản Spring Boot hiện đại

Với các dòng Spring Boot hiện đại (từ thế hệ 2.7 trở đi và được sử dụng trong Spring Boot 3.x), auto-configuration được khai báo trong file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng là tên đầy đủ của một auto-configuration class:

```text
com.example.library.autoconfigure.SearchAutoConfiguration
com.example.library.autoconfigure.MetricsAutoConfiguration
```

Khi thư viện được đóng gói thành JAR, file metadata nằm trong JAR và Spring Boot có thể đọc các class được liệt kê để tạo candidate list.

Điều này cho phép một starter hoặc thư viện tích hợp công bố auto-configuration của mình mà không cần ứng dụng người dùng tự import từng class.

### 6.2. Cơ chế cũ qua `spring.factories`

Ở các phiên bản Spring Boot cũ, auto-configuration thường được đăng ký trong:

```text
META-INF/spring.factories
```

Ví dụ metadata kiểu cũ:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.library.autoconfigure.SearchAutoConfiguration,\
com.example.library.autoconfigure.MetricsAutoConfiguration
```

Từ thế hệ Spring Boot 2.7, cơ chế file `AutoConfiguration.imports` được giới thiệu để đăng ký auto-configuration. Spring Boot 3 chuyển sang cơ chế mới cho auto-configuration registration; các dự án nâng cấp từ phiên bản cũ cần di chuyển metadata theo hướng dẫn của phiên bản tương ứng. `spring.factories` vẫn được dùng cho một số factory/extension point khác, nên không nên xóa file đó chỉ vì auto-configuration đã chuyển sang imports file.

### 6.3. So sánh hai cách đăng ký

| Nội dung | `spring.factories` kiểu cũ | `AutoConfiguration.imports` |
| --- | --- | --- |
| Vị trí | `META-INF/spring.factories` | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Dạng dữ liệu | Property key ánh xạ tới danh sách class | Một class name trên mỗi dòng |
| Vai trò lịch sử | Đăng ký auto-configuration trong các dòng Boot cũ | Cơ chế chuyên biệt cho auto-configuration ở các dòng hiện đại |
| Khi phát triển thư viện mới | Chỉ dùng nếu dòng Boot cũ yêu cầu | Dùng theo hướng dẫn của dòng Boot hiện đại |

Hãy theo đúng phiên bản Spring Boot mà thư viện hỗ trợ. Một starter cần tương thích nhiều thế hệ có thể cần metadata hoặc cấu trúc module theo chiến lược migration cụ thể; không nên sao chép máy móc cấu hình từ dự án cũ.

## 7. Auto-configuration class có hình dạng như thế nào?

Một auto-configuration class là configuration class chứa các bean mặc định và điều kiện để quyết định khi nào chúng được đăng ký.

Trong các phiên bản Spring Boot hiện đại, có thể dùng `@AutoConfiguration`:

```java
package com.example.library.autoconfigure;

import com.example.library.SearchClient;
import com.example.library.DefaultSearchClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(SearchClient.class)
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    public SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
```

Ví dụ giả định `SearchClient` và `DefaultSearchClient` thuộc thư viện tích hợp và có mặt khi dependency phù hợp được thêm vào.

Hai điều kiện có ý nghĩa khác nhau:

- `@ConditionalOnClass(SearchClient.class)`: chỉ xét cấu hình khi class `SearchClient` có trên classpath.
- `@ConditionalOnMissingBean(SearchClient.class)`: chỉ đăng ký bean mặc định nếu chưa có bean phù hợp theo kiểu.

`@AutoConfiguration` là cách đánh dấu cấu hình dành cho cơ chế auto-configuration. Nó dựa trên configuration class của Spring và thường được khai báo với `proxyBeanMethods = false`, phù hợp với cấu hình bean độc lập.

### 7.1. `@AutoConfiguration` và `@Configuration`

Bạn vẫn có thể thấy các auto-configuration cũ được khai báo bằng `@Configuration`. Trong các dòng Boot hiện đại, `@AutoConfiguration` biểu đạt rõ vai trò auto-configuration và hỗ trợ metadata về thứ tự trước/sau.

Ví dụ:

```java
@AutoConfiguration(
    after = DataSourceAutoConfiguration.class
)
public class ReportingAutoConfiguration {
}
```

Hoặc dùng annotation riêng:

```java
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
```

Các cơ chế ordering này điều khiển thứ tự xử lý giữa những auto-configuration class trong quá trình import. Chúng không phải `@Order` để sắp xếp mọi bean instance trong application context.

## 8. Điều kiện quyết định auto-configuration có được áp dụng không

Có mặt trong candidate list **không có nghĩa cấu hình chắc chắn được áp dụng**. Sau khi được tìm thấy, configuration class còn phải thỏa các điều kiện.

Một số condition phổ biến:

| Annotation | Dữ liệu được kiểm tra | Ví dụ |
| --- | --- | --- |
| `@ConditionalOnClass` | Classpath | Có Spring MVC hoặc thư viện client |
| `@ConditionalOnMissingClass` | Classpath | Không có implementation khác |
| `@ConditionalOnBean` | Bean definitions | Đã có `DataSource` hoặc dependency cần thiết |
| `@ConditionalOnMissingBean` | Bean definitions | Ứng dụng chưa cung cấp bean thay thế |
| `@ConditionalOnProperty` | Environment property | `feature.enabled=true` |
| `@ConditionalOnWebApplication` | Kiểu application context | Ứng dụng servlet hoặc reactive |
| `@ConditionalOnResource` | Resource | File cấu hình hoặc template tồn tại |

Ví dụ:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.messaging.MessageClient")
@ConditionalOnProperty(
    prefix = "messaging",
    name = "enabled",
    havingValue = "true"
)
public class MessagingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    MessagePublisher messagePublisher() {
        return new DefaultMessagePublisher();
    }
}
```

Để cấu hình trên được áp dụng, class tùy chọn phải có trên classpath và property phải bật. Bean method còn có điều kiện riêng để không thay thế bean do ứng dụng cung cấp.

### 8.1. Candidate, match và bean instance là ba giai đoạn khác nhau

```text
AutoConfiguration.imports
        |
        v
Candidate class được tìm thấy
        |
        v
Các condition được đánh giá
        |
        +-- Không match --> Bỏ qua cấu hình
        |
        +-- Match
              |
              v
       Xử lý configuration class
              |
              v
       Đăng ký bean definitions
              |
              v
       Khởi tạo bean khi cần
```

Một class có thể được liệt kê nhưng bị loại do condition. Một condition có thể match nhưng một bean method bên trong lại không match điều kiện riêng. Và ngay cả khi bean definition đã được đăng ký, quá trình tạo instance vẫn có thể thất bại do dependency hoặc cấu hình runtime.

## 9. `@AutoConfigurationPackage` và package gốc của ứng dụng

`@EnableAutoConfiguration` còn liên quan đến `@AutoConfigurationPackage`. Annotation này sử dụng registrar để ghi nhận package gốc của ứng dụng làm thông tin cho những cơ chế tìm kiếm khác của Spring Boot.

Ví dụ:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

Package `com.example.shop` có thể được đăng ký làm auto-configuration package. Những cơ chế như entity scanning mặc định của Spring Boot có thể dựa vào package này để xác định vùng tìm kiếm.

Phân biệt:

- `@ComponentScan` tìm component như `@Service`, `@Controller`, `@Component`.
- `@AutoConfigurationPackage` ghi nhận package gốc cho các cơ chế auto-configuration khác sử dụng.
- `@EnableAutoConfiguration` bật import auto-configuration.

Ba cơ chế phối hợp nhưng không thay thế nhau.

### 9.1. Vì sao vị trí lớp main quan trọng?

Thông thường, nên đặt lớp `@SpringBootApplication` ở package gốc chung:

```text
com.example.shop
├── ShopApplication.java
├── controller/
├── service/
├── repository/
└── domain/
```

Nhờ vậy, component scan mặc định và package gốc cho các cơ chế liên quan có thể bao phủ các package con của ứng dụng.

Nếu đặt lớp main quá sâu hoặc package của entity nằm ngoài vùng mặc định, bạn có thể cần cấu hình riêng như `scanBasePackages`, `@EntityScan` hoặc `@EnableJpaRepositories`. Mở rộng component scan không tự động thay đổi mọi phạm vi entity/repository scanning.

## 10. Loại trừ auto-configuration không cần thiết

Không phải auto-configuration nào có mặt trong classpath cũng phù hợp với ứng dụng. Spring Boot cho phép loại trừ những cấu hình cụ thể.

### 10.1. Dùng `exclude` trên `@SpringBootApplication`

Ví dụ:

```java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

@SpringBootApplication(
    exclude = DataSourceAutoConfiguration.class
)
public class DemoApplication {
}
```

Khi đó, `DataSourceAutoConfiguration` bị loại khỏi quá trình auto-configuration. Ví dụ này có thể hữu ích cho ứng dụng không cần cấu hình datasource tự động, nhưng nếu một bean khác vẫn cần `DataSource`, ứng dụng có thể không khởi động được.

### 10.2. Dùng `excludeName`

Khi class cần loại trừ không có sẵn tại compile time, có thể dùng tên đầy đủ:

```java
@SpringBootApplication(
    excludeName = {
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
    }
)
public class DemoApplication {
}
```

`excludeName` nhận tên class dưới dạng chuỗi. Cách này tránh phải import trực tiếp class loại trừ.

### 10.3. Dùng property

Có thể cấu hình:

```properties
spring.autoconfigure.exclude=\
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

Với nhiều class, cung cấp danh sách tên theo định dạng property phù hợp:

```properties
spring.autoconfigure.exclude=\
org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration,\
org.springframework.boot.autoconfigure.orm.jpa.HibernateJpaAutoConfiguration
```

Tên class chính xác phụ thuộc phiên bản Spring Boot; hãy tham khảo dependency và API của dự án.

### 10.4. Khi nào nên exclude?

Chỉ loại trừ khi bạn biết cấu hình nào đang được áp dụng và vì sao không cần nó. Ví dụ:

- Ứng dụng không dùng database nhưng có dependency vô tình kéo theo một cấu hình liên quan.
- Muốn tự cấu hình một phần hạ tầng theo cách khác.
- Một auto-configuration không tương thích với môi trường triển khai.

Không nên exclude hàng loạt chỉ để làm ứng dụng khởi động được. Nếu một auto-configuration được áp dụng ngoài ý muốn, hãy xem condition report và xác định dependency/property/bean nào khiến nó match.

## 11. Thứ tự giữa các auto-configuration

Auto-configuration có thể phụ thuộc vào bean được cung cấp bởi auto-configuration khác. Spring Boot hỗ trợ metadata để sắp xếp chúng.

Ví dụ:

```java
@AutoConfiguration
@AutoConfigureAfter(DataSourceAutoConfiguration.class)
public class AuditAutoConfiguration {
    // Cấu hình có thể cần DataSource
}
```

Hoặc:

```java
@AutoConfiguration
@AutoConfigureBefore(ValidationAutoConfiguration.class)
public class CustomValidationAutoConfiguration {
}
```

Trong các dòng hỗ trợ `@AutoConfiguration`, có thể dùng thuộc tính `before`, `after`, `beforeName` và `afterName` ngay trên annotation.

### 11.1. Ordering không thay thế condition

`@AutoConfigureAfter` chỉ sắp xếp thứ tự xử lý tương đối. Nó không tự bảo đảm dependency mà cấu hình cần tồn tại.

Nếu `AuditAutoConfiguration` cần một `DataSource`, vẫn nên có điều kiện:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
@ConditionalOnBean(DataSource.class)
public class AuditAutoConfiguration {
}
```

Điều kiện xác định cấu hình có đủ điều kiện áp dụng không; ordering xác định thứ tự xử lý giữa các cấu hình được import. Hai mục đích khác nhau.

### 11.2. Không nhầm auto-configuration ordering với `@Order`

| Cơ chế | Đối tượng được sắp xếp | Mục đích |
| --- | --- | --- |
| `@AutoConfigureBefore` / `@AutoConfigureAfter` | Auto-configuration classes | Sắp xếp cấu hình framework |
| `@Order` / `Ordered` | Bean hoặc extension point có hỗ trợ order | Sắp xếp phần tử/handler |
| Constructor injection | Quan hệ dependency giữa bean | Bảo đảm dependency được resolve để tạo bean |
| `@DependsOn` | Quan hệ khởi tạo theo bean name | Yêu cầu bean khác khởi tạo trước |

Nếu auto-configuration A cần bean B, hãy dùng condition và thứ tự cấu hình phù hợp. Không dùng `@Order` trên hai configuration class để thay cho dependency.

## 12. Tự tạo một auto-configuration cho thư viện

Giả sử bạn đang phát triển thư viện cung cấp client tìm kiếm. Người dùng chỉ cần thêm dependency của thư viện vào dự án; nếu chưa tự cung cấp `SearchClient`, thư viện sẽ cung cấp implementation mặc định.

### 12.1. Khai báo interface và implementation

```java
package com.example.search;

public interface SearchClient {
    String search(String query);
}
```

```java
package com.example.search;

public class DefaultSearchClient implements SearchClient {

    @Override
    public String search(String query) {
        return "Search result for: " + query;
    }
}
```

### 12.2. Tạo auto-configuration class

```java
package com.example.search.autoconfigure;

import com.example.search.DefaultSearchClient;
import com.example.search.SearchClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "search",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(SearchClient.class)
    public SearchClient searchClient() {
        return new DefaultSearchClient();
    }
}
```

Giải thích:

- `@AutoConfiguration` đánh dấu cấu hình dành cho auto-configuration.
- `@ConditionalOnProperty` chỉ bật tích hợp khi property phù hợp; ví dụ này mặc định bật nếu property không tồn tại.
- `@ConditionalOnMissingBean` nhường quyền nếu ứng dụng đã cung cấp `SearchClient`.
- `@Bean` cung cấp implementation mặc định.

Nếu implementation thực tế cần một thư viện tùy chọn, hãy bổ sung `@ConditionalOnClass` và tổ chức cấu hình để class tùy chọn chỉ được nạp khi dependency có mặt.

### 12.3. Đăng ký class trong imports file

Tạo file:

```text
src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.example.search.autoconfigure.SearchAutoConfiguration
```

Khi đóng gói thư viện, file này phải nằm trong JAR tại đúng đường dẫn `META-INF/spring/...`. Spring Boot đọc metadata từ classpath để tìm auto-configuration class.

### 12.4. Ứng dụng sử dụng thư viện

Ứng dụng chỉ cần thêm dependency thư viện. Nếu bật mặc định:

```properties
search.enabled=true
```

Hoặc bỏ property nếu cấu hình dùng `matchIfMissing = true`. Khi không có bean `SearchClient` khác, auto-configuration có thể đăng ký `DefaultSearchClient`.

Người dùng vẫn có thể tự cung cấp implementation:

```java
@Configuration(proxyBeanMethods = false)
public class ApplicationSearchConfiguration {

    @Bean
    public SearchClient searchClient() {
        return new CompanySearchClient();
    }
}
```

Khi auto-configuration được xử lý đúng thứ tự, `@ConditionalOnMissingBean(SearchClient.class)` khiến bean mặc định không được đăng ký.

### 12.5. Vì sao package của auto-configuration cần được tổ chức cẩn thận?

Auto-configuration được tìm qua metadata file, không cần dựa vào component scan của ứng dụng. Vì vậy, nên đặt nó trong package riêng như `com.example.search.autoconfigure`, ngoài package gốc mà ứng dụng người dùng quét.

Nếu để auto-configuration class nằm trong vùng component scan của ứng dụng, nó có thể bị phát hiện như configuration thông thường ngoài con đường import dự kiến. Điều này dễ làm điều kiện hoặc thứ tự xử lý không còn như thiết kế. Tách package và dùng imports file giúp vai trò của class rõ ràng.

## 13. Cơ chế import được xử lý ở những bước nào?

Luồng nội bộ có nhiều processor, nhưng có thể hình dung qua các giai đoạn:

1. Spring bắt đầu xử lý configuration class gốc của ứng dụng.
2. Đọc `@Import` và phát hiện `AutoConfigurationImportSelector`.
3. Xử lý configuration thông thường và thu thập những deferred imports.
4. `AutoConfigurationImportSelector` tải danh sách auto-configuration candidates từ metadata.
5. Áp dụng danh sách exclude, các import filter và điều kiện phù hợp.
6. Sắp xếp các auto-configuration class theo metadata ordering.
7. Các class được chọn tham gia quá trình xử lý configuration.
8. Bean methods và các registrar tương ứng đăng ký bean definitions.
9. Container tạo bean instances theo dependency graph, scope và lifecycle.

Đây là mô hình để học, không phải danh sách đầy đủ mọi lời gọi nội bộ trong từng phiên bản Spring Boot. Các bước chi tiết có thể thay đổi giữa các phiên bản.

### 13.1. Import không đồng nghĩa với tạo object ngay

Khi một auto-configuration class được import, điều đó chủ yếu có nghĩa Spring đưa cấu hình vào quá trình phân tích. Các `@Bean` methods có thể tạo bean definitions. Việc tạo object thật còn phụ thuộc scope, lazy initialization và thời điểm dependency được yêu cầu.

Ví dụ:

```java
@Bean
@Lazy
public ExpensiveReportClient reportClient() {
    return new ExpensiveReportClient();
}
```

Bean definition có thể được đăng ký khi cấu hình được xử lý, nhưng object có thể được tạo trễ đến lúc cần. Do đó, cần phân biệt:

```text
Candidate được tìm thấy
    ≠ configuration được import
    ≠ bean definition được đăng ký
    ≠ bean instance được tạo
```

Mỗi dấu `≠` biểu thị một giai đoạn khác nhau; một bước có thể bị bỏ qua hoặc thất bại mà không đồng nghĩa mọi bước trước đó đều chưa diễn ra.

## 14. Chẩn đoán auto-configuration

Khi một bean mặc định xuất hiện ngoài ý muốn hoặc không xuất hiện dù đã thêm starter, hãy kiểm tra condition report.

### 14.1. Bật `--debug`

Khởi động ứng dụng với:

```bash
./gradlew bootRun --args='--debug'
```

Hoặc Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Nếu chạy trên Windows, sử dụng `gradlew.bat` hoặc `mvnw.cmd` tương ứng. Cú pháp truyền argument có thể cần điều chỉnh theo shell và phiên bản plugin; trong IDE cũng có thể đặt `--debug` vào Program arguments.

Spring Boot có thể in **Conditions Evaluation Report** với:

- Positive matches: cấu hình có condition phù hợp.
- Negative matches: cấu hình bị bỏ qua và lý do.
- Exclusions: cấu hình bị loại trừ.
- Unconditional classes: cấu hình không phụ thuộc một số condition cụ thể.

### 14.2. Đặt câu hỏi theo đúng tầng

| Câu hỏi | Nơi cần kiểm tra |
| --- | --- |
| Auto-configuration class có trong candidate list không? | Imports metadata và dependency JAR |
| Class có bị loại trừ không? | `exclude`, `excludeName`, `spring.autoconfigure.exclude` |
| Condition nào không match? | Condition Evaluation Report |
| Bean definition có được đăng ký không? | Bean definition registry / application context |
| Bean instance tạo thất bại vì sao? | Exception, `Caused by`, dependency và lifecycle |
| Người dùng có cung cấp bean thay thế không? | `@ConditionalOnMissingBean`, bean definitions và cấu hình ứng dụng |

Không nên bật bean definition overriding để xử lý mọi lỗi auto-configuration. Nếu cấu hình bị bỏ qua vì thiếu class hoặc property, overriding không giải quyết được nguyên nhân.

### 14.3. Kiểm tra metadata trong thư viện

Nếu tự phát triển starter, hãy kiểm tra JAR sau khi build có file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

và file có chứa đúng fully qualified class name. Nếu file không được đóng gói hoặc class name sai, Spring Boot không thể tìm candidate theo metadata đó.

Với dự án dùng Spring Boot cũ, kiểm tra metadata `spring.factories` theo quy ước của phiên bản. Không trộn quy tắc đăng ký giữa các dòng Boot mà không có chiến lược tương thích rõ.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`@EnableAutoConfiguration` tự tạo mọi bean.” | Nó bật cơ chế tìm và import cấu hình; bean được đăng ký từ configuration/registrar khi điều kiện phù hợp |
| “Auto-configuration giống component scan.” | Component scan tìm component trong package; auto-configuration import cấu hình từ metadata |
| “Một class có trong imports file chắc chắn được áp dụng.” | Class còn phải qua exclusions và conditions |
| “Import class nghĩa là object được tạo ngay.” | Import cấu hình, đăng ký definition và khởi tạo instance là các bước khác nhau |
| “`@Order` sắp xếp mọi auto-configuration và mọi bean.” | Auto-configuration có ordering riêng; `@Order` dùng ở extension point hỗ trợ order |
| “`@ConditionalOnMissingBean` luôn nhìn thấy bean đăng ký sau.” | Condition chỉ đánh giá trạng thái definitions tại thời điểm nó chạy |
| “`spring.factories` không còn được dùng ở bất cứ đâu.” | Metadata auto-configuration chuyển sang imports file ở các dòng mới; `spring.factories` vẫn có vai trò khác tùy phiên bản |
| “`scanBasePackages` thay đổi tất cả vùng tìm entity/repository.” | Nó điều chỉnh component scan; entity và repository có cơ chế cấu hình riêng |
| “Exclude một auto-configuration sẽ xóa mọi bean cùng chức năng.” | Nó loại cấu hình được chỉ định; bean có thể vẫn được đăng ký từ cấu hình khác |

## 16. Bài thực hành

### Bài 1 — Quan sát `@SpringBootApplication`

Tạo một ứng dụng Spring Boot với lớp main:

```java
@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Mở source hoặc dùng IDE để xem các meta-annotation của `@SpringBootApplication`. Xác định annotation nào bật auto-configuration và annotation nào bật component scan.

### Bài 2 — Tự import một configuration

Tạo `FeatureConfiguration` có một `@Bean`. Dùng `@Import(FeatureConfiguration.class)` từ configuration class khác. Lấy bean từ application context và giải thích vì sao không cần component scan tìm class đó.

### Bài 3 — Thử một auto-configuration đơn giản

Tạo `SearchAutoConfiguration` với `@AutoConfiguration` và `@ConditionalOnMissingBean(SearchClient.class)`. Đăng ký class trong `AutoConfiguration.imports`. Chạy ứng dụng khi chưa có bean `SearchClient`, sau đó tự khai báo một bean `SearchClient` trong application.

Quan sát lúc nào bean mặc định được đăng ký và khi nào nó “back off”.

### Bài 4 — Loại trừ auto-configuration

Chọn một auto-configuration có trong dự án và loại trừ bằng `exclude` hoặc property `spring.autoconfigure.exclude`. Bật `--debug` và so sánh Condition Evaluation Report trước/sau khi loại trừ.

### Bài 5 — Kiểm tra classpath condition

Tạo một auto-configuration phụ thuộc một class tùy chọn. Thử chạy khi dependency có mặt và khi không có. Giải thích vì sao `@ConditionalOnClass` cần được đặt ở vị trí phù hợp để class tùy chọn không bị nạp quá sớm.

### Bài 6 — Phân biệt import và component scan

Tạo một configuration class nằm ngoài package gốc của ứng dụng. Không dùng component scan mở rộng, nhưng import class qua `@Import`. Quan sát bean vẫn được đăng ký. Giải thích vì sao import không phụ thuộc phạm vi package scan.

### Bài 7 — Đọc metadata JAR

Đóng gói một thư viện auto-configuration nhỏ. Mở JAR và tìm `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Xác nhận class name trong file trùng với package/class thực tế.

## 17. Ghi nhớ

`@EnableAutoConfiguration` bật cơ chế tự cấu hình của Spring Boot. Annotation này sử dụng `@Import` để đưa `AutoConfigurationImportSelector` vào quá trình xử lý; selector tìm candidate auto-configuration từ metadata, áp dụng exclusions và conditions, rồi trả về các cấu hình phù hợp để Spring tiếp tục xử lý.

Trong các dòng Spring Boot hiện đại, file `AutoConfiguration.imports` là nơi thư viện công bố auto-configuration class. Các class được chọn vẫn phải thỏa condition như classpath, property hoặc bean hiện có. Khi được import, cấu hình có thể đăng ký bean definitions; container khởi tạo object theo dependency, scope và lifecycle.

Khi phát triển ứng dụng hoặc starter, hãy phân biệt rõ **component scan**, **configuration import**, **auto-configuration candidate**, **condition match**, **bean definition** và **bean instance**. Hiểu đúng từng bước giúp bạn giải thích vì sao một starter tự cấu hình được, vì sao bean mặc định có thể nhường quyền cho ứng dụng, và cách chẩn đoán khi cấu hình tự động không hoạt động như mong đợi.
