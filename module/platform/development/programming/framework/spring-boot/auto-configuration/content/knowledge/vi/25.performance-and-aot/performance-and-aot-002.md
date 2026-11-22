# Dùng metadata và điều kiện lớp để tránh xử lý tích hợp không cần thiết

## 1. Vì sao custom starter cần lọc sớm?

Một thư viện Spring Boot có thể hỗ trợ nhiều công nghệ: HTTP client, SDK báo cáo, codec JSON, driver database hoặc adapter messaging. Khi ứng dụng thêm starter, các auto-configuration của thư viện trở thành ứng viên được Spring Boot xem xét. Nếu mỗi cấu hình đều quét package, nạp class tùy chọn, tạo bean hoặc kiểm tra hệ thống bên ngoài, startup sẽ tốn công cho những tích hợp ứng dụng không sử dụng.

Spring Boot có nhiều tầng để giảm công việc đó:

1. **Danh sách auto-configuration imports** xác định những cấu hình nào là ứng viên.
2. **Auto-configuration metadata** cho phép Boot lọc sớm ứng viên có condition chắc chắn không khớp.
3. **Class-level conditions** như **@ConditionalOnClass** giúp bỏ qua cấu hình tích hợp khi thư viện không có trên classpath.
4. **Nested configuration** cô lập các method signature tham chiếu tới thư viện tùy chọn, tránh JVM phải nạp kiểu đó khi dependency vắng mặt.
5. **AOT processing** có thể đánh giá cấu hình và tạo mã khởi tạo trước khi ứng dụng chạy, với các giới hạn về classpath và Environment.

Các cơ chế này liên quan nhưng không thay thế lẫn nhau. Metadata giúp lọc ứng viên sớm; condition quyết định cấu hình có được áp dụng; AOT tạo trước một phần kết quả xử lý context. Hiểu đúng từng tầng giúp starter khởi động nhanh và hoạt động an toàn khi dependency tùy chọn không có mặt.

## 2. Phân biệt các file metadata của Spring Boot

Có ba file thường gặp trong custom starter. Tên gần giống nhau nhưng mục đích khác nhau.

| File | Được tạo hoặc duy trì bởi | Mục đích |
| --- | --- | --- |
| **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** | Tác giả starter | Liệt kê các auto-configuration class để Spring Boot khám phá |
| **META-INF/spring-autoconfigure-metadata.properties** | spring-boot-autoconfigure-processor | Lưu condition metadata để Boot lọc sớm auto-configuration không phù hợp |
| **META-INF/spring-configuration-metadata.json** | spring-boot-configuration-processor | Mô tả các key @ConfigurationProperties cho IDE, autocomplete và tài liệu cấu hình |

### 2.1. AutoConfiguration.imports: tìm ứng viên

Một JAR chứa auto-configuration cần file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng ghi tên đầy đủ của một auto-configuration class:

~~~text
com.example.report.autoconfigure.ReportAutoConfiguration
com.example.report.autoconfigure.ReportWebAutoConfiguration
~~~

Spring Boot đọc file này từ các JAR trên classpath để tìm cấu hình được công bố. Có thể thêm comment bắt đầu bằng ký tự #.

File này **chỉ liệt kê ứng viên**. Nó không chứng minh thư viện tích hợp có mặt, không tạo bean và không thay thế condition. Một auto-configuration được liệt kê vẫn cần các điều kiện thích hợp để chỉ hoạt động trong ứng dụng tương ứng.

Các auto-configuration nên nằm trong package riêng, được nạp thông qua imports file và không trở thành mục tiêu của component scan. Không dùng @ComponentScan bên trong auto-configuration để quét một vùng package lớn; nếu cần thêm cấu hình hoặc component cụ thể, dùng @Import.

### 2.2. spring-autoconfigure-metadata.properties: lọc sớm

Spring Boot có annotation processor tên **spring-boot-autoconfigure-processor**. Processor thu thập các condition mà nó hỗ trợ trên auto-configuration và tạo file:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Khi file này có mặt, Spring Boot có thể dùng metadata để **eagerly filter** những auto-configuration chắc chắn không khớp trước khi xử lý sâu từng cấu hình. Ví dụ, nếu một integration yêu cầu class của SDK nhưng class đó không nằm trên classpath, Boot có thể loại ứng viên tương ứng sớm.

Lợi ích:

- Giảm số cấu hình phải được xử lý sâu.
- Tránh phân tích những nhánh tích hợp chắc chắn không dùng.
- Giảm công việc condition evaluation ở các giai đoạn sau.
- Hữu ích khi starter có nhiều auto-configuration và nhiều dependency tùy chọn.

