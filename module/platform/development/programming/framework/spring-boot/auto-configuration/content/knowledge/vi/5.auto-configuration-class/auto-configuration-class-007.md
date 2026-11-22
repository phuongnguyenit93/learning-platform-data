# Nhập thành phần phụ trợ bằng @Import thay cho quét thành phần rộng

## 1. Bài toán và mục tiêu

Khi viết một thư viện có **auto-configuration** cho Spring Boot, ta thường cần một hoặc vài cấu hình phụ trợ để cung cấp các bean mặc định, adapter hoặc converter. Cách tổ chức tốt là để lớp auto-configuration **nhập chính xác cấu hình phụ trợ cần thiết** qua **@Import**, thay vì mở rộng **@ComponentScan** ra toàn bộ package của thư viện.

Phân biệt:

- **@Import(SupportConfiguration.class)** chỉ định lớp cấu hình mà Spring cần xử lý. Lớp đó có thể khai báo nhiều phương thức **@Bean**, condition và các import khác.
- **@ComponentScan(basePackages = "...")** tìm nhiều component trong package phù hợp. Khi thư viện thêm một class được đánh dấu **@Component** hoặc **@Configuration**, tập bean được scan có thể thay đổi.
- **@EnableAutoConfiguration** của Spring Boot không tương đương với quét tất cả package. Trong Spring Boot 3.x, nó dùng metadata **AutoConfiguration.imports** để chọn auto-configuration candidates, rồi áp dụng điều kiện và loại trừ.

**Ý tưởng trung tâm:** auto-configuration chỉ nên đóng góp những thành phần cần cho feature đã được kích hoạt. Không nên làm một package scan rộng để “tìm mọi thứ có annotation”, bởi cách đó có thể đưa thành phần ngoài ý muốn vào ApplicationContext.

### 1.1. Vì sao điều này đáng học?

Giả sử thư viện audit có ba loại:

- **AuditAutoConfiguration**: quyết định khi nào audit được bật.
- **AuditSupportConfiguration**: tạo một bean AuditSink mặc định.
- **UnrelatedComponent**: một component khác dùng cho công cụ nội bộ, không thuộc audit runtime.

Nếu cấu hình audit dùng **@ComponentScan("dev.lesson.support")**, component thứ ba có thể bị nạp cùng với support configuration. Nếu dùng **@Import(AuditSupportConfiguration.class)**, Spring chỉ xử lý đường cấu hình được chỉ rõ và những nội dung do chính cấu hình đó khai báo. Một **@Component** khác đứng cùng package không tự được đăng ký chỉ vì class tồn tại.

Điều này giúp kiểm soát startup, dependency, xung đột bean và contract của thư viện tốt hơn.

## 2. Ba cách đưa cấu hình vào container

### 2.1. Component scan theo package

**@SpringBootApplication** bao gồm khả năng quét component. Khi lớp chính ở package **dev.lesson.app**, mặc định component scan nhắm package này và các package con.

~~~java
package dev.lesson.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

Đây là ví dụ cơ bản; nó cần các dependency Spring Boot để chạy. Class thuộc **dev.lesson.support** hoặc **dev.lesson.autoconfig** không nằm trong cây package **dev.lesson.app**, nên không tự được component scan mặc định tìm thấy.

Nếu thay bằng:

~~~java
@SpringBootApplication(scanBasePackages = "dev.lesson")
public class Application {
    // Các phương thức khác của ứng dụng.
}
~~~

phạm vi scan rộng hơn và có thể bao trùm support/autoconfig. Đoạn trên chỉ minh họa annotation, không phải file chạy độc lập. Khi scan rộng, các component mới được thêm vào package thư viện có thể xuất hiện trong container mà ứng dụng không cố ý yêu cầu.

### 2.2. @Import trực tiếp một cấu hình phụ trợ

~~~java
@AutoConfiguration
@Import(AuditSupportConfiguration.class)
class AuditAutoConfiguration {
}
~~~

**Đoạn code trên là minh họa rút gọn**, chưa có import statements và class definitions. Khi AuditAutoConfiguration được chọn, Spring sẽ xử lý AuditSupportConfiguration theo đường **@Import**. Nó không tự thực hiện component scan trên package chứa AuditSupportConfiguration.

