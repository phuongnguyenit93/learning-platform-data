# Quan hệ lịch sử giữa spring.factories và đăng ký auto-configuration

Trong các dự án Spring Boot cũ, bạn thường thấy một file có tên `META-INF/spring.factories` dùng để liệt kê các lớp auto-configuration. Từ Spring Boot 2.7, một file đăng ký chuyên biệt được giới thiệu: `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Đến Spring Boot 3.0, việc đăng ký auto-configuration qua key `org.springframework.boot.autoconfigure.EnableAutoConfiguration` trong `spring.factories` không còn được hỗ trợ.

Thay đổi này **không có nghĩa Spring Boot đã loại bỏ `spring.factories`**. File đó vẫn tiếp tục phục vụ nhiều extension point khác, chẳng hạn `ApplicationListener`, `ApplicationContextInitializer`, `EnvironmentPostProcessor` và `FailureAnalyzer`. Chỉ cơ chế đăng ký auto-configuration đã chuyển sang file imports chuyên biệt.

Bài học thuộc chương **Auto-configuration** của **Spring Boot Fundamentals**. Mục tiêu là hiểu vì sao cơ chế cũ được dùng, quá trình chuyển đổi qua các phiên bản, cách viết file đăng ký mới, cách duy trì thư viện tương thích nhiều dòng Spring Boot và những lỗi thường gặp khi đóng gói starter hoặc auto-configuration.

## 1. Auto-configuration cần một cơ chế khám phá

Spring Boot giúp ứng dụng có thể khởi động với ít cấu hình thủ công. Khi dependency phù hợp có trên classpath, Boot có thể tự động đăng ký những bean cần thiết, miễn là các điều kiện cấu hình tương ứng thỏa mãn.

Ví dụ, một thư viện có thể cung cấp auto-configuration cho client gửi email:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(MailClient.class)
public class MailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public MailClient mailClient(MailProperties properties) {
        return new MailClient(properties.host(), properties.port());
    }
}
```

Class trên định nghĩa cấu hình, nhưng Spring Boot cần biết **làm thế nào để tìm ra class này** khi ứng dụng chỉ thêm thư viện vào dependency. Không thể yêu cầu mỗi ứng dụng phải tự import mọi auto-configuration của tất cả starter.

Vì vậy, thư viện cần công bố một danh sách các lớp cấu hình được phép tham gia quá trình auto-configuration. Spring Boot đọc danh sách này trên classpath, sau đó xử lý condition, ordering và bean definitions.

Qua lịch sử Spring Boot, cách công bố danh sách đó đã thay đổi:

```text
Spring Boot 1.x đến 2.6
    META-INF/spring.factories
        key: EnableAutoConfiguration
                  │
                  ▼
Spring Boot 2.7
    AutoConfiguration.imports (cách mới)
    spring.factories (cách cũ vẫn tương thích)
                  │
                  ▼
Spring Boot 3.0 trở lên
    AutoConfiguration.imports
    spring.factories vẫn dành cho các extension point khác
```

Đây là mốc lịch sử quan trọng khi đọc một thư viện Spring Boot cũ hoặc nâng cấp một starter tự viết.

## 2. Cơ chế lịch sử: đăng ký qua spring.factories

Trước Spring Boot 2.7, auto-configuration thường được đăng ký trong file:

```text
META-INF/spring.factories
```

Đây là file theo định dạng Java properties. Key là tên đầy đủ của một extension point; value là danh sách class implementation được phân tách bằng dấu phẩy.

Ví dụ đăng ký auto-configuration:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.mail.autoconfigure.MailAutoConfiguration,\
com.example.storage.autoconfigure.StorageAutoConfiguration
```

Key:

```text
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

là tên đầy đủ của marker `EnableAutoConfiguration`. Value liệt kê các class auto-configuration mà Spring Boot cần xem xét.

### 2.1. Mỗi thư viện có thể đóng góp một spring.factories riêng

Giả sử một ứng dụng sử dụng ba thư viện:

```text
application.jar
├── spring-boot-autoconfigure.jar
├── mail-starter.jar
│   └── META-INF/spring.factories
├── storage-starter.jar
│   └── META-INF/spring.factories
└── metrics-starter.jar
    └── META-INF/spring.factories
```

Mỗi thư viện có thể khai báo các implementation của cùng một key trong file riêng. Spring Boot sử dụng cơ chế tải factories trên classpath để tổng hợp các ứng viên từ các thư viện.

Vì thế, ứng dụng không cần có một file `spring.factories` duy nhất chứa mọi auto-configuration của tất cả dependency. Mỗi starter có thể tự công bố các thành phần mở rộng của nó.

### 2.2. Cách Spring Boot xử lý danh sách

Có thể mô tả luồng ở mức khái niệm:

```text
Các JAR trên runtime classpath
          │
          ▼
Tìm các META-INF/spring.factories
          │
          ▼
Đọc key EnableAutoConfiguration
          │
          ▼
Tổng hợp tên các auto-configuration class
          │
          ▼
Xử lý exclusions, ordering và conditions
          │
          ▼
Đăng ký bean definitions phù hợp
          │
          ▼
Tạo bean trong ApplicationContext
```

File `spring.factories` chỉ là **nơi công bố implementation**. Nó không trực tiếp tạo bean và cũng không quyết định một auto-configuration chắc chắn được áp dụng.

Sau khi class được khám phá, Spring Boot vẫn cần xử lý các điều kiện như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean` và `@ConditionalOnMissingBean`. Một auto-configuration được liệt kê nhưng condition không khớp có thể không đóng góp bean nào.

### 2.3. Ví dụ lịch sử với thư viện tự viết

Một thư viện có thể có cấu trúc:

```text
mail-starter/
├── src/main/java/
│   └── com/example/mail/autoconfigure/
│       └── MailAutoConfiguration.java
└── src/main/resources/
    └── META-INF/
        └── spring.factories
```

Nội dung file:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.mail.autoconfigure.MailAutoConfiguration
```

Ứng dụng tiêu thụ chỉ cần khai báo dependency của starter. Nếu JAR được đóng gói đúng và các condition phù hợp, Boot có thể phát hiện auto-configuration mà không cần ứng dụng import class đó bằng tay.

### 2.4. Lịch sử không đồng nghĩa với cách khuyến nghị cho dự án mới

