# Phân biệt nhập một lớp bằng @Import với bật cơ chế @EnableAutoConfiguration

## 1. Hai công cụ giải quyết hai câu hỏi khác nhau

Trong Spring Framework, **@Import** cho phép một lớp cấu hình đưa **những cấu hình, component hoặc cơ chế import được chỉ rõ** vào quá trình xử lý của container. Trong Spring Boot, **@EnableAutoConfiguration** bật **cơ chế phát hiện và lựa chọn một tập lớp auto-configuration ứng viên theo classpath, metadata, các quy tắc loại trừ và điều kiện thực tế**.

Vì vậy, câu hỏi phù hợp khi nhìn thấy hai annotation là:

- **@Import(FooConfiguration.class)**: “Hãy đưa cấu hình FooConfiguration được chỉ đích danh vào tập cấu hình xử lý.”
- **@EnableAutoConfiguration**: “Hãy tìm các auto-configuration mà các thư viện công bố, loại bỏ những cấu hình bị exclude hoặc không phù hợp, rồi xử lý những nhánh đủ điều kiện.”

Một khác biệt quan trọng: **@EnableAutoConfiguration tự nó cũng sử dụng @Import**, nhưng nó import một **AutoConfigurationImportSelector**, chứ không viết sẵn danh sách mọi auto-configuration trong annotation. Vì thế không có mâu thuẫn khi nói @Import là một cơ chế nền của Spring và @EnableAutoConfiguration là tính năng cao hơn của Spring Boot.

**Không hiểu @Import là “chắc chắn tạo một object”**: import cấu hình khiến Spring xử lý các bean definition có liên quan; điều kiện, scope, lazy initialization và lỗi khởi tạo vẫn quyết định bean nào được đăng ký và khi nào instance được tạo.

## 2. Bảng so sánh trực diện

| Khía cạnh | @Import(FooConfiguration.class) | @EnableAutoConfiguration |
| --- | --- | --- |
| Đơn vị điều khiển | Lớp hoặc bộ chọn/registrar được chỉ rõ tại vị trí import | Hệ thống lựa chọn nhiều lớp auto-configuration ứng viên |
| Người quyết định tên cấu hình | Người viết mã annotation hoặc một ImportSelector được chỉ rõ | Các thư viện công bố ứng viên và bộ chọn của Spring Boot lọc chúng |
| Nguồn tìm kiếm | Class literal trong annotation; với selector, do selector quyết định | Các file **AutoConfiguration.imports** trên runtime classpath của Spring Boot 3.x |
| Có tự tìm mọi auto-configuration trên classpath không? | Không, nếu chỉ import trực tiếp một class | Có cơ chế đọc danh sách ứng viên và lọc |
| Có xét @Conditional không? | Có, nếu lớp hay các @Bean được import có gắn điều kiện | Có, trên lớp auto-configuration và các bean method liên quan |
| Có hỗ trợ “back off” không? | Có thể có, nếu cấu hình được import khai báo **@ConditionalOnMissingBean** | Thường dùng **@ConditionalOnMissingBean** để nhường bean mặc định cho ứng dụng |
| Thứ tự xử lý | Theo cơ chế xử lý configuration/import của Spring; phụ thuộc loại đối tượng import | Dùng **DeferredImportSelector** và các quy tắc before/after của auto-configuration |
| Cơ chế exclude của Spring Boot | Không có ý nghĩa “gỡ bỏ mọi @Import trực tiếp” | Hỗ trợ exclude/excludeName và **spring.autoconfigure.exclude** cho auto-configuration |
| Quan hệ với component scan | Không cần component scan mới import được class được chỉ rõ | Không cần component scan tìm từng lớp auto-configuration ứng viên |
| Dùng khi nào? | Ứng dụng muốn lắp ghép rõ ràng một module hoặc bật một cấu hình đã biết | Ứng dụng muốn Boot tự cấu hình các thành phần hợp với dependency và môi trường |

Dòng trong bảng về “@Import” mô tả **@Import chỉ đích danh một lớp**. Bản thân **@Import** còn nhận **ImportSelector**, **DeferredImportSelector** và **ImportBeanDefinitionRegistrar**, vì vậy có thể triển khai những chiến lược lựa chọn phức tạp hơn. Chính chi tiết này giải thích vì sao @EnableAutoConfiguration có thể xây dựng trên @Import.

## 3. @Import thực sự làm gì?

### 3.1. Nhập một lớp cấu hình đã biết

Một trường hợp thường gặp:

~~~java
package dev.lesson.manual;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class MailClientConfiguration {

    @Bean
    MailClient mailClient() {
        return new MailClient();
    }
}
~~~

~~~java
package dev.lesson.app;

import dev.lesson.manual.MailClientConfiguration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Configuration;

@Configuration
@Import(MailClientConfiguration.class)
public class AppConfiguration {
}
~~~

Đây là **hai mảnh mã giải thích**, chưa phải project chạy độc lập: class **MailClient** chưa được định nghĩa. Mục tiêu là thấy rằng Spring biết rõ lớp cấu hình cần xử lý: **MailClientConfiguration**. Nó không phải đọc danh sách auto-configuration của mọi starter để tìm lớp đó.