**@Import** có thể nhận class cấu hình, component class, ImportSelector hoặc ImportBeanDefinitionRegistrar. Vì thế một class được import vẫn có thể khai báo thêm các import tiếp theo. Nói cách khác: lợi ích là **chọn đường cấu hình tường minh**, không phải bảo đảm chỉ một BeanDefinition được tạo.

### 2.3. Boot chọn auto-configuration bằng metadata

Đối với Spring Boot 3.x, thư viện công bố ứng viên trong resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Ví dụ:

~~~text
dev.lesson.autoconfig.AuditAutoConfiguration
~~~

Khi ứng dụng có **@SpringBootApplication**, **@EnableAutoConfiguration** đã được bật. **AutoConfigurationImportSelector** đọc danh sách ứng viên, xử lý exclusions và các điều kiện phù hợp; class auto-configuration được chọn mới có cơ hội đưa cấu hình phụ trợ vào xử lý qua **@Import**.

Có hai tầng:

~~~text
@SpringBootApplication
          |
          v
@EnableAutoConfiguration
          |
          v
AutoConfiguration.imports
          |
          v
AuditAutoConfiguration  (candidate)
          |
       Điều kiện đạt?
          |
          v
@Import(AuditSupportConfiguration.class)
          |
          v
@Bean bên trong AuditSupportConfiguration
          |
       Điều kiện bean đạt?
          |
          v
Đăng ký BeanDefinition và tạo instance theo lifecycle

UnrelatedComponent trong cùng JAR:
    không tự xuất hiện nếu không có scan/import/registration phù hợp.
~~~

Đừng nhầm file **AutoConfiguration.imports** với annotation **@Import**: chúng có tên gần nhau nhưng giữ vai trò khác nhau. Resource công bố danh sách auto-configuration của Boot; annotation @Import nằm trong class cấu hình để chỉ định thêm lớp hoặc chiến lược import.

## 3. So sánh @Import và @ComponentScan rộng

| Đặc điểm | @Import class hỗ trợ cụ thể | @ComponentScan package rộng |
| --- | --- | --- |
| Đích phát hiện | Class được chỉ định trong annotation | Các candidate trong package và package con |
| Kiểm soát phạm vi | Thường rõ ràng, tập trung vào feature | Phụ thuộc nội dung package tại runtime |
| Khi thêm @Component mới vào package | Không tự thay đổi đường import đang có | Component mới có thể được đăng ký |
| Cần class nằm trong package scan? | Không | Có, hoặc phải mở rộng package scan |
| @Conditional còn tác dụng? | Có | Có |
| Thích hợp với cấu hình phụ trợ của auto-config? | Thường có | Nên tránh scan rộng các package thư viện |
| Rủi ro | Import transitive hoặc support tự scan vẫn có thể kéo rộng | Nạp nhiều component, tạo bean ngoài ý muốn |
| Cơ chế Boot chọn candidate | Riêng, từ AutoConfiguration.imports | Không phải chức năng cốt lõi của component scan |

Không kết luận rằng **@Import luôn an toàn**: nếu support class chứa @ComponentScan rộng hoặc một ImportSelector trả về quá nhiều class, phạm vi thực tế vẫn rộng. Thiết kế tốt là giữ cho những cấu hình được import **hữu hạn và có mục đích rõ ràng**.

### 3.1. Auto-configuration không nên được component-scan như cấu hình ứng dụng

Với Spring Boot 3.x, auto-configuration nên nằm trong package riêng và được đăng ký qua **AutoConfiguration.imports**. Spring Boot khuyến nghị auto-configuration không trở thành mục tiêu của component scanning thông thường. Các lớp **@Configuration** phụ trợ có thể được import bằng **@Import** cụ thể.

Nếu cố scan package chứa auto-config, một class có thể được xử lý ngoài đường AutoConfigurationImportSelector, khiến thứ tự, điều kiện và loại trừ không còn dễ suy luận như contract chuẩn. Tốt hơn là giữ module library ở package riêng và chỉ công bố những auto-config candidates mong muốn.

## 4. Thiết kế điều kiện và cơ chế back off

Trong auto-configuration, điều kiện nên đặt đúng tầng:

- **@ConditionalOnClass** trên class auto-configuration: yêu cầu API tùy chọn có mặt trên classpath.
- **@ConditionalOnProperty** trên class auto-configuration: bật/tắt cả nhánh theo một feature flag.
- **@ConditionalOnMissingBean** trên @Bean mặc định: nhường chỗ nếu ứng dụng đã khai báo bean phù hợp.
- Các condition ở support class hoặc từng method: giới hạn riêng những bean phụ trợ.

Sơ đồ quyết định:

~~~text
AuditAutoConfiguration là candidate
             |
             v
Class và property condition đạt?
         /              \
      Không              Có
        |                 |
     Bỏ nhánh        @Import support
                          |
                          v
                @Bean defaultAuditSink
                          |
                          v
                Đã có AuditSink user?
                    /           \
                  Có            Không
                   |              |
              Back off       Đăng ký default
                                   |
                                   v
                           Tạo instance khi cần
~~~

**Điều kiện không phải phép quét package.** Khi một @Conditional trên lớp auto-configuration không đạt, đường import bên trong lớp đó không được kích hoạt. Nếu một cấu hình ứng dụng khác import trực tiếp support class, đường khác ấy cần được xem độc lập; property trên auto-configuration không tự động áp dụng cho tất cả cách nhập cùng class.

**@ConditionalOnMissingBean** cũng không xuất hiện tự động trên mọi phương thức @Bean. Thư viện phải chủ động đặt annotation khi muốn hỗ trợ user override theo kiểu back off.

## 5. Ví dụ hoàn chỉnh với Spring Boot 3.3.13 và Java 21

Mục tiêu của project là chứng minh đồng thời:

1. Support configuration được import mà không cần quét package support.
2. Một @Component ở package support khác **không tự đăng ký**.
3. Property false tắt đường auto-configuration.
4. Exclude class auto-configuration khác với property condition.
5. Bean do người dùng khai báo được ưu tiên khi default có @ConditionalOnMissingBean.

**Yêu cầu:** JDK 21, Maven 3.9+, kết nối để tải dependency. Không cần web server hay database.

### 5.1. Cây thư mục

~~~text
selective-import-demo/
├── pom.xml
└── src/main/
    ├── java/dev/lesson/
    │   ├── api/AuditSink.java
    │   ├── support/AuditSupportConfiguration.java
    │   ├── support/extra/UnrelatedComponent.java
    │   ├── autoconfig/AuditAutoConfiguration.java
    │   └── app/DemoApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

**Lớp ứng dụng nằm ở dev.lesson.app**; support và autoconfig là những package anh em của app. Vì vậy @ComponentScan mặc định của @SpringBootApplication không vô tình lấy những class ngoài app. Đây là điều kiện thiết kế quan trọng để ví dụ thực sự phân biệt được hai con đường.

### 5.2. pom.xml

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
    <groupId>dev.lesson</groupId>
    <artifactId>selective-import-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>21</java.version>
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

### 5.3. Interface AuditSink

**src/main/java/dev/lesson/api/AuditSink.java**

~~~java
package dev.lesson.api;

@FunctionalInterface
public interface AuditSink {
    String record(String event);
}
~~~

Chương trình chỉ quan tâm interface. Auto-configuration có thể cung cấp implementation mặc định, còn ứng dụng có quyền tự khai báo implementation riêng.

### 5.4. Support configuration được nhập chính xác

**src/main/java/dev/lesson/support/AuditSupportConfiguration.java**

~~~java
package dev.lesson.support;

import dev.lesson.api.AuditSink;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class AuditSupportConfiguration {

    @Bean
    @ConditionalOnMissingBean(AuditSink.class)
    AuditSink defaultAuditSink() {
        return event -> "auto:" + event;
    }
}
~~~

Cấu hình này tạo một AuditSink mặc định **nếu** chưa có bean cùng interface phù hợp. Không cần @ComponentScan để Spring xử lý phương thức @Bean, vì một đường @Import sẽ đưa class cấu hình vào container.

**proxyBeanMethods=false** phù hợp do method @Bean không trực tiếp gọi những method @Bean khác. Nếu các bean phụ thuộc nhau, nên khai báo dependency qua tham số phương thức @Bean thay vì tự gọi method và dựa vào proxy interception.

### 5.5. Một component hiện diện trên classpath nhưng không thuộc feature

**src/main/java/dev/lesson/support/extra/UnrelatedComponent.java**

~~~java
package dev.lesson.support.extra;

import org.springframework.stereotype.Component;