Nhiều tài liệu hoặc bài viết cũ vẫn hướng dẫn đăng ký auto-configuration bằng `spring.factories`. Ví dụ đó đúng với các phiên bản Spring Boot tương ứng, nhưng không nên sao chép nguyên trạng vào một thư viện chỉ nhắm tới Boot 3.x.

Khi đọc một hướng dẫn, hãy kiểm tra version Spring Boot được dùng. Cùng một file đăng ký có thể hoạt động ở Boot 2.6, vẫn hoạt động trong giai đoạn chuyển tiếp 2.7, nhưng không còn đăng ký auto-configuration ở Boot 3.0.

## 3. Vì sao Spring Boot chuyển sang AutoConfiguration.imports?

Spring Boot 2.7 giới thiệu file chuyên biệt:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File mới giải quyết việc công bố danh sách auto-configuration bằng một định dạng rõ ràng hơn:

- Chỉ dành riêng cho auto-configuration.
- Mỗi dòng chứa một fully qualified class name.
- Không cần key properties dài.
- Không cần danh sách class phân tách bằng dấu phẩy và dấu nối dòng.
- Có thể thêm comment bắt đầu bằng `#`.
- Tách việc đăng ký auto-configuration khỏi các extension point khác vẫn dùng `spring.factories`.

Ví dụ:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
com.example.storage.autoconfigure.StorageAutoConfiguration
com.example.metrics.autoconfigure.MetricsAutoConfiguration
```

### 3.1. So sánh hai định dạng

| Tiêu chí | `spring.factories` cũ | `AutoConfiguration.imports` |
|---|---|---|
| Vị trí | `META-INF/spring.factories` | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Định dạng | Java properties | Danh sách class, một dòng mỗi class |
| Cấu trúc | Key và value | Không có key |
| Danh sách class | Phân tách bằng dấu phẩy | Mỗi class trên một dòng |
| Comment | Theo cú pháp properties | Dòng bắt đầu bằng `#` |
| Phạm vi | Nhiều extension point | Riêng danh sách auto-configuration |
| Trạng thái hiện đại | Không dùng key EnableAutoConfiguration từ Boot 3.0 | Cơ chế đăng ký auto-configuration hiện hành |

### 3.2. File mới không thay thế toàn bộ chức năng của spring.factories

Đây là điểm dễ hiểu nhầm nhất.

Spring Boot 3.0 bỏ hỗ trợ **đăng ký auto-configuration qua key EnableAutoConfiguration trong spring.factories**. Điều đó không có nghĩa mọi key khác trong file này bị xóa.

Ví dụ, các extension point vẫn sử dụng `spring.factories`:

- `org.springframework.context.ApplicationListener`.
- `org.springframework.context.ApplicationContextInitializer`.
- `org.springframework.boot.env.EnvironmentPostProcessor`.
- `org.springframework.boot.diagnostics.FailureAnalyzer`.

Vì vậy, một thư viện có thể cần đồng thời cả hai file:

```text
META-INF/
├── spring.factories
└── spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Trong đó:

- `spring.factories` chứa các extension point vẫn sử dụng cơ chế factories.
- `AutoConfiguration.imports` chứa danh sách auto-configuration.

Không xóa `spring.factories` khỏi một thư viện chỉ vì đã chuyển auto-configuration sang file imports. Hãy kiểm tra những key khác mà thư viện còn đăng ký.

## 4. Dòng thời gian: Boot 2.6, 2.7 và 3.0

Ba mốc này thường được dùng khi giải thích quá trình chuyển đổi.

### 4.1. Trước Spring Boot 2.7

Cơ chế phổ biến là:

```text
META-INF/spring.factories

org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.demo.autoconfigure.DemoAutoConfiguration
```

Spring Boot tìm key `EnableAutoConfiguration` để thu thập các auto-configuration class.

### 4.2. Spring Boot 2.7: giai đoạn chuyển tiếp

Spring Boot 2.7 giới thiệu `AutoConfiguration.imports` và khuyến nghị chuyển danh sách auto-configuration sang file mới.

Tuy nhiên, để tương thích ngược:

- Boot 2.7 vẫn đọc các entry auto-configuration cũ trong `spring.factories`.
- Có thể liệt kê cùng một auto-configuration trong cả hai file.
- Boot 2.7 loại bỏ các entry bị trùng khi chúng xuất hiện ở cả hai vị trí.
- Việc nạp auto-configuration từ `spring.factories` được đánh dấu deprecated.

Đây là giai đoạn phù hợp để các thư viện chuyển đổi mà vẫn duy trì khả năng hoạt động với những ứng dụng dùng dòng Boot cũ hơn.

### 4.3. Spring Boot 3.0: bỏ key đăng ký cũ

Spring Boot 3.0 loại bỏ hỗ trợ đăng ký auto-configuration qua key:

```text
org.springframework.boot.autoconfigure.EnableAutoConfiguration
```

trong `META-INF/spring.factories`.

Thay vào đó, auto-configuration phải được liệt kê trong:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Các entry `spring.factories` thuộc key khác vẫn không bị ảnh hưởng bởi thay đổi này.

### 4.4. Bảng timeline

| Phiên bản | `spring.factories` với key EnableAutoConfiguration | `AutoConfiguration.imports` |
|---|---|---|
| Boot 2.6 và cũ hơn | Cơ chế đăng ký auto-configuration thông dụng | Chưa phải cơ chế được hỗ trợ |
| Boot 2.7 | Vẫn được đọc để tương thích; cách cũ deprecated | Được giới thiệu và hỗ trợ |
| Boot 3.0 trở lên | Không còn hỗ trợ key này để đăng ký auto-configuration | Cơ chế đăng ký auto-configuration |

Một thư viện cần hỗ trợ nhiều dòng Boot phải chọn chiến lược đăng ký phù hợp với phiên bản thấp nhất và cao nhất mà nó cam kết hỗ trợ.

## 5. Định dạng và vị trí chính xác của AutoConfiguration.imports

Tên file đầy đủ rất quan trọng. Không phải mọi file có hậu tố `.imports` đều là danh sách auto-configuration.

Đường dẫn chuẩn:

```text
src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Sau khi build JAR, resource phải xuất hiện tại cùng đường dẫn bên trong artifact:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ nội dung:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
com.example.mail.autoconfigure.MailWebAutoConfiguration
```

### 5.1. Quy tắc viết class name

Mỗi dòng dùng fully qualified class name:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
```

Không viết:

```text
MailAutoConfiguration
```

