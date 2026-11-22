# Tác dụng phụ khi quét nhầm package tự cấu hình hoặc nhập cấu hình nội bộ trực tiếp

## 1. Vì sao một auto-configuration có thể chạy ngoài ý muốn?

Một thư viện Spring Boot thường cung cấp auto-configuration để đăng ký các bean mặc định khi ứng dụng thêm starter. Cấu hình đó có thể phụ thuộc vào classpath, property, web stack hoặc bean do ứng dụng cung cấp.

Spring Boot có một đường nạp riêng cho auto-configuration: class được công bố trong file AutoConfiguration.imports của JAR, sau đó được xử lý trong pipeline auto-configuration với ordering và condition tương ứng.

Sự cố xuất hiện khi ứng dụng hoặc chính thư viện vô tình mở rộng component scan tới package chứa các class tự cấu hình. Một class được đánh dấu @AutoConfiguration cũng là một @Configuration class. Vì vậy, nếu package đó nằm trong phạm vi @ComponentScan, Spring có thể phát hiện class như một component cấu hình thông thường.

Một tình huống khác là ứng dụng import trực tiếp một class cấu hình nội bộ nằm bên trong thư viện. Khi đó, cấu hình nội bộ có thể được đăng ký mà không đi qua các điều kiện ở class auto-configuration bên ngoài.

Hậu quả có thể gồm:

- Bean mặc định xuất hiện dù feature property đang tắt.
- Exclusion không loại được cấu hình bị component scan hoặc @Import trực tiếp nạp vào.
- @ConditionalOnMissingBean đánh giá quá sớm và không thấy bean tùy chỉnh của ứng dụng.
- Bean trùng tên gây BeanDefinitionOverrideException.
- Nhiều bean cùng type làm injection trở nên mơ hồ và gây NoUniqueBeanDefinitionException.
- Optional integration được nạp dù dependency hoặc feature tương ứng không nên hoạt động.
- Ứng dụng có bean, controller, repository hoặc security configuration ngoài dự kiến.
- Test dùng auto-configuration runner cho kết quả khác với ứng dụng thật có component scan rộng.

Bài dùng **Java 17 và Spring Boot 3.3.13** làm baseline. Các nguyên tắc dưới đây áp dụng cho kiến trúc auto-configuration của Spring Boot 3.x.

## 2. Phân biệt component scanning và auto-configuration imports

Hai cơ chế đều có thể đưa class cấu hình vào ApplicationContext, nhưng mục đích và thứ tự xử lý khác nhau.

### 2.1. Component scanning

@ComponentScan tìm các class phù hợp trong package được chỉ định. Các stereotype phổ biến được phát hiện gồm:

- @Component.
- @Service.
- @Repository.
- @Controller và @RestController.
- @Configuration.
- Các annotation tùy chỉnh được meta-annotate bằng @Component.

@SpringBootApplication bao gồm @ComponentScan. Nếu không tùy chỉnh package scan, package của class được đánh dấu @SpringBootApplication là scan root mặc định.

Ví dụ:

~~~java
package com.example.app;

import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
}
~~~

Với cấu trúc này, component scan mặc định tập trung vào package com.example.app và các package con.

Nếu đổi thành:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.example",
        "com.acme"
})
public class Application {
}
~~~

Spring sẽ quét cả package com.acme và các package con. Nếu thư viện Acme đặt auto-configuration hoặc helper @Configuration trong vùng đó, các class này có thể bị phát hiện như component.

### 2.2. Auto-configuration imports

Spring Boot tìm file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File liệt kê các auto-configuration class mà thư viện công bố, mỗi dòng một fully qualified class name:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
com.acme.reports.autoconfigure.ReportsWebAutoConfiguration
~~~

Các class này được Spring Boot nạp trong cơ chế auto-configuration. Cơ chế đó áp dụng exclusions, ordering và điều kiện phù hợp trước khi đăng ký cấu hình.

### 2.3. Vì sao @AutoConfiguration vẫn có thể bị component scan tìm thấy?

@AutoConfiguration là annotation meta-annotated bằng @Configuration. @Configuration lại là một component stereotype của Spring. Vì vậy, auto-configuration class có thể trở thành candidate của component scanner nếu package của nó bị quét.

Điều này không có nghĩa component scan là cách hợp lệ để phát hành auto-configuration. Tài liệu Spring Boot yêu cầu auto-configuration chỉ được nạp bằng cách khai báo trong AutoConfiguration.imports, đặt trong package riêng và không trở thành mục tiêu của component scan.

**Quy tắc thiết kế:** Auto-configuration là entry point do Spring Boot quản lý; component scan dành cho component thuộc phạm vi ứng dụng.

## 3. Pipeline xử lý và điểm khác biệt quan trọng

Có thể hình dung hai đường nạp như sau:

~~~text
ĐƯỜNG AUTO-CONFIGURATION
AutoConfiguration.imports
          |
          v
