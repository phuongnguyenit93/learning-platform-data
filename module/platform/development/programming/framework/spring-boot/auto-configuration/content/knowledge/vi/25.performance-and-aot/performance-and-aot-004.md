# Phân biệt giảm số ứng viên với trì hoãn khởi tạo bean

## 1. Hai cách tối ưu thường bị nhầm lẫn

Khi ứng dụng Spring Boot khởi động chậm, có thể thấy hai nhóm giải pháp:

- **Giảm số ứng viên auto-configuration hoặc cấu hình được áp dụng:** loại bỏ những cấu hình không cần thiết trước khi Spring phân tích sâu và đăng ký bean definition.
- **Trì hoãn khởi tạo bean (lazy initialization):** giữ bean definition trong ApplicationContext nhưng chỉ tạo object khi có yêu cầu sử dụng.

Hai giải pháp tác động vào hai giai đoạn khác nhau. Giảm ứng viên có thể giảm công việc discovery, đọc metadata, phân tích cấu hình, đánh giá condition và đăng ký bean. Lazy initialization chủ yếu trì hoãn việc tạo instance và thực thi quá trình khởi tạo của bean.

Nếu chỉ bật lazy initialization, ứng dụng vẫn có thể phải đọc và xử lý cùng một danh sách auto-configuration. Nếu loại bỏ một auto-configuration, các bean definition của cấu hình đó không được đăng ký. Đây là khác biệt quan trọng khi tối ưu một custom starter hoặc một ứng dụng có nhiều dependency.

Bài dùng **Java 17 và Spring Boot 3.3.13** làm baseline minh họa. Khi áp dụng cho dự án khác, cần kiểm tra tài liệu của đúng release line.

## 2. Phân biệt candidate, condition, bean definition và bean instance

Spring xử lý cấu hình qua nhiều bước. Không nên gọi tất cả các bước này là “tạo bean”.

| Khái niệm | Ý nghĩa | Câu hỏi tương ứng |
| --- | --- | --- |
| Auto-configuration candidate | Class được phát hiện từ danh sách imports và được xem xét để áp dụng | Class cấu hình nào sẽ được xem xét? |
| Condition evaluation | Đánh giá điều kiện classpath, property, bean, web context hoặc điều kiện tùy chỉnh | Cấu hình có đủ điều kiện không? |
| Bean definition | Metadata mô tả bean đã được đăng ký trong BeanFactory | Container biết bean này tồn tại với tên/type/scope nào? |
| Bean instance | Object thực tế được tạo từ bean definition | Constructor hoặc factory method đã chạy chưa? |

Một class có thể là candidate nhưng bị loại bởi condition. Một bean definition có thể tồn tại nhưng chưa có object instance vì được đánh dấu lazy. Một bean singleton có thể được tạo sớm khi một singleton eager khác cần inject nó.

Vì vậy, khi nói “giảm số bean”, cần chỉ rõ đang muốn giảm:

- Số auto-configuration candidate được xem xét.
- Số cấu hình vượt qua condition.
- Số bean definition được đăng ký.
- Số instance được khởi tạo trong lúc startup.
- Hay số instance thực sự được dùng trong suốt vòng đời ứng dụng.

## 3. Nhìn theo pipeline khởi động

Quy trình đơn giản hóa của auto-configuration:

~~~text
AutoConfiguration.imports
          |
          v
Tập hợp auto-configuration candidates
          |
          v
Loại exclusions và early filters
(metadata / AutoConfigurationImportFilter)
          |
          v
Phân tích configuration còn lại
          |
          v
Đánh giá @Conditional...
          |
          v
Đăng ký bean definitions
          |
          v
Tạo eager singleton instances
          |
          +---- Lazy bean: chờ lần đầu được yêu cầu
~~~

Các giai đoạn này có tác động hiệu năng khác nhau:

1. **Discovery/filtering:** quyết định class nào được xem xét. Loại candidate sớm có thể tránh đọc bytecode và phân tích những cấu hình không liên quan.
2. **Condition/registration:** quyết định cấu hình hoặc bean method có được áp dụng và đăng ký bean definition không.
3. **Instantiation:** constructor, factory method, dependency injection, post-processors và lifecycle callbacks tạo object.
4. **First use:** bean lazy được khởi tạo khi ứng dụng lần đầu yêu cầu bean hoặc gọi qua proxy/provider.

Lazy initialization tác động chủ yếu ở bước 3 và 4. Nó không tự loại candidate khỏi bước 1.

## 4. Giảm số auto-configuration candidate

### 4.1. Hiểu danh sách candidate trong Spring Boot 3.x

Trong Spring Boot 3.x, auto-configuration của một thư viện được công bố trong resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
com.acme.reports.autoconfigure.ReportsWebAutoConfiguration
com.acme.reports.autoconfigure.ReportsMetricsAutoConfiguration
~~~

