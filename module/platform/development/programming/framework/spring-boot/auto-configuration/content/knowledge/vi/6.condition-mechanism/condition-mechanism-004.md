# Điều kiện ở cấp lớp và cấp phương thức tác động đến phạm vi đăng ký như thế nào?

## 1. Câu hỏi cốt lõi

Trong Spring Boot auto-configuration, một annotation điều kiện không chỉ quyết định **đúng/sai**, mà vị trí đặt annotation còn xác định **phạm vi cấu hình bị ảnh hưởng khi điều kiện không khớp**.

So sánh hai khai báo dưới đây:

~~~java
// Cách A: điều kiện ở cấp lớp
@AutoConfiguration
@ConditionalOnProperty(prefix = "demo", name = "enabled", havingValue = "true")
public class DemoAutoConfiguration {

    @Bean
    ServiceA serviceA() { /* ... */ return null; }

    @Bean
    ServiceB serviceB() { /* ... */ return null; }
}
~~~

~~~java
// Cách B: điều kiện trên đúng một phương thức @Bean
@AutoConfiguration
public class DemoAutoConfiguration {

    @Bean
    ServiceA serviceA() { /* ... */ return null; }

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "enabled", havingValue = "true")
    ServiceB serviceB() { /* ... */ return null; }
}
~~~

**Hai đoạn chỉ là sơ đồ minh họa, không phải chương trình chạy được**: chưa có type `ServiceA`/`ServiceB` thực tế, và `return null` không phải cách cung cấp service hoàn chỉnh.

Nếu `demo.enabled=false`:

- **Cách A:** cả lớp cấu hình không được áp dụng theo đường đăng ký thông thường; hai bean definitions `serviceA` và `serviceB` thuộc lớp này đều không được đăng ký.
- **Cách B:** lớp cấu hình vẫn có thể được xử lý; `serviceA` vẫn có thể được đăng ký, còn `serviceB` bị bỏ qua do điều kiện gắn trên phương thức.

Đó chính là khác biệt về **phạm vi đăng ký**. Đặt điều kiện ở cấp lớp khi toàn bộ cấu hình cùng phụ thuộc một tiền đề; đặt ở cấp phương thức khi chỉ một bean cần phụ thuộc tiền đề đó.

Bài học này thuộc nhóm **Cơ chế điều kiện** của Spring Boot auto-configuration. Trọng tâm là tác động đến các bean definitions trong context, không phải cơ chế bật/tắt phương thức Java tại runtime.

## 2. Phân biệt năm tầng trước khi tìm nguyên nhân

Khi điều tra một bean không xuất hiện, hãy tránh gộp những khái niệm sau:

| Tầng | Ý nghĩa | Khả năng gây nhầm |
| --- | --- | --- |
| **Ứng viên auto-configuration** | Spring Boot tìm được tên lớp thông qua metadata trong classpath. | Có ứng viên không có nghĩa mọi điều kiện đều khớp. |
| **Import/chọn cấu hình** | Lớp được đưa vào quá trình phân tích sau exclusions/filters và cơ chế xử lý import. | Có class được chọn vẫn có thể bị condition cấp lớp từ chối. |
| **Đánh giá điều kiện** | Spring kiểm tra `Condition` gắn vào lớp hoặc phương thức. | Một cấp điều kiện đúng chưa bảo đảm mọi cấp liên quan đều đúng. |
| **Đăng ký bean definition** | Spring lưu mô tả cách tạo bean trong `BeanFactory`. | Có definition khác với đã tạo instance. |
| **Khởi tạo bean instance** | Container tạo object theo scope/dependency/lifecycle. | Constructor lỗi hoặc lazy init không phải condition mismatch. |