Tập hợp candidates
          |
          v
Exclusions và auto-configuration ordering
          |
          v
Conditions của auto-configuration
          |
          v
Đăng ký bean definitions
          |
          v
Khởi tạo bean theo dependency


ĐƯỜNG COMPONENT SCAN / @Import TRỰC TIẾP
@ComponentScan hoặc @Import
          |
          v
Phát hiện / nhập configuration class
          |
          v
Conditions gắn trực tiếp lên class hoặc bean method
          |
          v
Đăng ký bean definitions
          |
          v
Khởi tạo bean theo dependency
~~~

Điểm cần nhớ:

1. Component scan không tự áp dụng danh sách exclusions của AutoConfigurationImportSelector.
2. @Import trực tiếp không đưa class vào danh sách auto-configuration candidates để Boot sắp xếp theo @AutoConfigureBefore hoặc @AutoConfigureAfter.
3. Condition gắn trực tiếp trên class hoặc bean method vẫn được đánh giá khi class được scan/import.
4. Condition ở class auto-configuration bên ngoài không tự trở thành condition của một helper configuration được scan độc lập.
5. @ConditionalOnBean và @ConditionalOnMissingBean chỉ nhìn các bean definitions đã được xử lý tại thời điểm đánh giá. Đường auto-configuration được thiết kế để chạy sau các user-defined bean definitions; cấu hình bị scan như configuration thông thường có thể được xử lý ở thời điểm khác.

Không nên suy luận rằng mọi condition đều bị bỏ qua khi scan nhầm package. Condition trên chính class bị scan vẫn có hiệu lực. Vấn đề là đường nạp đã thay đổi, nên exclusions, ordering và điều kiện ở cấu hình cha có thể không còn bảo vệ cấu hình con.

## 4. Tác dụng phụ khi quét nhầm package

### 4.1. Bean xuất hiện dù property của feature đang tắt

Giả sử thư viện có cấu hình:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@Import(ReportsClientConfiguration.class)
public class ReportsAutoConfiguration {
}
~~~

Property false sẽ ngăn auto-configuration bên ngoài được áp dụng. Trong đường nạp đúng, helper ReportsClientConfiguration chỉ được import khi điều kiện của ReportsAutoConfiguration khớp.

Nhưng nếu ứng dụng quét thẳng package chứa helper:

~~~java
@ComponentScan("com.acme.reports.autoconfigure")
~~~

component scanner có thể phát hiện ReportsClientConfiguration độc lập. Bean method bên trong helper được xử lý dù property của cấu hình cha đang false.

Kết quả là feature bị tắt ở cấp auto-configuration nhưng bean của feature vẫn xuất hiện do một đường nạp khác.

### 4.2. Exclusion không còn chặn được cấu hình

Ứng dụng có thể loại auto-configuration:

~~~java
@SpringBootApplication(
        excludeName =
                "com.acme.reports.autoconfigure.ReportsAutoConfiguration")
public class Application {
}
~~~

Exclusion này điều khiển việc import candidate trong cơ chế auto-configuration.

Nếu cùng class cũng được component scan tìm thấy, component scanner vẫn có thể đăng ký nó như configuration class thông thường. Exclusion không phải bộ lọc toàn cục cho mọi đường nạp class cấu hình.

Tương tự, nếu ứng dụng trực tiếp @Import một internal configuration, exclusion tên auto-configuration bên ngoài không tự loại internal configuration đó.

### 4.3. Ordering bị bỏ qua

Các annotation:

~~~java
@AutoConfigureBefore(...)
@AutoConfigureAfter(...)
@AutoConfiguration(beforeName = "...")
@AutoConfiguration(afterName = "...")
~~~

được sử dụng để sắp xếp auto-configuration trong pipeline của Spring Boot.

Nếu một auto-configuration được component scan hoặc @Import trực tiếp, không nên kỳ vọng các metadata ordering đó tiếp tục điều khiển thứ tự như khi class được nạp qua AutoConfiguration.imports.

Điều này có thể làm condition theo bean nhìn thấy trạng thái khác, nhất là khi hai cấu hình cùng cung cấp bean mặc định hoặc phụ thuộc vào bean do cấu hình còn lại đăng ký.

Ordering của auto-configuration cũng chỉ ảnh hưởng thứ tự đăng ký bean definitions. Thứ tự tạo object thực tế vẫn do dependency và @DependsOn quyết định.

### 4.4. @ConditionalOnMissingBean đánh giá sai thời điểm

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
public class ReportsClientConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportClient.class)
    ReportClient reportClient() {
        return new ReportClient("https://default.example.test");
    }
}
~~~

@ConditionalOnMissingBean dựa vào bean definitions đã được xử lý tại thời điểm condition chạy.

Trong auto-configuration thông thường, Spring Boot nạp auto-configuration sau các user-defined bean definitions. Vì vậy bean tùy chỉnh của ứng dụng thường đã được đăng ký để default bean có thể back off.