File này được sinh trong lúc compile. **Không tự viết hoặc sửa thủ công** file metadata này. Hãy khai báo đúng annotation processor trong module chứa các auto-configuration class và kiểm tra file được đóng gói vào JAR.

Metadata chỉ hỗ trợ các condition mà processor và phiên bản Spring Boot nhận diện được. Nó không loại bỏ việc đánh giá condition ở runtime khi cần, và không phải cam kết rằng mọi custom condition đều có thể được quyết định trước.

### 2.3. spring-configuration-metadata.json: hỗ trợ người viết cấu hình

File **META-INF/spring-configuration-metadata.json** phục vụ một mục đích khác: mô tả các property được khai báo bằng **@ConfigurationProperties**, ví dụ tên key, kiểu dữ liệu, mô tả và gợi ý giá trị.

IDE có thể dùng file này để autocomplete và hiển thị trợ giúp khi người dùng viết application.yml hoặc application.properties.

File này thường được tạo bởi **spring-boot-configuration-processor**. Nó không phải file mà auto-configuration import selector dùng để lọc auto-configuration.

**Không nhầm hai processor:**

- **spring-boot-autoconfigure-processor** tạo condition metadata cho việc lọc auto-configuration.
- **spring-boot-configuration-processor** tạo configuration metadata cho IDE và người dùng starter.

Một starter có thể cần cả hai processor nếu vừa cung cấp auto-configuration vừa công bố các key cấu hình riêng.

## 3. Điều kiện lớp: chỉ nạp integration khi class cần thiết hiện diện

### 3.1. @ConditionalOnClass và @ConditionalOnMissingClass

**@ConditionalOnClass** cho phép một configuration được áp dụng khi class yêu cầu có trên classpath. **@ConditionalOnMissingClass** làm điều ngược lại: cấu hình chỉ được áp dụng khi class được chỉ định không có mặt.

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.report.ReportClient")
public class ReportAutoConfiguration {
    // Cấu hình cho ReportClient.
}
~~~

Khi com.acme.report.ReportClient không có trên classpath, auto-configuration này không được áp dụng.

Nếu cần điều kiện cho nhiều class, có thể liệt kê nhiều giá trị. Condition chỉ khớp khi các class cần thiết đều đáp ứng. Chọn đúng các class đại diện cho capability thực sự được dùng; không kiểm tra một class quá chung khiến feature bị bật dù phần integration cụ thể chưa đủ dependency.

### 3.2. Vì sao ASM metadata quan trọng?

Spring Boot đọc annotation metadata của configuration bằng ASM. ASM có thể đọc thông tin từ bytecode mà không cần nạp và khởi tạo class theo cách thông thường.

Vì vậy, với class-level condition, có thể dùng:

~~~java
@ConditionalOnClass(SomeOptionalClient.class)
~~~

ngay cả khi class đó không có trên runtime classpath của ứng dụng tiêu thụ. Annotation metadata được đọc như tên kiểu trong bytecode.

Nếu muốn tránh compile-time reference tới thư viện tùy chọn, có thể dùng thuộc tính name:

~~~java
@ConditionalOnClass(name = "com.acme.report.ReportClient")
~~~

name nhận tên class dưới dạng String. Cách này hữu ích khi thư viện tích hợp là optional dependency và module auto-configuration không muốn expose type của nó trong public API.

Khi dùng @ConditionalOnClass hoặc @ConditionalOnMissingClass bên trong một meta-annotation để tạo annotation tổng hợp, phải dùng name. Việc tham chiếu class bằng value trong trường hợp meta-annotation không được xử lý theo cùng cách.

### 3.3. Đặt condition trên configuration class thay vì chỉ trên @Bean method

Có một khác biệt quan trọng giữa condition trên class và condition trên method.

Đoạn sau có rủi ro khi ReportClient là optional:

~~~java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.acme.report.ReportClient")
    ReportService reportService(ReportClient client) {
        return new DefaultReportService(client);
    }
}
~~~

Trước khi method-level condition được áp dụng, JVM hoặc quá trình introspection có thể phải nạp class và xử lý method signature. Nếu kiểu trả về hoặc tham số của method tham chiếu tới class đang thiếu, ứng dụng có thể gặp lỗi linkage trước khi condition kịp loại method.

Cách an toàn hơn là **cô lập mọi method phụ thuộc optional type trong một nested @Configuration có class-level condition**:

~~~java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.report.ReportClient")
    static class ReportClientConfiguration {

        @Bean
        ReportService reportService(ReportClient client) {
            return new DefaultReportService(client);
        }
    }
}
~~~