@Component
public class UnrelatedComponent {
}
~~~

Trong project này, component đó không được **@Import** và không thuộc component scan của package **dev.lesson.app**. Nó vẫn được biên dịch và đóng gói vào JAR, nhưng **không tự biến thành bean**.

Đừng nhầm “class nằm trên classpath” với “bean đã có trong ApplicationContext”.

### 5.6. Auto-configuration bật bằng điều kiện và import support

**src/main/java/dev/lesson/autoconfig/AuditAutoConfiguration.java**

~~~java
package dev.lesson.autoconfig;

import dev.lesson.api.AuditSink;
import dev.lesson.support.AuditSupportConfiguration;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Import;

@AutoConfiguration
@ConditionalOnClass(AuditSink.class)
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
@Import(AuditSupportConfiguration.class)
public class AuditAutoConfiguration {
}
~~~

Phân tích:

- **@AutoConfiguration** đánh dấu lớp ứng viên thuộc cơ chế tự cấu hình của Boot.
- **@ConditionalOnClass** xác minh kiểu AuditSink hiện diện. Demo luôn có class này; thư viện thực có thể yêu cầu một API tùy chọn.
- **@ConditionalOnProperty** cho phép feature khi property vắng mặt hoặc bằng true; khi false, class auto-configuration không được áp dụng.
- **@Import(AuditSupportConfiguration.class)** mang support configuration đã chọn vào quá trình xử lý. Không có @ComponentScan trên package support.
- **@ConditionalOnMissingBean** nằm trong support configuration và quyết định riêng việc có đăng ký defaultAuditSink hay không.

### 5.7. AutoConfiguration.imports

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.lesson.autoconfig.AuditAutoConfiguration
~~~

Lưu ý: file này liệt kê **AuditAutoConfiguration**, không liệt kê **AuditSupportConfiguration** hay **UnrelatedComponent**. Support class được điều phối bằng @Import, còn UnrelatedComponent cố ý không được nạp.

Đây là cơ chế công bố auto-configuration candidates của Spring Boot 3.x. Tài liệu cũ có thể mô tả key EnableAutoConfiguration trong spring.factories; đó không phải format đăng ký auto-config candidates mới dùng trong project Boot 3.x này.

### 5.8. Ứng dụng chính và bean người dùng tùy chọn

**src/main/java/dev/lesson/app/DemoApplication.java**

~~~java
package dev.lesson.app;

import dev.lesson.api.AuditSink;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @Profile("custom")
    AuditSink customAuditSink() {
        return event -> "user:" + event;
    }

    @Bean
    ApplicationRunner showState(
            ObjectProvider<AuditSink> auditProvider,
            ApplicationContext context) {
        return args -> {
            AuditSink sink = auditProvider.getIfAvailable();
            System.out.println("audit=" +
                (sink == null ? "<none>" : sink.record("Hi")));
            System.out.println("unrelated=" +
                context.containsBean("unrelatedComponent"));
        };
    }
}
~~~

**ObjectProvider** cho phép kiểm tra khi không có AuditSink mà không làm startup thất bại vì injection bắt buộc. Trong profile **custom**, ứng dụng khai báo bean AuditSink của riêng mình, làm bean mặc định có @ConditionalOnMissingBean rút lui.

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
~~~

Các thiết lập này chỉ giúp gọn output. Trong môi trường có logging hoặc agent khác, có thể có thêm dòng log; dưới đây ghi các dòng do chính demo in.

### 5.9. Build và chạy

Tại thư mục **selective-import-demo**:

~~~bash
mvn -q -DskipTests package
~~~

**Kịch bản A: dùng auto-configuration mặc định**

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar
~~~

Dòng stdout từ ApplicationRunner:

~~~text
audit=auto:Hi
unrelated=false
~~~

Spring Boot chọn AuditAutoConfiguration từ imports, condition đạt và @Import xử lý support. UnrelatedComponent không có bean vì không được scan hay import.

**Kịch bản B: tắt feature bằng property**

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar --demo.audit.enabled=false
~~~

Output:

~~~text
audit=<none>
unrelated=false
~~~

Property làm condition trên class AuditAutoConfiguration không đạt. Đường @Import của nhánh auto-config đó không xử lý support.

**Kịch bản C: exclude auto-configuration**

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=dev.lesson.autoconfig.AuditAutoConfiguration
~~~

