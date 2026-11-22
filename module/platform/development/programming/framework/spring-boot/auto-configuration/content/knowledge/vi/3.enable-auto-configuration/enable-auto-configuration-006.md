# DeferredImportSelector và lý do Spring Boot trì hoãn xử lý auto-configuration

## 1. Mục tiêu của bài học

Spring Boot có thể tự đăng ký bean mặc định nhờ các lớp **auto-configuration**, nhưng thường phải ưu tiên lựa chọn do ứng dụng tự khai báo. Cơ chế `DeferredImportSelector` là một mảnh ghép quan trọng giúp đạt được điều đó: nó cho phép việc chọn và xử lý các cấu hình được import diễn ra **sau lượt xử lý các lớp `@Configuration` thông thường** trong quá trình phân tích cấu hình của Spring.

Sau bài này, bạn có thể:

- Phân biệt `@Import` một lớp cấu hình, `ImportSelector` và `DeferredImportSelector`.
- Giải thích đường đi từ `@SpringBootApplication`/`@EnableAutoConfiguration` tới `AutoConfigurationImportSelector` và danh sách auto-configuration ứng viên.
- Hiểu vì sao cần trì hoãn: **bean definition do ứng dụng cung cấp cần có cơ hội được đăng ký trước khi auto-configuration xét điều kiện dựa trên bean**, đặc biệt `@ConditionalOnMissingBean`.
- Phân biệt **chọn import**, **đánh giá điều kiện**, **đăng ký bean definition** và **khởi tạo bean**; việc “deferred” không có nghĩa chạy bất đồng bộ, chạy sau khi ứng dụng sẵn sàng hoặc tự khởi tạo bean muộn.
- Tự viết một auto-configuration với Java 17+ và kiểm chứng việc “back off” bằng các lệnh chạy cụ thể.

Bối cảnh: đây là bài về **kích hoạt auto-configuration** trong Spring Boot, tập trung vào ý nghĩa của cơ chế import trì hoãn. Những điều kiện về classpath, property hoặc bean chỉ được đề cập ở mức cần thiết để làm rõ vì sao quá trình chọn import phải đúng thứ tự.

## 2. Từ @Import tới DeferredImportSelector

Spring Framework hỗ trợ annotation `@Import` để đưa thêm cấu hình vào quá trình xử lý các lớp cấu hình. Có ba trường hợp nên phân biệt:

| Hình thức | Spring làm gì? | Khi nào hữu ích? |
| --- | --- | --- |
| `@Import(AdditionalConfig.class)` | Import một lớp cấu hình được chỉ định trực tiếp. | Bạn đã biết chính xác lớp nào cần đưa vào. |
| `@Import(CustomImportSelector.class)`, selector triển khai `ImportSelector` | Gọi selector để chọn danh sách tên lớp cần import. | Danh sách import phụ thuộc annotation metadata hay logic lựa chọn. |
| `@Import(CustomDeferredSelector.class)`, selector triển khai `DeferredImportSelector` | Ghi nhận selector và xử lý việc chọn import theo **pha deferred** sau khi các cấu hình thông thường đã được phân tích. | Các import phụ thuộc điều kiện hoặc cần được xét sau cấu hình do ứng dụng khai báo. |

Ví dụ minh họa một `ImportSelector` thông thường:

~~~java
import org.springframework.context.annotation.ImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class BasicImportSelector implements ImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {"com.example.config.ExtraConfiguration"};
    }
}
~~~

Đây chỉ là **một class minh họa API**, chưa phải chương trình tự chạy: `ExtraConfiguration` cần thực sự tồn tại và một lớp cấu hình cần import selector bằng `@Import(BasicImportSelector.class)`. Điểm chính là `selectImports(...)` trả về **tên lớp cấu hình**; nó không trực tiếp trả về object bean, không gọi constructor bean và không tự khởi động context.

`DeferredImportSelector` là biến thể của `ImportSelector`:

~~~java
import org.springframework.context.annotation.DeferredImportSelector;
import org.springframework.core.type.AnnotationMetadata;

public class DelayedImportSelector implements DeferredImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata metadata) {
        return new String[] {"com.example.config.ExtraConfiguration"};
    }
}
~~~