Nếu helper configuration bị component scan và xử lý như cấu hình ứng dụng thông thường, nó có thể được đánh giá trước khi user configuration khác được xử lý. Khi đó condition có thể chưa nhìn thấy bean tùy chỉnh.

Các biểu hiện có thể gồm:

- Default bean vẫn được đăng ký.
- Cùng type có nhiều candidate.
- Bean name trùng nhau gây lỗi đăng ký.
- Kết quả phụ thuộc vào thứ tự xử lý configuration.

Đây là một lý do Spring Boot khuyến nghị đặt @ConditionalOnBean và @ConditionalOnMissingBean trên auto-configuration class hoặc bean method thuộc đường auto-configuration, thay vì dùng chúng như cơ chế lựa chọn bean chung cho mọi configuration được scan.

### 4.5. Optional integration bị nạp ngoài ý muốn

Giả sử auto-configuration ngoài có:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.optional.PdfSdk")
@ConditionalOnProperty(
        prefix = "acme.reports.pdf",
        name = "enabled",
        havingValue = "true")
@Import(PdfClientConfiguration.class)
public class PdfAutoConfiguration {
}
~~~

Nếu ứng dụng import trực tiếp PdfClientConfiguration, các condition của PdfAutoConfiguration không tự áp dụng cho helper.

Nếu helper tham chiếu class tùy chọn không có trên classpath, quá trình phân tích hoặc nạp class có thể thất bại với lỗi như NoClassDefFoundError. Nếu dependency có mặt nhưng property tắt, helper vẫn có thể tạo bean không mong muốn.

Mỗi helper có ranh giới dependency tùy chọn phải được thiết kế sao cho không thể bị nạp an toàn chỉ nhờ một condition ở class cha nếu nó có khả năng được import độc lập.

### 4.6. Bean pollution và lỗi injection

Quét package quá rộng có thể đưa thêm component không thuộc ứng dụng vào context:

- Một service nội bộ không dành cho consumer.
- Repository kết nối tới data source không được cấu hình.
- Controller tạo endpoint ngoài dự kiến.
- Security filter hoặc configuration thay đổi chain.
- Hai implementation cùng type khiến injection không xác định được candidate.

Các lỗi thường gặp:

~~~text
NoUniqueBeanDefinitionException
BeanDefinitionOverrideException
NoSuchBeanDefinitionException
NoClassDefFoundError
~~~

Tên lỗi cụ thể phụ thuộc loại xung đột và thời điểm bean được tạo.

### 4.7. Test và production có thể khác nhau

Một test dùng:

~~~java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(ReportsAutoConfiguration.class));
~~~

sẽ kiểm tra đường auto-configuration được chỉ định. Nó không tự tái tạo một @ComponentScan rộng trong ứng dụng.

Do đó, unit test auto-configuration có thể pass trong khi ứng dụng thật vẫn nạp helper từ component scan. Cần có consumer test sử dụng đúng package scanning và đúng starter JAR của ứng dụng.

## 5. Đặt package của ứng dụng ở đâu?

### 5.1. Đặt main application class trong root package của ứng dụng

Cấu trúc tốt:

~~~text
com.example.app
├── Application.java
├── customer
│   ├── CustomerController.java
│   └── CustomerService.java
└── billing
    ├── BillingController.java
    └── BillingService.java

com.acme.reports
├── ReportClient.java
└── autoconfigure
    ├── ReportsAutoConfiguration.java
    └── internal
        └── ReportsClientConfiguration.java
~~~

Main class:

~~~java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Scan root mặc định là com.example.app. Package com.acme.reports nằm ngoài vùng component scan của ứng dụng; Spring Boot vẫn tìm ReportsAutoConfiguration qua AutoConfiguration.imports.

### 5.2. Tránh default package

Không đặt main class hoặc class Java trong default package, tức không có khai báo package.

Default package có thể khiến các cơ chế scanning phải đọc class từ rất nhiều JAR trên classpath. Điều đó làm phạm vi tìm kiếm khó kiểm soát và có thể gây thêm component ngoài dự kiến.

Dùng package theo reversed domain name, ví dụ com.example.app.

### 5.3. Nếu ứng dụng có nhiều package nghiệp vụ

Nếu cần scan nhiều package thuộc chính ứng dụng, dùng marker class để chỉ rõ từng vùng:

~~~java
@SpringBootApplication(scanBasePackageClasses = {
        Application.class,
        BillingPackage.class,
        CustomerPackage.class
})
public class Application {
}
~~~

Các marker class nên nằm trong package thuộc source code ứng dụng. Không dùng marker class từ thư viện ngoài để vô tình mở rộng scan root sang package vendor.

scanBasePackageClasses và scanBasePackages điều khiển component scan. Chúng không thay thế các cơ chế chuyên biệt như @EntityScan hoặc @ConfigurationPropertiesScan.