Configuration con chỉ được xử lý khi class condition khớp. Khi SDK không có trên classpath, Spring có thể bỏ qua nhánh này trước khi xử lý các method có signature phụ thuộc SDK.

Trong module auto-configuration lớn, cũng có thể đặt condition trên auto-configuration class cấp cao nhất nếu toàn bộ cấu hình đó chỉ có ý nghĩa khi SDK hiện diện. Giữ class chứa condition không tham chiếu trực tiếp tới optional type; chuyển các method cần SDK vào nested configuration.

### 3.4. Kết hợp class condition với property và bean condition

Classpath condition trả lời câu hỏi thư viện có thể được sử dụng không. Property condition trả lời người vận hành có bật feature không. Bean condition cho phép ứng dụng thay implementation mặc định.

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.report.ReportClient")
@ConditionalOnProperty(
        prefix = "app.report",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class ReportClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(ReportService.class)
        ReportService reportService(ReportClient client) {
            return new DefaultReportService(client);
        }
    }
}
~~~

Các condition kết hợp theo phép AND. Khi SDK thiếu hoặc property tắt, configuration không được áp dụng. Khi cả hai điều kiện khớp, bean mặc định chỉ được tạo nếu ứng dụng chưa cung cấp ReportService.

Đặt @ConditionalOnMissingBean trên auto-configuration hoặc bean method phù hợp với contract của starter. Bean conditions phụ thuộc các bean definitions đã được xử lý tới thời điểm đánh giá; Spring Boot khuyến nghị dùng chúng trong auto-configuration vì auto-configuration được xử lý sau user-defined bean definitions.

## 4. Tổ chức custom starter để tránh kéo và xử lý dependency không dùng

Một custom starter thường tách thành hai module:

~~~text
report-spring-boot-autoconfigure
    - Auto-configuration classes
    - Class/property/bean conditions
    - Configuration properties
    - Annotation processor metadata

report-spring-boot-starter
    - Dependency bundle cho trải nghiệm mặc định
    - Phụ thuộc vào autoconfigure module
    - Khai báo các SDK cần thiết cho feature mà starter bật sẵn
~~~

Trong module autoconfigure, dependency tới SDK có thể được đánh dấu optional trong Maven hoặc compile-only trong Gradle nếu thiết kế yêu cầu consumer tự chọn thư viện. Starter module khai báo các dependency cần thiết cho trải nghiệm mặc định.

Ví dụ Maven dependency trong autoconfigure module:

~~~xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>report-sdk</artifactId>
    <version>1.2.0</version>
    <optional>true</optional>
</dependency>
~~~

Ví dụ Gradle:

~~~kotlin
dependencies {
    compileOnly("com.acme:report-sdk:1.2.0")
    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )
}
~~~

Class condition bảo vệ nhánh tích hợp khi SDK vắng mặt. Optional/compile-only dependency điều khiển việc thư viện có tự truyền sang consumer hay không. Hai cơ chế phục vụ hai lớp khác nhau; khai báo optional không tự động thay thế class condition.

Nếu starter mặc định cần SDK, starter module phải khai báo dependency đó trực tiếp và ở scope phù hợp với runtime của ứng dụng. Nếu starter có nhiều feature tùy chọn, có thể tách thành các starter nhỏ theo capability thay vì kéo tất cả SDK vào mọi ứng dụng.

## 5. Ví dụ hoàn chỉnh: Report starter chỉ tạo bean khi SDK có mặt

Ví dụ dưới đây dùng Java 17 và Spring Boot 3.5.0. Để project demo tự biên dịch được, ta tạo một class ReportClient nhỏ trong source. Trong starter thật, class này đến từ SDK riêng và dependency được khai báo optional trong module autoconfigure.

Ví dụ kiểm tra ba tình huống:

1. SDK có mặt và property bật: tạo service mặc định.
2. SDK không có: bỏ qua toàn bộ integration mà context vẫn khởi động.
3. Property tắt: không tạo service dù SDK vẫn có mặt.

### 5.1. Cấu trúc thư mục

~~~text
report-autoconfigure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── example/
    │   │   │   ├── sdk/
    │   │   │   │   └── ReportClient.java
    │   │   │   ├── report/
    │   │   │   │   └── ReportService.java
    │   │   │   └── autoconfigure/
    │   │   │       └── ReportAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/
    │           └── spring/
    │               └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/
            └── example/
                └── autoconfigure/
                    └── ReportAutoConfigurationTests.java
~~~

### 5.2. Tệp pom.xml