`@AutoConfiguration` của Spring Boot là một dạng `@Configuration`. Boot cung cấp các annotation điều kiện như `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `@ConditionalOnWebApplication`, v.v.

Cơ chế nền là `@Conditional` của Spring Framework. Một condition có thể được áp dụng lên kiểu cấu hình hoặc một phương thức tạo bean. Các điều kiện của Spring Boot được viết để hỗ trợ việc đăng ký cấu hình tùy theo classpath, environment và các bean đã có.

Thông thường, một auto-configuration được công bố bởi thư viện tại:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Tệp này chứa tên đầy đủ của các lớp auto-configuration ứng viên. Đăng ký ứng viên **chưa bảo đảm** điều kiện lớp khớp, điều kiện phương thức khớp hoặc bean được tạo thành công.

## 3. Điều kiện ở cấp lớp: cổng chung của cấu hình

Xét cấu hình:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class FeatureAutoConfiguration {

    @Bean
    FeatureEngine engine() { /* ... */ return null; }

    @Bean
    FeatureRegistry registry() { /* ... */ return null; }
}
~~~

Đây là snippet minh họa phạm vi; các type chưa được định nghĩa. Annotation trên **`FeatureAutoConfiguration`** có nghĩa: chỉ xử lý nhánh cấu hình này khi `demo.feature.enabled` được phân giải thành `true`.

Với `matchIfMissing=false` (mặc định), khóa vắng mặt cũng làm điều kiện không khớp. Nếu lớp ngoài không khớp, **không có bean definitions `engine` và `registry` nào được khai báo qua lớp này**.

Sơ đồ:

~~~text
FeatureAutoConfiguration
  @ConditionalOnProperty(demo.feature.enabled=true)
          |
          +-- false / missing ----> bỏ qua nhánh cấu hình
          |                         |- engine: không đăng ký
          |                         '- registry: không đăng ký
          |
          '-- true --------------> xử lý các @Bean bên trong
                                     |- engine: còn xét điều kiện riêng
                                     '- registry: còn xét điều kiện riêng
~~~

Như vậy, điều kiện lớp **không đồng nghĩa tất cả bean của context bị xóa**. Nó chỉ quyết định việc áp dụng lớp cấu hình ấy theo nhánh đăng ký đang xét. Bean của ứng dụng, auto-configuration khác hoặc những đường import độc lập không tự nhiên bị xóa theo.

Đặc biệt, khi lớp cấu hình không khớp, đừng giải thích rằng Spring đã tạo các bean rồi “tắt” chúng. Trong đường xử lý thường gặp, bean definitions đó **không được đăng ký ngay từ đầu**.

### Khi nào nên đặt điều kiện cấp lớp?

- Cả cấu hình chỉ có ý nghĩa khi có một thư viện nền tảng trên classpath, ví dụ tích hợp A không thể hoạt động nếu thiếu API của A.
- Cả nhóm bean cùng là một tính năng có công tắc bật/tắt chung.
- Cấu hình chỉ có ý nghĩa trong ứng dụng servlet hoặc reactive tương ứng.
- Nếu tiền đề sai, **mọi bean thuộc lớp đó** đều không cần tồn tại.

Nếu chỉ một bean phụ thuộc property hoặc thư viện tùy chọn, điều kiện cấp lớp có thể **rộng quá mức**. Lúc đó nên chuyển xuống phương thức hoặc một cấu hình con có phạm vi hẹp hơn.

### @ConditionalOnProperty ở cấp lớp

Các trường hợp với `havingValue="true"` và `matchIfMissing=false`:

| Giá trị Environment tra được | Kết quả |
| --- | --- |
| `"true"` | Khớp. |
| `"false"` | Không khớp. |
| `"other"` | Không khớp. |
| Không có khóa | Không khớp. |

Nếu `matchIfMissing=true`, khóa vắng có thể được coi là khớp. Nếu bỏ `havingValue`, `@ConditionalOnProperty` có quy tắc mặc định là khóa tồn tại với giá trị **không bằng `false`**; đừng mặc định quy tắc này giống boolean strict. Spring Boot 3.5 còn có `@ConditionalOnBooleanProperty` khi muốn diễn đạt rõ thuộc tính boolean.

Một khóa có thể xuất hiện trong file `application.properties` nhưng bị nguồn ưu tiên cao hơn ghi đè; condition kiểm tra giá trị đã được phân giải từ `Environment` tại lúc đánh giá, không đọc duy nhất một file.

## 4. Điều kiện ở phương thức @Bean: cổng của một định nghĩa bean

Xét:

~~~java
@AutoConfiguration
public class FeatureAutoConfiguration {

    @Bean
    FeatureEngine engine() { /* ... */ return null; }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "report-enabled",
            havingValue = "true"
    )
    ReportService reportService() { /* ... */ return null; }
}
~~~

Đây cũng là snippet minh họa, chưa tự chạy. Không có điều kiện lớp ngoài nên `engine()` có thể được đăng ký như thông thường. `reportService()` được đăng ký **chỉ khi** property `demo.report-enabled=true`; property sai không làm `engine()` bị bỏ qua.

~~~text
FeatureAutoConfiguration (được xử lý)
       |
       +-- @Bean engine() ----------> đăng ký nếu không có cổng khác ngăn
       |
       '-- @Bean reportService()
              @ConditionalOnProperty
                    |
                    +-- false -----> chỉ reportService không đăng ký
                    '-- true ------> reportService có thể đăng ký
~~~

Lưu ý “có thể đăng ký” là cách diễn đạt chính xác: việc một condition khớp không chứng minh không có các ràng buộc khác, lỗi cấu hình hoặc vấn đề ở bước tạo instance.

### Vì sao scope của điều kiện phương thức quan trọng?

Một auto-configuration thường cung cấp nhiều bean liên quan nhưng không đồng nhất về điều kiện:

- `CoreService` có thể hoạt động cả trong ứng dụng CLI.
- `HttpAdapter` chỉ cần khi bật integration HTTP.
- `MetricsReporter` chỉ cần khi bật metrics.
- `DefaultNotifier` chỉ cần khi người dùng chưa tự khai báo `Notifier`.

Nếu đặt cả ba điều kiện tùy chọn ở lớp ngoài, một tính năng phụ bị tắt có thể làm biến mất cả core service. Đặt chúng lên từng bean method hoặc phân nhóm qua các lớp cấu hình lồng là thiết kế dễ thay đổi hơn.

## 5. Điều kiện ở lớp và phương thức kết hợp thế nào?

Điều kiện trên đường từ lớp cấu hình tới bean hoạt động như **các cổng cùng cần mở**. Với một bean có condition ở cả class và method, điều kiện phương thức không thể “cứu” bean khi điều kiện lớp đã loại cấu hình:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "demo", name = "auto", havingValue = "true")
public class FeatureAutoConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "reports", havingValue = "true")
    ReportService reportService() { /* ... */ return null; }
}
~~~

Điều kiện logic để bean xuất hiện theo nhánh này là:

~~~text
autoConfiguration được phát hiện / không bị exclude
  AND demo.auto = true
  AND demo.reports = true
  AND mọi điều kiện liên quan khác khớp
  THEN reportService có thể được đăng ký
~~~

Bảng minh họa đúng phạm vi:

| `demo.auto` | `demo.reports` | Lớp ngoài | `reportService` |
| --- | --- | --- | --- |
| `true` | `true` | Qua cổng | Có thể đăng ký |
| `true` | `false` | Qua cổng | Bị bỏ qua |
| `false` | `true` | Bị bỏ qua | Bị bỏ qua cùng lớp ngoài |
| `false` | `false` | Bị bỏ qua | Bị bỏ qua |
| Vắng | `true` | Không khớp với mặc định `matchIfMissing=false` | Bị bỏ qua |

Bảng không có nghĩa Spring chắc chắn gọi condition phương thức khi điều kiện lớp đã từ chối. Trong một nhánh cấu hình bị bỏ qua, việc đánh giá sâu hơn có thể không diễn ra. Đây là **mô hình kết quả**, không phải danh sách callback phải chạy.

### Nhiều conditions trên cùng một vị trí

Ví dụ:

~~~java
@Bean
@ConditionalOnProperty(prefix = "demo", name = "audit", havingValue = "true")
@ConditionalOnMissingBean(AuditService.class)
AuditService auditService() { /* ... */ return null; }
~~~

Đây là snippet; class `AuditService` chưa khai báo. Bean chỉ có thể được đăng ký khi **property cho phép và chưa có bean phù hợp**. Nhiều điều kiện tại cùng vị trí thường cần **đồng thời khớp**, không phải quan hệ OR.

Nếu muốn “A hoặc B”, không thể mặc định rằng đặt hai annotation điều kiện sẽ tạo OR. Cần cấu trúc các nhánh cấu hình hoặc tự viết `Condition` cho logic mong muốn.

## 6. @ConditionalOnMissingBean đặt ở cấp nào?

Một trường hợp rất quan trọng với auto-configuration là **back-off**: thư viện cung cấp mặc định, nhưng ứng dụng được phép thay bean của thư viện.

Giả sử một auto-configuration có cả `NotificationService` mặc định và `AuditRegistry`. Nếu đặt:

~~~java
@AutoConfiguration
@ConditionalOnMissingBean(NotificationService.class)
public class NotificationAutoConfiguration {

    @Bean
    NotificationService defaultNotificationService() { /* ... */ return null; }

    @Bean
    AuditRegistry auditRegistry() { /* ... */ return null; }
}
~~~

thì khi ứng dụng tự khai báo `NotificationService`, condition **trên class** không khớp. Theo đường xử lý này, **cả `defaultNotificationService` và `auditRegistry`** bị ảnh hưởng. Đây có thể là hiệu ứng phụ không mong muốn nếu registry nên tồn tại dù notifier đã được thay thế.

Nếu điều kiện chỉ nhằm thay riêng notifier, hãy chuyển xuống method:

~~~java
@AutoConfiguration
public class NotificationAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationService.class)
    NotificationService defaultNotificationService() { /* ... */ return null; }

    @Bean
    AuditRegistry auditRegistry() { /* ... */ return null; }
}
~~~

Khi ứng dụng có `NotificationService` của riêng mình, **bean mặc định** lùi bước, còn `auditRegistry` vẫn có thể được đăng ký. Đây là cách đặt condition hợp với yêu cầu “chỉ bỏ qua một default bean”.

**Chi tiết cần hiểu đúng:** theo tài liệu Spring Boot, đối với bean conditions như `@ConditionalOnMissingBean`, việc đặt condition ở cấp class không có nghĩa condition dùng một bộ quy tắc tìm bean hoàn toàn khác method level; một khác biệt quan trọng là **class condition có thể ngăn đăng ký chính configuration class nếu không khớp**, trong khi method condition chỉ bỏ bean tương ứng.

### Tại sao @ConditionalOnMissingBean cần lưu ý thời điểm?

`@ConditionalOnBean` và `@ConditionalOnMissingBean` xem những bean definitions đã được xử lý tới thời điểm điều kiện chạy, không nhìn trước tất cả definitions sẽ xuất hiện về sau. Spring Boot trì hoãn import auto-configuration để các định nghĩa bean của ứng dụng thông thường có cơ hội được xử lý trước; vì thế những bean conditions này phù hợp nhất trong auto-configuration.

Để condition theo type đáng tin cậy, khai báo return type rõ ràng cho `@Bean`. Với Spring Boot 3.5, điều kiện bean có thể tính tới thông tin generic ở method return type; nếu bạn muốn kiểm tra toàn bộ bean thuộc một raw type, có thể chỉ rõ type trong annotation, ví dụ `@ConditionalOnMissingBean(Converter.class)`, thay vì phụ thuộc generic inference.

Đừng viết một `@Bean Object notifier()` rồi mong mọi điều kiện theo `NotificationService` tự hiểu chính xác kiểu runtime của object trong mọi pha.

## 7. @ConditionalOnClass: vì sao đặt ở class đôi khi còn ảnh hưởng class loading?

Spring Boot hỗ trợ `@ConditionalOnClass` để chỉ dùng cấu hình khi class thư viện có sẵn trên classpath. Khi đặt trực tiếp lên `@Configuration` class, framework có thể đọc annotation metadata bằng ASM trước khi phải tải class cấu hình, nhờ đó bảo vệ nhánh cấu hình có optional dependency.

Nhưng trường hợp sau có nguy cơ:

~~~java
@Bean
@ConditionalOnClass(name = "com.vendor.sdk.Client")
com.vendor.sdk.Client client() {
    return new com.vendor.sdk.Client();
}
~~~

**Đây là ví dụ minh họa, không biên dịch nếu chưa có SDK tại compile-time.** Dù method có `@ConditionalOnClass`, JVM có thể phải đọc signature của method có return type `Client` trước khi điều kiện được đánh giá. Nếu dependency optional vắng ở runtime, vấn đề class loading có thể xuất hiện.

Một mẫu an toàn hơn cho auto-configuration:

~~~java
@AutoConfiguration
public class VendorAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.Client")
    static class ClientConfiguration {

        @Bean
        com.vendor.sdk.Client client() {
            return new com.vendor.sdk.Client();
        }
    }
}
~~~

Đây là **mẫu kiến trúc chưa runnable** nếu không có SDK; các import annotation cũng được rút gọn. Lớp `ClientConfiguration` chỉ được xử lý khi class điều kiện có sẵn, tách method signature phụ thuộc SDK ra khỏi phần còn lại của auto-configuration. Trong dự án thật, SDK có thể có ở compile-time của module tự cấu hình nhưng là optional dependency tại runtime của ứng dụng.

**Không suy ra mọi @ConditionalOnClass trên method đều vô dụng.** Cảnh báo cụ thể liên quan đặc biệt tới trường hợp method signature nhắc tới class optional có thể vắng.

### Lớp lồng là cấp trung gian

Ngoài hai cấp class và method, Spring hỗ trợ `static nested @Configuration` để gom một nhánh bean:

~~~text
Outer @AutoConfiguration
    |- CoreService (bean cấp outer)
    '- Nested @Configuration, @ConditionalOnClass(optional SDK)
         |- OptionalClient
         '- OptionalAdapter
~~~

Ở đây `@ConditionalOnClass` của nested class chặn cả nhóm hai bean tích hợp SDK, nhưng **không chặn CoreService** thuộc outer. Tức nested class là một cách chọn **scope trung gian**, giúp tránh condition ngoài quá rộng và lặp condition từng method.

Tuy nhiên, nếu nested class bị import độc lập hoặc nằm trong vùng component scan theo một đường khác, đừng giả định mọi condition ngoài luôn bao phủ nó như khi nested class chỉ được xử lý qua outer configuration.

## 8. Ví dụ Maven/Java 17+ chạy được: quan sát phạm vi cấp lớp và cấp @Bean

Để nhìn thấy khác biệt không phải bằng lý thuyết, ta tạo một ứng dụng Spring Boot đơn giản gồm:

- Một lớp `@AutoConfiguration` có **cổng chung** `demo.auto.enabled`. Mặc định cổng mở khi property vắng.
- Một bean `CoreService` không có điều kiện method riêng.
- Một bean `ReportService` chỉ được đăng ký khi `demo.report.enabled=true`.
- Một bean `HttpMarker` chỉ được đăng ký khi `demo.http.enabled=true`. Tên “HttpMarker” chỉ là chuỗi minh họa, **không tạo HTTP server**.
- Một bean `Notifier` mặc định dùng `@ConditionalOnMissingBean` tại method. Ứng dụng có thể thay nó bằng bean custom riêng.
- Một `ApplicationRunner` kiểm tra type nào thực sự có trong context.

Ví dụ dùng **Spring Boot 3.5.0, Java 17+ và Maven**, không cần database, web dependency hoặc external server.

### 8.1. Cấu trúc thư mục

~~~text
conditional-scope-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/
    │   │   ├── CoreService.java
    │   │   ├── ReportService.java
    │   │   ├── HttpMarker.java
    │   │   └── Notifier.java
    │   ├── app/DemoApplication.java
    │   └── autoconfig/ScopeAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Package của ứng dụng là `com.example.app`; package của auto-configuration là `com.example.autoconfig`. Đây là các package ngang hàng, nên component scan mặc định của ứng dụng không tự quét auto-configuration. Boot nhận lớp qua imports metadata đúng mục đích.

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>conditional-scope-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.3. Bốn interface

Tệp `src/main/java/com/example/api/CoreService.java`:

~~~java
package com.example.api;

public interface CoreService {
    String value();
}
~~~

Tệp `src/main/java/com/example/api/ReportService.java`:

~~~java
package com.example.api;

public interface ReportService {
    String value();
}
~~~

Tệp `src/main/java/com/example/api/HttpMarker.java`:

~~~java
package com.example.api;

public interface HttpMarker {
    String value();
}
~~~

Tệp `src/main/java/com/example/api/Notifier.java`:

~~~java
package com.example.api;

public interface Notifier {
    String value();
}
~~~

Các interface đơn giản giúp xác định rõ type cho bean conditions và `ObjectProvider`. Chỉ khai báo type trong classpath không có nghĩa Spring đã tạo bean cùng type.

### 8.4. ScopeAutoConfiguration.java

Tệp `src/main/java/com/example/autoconfig/ScopeAutoConfiguration.java`:

~~~java
package com.example.autoconfig;

import com.example.api.CoreService;
import com.example.api.ReportService;
import com.example.api.HttpMarker;
import com.example.api.Notifier;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.auto",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class ScopeAutoConfiguration {

    @Bean
    CoreService coreService() {
        return () -> "CORE";
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "enabled",
            havingValue = "true"
    )
    ReportService reportService() {
        return () -> "REPORT";
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.http",
            name = "enabled",
            havingValue = "true"
    )
    HttpMarker httpMarker() {
        return () -> "HTTP";
    }

    @Bean
    @ConditionalOnMissingBean(Notifier.class)
    Notifier defaultNotifier() {
        return () -> "DEFAULT";
    }
}
~~~

Phạm vi:

- **`demo.auto.enabled` ở class:** chặn tất cả các bean khai báo từ `ScopeAutoConfiguration` khi nhận `false`. Nếu property vắng, `matchIfMissing=true` cho phép class.
- **`demo.report.enabled` trên method:** chỉ chặn `reportService()`; core, marker và notifier không vì thế bị chặn.
- **`demo.http.enabled` trên method:** chỉ chặn `httpMarker()`; không phụ thuộc bản thân `demo.report.enabled`.
- **`@ConditionalOnMissingBean(Notifier.class)` trên method:** chỉ chặn default notifier nếu đã có bean `Notifier` phù hợp. Không làm biến mất `CoreService` hay `ReportService`.

Cả `ReportService` và `HttpMarker` ở đây đều là interface giả lập chức năng, không đòi hỏi classpath web nào.

### 8.5. AutoConfiguration.imports

Tạo tệp đúng đường dẫn:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung một dòng:

~~~text
com.example.autoconfig.ScopeAutoConfiguration
~~~

Tệp này giúp Boot khám phá lớp auto-configuration ứng viên. Nếu thiếu tệp hoặc sai FQCN, kết quả không có bean mặc định có thể do **không phát hiện cấu hình**, khác với việc điều kiện cấp lớp hay cấp method không khớp.

### 8.6. DemoApplication.java

Tệp `src/main/java/com/example/app/DemoApplication.java`:

~~~java
package com.example.app;

import com.example.api.CoreService;
import com.example.api.ReportService;
import com.example.api.HttpMarker;
import com.example.api.Notifier;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.custom",
            name = "enabled",
            havingValue = "true"
    )
    Notifier customNotifier() {
        return () -> "CUSTOM";
    }

    @Bean
    ApplicationRunner printBeans(
            ObjectProvider<CoreService> coreProvider,
            ObjectProvider<ReportService> reportProvider,
            ObjectProvider<HttpMarker> httpProvider,
            ObjectProvider<Notifier> notifierProvider) {

        return args -> {
            CoreService core = coreProvider.getIfAvailable();
            ReportService report = reportProvider.getIfAvailable();
            HttpMarker http = httpProvider.getIfAvailable();
            Notifier notifier = notifierProvider.getIfAvailable();

            System.out.println("core="
                    + (core == null ? "ABSENT" : core.value()));
            System.out.println("report="
                    + (report == null ? "ABSENT" : report.value()));
            System.out.println("http="
                    + (http == null ? "ABSENT" : http.value()));
            System.out.println("notifier="
                    + (notifier == null ? "ABSENT" : notifier.value()));
        };
    }
}
~~~

Vì ứng dụng có một `Notifier` custom trong cấu hình người dùng, `@ConditionalOnMissingBean` trên auto-configuration có thể back off. `ObjectProvider#getIfAvailable()` cho phép in `ABSENT` nếu type không có bean. Với đúng các trường hợp của ví dụ, mỗi type có tối đa một bean; nếu cố tình thêm nhiều bean cùng type mà không có một primary/candidate duy nhất, có thể gặp lỗi ambiguity.

