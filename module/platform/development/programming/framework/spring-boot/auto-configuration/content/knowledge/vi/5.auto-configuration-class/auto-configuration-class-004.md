# Điều kiện đặt ở lớp ngoài, lớp lồng nhau và phương thức @Bean trong Spring Boot auto-configuration

## 1. Vì sao vị trí đặt điều kiện quan trọng?

Spring Boot không chỉ hỏi “điều kiện có đúng không?”, mà còn hỏi **điều kiện đang bảo vệ phạm vi nào**. Cùng một `@ConditionalOnProperty` nhưng đặt trên lớp `@AutoConfiguration`, lớp `@Configuration` lồng nhau hay phương thức `@Bean` sẽ tạo ra kết quả khác nhau.

Bài học tập trung vào ba mức:

1. **Lớp ngoài:** điều kiện quyết định cả auto-configuration có được áp dụng theo đường xử lý thông thường hay không. Nếu không khớp, những bean do cấu hình đó cung cấp không được đăng ký qua nhánh ấy.
2. **Lớp cấu hình lồng nhau:** điều kiện chỉ bảo vệ **một nhóm bean**. Phần còn lại của lớp ngoài vẫn có thể hoạt động.
3. **Phương thức `@Bean`:** điều kiện chỉ bảo vệ **một bean definition**. Các phương thức khác cùng lớp có thể vẫn được đăng ký.

Một cấu trúc có cả ba cấp có thể diễn đạt như sau:

~~~text
@AutoConfiguration
@ConditionalOnProperty("demo.auto=true")       ← cổng lớp ngoài
└── MainAutoConfiguration
    ├── @Bean mainService()                     ← bean của lớp ngoài
    │   └── @ConditionalOnMissingBean           ← cổng riêng của mainService
    │
    └── @Configuration NestedMetricsConfig
        ├── @ConditionalOnProperty("demo.metrics=true")
        │                                        ← cổng nhóm lồng nhau
        ├── @Bean metricsService()              ← qua cổng nhóm là được
        └── @Bean detailsService()
            └── @ConditionalOnProperty("demo.details=true")
                                                 ← cổng của một phương thức
~~~

Theo đường xử lý cấu hình thông thường, muốn có `detailsService` thì **cả** điều kiện ngoài, điều kiện nhóm lồng và điều kiện của chính phương thức đều phải đúng. Ngược lại, muốn có `mainService` không bắt buộc `demo.metrics=true`, vì bean này nằm ngoài nhóm metrics.

**Mục tiêu:** hiểu phạm vi hiệu lực, các mốc đánh giá và những lỗi dễ mắc khi thiết kế auto-configuration; tự chạy một ví dụ Java 17+ để quan sát kết quả thay đổi theo properties; biết chẩn đoán đúng class hay bean nào không khớp.

## 2. Từ @Conditional đến bean definition

Trong Spring Framework, `@Conditional` gắn một hoặc nhiều `Condition` lên một thành phần cấu hình. Spring Boot cung cấp các điều kiện tiện dụng, ví dụ:

- `@ConditionalOnClass`, `@ConditionalOnMissingClass`: dựa trên sự hiện diện của class trên classpath.
- `@ConditionalOnProperty`: dựa trên thuộc tính của `Environment`.
- `@ConditionalOnBean`, `@ConditionalOnMissingBean`: dựa trên bean definitions/beans có thể quan sát được khi đánh giá.
- `@ConditionalOnWebApplication`: dựa trên môi trường ứng dụng web.
- `@ConditionalOnResource`: dựa trên sự hiện diện của resource.

**Điều kiện không phải là cơ chế điều khiển một instance bean sau khi bean đã chạy.** Trong xử lý cấu hình, nó quyết định có đưa cấu hình hoặc bean definition tương ứng vào context hay không. Khi property thay đổi sau thời điểm condition đã xét, Spring Boot thường **không tự đánh giá lại tất cả điều kiện để thêm/xóa bean**.

Khác biệt cần nhớ:

| Khái niệm | Ý nghĩa |
| --- | --- |
| Auto-configuration được **khám phá** | Tên class được Spring Boot biết qua tài nguyên imports trên classpath. |
| Auto-configuration được **chọn/import** | Được xem xét sau cơ chế lọc, exclusions và sắp xếp. |
| Điều kiện **khớp** | Lớp hoặc phương thức được phép tham gia theo điều kiện tương ứng. |
| Bean definition được **đăng ký** | Container biết cách tạo một bean, còn tùy dependency/scope/lazy. |
| Bean được **khởi tạo** | Instance thực sự được tạo và xử lý lifecycle; có thể thất bại vì lý do khác. |

Không dùng “condition pass” làm bằng chứng rằng bean chắc chắn đã được khởi tạo. Cũng không dùng “không có bean” để khẳng định auto-configuration không được khám phá.

### Thứ tự đánh giá và các điều kiện ghép

Trong đường xử lý thông thường, điều kiện ở thành phần bao ngoài và thành phần con kết hợp theo nghĩa **đều phải cho phép**: nếu lớp ngoài bị từ chối, nhóm lồng và các bean thuộc đường đó không được đăng ký. Nếu lớp ngoài được chấp nhận nhưng nhóm lồng bị từ chối, bean ngoài nhóm vẫn có thể được tạo.