Khi Spring xử lý AppConfiguration, nó sẽ xem cấu hình được import, từ đó có thể đăng ký bean definition của **mailClient()**. Nếu class hoặc method được import có **@Conditional**, những điều kiện đó vẫn áp dụng. Nếu là bean lazy, có thể chưa tạo instance tại thời điểm definition xuất hiện.

Không cần đặt MailClientConfiguration trong package được **@ComponentScan** quét: đường đi qua import đã chỉ rõ class. Điều này hữu ích khi lắp một thư viện nội bộ hoặc một nhóm bean cần được bật một cách tường minh.

### 3.2. @Import không chỉ nhận @Configuration

Theo cơ chế của Spring Framework, **@Import** có thể chỉ đến:

1. **Lớp cấu hình hoặc component** được Spring xử lý để đăng ký bean tương ứng.
2. **ImportSelector**: tự tính ra danh sách các class cấu hình cần import.
3. **DeferredImportSelector**: biến thể selector có lịch xử lý trì hoãn trong quá trình phân tích cấu hình.
4. **ImportBeanDefinitionRegistrar**: trực tiếp đăng ký thêm các bean definition bằng API registry.

Một ví dụ selector minh họa, không phải chương trình độc lập:

~~~java
class FeatureSelector implements org.springframework.context.annotation.ImportSelector {
    @Override
    public String[] selectImports(
            org.springframework.core.type.AnnotationMetadata metadata) {
        return new String[] {"dev.lesson.manual.MailClientConfiguration"};
    }
}
~~~

~~~java
@Import(FeatureSelector.class)
class SelectedFeatureConfiguration {
}
~~~

Với trường hợp này, code tại điểm import không liệt kê MailClientConfiguration; selector quyết định danh sách. Do đó khẳng định “@Import **luôn** nạp đúng một lớp được viết trong ngoặc” là sai. Điểm phân biệt thực tế với **@EnableAutoConfiguration** là chiến lược chọn **được Spring Boot cung cấp**, dựa trên danh sách auto-configuration của các JAR và những điều kiện được Boot chuẩn hóa.

### 3.3. Import không có nghĩa vượt qua condition

Giả sử cấu hình trực tiếp được import có điều kiện:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "lesson.manual",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
class ManualFeatureConfiguration {
    // Các phương thức @Bean của cấu hình này.
}
~~~

Đoạn này minh họa annotation, không phải file Java chạy độc lập. Nếu **lesson.manual.enabled=false**, class có thể bị loại bởi condition dù đã được @Import chỉ định. Điều khác biệt với auto-configuration nằm ở **đường tìm và chọn ứng viên**, không phải ở việc @Import bỏ qua mọi điều kiện.

## 4. @EnableAutoConfiguration xây dựng trên @Import như thế nào?

Trong Spring Boot 3.x, annotation **@EnableAutoConfiguration** gắn hai cơ chế cốt lõi:

- **@AutoConfigurationPackage**: ghi nhận package mặc định phục vụ một số tính năng được auto-configure, chẳng hạn các cơ chế tìm entity/repository trong tình huống phù hợp.
- **@Import(AutoConfigurationImportSelector.class)**: đăng ký selector chuyên trách lựa chọn auto-configuration của Boot.

Mô hình cấu trúc được rút gọn:

~~~java
@AutoConfigurationPackage
@Import(AutoConfigurationImportSelector.class)
public @interface EnableAutoConfiguration {
    Class<?>[] exclude() default {};
    String[] excludeName() default {};
}
~~~

Đây **không phải** toàn bộ source code của annotation để copy vào dự án. Mục đích là thấy đường dẫn từ **@EnableAutoConfiguration** đến **@Import**.

Thông thường developer dùng:

~~~java
@SpringBootApplication
public class Application {
}
~~~

**@SpringBootApplication** gồm các ý nghĩa nền: **@SpringBootConfiguration**, **@EnableAutoConfiguration** và **@ComponentScan**. Do đó ứng dụng có @SpringBootApplication đã bật auto-configuration, không cần gắn @EnableAutoConfiguration thêm lần nữa.

### 4.1. AutoConfigurationImportSelector là gì?

**AutoConfigurationImportSelector** triển khai **DeferredImportSelector**. Nó phối hợp phát hiện và chọn lớp auto-configuration trước khi chúng được xử lý như các import phù hợp. “Deferred” nghĩa là việc xử lý những import này được trì hoãn trong quá trình phân tích các configuration class của Spring; đây là một phần giúp các cấu hình do ứng dụng chủ động khai báo được xét trước các cấu hình mặc định của Boot.

Nhưng **không** nên suy từ “deferred” rằng tất cả bean instance ứng dụng đã được tạo xong trước khi auto-config chạy. Quá trình đăng ký **bean definition** và quá trình **khởi tạo instance** là hai pha logic khác nhau. Condition dạng **@ConditionalOnMissingBean** dựa trên thông tin bean đã được xử lý trong container tại lúc đánh giá, không cần object của bean đó đã được tạo.

### 4.2. Boot phát hiện các ứng viên ở đâu?

Trong Spring Boot 3.x, các thư viện cung cấp danh sách ứng viên bằng resource đúng tên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Một resource có thể chứa:

~~~text
dev.lesson.autoconfig.AutoFeatureAutoConfiguration
dev.lesson.autoconfig.CacheFeatureAutoConfiguration
~~~

Mỗi dòng là tên lớp auto-configuration đủ điều kiện **để được xét**, không phải cam kết sẽ được khởi tạo. Các JAR có mặt trên runtime classpath cung cấp những resource tương ứng. Thêm/bỏ starter hoặc thay đổi dependency có thể thay đổi cả danh sách ứng viên lẫn khả năng đạt **@ConditionalOnClass**.

**Đừng nhầm với @ComponentScan**: một class auto-configuration thường nằm ngoài package scan của ứng dụng, nhưng Boot vẫn tìm được nhờ file imports. Ngược lại, gắn **@AutoConfiguration** lên một class nhưng không đăng ký đúng cơ chế imports thì Boot không tự động tìm ra class chỉ từ tên annotation đó.

Tài liệu đời cũ sử dụng key EnableAutoConfiguration trong **META-INF/spring.factories**. Với Spring Boot 3.x, định dạng công bố ứng viên là **AutoConfiguration.imports**. File spring.factories vẫn có những ứng dụng SPI khác; đừng dùng ký ức về định dạng cũ để sửa đường dẫn imports của một thư viện Boot 3.

### 4.3. Lọc ứng viên, loại trừ và kiểm tra điều kiện

Có thể hình dung quy trình:

~~~text
Ứng dụng khởi động với @EnableAutoConfiguration
                    |
                    v
@Import(AutoConfigurationImportSelector.class)
                    |
                    v
Tìm các file AutoConfiguration.imports trên runtime classpath
                    |
                    v
Tập ứng viên ban đầu, loại trùng và áp dụng exclude
                    |
                    v
Sàng lọc bằng metadata/điều kiện phù hợp
                    |
                    v
Import những cấu hình còn phù hợp vào quá trình xử lý
                    |
                    v
Đánh giá @Conditional ở class và các @Bean
                    |
       +------------+---------------+
       |                            |
  Không đạt                      Đạt điều kiện
       |                            |
  Bỏ nhánh tương ứng          Đăng ký bean definition
                                     |
                                     v
                       Container tạo instance theo lifecycle
~~~

Sơ đồ này **rút gọn**; Spring có nhiều pha parse/registration và một số condition được đánh giá ở các thời điểm khác nhau. Một class có thể là ứng viên, thậm chí được xử lý, nhưng một phương thức @Bean bên trong vẫn bị loại riêng.

Các điều kiện thường gặp:

| Annotation | Câu hỏi Spring Boot dùng để quyết định |
| --- | --- |
| **@ConditionalOnClass** | Có class/thư viện bắt buộc trên classpath không? |
| **@ConditionalOnMissingClass** | Có thiếu class mục tiêu không? |
| **@ConditionalOnProperty** | Thuộc tính cuối cùng trong Environment có giá trị phù hợp không? |
| **@ConditionalOnBean** | Trong phạm vi tìm kiếm phù hợp đã có bean theo kiểu/tên chưa? |
| **@ConditionalOnMissingBean** | Chưa có bean phù hợp để nhường chỗ cho mặc định? |
| **@ConditionalOnWebApplication** | Đây có phải loại ứng dụng web được nhánh yêu cầu không? |
| **@ConditionalOnResource** | Resource mà nhánh cần có tồn tại không? |

Thí dụ, một auto-config tạo bean mặc định khi class API có mặt, property bật và chưa có bean người dùng. Một trong các điều kiện không đạt thì **nhánh bean mặc định** bị bỏ qua. Thêm dependency chỉ làm một số condition có cơ hội đạt; không biến **@EnableAutoConfiguration** thành “bật tất cả mọi thứ”.

### 4.4. Bị exclude khác với không đạt condition

Spring Boot hỗ trợ loại **auto-configuration class** bằng:

- **@EnableAutoConfiguration(exclude = SomeAutoConfiguration.class)**.
- **@EnableAutoConfiguration(excludeName = "package.SomeAutoConfiguration")**.
- **@SpringBootApplication(exclude = ...)** hoặc **excludeName** tương ứng.
- Thuộc tính **spring.autoconfigure.exclude** chứa tên class auto-configuration muốn loại.

Loại trừ tác động lên **đường lựa chọn auto-configuration**. Nó **không có nghĩa** Spring tự động hoàn tác một class cấu hình được ứng dụng **@Import** trực tiếp qua đường khác. Nếu bạn tự viết **@Import(XConfiguration.class)**, hãy kiểm soát việc import đó bằng cấu hình hoặc điều kiện riêng; không mặc định kỳ vọng **spring.autoconfigure.exclude** gỡ được mọi import thủ công. Đặc biệt, **trực tiếp import một lớp auto-configuration nội bộ của Boot** không phải cách tùy biến được khuyến nghị: các lớp đó là chi tiết triển khai và có thể thay đổi qua phiên bản.

## 5. Ví dụ chạy được: cùng một ứng dụng có cả @Import và @EnableAutoConfiguration

Ta xây project nhỏ với **Java 21, Spring Boot 3.3.13, Maven 3.9+**. Bài tập cô lập ba đường xử lý:

1. **ManualFeatureConfiguration** được import bằng **@Import** chỉ đích danh.
2. **AutoFeatureAutoConfiguration** được phát hiện qua **AutoConfiguration.imports** khi bật **@EnableAutoConfiguration**.
3. Một bean người dùng tự khai báo, bật bằng Spring profile **custom**, khiến auto-config rút lui nhờ **@ConditionalOnMissingBean**.

Không dùng **@ComponentScan** trong ví dụ để loại bỏ khả năng một class được tìm thấy nhờ package scanning, giúp nhìn rõ hai đường import.

Cấu trúc thư mục:

~~~text
import-vs-auto/
├── pom.xml
└── src/main/
    ├── java/dev/lesson/
    │   ├── api/
    │   │   ├── ManualMarker.java
    │   │   └── AutoMarker.java
    │   ├── manual/
    │   │   └── ManualFeatureConfiguration.java
    │   ├── autoconfig/
    │   │   └── AutoFeatureAutoConfiguration.java
    │   └── app/
    │       └── LessonApplication.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

### 5.1. Khai báo dependency

**pom.xml**

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
    <artifactId>import-vs-auto</artifactId>
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

Starter cơ bản đủ cho Spring Boot, Spring Context và cơ chế auto-configuration. Không cần web server, database hoặc starter-web cho ví dụ này.

### 5.2. Hai kiểu bean để quan sát

**src/main/java/dev/lesson/api/ManualMarker.java**

~~~java
package dev.lesson.api;

public record ManualMarker(String source) {
}
~~~

**src/main/java/dev/lesson/api/AutoMarker.java**

~~~java
package dev.lesson.api;

public record AutoMarker(String source) {
}
~~~

Hai record là các kiểu đơn giản, giúp quan sát bean nào có mặt và bean đó do nguồn nào cung cấp.

### 5.3. Cấu hình được @Import trực tiếp

**src/main/java/dev/lesson/manual/ManualFeatureConfiguration.java**

~~~java
package dev.lesson.manual;

import dev.lesson.api.ManualMarker;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
    prefix = "lesson.manual",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class ManualFeatureConfiguration {

    @Bean
    ManualMarker manualMarker() {
        return new ManualMarker("imported");
    }
}
~~~

Class này được ứng dụng chỉ rõ qua **@Import(ManualFeatureConfiguration.class)**. Tại đây ta cố ý thêm **@ConditionalOnProperty** để chứng minh: ngay cả cấu hình được import trực tiếp vẫn có thể bị condition loại bỏ. Với property vắng mặt, **matchIfMissing=true** cho phép cấu hình hoạt động.

### 5.4. Auto-configuration là ứng viên của Boot

**src/main/java/dev/lesson/autoconfig/AutoFeatureAutoConfiguration.java**

~~~java
package dev.lesson.autoconfig;

import dev.lesson.api.AutoMarker;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(AutoMarker.class)
public class AutoFeatureAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AutoMarker.class)
    @ConditionalOnProperty(
        prefix = "lesson.auto",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    AutoMarker defaultAutoMarker() {
        return new AutoMarker("default");
    }
}
~~~

Trong project này **AutoMarker** luôn có trên classpath. Điều kiện class giúp giải thích cách Boot thường bảo vệ auto-configuration phụ thuộc vào API tùy chọn; khi viết starter thư viện độc lập, API có thể đến từ dependency bên ngoài và không luôn tồn tại.

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.lesson.autoconfig.AutoFeatureAutoConfiguration
~~~

Chính resource này đưa AutoFeatureAutoConfiguration vào tập ứng viên. Ứng dụng chính sẽ không @Import trực tiếp class này. Tên package **dev.lesson.autoconfig** cũng nằm ngoài package chứa lớp chính **dev.lesson.app**; ví dụ không bật component scan nên sẽ không có con đường nhận nhầm class từ component scanning.

### 5.5. Lớp chính khai báo hai cơ chế khác nhau

**src/main/java/dev/lesson/app/LessonApplication.java**

~~~java
package dev.lesson.app;

import dev.lesson.api.AutoMarker;
import dev.lesson.api.ManualMarker;
import dev.lesson.manual.ManualFeatureConfiguration;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Profile;

@SpringBootConfiguration(proxyBeanMethods = false)
@EnableAutoConfiguration
@Import(ManualFeatureConfiguration.class)
public class LessonApplication {

    public static void main(String[] args) {
        SpringApplication.run(LessonApplication.class, args);
    }

    @Bean
    @Profile("custom")
    AutoMarker userAutoMarker() {
        return new AutoMarker("user");
    }

    @Bean
    ApplicationRunner showSources(
            ObjectProvider<ManualMarker> manualProvider,
            ObjectProvider<AutoMarker> autoProvider) {

        return args -> {
            ManualMarker manual = manualProvider.getIfAvailable();
            AutoMarker automatic = autoProvider.getIfAvailable();

            System.out.println("manual=" +
                (manual == null ? "absent" : manual.source()));
            System.out.println("auto=" +
                (automatic == null ? "absent" : automatic.source()));
        };
    }
}
~~~