Mỗi dòng là một auto-configuration class được công bố. Spring Boot đọc các resource từ dependency JAR để tập hợp candidate.

Không nên đưa mọi cấu hình có thể tưởng tượng vào imports. Hãy tách cấu hình theo tích hợp thực sự cần thiết, ví dụ JDBC, web, metrics hoặc messaging, để ứng dụng chỉ cần một nhóm tính năng không phải phân tích các nhánh không liên quan.

Auto-configuration nên được nạp qua imports resource và không nên bị component scan của ứng dụng quét như configuration thông thường. Tránh đặt package auto-configuration bên trong vùng component scan của ứng dụng tiêu thụ; tránh dùng component scan rộng từ bên trong auto-configuration. Dùng @Import tường minh cho các cấu hình liên quan.

### 4.2. Loại cấu hình không cần bằng exclusions

Nếu ứng dụng biết rõ một auto-configuration không cần thiết, có thể loại nó khỏi danh sách được áp dụng.

Dùng annotation:

~~~java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class ReportsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportsApplication.class, args);
    }
}
~~~

Nếu không muốn tham chiếu class trực tiếp, có thể dùng tên đầy đủ:

~~~java
@SpringBootApplication(
        excludeName = "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class ReportsApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReportsApplication.class, args);
    }
}
~~~

Hoặc cấu hình property:

~~~properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
~~~

Exclusion phù hợp khi ứng dụng có chủ đích không dùng một integration. Không loại cấu hình chỉ vì tên nó có vẻ không cần thiết; hãy xác nhận không có bean hoặc integration khác phụ thuộc vào cấu hình đó.

Exclusion làm cấu hình bị loại khỏi tập cấu hình được nhập. Nó khác lazy initialization: không có bean definition mặc định nào từ auto-configuration bị loại.

### 4.3. Dùng starter tối thiểu và dependency đúng mục đích

Một starter thường kéo theo nhiều dependency. Nếu starter luôn đưa JDBC, messaging, web và metrics vào classpath dù người dùng chỉ cần core API, Spring Boot sẽ phải xử lý thêm các ứng viên auto-configuration liên quan.

Khi thiết kế custom starter:

- Chỉ đưa dependency cần cho use case mặc định.
- Đánh dấu dependency tích hợp tùy chọn là optional trong module auto-configure khi phù hợp.
- Tách starter theo nhóm tích hợp nếu các nhóm có thể dùng độc lập.
- Không đưa dependency nặng vào classpath chỉ để cung cấp một tính năng hiếm khi dùng.
- Kiểm tra runtime dependency tree của ứng dụng tiêu thụ, không chỉ nhìn POM của module thư viện.

Giảm dependency có thể đồng thời giảm số class trên classpath, số auto-configuration candidate có khả năng khớp và chi phí class loading.

### 4.4. Early filtering bằng auto-configuration metadata

Spring Boot có cơ chế lọc một số auto-configuration rất sớm. Annotation processor của Boot thu thập các condition được hỗ trợ và sinh file:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Khi metadata này có trong JAR, Spring Boot có thể dùng nó để loại sớm những auto-configuration không phù hợp. Một số điều kiện như kiểm tra classpath có thể được đánh giá bằng metadata trước khi bytecode của auto-configuration được đọc.

Điều này đặc biệt hữu ích cho thư viện có nhiều auto-configuration và nhiều optional dependency. Nếu class cần thiết không có trên classpath, candidate tương ứng có thể bị loại sớm.

Để bật annotation processor trong Maven, thêm vào module auto-configure:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.12.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        <version>3.3.13</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Với Gradle:

~~~groovy
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-autoconfigure-processor")
}
~~~

Sau khi build, kiểm tra file metadata trong output:

~~~text
target/classes/META-INF/spring-autoconfigure-metadata.properties
~~~

Tên file này khác với configuration metadata dành cho IDE:

~~~text
META-INF/spring-configuration-metadata.json
~~~

File JSON mô tả property, type, description và gợi ý cấu hình. File autoconfigure metadata hỗ trợ việc lọc auto-configuration. Không nhầm hai mục đích.

Không phải mọi condition tùy chỉnh đều có thể được đánh giá ở bước early filtering. Các condition không được processor mô tả vẫn cần được xử lý ở giai đoạn configuration parsing thông thường.

### 4.5. AutoConfigurationImportFilter là cơ chế mức thấp

Spring Boot cung cấp interface:

~~~java
org.springframework.boot.autoconfigure.AutoConfigurationImportFilter
~~~

Filter nhận danh sách class candidate và metadata, sau đó trả về mảng boolean cho biết candidate nào được import. Interface này được thiết kế để loại auto-configuration trước khi bytecode của class được đọc.