### 5.4. Không mở rộng scan root tới toàn bộ dependency namespace

Ví dụ dễ gây rủi ro:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.example",
        "com.acme",
        "org.springframework"
})
public class Application {
}
~~~

Đây là phạm vi quá rộng. Spring có thể đọc các configuration/component trong nhiều thư viện mà ứng dụng không có ý định quản lý bằng component scan.

Chỉ scan package mà ứng dụng sở hữu. Các thư viện Spring Boot nên tự công bố auto-configuration theo cơ chế imports.

## 6. Thiết kế đúng custom auto-configuration

### 6.1. Auto-configuration là entry point

Class auto-configuration nên:

- Có annotation @AutoConfiguration.
- Có condition phù hợp với classpath, property hoặc bean.
- Được công bố trong AutoConfiguration.imports.
- Không nằm trong package mà ứng dụng consumer quét.
- Không bật @ComponentScan để tìm helper.
- Dùng @Import cụ thể để nạp cấu hình nội bộ cần thiết.

Ví dụ:

~~~java
package com.acme.reports.autoconfigure;

import com.acme.reports.autoconfigure.internal.ReportsClientConfiguration;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Import;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@Import(ReportsClientConfiguration.class)
public class ReportsAutoConfiguration {
}
~~~

### 6.2. Helper configuration được import tường minh

~~~java
package com.acme.reports.autoconfigure.internal;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportsClientConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportClient.class)
    public ReportClient reportClient() {
        return new ReportClient("https://reports.example.test");
    }
}
~~~

Helper này được root auto-configuration import khi điều kiện của root thỏa mãn.

Trong thư viện thực tế, có thể giữ helper class ở package nội bộ hoặc dùng nested configuration để hạn chế việc consumer phụ thuộc vào class implementation. Nếu helper không cần là public API, không nên khuyến khích consumer import trực tiếp nó.

### 6.3. AutoConfiguration.imports chỉ liệt kê entry point

Tạo file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

Không liệt kê helper configuration như một auto-configuration candidate riêng nếu nó chỉ là chi tiết triển khai được root class import.

### 6.4. Không dùng component scan bên trong auto-configuration

Không viết:

~~~java
@AutoConfiguration
@ComponentScan("com.acme.reports")
public class ReportsAutoConfiguration {
}
~~~

Cách này khiến phạm vi đăng ký bean phụ thuộc vào package layout và stereotype annotation của mọi class bên trong package.

Dùng:

~~~java
@AutoConfiguration
@Import({
        ReportsClientConfiguration.class,
        ReportsMetricsConfiguration.class
})
public class ReportsAutoConfiguration {
}
~~~

Danh sách import tường minh giúp reviewer biết chính xác cấu hình nào được kích hoạt và giúp package nội bộ có thể thay đổi mà không làm thay đổi phạm vi scan.

## 7. Phân biệt import auto-configuration và import helper nội bộ

Không phải mọi @Import đều sai. Cần phân biệt hai tình huống.

### 7.1. Đúng: root auto-configuration import helper

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@Import(ReportsClientConfiguration.class)
public class ReportsAutoConfiguration {
}
~~~

Spring Boot nạp root class qua AutoConfiguration.imports. Root condition quyết định helper có được import hay không. Helper được import cụ thể và là một phần triển khai của feature.

### 7.2. Rủi ro: ứng dụng import helper trực tiếp

~~~java
@Configuration(proxyBeanMethods = false)
@Import(ReportsClientConfiguration.class)
public class ApplicationConfiguration {
}
~~~

Cấu hình ứng dụng đã bỏ qua ReportsAutoConfiguration. Condition property ở root không còn bảo vệ helper. Nếu property acme.reports.enabled=false, helper vẫn có thể tạo ReportClient.

Consumer cũng phụ thuộc vào package nội bộ của thư viện. Nếu nhà cung cấp đổi cấu trúc package hoặc tách module, code ứng dụng có thể hỏng dù API starter không đổi.

### 7.3. Import trực tiếp root auto-configuration cũng cần cân nhắc

~~~java
@Configuration(proxyBeanMethods = false)
@Import(ReportsAutoConfiguration.class)
public class ApplicationConfiguration {
}
~~~

Trong trường hợp này, condition gắn trực tiếp lên ReportsAutoConfiguration vẫn được xử lý. Tuy nhiên, class đang được nhập qua đường @Import thông thường thay vì candidate list của Boot.

Không nên kỳ vọng auto-configuration ordering và exclusions được áp dụng giống hệt đường AutoConfiguration.imports. Nếu class đã được công bố là auto-configuration, hãy để Spring Boot quản lý việc nạp nó.

### 7.4. Khi ứng dụng thật sự cần một cấu hình công khai

Nếu thư viện có use case yêu cầu consumer chủ động bật cấu hình, hãy cung cấp một API configuration được thiết kế cho consumer và tài liệu hóa rõ:

- Class nào là public API.
- Condition nào cần được cấu hình.
- Dependency nào bắt buộc.
- Bean nào được đăng ký.
- Hành vi khi kết hợp với starter auto-configuration.

Không biến package internal thành API chỉ vì consumer có thể truy cập class đó.

## 8. Ví dụ Maven hoàn chỉnh để tái hiện lỗi

Ví dụ dưới đây dùng Java 17 và Spring Boot 3.3.13. Thư viện Acme có một root auto-configuration được bảo vệ bằng property. Helper configuration tạo ReportClient.

Mục tiêu kiểm thử:

1. Auto-configuration được nạp đúng: property true tạo bean.
2. Property false: đường auto-configuration đúng không tạo bean.
3. Ứng dụng import helper trực tiếp: bean xuất hiện dù property false.
4. Component scan package thư viện: helper bị phát hiện dù root condition false.
5. Exclusion không ngăn class bị component scan nạp.
6. Bean tùy chỉnh của ứng dụng khiến default auto-configuration back off.

### 8.1. Cấu trúc project

~~~text
wrong-package-scan-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── com/example/app/
    │   │   │   └── Application.java
    │   │   └── com/acme/reports/
    │   │       ├── ReportClient.java
    │   │       └── autoconfigure/
    │   │           ├── ReportsAutoConfiguration.java
    │   │           └── internal/
    │   │               └── ReportsClientConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/tests/
            └── ReportsScanningTests.java
~~~

### 8.2. pom.xml

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
    <artifactId>wrong-package-scan-demo</artifactId>
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

### 8.3. ReportClient.java

**src/main/java/com/acme/reports/ReportClient.java**

~~~java
package com.acme.reports;

public record ReportClient(String endpoint) {
}
~~~

### 8.4. ReportsAutoConfiguration.java

**src/main/java/com/acme/reports/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.acme.reports.autoconfigure;

import com.acme.reports.autoconfigure.internal.ReportsClientConfiguration;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Import;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@Import(ReportsClientConfiguration.class)
public class ReportsAutoConfiguration {
}
~~~

### 8.5. ReportsClientConfiguration.java

**src/main/java/com/acme/reports/autoconfigure/internal/ReportsClientConfiguration.java**

~~~java
package com.acme.reports.autoconfigure.internal;

import com.acme.reports.ReportClient;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ReportsClientConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportClient.class)
    public ReportClient reportClient() {
        return new ReportClient("https://default.example.test");
    }
}
~~~

### 8.6. AutoConfiguration.imports

Tạo file:

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
com.acme.reports.autoconfigure.ReportsAutoConfiguration
~~~

Chỉ root auto-configuration được công bố. Helper được root class import bằng @Import.

### 8.7. Application.java

**src/main/java/com/example/app/Application.java**