Điều kiện trên một lớp có thể được xử lý ở thời điểm khác điều kiện trên phương thức. Spring Framework phân biệt `ConfigurationCondition.ConfigurationPhase.PARSE_CONFIGURATION` và `REGISTER_BEAN`; mỗi implementation có pha riêng. Vì vậy sơ đồ “ba cổng” là cách tư duy về **phạm vi**, không phải cam kết tất cả điều kiện đều chạy tuần tự ngay tại một dòng code.

Một lưu ý nâng cao: `@Conditional` ở lớp ngoài không phải “luật kế thừa Java” áp lên mọi lớp lồng bất kể cách nạp. Nếu lớp `@Configuration` lồng được **đăng ký riêng** qua component scan hoặc `@Import` độc lập, nó có thể được xử lý bằng các điều kiện của chính nó; điều kiện của lớp bao ngoài không nhất thiết áp dụng như khi Spring đi qua lớp ngoài để phân tích lớp lồng. Để kiến trúc rõ ràng, đừng đồng thời đăng ký lớp lồng theo một đường độc lập nếu bạn muốn nó luôn phụ thuộc vào cổng ngoài.

## 3. Đặt @Conditional ở lớp @AutoConfiguration bên ngoài

Ví dụ:

~~~java
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo",
        name = "auto",
        havingValue = "true",
        matchIfMissing = true
)
public class DemoAutoConfiguration {
    // Các @Bean và @Configuration lồng nhau.
}
~~~

Đây là **một snippet minh họa**, chưa có package, chưa có bean và chưa phải chương trình độc lập. Nó biểu đạt:

- `demo.auto=true`: điều kiện ngoài khớp.
- `demo.auto=false`: không khớp.
- Khóa `demo.auto` vắng mặt: **vẫn khớp** vì `matchIfMissing=true`.
- Giá trị `demo.auto=other`: không khớp khi `havingValue="true"`.

Khi điều kiện ngoài không khớp, các bean được định nghĩa thông qua lớp này sẽ không được đăng ký **theo nhánh xử lý thông thường của lớp cấu hình đó**. Điều này thích hợp khi một auto-configuration có **điều kiện tiên quyết chung** cho toàn bộ tính năng, chẳng hạn một property tắt toàn bộ tính năng, loại ứng dụng hoặc dependency bắt buộc.

Tuy nhiên, không nên đưa mọi điều kiện nhỏ lên lớp ngoài. Nếu chỉ tính năng phụ cần một thư viện tùy chọn, đặt `@ConditionalOnClass` cho cả lớp ngoài có thể vô tình vô hiệu hóa cả các bean lõi **không phụ thuộc thư viện đó**.

**Tiêu chí chọn cấp lớp ngoài:** nếu điều kiện không khớp thì **mọi bean do cấu hình này cung cấp đều nên không tồn tại**. Nếu chỉ một phần không nên tồn tại, hãy dùng lớp lồng hoặc phương thức `@Bean`.

### Dùng @ConditionalOnClass ở đâu?

`@ConditionalOnClass(SomeApi.class)` ở lớp `@Configuration` là một mẫu phổ biến. Boot có thể đọc annotation metadata từ bytecode (ASM) mà không nhất thiết phải tải sớm class optional. Nhưng việc kiểm tra class trên phương thức `@Bean` có **return type là class tùy chọn** có thể gặp vấn đề trước khi condition được đánh giá do JVM cần xử lý chữ ký phương thức.

Khi một integration phụ thuộc loại class không chắc có trên runtime classpath, hãy **cô lập integration trong một lớp `@Configuration` lồng nhau có `@ConditionalOnClass`**, thay vì chỉ gắn điều kiện lên phương thức trả về loại class tùy chọn. Chi tiết ở phần 5.

## 4. Đặt @Conditional trên lớp @Configuration lồng nhau

Lớp lồng nhau giúp nhóm các bean cùng một điều kiện:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "demo",
        name = "metrics",
        havingValue = "true"
)
static class MetricsConfiguration {

    @Bean
    MetricsService metricsService() {
        return new MetricsService();
    }

    @Bean
    DetailsService detailsService() {
        return new DetailsService();
    }
}
~~~

Đây là **đoạn code minh họa bên trong lớp cấu hình ngoài**, chưa tự biên dịch độc lập vì thiếu import và khai báo `MetricsService`/`DetailsService`. Nếu điều kiện nhóm `demo.metrics=true` không khớp, cả hai phương thức bean nằm trong nhóm này bị bỏ qua theo nhánh cấu hình đó; nhưng các bean khác ở lớp ngoài không cần bị bỏ qua.

Trong auto-configuration thường dùng **`static class`** có annotation `@Configuration(proxyBeanMethods = false)`. `static` tránh ràng buộc không cần thiết tới instance lớp ngoài; `proxyBeanMethods=false` phù hợp khi các bean được liên kết qua dependency injection thay vì gọi chéo phương thức `@Bean` trực tiếp như một factory cần proxy.

### Tại sao nhóm lồng nhau có ích?

Giả sử một thư viện có bộ xử lý lõi không cần thư viện web nhưng thêm endpoint HTTP khi ứng dụng có Servlet API. Nếu dùng `@ConditionalOnClass` ở lớp ngoài, phần lõi cũng biến mất khi chạy CLI. Tách ra:

~~~java
@AutoConfiguration
public class SharedAutoConfiguration {

    @Bean
    CoreService coreService() {
        return new CoreService();
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "jakarta.servlet.Servlet")
    static class ServletOnlyConfiguration {

        // Các @Bean tích hợp servlet được khai báo ở đây.
    }
}
~~~

Đoạn này **mang tính cấu trúc, không phải ví dụ chạy độc lập**; `CoreService` và bean servlet là type minh họa. Ý nghĩa: bean lõi có thể tồn tại trên CLI hoặc trong ứng dụng không có servlet, còn nhóm tích hợp servlet chỉ được xét khi class cần thiết sẵn sàng.

Có thể đặt nhiều lớp lồng độc lập bên trong một `@AutoConfiguration`, mỗi lớp bảo vệ một nhánh tích hợp khác nhau. Chúng không buộc phải có chung điều kiện ngoài nếu thư viện không có một điều kiện tiên quyết chung.

### An toàn khi class optional không nằm trên classpath

Spring Boot khuyến nghị chính kiểu cô lập sau:

~~~java
@AutoConfiguration
public class ExternalIntegrationAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.sdk.Client")
    static class VendorClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        com.vendor.sdk.Client client() {
            return new com.vendor.sdk.Client();
        }
    }
}
~~~

Đây là **mẫu minh họa kiến trúc**, không biên dịch nếu chưa thêm dependency SDK lúc compile và chưa có loại constructor tương ứng. Khi đóng gói thư viện, SDK có thể là **compile dependency** để xây dựng class integration nhưng **không bắt buộc có ở runtime** trong mọi ứng dụng. Việc gắn `@ConditionalOnClass` ở lớp cấu hình cô lập giúp Spring quyết định có phân tích nhóm bean chứa chữ ký kiểu optional hay không. Không đặt annotation chỉ trên `client()` rồi mặc định nó sẽ bảo vệ khỏi mọi lỗi load class.

Nếu cần tạo composed annotation có `@ConditionalOnClass` làm meta-annotation, tài liệu Spring Boot lưu ý nên dùng thuộc tính `name` thay cho thuộc tính `value` tham chiếu trực tiếp class vì cách đọc bytecode metadata không giống trường hợp annotation gắn trực tiếp.

## 5. Đặt @Conditional ở phương thức @Bean

Một condition trên phương thức chỉ điều khiển **bean được khai báo ở phương thức đó**:

~~~java
@Bean
@ConditionalOnProperty(
        prefix = "demo",
        name = "details",
        havingValue = "true"
)
DetailsService detailsService() {
    return new DetailsService();
}
~~~

Đây là đoạn trong lớp cấu hình, không phải chương trình đầy đủ. Nếu `demo.details=false`, bean `detailsService` bị bỏ qua, nhưng những phương thức `@Bean` không có điều kiện đó vẫn có thể được đăng ký.

Mẫu quan trọng khác cho auto-configuration là:

~~~java
@Bean
@ConditionalOnMissingBean(GreetingService.class)
GreetingService defaultGreetingService() {
    return () -> "AUTO";
}
~~~

Mẫu này giả định đã khai báo interface `GreetingService`. Khi ứng dụng có bean `GreetingService` phù hợp, bean mặc định **back off**; các bean khác cùng auto-configuration không nhất thiết bị tắt. Đây là cách viết thích hợp khi **chỉ muốn cho phép thay thế một bean mặc định**.

### Đặt @ConditionalOnMissingBean tại lớp hay phương thức?

| Vị trí | Ý nghĩa |
| --- | --- |
| Trên lớp `@AutoConfiguration` / `@Configuration` | Nếu không khớp, bỏ qua đăng ký lớp cấu hình đó và các bean thuộc nhánh xử lý của nó. |
| Trên lớp `@Configuration` lồng | Nếu không khớp, bỏ qua cả **nhóm bean** thuộc lớp lồng ấy. |
| Trên một phương thức `@Bean` | Nếu không khớp, chỉ bỏ qua **định nghĩa bean của phương thức đó**. |

Ví dụ có một cấu hình chứa ba bean nhưng chỉ một bean cần back-off: nếu đặt `@ConditionalOnMissingBean(MyService.class)` trên **lớp ngoài**, khi ứng dụng có `MyService` thì **cả cấu hình** bị từ chối, có thể bỏ mất các bean tiện ích không liên quan. Đặt điều kiện trên đúng phương thức cung cấp `MyService` sẽ tránh ảnh hưởng ngoài ý muốn.

### Tại sao thứ tự đăng ký bean definitions quan trọng?

`@ConditionalOnMissingBean` và `@ConditionalOnBean` nhìn vào các bean definitions/beans đã được xử lý tới lúc điều kiện được xét. Chúng không nhìn trước mọi bean sẽ xuất hiện trong tương lai. Spring Boot dùng cơ chế import auto-configuration trì hoãn để đảm bảo các cấu hình do người dùng cung cấp được xử lý trước phần tự cấu hình, nên các điều kiện bean ở auto-configuration có thể back off đúng hơn.