Filter tùy chỉnh có thể được đăng ký qua resource META-INF/spring.factories, ví dụ:

~~~properties
org.springframework.boot.autoconfigure.AutoConfigurationImportFilter=\
com.acme.reports.autoconfigure.ReportsImportFilter
~~~

Mỗi phần tử trong mảng kết quả phải tương ứng với một candidate đầu vào; không thay đổi danh sách đầu vào. Filter phải nhẹ, xác định và không tạo side effect.

Trong phần lớn thư viện, nên dùng built-in conditions và annotation processor của Spring Boot. Chỉ viết AutoConfigurationImportFilter khi có quy tắc lọc ở mức candidate mà các cơ chế chuẩn không biểu đạt được. Một filter tùy chỉnh sai có thể vô tình loại cấu hình cần thiết và làm ứng dụng thiếu bean khó chẩn đoán.

### 4.6. Condition không phải lazy initialization

Các annotation như:

~~~java
@ConditionalOnClass(ReportSdk.class)
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true"
)
@ConditionalOnMissingBean(ReportClient.class)
~~~

quyết định cấu hình hoặc bean method có được áp dụng hay không.

Nếu condition không khớp, bean tương ứng không được đăng ký. Đây là việc giảm cấu hình/bean definition.

Nếu condition khớp nhưng bean được đánh dấu @Lazy, bean definition vẫn được đăng ký và object được tạo khi có yêu cầu. Đây là việc trì hoãn instance creation.

Condition ở cấp class có thể giúp bỏ qua toàn bộ configuration class; condition ở cấp method có thể chỉ ngăn một bean cụ thể được đăng ký. Hãy đặt condition ở phạm vi nhỏ nhất phù hợp với logic để tránh loại quá nhiều cấu hình.

### 4.7. Ordering không làm giảm candidate

Các annotation:

~~~java
@AutoConfigureBefore(...)
@AutoConfigureAfter(...)
@AutoConfigureOrder(...)
~~~

chỉ sắp xếp thứ tự áp dụng auto-configuration. Chúng không loại candidate và không làm bean lazy.

Không dùng ordering annotation như một biện pháp tối ưu số lượng cấu hình. Chỉ dùng khi hai cấu hình thực sự có quan hệ thứ tự về bean definitions hoặc condition.

## 5. Trì hoãn khởi tạo bean bằng lazy initialization

### 5.1. Lazy bean vẫn tồn tại trong container

Khi một bean được đánh dấu lazy:

~~~java
@Bean
@Lazy
ReportClient reportClient() {
    return new ReportClient();
}
~~~

Spring vẫn đăng ký bean definition. Khi ApplicationContext refresh, container không tạo singleton instance đó ngay. Instance được tạo khi có yêu cầu đầu tiên.

Có thể hình dung:

| Thời điểm | Bean definition | Singleton instance |
| --- | --- | --- |
| Sau khi context refresh | Có | Chưa có |
| Sau lần đầu getBean | Có | Có |
| Những lần getBean tiếp theo | Có | Trả về cùng singleton instance |

Lazy initialization không xóa tên bean, type, scope hay metadata của bean khỏi container.

### 5.2. Lazy cho từng bean

Có thể đánh dấu method @Bean:

~~~java
@Configuration(proxyBeanMethods = false)
public class ReportsConfiguration {

    @Bean
    @Lazy
    ReportClient reportClient() {
        return new ReportClient();
    }
}
~~~

Hoặc đánh dấu class configuration:

~~~java
@Configuration(proxyBeanMethods = false)
@Lazy
public class OptionalReportsConfiguration {

    @Bean
    ReportClient reportClient() {
        return new ReportClient();
    }

    @Bean
    ReportHistoryClient historyClient() {
        return new ReportHistoryClient();
    }
}
~~~

Các bean được định nghĩa trong configuration này sẽ mặc định lazy, trừ khi có cấu hình cụ thể khác. Dùng cách này khi cả nhóm bean đều là tính năng tùy chọn và có thể chưa được dùng trong một số lần chạy.

### 5.3. Bật lazy initialization toàn ứng dụng

Spring Boot cho phép bật lazy initialization toàn cục:

~~~yaml
spring:
  main:
    lazy-initialization: true
~~~

Hoặc:

~~~properties
spring.main.lazy-initialization=true
~~~

Khi bật, nhiều bean của ứng dụng sẽ được khởi tạo khi cần thay vì khi startup. Có thể loại một bean khỏi chế độ lazy bằng:

~~~java
@Bean
@Lazy(false)
CriticalStartupVerifier criticalStartupVerifier() {
    return new CriticalStartupVerifier();
}
~~~