**Tại sao không dùng @SpringBootApplication trong bài chạy này?** Mục đích là hiển thị hai annotation cần so sánh ngay trên cùng lớp chính, và không kéo theo **@ComponentScan**. **@SpringBootConfiguration** đánh dấu lớp cấu hình ứng dụng; **@EnableAutoConfiguration** bật selector của Boot; **@Import(ManualFeatureConfiguration.class)** chỉ đích danh cấu hình thủ công.

Với ứng dụng sản phẩm thông thường, **@SpringBootApplication** là cách viết ngắn gọn và được khuyến nghị; cách khai báo tách riêng trong bài này phục vụ học cơ chế.

Bean **userAutoMarker()** chỉ có khi bật Spring profile **custom**; nó giúp kiểm chứng cơ chế tự động nhường chỗ cho bean người dùng. **ObjectProvider** giúp ứng dụng vẫn chạy khi bean vắng mặt. Nếu inject **AutoMarker** trực tiếp như dependency bắt buộc, kịch bản tắt auto-config có thể làm ứng dụng thất bại vì thiếu bean.

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
logging.level.root=OFF
~~~

Thiết lập này chỉ giúp output tập trung vào hai dòng demo; không tác động đến điều kiện được định nghĩa trong bài. Khi cần quan sát condition report, hãy ghi đè logging theo hướng dẫn ở phần chẩn đoán.

### 5.6. Build và chạy

Chuẩn bị JDK 21 và Maven 3.9+, đứng tại thư mục **import-vs-auto**:

~~~bash
mvn -q -DskipTests package
~~~

**Kịch bản A — Không truyền property, cả hai nguồn đều có mặt:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar
~~~

Hai dòng do chương trình in:

~~~text
manual=imported
auto=default
~~~

Giải thích: **@Import** đưa ManualFeatureConfiguration vào xử lý, property manual không khai báo nên condition mặc định cho phép. **@EnableAutoConfiguration** tìm AutoFeatureAutoConfiguration qua imports; class và property thỏa điều kiện, chưa có bean AutoMarker của người dùng, vì vậy default được đăng ký.

**Kịch bản B — Tắt bean từ auto-configuration bằng property:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --lesson.auto.enabled=false
~~~

Output:

~~~text
manual=imported
auto=absent
~~~

AutoFeatureAutoConfiguration vẫn có thể là ứng viên được selector tìm thấy. Tuy nhiên method **defaultAutoMarker** không được đăng ký vì **@ConditionalOnProperty** không đạt. Việc tắt property của nhánh auto **không ảnh hưởng** đến cấu hình ManualFeatureConfiguration được import độc lập.

**Kịch bản C — Exclude toàn bộ auto-configuration class:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=dev.lesson.autoconfig.AutoFeatureAutoConfiguration
~~~

Output:

~~~text
manual=imported
auto=absent
~~~

Nhìn output giống kịch bản B nhưng **nguyên nhân khác nhau**: ở đây class auto-configuration bị loại khỏi cơ chế chọn, không chỉ method bean không thỏa property. **@Import** thủ công của ManualFeatureConfiguration vẫn còn và vẫn tạo bean.

**Kịch bản D — Tắt condition trong cấu hình được @Import trực tiếp:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --lesson.manual.enabled=false
~~~

Output:

~~~text
manual=absent
auto=default
~~~

Điều này bác bỏ hiểu nhầm “@Import khiến mọi bean trong class đó nhất định được tạo”. **@ConditionalOnProperty** trên ManualFeatureConfiguration vẫn hoạt động bình thường; còn nhánh auto không bị ảnh hưởng.

**Kịch bản E — Người dùng cung cấp AutoMarker riêng:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom
~~~

Output:

~~~text
manual=imported
auto=user
~~~

Khi profile **custom** hoạt động, phương thức **userAutoMarker()** đăng ký bean do ứng dụng định nghĩa. Vì default trong AutoFeatureAutoConfiguration có **@ConditionalOnMissingBean(AutoMarker.class)**, nhánh mặc định rút lui. Đây là quy tắc điều kiện, **không phải kết quả tự phát của @Import hoặc một cơ chế ghi đè bean cùng tên**.

**Kịch bản F — Property tắt default nhưng bean người dùng vẫn tồn tại:**

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom --lesson.auto.enabled=false
~~~

Output:

~~~text
manual=imported
auto=user
~~~

Property của default chỉ điều khiển nhánh default; nó không tự động vô hiệu hóa bean userAutoMarker thuộc cấu hình ứng dụng.

### 5.7. Thử tắt hẳn @EnableAutoConfiguration để đối chiếu

Tại source **LessonApplication.java**, xóa riêng annotation **@EnableAutoConfiguration** và dòng import Java tương ứng; **giữ nguyên @SpringBootConfiguration, @Import(ManualFeatureConfiguration.class), @Bean ApplicationRunner**. Sau đó build lại với cùng lệnh:

~~~bash
mvn -q -DskipTests package
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar
~~~

Output kỳ vọng trong cấu hình mặc định không bật profile custom:

~~~text
manual=imported
auto=absent
~~~

Khi bỏ @EnableAutoConfiguration, không còn selector của Boot đọc AutoConfiguration.imports cho ứng dụng này. ManualFeatureConfiguration vẫn đi theo đường **@Import** trực tiếp và được xử lý. Đây là đối chiếu rõ nhất về khác biệt chức năng giữa hai annotation.