Một lưu ý về type: điều kiện dựa trên bean chỉ phân giải thông tin type mà Spring biết ở thời điểm xét. Với `@Bean`, hãy khai báo return type đủ cụ thể và phù hợp, không dùng `Object` vô cớ làm mất thông tin loại. Trong ví dụ thực hành, ta khai báo tường minh type interface khi muốn điều kiện kiểm tra cùng interface.

### Nhiều điều kiện trên cùng một cấp

Nếu một bean có hai điều kiện:

~~~java
@Bean
@ConditionalOnProperty(prefix = "demo", name = "logging", havingValue = "true")
@ConditionalOnMissingBean(AuditLogger.class)
AuditLogger auditLogger() {
    return new DefaultAuditLogger();
}
~~~

Đây là snippet minh họa; cần định nghĩa `AuditLogger` và `DefaultAuditLogger`. Bean chỉ được đăng ký khi **property đúng và không có bean logger phù hợp**. Không phải hai điều kiện theo kiểu “chỉ cần một trong hai đúng”. Nếu muốn logic OR phức tạp, cần tổ chức các nhóm cấu hình hoặc tự viết `Condition` phù hợp, chứ không giả định nhiều annotations là OR.

## 6. Bảng tổng kết ba tầng và cách chọn vị trí

| Câu hỏi thiết kế | Lựa chọn nên cân nhắc | Vì sao |
| --- | --- | --- |
| Một property tắt **toàn bộ** tính năng | Condition ở lớp `@AutoConfiguration` ngoài | Giữ một cổng điều khiển chung. |
| Một integration phụ thuộc SDK tùy chọn | Condition ở lớp `@Configuration` lồng | Giữ bean lõi khi thiếu SDK và cô lập class loading. |
| Chỉ một bean cần được thay thế bởi ứng dụng | `@ConditionalOnMissingBean` tại phương thức `@Bean` | Chỉ bean mặc định đó back off. |
| Một nhóm bean chỉ bật khi `feature.metrics=true` | Condition tại lớp lồng chứa nhóm | Tránh lặp annotation trên mọi phương thức. |
| Trong nhóm metrics, chỉ bean details cần thêm property | Condition tại riêng `detailsService()` | Tránh tắt cả nhóm metrics. |
| Một bean cần hai điều kiện độc lập | Ghép cả hai annotation tại cấp phù hợp | Cùng phải khớp ở cấp đó. |

**Quy tắc thực hành:** đưa một condition lên cấp cao nhất mà **mọi bean nằm trong phạm vi ấy đều cần điều kiện đó**. Nếu đưa quá cao, bạn loại dư bean; nếu đặt quá thấp, bạn lặp điều kiện và dễ bỏ sót hoặc tạo rủi ro load class optional.

## 7. Ví dụ chạy được: Spring Boot 3.5.0 và Java 17+

Ta viết một auto-configuration đăng ký qua `AutoConfiguration.imports`, có đủ ba tầng:

- Điều kiện **ngoài**: `demo.auto=true` hoặc property vắng (mặc định bật).
- Điều kiện **lớp lồng**: `demo.metrics=true` bật nhóm metrics.
- Điều kiện **phương thức trong lớp lồng**: `demo.details=true` bật riêng details; vì nằm trong nhóm metrics, vẫn cần `demo.metrics=true`.
- Điều kiện **phương thức ở lớp ngoài**: `@ConditionalOnMissingBean(MessageService.class)` khiến bean mặc định lùi bước nếu ứng dụng đã cung cấp `MessageService`.

Dự án Java 17+ không cần database, web server hoặc SDK ngoài Spring Boot starter. Bản minh họa chọn **Spring Boot 3.5.0**, một phiên bản cụ thể để tránh phụ thuộc mơ hồ vào API bản mới nhất.

### 7.1. Cấu trúc

~~~text
condition-scopes-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── api/
    │   │   ├── MessageService.java
    │   │   ├── MetricsService.java
    │   │   └── DetailsService.java
    │   ├── app/DemoApplication.java
    │   └── autoconfig/DemoAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

`DemoApplication` nằm trong package `com.example.app`. `DemoAutoConfiguration` nằm ở `com.example.autoconfig`, **ngoài vùng component scan mặc định của ứng dụng**. Class auto-configuration chỉ được ứng dụng phát hiện nhờ imports metadata; cách tổ chức này tránh nhầm kết quả do component scan.

### 7.2. pom.xml

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
    <artifactId>condition-scopes-demo</artifactId>
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

### 7.3. Ba interface nhỏ

`src/main/java/com/example/api/MessageService.java`:

~~~java
package com.example.api;

public interface MessageService {
    String message();
}
~~~

`src/main/java/com/example/api/MetricsService.java`:

~~~java
package com.example.api;

public interface MetricsService {
    String metric();
}
~~~

`src/main/java/com/example/api/DetailsService.java`:

~~~java
package com.example.api;

public interface DetailsService {
    String detail();
}
~~~

Mỗi interface đóng vai trò một type bean riêng. Chúng chỉ khai báo contract; bản thân interface hiện diện trên classpath **không đồng nghĩa một bean đã tồn tại**.

### 7.4. DemoAutoConfiguration.java

`src/main/java/com/example/autoconfig/DemoAutoConfiguration.java`:

~~~java
package com.example.autoconfig;