Global lazy initialization là thay đổi hành vi rộng. Trước khi bật trong production, cần kiểm tra các bean cần thiết cho readiness, startup validation, security, migrations, scheduled tasks và các dependency được khởi tạo gián tiếp.

### 5.4. Dependency eager có thể kéo lazy bean lên lúc startup

Một điểm dễ gây hiểu nhầm: đánh dấu bean là lazy không đảm bảo nó luôn được trì hoãn.

Ví dụ:

~~~java
@Bean
@Lazy
ReportClient reportClient() {
    return new ReportClient();
}

@Bean
ReportFacade reportFacade(ReportClient reportClient) {
    return new ReportFacade(reportClient);
}
~~~

ReportFacade là singleton eager. Khi Spring tạo ReportFacade, nó cần ReportClient để inject constructor/method parameter. Vì vậy ReportClient cũng phải được tạo trong lúc startup.

Để thật sự trì hoãn việc lấy dependency, có thể inject ObjectProvider:

~~~java
@Bean
ReportFacade reportFacade(ObjectProvider<ReportClient> clients) {
    return new ReportFacade(clients);
}
~~~

ReportFacade được tạo lúc startup nhưng ReportClient chỉ được lấy khi code gọi:

~~~java
ReportClient client = clients.getObject();
~~~

Một cách khác là đánh dấu injection point bằng @Lazy để Spring inject proxy:

~~~java
public ReportFacade(@Lazy ReportClient reportClient) {
    this.reportClient = reportClient;
}
~~~

Proxy trì hoãn việc resolve target cho đến khi phương thức được gọi. Cần hiểu proxy và lifecycle để tránh kỳ vọng sai, nhất là với type final hoặc cách gọi không tương thích proxy.

### 5.5. Khi nào nên dùng ObjectProvider?

ObjectProvider phù hợp khi bean chỉ được cần trong một nhánh nghiệp vụ:

~~~java
@Component
public class ExportService {

    private final ObjectProvider<PdfRenderer> renderers;

    public ExportService(ObjectProvider<PdfRenderer> renderers) {
        this.renderers = renderers;
    }

    public byte[] exportPdf(Report report) {
        PdfRenderer renderer = renderers.getObject();
        return renderer.render(report);
    }
}
~~~

Nếu ứng dụng chỉ xuất CSV trong một số lần chạy, PdfRenderer có thể không cần được tạo cho đến khi nhánh PDF được gọi.

ObjectProvider cũng cung cấp các thao tác như getIfAvailable và getIfUnique khi dependency là tùy chọn hoặc có nhiều candidate. Chọn method theo contract; đừng dùng getIfAvailable để che giấu một dependency thực sự bắt buộc.

## 6. So sánh trực tiếp hai chiến lược

| Tiêu chí | Giảm candidate/condition không khớp | Lazy initialization |
| --- | --- | --- |
| Candidate trong danh sách imports | Có thể bị loại | Vẫn được giữ |
| Configuration được phân tích | Có thể được bỏ qua sớm | Thường vẫn được xử lý |
| Bean definition | Không đăng ký nếu cấu hình/bean bị loại | Vẫn đăng ký |
| Bean instance lúc startup | Không có instance từ bean bị loại | Có thể chưa có instance |
| Startup work | Có thể giảm discovery, parsing, condition và registration | Giảm constructor/lifecycle work của bean lazy |
| Chi phí lần đầu sử dụng | Không có bean để dùng nếu đã bị loại | Có thể tăng do khởi tạo tại first use |
| Lỗi cấu hình | Condition không khớp có thể được thấy trong report; bean không được tạo | Lỗi constructor/dependency có thể chỉ xuất hiện khi bean được yêu cầu |
| Bộ nhớ | Có thể giảm cả metadata/definition/instance liên quan | Có thể giảm instance tạm thời; nếu bean cuối cùng đều được dùng, mức tiết kiệm có thể nhỏ |
| Phù hợp | Integration không dùng, dependency tùy chọn, auto-configuration không liên quan | Bean nặng, hiếm khi dùng, nhánh chức năng ít truy cập |

Ví dụ:

- Ứng dụng không dùng JDBC: loại dependency hoặc exclude DataSourceAutoConfiguration khi có chủ đích. Lazy initialization không làm biến mất cấu hình JDBC khỏi candidate list.
- Ứng dụng có chức năng export PDF nhưng phần lớn request chỉ xuất CSV: có thể giữ bean PDF trong context và dùng lazy/ObjectProvider để chỉ tạo khi cần.
- Thư viện có optional SDK: dùng @ConditionalOnClass và optional dependency để bean không được đăng ký khi SDK vắng mặt. Không dùng @Lazy để thay thế classpath condition.

## 7. Ví dụ Maven hoàn chỉnh: condition loại bean và lazy trì hoãn instance