Hãy phục hồi **@EnableAutoConfiguration** sau thí nghiệm nếu muốn chạy lại A–F. Trong ứng dụng dùng **@SpringBootApplication** thay cho ba annotation tách rời, cơ chế auto-configuration đã được bật gián tiếp; xóa một annotation @EnableAutoConfiguration viết dư ở ngoài sẽ không làm mất cơ chế đó.

## 6. Vì sao không nên @Import trực tiếp mọi lớp auto-configuration?

Một suy nghĩ phổ biến: “Nếu Boot cũng dùng @Import thì tôi import thẳng AutoFeatureAutoConfiguration vào app, cần gì @EnableAutoConfiguration?” Cách làm ấy có thể khiến một class được xử lý như cấu hình tường minh, nhưng lại **bỏ qua mục đích kiến trúc** của cơ chế auto-configuration:

1. **Tập cấu hình động theo thư viện:** Khi thêm/bỏ starter, Boot có thể xét những auto-configuration được các JAR công bố. Import thủ công một danh sách cố định làm ứng dụng phải tự quản danh sách.
2. **Cơ chế exclude chuẩn:** Loại một candidate khỏi bộ chọn auto-configuration không có nghĩa xóa mọi con đường @Import trực tiếp đến cùng class đó.
3. **Thứ tự và nhóm xử lý:** Auto-configuration được sắp xếp và xử lý bằng cơ chế selector của Boot, hỗ trợ các condition xét bean đã có. Import trực tiếp một class có thể làm thay đổi thời điểm xử lý so với ý định của tác giả thư viện.
4. **Ranh giới API:** Các lớp auto-configuration nội bộ thường được xem như chi tiết triển khai. Spring Boot khuyến nghị ứng dụng tùy biến qua property, bean người dùng hoặc exclude có chủ đích thay vì phụ thuộc mã nguồn nội bộ của auto-config.
5. **Không nên quét component các auto-config:** Nếu để class auto-configuration bị @ComponentScan phát hiện như component thông thường, lớp đó có thể đi qua con đường ngoài selector mong muốn và làm kết quả khó đoán.

Dù vậy, **@Import là công cụ hoàn toàn phù hợp** để lắp một cấu hình do ứng dụng hoặc thư viện của bạn cung cấp như **ManualFeatureConfiguration**. Vấn đề là chọn đúng contract: **lắp ghép tường minh** thì dùng @Import; **đề xuất cấu hình mặc định theo môi trường** thì viết auto-configuration được đăng ký qua imports và để @EnableAutoConfiguration xử lý.

## 7. Các hiểu nhầm tinh vi cần tránh

### 7.1. “@Import không xét @Conditional”

Sai. Spring Framework xử lý condition trên configuration class và bean methods được import. Trường hợp D trong ví dụ chứng minh cấu hình ManualFeatureConfiguration bị loại khi **lesson.manual.enabled=false**. Khác biệt nằm ở việc ứng viên được nạp theo cách nào, không phải import là quyền “bỏ qua” condition.

### 7.2. “@EnableAutoConfiguration tương đương @ComponentScan”

Sai. Component scan tìm component theo package và annotation; auto-configuration tìm các lớp ứng viên từ file imports rồi áp dụng điều kiện. Hai công cụ thường cùng có mặt trong **@SpringBootApplication**, nhưng chúng giữ vai trò riêng. Nếu một **@Service** nằm ngoài package scan, chỉ bật auto-configuration không bảo đảm service đó được phát hiện. Tương tự, một auto-configuration có thể ở ngoài package scan nhưng vẫn được Boot xử lý qua selector.

### 7.3. “Chỉ cần class có @AutoConfiguration là Boot sẽ tự nạp”

Sai với Spring Boot 3.x. Class auto-configuration của một thư viện cần được công bố trong resource **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** để tham gia cơ chế phát hiện ứng viên. Việc một cấu hình được @Import trực tiếp qua con đường khác là tình huống riêng, không chứng minh auto-configuration registration đã đúng.

### 7.4. “Nếu class có trong imports thì mọi bean của nó đều đã tạo”

Sai. **Imports** chỉ đưa class vào danh sách ứng viên. Sau đó còn exclude và condition ở cấp class/method. Ngay cả khi BeanDefinition đã đăng ký, instance có thể lazy hoặc lỗi khi tạo. Trong ví dụ, property false khiến method default không tạo bean dù class auto-config hiện diện.

### 7.5. “@ConditionalOnMissingBean là thuộc tính tự động của mọi @AutoConfiguration”

Sai. **@ConditionalOnMissingBean** là annotation điều kiện mà tác giả cấu hình phải khai báo đúng nơi cần tạo mặc định. Không phải mọi @Bean trong một class có @AutoConfiguration đều tự động rút lui khi ứng dụng khai báo bean cùng kiểu.

### 7.6. “@Import luôn lấy đúng một lớp rồi hết”

Sai. **@Import** có thể import nhiều class, ImportSelector, DeferredImportSelector hoặc ImportBeanDefinitionRegistrar. **@EnableAutoConfiguration** khai thác hình thức import selector. Khi nhìn vào source, cần đọc cả loại mà @Import nhận, không chỉ tên annotation.