Không viết package path bằng dấu gạch chéo:

```text
com/example/mail/autoconfigure/MailAutoConfiguration.class
```

Không thêm hậu tố `.class`. File chứa tên class Java, không phải đường dẫn file class.

### 5.2. Comment và dòng trống

Có thể thêm comment bắt đầu bằng `#`:

```text
# Core auto-configuration
com.example.mail.autoconfigure.MailAutoConfiguration

# Optional web integration
com.example.mail.autoconfigure.MailWebAutoConfiguration
```

Comment giúp người duy trì thư viện hiểu mục đích từng nhóm cấu hình. Dòng trống có thể dùng để tách nhóm cho dễ đọc.

### 5.3. Nested auto-configuration class

Trong trường hợp hiếm khi auto-configuration là nested class, dùng ký hiệu `$` giữa outer class và nested class:

```text
com.example.Outer$NestedAutoConfiguration
```

Tuy nhiên, thông thường nên đặt auto-configuration class ở package và class riêng để dễ quản lý, kiểm thử và sắp xếp.

## 6. Annotation @AutoConfiguration được giới thiệu cùng cơ chế mới

Spring Boot 2.7 giới thiệu annotation:

```java
import org.springframework.boot.autoconfigure.AutoConfiguration;
```

Annotation này được dùng để đánh dấu top-level auto-configuration class được liệt kê trong `AutoConfiguration.imports`.

Ví dụ:

```java
package com.example.mail.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(MailClient.class)
public class MailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public MailClient mailClient() {
        return new MailClient();
    }
}
```

`@AutoConfiguration` được meta-annotate với `@Configuration`, do đó auto-configuration vẫn là cấu hình Spring thông thường. Annotation mới còn hỗ trợ các thuộc tính ordering như `before`, `beforeName`, `after` và `afterName`.

### 6.1. @AutoConfiguration thay vai trò đánh dấu top-level class

Trước đây, auto-configuration thường dùng:

```java
@Configuration
public class MailAutoConfiguration {
}
```

Với cơ chế mới, top-level auto-configuration nên dùng:

```java
@AutoConfiguration
public class MailAutoConfiguration {
}
```

Các configuration class lồng bên trong hoặc được import bởi auto-configuration vẫn có thể sử dụng `@Configuration` như thông thường.

Không nên hiểu rằng `@AutoConfiguration` thay thế mọi `@Configuration` trong ứng dụng. Nó có mục đích riêng cho các lớp auto-configuration.

### 6.2. @AutoConfiguration không tự đăng ký class

Việc gắn `@AutoConfiguration` lên class không có nghĩa Spring Boot tự tìm thấy class ở mọi package.

Class vẫn cần được liệt kê trong file imports:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
```

Đồng thời, auto-configuration class nên nằm trong package riêng và không phải mục tiêu của component scan ứng dụng. Cơ chế đăng ký imports là đường khám phá dành cho auto-configuration.

### 6.3. Ordering với @AutoConfiguration

Có thể khai báo:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class MailDatabaseIntegrationAutoConfiguration {
}
```

Hoặc:

```java
@AutoConfiguration(beforeName = "com.example.other.OtherAutoConfiguration")
public class MailIntegrationAutoConfiguration {
}
```

Các thuộc tính ordering quyết định thứ tự xử lý auto-configuration classes. Chúng **không** quyết định trực tiếp thứ tự tạo bean instance. Bean instance vẫn được tạo theo dependency graph, scope và các quan hệ như `@DependsOn`.

## 7. Ví dụ hoàn chỉnh: chuyển một thư viện từ spring.factories sang imports

Giả sử thư viện `acme-mail-spring-boot-starter` có auto-configuration:

```text
acme-mail-spring-boot-starter/
└── src/main/
    ├── java/
    │   └── com/acme/mail/autoconfigure/
    │       └── AcmeMailAutoConfiguration.java
    └── resources/
        └── META-INF/
            └── spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

### 7.1. Auto-configuration class

```java
package com.acme.mail.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(AcmeMailClient.class)
@ConditionalOnProperty(
        prefix = "acme.mail",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class AcmeMailAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public AcmeMailClient acmeMailClient(AcmeMailProperties properties) {
        return new AcmeMailClient(
                properties.host(),
                properties.port()
        );
    }
}
```

Ví dụ giả định `AcmeMailClient` và `AcmeMailProperties` là các class được thư viện cung cấp và đã có cấu hình binding tương ứng.

### 7.2. File imports

Tạo:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.acme.mail.autoconfigure.AcmeMailAutoConfiguration
```

### 7.3. Cấu hình của ứng dụng sử dụng starter

```yaml
acme:
  mail:
    enabled: true
    host: smtp.example.test
    port: 587
```

Ứng dụng thêm dependency starter. Spring Boot tìm file imports trong JAR, thu thập auto-configuration class, kiểm tra classpath và property condition, rồi đăng ký bean nếu điều kiện phù hợp.

### 7.4. Người dùng có thể thay bean mặc định

Ứng dụng có thể tự khai báo:

```java
@Configuration(proxyBeanMethods = false)
public class CustomMailConfiguration {

    @Bean
    public AcmeMailClient acmeMailClient() {
        return new CustomAcmeMailClient();
    }
}
```

Nếu custom bean được đăng ký trước khi auto-configuration method condition được đánh giá, `@ConditionalOnMissingBean` khiến bean mặc định lùi lại.

Đây là pattern phổ biến: thư viện cung cấp default behavior nhưng cho phép ứng dụng tùy biến bằng bean riêng.

## 8. Hỗ trợ đồng thời Spring Boot 2.x và 3.x

Một thư viện dùng trong nhiều ứng dụng có thể phải hỗ trợ:

- Ứng dụng cũ dùng Spring Boot 2.6 hoặc thấp hơn.
- Ứng dụng chuyển tiếp dùng Spring Boot 2.7.
- Ứng dụng mới dùng Spring Boot 3.x.

Trong trường hợp này, cần hiểu rõ vùng tương thích.

### 8.1. Đăng ký ở cả hai file trong giai đoạn chuyển tiếp

Một thư viện có thể liệt kê cùng auto-configuration ở cả:

```text
META-INF/spring.factories
```

và:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Ví dụ file cũ:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.mail.autoconfigure.MailAutoConfiguration
```

File mới:

```text
com.example.mail.autoconfigure.MailAutoConfiguration
```

Kết quả theo version:

| Phiên bản chạy | Kết quả |
|---|---|
| Boot 2.6 và cũ hơn | Dùng entry trong `spring.factories` |
| Boot 2.7 | Hỗ trợ cả hai vị trí và khử trùng lặp |
| Boot 3.x | Dùng file imports; key EnableAutoConfiguration trong `spring.factories` không còn được đọc để đăng ký auto-configuration |

Đây là cách được Spring Boot 2.7 release notes mô tả cho thư viện cần hỗ trợ cả dòng cũ và dòng mới.

### 8.2. Chú ý annotation class theo phiên bản

`@AutoConfiguration` được giới thiệu trong Spring Boot 2.7. Nếu thư viện còn cam kết chạy trên Boot cũ hơn 2.7, hãy kiểm tra tương thích classpath của annotation và các API được sử dụng.

Không nên chỉ thay file đăng ký rồi giả định mọi source code của thư viện vẫn tương thích với mọi phiên bản. Cần xem:

- Phiên bản Spring Boot thấp nhất được hỗ trợ.
- Các annotation/API mà class auto-configuration tham chiếu.
- Phiên bản Java baseline.
- Spring Framework API được dùng trong code.
- Cách kiểm thử ma trận phiên bản.

Với thư viện cần hỗ trợ nhiều major line, có thể cần thiết kế source/API tương thích hoặc phát hành các dòng artifact riêng. Hãy kiểm tra bằng các ứng dụng mẫu thực sự chạy trên từng version được cam kết.

### 8.3. Không bỏ file cũ quá sớm

Nếu thư viện vẫn cần hỗ trợ Boot 2.6 hoặc thấp hơn, xóa entry `EnableAutoConfiguration` khỏi `spring.factories` sẽ làm auto-configuration không được khám phá trên các phiên bản đó.

Ngược lại, nếu chỉ nhắm tới Boot 3.x, việc tiếp tục duy trì key cũ trong `spring.factories` không có tác dụng đăng ký auto-configuration và có thể gây hiểu nhầm cho người bảo trì.

Quyết định giữ hai file phải dựa trên ma trận phiên bản được hỗ trợ, không phải thói quen.

## 9. spring.factories vẫn được dùng cho các extension point nào?

File `spring.factories` có phạm vi rộng hơn auto-configuration. Nó là cơ chế factories để công bố các implementation theo key class/interface.

Trong Spring Boot hiện đại, một số extension point vẫn dùng cơ chế này.

### 9.1. ApplicationListener

Listener có thể cần nhận event rất sớm, thậm chí trước khi ApplicationContext được tạo. Khi đó đăng ký nó như một bean trong context có thể quá muộn.

Ví dụ:

```properties
org.springframework.context.ApplicationListener=\
com.example.bootstrap.StartupListener
```

Class:

```java
package com.example.bootstrap;

import org.springframework.boot.context.event.ApplicationStartingEvent;
import org.springframework.context.ApplicationListener;

public class StartupListener
        implements ApplicationListener<ApplicationStartingEvent> {

    @Override
    public void onApplicationEvent(ApplicationStartingEvent event) {
        System.out.println("SpringApplication is starting");
    }
}
```

Spring Boot có thể nạp listener từ factories và đăng ký với `SpringApplication` ở giai đoạn phù hợp.

### 9.2. ApplicationContextInitializer

Initializer được dùng để tùy chỉnh ApplicationContext trước khi context được refresh:

```properties
org.springframework.context.ApplicationContextInitializer=\
com.example.bootstrap.CustomContextInitializer
```

Ví dụ:

```java
package com.example.bootstrap;

import org.springframework.context.ApplicationContextInitializer;
import org.springframework.context.ConfigurableApplicationContext;

public class CustomContextInitializer
        implements ApplicationContextInitializer<ConfigurableApplicationContext> {

    @Override
    public void initialize(
            ConfigurableApplicationContext applicationContext
    ) {
        System.out.println("Preparing ApplicationContext");
    }
}
```

Đây là extension point khác với auto-configuration. Initializer tác động đến quá trình chuẩn bị context; nó không phải danh sách các cấu hình bean mặc định.

### 9.3. EnvironmentPostProcessor

`EnvironmentPostProcessor` cho phép điều chỉnh Environment trước khi ApplicationContext được refresh:

```properties
org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.bootstrap.CustomEnvironmentPostProcessor
```

Ví dụ:

```java
package com.example.bootstrap;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.env.EnvironmentPostProcessor;
import org.springframework.core.env.ConfigurableEnvironment;

public class CustomEnvironmentPostProcessor
        implements EnvironmentPostProcessor {

    @Override
    public void postProcessEnvironment(
            ConfigurableEnvironment environment,
            SpringApplication application
    ) {
        System.out.println("Environment is being prepared");
    }
}
```

Extension point này phù hợp khi thư viện cần nạp thêm PropertySource hoặc tùy chỉnh Environment trước khi quá trình tạo bean bắt đầu.

### 9.4. FailureAnalyzer

FailureAnalyzer giúp chuyển một lỗi startup thành thông báo dễ hiểu hơn:

```properties
org.springframework.boot.diagnostics.FailureAnalyzer=\
com.example.diagnostics.CustomFailureAnalyzer
```

Ví dụ minh họa:

```java
package com.example.diagnostics;

import org.springframework.boot.diagnostics.AbstractFailureAnalyzer;
import org.springframework.boot.diagnostics.FailureAnalysis;