Ví dụ dùng **Java 17 và Spring Boot 3.3.13**. Một custom auto-configuration tạo ReportClient khi property được bật. Bean được đánh dấu lazy để minh họa rằng bean definition vẫn tồn tại dù instance chưa được tạo.

### 7.1. Cấu trúc project

~~~text
lazy-vs-candidate-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/app/
    │   │   └── ReportsDemoApplication.java
    │   ├── java/com/example/lib/
    │   │   ├── ReportClient.java
    │   │   └── autoconfigure/
    │   │       └── ReportsAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/lib/autoconfigure/
            └── ReportsAutoConfigurationTests.java
~~~

Package của thư viện nằm ngoài package component scan của ứng dụng. Spring Boot tìm auto-configuration thông qua imports resource.

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>lazy-vs-candidate-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
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

**src/main/java/com/example/lib/ReportClient.java**

~~~java
package com.example.lib;

public record ReportClient(String endpoint) {
}
~~~

### 7.4. ReportsAutoConfiguration.java

**src/main/java/com/example/lib/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.example.lib.autoconfigure;

import com.example.lib.ReportClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Lazy;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
public class ReportsAutoConfiguration {

    @Bean
    @Lazy
    ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

Khi property không có hoặc không phải true, auto-configuration không được áp dụng và bean definition reportClient không được đăng ký.

Khi property là true, bean definition được đăng ký. Do @Lazy, ReportClient singleton chưa được tạo trong quá trình refresh nếu không có bean eager nào phụ thuộc trực tiếp vào nó.

### 7.5. AutoConfiguration.imports

Tạo file:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.example.lib.autoconfigure.ReportsAutoConfiguration
~~~

Resource này công bố candidate cho Spring Boot 3.x. Nếu muốn kiểm tra candidate được phát hiện từ JAR đã đóng gói, hãy chạy một ứng dụng consumer độc lập chỉ thêm starter hoặc artifact autoconfigure. Các test dùng AutoConfigurations.of bên dưới nạp class trực tiếp, vì vậy chúng tập trung kiểm tra condition và bean lifecycle.

### 7.6. ReportsDemoApplication.java

**src/main/java/com/example/app/ReportsDemoApplication.java**

~~~java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReportsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReportsDemoApplication.class, args);
    }
}
~~~

Để bật feature khi chạy:

~~~properties
acme.reports.enabled=true
~~~

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Vì không có bean eager nào inject ReportClient trong ví dụ này, bean definition có thể tồn tại mà instance chưa được tạo cho đến khi một consumer yêu cầu nó.

## 8. Kiểm thử phân biệt bean definition với singleton instance

**src/test/java/com/example/lib/autoconfigure/ReportsAutoConfigurationTests.java**

~~~java
package com.example.lib.autoconfigure;