### 8.7. application.properties

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Đặt tại `src/main/resources/application.properties`. Ta không khai báo bốn công tắc `demo.*.enabled` trong file, để có thể thay đổi chúng qua command-line. Các dòng log không thuộc chương trình có thể khác theo môi trường; phần stdout trình bày dưới đây là bốn dòng do `printBeans` tự in.

### 8.8. Build và thử từng tình huống

Cài Java 17+ và Maven. Từ thư mục `conditional-scope-demo`:

~~~bash
mvn -q -DskipTests package
java -jar target/conditional-scope-demo-1.0.0.jar
~~~

Bốn dòng chương trình in:

~~~text
core=CORE
report=ABSENT
http=ABSENT
notifier=DEFAULT
~~~

Lý do: class condition `demo.auto.enabled` cho phép vắng property; `coreService()` không có điều kiện riêng; hai method report/http chưa được bật; chưa có custom notifier nên default notifier được đăng ký.

**Tình huống 2 — chỉ bật report:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.report.enabled=true
~~~

~~~text
core=CORE
report=REPORT
http=ABSENT
notifier=DEFAULT
~~~

Bật report không làm đổi bean HTTP hay notifier. Đây là bằng chứng trực tiếp của **scope cấp phương thức**.

**Tình huống 3 — chỉ bật marker HTTP:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.http.enabled=true
~~~