~~~java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {

    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Application nằm trong com.example.app. Vì vậy component scan mặc định không quét com.acme.reports. Auto-configuration vẫn được tìm qua imports resource.

Để bật feature:

~~~properties
acme.reports.enabled=true
~~~

### 8.8. ReportsScanningTests.java

**src/test/java/com/example/tests/ReportsScanningTests.java**

~~~java
package com.example.tests;

import com.acme.reports.ReportClient;
import com.acme.reports.autoconfigure.ReportsAutoConfiguration;
import com.acme.reports.autoconfigure.internal.ReportsClientConfiguration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsScanningTests {

    private final ApplicationContextRunner bootRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(BootConfiguration.class);

    @Test
    void autoConfigurationCreatesDefaultWhenEnabled() {
        bootRunner.withPropertyValues("acme.reports.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://default.example.test");
                });
    }

    @Test
    void autoConfigurationDoesNotCreateBeanWhenDisabled() {
        bootRunner.withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);
                });
    }

    @Test
    void directImportOfInternalConfigurationBypassesRootProperty() {
        new ApplicationContextRunner()
                .withUserConfiguration(DirectInternalImportConfiguration.class)
                .withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                });
    }

    @Test
    void broadComponentScanFindsHelperEvenWhenRootConditionIsFalse() {
        new ApplicationContextRunner()
                .withUserConfiguration(BroadComponentScanConfiguration.class)
                .withPropertyValues("acme.reports.enabled=false")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                });
    }

    @Test
    void autoConfigurationExclusionDoesNotStopComponentScan() {
        new ApplicationContextRunner()
                .withUserConfiguration(ExclusionAndBroadScanConfiguration.class)
                .withPropertyValues("acme.reports.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                });
    }

    @Test
    void userBeanMakesDefaultAutoConfigurationBackOff() {
        bootRunner
                .withPropertyValues("acme.reports.enabled=true")
                .withUserConfiguration(CustomClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://custom.example.test");
                });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration
    static class BootConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    @Import(ReportsClientConfiguration.class)
    static class DirectInternalImportConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(basePackageClasses = ReportsAutoConfiguration.class)
    static class BroadComponentScanConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAutoConfiguration(
            excludeName =
                    "com.acme.reports.autoconfigure.ReportsAutoConfiguration")
    @ComponentScan(basePackageClasses = ReportsAutoConfiguration.class)
    static class ExclusionAndBroadScanConfiguration {
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomClientConfiguration {

        @Bean
        ReportClient customReportClient() {
            return new ReportClient("https://custom.example.test");
        }
    }
}
~~~

### 8.9. Chạy test

Trong thư mục chứa pom.xml:

~~~bash
mvn clean test
~~~

Kết quả mong đợi:

| Test | Kết quả |
| --- | --- |
| Property true qua auto-configuration | Có một ReportClient mặc định |
| Property false qua auto-configuration | Không có ReportClient |
| Import helper trực tiếp khi property false | ReportClient vẫn xuất hiện |
| Component scan package thư viện khi property false | ReportClient vẫn xuất hiện |
| Exclude root auto-configuration nhưng vẫn component scan | Class bị scan vẫn có thể tạo ReportClient |
| User bean được khai báo trước auto-configuration | Default bean back off, custom endpoint được giữ |

Hai test ở giữa cố ý tái hiện cấu hình sai để chỉ ra đường nạp đã bypass gate ở root. Chúng không phải cấu hình nên giữ trong ứng dụng production.

## 9. Cách điều tra khi bean xuất hiện ngoài ý muốn

### 9.1. Kiểm tra package scan

Tìm các khai báo có thể mở rộng phạm vi scan:

~~~text
@SpringBootApplication(scanBasePackages = ...)
@SpringBootApplication(scanBasePackageClasses = ...)
@ComponentScan(...)
@ComponentScan(basePackages = ...)
@ComponentScan(basePackageClasses = ...)
~~~

Tìm cả cấu hình XML, ImportSelector hoặc ImportBeanDefinitionRegistrar tùy chỉnh nếu ứng dụng có dùng.

Lệnh tìm kiếm trong source:

~~~bash
rg -n "@ComponentScan|scanBasePackages|basePackages|AutoConfiguration.imports|@Import" src
~~~

Xem package của main application class và package thực tế của thư viện. Xác định component scan có bao trùm package auto-configuration hay helper không.

### 9.2. Bật Condition Evaluation Report

Chạy ứng dụng với:

~~~bash
java -jar application.jar --debug
~~~

Hoặc cấu hình:

~~~properties
debug=true
~~~

Condition Evaluation Report giúp xác định auto-configuration nào match/no-match và lý do. Nếu report cho thấy root auto-configuration không match nhưng bean vẫn tồn tại, hãy kiểm tra đường component scan hoặc direct import của helper.

Có thể dùng Actuator conditions endpoint nếu ứng dụng đã có Actuator và endpoint được expose/bảo vệ phù hợp:

~~~text
GET /actuator/conditions
~~~

### 9.3. Xem nguồn của BeanDefinition

Khi biết tên bean, có thể kiểm tra metadata đăng ký:

~~~java
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.context.ConfigurableApplicationContext;

public static void inspectReportClient(
        ConfigurableApplicationContext context) {

    var beanFactory = context.getBeanFactory();

    if (!beanFactory.containsBeanDefinition("reportClient")) {
        System.out.println("reportClient definition not found");
        return;
    }

    BeanDefinition definition =
            beanFactory.getBeanDefinition("reportClient");

    System.out.println(
            "resource = " + definition.getResourceDescription());
    System.out.println(
            "factory bean = " + definition.getFactoryBeanName());
    System.out.println(
            "factory method = " + definition.getFactoryMethodName());
    System.out.println(
            "bean class = " + definition.getBeanClassName());
}
~~~

Với bean được tạo bằng @Bean method, factory bean và factory method thường giúp truy ra configuration class đã đăng ký bean. Resource description có thể có hoặc không tùy loại BeanDefinition.

Nếu có nhiều bean cùng type, liệt kê tên bean:

~~~java
String[] names = context.getBeanFactory()
        .getBeanNamesForType(ReportClient.class);

System.out.println(java.util.Arrays.toString(names));
~~~

Đừng chỉ kiểm tra getBean(type) rồi kết luận. Nếu có nhiều candidate, tra cứu theo type có thể ném NoUniqueBeanDefinitionException; danh sách tên giúp thấy các nguồn đăng ký.

### 9.4. So sánh context test với context ứng dụng

Dùng ApplicationContextRunner để kiểm tra riêng:

- Auto-configuration đúng với property true/false.
- User-defined bean có làm default back off không.
- Helper bị import trực tiếp có tạo bean không.
- Component scan package rộng có tìm thấy helper không.
- Exclusion có bị một đường scan khác bỏ qua không.

Sau đó chạy consumer smoke test bằng đúng starter JAR và cấu hình component scan của ứng dụng. Đây là cách phát hiện khác biệt giữa test auto-configuration cô lập và application context thực tế.

## 10. Cách khắc phục theo thứ tự

### 10.1. Thu hẹp component scan trước

Đặt main class trong root package của ứng dụng và chỉ scan package ứng dụng sở hữu.

Thay:

~~~java
@SpringBootApplication(scanBasePackages = {
        "com.example",
        "com.acme"
})
~~~

bằng:

~~~java
@SpringBootApplication
~~~

nếu main class đã nằm trong root package phù hợp.

Nếu ứng dụng cần nhiều vùng package riêng, dùng marker class thuộc source code ứng dụng.

### 10.2. Đưa auto-configuration ra ngoài scan root

Đặt package của thư viện dưới namespace riêng, ví dụ com.acme.reports, trong khi application scan chỉ nhắm vào com.example.app.

Không dựa vào việc class là internal hoặc package-private để bảo vệ nó khỏi component scan. Biện pháp chính là không quét package đó.

### 10.3. Loại bỏ @ComponentScan khỏi auto-configuration

Thay component scan bên trong auto-configuration bằng @Import cụ thể.

Nếu helper chỉ phục vụ một nhánh optional integration, import helper từ nested configuration đã có condition tương ứng.

### 10.4. Không import internal configuration trong application

Nếu consumer đang có:

~~~java
@Import(ReportsClientConfiguration.class)
~~~

hãy bỏ import đó và thêm starter/artifact đã công bố. Để Spring Boot nạp ReportsAutoConfiguration từ imports resource.

Nếu ứng dụng cần một tính năng riêng, yêu cầu nhà cung cấp cung cấp API configuration được hỗ trợ thay vì dùng class trong package internal.

### 10.5. Đưa condition vào đúng ranh giới

Root auto-configuration nên chứa điều kiện bật feature. Helper configuration chỉ được import qua root class.

Với optional class, có thể cô lập classpath condition trong nested configuration:

~~~java
@AutoConfiguration
public class ReportsAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.optional.PdfSdk")
    @ConditionalOnProperty(
            prefix = "acme.reports.pdf",
            name = "enabled",
            havingValue = "true")
    static class PdfConfiguration {

        @Bean
        PdfClient pdfClient() {
            return new PdfClient();
        }
    }
}
~~~