Maven Compiler Plugin 3.12.0 trở lên hỗ trợ cấu hình annotation processor theo cách Spring Boot khuyến nghị. Ví dụ dùng 3.13.0 và processor cùng phiên bản Spring Boot 3.5.0.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
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

    <groupId>example</groupId>
    <artifactId>report-autoconfigure-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.5.0</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Nếu project còn có @ConfigurationProperties và muốn tạo metadata cho IDE, thêm spring-boot-configuration-processor vào annotationProcessorPaths như một processor riêng. Processor đó phục vụ spring-configuration-metadata.json; nó không thay thế spring-boot-autoconfigure-processor.

### 5.3. Tệp ReportClient.java

Đây là SDK giả lập để ví dụ có thể biên dịch độc lập:

~~~java
package example.sdk;

public final class ReportClient {

    public String status() {
        return "report-client-ready";
    }
}
~~~

### 5.4. Tệp ReportService.java

~~~java
package example.report;

public interface ReportService {
    String status();
}
~~~

### 5.5. Tệp ReportAutoConfiguration.java

~~~java
package example.autoconfigure;

import example.report.ReportService;
import example.sdk.ReportClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@ConditionalOnClass(name = "example.sdk.ReportClient")
@ConditionalOnProperty(
        prefix = "app.report",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class ReportClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(ReportService.class)
        ReportService reportService(ReportClient client) {
            return client::status;
        }
    }
}
~~~

Điểm quan trọng:

- Auto-configuration class dùng tên class dưới dạng String trong @ConditionalOnClass.
- Auto-configuration class không có method signature tham chiếu trực tiếp tới SDK.
- Method nhận ReportClient nằm trong nested configuration, được xử lý khi class-level conditions khớp.
- @ConditionalOnProperty cho phép tắt feature ngay cả khi SDK có mặt.
- @ConditionalOnMissingBean cho phép ứng dụng thay ReportService mặc định.

Trong module autoconfigure thật, nếu ReportClient đến từ một SDK optional dependency, bỏ class giả lập trong project demo và khai báo SDK trong build file theo scope thích hợp.

### 5.6. Tệp AutoConfiguration.imports

Tạo file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
example.autoconfigure.ReportAutoConfiguration
~~~

### 5.7. Tệp ReportAutoConfigurationTests.java

~~~java
package example.autoconfigure;

import example.report.ReportService;
import example.sdk.ReportClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ReportAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ReportAutoConfiguration.class)
                    );

    @Test
    void createsReportServiceWhenSdkIsPresentAndFeatureIsEnabled() {
        runner.withPropertyValues("app.report.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ReportService.class);

                    assertThat(context.getBean(ReportService.class).status())
                            .isEqualTo("report-client-ready");
                });
    }

    @Test
    void skipsIntegrationWhenSdkIsMissing() {
        runner.withClassLoader(new FilteredClassLoader(ReportClient.class))
                .withPropertyValues("app.report.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("reportService");
                });
    }

    @Test
    void skipsIntegrationWhenFeatureIsDisabled() {
        runner.withPropertyValues("app.report.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("reportService");
                });
    }

    @Test
    void backsOffWhenApplicationProvidesItsOwnService() {
        runner.withUserConfiguration(UserReportConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ReportService.class);
                    assertThat(context).hasBean("customReportService");
                    assertThat(context).doesNotHaveBean("reportService");

                    assertThat(context.getBean(ReportService.class).status())
                            .isEqualTo("custom-report-service");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserReportConfiguration {

        @Bean
        ReportService customReportService() {
            return () -> "custom-report-service";
        }
    }
}
~~~

### 5.8. Chạy test

Tại thư mục có pom.xml, dùng JDK 17+ và Maven:

~~~bash
java -version
mvn -version
mvn test
~~~

**Kết quả mong đợi:** bốn test JUnit pass và Maven kết thúc BUILD SUCCESS nếu dependency tải thành công. Đây là kết quả kỳ vọng từ ví dụ, chưa phải kết quả chạy thực tế. Test không gọi System.out.println nên không có stdout nghiệp vụ cố định; báo cáo nằm trong target/surefire-reports.

Test thứ hai là bằng chứng quan trọng: SDK bị ẩn khỏi classloader của ApplicationContext, nhưng context vẫn khởi động và bean tích hợp không được đăng ký. Test này kiểm tra tính an toàn của class condition; nó không thay thế việc kiểm tra dependency graph của artifact đã publish.

## 6. Bật annotation processor để tạo auto-configuration metadata

### 6.1. Maven

Trong module chứa các auto-configuration class, khai báo spring-boot-autoconfigure-processor trên annotation processor path của Maven Compiler Plugin:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.13.0</version>
    <configuration>
        <annotationProcessorPaths>
            <path>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-autoconfigure-processor</artifactId>
                <version>3.5.0</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