~~~text
core=CORE
report=ABSENT
http=HTTP
notifier=DEFAULT
~~~

Chức năng marker được điều khiển riêng biệt với report. Không có HTTP server thật, nên thử nghiệm không yêu cầu port hoặc web dependencies.

**Tình huống 4 — bật cả hai method:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.report.enabled=true --demo.http.enabled=true
~~~

~~~text
core=CORE
report=REPORT
http=HTTP
notifier=DEFAULT
~~~

**Tình huống 5 — tắt condition cấp class, dù các method đều bật:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.auto.enabled=false --demo.report.enabled=true --demo.http.enabled=true
~~~

~~~text
core=ABSENT
report=ABSENT
http=ABSENT
notifier=ABSENT
~~~

Lớp ngoài không được áp dụng, nên không bean nào được cung cấp **qua lớp auto-configuration này**. Hai method conditions nhận `true` cũng không làm bean “vượt” qua condition cấp class.

**Tình huống 6 — ứng dụng thay riêng notifier mặc định:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.custom.enabled=true --demo.report.enabled=true
~~~

~~~text
core=CORE
report=REPORT
http=ABSENT
notifier=CUSTOM
~~~

Bean custom của ứng dụng làm `@ConditionalOnMissingBean(Notifier.class)` không khớp, nhưng `CoreService` và `ReportService` vẫn hoạt động. Nếu condition missing bean bị đặt lên **class ngoài** thay vì method, kết quả có thể loại cả core/report — trái với mục đích cho phép chỉ thay notifier.