Output:

~~~text
audit=<none>
unrelated=false
~~~

Ở đây Boot loại auto-configuration khỏi ứng viên áp dụng; không phải chỉ method @Bean không match property. Kết quả quan sát giống B nhưng lý do khác.

**Kịch bản D: người dùng cung cấp implementation riêng**

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom
~~~

Output:

~~~text
audit=user:Hi
unrelated=false
~~~

Bean customAuditSink đã được ứng dụng đăng ký, khiến **@ConditionalOnMissingBean(AuditSink.class)** của defaultAuditSink không đạt. Support class vẫn có thể được import nhưng bean mặc định không được đăng ký.

**Kịch bản E: property false nhưng bean người dùng vẫn còn**

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom --demo.audit.enabled=false
~~~

Output:

~~~text
audit=user:Hi
unrelated=false
~~~

Property chỉ chặn auto-configuration của thư viện; không vô hiệu hóa bean do ứng dụng khai báo độc lập.

| Kịch bản | Auto-config được áp dụng? | Có bean AuditSink mặc định? | Có bean AuditSink custom? | UnrelatedComponent là bean? |
| --- | --- | --- | --- | --- |
| A | Có | Có | Không | Không |
| B | Không, do condition | Không | Không | Không |
| C | Không, do exclude | Không | Không | Không |
| D | Có | Không, do back off | Có | Không |
| E | Không, do condition | Không | Có | Không |

### 5.10. Thí nghiệm mở component scan có kiểm soát

Để chứng minh UnrelatedComponent có thể xuất hiện do scan, có thể thay annotation trên lớp chính bằng đoạn sau **nhưng giữ nguyên các method/main khác**:

~~~java
@SpringBootApplication(
    scanBasePackages = {
        "dev.lesson.app",
        "dev.lesson.support.extra"
    }
)
public class DemoApplication {
    // Các thành phần khác như bản chạy đầy đủ.
}
~~~

Đây chỉ là snippet annotation minh họa, không phải file độc lập. Sau khi mở scan tới **dev.lesson.support.extra**, bean name mặc định của UnrelatedComponent là **unrelatedComponent**, nên dòng thứ hai từ runner trở thành:

~~~text
unrelated=true
~~~

Không thay scanBasePackages bằng **"dev.lesson"** chỉ để tìm một support class: package đó còn chứa **dev.lesson.autoconfig** và các phần thư viện khác. Quét rộng như vậy có thể khiến những cấu hình không được intended selector chọn cũng bị Spring tìm thấy qua component scan.

## 6. Khi nào dùng @Import, ImportSelector hoặc Registrar?

### 6.1. @Import một hoặc vài configuration class cố định

Nếu feature luôn cần hai nhóm support rõ ràng:

~~~java
@Import({
    AuditSupportConfiguration.class,
    ConversionSupportConfiguration.class
})
class FeatureAutoConfiguration {
}
~~~

Đây là minh họa, ConversionSupportConfiguration chưa được định nghĩa trong project mẫu. Mọi class được import vẫn chịu các condition của chính nó; không biến import thành phép tạo object ngay tức khắc.

Dùng cách này nếu danh sách cấu hình **ổn định, hữu hạn và đã biết tại compile time**.

### 6.2. ImportSelector cho lựa chọn động

Nếu danh sách class cần import phụ thuộc vào metadata của annotation, có thể dùng **ImportSelector**:

~~~java
public class FeatureSelector
        implements org.springframework.context.annotation.ImportSelector {

    @Override
    public String[] selectImports(
            org.springframework.core.type.AnnotationMetadata metadata) {
        return new String[] {
            "dev.lesson.support.AuditSupportConfiguration"
        };
    }
}
~~~

Đây là ví dụ API đơn lẻ, không phải project tự chạy. Có thể viết **@Import(FeatureSelector.class)** để selector trả danh sách cấu hình cần xử lý.

Trong auto-configuration thông thường, **không cần tự xây selector chỉ để thay thế cơ chế của Boot**; nên dùng @AutoConfiguration, AutoConfiguration.imports, condition và @Import support class cụ thể.

### 6.3. ImportBeanDefinitionRegistrar cho registration phức tạp