import com.example.api.DetailsService;
import com.example.api.MessageService;
import com.example.api.MetricsService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo",
        name = "auto",
        havingValue = "true",
        matchIfMissing = true
)
public class DemoAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MessageService.class)
    MessageService defaultMessageService() {
        return () -> "AUTO";
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo",
            name = "metrics",
            havingValue = "true"
    )
    static class MetricsConfiguration {

        @Bean
        MetricsService metricsService() {
            return () -> "METRICS";
        }

        @Bean
        @ConditionalOnProperty(
                prefix = "demo",
                name = "details",
                havingValue = "true"
        )
        DetailsService detailsService() {
            return () -> "DETAILS";
        }
    }
}
~~~

Nhận diện từng cấp:

- `@ConditionalOnProperty(demo.auto)` ở lớp ngoài: ảnh hưởng **mọi bean** của auto-configuration theo đường này.
- `@ConditionalOnMissingBean(MessageService.class)` tại `defaultMessageService()`: chỉ bỏ qua **bean mặc định**, không tắt nhóm metrics.
- `@ConditionalOnProperty(demo.metrics)` tại `MetricsConfiguration`: điều khiển **cả `metricsService()` và `detailsService()`**.
- `@ConditionalOnProperty(demo.details)` tại `detailsService()`: chỉ điều khiển **bean details**, nhưng không vượt qua được cổng nhóm nếu `demo.metrics=false`.

Lớp lồng là `static` và có `@Configuration(proxyBeanMethods = false)`, đúng mẫu phù hợp để gom điều kiện. Các class interface đều thuộc dự án và có trên classpath, nên ví dụ không cần xử lý optional dependency.

### 7.5. Metadata AutoConfiguration.imports

Tệp ở đúng đường dẫn `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` có nội dung một dòng:

~~~text
com.example.autoconfig.DemoAutoConfiguration
~~~

**Chỉ liệt kê lớp auto-configuration ngoài**, không liệt kê `DemoAutoConfiguration$MetricsConfiguration` như một ứng viên độc lập. Spring sẽ xử lý lớp lồng thông qua cấu hình ngoài. Nếu chủ động công bố lớp lồng thành auto-configuration riêng hoặc cho component scan quét nó, phạm vi điều kiện ngoài không còn giống mô hình ba tầng đang học.

### 7.6. DemoApplication.java

`src/main/java/com/example/app/DemoApplication.java`:

~~~java
package com.example.app;

import com.example.api.DetailsService;
import com.example.api.MessageService;
import com.example.api.MetricsService;
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
            prefix = "demo",
            name = "custom",
            havingValue = "true"
    )
    MessageService userMessageService() {
        return () -> "CUSTOM";
    }

    @Bean
    ApplicationRunner report(
            ObjectProvider<MessageService> messages,
            ObjectProvider<MetricsService> metrics,
            ObjectProvider<DetailsService> details) {
        return args -> {
            MessageService msg = messages.getIfAvailable();
            MetricsService met = metrics.getIfAvailable();
            DetailsService det = details.getIfAvailable();

            System.out.println("message="
                    + (msg == null ? "ABSENT" : msg.message()));
            System.out.println("metrics="
                    + (met == null ? "ABSENT" : met.metric()));
            System.out.println("details="
                    + (det == null ? "ABSENT" : det.detail()));
        };
    }
}
~~~

`userMessageService()` là bean do **ứng dụng** định nghĩa, hoạt động khi `demo.custom=true`. Vì auto-configuration được xử lý sau các bean definitions của ứng dụng, `@ConditionalOnMissingBean` tại bean mặc định nhận thấy bean `MessageService` và back off. `ObjectProvider` cho phép in `ABSENT` mà không lỗi injection bắt buộc nếu một type không có bean.

Các trường hợp trong bài chỉ có tối đa một bean mỗi interface. Nếu bạn tự thêm hai bean cùng type, `getIfAvailable()` có thể lỗi vì không duy nhất; đó là chủ đề DI khác, không phải một thuộc tính của điều kiện lớp ngoài/lồng/bean.

### 7.7. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Không đặt `demo.auto`, `demo.metrics`, `demo.details` hoặc `demo.custom` trong file. Những khóa này được đưa bằng command-line để mỗi lần chạy chỉ thay đổi các cổng mong muốn. Tắt bớt logging giúp phân biệt stdout do ví dụ in với log khởi động (vẫn có thể có thông báo từ JVM hoặc môi trường).

### 7.8. Biên dịch và chạy

Cài JDK 17+ và Maven, đứng tại thư mục `condition-scopes-demo`, chạy:

~~~bash
mvn -q -DskipTests package
java -jar target/condition-scopes-demo-1.0.0.jar
~~~

Ba dòng chương trình in:

~~~text
message=AUTO
metrics=ABSENT
details=ABSENT
~~~

Giải thích: `demo.auto` vắng nhưng điều kiện ngoài có `matchIfMissing=true`; không có bean `MessageService` do người dùng khai báo, nên `defaultMessageService` được tạo. `demo.metrics` vắng nên cả nhóm lồng bị bỏ qua.

**Bật nhóm metrics nhưng chưa bật details:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.metrics=true
~~~

~~~text
message=AUTO
metrics=METRICS
details=ABSENT
~~~