### 7.7. “Thứ tự trong file imports quyết định thứ tự chạy constructor”

Sai. Spring Boot có metadata/thứ tự auto-configuration như **@AutoConfiguration(before = ...)**, **after = ...** để định hướng thứ tự xử lý cấu hình. Các điều này chủ yếu tác động đến thời điểm **bean definition** được xử lý. Instance được tạo dựa trên lifecycle và dependency; thứ tự khởi tạo object không mặc nhiên bằng thứ tự dòng trong file imports.

### 7.8. “Dùng spring.autoconfigure.exclude sẽ vô hiệu mọi class cùng tên ở khắp nơi”

Không nên dự đoán vậy. Property exclude được thiết kế để loại **auto-configuration candidate** qua cơ chế Boot. Nếu code của ứng dụng vẫn có @Import trực tiếp một class hay tự tạo bean tương ứng, cần xét con đường đó riêng. Đặc biệt, không lạm dụng import trực tiếp auto-configuration nội bộ rồi kỳ vọng tất cả chế độ exclude/ordering vẫn giống trường hợp selector quản lý.

## 8. Debug: khi không biết một bean đến từ đường nào

Khi một bean có mặt hoặc vắng mặt trái kỳ vọng, hãy tách câu hỏi thành các bước:

1. **Tìm nguồn đăng ký**: bean nằm trong phương thức @Bean của lớp ứng dụng được import trực tiếp, component scan, hay class auto-configuration? Đọc class khai báo bean và annotations của nó.
2. **Đối chiếu annotation trên lớp chính**: có @SpringBootApplication hoặc @EnableAutoConfiguration không? Có @Import thủ công không? Có component scan bất ngờ không?
3. **Nếu là auto-config**: kiểm tra JAR chứa class và file AutoConfiguration.imports, các quy tắc exclude và condition theo class/method.
4. **Nếu là @Import trực tiếp**: kiểm tra annotation import, class cấu hình được chỉ tới, các @Conditional và thứ tự import. Đừng dùng condition report của Boot như nguồn duy nhất cho các cấu hình thường.
5. **Kiểm tra bean người dùng**: có bean phù hợp làm @ConditionalOnMissingBean không đạt không? Có profile thay đổi tập definition không?
6. **Phân biệt registration với startup**: bean có definition nhưng lỗi lúc constructor/inject/init là vấn đề khởi tạo, cần xem stack trace thay vì chỉ condition report.

Với ví dụ ở mục 5, muốn xem **Condition Evaluation Report**, dùng:

~~~bash
java -jar target/import-vs-auto-0.0.1-SNAPSHOT.jar --debug --logging.level.root=INFO
~~~

Phần báo cáo giúp giải thích auto-configuration nào match/không match, những ứng viên bị exclude và lý do điều kiện cụ thể. Khi chạy kịch bản B, tìm điều kiện property của **defaultAutoMarker**; khi bật custom profile, xem nhánh **@ConditionalOnMissingBean**. Kịch bản C là loại trừ candidate khỏi selector, khác với negative match tại một method.

**Condition report không chứng minh mọi bean instance đã được tạo thành công**. Nếu có lỗi constructor hoặc dependency, cần xem thông báo **BeanCreationException**. Đối với các cấu hình import trực tiếp không thuộc danh sách auto-configuration, dùng thêm API BeanFactory, log của cấu hình và kiểm tra bean thực tế; không suy ngược rằng vì không thấy trong report nên @Import không hoạt động.

Khi thêm Actuator và cấu hình endpoint thích hợp, **/actuator/conditions** giúp xem kết quả điều kiện ở dạng JSON. Endpoint không mặc định phơi bày công khai; hãy cấu hình exposure và phân quyền theo môi trường. **/actuator/beans** hỗ trợ xem các bean mà context biết tới, nhưng cũng không thay thế việc phân biệt nguồn đăng ký.

## 9. Chọn cách nào trong thực tế?

| Nhu cầu | Công cụ phù hợp | Lý do |
| --- | --- | --- |
| Ứng dụng luôn muốn nạp một cấu hình cụ thể do đội mình sở hữu | **@Import(MyConfiguration.class)** | Rõ ràng, kiểm soát chặt lớp cần xử lý |
| Tạo annotation tùy biến để bật một nhóm module rõ ràng | Meta-annotation dùng **@Import** hoặc ImportSelector phù hợp | Gom cấu hình lắp ghép theo contract của thư viện |
| Thư viện muốn tự đề xuất các bean mặc định khi được thêm vào ứng dụng Boot | **@AutoConfiguration**, file **AutoConfiguration.imports**, điều kiện phù hợp | Tương thích cơ chế chọn ứng viên và back off |
| Ứng dụng Boot thông thường cần tính năng tự cấu hình | **@SpringBootApplication** | Đã bao gồm @EnableAutoConfiguration và các vai trò khởi động cần thiết |
| Muốn thay đổi tham số của bean auto-configured | Property được hỗ trợ | Không cần tự import class nội bộ |
| Muốn tự cung cấp bean thay cho mặc định | **@Bean** trong cấu hình người dùng, kiểm tra @ConditionalOnMissingBean | Boot có thể nhường mặc định khi được thiết kế để back off |
| Muốn tắt riêng một auto-configuration | **exclude/excludeName/spring.autoconfigure.exclude** | Loại class khỏi cơ chế selector tương ứng |
| Muốn xem vì sao auto-config bị loại | **Condition Evaluation Report** | Cho biết positive/negative matches, exclusions và lý do |