Dùng Maven parent/BOM phù hợp để giữ version đồng bộ với Spring Boot của module. Nếu có nhiều annotation processor, khai báo tất cả trong danh sách; đừng vô tình bỏ processor khác khi thay cấu hình annotation processor path.

### 6.2. Gradle

Với Gradle, khai báo processor trong configuration annotationProcessor:

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")

    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

Nếu module còn cần metadata cho @ConfigurationProperties, thêm processor tương ứng:

~~~kotlin
dependencies {
    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )
}
~~~

Không đặt annotation processor vào implementation chỉ để làm cho class có mặt trên runtime classpath. Processor là công cụ build-time; nó nên chạy trong configuration dành cho annotation processing.

### 6.3. Processor phải chạy ở đúng module

Nếu project multi-module, đặt spring-boot-autoconfigure-processor trong module thực sự chứa source của @AutoConfiguration. Thêm processor chỉ vào starter bundle rỗng sẽ không tạo metadata cho source nằm trong module autoconfigure khác.

Sau khi compile/package, kiểm tra JAR chứa cả:

- META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.
- META-INF/spring-autoconfigure-metadata.properties.

Nếu metadata file không có, kiểm tra annotation processor path, compiler logs, module build và nội dung JAR. Auto-configuration vẫn có thể chạy nhờ runtime conditions, nhưng Boot không có file này để thực hiện bước lọc sớm dựa trên metadata đã sinh.

## 7. AOT: chuyển một phần quyết định cấu hình sang build time

### 7.1. AOT khác auto-configuration metadata

Hai cơ chế thường được nhắc cùng nhau vì đều cải thiện startup, nhưng phạm vi khác nhau:

| Cơ chế | Thời điểm | Phạm vi |
| --- | --- | --- |
| Auto-configuration metadata | Compile/package thư viện | Lọc sớm auto-configuration candidate dựa trên condition metadata được hỗ trợ |
| Spring AOT processing | Build ứng dụng | Phân tích ApplicationContext và tạo mã khởi tạo, bytecode/hints cần thiết |
| Runtime condition evaluation | Khi ứng dụng chạy ở chế độ thường | Đánh giá conditions theo classpath và Environment runtime |

Auto-configuration metadata không tạo toàn bộ bean definitions của ứng dụng. AOT processing đi sâu hơn: nó phân tích context ở build time, tạo mã Java/bytecode và runtime hints để giảm công việc phải làm khi khởi động.

### 7.2. Điều kiện được đánh giá ở build time

Với ứng dụng AOT-processed, classpath phải được xác định đầy đủ tại build time. Các condition ảnh hưởng việc bean có tồn tại hay không được đánh giá theo Environment khi build AOT.

Điều đó có nghĩa:

- Dependency classpath được dùng lúc build phải tương ứng với artifact chạy.
- Profile ảnh hưởng tới bean presence phải được chọn khi build AOT.
- Property như app.report.enabled nếu quyết định có tạo bean hay không sẽ được xét ở build time.
- Bean đã được tạo trong quá trình AOT không thể được tắt lại bằng cách đổi property lúc chạy.
- Không nên thiết kế feature flag với kỳ vọng có thể thay đổi cấu trúc bean tùy ý sau khi AOT artifact đã được tạo.

Ví dụ, nếu build AOT với app.report.enabled=true và bean report được tạo, thay property thành false ở runtime không tương đương với việc chạy ứng dụng ở chế độ thông thường. Hãy cấu hình Environment/profile đúng khi chạy process AOT.

Nếu ứng dụng cần bật/tắt một integration linh hoạt theo runtime property, hãy cân nhắc giữ quyết định đó ở runtime hoặc thiết kế bean luôn tồn tại nhưng tự điều khiển hành vi bên trong theo cấu hình runtime. Lựa chọn phụ thuộc vào việc property thay đổi hành vi hay thay đổi sự tồn tại của bean.

### 7.3. RuntimeHints và native image

AOT có thể tạo hoặc sử dụng RuntimeHints cho những thao tác khó suy luận bằng static analysis, ví dụ:

- Reflection.
- Đọc resource theo tên hoặc pattern.
- Serialization.
- JDK dynamic proxies.

Nếu SDK của starter dùng reflection hoặc đọc file resource động, class condition không tự giải quyết yêu cầu native image. Cần cung cấp runtime hints phù hợp, chẳng hạn qua RuntimeHintsRegistrar và cơ chế import hints của Spring Boot/Spring Framework.

Class condition trả lời liệu integration có được áp dụng. Runtime hints mô tả những thao tác dynamic mà runtime/native image cần cho phép. Đây là hai trách nhiệm riêng.