public class CustomFailureAnalyzer
        extends AbstractFailureAnalyzer<IllegalStateException> {

    @Override
    protected FailureAnalysis analyze(
            Throwable rootFailure,
            IllegalStateException cause
    ) {
        return new FailureAnalysis(
                "Application configuration is invalid.",
                "Check the custom feature settings.",
                cause
        );
    }
}
```

FailureAnalyzer thuộc hạ tầng chẩn đoán lỗi khởi động, không phải một bean nghiệp vụ thông thường.

### 9.5. Bảng phân biệt

| Mục đích | Key/resource thường dùng |
|---|---|
| Đăng ký auto-configuration hiện đại | `AutoConfiguration.imports` |
| Application listeners được nạp qua factories | `ApplicationListener` trong `spring.factories` |
| Application context initializers | `ApplicationContextInitializer` trong `spring.factories` |
| Environment post-processors | `EnvironmentPostProcessor` trong `spring.factories` |
| Failure analyzers | `FailureAnalyzer` trong `spring.factories` |

Danh sách này là các ví dụ phổ biến, không phải toàn bộ extension point có thể được nạp bằng factories. Khi di chuyển một thư viện, hãy kiểm tra từng key trong file thay vì xóa cả file.

## 10. Đừng nhầm AutoConfiguration.imports với các file .imports khác

Spring Boot sử dụng nhiều file imports cho những mục đích khác nhau.

Ví dụ:

```text
META-INF/spring/
├── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports
```

File đầu đăng ký auto-configuration thông thường. File thứ hai phục vụ management context configuration trong Actuator.

Spring Boot 2.7 cũng chuyển đăng ký một số test slice configuration từ `spring.factories` sang file:

```text
META-INF/spring/<fully-qualified-name-of-test-annotation>.imports
```

Đây là cơ chế riêng cho test slice. Không nên đưa test configuration vào `AutoConfiguration.imports` chỉ vì cả hai đều dùng đuôi `.imports`.

Khi làm việc với file imports, luôn xác định **tên file đầy đủ và extension point mà file đó đăng ký**.

## 11. Đóng gói nhiều thư viện: vì sao cần merge resource?

Một ứng dụng có thể phụ thuộc nhiều starter, mỗi starter đóng góp file:

```text
starter-a.jar
└── META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── com.example.a.AutoConfiguration

starter-b.jar
└── META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── com.example.b.AutoConfiguration
```

Khi chạy theo classpath hoặc executable JAR thông thường, Spring Boot có thể tìm các resource cùng tên trong các dependency JAR và tổng hợp các candidate.

Nhưng nếu bạn tạo **uber JAR/shaded JAR** bằng cách giải nén nhiều dependency rồi gộp chúng thành một file, nhiều resource có cùng đường dẫn có thể bị ghi đè nếu plugin không được cấu hình để append.

Kết quả nguy hiểm: ứng dụng chỉ còn một phần danh sách auto-configuration, dù mọi thư viện vẫn nằm trong JAR.

### 11.1. Ví dụ lỗi khi merge sai

Giả sử:

```text
starter-a: AutoConfiguration.imports
    com.example.a.AutoConfiguration

starter-b: AutoConfiguration.imports
    com.example.b.AutoConfiguration
```

Nếu quy trình đóng gói chỉ giữ một file trùng đường dẫn thay vì ghép nội dung, output cuối có thể chỉ còn:

```text
com.example.b.AutoConfiguration
```

Auto-configuration của starter A biến mất khỏi danh sách discovery.

Đây là lỗi đóng gói resource, không phải lỗi condition hoặc component scanning.

### 11.2. Maven Shade Plugin

Nếu dùng `maven-shade-plugin` để tạo shaded JAR, có thể cần `AppendingTransformer` cho resource imports:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
```

Nếu project cũng đóng gói management context imports, cấu hình append file tương ứng:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports</resource>
</transformer>
```

Đây là cấu hình cho tình huống dùng Maven Shade Plugin; không cần thêm vào mọi project Maven. Spring Boot executable JAR thông thường không đồng nghĩa với một shaded JAR được giải nén và hợp nhất resource theo cách này.

### 11.3. Gradle Shadow Plugin

Với Gradle Shadow Plugin:

```groovy
tasks.withType(com.github.jengelman.gradle.plugins.shadow.tasks.ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
    append("META-INF/spring/org.springframework.boot.actuate.autoconfigure.web.ManagementContextConfiguration.imports")
}
```

Tên package/task type có thể khác theo version plugin. Điều quan trọng là cấu hình Shadow để append các resource imports trùng đường dẫn thay vì giữ một bản bất kỳ.

Nếu thư viện còn dùng `spring.factories` cho extension point khác, hãy kiểm tra cơ chế merge factories tương ứng của plugin. Đừng chỉ merge imports rồi vô tình làm mất các factories entry còn cần thiết.

### 11.4. Kiểm tra nội dung JAR sau khi build

Dùng lệnh:

```bash
jar --list --file build/libs/application-all.jar
```

Tìm:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Sau đó có thể trích hoặc xem nội dung resource để xác nhận mọi auto-configuration dự kiến đều có trong file cuối cùng.

Nếu build một Spring Boot executable JAR chuẩn, hãy kiểm tra resource trong dependency JAR lồng bên trong hoặc dùng công cụ phù hợp để xem nội dung từng nested JAR. Không mặc định rằng mọi dependency resource phải được flatten vào cùng một file ở root JAR.

## 12. Auto-configuration class nên được tổ chức thế nào?

Việc đổi file đăng ký không thay thế các quy ước thiết kế auto-configuration.

Một cấu trúc thư viện có thể như sau:

```text
acme-storage-spring-boot-autoconfigure/
├── src/main/java/
│   └── com/acme/storage/autoconfigure/
│       ├── AcmeStorageAutoConfiguration.java
│       ├── AcmeStorageProperties.java
│       └── AcmeStorageClient.java
└── src/main/resources/
    ├── META-INF/spring/
    │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── META-INF/
        └── additional-spring-configuration-metadata.json