**Tình huống 7 — class auto-configuration tắt nhưng bean ứng dụng còn:**

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.auto.enabled=false --demo.custom.enabled=true --demo.report.enabled=true
~~~

~~~text
core=ABSENT
report=ABSENT
http=ABSENT
notifier=CUSTOM
~~~

Condition class chỉ điều khiển bean do `ScopeAutoConfiguration` cung cấp. Bean `customNotifier()` nằm ở một lớp cấu hình khác, vì vậy có thể tiếp tục tồn tại.

### 8.9. Ma trận kết quả

| `auto` | `report` | `http` | `custom` | Core | Report | HTTP | Notifier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| vắng | vắng | vắng | vắng | CORE | ABSENT | ABSENT | DEFAULT |
| vắng | true | vắng | vắng | CORE | REPORT | ABSENT | DEFAULT |
| vắng | vắng | true | vắng | CORE | ABSENT | HTTP | DEFAULT |
| vắng | true | true | vắng | CORE | REPORT | HTTP | DEFAULT |
| false | true | true | vắng | ABSENT | ABSENT | ABSENT | ABSENT |
| vắng | true | vắng | true | CORE | REPORT | ABSENT | CUSTOM |
| false | true | vắng | true | ABSENT | ABSENT | ABSENT | CUSTOM |