import com.example.lib.ReportClient;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void disabledFeatureDoesNotRegisterBeanDefinition() {
        runner.withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);

                    assertThat(context.getBeanFactory()
                            .containsBeanDefinition("reportClient"))
                            .isFalse();

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isFalse();
                });
    }

    @Test
    void enabledFeatureRegistersDefinitionButDefersInstance() {
        runner.withPropertyValues("acme.reports.enabled=true")
                .run(context -> {
                    assertThat(context).hasBean("reportClient");

                    assertThat(context.getBeanFactory()
                            .containsBeanDefinition("reportClient"))
                            .isTrue();

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isFalse();

                    ReportClient client =
                            context.getBean("reportClient", ReportClient.class);

                    assertThat(client.endpoint())
                            .isEqualTo("https://reports.example.test");

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isTrue();
                });
    }

    @Test
    void eagerConsumerForcesLazyDependencyDuringRefresh() {
        runner.withPropertyValues("acme.reports.enabled=true")
                .withUserConfiguration(EagerConsumerConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(EagerFacade.class);

                    assertThat(context.getBeanFactory()
                            .containsBeanDefinition("reportClient"))
                            .isTrue();

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isTrue();
                });
    }

    @Test
    void objectProviderDefersDependencyUntilItIsRequested() {
        runner.withPropertyValues("acme.reports.enabled=true")
                .withUserConfiguration(DeferredConsumerConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(DeferredFacade.class);

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isFalse();

                    DeferredFacade facade =
                            context.getBean(DeferredFacade.class);

                    ReportClient client = facade.getClient();

                    assertThat(client.endpoint())
                            .isEqualTo("https://reports.example.test");

                    assertThat(context.getBeanFactory()
                            .containsSingleton("reportClient"))
                            .isTrue();
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class EagerConsumerConfiguration {

        @Bean
        EagerFacade eagerFacade(ReportClient client) {
            return new EagerFacade(client);
        }
    }

    record EagerFacade(ReportClient client) {
    }

    @Configuration(proxyBeanMethods = false)
    static class DeferredConsumerConfiguration {

        @Bean
        DeferredFacade deferredFacade(
                ObjectProvider<ReportClient> clients) {
            return new DeferredFacade(clients);
        }
    }

    static class DeferredFacade {

        private final ObjectProvider<ReportClient> clients;

        DeferredFacade(ObjectProvider<ReportClient> clients) {
            this.clients = clients;
        }

        ReportClient getClient() {
            return this.clients.getObject();
        }
    }
}
~~~

Chạy test:

~~~bash
mvn clean test
~~~

Kỳ vọng **bốn test pass**:

1. Feature tắt: không có bean definition và không có singleton instance.
2. Feature bật: bean definition tồn tại nhưng singleton chưa được tạo; lần gọi getBean đầu tiên tạo instance.
3. Bean eager inject ReportClient trực tiếp: dependency lazy vẫn được tạo trong lúc refresh để đáp ứng injection.
4. Bean eager inject ObjectProvider: ReportClient vẫn chưa được tạo cho đến khi provider.getObject() được gọi.

Hai assertion quan trọng trong ví dụ là:

~~~java
context.getBeanFactory().containsBeanDefinition("reportClient")
context.getBeanFactory().containsSingleton("reportClient")
~~~

Assertion đầu kiểm tra bean definition. Assertion sau kiểm tra singleton instance đã được tạo hay chưa. Chúng không trả lời cùng một câu hỏi.

## 9. AOT liên quan thế nào đến candidate filtering và lazy initialization?

### 9.1. AOT là tối ưu ở build-time

Spring AOT phân tích ApplicationContext trong lúc build và tạo code/hints tối ưu cho ứng dụng. AOT là bước bắt buộc khi xây Spring ApplicationContext thành native image.

Với Spring Boot, AOT chuẩn bị BeanFactory ở build-time. Các condition cũng được đánh giá trong quá trình này. Điều đó có nghĩa:

- Classpath dùng lúc AOT phải đại diện cho classpath lúc chạy.
- Profile ảnh hưởng đến bean phải được chọn đúng khi build.
- Property ảnh hưởng đến việc bean có được đăng ký hay không cần có giá trị phù hợp trong môi trường build AOT.
- Không thể kỳ vọng đổi một property condition ở runtime sẽ tạo ra bean mà AOT đã không sinh ra.

Ví dụ, nếu build AOT với:

~~~properties
acme.reports.enabled=false
~~~

thì auto-configuration có thể không được đưa vào cấu hình AOT. Chạy binary sau đó với enabled=true không thể tự bổ sung bean đã bị loại trong build-time processing.

### 9.2. AOT không đồng nghĩa lazy initialization

AOT và lazy initialization giải quyết vấn đề khác nhau:

| Cơ chế | Thời điểm quyết định | Tác động chính |
| --- | --- | --- |
| Candidate filtering | Khi import auto-configuration | Loại class không cần xem xét |
| Condition evaluation | Khi xử lý configuration; trong AOT là build-time | Quyết định bean definition có được đăng ký |
| Lazy initialization | Khi ApplicationContext chạy | Trì hoãn tạo instance đến lúc được yêu cầu |
| AOT processing | Build-time | Sinh code/hints và chuẩn bị context theo classpath/Environment đã chọn |

Một bean được giữ trong AOT-generated context vẫn có thể được cấu hình lazy nếu bean definition và cách sử dụng hỗ trợ điều đó. AOT không biến @Lazy thành exclusion và cũng không biến exclusion thành lazy.

### 9.3. Chạy AOT với Maven

Có thể gọi goal process-aot của Spring Boot Maven Plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>process-aot</id>
            <goals>
                <goal>process-aot</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Sau khi cấu hình plugin, chạy:

~~~bash
mvn spring-boot:process-aot
~~~

Với project dùng Spring Boot parent và native build tools được cấu hình, native profile có thể hỗ trợ quy trình:

~~~bash
mvn -Pnative package
~~~

Lệnh native cần môi trường GraalVM/native build tools phù hợp. Chỉ chạy process-aot không đồng nghĩa đã tạo native executable.

Trước khi bật AOT trong CI, hãy đưa đúng profile và property ảnh hưởng đến condition vào môi trường process-aot. Kiểm tra các profile/condition có cùng kết quả giữa build và môi trường triển khai.

## 10. Đo hiệu năng đúng cách

Không nên kết luận một chiến lược nhanh hơn chỉ từ một lần khởi động hoặc chỉ nhìn số bean.

### 10.1. Đo startup steps

Spring Boot hỗ trợ ApplicationStartup để theo dõi các bước trong quá trình khởi động. Có thể dùng BufferingApplicationStartup:

~~~java
@SpringBootApplication
public class ReportsApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(ReportsApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048));

        application.run(args);
    }
}
~~~