Với các lớp minh họa trên, phần khác biệt về thời điểm là: Spring không xử lý danh sách import của `DelayedImportSelector` ngay tại vị trí gặp annotation như selector thông thường; nó **thu thập selector để xử lý về sau trong quá trình phân tích configuration classes**. API còn hỗ trợ `Ordered`/`@Order` để điều khiển thứ tự giữa các deferred selector, và `getImportGroup()` để gom kết quả trước khi xuất danh sách import cuối.

Cụm “trì hoãn xử lý sau các `@Configuration`” cần hiểu đúng phạm vi: đây là **một pha trong xử lý configuration metadata và bean definitions của lần refresh hiện tại**, không phải chờ đến `ApplicationReadyEvent` hay sau `ApplicationRunner`.

## 3. AutoConfigurationImportSelector nằm ở đâu?

Trong Spring Boot, annotation `@SpringBootApplication` bao gồm khả năng bật auto-configuration thông qua `@EnableAutoConfiguration`. Đường đi khái niệm:

~~~text
@SpringBootApplication
  └── @EnableAutoConfiguration
        └── @Import(AutoConfigurationImportSelector.class)
              └── implements DeferredImportSelector
                    └── lựa chọn/nhóm/sắp xếp các auto-configuration
                          └── nhập các @AutoConfiguration phù hợp
                                └── xét @Conditional trên lớp / @Bean
                                      └── đăng ký bean definitions phù hợp
~~~

`AutoConfigurationImportSelector` là lớp hạ tầng của Spring Boot, triển khai `DeferredImportSelector` cùng các callback như `EnvironmentAware` và `BeanFactoryAware`. Nó đọc các lựa chọn loại trừ và tìm những lớp auto-configuration ứng viên. Với Spring Boot 3.x, các ứng viên do thư viện công bố qua tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng hợp lệ trong tài nguyên này chỉ định tên đầy đủ của một lớp auto-configuration, chẳng hạn:

~~~text
com.example.autoconfig.GreeterAutoConfiguration
~~~

Đây là **tên tệp metadata nằm trong JAR/classpath**, không phải bean, không phải file application.properties và cũng không phải một `@ComponentScan`. Một dependency có thể chứa tài nguyên này để Boot tìm được các cấu hình do dependency cung cấp. Trong Spring Boot hiện đại, nên đăng ký lớp auto-configuration qua cơ chế `AutoConfiguration.imports` đúng phiên bản, thay vì cho component scanning tình cờ quét nó.

### Các công đoạn, tránh gộp làm một

1. **Phát hiện ứng viên:** Boot thu thập tên auto-configuration do các thư viện trên classpath đăng ký. Một lớp có trong file `AutoConfiguration.imports` chỉ là **ứng viên**.
2. **Loại trừ và lọc sơ bộ:** Boot xét các lớp cần loại trừ, bộ lọc/metadata có thể loại bỏ ứng viên không phù hợp, ví dụ khi thiếu class bắt buộc. Lớp bị loại ở đây sẽ không được import như cấu hình được chọn.
3. **Nhóm và sắp xếp:** Boot có thể nhóm kết quả từ các selector và sắp xếp auto-configuration theo quan hệ trước/sau để quyết định **thứ tự xử lý cấu hình**.
4. **Phân tích các lớp đã import:** Spring tiếp tục xử lý metadata của auto-configuration, bao gồm các `@Conditional` ở cấp lớp, nested configuration và phương thức `@Bean`.
5. **Đăng ký bean definitions, rồi tạo bean:** Những định nghĩa bean hợp lệ mới được đưa vào context. Việc tạo instance bean thuộc giai đoạn khác và còn phụ thuộc scope, lazy initialization, dependency và bean lifecycle.

Không nên nói “có trong imports file thì mọi bean sẽ xuất hiện”: có thể bị exclude, filter, điều kiện không khớp hoặc xảy ra lỗi ở giai đoạn tạo bean. Cũng không nên nói “selector tạo bean”: selector chọn **những lớp sẽ tham gia cấu hình**.

## 4. Vì sao phải trì hoãn auto-configuration?

Động cơ quan trọng nhất là **ưu tiên cấu hình ứng dụng so với cấu hình mặc định của framework**.

Hãy tưởng tượng thư viện cung cấp một dịch vụ gửi thông báo. Ứng dụng có thể muốn tự định nghĩa `NotificationSender`. Auto-configuration chỉ nên tạo sender mặc định khi không có bean phù hợp. Thông thường có một phương thức:

~~~java
@Bean
@ConditionalOnMissingBean(NotificationSender.class)
NotificationSender defaultNotificationSender() {
    return new DefaultNotificationSender();
}
~~~

Đây là đoạn mã minh họa; `NotificationSender` và `DefaultNotificationSender` là các type giả định, cần khai báo mới có thể biên dịch. Quy tắc mong muốn:

- Nếu ứng dụng đã khai báo `@Bean NotificationSender customSender()`, Boot **lùi bước** và không đăng ký sender mặc định tương ứng.
- Nếu ứng dụng chưa khai báo, Boot có thể đăng ký bean mặc định, miễn các điều kiện khác cũng khớp.

`@ConditionalOnMissingBean` không đi ngược thời gian để xem mọi bean sẽ tồn tại trong tương lai. Theo tài liệu Spring Boot, điều kiện bean cần dựa trên **bean definitions đã được xử lý tới thời điểm đánh giá**. Nếu auto-configuration được xử lý quá sớm, nó có thể chưa nhìn thấy một bean do người dùng tự định nghĩa, từ đó tạo cấu hình mặc định ngoài ý muốn.

`DeferredImportSelector` giải quyết vấn đề thứ tự ở tầng import: các lựa chọn import auto-configuration được xử lý **sau** cấu hình thông thường. Vì vậy, auto-configuration có cơ sở để thấy các bean definitions của ứng dụng khi áp dụng điều kiện “missing bean”. Tài liệu Boot vì thế khuyến nghị đặt `@ConditionalOnBean` và `@ConditionalOnMissingBean` chủ yếu trên auto-configuration.

Sơ đồ so sánh logic:

~~~text
Xử lý sớm, không bảo đảm thứ tự (hình dung nguy cơ)
    1. Xét mặc định: chưa thấy NotificationSender
    2. Đăng ký defaultSender
    3. Sau đó mới xử lý @Bean customSender
       → có thể xảy ra xung đột hoặc hành vi ngoài kỳ vọng

Xử lý theo cơ chế deferred của Boot
    1. Xử lý cấu hình ứng dụng: thấy customSender
    2. Đến pha import auto-configuration
    3. Xét @ConditionalOnMissingBean(NotificationSender.class)
    4. Điều kiện không khớp → bỏ qua defaultSender
       → ứng dụng giữ quyền tùy chỉnh
~~~

Đây là giải thích **lý do kiến trúc** chứ không phải tuyên bố rằng mọi thứ tự đăng ký sai nhất định dẫn đến hai bean trùng tên. Kết quả cụ thể còn tùy điều kiện, kiểu bean, tên bean và cách người dùng đăng ký chúng.

### Tại sao không chỉ ưu tiên bằng cách đổi tên bean?

Tên bean chỉ giải quyết một phần. Điều kiện `@ConditionalOnMissingBean` có thể dựa trên type, tên, annotation và các thuộc tính tìm kiếm khác. Một bean tên `customSender` vẫn có thể là bean cùng **type** với mặc định `defaultSender`. Đây là lý do thứ tự xử lý **định nghĩa bean** mới là trọng tâm; đổi tên bean không thay thế được cơ chế back-off có điều kiện.

### Vì sao việc trì hoãn cũng tốt cho các loại điều kiện khác?

Một số auto-configuration cần biết thư viện nào tồn tại, các cấu hình liên quan, môi trường servlet/reactive, properties và bean khác. Cách chọn import theo pha deferred tạo một điểm xử lý nhất quán để lọc, sắp xếp và phối hợp nhiều auto-configuration. Tuy vậy, **không phải điều kiện nào cũng cần deferred vì cùng một lý do**: ví dụ `@ConditionalOnClass` có thể kiểm tra classpath mà không phụ thuộc bean application. Lợi ích quan trọng với bean conditions là thứ tự so với những bean definitions do ứng dụng tạo.

## 5. DeferredImportSelector.Group giúp điều gì?

Spring Framework cho phép `DeferredImportSelector` khai báo `getImportGroup()`. Group tiếp nhận kết quả từ nhiều deferred selectors và có thể phối hợp thứ tự, lọc, loại trùng hoặc chọn lại những import được phát ra. `AutoConfigurationImportSelector` sử dụng một nhóm chuyên biệt của Spring Boot để xử lý các lựa chọn auto-configuration.