Lớp lồng được chấp nhận, nhưng `detailsService()` bị bỏ qua do `demo.details` vắng. Bean ngoài nhóm vẫn có mặt.

**Bật đủ ba cổng để tạo details:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.metrics=true --demo.details=true
~~~

~~~text
message=AUTO
metrics=METRICS
details=DETAILS
~~~

Đây là trường hợp nhóm lồng và phương thức đều vượt qua điều kiện.

**Bật details nhưng không bật nhóm:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.details=true
~~~

~~~text
message=AUTO
metrics=ABSENT
details=ABSENT
~~~

Đây là phép thử quan trọng: `demo.details=true` **không thể tạo detailsService** nếu `MetricsConfiguration` bị bỏ qua. Cổng cấp phương thức không vượt qua được cổng cấp nhóm.

**Tắt toàn bộ auto-configuration:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.auto=false --demo.metrics=true --demo.details=true
~~~

~~~text
message=ABSENT
metrics=ABSENT
details=ABSENT
~~~

Điều kiện lớp ngoài không khớp; không có bean mặc định nào từ auto-configuration này. Dù hai property cho lớp lồng/method là `true`, chúng không thể “khôi phục” nhánh cấu hình đã bị loại.

**Thay thế riêng MessageService bằng bean ứng dụng:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.custom=true --demo.metrics=true --demo.details=true
~~~

~~~text
message=CUSTOM
metrics=METRICS
details=DETAILS
~~~

`defaultMessageService()` bị `@ConditionalOnMissingBean` bỏ qua vì đã có bean user; nhưng nhóm metrics vẫn được đăng ký. Đây là minh họa rõ vì sao điều kiện back-off của **một bean** không nên vô tình đặt lên **cả lớp ngoài**.

**Ứng dụng vẫn có bean tùy chỉnh khi tắt lớp ngoài:**

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.auto=false --demo.custom=true --demo.metrics=true --demo.details=true
~~~

~~~text
message=CUSTOM
metrics=ABSENT
details=ABSENT
~~~

Property `demo.auto=false` chỉ tắt **auto-configuration mẫu**, không tắt `@Bean userMessageService()` do ứng dụng khai báo ở một lớp cấu hình khác.

### 7.9. Ma trận kết quả

| demo.auto | demo.custom | demo.metrics | demo.details | message | metrics | details |
| --- | --- | --- | --- | --- | --- | --- |
| vắng | vắng | vắng | vắng | AUTO | ABSENT | ABSENT |
| vắng | vắng | true | vắng | AUTO | METRICS | ABSENT |
| vắng | vắng | true | true | AUTO | METRICS | DETAILS |
| vắng | vắng | vắng | true | AUTO | ABSENT | ABSENT |
| false | vắng | true | true | ABSENT | ABSENT | ABSENT |
| vắng | true | true | true | CUSTOM | METRICS | DETAILS |
| false | true | true | true | CUSTOM | ABSENT | ABSENT |

Các chuỗi in trên là **stdout do ứng dụng tự tạo**, không bao gồm log Spring Boot. Cần hiểu các dòng `AUTO`/`METRICS`/`DETAILS` là kết quả các lambda return value trong mã mẫu, không phải keyword hay chế độ tự động có sẵn của Boot.

## 8. Đọc Condition Evaluation Report để xác minh từng tầng

Khi một bean không xuất hiện, dùng condition report thay vì suy đoán. Chạy lại JAR, bật debug và nâng mức log để báo cáo có thể hiển thị:

~~~bash
java -jar target/condition-scopes-demo-1.0.0.jar --demo.metrics=true --debug --logging.level.root=INFO
~~~

Tìm tên lớp:

- `DemoAutoConfiguration`: điều kiện lớp ngoài có khớp không?
- `DemoAutoConfiguration.MetricsConfiguration` (cách hiển thị có thể khác): nhóm lồng có khớp không?
- `DemoAutoConfiguration.MetricsConfiguration#detailsService`: property riêng của bean details có khớp không?
- `DemoAutoConfiguration#defaultMessageService`: `@ConditionalOnMissingBean` có tìm thấy bean `MessageService` do ứng dụng cung cấp không?

Tên và cấu trúc log có thể khác giữa các phiên bản; hãy đọc **nguyên nhân** của positive/negative matches, không dựa vào một chuỗi log chính xác từng ký tự. Condition report không phải danh sách mọi bean đã được khởi tạo thành công.

Nếu dùng Actuator, endpoint `/actuator/conditions` có thể cung cấp thông tin điều kiện khi dependency, exposure và bảo mật được cấu hình. Đừng giả định endpoint này đã bật hoặc an toàn để public; không lộ property nhạy cảm khi debug.

### Một vài trường hợp cần tra ngay

**Thấy lớp ngoài negative match:** trước hết kiểm tra `demo.auto` ở Environment và các nguồn ghi đè. Không dành thời gian debug bean method bên trong khi lớp ngoài đã bị loại.

**Lớp ngoài positive, nhóm metrics negative:** xem `demo.metrics`; không chỉnh `demo.details` vì bản thân nhóm chưa được áp dụng.

**Nhóm metrics positive, detailsService negative:** kiểm tra `demo.details` và `havingValue` ở phương thức details.