Khi có Actuator và cấu hình endpoint startup, có thể thu thập dữ liệu startup để xác định bước tốn thời gian. Java Flight Recorder cũng hữu ích để xem class loading, allocation, garbage collection và hoạt động JVM.

### 10.2. Đo cả first-use latency

Khi bật lazy initialization, startup có thể nhanh hơn nhưng request đầu tiên gọi bean sẽ phải chịu chi phí khởi tạo. Vì vậy hãy đo ít nhất:

- Thời gian từ process start đến ApplicationReadyEvent.
- Thời gian từ readiness đến request đầu tiên hoàn thành.
- Latency của request đầu tiên sử dụng bean lazy.
- Latency ổn định sau warm-up.
- Heap usage và allocation sau startup và sau khi các chức năng đã được dùng.

Không chỉ đo thời gian startup rồi tuyên bố lazy luôn cải thiện hiệu năng. Với service nhận traffic ngay sau readiness, first-use delay có thể ảnh hưởng trải nghiệm hoặc autoscaling.

### 10.3. Thiết kế benchmark công bằng

Khi so sánh:

1. Dùng cùng JDK, container limit, heap, CPU, dependency graph và cấu hình.
2. Chạy nhiều lần, loại bỏ lần đầu nếu có ảnh hưởng tải class/JIT hoặc ghi rõ cold-start riêng.
3. So sánh median và p95 thay vì chỉ chọn lần chạy nhanh nhất.
4. Dùng cùng workload và cùng readiness definition.
5. Ghi lại số auto-configuration được import, bean definitions và singleton instances.
6. Đo cả startup và first-use; không bỏ qua chi phí chuyển sang request đầu tiên.

Một thử nghiệm có thể so sánh ba biến thể:

| Biến thể | Candidate/condition | Lazy |
| --- | --- | --- |
| A | Giữ cấu hình mặc định | Tắt |
| B | Loại integration không dùng | Tắt |
| C | Giữ bean tùy chọn | Bật cho bean được chọn |

Từ kết quả mới quyết định nên giảm dependency, exclude cấu hình hay trì hoãn instance.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bật lazy nhưng số auto-configuration candidate không giảm | Lazy chỉ trì hoãn tạo instance | Dùng dependency tối thiểu, exclusions hoặc early filtering khi phù hợp |
| Bean definition vẫn tồn tại dù bean chưa được tạo | Đang kiểm tra lazy bean | Phân biệt containsBeanDefinition và containsSingleton |
| Đánh dấu @Lazy nhưng bean vẫn tạo lúc startup | Singleton eager inject trực tiếp bean lazy | Dùng ObjectProvider hoặc @Lazy tại injection point nếu thực sự muốn trì hoãn |
| Feature tắt nhưng vẫn có bean | Condition đặt sai class/method hoặc property không như mong đợi | Kiểm tra Condition Evaluation Report và vị trí condition |
| Exclude một auto-configuration làm ứng dụng thiếu nhiều bean | Cấu hình bị loại có cung cấp prerequisite cho integration khác | Xác minh dependency giữa cấu hình trước khi exclude |
| Thêm nhiều starter khiến startup chậm | Classpath có thêm dependency và auto-configuration | Tách optional integration và chỉ đưa dependency cần thiết vào starter |
| Annotation processor không sinh autoconfigure metadata | Processor chưa được cấu hình trong module auto-configure | Thêm spring-boot-autoconfigure-processor vào annotationProcessorPaths/annotationProcessor |
| Nhầm configuration metadata với autoconfigure metadata | Hai file phục vụ hai mục đích khác nhau | Phân biệt spring-configuration-metadata.json và spring-autoconfigure-metadata.properties |
| Tự viết AutoConfigurationImportFilter quá phức tạp | Dùng SPI mức thấp cho quy tắc condition thông thường | Ưu tiên built-in conditions và processor |
| Dùng @AutoConfigureBefore để mong loại candidate | Ordering chỉ sắp xếp thứ tự | Dùng exclusion/filter/condition đúng mục đích |
| Startup nhanh nhưng request đầu chậm | Lazy chuyển chi phí sang first use | Warm-up có chủ đích hoặc giữ eager cho bean critical |
| Lỗi cấu hình chỉ xuất hiện khi request đầu tiên | Bean lazy chưa được khởi tạo khi startup | Thêm smoke test hoặc kiểm tra bean quan trọng trước readiness |
| AOT build với property khác production | Condition đã được đánh giá ở build-time | Đồng bộ profile/property khi process-aot |
| Đổi property runtime nhưng AOT bean không xuất hiện | Condition đã quyết định ở build-time | Build lại với environment đúng hoặc thiết kế feature toggle runtime trong bean đã được tạo |