Khi phải đăng ký BeanDefinition theo tên/kiểu được tính bằng logic chương trình, **ImportBeanDefinitionRegistrar** là extension point nâng cao. Nó có thể tạo definition từ AnnotationMetadata và registry. Không nên dùng registrar nếu một @Bean trong support configuration đã thể hiện đúng ý định: cách đơn giản dễ đọc, dễ bảo trì và dễ chẩn đoán hơn.

## 7. Các rủi ro vẫn tồn tại dù dùng @Import

Đừng chỉ thay tên annotation mà bỏ qua thiết kế:

1. **SupportConfiguration tự dùng @ComponentScan rộng**: @Import support vẫn có thể kích hoạt scan phụ, kéo vào nhiều component.
2. **SupportConfiguration import tiếp nhiều module**: cần đọc các đường import transitive.
3. **SupportConfiguration bị import ở nhiều nơi**: mặc dù Spring có cơ chế xử lý configuration, các đường đăng ký/condition có thể trở nên khó suy luận; nên xác định một nơi điều phối rõ ràng.
4. **Không có @ConditionalOnMissingBean trên default**: khi ứng dụng thêm bean cùng interface, có thể xuất hiện nhiều bean và injection mơ hồ.
5. **Điều kiện nằm sai tầng**: @ConditionalOnProperty ở auto-config không tự chặn support nếu support cũng được import trực tiếp qua một nhánh khác.
6. **Bean hỗ trợ có side effect**: constructor/factory method mở kết nối hoặc chạy background job nên có điều kiện thích hợp để không khởi tạo không cần thiết.

Điểm quyết định là **lập ranh giới feature**. @Import làm ranh giới dễ nhìn hơn, nhưng vẫn cần condition, quy ước package, bean naming và lifecycle phù hợp.

## 8. Debug khi một bean ngoài ý muốn xuất hiện

Hãy kiểm tra theo thứ tự:

1. **Tên bean và class nguồn**: bean được tạo từ @Bean nào, một component scan hay registrar?
2. **Package scan**: @SpringBootApplication nằm ở package nào? Có scanBasePackages hoặc @ComponentScan nào mở rộng không?
3. **Imports đường Boot**: auto-config class có trong **AutoConfiguration.imports** không? Có bị exclude hoặc condition class/property không đạt không?
4. **@Import phụ trợ**: auto-config import lớp nào? Lớp support có @ComponentScan, @Import hoặc @Bean nào khác không?
5. **Bean người dùng và back off**: @ConditionalOnMissingBean đã đúng type/name chưa?
6. **Lỗi khởi tạo**: nếu definition có nhưng bean tạo thất bại, xem BeanCreationException và dependency chain.

Với project demo, có thể bật chẩn đoán condition bằng:

~~~bash
java -jar target/selective-import-demo-0.0.1-SNAPSHOT.jar --debug --logging.level.root=INFO
~~~

**Condition Evaluation Report** giúp tìm lý do Boot chọn/bỏ qua AuditAutoConfiguration. Report không phải công cụ khẳng định mọi bean instance đã được tạo; đối với bean được import trực tiếp, vẫn cần xem bean metadata và đường configuration tương ứng.

Nếu thêm Actuator và cấu hình exposure/bảo mật phù hợp, **/actuator/conditions** cung cấp condition report và **/actuator/beans** cung cấp thông tin các bean. Không phơi bày endpoint quản trị ngoài môi trường tin cậy khi chưa bảo vệ truy cập.

## 9. Sai lầm phổ biến

| Sai lầm | Điều đúng |
| --- | --- |
| “Có @Configuration trên classpath là Boot tự nhập.” | Phải có đường import, component scan hoặc registration phù hợp. |
| “@Import luôn quét package của class được import.” | @Import chỉ định class/selector/registrar, không tự scan toàn package. |
| “Có @Component thì luôn có bean.” | Chỉ khi class được phát hiện hoặc đăng ký trong container. |
| “Auto-configuration cần @ComponentScan để tìm support.” | Thường nên import support configuration cụ thể. |
| “@Import bỏ qua @Conditional.” | Condition vẫn được đánh giá ở lớp/phương thức liên quan. |
| “Property tắt auto-config xóa bean của ứng dụng.” | Không; user-defined bean có vòng đời/đường đăng ký riêng. |
| “@ConditionalOnMissingBean có sẵn cho mọi @Bean.” | Phải khai báo ở nhánh muốn back off. |
| “@ComponentScan và AutoConfiguration.imports là cùng cơ chế.” | Một cơ chế theo package, một cơ chế công bố auto-config candidates. |
| “Import support đồng nghĩa bean instance đã tạo.” | Đăng ký definition và khởi tạo instance là hai giai đoạn. |
| “Mở scan toàn thư viện luôn nhanh hơn.” | Có thể tạo bean ngoài ý muốn và khiến cấu hình phụ thuộc package. |