**Có MessageService CUSTOM, không thấy mặc định:** kiểm tra `@ConditionalOnMissingBean`; đây có thể là **back-off đúng** chứ không phải lỗi.

**Không thấy toàn bộ auto-configuration trong report:** kiểm tra metadata `AutoConfiguration.imports` trong JAR, exclusions, điều kiện/filter sớm, classpath và context đang chạy; việc không xuất hiện ở report **không tự chứng minh** một lỗi duy nhất.

## 9. Lỗi phổ biến khi đặt điều kiện sai cấp

### 9.1. Đặt điều kiện nhóm lên lớp ngoài

Sai phạm vi:

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "demo", name = "metrics", havingValue = "true")
public class MyAutoConfiguration {
    // Cả coreService lẫn metricsService đều bị loại nếu demo.metrics=false.
}
~~~

Nếu `coreService` vẫn phải tồn tại khi metrics tắt, đây là thiết kế không đúng. Cách sửa: chỉ bảo vệ một `MetricsConfiguration` lồng nhau hoặc bean metrics; giữ core ngoài điều kiện nhóm.

### 9.2. Đặt @ConditionalOnMissingBean lên lớp ngoài chỉ để thay một bean

Nếu cả lớp ngoài còn cung cấp `HealthMarker` và `EventPublisher`, khi ứng dụng tự khai báo bean `MessageService`, điều kiện ngoài khiến mọi bean thuộc auto-configuration bị bỏ qua. Chỉ đặt điều kiện lên `defaultMessageService()` nếu mong muốn là thay riêng message service.

### 9.3. Gắn @ConditionalOnClass lên @Bean có return type optional

Đây là bẫy khi type trả về không có ở runtime. Annotation có thể chưa kịp bảo vệ khỏi việc JVM xử lý signature của phương thức. Đặt điều kiện ở **lớp `@Configuration` lồng cô lập** để Spring có thể đánh giá sự hiện diện class trước khi xử lý các phương thức có chữ ký phụ thuộc type đó.

### 9.4. Cho rằng lớp lồng luôn tự động kế thừa điều kiện ngoài

Trong đường xử lý qua outer config, điều kiện ngoài chặn cả nhánh; nhưng nếu bạn **quét hoặc import trực tiếp** lớp lồng qua một lối khác, các điều kiện trên outer không nhất thiết được áp dụng. Đặt auto-configuration ngoài vùng component scan và không công bố lớp lồng như ứng viên độc lập nếu muốn giữ cách hiểu “ba cổng”.

### 9.5. Nhầm @Conditional với logic chạy ở runtime

Một condition loại bean definition khi context đang khởi động; không phải `if` chạy lại mỗi lần gọi method. Thay đổi property sau khi ứng dụng sẵn sàng thường không tự thêm/xóa những bean definitions trước đó. Nếu muốn hành vi runtime thay đổi liên tục, nên thiết kế service đọc cấu hình động hoặc cơ chế refresh phù hợp thay vì dựa vào điều kiện auto-configuration.

### 9.6. Nhầm “có điều kiện cùng lúc” với OR

Trên cùng bean, hai annotation điều kiện thường cần **cùng khớp**. Tương tự, nếu outer, nested và bean method mỗi cấp đều đặt điều kiện thì **mọi cổng liên quan phải mở**. Đừng kỳ vọng điều kiện phương thức đúng có thể vượt qua điều kiện lớp lồng sai.

### 9.7. Dùng interface quá chung làm return type và suy luận sai kết quả bean condition

Bean conditions đọc thông tin type Spring biết tới thời điểm xét; khai báo `@Bean Object service()` có thể khiến kiểm tra type cụ thể kém tin cậy hơn mong đợi. Hãy khai báo return type đủ cụ thể và rõ ràng. Điều kiện `@ConditionalOnMissingBean` với type tường minh là một lựa chọn tốt nếu muốn một bean mặc định được thay thế bằng implementation cùng contract.

### 9.8. Nhầm điều kiện class với việc dependency đã có bean

`@ConditionalOnClass(SomeType.class)` chỉ xác nhận class tồn tại trên classpath; nó không chứng minh trong context có bean `SomeType`. Muốn bảo đảm có bean tiền đề, dùng `@ConditionalOnBean` phù hợp và hiểu rõ thứ tự bean definitions. Với application context có nhiều cấp, còn cần xét phạm vi tìm kiếm `search`.

### 9.9. Đặt bean conditions ở cấu hình ứng dụng không bảo đảm thứ tự

Khi một điều kiện kiểm tra thiếu bean chạy quá sớm, nó có thể chưa nhìn thấy bean dự định đăng ký sau đó. Tài liệu Boot khuyên dùng `@ConditionalOnBean`/`@ConditionalOnMissingBean` chủ yếu ở auto-configuration vì được xử lý sau bean definitions của người dùng.

### 9.10. Diễn giải sai kết quả do test slice hoặc classpath

Trong test slice, không phải toàn bộ auto-configuration được nạp như `@SpringBootTest` thông thường. Nếu một bean vắng mặt, hãy xác nhận loại context và tập auto-configuration được import. Khi so sánh condition report giữa hai test, bảo đảm chúng chạy trong các context tương đương.

## 10. Quy trình thiết kế đúng phạm vi điều kiện

Khi xây một starter hoặc auto-configuration mới:

1. **Liệt kê các bean sẽ cung cấp**, phân nhóm lõi và optional. Với từng bean, nêu rõ phụ thuộc classpath, property, profile hoặc bean khác.
2. **Chọn điều kiện chung của toàn lớp.** Chỉ đặt ngoài nếu không khớp thì không bean nào của cấu hình nên tồn tại.
3. **Tách nhóm optional bằng static nested @Configuration.** Đặt `@ConditionalOnClass`, `@ConditionalOnProperty` hoặc điều kiện web phù hợp ở lớp lồng để gom các bean phụ thuộc cùng tiền đề.
4. **Đặt điều kiện riêng lên từng @Bean.** Dùng `@ConditionalOnMissingBean` để cho phép người dùng thay bean mặc định; dùng property condition để bật riêng một bean.
5. **Cẩn thận khi type optional vắng.** Đặt mọi method có chữ ký liên quan SDK trong lớp cấu hình được bảo vệ bởi class condition; không chỉ bảo vệ từng method.
6. **Đảm bảo lớp ngoài được Boot khám phá đúng.** Đăng ký tên FQCN trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` và không để package auto-config bị component scan tùy tiện.
7. **Tạo ma trận test.** Kiểm tra outer ON/OFF, nhóm ON/OFF, method ON/OFF, có/không bean custom. Kiểm tra cả tổ hợp property child=true nhưng group=false để xác nhận thứ bậc.
8. **Quan sát report và bean definitions.** Nếu kết quả không như mong đợi, tìm đúng cấp bị chặn trước khi sửa annotation.

Bảng “quyết định” có thể dùng trong review:

| Nhận xét về requirement | Thay đổi đề xuất |
| --- | --- |
| “Tắt metrics cũng tắt luôn message service, dù không mong muốn” | Di chuyển `@ConditionalOnProperty(metrics)` từ outer xuống nested metrics config. |
| “Ứng dụng đã có message bean nhưng mất luôn metrics” | Di chuyển `@ConditionalOnMissingBean(MessageService.class)` từ outer xuống bean mặc định. |
| “details vẫn không có dù property details=true” | Kiểm tra cả outer `demo.auto` và nested `demo.metrics` trước. |
| “Thiếu SDK optional làm app lỗi load class” | Cô lập chữ ký SDK trong nested config có `@ConditionalOnClass`. |
| “Log không thấy @Bean details” | Dùng condition report và kiểm tra chính tên method; đừng chỉ xem lớp ngoài. |

## 11. Câu hỏi tự đánh giá

**1. Điều kiện outer không khớp nhưng điều kiện @Bean bên trong khớp, bean có được đăng ký không?** Không, theo đường xử lý cấu hình qua outer; method không vượt được cổng ngoài.

**2. Điều kiện trên nested config không khớp, bean đặt trực tiếp ở outer còn tồn tại không?** Có thể có, miễn outer và các điều kiện riêng của bean đó đều khớp.

**3. Tại sao nên dùng static nested @Configuration cho SDK optional?** Để cô lập cấu hình phụ thuộc class có thể vắng trên runtime và tránh rủi ro JVM xử lý method signatures quá sớm.

**4. @ConditionalOnMissingBean đặt ở phương thức có ảnh hưởng mọi bean khác trong cùng class không?** Không; nó bảo vệ bean definition của phương thức đó.

**5. Nếu demo.details=true nhưng demo.metrics=false?** Bean details trong nhóm metrics không tồn tại vì điều kiện nested không khớp.

**6. Nếu demo.auto=false và demo.custom=true?** Bean tùy chỉnh do ứng dụng khai báo vẫn có mặt; các bean của auto-configuration mẫu bị loại.

**7. Nếu ứng dụng có MessageService custom và metrics được bật?** Bean mặc định MessageService back off, nhưng MetricsService vẫn có thể tồn tại.

**8. Có nên dùng @ConditionalOnClass trên một @Bean trả về class SDK tùy chọn để bảo đảm an toàn class loading không?** Không nên chỉ dựa vào điều đó; hãy tách method vào lớp cấu hình lồng có class condition.

**9. Điều kiện trên lớp lồng có tự động bị outer chặn nếu lớp lồng được @Import trực tiếp từ nơi khác không?** Không thể mặc định; đường đăng ký độc lập có thể khiến điều kiện outer không được áp dụng.

**10. Muốn biết tại sao một bean không được đăng ký, cần xem gì?** Xác nhận imports/exclusions, điều kiện ở lớp ngoài, nhóm lồng và bean method, cùng Condition Evaluation Report và các bean definitions hiện có.

## Tài liệu chính thức

- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot 3.5 — `ConditionalOnClass` API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Framework — `@Conditional` và cấu hình Java: https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html

**Kết luận:** vị trí đặt `@Conditional` quyết định **phạm vi cấu hình bị bỏ qua**. Dùng điều kiện ở outer cho tiền đề chung, ở nested `@Configuration` cho nhóm bean và sự phụ thuộc optional, ở từng `@Bean` cho quyết định riêng như back-off. Mọi điều kiện trên đường từ outer đến bean phải cùng cho phép; đây là cách thiết kế auto-configuration dễ dự đoán, ít vô hiệu hóa thừa và dễ chẩn đoán.