Khi tham số CLI không truyền, giá trị là **vắng**, không phải tất cả property đều mặc định thành false. Riêng `demo.auto.enabled` được cho phép nếu vắng nhờ `matchIfMissing=true`. Những property ở method dùng mặc định `matchIfMissing=false`.

## 9. Cách debug điều kiện cấp lớp và method

Đừng chỉ xem `Environment.getProperty(...)` ở thời điểm `ApplicationRunner`. Điều kiện được đánh giá khi Spring xử lý configuration/bean definitions; việc thay đổi property muộn hơn không tự làm Spring đăng ký lại bean.

Để xem lý do, chạy ứng dụng với condition report:

~~~bash
java -jar target/conditional-scope-demo-1.0.0.jar --demo.report.enabled=true --debug --logging.level.root=INFO
~~~

Trong output `Condition Evaluation Report` (nếu logging cho phép hiển thị), hãy tìm:

- `ScopeAutoConfiguration`: điều kiện cấp lớp `demo.auto.enabled`.
- `ScopeAutoConfiguration#reportService`: điều kiện của method report.
- `ScopeAutoConfiguration#httpMarker`: điều kiện của method HTTP.
- `ScopeAutoConfiguration#defaultNotifier`: điều kiện missing bean.
- Đối chiếu khi chạy `--demo.auto.enabled=false` để thấy condition lớp ngoài thay đổi.