Khái quát callback:

~~~text
ConfigurationClassParser
    ├── phân tích @Configuration thông thường
    ├── ghi nhận DeferredImportSelector
    └── xử lý deferred selectors
          ├── đặt selector vào group tương ứng
          ├── group.process(metadata, selector)
          └── group.selectImports()
                → danh sách Entry(metadata, importClassName)
                → tiếp tục phân tích các cấu hình được import
~~~

**Group không phải một nhóm thread**. `process` và `selectImports` tham gia xử lý metadata trong quá trình xây dựng context, không phải cơ chế parallel execution. Nếu tự viết `DeferredImportSelector.Group`, phải bảo đảm các import xuất ra có thứ tự và metadata hợp lệ, đồng thời tránh side effect phụ thuộc thứ tự tùy tiện.

`AutoConfigurationImportSelector.AutoConfigurationGroup` là chi tiết triển khai của Boot: không cần tự gọi hay tự instantiate nó trong ứng dụng. Việc nhà phát triển ứng dụng nên làm là dùng annotation và metadata công khai (`@AutoConfiguration`, imports file, conditions và các quy tắc ordering).

## 6. Thứ tự auto-configuration: @AutoConfiguration(before/after) khác gì?

Ngay cả sau pha deferred, các auto-configuration vẫn có thể cần thứ tự đối với nhau. Ví dụ cấu hình A cung cấp bean tiền đề để B áp dụng điều kiện `@ConditionalOnBean`. Spring Boot hỗ trợ:

~~~java
@AutoConfiguration(after = SomeOtherAutoConfiguration.class)
public class MyAutoConfiguration {
    // Các bean definitions và điều kiện phù hợp
}
~~~

Đây là snippet minh họa, **chưa phải một class đầy đủ**: cần import annotation đúng package và định nghĩa `SomeOtherAutoConfiguration`. Có thể dùng `before`, `after`, `beforeName`, `afterName`; annotation chuyên dụng `@AutoConfigureBefore`/`@AutoConfigureAfter` và `@AutoConfigureOrder` cũng tồn tại.

Cần phân biệt ba loại thứ tự:

| Loại thứ tự | Ý nghĩa thực tế |
| --- | --- |
| Thứ tự selector thông thường so với deferred selector | Quyết định lúc **lựa chọn và phân tích import** được thực hiện tương đối với cấu hình ứng dụng. |
| Thứ tự giữa các auto-configuration | Tác động đến **thứ tự xử lý và đăng ký bean definitions** của các auto-configuration, hữu ích cho điều kiện phụ thuộc những định nghĩa đã có. |
| Thứ tự khởi tạo bean | Do dependency graph, `@DependsOn`, eager/lazy và lifecycle quản lý; **không** được quyết định trực tiếp bởi `@AutoConfiguration(after=...)`. |

Điều kiện trên lớp và điều kiện trên phương thức cũng có thể được xử lý ở các pha khác nhau. Spring Framework có `ConfigurationCondition.ConfigurationPhase.PARSE_CONFIGURATION` và `REGISTER_BEAN`; không nên suy luận mọi điều kiện chạy tại một dòng thời gian duy nhất. Trong thực tế, hãy dùng **Condition Evaluation Report** để xem kết quả của các điều kiện.

### Những ngộ nhận về thứ tự

- **“Deferred nghĩa là tất cả bean của Boot tạo sau cùng.”** Không. Đây là cơ chế defer việc xử lý import/configuration, không phải cam kết mọi instance khởi tạo cuối cùng.
- **“after = X nghĩa là bean của X được new trước bean của tôi.”** Không. Ordering của auto-configuration tác động thứ tự định nghĩa; khởi tạo còn do phụ thuộc bean.
- **“Một @ConditionalOnMissingBean đảm bảo bỏ qua khi mọi bean trong tương lai tồn tại.”** Không. Nó dựa trên bean definitions đã được xử lý tại thời điểm condition được đánh giá.
- **“Đã dùng @AutoConfiguration thì không cần khai báo imports file.”** Với auto-configuration được đóng gói theo cơ chế Boot 3.x, vẫn cần metadata `AutoConfiguration.imports` để Boot phát hiện.

## 7. Thực hành Java 17+ / Spring Boot 3.5.0: ứng dụng thắng bean mặc định