### 7.4. Khi nào nên dùng AOT?

AOT phù hợp khi:

- Muốn giảm startup time của ứng dụng.
- Classpath và tập bean tương đối ổn định giữa build và runtime.
- Có quy trình build/deploy kiểm soát profile và property ảnh hưởng conditions.
- Cần tạo native image hoặc tận dụng mã khởi tạo được sinh trước.

AOT cần được kiểm thử trên artifact đã xử lý AOT, vì test context thông thường không chứng minh native image hoặc AOT runtime hints đã đầy đủ. Với Spring Boot, ApplicationContextRunner không chạy trong native image; dùng test phù hợp cho native/AOT integration khi cần xác nhận khả năng tương thích.

## 8. Cách xác minh metadata và hành vi lọc

### 8.1. Kiểm tra file trong JAR

Sau khi build:

~~~bash
mvn clean package
jar tf target/report-autoconfigure-demo-1.0.0-SNAPSHOT.jar
~~~

Tìm các đường dẫn:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
~~~

Nếu project có @ConfigurationProperties và configuration processor, có thể còn thấy:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Trên Windows PowerShell, có thể trích metadata để đọc:

~~~powershell
jar xf target/report-autoconfigure-demo-1.0.0-SNAPSHOT.jar META-INF/spring-autoconfigure-metadata.properties
Get-Content META-INF/spring-autoconfigure-metadata.properties
~~~

Không sửa file sinh ra để ép condition khớp. Hãy sửa annotation/source hoặc build configuration rồi chạy build lại.

### 8.2. Kiểm tra runtime condition

Chạy ứng dụng với --debug để xem Condition Evaluation Report. Báo cáo giúp xác định auto-configuration nào match, không match và condition nào là lý do.

Trong test, có thể dùng ConditionEvaluationReportLoggingListener cùng ApplicationContextRunner để in report ở mức INFO hoặc DEBUG. Dùng FilteredClassLoader để kiểm tra nhánh khi SDK thiếu.

Một bộ test nên bao gồm:

| SDK | Property | Kết quả |
| --- | --- | --- |
| Có | Thiếu, mặc định bật | Bean được tạo |
| Có | true | Bean được tạo |
| Có | false | Bean không được tạo |
| Không | true | Integration bị bỏ qua |
| Không | false | Integration bị bỏ qua |
| Có | true và user bean có sẵn | Bean mặc định back off |

### 8.3. Kiểm tra artifact consumer

Test trong module autoconfigure thường có SDK trên test classpath. Vì vậy, test dùng FilteredClassLoader là cần thiết nhưng chưa đủ để chứng minh dependency graph của consumer đúng.

Cần kiểm tra thêm:

- Maven dependency tree hoặc Gradle runtime classpath của ứng dụng sample.
- JAR autoconfigure đã publish có imports file và autoconfigure metadata.
- Starter bundle chỉ kéo những dependency cần cho trải nghiệm mặc định.
- Ứng dụng chỉ dùng autoconfigure module mà không cài SDK có thể khởi động và bỏ qua integration.
- Ứng dụng thêm starter chuẩn có SDK runtime dependency thì integration được kích hoạt.

## 9. Tối ưu condition mà không làm startup khó dự đoán

### 9.1. Ưu tiên condition rẻ và có thể đánh giá từ metadata

Class presence và property là các tín hiệu đơn giản. Hãy đặt class condition ở configuration boundary để Boot có thể bỏ qua toàn bộ nhánh tích hợp khi SDK vắng mặt.

Không thực hiện công việc nặng trong condition:

- Không mở kết nối database hoặc broker.
- Không gửi HTTP request để kiểm tra service bên ngoài.
- Không đọc file lớn hoặc scan toàn bộ filesystem.
- Không tạo bean nghiệp vụ để quyết định condition.
- Không dùng condition làm nơi chạy health check.

Condition nên là quyết định cấu hình nhanh và xác định. Kiểm tra kết nối thật thuộc lifecycle của client/health indicator hoặc integration test.

### 9.2. Tránh component scan rộng trong auto-configuration

Auto-configuration được nạp qua imports file. Không cần dùng component scan để tìm lại các class mà starter đã biết rõ.

Nếu integration có một vài cấu hình con hoặc component cụ thể, dùng @Import để khai báo tường minh. Điều này làm rõ phạm vi và tránh scan package chứa các thành phần không liên quan.

### 9.3. Dùng bean conditions đúng nơi