Cách này giữ các tham chiếu tới optional API trong vùng configuration có condition tương ứng. Tuy nhiên, nếu nested configuration vẫn nằm trong package bị quét trực tiếp hoặc bị import độc lập, hãy bảo đảm ranh giới condition của chính nó đủ an toàn.

### 10.6. Dùng exclusion filter như giải pháp chuyển tiếp

Nếu chưa thể thu hẹp package scan ngay, có thể loại rõ auto-configuration hoặc internal package khỏi component scan:

~~~java
@ComponentScan(
        basePackages = "com.acme",
        excludeFilters = @ComponentScan.Filter(
                type = FilterType.REGEX,
                pattern = "com\\.acme\\.reports\\.autoconfigure\\..*"))
~~~

Đây là biện pháp bảo vệ ở ứng dụng. Nó không thay thế việc thiết kế package scan hẹp và có thể cần cập nhật khi package thư viện thay đổi.

Nếu chỉ muốn loại một class, có thể dùng ASSIGNABLE_TYPE filter. Nếu cần loại cả package nội bộ, regex package có thể dễ quản lý hơn nhưng phải kiểm tra kỹ pattern.

## 11. Các nguyên tắc thiết kế để tránh tái diễn

### Với ứng dụng tiêu thụ

- [ ] Main application class nằm trong root package của ứng dụng.
- [ ] Component scan chỉ bao phủ package do ứng dụng quản lý.
- [ ] Không scan namespace của vendor hoặc org.springframework.
- [ ] Không import package internal của starter.
- [ ] Dùng exclusions chỉ cho auto-configuration candidate được công bố.
- [ ] Dùng @EntityScan hoặc @ConfigurationPropertiesScan riêng khi cần phạm vi chuyên biệt.

### Với thư viện/starter

- [ ] @AutoConfiguration class được liệt kê trong AutoConfiguration.imports.
- [ ] Auto-configuration nằm trong package riêng và không bị scan.
- [ ] Không bật @ComponentScan bên trong auto-configuration.
- [ ] Dùng @Import cụ thể cho helper configuration.
- [ ] Optional integration có classpath condition riêng.
- [ ] @ConditionalOnMissingBean đặt ở đường auto-configuration được xử lý sau user beans.
- [ ] Helper nội bộ không được quảng bá như API consumer.
- [ ] Starter không kéo dependency tùy chọn không cần thiết vào classpath mặc định.
- [ ] Có consumer test cho cả property enabled và disabled.
- [ ] Có test phát hiện component scan nhầm package và direct import helper.