Ví dụ sau xây dựng **auto-configuration của chính dự án**, đăng ký qua `AutoConfiguration.imports`. Ứng dụng có bean tùy chỉnh theo property `demo.user=true`. Khi bean tùy chỉnh có mặt, mặc định sẽ lùi bước. Khi auto-configuration bị vô hiệu hóa bằng một điều kiện property khác, dự án không có bean mặc định. Nhờ vậy, ba tình huống có thể quan sát được mà không cần cơ sở dữ liệu hoặc web server.

Đây là ví dụ đầy đủ với Maven và JDK 17+, không cần source code từ những bài khác.

### 7.1. Cấu trúc thư mục

~~~text
deferred-import-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── com/example/
        │       ├── api/Greeter.java
        │       ├── app/DemoApplication.java
        │       └── autoconfig/GreeterAutoConfiguration.java
        └── resources/
            ├── application.properties
            └── META-INF/spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Cố tình đặt `DemoApplication` ở `com.example.app` và `GreeterAutoConfiguration` ở `com.example.autoconfig` (hai package ngang hàng). Component scanning mặc định của `@SpringBootApplication` trong `com.example.app` không tự quét lớp auto-configuration. Nó được đưa vào thông qua **imports metadata** như cơ chế cần minh họa.

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
    <artifactId>deferred-import-demo</artifactId>
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

### 7.3. Greeter.java

Tệp `src/main/java/com/example/api/Greeter.java`:

~~~java
package com.example.api;

public interface Greeter {
    String sayHello();
}
~~~

Đây chỉ là contract Java đơn giản. **Chỉ có interface trên classpath chưa tạo bean**.

### 7.4. GreeterAutoConfiguration.java

Tệp `src/main/java/com/example/autoconfig/GreeterAutoConfiguration.java`:

~~~java
package com.example.autoconfig;

import com.example.api.Greeter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo",
        name = "auto",
        havingValue = "true",
        matchIfMissing = true
)
public class GreeterAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Greeter.class)
    Greeter defaultGreeter() {
        return () -> "AUTO";
    }
}
~~~

Hai lớp điều kiện:

- Điều kiện trên lớp: `demo.auto` mặc định cho phép cấu hình, nhưng `--demo.auto=false` sẽ loại cấu hình này.
- Điều kiện tại `@Bean`: chỉ đăng ký `defaultGreeter` khi chưa có bean `Greeter` phù hợp được nhìn thấy tại lúc xét điều kiện.

`@AutoConfiguration` bản chất cũng là một kiểu cấu hình Spring. Nó không tự đồng nghĩa “bean luôn được tạo”. Annotation cũng không thay thế việc đăng ký metadata của thư viện.

### 7.5. AutoConfiguration.imports

Tệp phải có đường dẫn chính xác:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Và nội dung:

~~~text
com.example.autoconfig.GreeterAutoConfiguration
~~~

Nếu tệp không được đóng gói vào JAR đúng chỗ, Spring Boot sẽ không phát hiện auto-configuration ví dụ qua cơ chế này. Đừng dùng `@ComponentScan` để sửa lỗi metadata: làm vậy che mất điều đang học.

### 7.6. DemoApplication.java

Tệp `src/main/java/com/example/app/DemoApplication.java`:

~~~java
package com.example.app;

import com.example.api.Greeter;
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
            name = "user",
            havingValue = "true"
    )
    Greeter userGreeter() {
        return () -> "USER";
    }

    @Bean
    ApplicationRunner printResult(ObjectProvider<Greeter> greeters) {
        return args -> {
            Greeter greeter = greeters.getIfAvailable();
            System.out.println("GREETER="
                    + (greeter == null ? "NONE" : greeter.sayHello()));
        };
    }
}
~~~

Lớp gốc là cấu hình của **ứng dụng**. Bean `userGreeter` của ứng dụng được xử lý trước auto-configuration của Boot. Khi property bật bean này, `@ConditionalOnMissingBean(Greeter.class)` tại `defaultGreeter` sẽ không khớp.

`ObjectProvider<Greeter>` cho phép lấy bean nếu có, hoặc `null` nếu không có; dùng cách này để tình huống không có `Greeter` vẫn chạy và in `NONE`. Nếu có nhiều bean cùng kiểu, `getIfAvailable()` có thể báo lỗi do không duy nhất, nhưng với đúng cấu hình mẫu các trường hợp đều có tối đa một `Greeter`.