@ConditionalOnBean và @ConditionalOnMissingBean thường phụ thuộc bean definitions đã được đăng ký tới thời điểm condition được đánh giá. Spring Boot khuyến nghị đặt các bean conditions này trên auto-configuration để chúng được đánh giá sau user-defined bean definitions.

Không dùng bean condition để thay thế class condition cho optional SDK. Class condition giải quyết việc thư viện có thể được nạp hay không; bean condition giải quyết việc một bean đã được ứng dụng cung cấp hay chưa.

### 9.4. Không lạm dụng SpEL condition tham chiếu bean

@ConditionalOnExpression có thể dùng cho logic biểu thức, nhưng tham chiếu bean trong SpEL có thể khiến bean được khởi tạo rất sớm trong quá trình refresh context. Bean đó có thể không được post-process đầy đủ, ví dụ configuration properties binding, và trạng thái có thể chưa hoàn chỉnh.

Nếu chỉ kiểm tra property, dùng @ConditionalOnProperty. Nếu kiểm tra class, dùng @ConditionalOnClass. Chỉ dùng SpEL khi biểu thức thực sự cần thiết và không kích hoạt bean sớm ngoài ý muốn.

### 9.5. Thứ tự auto-configuration không phải thứ tự khởi tạo bean

@AutoConfigureBefore, @AutoConfigureAfter và @AutoConfigureOrder điều khiển thứ tự các bean definitions được đăng ký trong quá trình xử lý auto-configuration. Chúng không bảo đảm thứ tự instance bean được khởi tạo; việc đó phụ thuộc dependency injection và các quan hệ như @DependsOn.

Dùng ordering để giải quyết phụ thuộc cấu hình, không dùng nó như một thủ thuật tối ưu startup hoặc ép một SDK khởi tạo trước mọi thứ.

## 10. Lỗi thường gặp

1. **Chỉ tạo AutoConfiguration.imports rồi cho rằng đã tối ưu.** File này tìm ứng viên; condition và metadata mới quyết định nhánh nào cần xử lý.
2. **Quên spring-boot-autoconfigure-processor.** Runtime condition vẫn có thể chạy nhưng file metadata tối ưu không được tạo.
3. **Đặt processor ở starter rỗng thay vì module autoconfigure.** Processor phải chạy ở module chứa source auto-configuration.
4. **Nhầm autoconfigure metadata với configuration metadata JSON.** Một file giúp lọc condition; file kia hỗ trợ IDE và property documentation.
5. **Tự viết spring-autoconfigure-metadata.properties.** File được sinh bởi processor; sửa thủ công dễ sai và bị ghi đè.
6. **Đặt optional SDK type trong method signature của configuration không có class boundary.** JVM có thể nạp type trước khi method-level condition có hiệu lực.
7. **Chỉ gắn @ConditionalOnClass lên @Bean method.** Với optional return/parameter type, hãy cô lập method trong nested configuration có class-level condition.
8. **Dùng class literal trong meta-annotation condition.** Với composed annotation, dùng thuộc tính name.
9. **Dùng component scan rộng trong auto-configuration.** Điều này có thể làm Spring xử lý thêm nhiều class không liên quan.
10. **Cho rằng @ConditionalOnClass thay thế dependency declaration.** Condition chỉ quyết định có áp dụng cấu hình; nó không thêm SDK vào runtime classpath.
11. **Đánh dấu dependency optional nhưng starter không khai báo lại.** Ứng dụng thêm starter có thể thiếu SDK mà feature mặc định cần.
12. **Dùng @ConditionalOnMissingBean thay class condition.** Bean condition không bảo vệ việc nạp optional class.
13. **Gọi network hoặc database trong condition.** Startup trở nên chậm, phụ thuộc môi trường và khó kiểm thử.
14. **Cho rằng AOT vẫn cho phép thay property làm thay đổi bean presence ở runtime.** Conditions ảnh hưởng bean được đánh giá trong quá trình AOT build.
15. **Quên RuntimeHints cho reflection/resource trong native image.** Class condition không tự đăng ký các thao tác dynamic cần thiết.
16. **Chỉ test khi SDK có mặt.** Cần test classpath thiếu bằng FilteredClassLoader.
17. **Chỉ kiểm tra test context mà không kiểm tra JAR.** Artifact publish phải chứa imports file và metadata đúng.
18. **Dùng @AutoConfigureBefore để ép thứ tự khởi tạo instance.** Annotation chỉ điều khiển thứ tự bean definitions.

## 11. Checklist trước khi phát hành custom starter