```

### 12.1. Không dựa vào component scanning để tìm auto-configuration

Auto-configuration classes nên được khám phá thông qua file imports. Chúng nên nằm trong package riêng và không phải mục tiêu của component scanning thông thường của ứng dụng.

Ví dụ, nếu lớp main của ứng dụng ở package:

```text
com.acme.application
```

còn thư viện auto-configuration ở:

```text
com.acme.storage.autoconfigure
```

thì việc package của thư viện nằm ngoài vùng component scan là bình thường. File imports giúp Boot phát hiện nó mà không cần scan toàn bộ package thư viện.

Auto-configuration không nên bật component scanning rộng để tìm các thành phần của chính thư viện. Dùng `@Import` cụ thể cho các cấu hình hoặc component cần thiết để tránh quét nhầm package ứng dụng.

### 12.2. Sử dụng condition để tránh tạo bean không cần thiết

Ví dụ:

```java
@AutoConfiguration
@ConditionalOnClass(AcmeStorageClient.class)
@EnableConfigurationProperties(AcmeStorageProperties.class)
public class AcmeStorageAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    @ConditionalOnProperty(
            prefix = "acme.storage",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    public AcmeStorageClient acmeStorageClient(
            AcmeStorageProperties properties
    ) {
        return new AcmeStorageClient(properties.endpoint());
    }
}
```

Cấu hình này minh họa một auto-configuration có điều kiện theo classpath, property và bean hiện có. Trong project thực tế, hãy bảo đảm các class/property type đã được định nghĩa và các điều kiện phù hợp với mục đích của starter.

### 12.3. Auto-configuration ordering

Nếu auto-configuration cần được xử lý sau một cấu hình khác:

```java
@AutoConfiguration(after = DataSourceAutoConfiguration.class)
public class AcmeJdbcAutoConfiguration {
}
```

Có thể dùng các thuộc tính `before`, `beforeName`, `after` và `afterName` hoặc annotation ordering tương ứng.

Ordering ảnh hưởng thứ tự áp dụng configuration và thời điểm các condition theo bean có thể quan sát definitions. Nó không điều khiển thứ tự tạo instance độc lập với dependency graph.

## 13. Chẩn đoán khi auto-configuration không được phát hiện

Nếu ứng dụng thêm starter nhưng bean mặc định không xuất hiện, hãy kiểm tra theo từng lớp vấn đề.

### 13.1. Kiểm tra file đăng ký có nằm trong JAR không

Đầu tiên xem artifact của thư viện:

```bash
jar --list --file acme-storage-spring-boot-autoconfigure.jar
```

Phải thấy resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nếu dùng Boot cũ và vẫn cần hỗ trợ `spring.factories`, kiểm tra cả:

```text
META-INF/spring.factories
```

### 13.2. Kiểm tra tên class trong imports

Mỗi dòng phải là fully qualified name hợp lệ. Các lỗi thường gặp:

- Sai package.
- Sai chữ hoa/chữ thường.
- Đổi tên class nhưng quên cập nhật file imports.
- Ghi thêm `.class`.
- Dùng dấu `/` thay vì dấu `.` giữa package.
- Class không có trong runtime artifact.
- Class là nested class nhưng dùng sai ký hiệu `$`.

### 13.3. Kiểm tra đúng version Spring Boot

Một thư viện chỉ có `spring.factories` key EnableAutoConfiguration:

- Có thể chạy trên Boot 2.6.
- Vẫn có thể chạy trên Boot 2.7 do hỗ trợ tương thích.
- Không đăng ký auto-configuration trên Boot 3.0+.

Nếu ứng dụng chạy Boot 3 mà bean không xuất hiện, hãy kiểm tra file imports trước khi điều chỉnh các condition khác.

### 13.4. Kiểm tra condition report

Chạy ứng dụng với `--debug`:

```bash
java -jar application.jar --debug
```

Condition Evaluation Report có thể cho biết auto-configuration được phát hiện nhưng condition không khớp.

Cần phân biệt:

```text
Không tìm thấy auto-configuration candidate
          │
          └── Kiểm tra imports resource, classpath, version

Tìm thấy candidate nhưng condition không khớp
          │
          └── Kiểm tra classpath, property, bean, profile

Condition khớp nhưng bean không được tạo
          │
          └── Kiểm tra dependency, bean definition, initialization
```

Không nên kết luận file imports sai chỉ vì bean không có. Có thể auto-configuration đã được phát hiện nhưng `@ConditionalOnProperty` hoặc `@ConditionalOnMissingBean` dẫn đến kết quả khác dự kiến.

### 13.5. Kiểm tra exclusions

Ứng dụng có thể loại trừ auto-configuration qua:

```java
@SpringBootApplication(
        exclude = MailAutoConfiguration.class
)
public class Application {
}
```

Hoặc cấu hình:

```yaml
spring:
  autoconfigure:
    exclude:
      - com.example.mail.autoconfigure.MailAutoConfiguration
```

Nếu class có trong imports nhưng bị exclude, nó vẫn không được áp dụng. Hãy kiểm tra danh sách exclusions trong source code, properties và report.

## 14. Test auto-configuration đúng cách

Một thư viện starter nên kiểm tra rằng auto-configuration được khám phá từ resource và các condition hoạt động như mong đợi.

Spring Boot cung cấp `ApplicationContextRunner` để test một configuration nhỏ mà không cần khởi động toàn bộ ứng dụng web.

Ví dụ:

```java
class MailAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(MailAutoConfiguration.class)
                    );

    @Test
    void createsMailClientWhenEnabled() {
        contextRunner
                .withPropertyValues("acme.mail.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(MailClient.class);
                });
    }
}
```

Ví dụ minh họa test condition của auto-configuration. Cần có dependency test tương ứng và import các class cần thiết.

### 14.1. Test class có được xử lý không?

`ApplicationContextRunner` với `AutoConfigurations.of(...)` giúp kiểm tra nội dung cấu hình được chỉ định. Tuy nhiên, test này **không nhất thiết xác nhận file AutoConfiguration.imports trong JAR được đóng gói đúng** vì class đã được chỉ định trực tiếp trong test.

Muốn kiểm tra discovery từ artifact, cần có kiểm thử hoặc ứng dụng mẫu thực sự tiêu thụ thư viện như một dependency, rồi khởi tạo Spring Boot theo cơ chế bình thường.

### 14.2. Các trường hợp nên kiểm tra

- Dependency optional có mặt và không có.
- Property bật, tắt và không khai báo.
- Người dùng tự cung cấp bean để thay default.
- Có nhiều bean cùng type.
- Auto-configuration bị exclude.
- Các auto-configuration ordering cần thiết.
- File imports có trong JAR phát hành.
- Shaded/uber JAR giữ đầy đủ danh sách resource.

Test condition và test packaging trả lời hai câu hỏi khác nhau. Một test context pass không bảo đảm resource registration trong artifact phát hành không bị mất.

## 15. Những lỗi thường gặp khi chuyển đổi

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Boot 3 không tìm thấy auto-configuration | Chỉ đăng ký bằng key EnableAutoConfiguration trong `spring.factories` | Chuyển class sang `AutoConfiguration.imports` |
| Boot 2.6 không tìm thấy auto-configuration sau migration | Đã xóa entry `spring.factories` nhưng version cũ chưa hỗ trợ imports | Giữ entry cũ nếu còn hỗ trợ Boot 2.6 trở xuống |
| Boot 2.7 chạy được dù có hai file | Boot 2.7 hỗ trợ cả hai vị trí và deduplicate | Đây là hành vi tương thích được thiết kế |
| Boot 3 vẫn không tạo bean dù file imports có class | Condition không khớp hoặc class không load được | Xem Condition Evaluation Report và runtime classpath |
| Auto-configuration biến mất sau tạo shaded JAR | Resource cùng đường dẫn bị ghi đè thay vì append | Cấu hình resource transformer/append |
| Một thư viện khác vẫn cần `spring.factories` | Xóa toàn bộ file khi migration | Giữ các key còn được hỗ trợ |
| Đăng ký class nhưng cấu hình không được áp dụng | Class có trong imports nhưng bị exclude hoặc condition false | Kiểm tra exclusions và conditions |
| Auto-configuration bị đăng ký hai lần | Đăng ký cả hai file trên Boot 2.7 nhưng class khác biệt hoặc cơ chế merge không như dự kiến | Kiểm tra cùng FQCN, nội dung resource và report |
| Lỗi class không tồn tại khi chạy Boot cũ | Source tham chiếu API/annotation chỉ có ở Boot mới | Kiểm tra baseline version và compatibility |
| Test pass nhưng starter phát hành không hoạt động | Test import class trực tiếp, không kiểm tra file trong artifact | Thêm integration test tiêu thụ JAR thật |

### 15.1. Không nhầm lỗi discovery với lỗi condition

Nếu Boot 3 không phát hiện class vì file imports thiếu, condition chưa phải nguyên nhân. Nếu Boot đã phát hiện class nhưng `@ConditionalOnClass` không khớp, đổi file imports không giải quyết được.

Chẩn đoán theo thứ tự:

1. Class có trong artifact không?
2. File đăng ký có đúng path và nội dung không?
3. Phiên bản Boot có hỗ trợ cơ chế đăng ký đó không?
4. Auto-configuration có bị exclude không?
5. Các condition có khớp không?
6. Bean definitions và dependency có hợp lệ không?

## 16. Hướng dẫn migration theo từng tình huống

### Tình huống A — Thư viện chỉ hỗ trợ Boot 3.x

Dùng:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Đánh dấu class bằng `@AutoConfiguration` và không dùng key EnableAutoConfiguration trong `spring.factories` để đăng ký auto-configuration.

Nếu thư viện vẫn cần `ApplicationListener` hoặc `EnvironmentPostProcessor`, giữ file `spring.factories` cho các key đó.

### Tình huống B — Thư viện hỗ trợ Boot 2.7 và 3.x

Có thể đăng ký cùng class ở cả hai file trong giai đoạn chuyển tiếp:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.lib.autoconfigure.LibAutoConfiguration
```