Tên hiển thị cụ thể và format log phụ thuộc phiên bản Boot; hãy đọc **lý do match/mismatch**, không khăng khăng phải có một dòng log cố định. Khi class condition không khớp, điều kiện method có thể chưa được đánh giá độc lập như trong trường hợp class được chấp nhận. Vì vậy, **không thấy negative match của một method** chưa đủ để nói method chắc chắn được đăng ký.

Nếu dùng Spring Boot Actuator, endpoint `/actuator/conditions` (khi có dependency và expose an toàn) cung cấp thông tin condition. Đừng public endpoint diagnostic nhạy cảm mà không kiểm soát truy cập. Trong bài học đơn giản không cần cài Actuator; report qua `--debug` là đủ.

### Checklist ngắn khi bean không có

1. **Xác minh auto-configuration được phát hiện**: class có trong `AutoConfiguration.imports` và JAR nằm trên runtime classpath.
2. **Xem exclusions/filters**: ứng dụng có loại class đó qua `exclude` hoặc `spring.autoconfigure.exclude` không?
3. **Kiểm tra condition cấp class trước**: nếu đã false, bean methods của nhánh này không được đăng ký.
4. **Nếu class match, kiểm tra đúng method**: property riêng, bean tiền đề, thiếu class, scope.
5. **Đối chiếu giá trị property đã phân giải**: command line, system properties, environment variables, file config và profiles có thể ghi đè lẫn nhau.
6. **Nếu condition match nhưng bean vẫn lỗi**, phân biệt lỗi tạo instance/dependency với lỗi đăng ký definition.
7. **Đối chiếu một cặp chạy tối thiểu**: chỉ đổi một tham số từ false sang true để kết luận phạm vi bị ảnh hưởng.

## 10. Những sai lầm đáng tránh

### Sai lầm 1: “Có một method condition false thì cả class bị bỏ qua”

Không đúng. `@Conditional` đặt ở method chỉ ảnh hưởng bean definition do method ấy đóng góp. Các method khác vẫn có cơ hội được xử lý nếu class và những điều kiện liên quan không cản trở.

### Sai lầm 2: “Class condition true nghĩa là mọi bean method bên trong chắc chắn có”

Không đúng. Class condition true chỉ mở cổng ngoài. Mỗi method còn có điều kiện riêng; cũng có thể có lỗi tạo bean, `@Lazy` hoặc những ràng buộc khác.

### Sai lầm 3: “Method condition true có thể mở lại class đã bị loại”

Không đúng. Nếu cấu hình ngoài không được áp dụng, method nằm trong nhánh ấy không được dùng để đăng ký bean. Property method đúng không đảo ngược property class sai.

### Sai lầm 4: “@ConditionalOnMissingBean trên class chỉ bỏ một bean default”

Không đúng nếu class còn cung cấp các bean khác: khi condition cấp class không khớp, scope bị ảnh hưởng rộng hơn. Đặt missing-bean condition vào đúng method của bean muốn back off khi các bean khác vẫn phải hoạt động.

### Sai lầm 5: “Khai báo @ConditionalOnClass trên method luôn đủ an toàn với optional SDK”

Không nên phụ thuộc như vậy khi return type của method là class optional. Tách thành nested `@Configuration` với condition cấp class để tránh vấn đề tải method signature trước khi condition được xét.

### Sai lầm 6: “@ConditionalOnClass chứng minh đã có bean cùng type”

Không đúng. Nó kiểm tra classpath; muốn kiểm tra bean definition/bean tiền đề, dùng `@ConditionalOnBean` phù hợp với thứ tự xử lý.

### Sai lầm 7: “Bean không có nghĩa là ứng viên chưa được khám phá”

Không đúng. Cần kiểm tra imports metadata, exclusions, class condition, method condition và cuối cùng là khởi tạo bean. Một bean thiếu có nhiều nguyên nhân thuộc các giai đoạn khác nhau.

### Sai lầm 8: “Thêm property trong ApplicationRunner sẽ tự tạo bean mới”

Không. Property condition dùng lúc đánh giá cấu hình, không phải một event listener phản ứng với mọi thay đổi `Environment`. Muốn thay bean graph theo startup condition, cần cấu hình đúng trước refresh và tạo context theo cấu hình đó.

### Sai lầm 9: “Mọi type return của @Bean đều kiểm tra như nhau”