### 7.7. application.properties

Tệp `src/main/resources/application.properties`:

~~~properties
spring.main.banner-mode=off
logging.level.root=ERROR
~~~

Không gán mặc định `demo.user` hay `demo.auto` trong file: hai property này được điều khiển bằng tham số ứng dụng bên dưới. Bạn có thể giữ nguyên cấu hình log hoặc thay đổi để quan sát condition report.

### 7.8. Đóng gói và chạy

Tại thư mục `deferred-import-demo`:

~~~bash
mvn -q -DskipTests package
java -jar target/deferred-import-demo-1.0.0.jar
~~~

Dòng do ứng dụng in:

~~~text
GREETER=AUTO
~~~

Vì ứng dụng chưa đăng ký `Greeter` tùy chỉnh và `demo.auto` không có (được cho phép nhờ `matchIfMissing=true`), auto-configuration đăng ký bean mặc định.

Chạy với bean do ứng dụng khai báo:

~~~bash
java -jar target/deferred-import-demo-1.0.0.jar --demo.user=true
~~~

Dòng do ứng dụng in:

~~~text
GREETER=USER
~~~

`userGreeter` đã được đăng ký; auto-configuration kiểm tra thiếu `Greeter` thì không khớp và **lùi bước**. Đây là kết quả phù hợp với lý do xử lý import auto-configuration theo pha deferred.

Vô hiệu hóa auto-configuration mẫu mà không bật bean tùy chỉnh:

~~~bash
java -jar target/deferred-import-demo-1.0.0.jar --demo.auto=false
~~~

Dòng do ứng dụng in:

~~~text
GREETER=NONE
~~~

Điều kiện trên lớp `GreeterAutoConfiguration` không khớp; ứng dụng không có `userGreeter`. Vì vậy không có bean `Greeter`.

Bật bean ứng dụng dù auto-configuration bị tắt:

~~~bash
java -jar target/deferred-import-demo-1.0.0.jar --demo.auto=false --demo.user=true
~~~

Dòng do ứng dụng in:

~~~text
GREETER=USER
~~~

Đây là bằng chứng rằng **cấu hình ứng dụng và auto-configuration là hai nguồn định nghĩa bean khác nhau**. Việc một auto-configuration bị loại không có nghĩa các `@Bean` của ứng dụng cũng bị loại.

Bảng tổng hợp:

| Tham số | Bean do ứng dụng | Bean mặc định | In ra |
| --- | --- | --- | --- |
| Không có | Không | Có | `GREETER=AUTO` |
| `--demo.user=true` | Có | Bị `@ConditionalOnMissingBean` bỏ qua | `GREETER=USER` |
| `--demo.auto=false` | Không | Không, điều kiện lớp không khớp | `GREETER=NONE` |
| `--demo.auto=false --demo.user=true` | Có | Không | `GREETER=USER` |

**Phạm vi suy luận:** các dòng `GREETER=...` là stdout do chương trình tự in, không bao gồm log của Spring Boot/JVM/Maven (có thể khác theo môi trường). Ví dụ mô tả cơ chế đúng theo metadata và điều kiện của Spring Boot 3.5.0; nó không có ý chứng minh callback nội bộ chỉ bằng thứ tự dòng log, vì các callback chọn import không được in ra trong ví dụ.

## 8. Cách chứng minh deferred import có hiệu lực

### Quan sát lý do condition khớp hoặc không khớp

Chạy thêm chế độ debug và cho phép log ở mức phù hợp:

~~~bash
java -jar target/deferred-import-demo-1.0.0.jar --demo.user=true --debug --logging.level.root=INFO
~~~

Tìm tên `GreeterAutoConfiguration` và `defaultGreeter` trong **Condition Evaluation Report** nếu báo cáo được log ra. Nội dung/nhãn dòng cụ thể phụ thuộc phiên bản Boot và logging. Hãy tìm nguyên nhân bean mặc định không được đăng ký vì có `Greeter` do ứng dụng cung cấp. Chạy lại không có `--demo.user=true` để đối chiếu.