và:

```text
com.example.lib.autoconfigure.LibAutoConfiguration
```

Boot 2.7 đọc cả hai và khử trùng lặp; Boot 3 dùng file imports. Hãy kiểm thử trên các version Boot thực sự được hỗ trợ.

### Tình huống C — Thư viện vẫn hỗ trợ Boot 2.6 hoặc thấp hơn

Giữ `spring.factories` entry vì các version đó chưa hỗ trợ cơ chế imports mới. Có thể đồng thời đóng gói file imports để các version mới sử dụng.

Cần kiểm tra annotation/API trong auto-configuration class tương thích với phiên bản thấp nhất. `@AutoConfiguration` xuất hiện từ Boot 2.7; nếu artifact còn phải chạy với Boot cũ hơn, đừng giả định annotation mới tồn tại trên runtime classpath của chúng.

### Tình huống D — Thư viện có nhiều extension point trong spring.factories

Ví dụ file cũ:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.example.lib.autoconfigure.LibAutoConfiguration

org.springframework.context.ApplicationListener=\
com.example.lib.bootstrap.LibListener

org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.lib.bootstrap.LibEnvironmentPostProcessor
```

Sau migration, tách riêng phần auto-configuration:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.example.lib.autoconfigure.LibAutoConfiguration
```

Giữ `spring.factories` với các key còn dùng:

```properties
org.springframework.context.ApplicationListener=\
com.example.lib.bootstrap.LibListener

org.springframework.boot.env.EnvironmentPostProcessor=\
com.example.lib.bootstrap.LibEnvironmentPostProcessor
```

Đây là cách migration có chủ đích: chuyển đúng một extension point, không xóa cơ chế factories cho những extension point khác.

## 17. Phân biệt các loại file metadata trong Spring Boot

Trong thư mục `META-INF` có thể có nhiều file với tên và mục đích khác nhau.

| File | Mục đích |
|---|---|
| `META-INF/spring.factories` | Đăng ký nhiều loại factory/extension point; trước Boot 3 còn chứa key EnableAutoConfiguration |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Đăng ký auto-configuration class |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements` | Khai báo quan hệ thay thế giữa auto-configuration class cũ và mới trong các trường hợp migration |
| `META-INF/spring-autoconfigure-metadata.properties` | Metadata được annotation processor tạo để lọc nhanh một số auto-configuration condition và cải thiện startup |
| `META-INF/spring-configuration-metadata.json` | Metadata hỗ trợ IDE/documentation cho configuration properties |
| `META-INF/spring/<test-slice-annotation>.imports` | Đăng ký configuration cho test slice theo cơ chế tương ứng |

Không nên dùng nhầm `spring-autoconfigure-metadata.properties` làm file đăng ký auto-configuration. Nó là metadata tối ưu việc lọc điều kiện, còn `AutoConfiguration.imports` mới liệt kê các candidate class.

## 18. Quan hệ giữa imports, conditions và auto-configuration metadata

Một auto-configuration class có thể xuất hiện trong imports nhưng chưa chắc được áp dụng.

Luồng khái niệm:

```text
AutoConfiguration.imports
          │
          ▼
Danh sách candidate auto-configuration
          │
          ▼
Exclusions và ordering
          │
          ▼
Condition evaluation
  ├── classpath
  ├── property
  ├── bean registry
  ├── web application
  └── các điều kiện khác
          │
          ▼
Bean definitions được đăng ký
          │
          ▼