- [ ] Mỗi auto-configuration được liệt kê trong AutoConfiguration.imports.
- [ ] Auto-configuration không bị component scan tìm lại ngoài ý muốn.
- [ ] SDK tùy chọn được khai báo đúng scope trong module autoconfigure.
- [ ] Starter module khai báo dependency cần cho trải nghiệm mặc định.
- [ ] @ConditionalOnClass bảo vệ integration phụ thuộc SDK.
- [ ] Optional type được cô lập trong nested configuration.
- [ ] Property condition có default rõ ràng nếu feature có cờ bật/tắt.
- [ ] @ConditionalOnMissingBean cho phép ứng dụng thay bean mặc định khi phù hợp.
- [ ] spring-boot-autoconfigure-processor chạy trong module chứa auto-configuration.
- [ ] JAR chứa spring-autoconfigure-metadata.properties.
- [ ] Không nhầm file đó với spring-configuration-metadata.json.
- [ ] Test có SDK và test thiếu SDK bằng FilteredClassLoader.
- [ ] Test feature property bật/tắt và user bean back-off.
- [ ] Condition Evaluation Report có thể giải thích nhánh bị bỏ qua.
- [ ] Nếu dùng AOT, Environment/profile được cấu hình tại build time.
- [ ] Nếu dùng native image, RuntimeHints cho reflection/resources/serialization/proxies đã được kiểm tra.
- [ ] Kiểm tra dependency graph và nội dung JAR consumer thực tế.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** AutoConfiguration.imports có nhiệm vụ gì?  
**Đáp án:** Liệt kê các auto-configuration class mà Spring Boot có thể khám phá trong JAR.

**Câu 2.** spring-autoconfigure-metadata.properties được tạo bởi processor nào?  
**Đáp án:** spring-boot-autoconfigure-processor.

**Câu 3.** Metadata file này giúp tăng tốc bằng cách nào?  
**Đáp án:** Boot dùng metadata condition được hỗ trợ để lọc sớm các auto-configuration không khớp trước khi xử lý sâu.

**Câu 4.** spring-configuration-metadata.json khác gì?  
**Đáp án:** Nó mô tả configuration properties để IDE hỗ trợ autocomplete/documentation; không phải file lọc auto-configuration.

**Câu 5.** Vì sao @ConditionalOnClass có thể kiểm tra class không nằm trên runtime classpath?  
**Đáp án:** Spring Boot đọc annotation metadata bằng ASM, không cần nạp class theo cách thông thường để lấy tên kiểu.

**Câu 6.** Vì sao condition trên @Bean method có thể quá muộn khi return type là optional class?  
**Đáp án:** JVM/introspection có thể phải nạp class và method signature trước khi method condition được áp dụng; nested configuration tạo ranh giới class-level an toàn.

**Câu 7.** Có nên gọi HTTP request trong condition để xác nhận SDK hoạt động không?  
**Đáp án:** Không. Condition cần nhanh và xác định; kiểm tra kết nối thuộc health check hoặc integration test.

**Câu 8.** AOT có cho phép thay app.report.enabled để bật/tắt bean sau khi build không?  
**Đáp án:** Không nếu property đó quyết định bean presence trong AOT processing; condition được đánh giá theo Environment lúc build.

**Câu 9.** Class condition có tự thêm dependency vào runtime classpath không?  
**Đáp án:** Không. Dependency phải được cung cấp bởi consumer hoặc starter; condition chỉ quyết định có áp dụng cấu hình hay không.

**Câu 10.** RuntimeHints giải quyết vấn đề nào?  
**Đáp án:** Mô tả những thao tác như reflection, resource loading, serialization và JDK proxies cần được cho phép trong môi trường AOT/native.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, candidate imports, class conditions và autoconfigure metadata: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — ConditionalOnClass: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.5 API — AutoConfigurationImportFilter: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html
- Spring Boot 3.5 API — AutoConfigurationMetadata: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfigurationMetadata.html
- Spring Boot 3.5 Reference — Ahead-of-Time Processing: https://docs.spring.io/spring-boot/3.5/reference/packaging/aot.html
- Spring Boot 3.5 How-to — Ahead-of-Time Processing and condition limitations: https://docs.spring.io/spring-boot/3.5/how-to/aot.html
- Spring Framework Reference — Ahead-of-Time Optimizations and RuntimeHints: https://docs.spring.io/spring-framework/reference/core/aot.html

**Ghi nhớ:** AutoConfiguration.imports tìm các ứng viên; spring-autoconfigure-metadata.properties giúp Boot lọc sớm; @ConditionalOnClass bảo vệ nhánh cần thư viện; nested configuration giữ optional type khỏi bị nạp quá sớm. AOT tiến thêm một bước bằng cách xử lý context ở build time, vì vậy classpath và các property quyết định bean phải được chọn trước khi đóng gói artifact.