## 10. Tự kiểm tra

**Câu 1.** AuditSupportConfiguration và UnrelatedComponent cùng nằm dưới package support. Nếu chỉ @Import(AuditSupportConfiguration.class), UnrelatedComponent có tự đăng ký không?

**Đáp án:** Không, nếu class đó không được scan/import/đăng ký theo đường khác. Cùng package không đủ.

**Câu 2.** Lớp support không nằm trong component scan, tại sao các @Bean bên trong vẫn hoạt động?

**Đáp án:** @Import đưa class cấu hình vào quá trình xử lý configuration. Spring có thể đăng ký các @Bean đủ điều kiện của class đó.

**Câu 3.** @Import có thể chứa một ImportSelector không?

**Đáp án:** Có. Spring Framework hỗ trợ class cấu hình, component, ImportSelector và ImportBeanDefinitionRegistrar. Với tập class support cố định, import trực tiếp thường dễ hiểu hơn.

**Câu 4.** Kịch bản property false nhưng profile custom đang bật sẽ in gì?

**Đáp án:** audit=user:Hi và unrelated=false. Property của auto-configuration không loại bỏ bean ứng dụng.

**Câu 5.** Exclude AuditAutoConfiguration nhưng ứng dụng tự @Import(AuditSupportConfiguration.class) thì sao?

**Đáp án:** Support class vẫn có thể được xử lý theo đường import tường minh của ứng dụng. Exclude Boot không mặc nhiên loại tất cả đường import độc lập.

**Câu 6.** Tại sao không nên @ComponentScan cả package autoconfig của một thư viện?

**Đáp án:** Có thể khiến những lớp auto-configuration được xử lý ngoài cơ chế lựa chọn candidates, ordering và exclusion chuẩn của Boot.

**Câu 7.** Nếu bean AuditSink user tồn tại nhưng lazy, defaultAuditSink có thể back off không?

**Đáp án:** Có. @ConditionalOnMissingBean xét thông tin bean đã được đăng ký, không đòi user instance phải được khởi tạo xong.

**Câu 8.** Có nên đặt @ComponentScan vào support class để “dễ thêm bean về sau”?

**Đáp án:** Chỉ khi thực sự cần một cơ chế phát hiện nhiều component và đã thiết kế điều kiện/filter rõ ràng. Nếu feature chỉ cần vài bean hỗ trợ, khai báo @Bean cụ thể hoặc import configuration cụ thể dễ kiểm soát hơn.

## 11. Ghi nhớ

Trong ứng dụng thông thường, **@ComponentScan** rất hữu ích để tìm các component của chính ứng dụng. Nhưng trong một thư viện Spring Boot, đặc biệt ở lớp **@AutoConfiguration**, hãy ưu tiên **@Import cấu hình phụ trợ được chọn có chủ đích**, thay vì quét rộng package thư viện. Khi cần nhiều bean, gom chúng vào SupportConfiguration với @Bean và condition rõ ràng.

Luồng tư duy đúng:

~~~text
Candidate auto-config từ AutoConfiguration.imports
             |
             v
Condition và exclude quyết định nhánh
             |
             v
@Import chỉ định support configuration
             |
             v
Các @Bean được xét condition và đăng ký definition
             |
             v
Instance được tạo theo scope/dependency/lifecycle
~~~

Một class khác cùng package, dù có @Component, vẫn **không tự trở thành bean** nếu không có đường scan/import/registration. Đây là lợi ích cụ thể của nhập thành phần phụ trợ chọn lọc: container phản ánh tính năng được bật, chứ không phản ánh mọi class vô tình nằm trong một package.

### Tài liệu tham khảo

- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Framework, *Using the @Import Annotation*: https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html
- Spring Framework, *Classpath Scanning and Managed Components*: https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html
- Spring Framework, API **@Import**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Import.html