Bean instances được tạo
```

Spring Boot còn có thể tạo `spring-autoconfigure-metadata.properties` qua annotation processor để lọc sớm một số auto-configuration không thể khớp. Điều này giúp giảm công việc xử lý ở startup.

Metadata tối ưu không thay thế file imports. Hai file phục vụ hai giai đoạn khác nhau:

- Imports trả lời: **những auto-configuration nào là candidate?**
- Auto-configuration metadata hỗ trợ trả lời sớm: **candidate nào có thể bị loại dựa trên condition metadata?**

Không cần tự viết file metadata tối ưu trong đa số dự án. Khi xây dựng thư viện auto-configuration, hãy cấu hình annotation processor theo tài liệu của Spring Boot nếu muốn tạo metadata phục vụ startup optimization và IDE assistance.

## 19. Quy trình kiểm tra một thư viện sau migration

Khi chuyển từ spring.factories sang AutoConfiguration.imports, có thể thực hiện theo trình tự sau:

### Bước 1 — Liệt kê các key đang có

Mở `META-INF/spring.factories` và ghi nhận từng key. Chỉ key `EnableAutoConfiguration` được chuyển sang cơ chế auto-configuration imports theo thay đổi Boot 3.0.

Các key như `ApplicationListener`, `ApplicationContextInitializer`, `EnvironmentPostProcessor` và `FailureAnalyzer` cần được giữ nếu thư viện vẫn dùng.

### Bước 2 — Tạo imports resource đúng đường dẫn

Tạo:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Mỗi dòng là một fully qualified class name.

### Bước 3 — Cập nhật annotation auto-configuration

Với baseline Boot 2.7 trở lên, dùng `@AutoConfiguration` cho top-level auto-configuration classes. Giữ `@Configuration` cho các cấu hình con được import hoặc lồng bên trong theo cách thông thường.

### Bước 4 — Chọn chiến lược tương thích

Nếu hỗ trợ Boot 2.6 hoặc thấp hơn, giữ entry cũ trong `spring.factories`. Nếu chỉ hỗ trợ Boot 3, dùng imports làm cơ chế đăng ký auto-configuration chính.

### Bước 5 — Kiểm tra artifact

Dùng `jar --list` và công cụ xem nội dung JAR để xác nhận imports file có mặt, đúng tên, đúng đường dẫn và chứa đủ class.

### Bước 6 — Kiểm tra resource merge

Nếu tạo shaded/uber JAR, cấu hình append các imports resource và kiểm tra file kết quả sau khi merge.

### Bước 7 — Chạy ứng dụng tiêu thụ starter

Tạo một ứng dụng nhỏ chỉ khai báo dependency starter. Không import auto-configuration bằng tay. Khởi động context và xác nhận bean xuất hiện theo điều kiện dự kiến.

### Bước 8 — Kiểm tra nhiều version Boot

Nếu thư viện cam kết hỗ trợ nhiều dòng, chạy integration test trên từng dòng được hỗ trợ. Đừng suy luận tương thích chỉ từ việc compile thành công trên một version.

## 20. Bài thực hành

### Bài 1 — Đọc file spring.factories cũ

Tạo file `META-INF/spring.factories` với key `EnableAutoConfiguration` và một auto-configuration class. Chạy project với Spring Boot 2.6 hoặc phiên bản tương thích để quan sát class được phát hiện.

### Bài 2 — Chuyển sang imports

Tạo `AutoConfiguration.imports` với cùng fully qualified class name. Chạy trên Boot 2.7. Đặt class trong cả hai file để quan sát cơ chế tương thích và khử trùng lặp.

### Bài 3 — Thử Boot 3

Chạy cùng thư viện trên Boot 3.x. Tạm bỏ file imports nhưng giữ key cũ trong `spring.factories`. Quan sát auto-configuration không còn được đăng ký qua key đó. Khôi phục imports và chạy lại.

### Bài 4 — Giữ extension point khác

Thêm một `ApplicationListener` hoặc `EnvironmentPostProcessor` vào `spring.factories`. Sau migration, xác nhận extension point đó vẫn hoạt động trong khi auto-configuration đã chuyển sang imports.

### Bài 5 — Kiểm tra custom bean back-off

Tạo auto-configuration có `@ConditionalOnMissingBean`. Chạy một lần không có custom bean, một lần có custom bean. Quan sát khi nào default bean được đăng ký.

### Bài 6 — Thử resource merge

Tạo hai thư viện thử nghiệm, mỗi thư viện có một imports file cùng đường dẫn nhưng liệt kê class khác nhau. Tạo shaded JAR mà không append resource, sau đó cấu hình append. So sánh nội dung cuối để thấy vì sao resource merge quan trọng.

### Bài 7 — Phân loại file META-INF

Cho một thư viện có `spring.factories`, `AutoConfiguration.imports`, `spring-autoconfigure-metadata.properties` và `spring-configuration-metadata.json`. Giải thích mục đích từng file và giai đoạn sử dụng.

### Bài 8 — Kiểm tra ma trận tương thích

Tạo ứng dụng tiêu thụ starter trên các version Boot mà thư viện cam kết hỗ trợ. Xác nhận:

- Auto-configuration được phát hiện.
- Các extension point khác vẫn được nạp.
- Conditions hoạt động đúng.
- Bean tùy chỉnh có thể thay thế bean mặc định.
- Artifact cuối giữ đầy đủ metadata resource.

## 21. Tài liệu tham khảo chính thức

- [Spring Boot 2.7 Release Notes — Auto-configuration Registration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes): file `AutoConfiguration.imports` được giới thiệu, hỗ trợ tương thích với `spring.factories` và việc khử trùng lặp.
- [Spring Boot 3.0 Migration Guide — Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): bỏ hỗ trợ key `EnableAutoConfiguration` trong `spring.factories`; các key khác không bị ảnh hưởng.
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): đường dẫn, định dạng imports, ordering và các quy ước viết auto-configuration.
- [Spring Boot Reference — Application Events and Listeners](https://docs.spring.io/spring-boot/reference/features/spring-application.html): đăng ký listener qua `spring.factories`.
- [Spring Boot How-to — Customize the Environment or ApplicationContext Before It Starts](https://docs.spring.io/spring-boot/how-to/application.html): đăng ký `ApplicationContextInitializer` và `EnvironmentPostProcessor`.

Điểm cốt lõi của lịch sử chuyển đổi là: **`spring.factories` từng là nơi đăng ký auto-configuration, Boot 2.7 giới thiệu file imports chuyên biệt và duy trì tương thích, còn Boot 3.0 chuyển hẳn việc đăng ký auto-configuration sang `AutoConfiguration.imports`.** Các extension point khác vẫn có thể dùng `spring.factories`. Khi nâng cấp hoặc phát hành starter, hãy kiểm tra key cụ thể, version Boot được hỗ trợ và cách đóng gói resource để tránh mất cấu hình tự động.