Không hẳn. Bean condition chỉ dùng thông tin type Spring biết tại thời điểm xét. Khai báo return type rõ ràng, phù hợp (kể cả type/generic khi liên quan) giúp điều kiện ổn định. Đừng giấu type trong `Object` rồi mong kiểm tra missing bean theo interface luôn chính xác.

### Sai lầm 10: “Các annotation điều kiện ghép theo phép OR”

Với nhiều conditions ở cùng một cấp, thông thường tất cả đều phải khớp. Nếu một method có condition property và missing bean, cả hai đều cần cho phép. Cấu trúc điều kiện có OR thực sự cần được thiết kế tường minh.

## 11. Cách quyết định đặt condition ở đâu

Khi xây một auto-configuration, áp dụng thứ tự sau:

**Bước 1 — Liệt kê tất cả bean.** Bean nào cần có trong mọi trường hợp, bean nào chỉ dùng khi bật tính năng, bean nào có thể bị người dùng thay thế?

**Bước 2 — Tìm tiền đề chung.** Chỉ đưa condition lên lớp ngoài nếu **mọi bean của lớp** đều thực sự phụ thuộc tiền đề đó.

**Bước 3 — Tách các lựa chọn riêng.** Những bean tích hợp report, HTTP, observability hoặc adapter tùy chọn nên có method condition hoặc một nested configuration riêng.

**Bước 4 — Đặt back-off chính xác.** `@ConditionalOnMissingBean` trên bean mặc định thường phù hợp hơn đặt trên toàn class, trừ khi cả cấu hình thực sự phải tắt khi bean đó tồn tại.

**Bước 5 — Xử lý optional class an toàn.** Nếu chữ ký bean method nhắc đến class có thể vắng ở runtime, cô lập method vào `static nested @Configuration` với classpath condition.

**Bước 6 — Kiểm tra ma trận.** Phải có test cho cả hai case condition lớp đúng/sai, và với class đúng thì từng method đúng/sai. Kiểm tra riêng tình huống user-supplied bean.

**Bước 7 — Debug theo scope.** Tìm đúng component trong condition report: class hay `Class#method`. Một “negative match” tại method không đồng nghĩa class ngoài bị từ chối.

Một câu hỏi quyết định đơn giản: **“Nếu điều kiện không khớp, tôi thực sự muốn bỏ qua bao nhiêu bean?”** Câu trả lời “toàn bộ” thường dẫn đến cấp class; câu trả lời “một bean” dẫn đến cấp method; câu trả lời “một nhóm” gợi ý nested `@Configuration`.

## 12. Câu hỏi tự kiểm tra

**1. Một class có ba phương thức @Bean, condition cấp class false. Có bao nhiêu bean từ nhánh đó được đăng ký?** Không bean nào được đăng ký qua nhánh class ấy.

**2. Class condition true, method B false, method A không có condition riêng. Method A có bị bỏ không?** Không chỉ vì B false; A vẫn có thể đăng ký nếu không có điều kiện khác cản trở.

**3. Property method=true nhưng property class=false, bean có tồn tại không?** Không qua nhánh ấy; method không vượt được cổng class.

**4. Ứng dụng đã cung cấp Notifier, defaultNotifier() có @ConditionalOnMissingBean. Điều gì xảy ra?** Default notifier bị bỏ qua, bean Notifier của ứng dụng còn; các method khác không tự động bị bỏ qua.

**5. Vì sao không đặt mọi @ConditionalOnProperty lên class ngoài?** Nó có thể loại cả các bean không phụ thuộc property đó, gây mất tính năng không liên quan.

**6. @ConditionalOnClass kiểm tra điều gì?** Classpath, không phải một bean cùng type đã có trong context.

**7. Khi return type của @Bean là class SDK optional, nên bảo vệ thế nào?** Dùng nested configuration có class condition để cô lập method signature.

**8. @ConditionalOnProperty không có havingValue mặc định kiểm tra thế nào?** Khi khóa hiện diện và giá trị không phải `false`, với `matchIfMissing=false` thì khóa vắng không khớp.

**9. Vì sao condition report cần đọc cả class và Class#method?** Vì class có thể được chọn nhưng method riêng vẫn bị loại bởi condition.

**10. Condition đánh giá trước hay sau ApplicationRunner?** Trong xử lý cấu hình/bean definitions khi khởi tạo context, thông thường trước runner; runner không tự kích hoạt đánh giá lại condition.

## Nguồn tài liệu chính thức

- Spring Boot — Creating Your Own Auto-configuration (Class Conditions, Bean Conditions, Property Conditions): https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — `@ConditionalOnClass` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot — `@ConditionalOnProperty` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot — Using Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Framework — `@Conditional` API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Conditional.html

**Kết luận:** điều kiện **cấp lớp** bảo vệ phạm vi một configuration; điều kiện **cấp phương thức** bảo vệ phạm vi một bean definition. Khi kết hợp, bean chỉ được đăng ký nếu các cổng điều kiện có liên quan đều cho phép. Chọn đúng cấp giúp auto-configuration tự lùi bước ở nơi cần thiết mà không vô hiệu hóa các bean khác.