Sự phân biệt có ý nghĩa thiết kế: **@Import** mô tả một quyết định lắp ghép cụ thể của ứng dụng; **@EnableAutoConfiguration** mở một bộ máy đề xuất cấu hình có điều kiện dựa trên khả năng thực tế của ứng dụng và những ứng viên các thư viện đã công bố.

## 10. Bài tập tự đánh giá

**Câu 1.** Ứng dụng dùng **@Import(CacheConfiguration.class)**, không bật @EnableAutoConfiguration. CacheConfiguration không có condition và có một @Bean singleton bình thường. Spring có thể đăng ký bean từ cấu hình đó không?

**Đáp án:** Có, vì @Import trực tiếp đủ để đưa class cấu hình vào xử lý. Không cần selector auto-configuration. Việc tạo instance còn tùy vòng đời.

**Câu 2.** Class **XAutoConfiguration** nằm trong file **AutoConfiguration.imports** và trên classpath, nhưng thuộc tính để bật một @Bean của nó là false. Class đó có tạo bean này không?

**Đáp án:** Không, nếu condition của bean yêu cầu thuộc tính đó true. Có mặt trong danh sách ứng viên không đồng nghĩa bean method match.

**Câu 3.** Một dự án có @SpringBootApplication. Thêm @EnableAutoConfiguration lần nữa có cần thiết để bật auto-configuration không?

**Đáp án:** Không. @SpringBootApplication đã chứa @EnableAutoConfiguration; thêm annotation trùng thường là dư thừa và làm code khó đọc.

**Câu 4.** Trong ví dụ runnable, bỏ @EnableAutoConfiguration nhưng giữ @Import(ManualFeatureConfiguration.class). Hai dòng output ở cấu hình mặc định là gì?

**Đáp án:**

~~~text
manual=imported
auto=absent
~~~

**Câu 5.** Vẫn bật @EnableAutoConfiguration, nhưng chạy với **--lesson.manual.enabled=false**. Tại sao bean manual mất?

**Đáp án:** @Import đưa cấu hình vào quá trình xử lý nhưng **@ConditionalOnProperty** trên class ManualFeatureConfiguration không đạt. Import không bỏ qua condition.

**Câu 6.** Vì sao **@EnableAutoConfiguration** vừa khác @Import trực tiếp, vừa có quan hệ với @Import?

**Đáp án:** @EnableAutoConfiguration **sử dụng @Import(AutoConfigurationImportSelector.class)** để kích hoạt một selector. Cơ chế import là công cụ nền; cách selector tìm danh sách ứng viên từ nhiều JAR, lọc điều kiện và exclude mới là hành vi đặc thù của Spring Boot.

**Câu 7.** Một auto-configuration có @ConditionalOnMissingBean(Client.class), ứng dụng import một cấu hình riêng đăng ký bean Client nhưng bean này lazy. Mặc định có thể back off trước khi Client lazy được tạo không?

**Đáp án:** Có. Condition thiếu bean xét thông tin bean đã xử lý trong container, không yêu cầu đối tượng lazy phải được khởi tạo xong.

**Câu 8.** Vì sao không nên trực tiếp @Import vào các lớp auto-configuration nội bộ của Spring Boot để “tiết kiệm” dùng @EnableAutoConfiguration?

**Đáp án:** Cách đó làm ứng dụng phụ thuộc chi tiết triển khai và bỏ qua ý nghĩa của cơ chế tìm/lọc/sắp thứ tự ứng viên chuẩn. Nên dùng property, bean override/back off có điều kiện, hoặc exclude có chủ đích.

## 11. Ghi nhớ

**@Import** nói về **cấu hình được đưa vào xử lý qua một đường import chỉ rõ**; nó có thể import một class cụ thể hoặc một selector/registrar. **@EnableAutoConfiguration** nói về **kích hoạt quy trình Spring Boot phát hiện và chọn các auto-configuration ứng viên dựa trên classpath, imports metadata, exclude và condition**. Điều cốt lõi là *cách tìm và lựa chọn cấu hình*, không phải việc một bên có điều kiện còn bên kia không có.

Khi debug một bean bất kỳ, hãy lần theo nguồn đăng ký của nó: **@Import trực tiếp, component scan hay auto-configuration candidate**. Sau đó mới hỏi condition có đạt không, definition đã được đăng ký chưa, và instance có khởi tạo được không. Tách những câu hỏi này giúp dự đoán đúng hành vi khi thêm starter, đổi property, khai báo bean người dùng, exclude auto-configuration hoặc thay cấu trúc module.

### Tài liệu tham khảo

- Spring Framework, *Using the @Import Annotation*: https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html
- Spring Framework, API **@Import**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Import.html
- Spring Framework, API **ImportSelector**: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ImportSelector.html
- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot, API **@EnableAutoConfiguration**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