Cần nhớ: report cho biết **kết quả đánh giá điều kiện**; nó không phải stack trace toàn bộ callback `ConfigurationClassParser`. Nếu muốn quan sát thực tế lúc `AutoConfigurationImportSelector` được gọi, hãy debug source bằng IDE với breakpoint trong các lớp hạ tầng Boot/Spring Framework thuộc đúng phiên bản, ví dụ `AutoConfigurationImportSelector` và lớp xử lý deferred import của parser. Đừng thêm mã sản xuất chỉ để in ra một implementation detail.

### Xác minh import metadata nằm trong JAR

Sau khi đóng gói trên hệ thống có lệnh `jar`:

~~~bash
jar tf target/deferred-import-demo-1.0.0.jar
~~~

Tìm mục tài nguyên bên trong `BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Vì output `jar tf` liệt kê nhiều file, không có một stdout cố định; chỉ cần xác nhận đường dẫn metadata tồn tại trong JAR.

Nếu metadata không có, kiểm tra tên tệp, vị trí `src/main/resources` và quá trình build. Nếu tệp có mà vẫn không thấy bean, kiểm tra property, annotation conditions, exclusions và report thay vì suy ra deferred selector đã hỏng.

### Phân biệt “được import” và “bean đã khởi tạo”

Một auto-configuration có thể được chọn và phân tích, nhưng một bean bên trong vẫn không được đăng ký vì `@ConditionalOnMissingBean`. Hoặc định nghĩa bean có thể được đăng ký nhưng instance bị trì hoãn vì `@Lazy`. Hoặc quá trình tạo instance có thể thất bại do thiếu dependency. Đừng dùng duy nhất một dấu hiệu (classpath có starter, class có trong imports file, condition dương tính ở cấp lớp) để kết luận về toàn bộ bean graph.

## 9. Tại sao không nên tự áp dụng DeferredImportSelector cho mọi cấu hình?

`DeferredImportSelector` phù hợp khi thư viện cần chọn tập cấu hình có điều kiện ở pha trễ, đặc biệt trường hợp giống auto-configuration. Còn trong code ứng dụng, nhiều nhu cầu đơn giản hơn có thể giải quyết bằng `@Configuration`, `@Bean`, `@Import` hoặc component scanning.

Việc tự tạo deferred selector thường làm tăng độ phức tạp: thứ tự giữa selector, metadata, cách áp dụng condition, grouping và tính rõ ràng của API. Nếu chỉ muốn cho phép người dùng thay bean mặc định trong starter riêng, cách công khai và dễ bảo trì nhất thường là:

1. Viết lớp `@AutoConfiguration` đặt điều kiện thích hợp.
2. Đăng ký nó đúng bằng `AutoConfiguration.imports`.
3. Đặt `@ConditionalOnMissingBean` ở bean cần lùi bước và trả về type đủ cụ thể.
4. Nếu nhiều auto-configuration phụ thuộc nhau, chỉ định ordering bằng `before`/`after` phù hợp.
5. Tạo test hoặc ví dụ chạy để kiểm tra cả trường hợp có và không có bean của người dùng.

**Không được viết một selector tùy chỉnh chỉ để tạo instance bean bằng tay**; selector trả về class names và không thay thế Spring IoC container.

## 10. Những lỗi và cách hiểu sai thường gặp

### Nhầm “deferred” với async / lazy

Deferred ở đây là **lịch xử lý import metadata trong một lượt cấu hình**. Nó không sử dụng thread pool, không có `CompletableFuture`, không bảo đảm bean `@Lazy` và không trì hoãn đến sau khi nhận request đầu tiên.

### Nhầm auto-configuration ordering với bean dependency ordering

`@AutoConfiguration(after = X.class)` giúp kiểm soát thứ tự áp dụng auto-configuration. Nó không cưỡng bức bean của X phải hoàn thành khởi tạo trước bean của cấu hình hiện tại. Sử dụng dependency injection/`@DependsOn` nếu có yêu cầu khởi tạo cụ thể và hiểu rõ lý do.

### Đặt @ConditionalOnMissingBean trong một @Configuration ứng dụng tùy ý

Điều kiện chỉ biết các định nghĩa đã xử lý tại thời điểm nó được kiểm tra. Nếu dùng bean conditions trên các cấu hình ứng dụng có thứ tự không rõ, có thể nhận kết quả khác mong muốn. Tài liệu Boot khuyến nghị những điều kiện này ở auto-configuration vì cơ chế load sau cấu hình của người dùng.

### Để auto-configuration trong package component scan

Nếu cùng một lớp auto-configuration vừa được component scanning phát hiện vừa được đưa qua imports metadata, ý nghĩa thử nghiệm về thứ tự deferred trở nên khó kiểm soát. Theo tài liệu Boot, auto-configuration nên nằm ngoài component scan và được phát hiện qua imports file; không bật quét component bổ sung bên trong auto-configuration một cách tùy tiện.

### Quên AutoConfiguration.imports

`@AutoConfiguration` trên một class không tự đặt class đó vào danh sách ứng viên ở classpath. Kiểm tra chính xác đường dẫn, nội dung từng dòng và packaging.

### Thấy @ConditionalOnMissingBean không khớp thì tưởng là lỗi

Nếu ứng dụng có bean cùng kiểu phù hợp, đó chính là hành vi “back off” mong muốn. Hãy đọc condition report và quan sát bean thực sự trong context.

### Dùng ordering để “chữa” mọi lỗi condition

Một condition fail có thể do thiếu class, property không đúng, profile khác, bean đã tồn tại hoặc auto-configuration bị exclude. `before`/`after` chỉ liên quan đến thứ tự auto-configuration; trước khi chỉnh thứ tự, cần biết lý do condition fail.

### Nghĩ rằng mọi cấu hình mặc định đều cho phép override

Không phải mọi auto-configuration đều có `@ConditionalOnMissingBean` cho mọi bean. Cần xem logic điều kiện thực tế của lớp thuộc phiên bản Boot và thư viện đang dùng. “Ứng dụng ưu tiên” là nguyên tắc thiết kế rộng, nhưng hiệu ứng cụ thể phụ thuộc điều kiện ở từng bean.

## 11. Câu hỏi tự đánh giá

1. **`ImportSelector` trả về gì?** Danh sách tên lớp cần import, không phải instance bean.
2. **`DeferredImportSelector` khác selector thường ở đâu?** Nó được xử lý ở pha deferred sau lượt xử lý configuration classes thông thường.
3. **Tại sao Boot dùng cơ chế này?** Để phối hợp các auto-configuration sau cấu hình ứng dụng, đặc biệt cho điều kiện dựa trên các bean definitions đã có, và để nhóm/lọc/sắp xếp ứng viên.
4. **`AutoConfigurationImportSelector` có tự gọi `@Bean` không?** Không; nó lựa chọn cấu hình. Spring container xử lý bean definitions và tạo instance ở các pha tương ứng.
5. **Thêm lớp vào `AutoConfiguration.imports` có bảo đảm bean được tạo không?** Không; còn exclude, filter, conditions và quá trình khởi tạo.
6. **Tại sao `@ConditionalOnMissingBean` có thể phụ thuộc thứ tự?** Vì nó kiểm tra những bean definitions đã được xử lý tính đến thời điểm đánh giá.
7. **`@AutoConfiguration(after = X.class)` có điều khiển thứ tự khởi tạo instance bean không?** Không; nó điều khiển thứ tự áp dụng cấu hình.
8. **Khi chạy demo với `--demo.user=true`, tại sao in USER?** Bean do ứng dụng khai báo được đăng ký, khiến điều kiện thiếu `Greeter` của bean mặc định không khớp.
9. **Nếu `--demo.auto=false --demo.user=true` thì có bean không?** Có bean do ứng dụng cung cấp; điều kiện tắt auto-configuration không ảnh hưởng bean đó.
10. **“Defer” ở đây có chờ ApplicationReadyEvent không?** Không, nó diễn ra trong quá trình xử lý configuration của lần refresh context.

## Tài liệu tham khảo chính thức

- Spring Framework — `DeferredImportSelector` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/DeferredImportSelector.html
- Spring Framework — `ImportSelector` Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ImportSelector.html
- Spring Boot — `AutoConfigurationImportSelector` API: https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
- Spring Boot — Auto-configuration: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html

**Ghi nhớ:** `DeferredImportSelector` giúp Spring Boot xử lý việc import auto-configuration **sau cấu hình ứng dụng**, để các điều kiện như `@ConditionalOnMissingBean` có thể quan sát lựa chọn do ứng dụng khai báo và chỉ thêm phần mặc định còn thiếu. Đây là thứ tự **phân tích cấu hình và đăng ký bean definition**, không phải cơ chế khởi tạo bean bất đồng bộ hay muộn hơn toàn bộ ứng dụng.