## 12. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Bean xuất hiện dù property feature false | Helper config bị scan/import độc lập | Thu hẹp scan; import helper chỉ từ root auto-config |
| excludeName không loại được bean | Class vẫn được component scan hoặc direct import | Xác định đường nạp và loại đúng đường đó |
| Default bean không back off cho custom bean | @ConditionalOnMissingBean chạy trước khi custom definition được xử lý | Để bean default trong auto-configuration path |
| Nhiều bean cùng type | Hai configuration cùng đăng ký implementation | Tìm bean names và nguồn BeanDefinition |
| BeanDefinitionOverrideException | Hai definition dùng cùng bean name | Loại đường đăng ký trùng và đặt ownership rõ |
| NoClassDefFoundError khi optional SDK vắng mặt | Helper bị nạp trực tiếp ngoài classpath gate | Cô lập optional API trong nested configuration có condition |
| @AutoConfigureAfter không còn tác dụng | Auto-config bị scan/import như config thông thường | Chỉ nạp auto-config qua imports |
| Unit test pass nhưng production fail | Test runner không tái tạo broad scan của ứng dụng | Thêm consumer test với package scan thật |
| Component scan bắt cả controller/repository ngoài dự kiến | scanBasePackages quá rộng | Dùng marker package và scan root của ứng dụng |
| Đổi package thư viện làm ứng dụng hỏng | Consumer phụ thuộc class internal | Dùng starter/API công khai và migration guide |
| @Import helper làm feature bật dù disabled | Import bỏ qua condition của root class | Gỡ import trực tiếp; dùng entry point đã công bố |
| Condition report root no-match nhưng bean vẫn có | Có đường đăng ký khác | Kiểm tra component scan, @Import và BeanDefinition source |

## 13. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao @AutoConfiguration có thể bị component scan phát hiện?  
**Đáp án:** Vì @AutoConfiguration meta-annotated bằng @Configuration và @Configuration là component stereotype. Nếu package bị scan, class có thể được phát hiện như configuration thông thường.

**Câu 2.** Auto-configuration class nên được nạp bằng cơ chế nào?  
**Đáp án:** Khai báo class trong META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.

**Câu 3.** Vì sao component scan package của thư viện có thể làm feature property false nhưng helper bean vẫn xuất hiện?  
**Đáp án:** Helper configuration có thể được scan độc lập, không đi qua condition ở root auto-configuration.

**Câu 4.** @SpringBootApplication mặc định component scan từ đâu?  
**Đáp án:** Package chứa class được đánh dấu @SpringBootApplication và các package con, trừ khi cấu hình scan root khác.

**Câu 5.** ExcludeName có chặn class bị component scan không?  
**Đáp án:** Không. Exclusion điều khiển auto-configuration import candidates; component scan là một đường đăng ký riêng.

**Câu 6.** Có nên dùng @ComponentScan trong custom auto-configuration để tìm helper không?  
**Đáp án:** Không. Dùng @Import cụ thể để danh sách cấu hình được kiểm soát và không phụ thuộc package scanning.

**Câu 7.** Vì sao @ConditionalOnMissingBean nhạy với việc scan nhầm?  
**Đáp án:** Condition chỉ thấy bean definitions đã được xử lý. Auto-configuration chuẩn chạy sau user definitions; helper bị scan như config thông thường có thể được xử lý quá sớm.

**Câu 8.** Nếu ứng dụng cần import một class configuration nội bộ của starter, nên làm gì?  
**Đáp án:** Yêu cầu thư viện cung cấp API configuration được hỗ trợ hoặc dùng starter. Không phụ thuộc package internal.

**Câu 9.** Làm sao tìm nguồn tạo ra một bean bất ngờ?  
**Đáp án:** Liệt kê bean names theo type, đọc BeanDefinition factoryBeanName/factoryMethodName/resourceDescription, bật --debug và kiểm tra component scan/imports.

**Câu 10.** Vì sao cần consumer test ngoài unit test auto-configuration?  
**Đáp án:** Consumer test tái hiện classpath, imports resource và package scan của ứng dụng thật, giúp phát hiện đường nạp ngoài ý muốn mà runner cô lập có thể bỏ qua.

## 14. Tài liệu tham khảo chính thức

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — Structuring Your Code](https://docs.spring.io/spring-boot/3.3/reference/using/structuring-your-code.html)
- [Spring Boot 3.3 — Using the @SpringBootApplication Annotation](https://docs.spring.io/spring-boot/3.3/reference/using/using-the-springbootapplication-annotation.html)
- [Spring Boot 3.3 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3 API — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Framework 6.1 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.1/core/beans/classpath-scanning.html)

**Ghi nhớ:** Auto-configuration phải đi qua AutoConfiguration.imports để Spring Boot quản lý conditions, ordering và exclusions. Component scan chỉ nên nhắm vào package của ứng dụng. Helper configuration được import tường minh từ root auto-configuration; consumer không import package internal. Khi bean xuất hiện dù feature bị tắt hoặc exclusion không có tác dụng, hãy kiểm tra component scan và direct @Import trước khi thay đổi condition.