## 12. Checklist tối ưu custom starter

### Giảm candidate và configuration work

- [ ] AutoConfiguration.imports chỉ liệt kê cấu hình thực sự được hỗ trợ.
- [ ] Auto-configuration không bị component scan ngoài ý muốn.
- [ ] Optional integrations có dependency riêng và condition phù hợp.
- [ ] Ứng dụng loại cấu hình không dùng bằng exclusions có chủ đích.
- [ ] Module auto-configure dùng spring-boot-autoconfigure-processor.
- [ ] Kiểm tra spring-autoconfigure-metadata.properties trong artifact build.
- [ ] Không dùng ordering annotation như một công cụ lọc.

### Lazy initialization

- [ ] Chỉ đánh dấu lazy cho bean thật sự có thể chưa được dùng.
- [ ] Kiểm tra dependency eager có kéo lazy bean lên startup không.
- [ ] Dùng ObjectProvider hoặc lazy proxy khi cần trì hoãn dependency.
- [ ] Giữ eager cho bean bắt buộc để xác thực startup/readiness.
- [ ] Đo first-use latency và memory sau khi bean được tạo.
- [ ] Có test phát hiện lỗi khởi tạo bean lazy trước khi phát hành.

### AOT và đo lường

- [ ] Build AOT với đúng classpath, profile và property ảnh hưởng condition.
- [ ] Kiểm tra các condition có kết quả đúng trong build-time environment.
- [ ] Không kỳ vọng runtime property tạo lại bean bị loại trong AOT.
- [ ] Đo startup steps bằng ApplicationStartup hoặc JFR.
- [ ] So sánh startup, first-use latency, p95 và memory bằng workload giống nhau.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Candidate auto-configuration khác bean instance như thế nào?  
**Đáp án:** Candidate là class được xem xét để áp dụng; bean instance là object thực tế được tạo từ bean definition sau đó.

**Câu 2.** Nếu auto-configuration bị exclude, bean definition mặc định của nó có được đăng ký không?  
**Đáp án:** Không. Cấu hình đã bị loại khỏi tập cấu hình được nhập.

**Câu 3.** Nếu một bean được đánh dấu @Lazy, bean definition có biến mất không?  
**Đáp án:** Không. Bean definition vẫn tồn tại; instance chỉ được tạo khi có yêu cầu.

**Câu 4.** Vì sao một bean eager có thể khiến dependency @Lazy được tạo lúc startup?  
**Đáp án:** Spring cần resolve dependency để tạo bean eager. Nếu inject trực tiếp instance, dependency lazy phải được khởi tạo để đáp ứng injection.

**Câu 5.** ObjectProvider giúp trì hoãn dependency như thế nào?  
**Đáp án:** Consumer được inject provider trước; bean mục tiêu chỉ được lấy khi gọi getObject hoặc method tương ứng.

**Câu 6.** spring-autoconfigure-metadata.properties dùng để làm gì?  
**Đáp án:** Chứa condition metadata do annotation processor tạo để Spring Boot có thể early-filter một số auto-configuration không phù hợp.

**Câu 7.** AOT đánh giá condition ở thời điểm nào?  
**Đáp án:** Trong build-time processing. Classpath, profile và property ảnh hưởng việc đăng ký bean cần phù hợp với môi trường build.

**Câu 8.** Khi bật lazy, vì sao cần đo request đầu tiên?  
**Đáp án:** Chi phí tạo bean được chuyển từ startup sang lần sử dụng đầu tiên; startup nhanh hơn có thể đi kèm first-use latency cao hơn.

**Câu 9.** @AutoConfigureAfter có giảm số candidate không?  
**Đáp án:** Không. Nó chỉ gợi ý thứ tự áp dụng auto-configuration.

**Câu 10.** Muốn xác nhận lazy bean có definition nhưng chưa có instance, kiểm tra gì?  
**Đáp án:** containsBeanDefinition(name) phải true và containsSingleton(name) phải false trước lần tra cứu đầu tiên.

## 14. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — SpringApplication và Lazy Initialization](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html)
- [AutoConfigurationImportFilter — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html)
- [Ahead-of-Time Processing — Spring Boot 3.3.13](https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html)
- [Lazy-initialized Beans — Spring Framework](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html)

**Ghi nhớ:** Giảm candidate làm Spring ít phải xem xét và áp dụng cấu hình hơn; condition không khớp làm bean definition không được đăng ký; lazy initialization giữ definition nhưng trì hoãn instance. AOT chuyển việc phân tích context và đánh giá condition sang build-time. Hãy chọn đúng giai đoạn cần tối ưu, rồi đo cả startup, first-use latency và memory trước khi quyết định chiến lược.
