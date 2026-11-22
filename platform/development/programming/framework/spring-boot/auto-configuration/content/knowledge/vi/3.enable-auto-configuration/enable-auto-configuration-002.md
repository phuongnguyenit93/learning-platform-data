# @EnableAutoConfiguration kích hoạt lựa chọn cấu hình như thế nào?

## 1. Điều được kích hoạt là một cơ chế lựa chọn, không phải tất cả cấu hình

Khi thêm **@EnableAutoConfiguration** vào một lớp cấu hình Spring, ứng dụng cho phép Spring Boot **tìm các lớp auto-configuration ứng viên, áp dụng quy tắc loại trừ, kiểm tra điều kiện và đăng ký các bean definition phù hợp**. Annotation này không tự động tạo mọi bean trong toàn bộ thư viện Spring Boot. Tập bean cuối cùng còn phụ thuộc vào **classpath**, **Environment và thuộc tính**, **loại ứng dụng**, **bean do người dùng định nghĩa**, các điều kiện khác và khả năng khởi tạo thực tế.

Với dự án Spring Boot thông thường, developer thường không viết annotation này trực tiếp, vì **@SpringBootApplication** đã chứa **@EnableAutoConfiguration**.

Ví dụ tối giản:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MyApplication {
    public static void main(String[] args) {
        SpringApplication.run(MyApplication.class, args);
    }
}
~~~

Đoạn trên minh họa cách bật, chưa phải file độc lập có package/cấu trúc Maven. Chính **@SpringBootApplication** khiến phần auto-configuration được kích hoạt; không cần gắn thêm **@EnableAutoConfiguration** lần thứ hai lên cùng ứng dụng.

Điều quan trọng là phân biệt ba sự kiện:

1. **Đã bật cơ chế**: có **@EnableAutoConfiguration** trực tiếp hoặc gián tiếp.
2. **Đã chọn nhánh cấu hình**: một ứng viên không bị exclude và các điều kiện liên quan đạt.
3. **Đã có bean instance**: bean definition được chọn và sau đó container thực sự tạo được đối tượng theo lifecycle/scope.

Ba sự kiện không tương đương. Có bật auto-configuration nhưng không có DataSource nếu môi trường không đủ điều kiện. Có một cấu hình được chọn nhưng bean lazy bên trong vẫn chưa được khởi tạo.

## 2. Cấu tạo của annotation và các annotation liên quan

Ở Spring Boot 3.x, **@EnableAutoConfiguration** được xây trên hai mắt xích quan trọng:

- **@AutoConfigurationPackage**: đăng ký package mặc định phục vụ một số cơ chế auto-configured như tìm entity hoặc Spring Data repository. Package này thường lấy từ package chứa lớp đã gắn **@EnableAutoConfiguration**. Đây **không phải** lệnh quét tất cả component trong mọi thư viện.
- **@Import(AutoConfigurationImportSelector.class)**: đưa bộ chọn auto-configuration vào quá trình xử lý cấu hình của Spring. Đây là phần trực tiếp góp phần phát hiện, lọc và import ứng viên auto-configuration.

Hình dung về mặt cấu trúc (đã giản lược các annotation về target/retention/documentation):

~~~java
@AutoConfigurationPackage
@Import(AutoConfigurationImportSelector.class)
public @interface EnableAutoConfiguration {
    Class<?>[] exclude() default {};
    String[] excludeName() default {};
}
~~~

**Đây chỉ là mô hình giải thích**, không phải mã nguồn annotation đầy đủ để copy định nghĩa lại. Hai thuộc tính **exclude** và **excludeName** giúp ứng dụng loại cấu hình không mong muốn khỏi danh sách ứng viên.

**@SpringBootApplication** kết hợp ba vai trò chính:

| Vai trò | Annotation nền | Ý nghĩa |
| --- | --- | --- |
| Lớp cấu hình khởi động | **@SpringBootConfiguration** | Lớp ứng dụng có thể khai báo bean và import cấu hình. |
| Quét component ứng dụng | **@ComponentScan** | Tìm các component trong package được chỉ định hoặc package gốc mặc định. |
| Tự cấu hình | **@EnableAutoConfiguration** | Import các auto-configuration ứng viên từ metadata, sau đó xét điều kiện. |

Việc “component của ứng dụng được quét” khác với việc “auto-configuration được nạp”. Một thư viện có thể mang auto-configuration nằm ngoài package scan của ứng dụng và vẫn được Boot phát hiện thông qua metadata imports. Ngược lại, một class mang **@AutoConfiguration** nhưng không đăng ký đúng cơ chế phát hiện không tự nhiên được nạp chỉ vì annotation đó có mặt trên source file.

Bạn cũng có thể dùng các annotation tường minh trên cấu hình chính:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.context.annotation.ComponentScan;

@SpringBootConfiguration
@EnableAutoConfiguration
@ComponentScan
public class ExplicitApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExplicitApplication.class, args);
    }
}
~~~

Đây là lựa chọn thay thế minh họa tương đương về ba vai trò chính. Thực tế nên ưu tiên **@SpringBootApplication** khi không có yêu cầu cấu hình đặc biệt. Không khai báo cả hai lớp cấu hình ứng dụng ở hai ví dụ làm entry point của cùng dự án mà không thiết kế rõ ràng.

### 2.1. Package của lớp chính có ý nghĩa gì?

Đặt lớp ứng dụng trong package gốc, chẳng hạn **dev.example.app**, ảnh hưởng vùng **@ComponentScan** mặc định. Đồng thời, **@AutoConfigurationPackage** xác định package mặc định phục vụ những tính năng auto-configured tìm kiếm entity/repository. Thuộc tính **scanBasePackages** của **@SpringBootApplication** điều chỉnh phạm vi component scan, nhưng không tự động đổi mọi package mà entity/repository scanning dùng. Khi muốn đổi các phạm vi chuyên biệt, cần xem annotation và cấu hình chuyên biệt của tính năng đó.

Không nhầm “không quét được **@Service** của ứng dụng” với “**@EnableAutoConfiguration** không hoạt động”; hai đường phát hiện khác nhau.

## 3. Chuỗi xử lý từ annotation đến tập cấu hình được chọn

Spring Framework xử lý các lớp **@Configuration** trong quá trình refresh ApplicationContext. Trong quá trình đó, **@Import(AutoConfigurationImportSelector.class)** cho phép Spring Boot tham gia lựa chọn cấu hình. **AutoConfigurationImportSelector** là một **DeferredImportSelector**: các import auto-configuration được xử lý ở giai đoạn trì hoãn, giúp cấu hình và bean definition do ứng dụng chủ động khai báo có cơ hội được xử lý trước. Điều này hỗ trợ cơ chế “back off” khi ứng dụng đã tự cung cấp bean.

Sơ đồ khái niệm:

~~~text
@SpringBootApplication
        |
        v
@EnableAutoConfiguration
        |
        +--> @AutoConfigurationPackage
        |         |
        |         +--> Đăng ký package mặc định cho một số tính năng
        |
        +--> @Import(AutoConfigurationImportSelector.class)
                  |
                  v
       Đọc danh sách auto-configuration ứng viên từ các JAR
                  |
                  v
       Khử trùng lặp và áp dụng cấu hình loại trừ
                  |
                  v
       Sàng lọc ứng viên theo điều kiện/metadata phù hợp
                  |
                  v
       Import các @AutoConfiguration đủ điều kiện để xử lý
                  |
                  v
       Xét điều kiện ở cấp lớp và từng @Bean
                  |
                  +--> Không đạt: bỏ qua lớp/bean tương ứng
                  |
                  +--> Đạt: đăng ký bean definition
                                      |
                                      v
                    Spring container tạo instance khi cần
~~~

Sơ đồ đơn giản hóa các pass xử lý condition và registration. Không có nghĩa mọi condition chỉ được kiểm tra đúng một lần tại một vị trí; trong thực tế một số điều kiện có thể được đánh giá trong giai đoạn parse configuration và một số tại giai đoạn đăng ký bean.

### 3.1. Tìm ứng viên trong JAR

Trong Spring Boot 3.x, các thư viện đăng ký auto-configuration bằng một resource đúng tên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung là tên lớp đầy đủ, mỗi dòng một ứng viên, ví dụ:

~~~text
dev.example.autoconfig.GreetingAutoConfiguration
dev.example.autoconfig.OptionalFeatureAutoConfiguration
~~~

Tên **.imports** là một phần của contract phát hiện ứng viên. Các class có thể nằm trong JAR ứng dụng hoặc JAR thư viện. Spring Boot đọc tài nguyên từ runtime classpath; các module/thư viện hiện diện quyết định danh sách resource nào có thể được đọc.

**Lưu ý phiên bản:** Với Spring Boot 3.x, cơ chế imports là cách đăng ký ứng viên auto-configuration. Tài liệu về Spring Boot đời cũ từng trình bày đăng ký dưới key **EnableAutoConfiguration** trong **META-INF/spring.factories**. Không lấy ví dụ cũ đó làm định dạng đăng ký auto-configuration mới cho Spring Boot 3.x. Resource **spring.factories** vẫn có các mục đích SPI khác; hai điều này không mâu thuẫn.

Chỉ liệt kê một class trong imports biến nó thành **ứng viên**, chưa bảo đảm bean của nó sẽ được tạo. Cần có **@AutoConfiguration** và các điều kiện thích hợp. Spring Boot thường khuyến nghị để auto-configuration trong package riêng, không cho component scan của ứng dụng bắt chúng như component thông thường.

### 3.2. Từ ứng viên đến lớp cấu hình được xử lý

Có thể chia lựa chọn thành những loại quyết định sau:

- **Có thể tìm thấy:** resource imports hiện diện trên classpath và liệt kê class đúng tên.
- **Không bị loại trừ:** class không nằm trong **exclude**, **excludeName** hoặc **spring.autoconfigure.exclude**.
- **Đủ điều kiện class/property/web/resource/bean:** annotation điều kiện trên class auto-configuration hoặc một nhánh lồng nhau có thể khiến Spring bỏ qua class đó.
- **Bean method đủ điều kiện:** ngay cả khi lớp auto-configuration được xử lý, một **@Bean** cụ thể vẫn có thể bị loại vì **@ConditionalOnMissingBean**, **@ConditionalOnProperty** hoặc condition khác.
- **Khởi tạo thành công:** sau khi definition được đăng ký, dependencies, constructor, init callback và tài nguyên thật vẫn phải hoạt động.

“Ứng viên đã có trong imports”, “positive match trong report”, “definition đã đăng ký” và “instance đã tạo” là các trạng thái khác nhau.

### 3.3. Tác dụng của metadata và thứ tự auto-configuration

Spring Boot có thể dùng metadata điều kiện được sinh sẵn, chẳng hạn **META-INF/spring-autoconfigure-metadata.properties**, để lọc sớm các ứng viên hiển nhiên không phù hợp, giúp giảm chi phí startup. Metadata tối ưu hóa **không thay thế** file **AutoConfiguration.imports** làm danh sách ứng viên.

Nếu có nhiều auto-configuration, có thể định hướng thứ tự xử lý bằng **@AutoConfiguration(after = ...)**, **@AutoConfiguration(before = ...)** hoặc các annotation chuyên biệt về thứ tự auto-configuration. Thứ tự này chủ yếu ảnh hưởng **thứ tự xử lý/đăng ký bean definition**, đặc biệt quan trọng với điều kiện xét bean đã có. Nó **không bảo đảm** thứ tự constructor của mọi bean instance; dependency và lifecycle quyết định thứ tự khởi tạo thích hợp.

## 4. Điều kiện quyết định có áp dụng auto-configuration hay không

Các annotation điều kiện phổ biến:

| Điều kiện | Tín hiệu xét | Cách hiểu |
| --- | --- | --- |
| **@ConditionalOnClass** | Class trên runtime classpath | Chỉ xử lý nhánh khi thư viện cần thiết có mặt. |
| **@ConditionalOnMissingClass** | Class không có trên classpath | Chọn nhánh thay thế cho trường hợp thiếu thư viện. |
| **@ConditionalOnProperty** | Giá trị một property trong Environment | Bật/tắt nhánh theo thuộc tính cuối cùng mà Spring đọc. |
| **@ConditionalOnBean** | Bean phù hợp đã có trong ngữ cảnh xét | Phụ thuộc cấu hình hoặc dịch vụ khác đã được đăng ký. |
| **@ConditionalOnMissingBean** | Chưa có bean phù hợp | Cho phép auto-configuration cung cấp mặc định khi người dùng chưa khai báo. |
| **@ConditionalOnWebApplication** | Kiểu môi trường web | Chỉ chọn cấu hình dành cho servlet hoặc reactive theo yêu cầu. |
| **@ConditionalOnResource** | Resource cần thiết | Chỉ chọn cấu hình khi resource xác định hiện diện. |

Với điều kiện **@ConditionalOnProperty(prefix = "demo.greeting", name = "enabled", havingValue = "true", matchIfMissing = true)**:

- **demo.greeting.enabled=true**: điều kiện đạt.
- **demo.greeting.enabled=false**: điều kiện không đạt.
- Property vắng mặt: điều kiện đạt vì **matchIfMissing=true**.
- Nếu class bắt buộc của cấu hình vắng mặt, property đúng vẫn chưa đủ để kích hoạt nhánh.

Không phải mọi property có chữ **enabled** đều có mặc định như vậy; phải xem annotation và tài liệu của từng cấu hình.

### 4.1. Bean người dùng khiến mặc định rút lui ra sao?

Rất nhiều auto-configuration sử dụng **@ConditionalOnMissingBean**. Khi ứng dụng tự định nghĩa một bean phù hợp, nhánh mặc định có điều kiện này **không đăng ký bean trùng chức năng**. Đây là cơ chế Boot ưu tiên cấu hình người dùng mà không cần tắt tất cả auto-configuration.

Ví dụ minh họa, không phải chương trình độc lập:

~~~java
@AutoConfiguration
@ConditionalOnClass(PaymentClient.class)
class PaymentClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(PaymentClient.class)
    PaymentClient defaultPaymentClient() {
        return new PaymentClient();
    }
}
~~~

**PaymentClient** ở đây là kiểu giả định phục vụ giải thích. Nếu class và các điều kiện khác phù hợp nhưng ứng dụng đã định nghĩa bean **PaymentClient**, bean mặc định không được đăng ký. Điều này không dựa trên việc constructor của bean người dùng đã chạy hay chưa; container có thể xét các bean definition đã được xử lý.

**Cảnh báo về thứ tự:** các điều kiện **@ConditionalOnBean** và **@ConditionalOnMissingBean** dựa trên định nghĩa đã được xử lý tại thời điểm đánh giá. Spring Boot khuyến nghị đặt chúng trong các lớp auto-configuration thay vì lạm dụng trên cấu hình ứng dụng thường, vì auto-configuration được xử lý sau định nghĩa do người dùng khai báo.

**Không phải mọi @Bean đều có @ConditionalOnMissingBean.** Nếu một cấu hình cố ý cung cấp nhiều bean hoặc không có guard này, việc thêm bean cùng kiểu có thể dẫn đến nhiều bean và xung đột injection; không được suy rằng Boot luôn tự lùi.

## 5. Ví dụ hoàn chỉnh: quan sát auto-configuration được bật và lựa chọn bean

Ví dụ sử dụng **Java 21**, **Maven 3.9+**, **Spring Boot 3.3.13**. Ta viết một auto-configuration nhỏ có tên **GreetingAutoConfiguration** và đăng ký bằng file imports. Sau đó chạy ứng dụng để so sánh bốn trạng thái:

1. Điều kiện đạt: tạo **GreetingService** mặc định.
2. Property tắt: không tạo mặc định.
3. Bean người dùng xuất hiện: mặc định rút lui.
4. Loại cả class auto-configuration: không áp dụng dù điều kiện khác có thể đạt.

Ứng dụng được thiết kế để in một dòng kết quả duy nhất của chương trình ở từng lần chạy. Các thông báo từ Maven hay công cụ bên ngoài không thuộc stdout của code ứng dụng.

### 5.1. Cấu trúc source

~~~text
enable-auto-demo/
├── pom.xml
└── src/main/
    ├── java/dev/academy/
    │   ├── api/GreetingService.java
    │   ├── autoconfig/GreetingAutoConfiguration.java
    │   └── app/
    │       ├── DemoApplication.java
    │       └── UserGreetingConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Đặt lớp chính trong **dev.academy.app** và auto-configuration trong **dev.academy.autoconfig** nhằm minh họa: lớp auto-configuration **nằm ngoài component scan mặc định của app**, nhưng vẫn được import từ metadata của Boot. Không gắn **@Component** hoặc **@ComponentScan** vào lớp auto-configuration.

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

    <groupId>dev.academy</groupId>
    <artifactId>enable-auto-demo</artifactId>
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

**src/main/java/dev/academy/api/GreetingService.java**

~~~java
package dev.academy.api;

@FunctionalInterface
public interface GreetingService {
    String greet(String name);
}
~~~

**src/main/java/dev/academy/autoconfig/GreetingAutoConfiguration.java**

~~~java
package dev.academy.autoconfig;

import dev.academy.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    @ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    GreetingService defaultGreetingService() {
        return name -> "Auto: " + name;
    }
}
~~~

Cách đọc:

- **@AutoConfiguration** đánh dấu đây là lớp cấu hình auto-configuration của Spring Boot.
- **@ConditionalOnClass(GreetingService.class)** yêu cầu API có trên classpath. Trong project mẫu API được định nghĩa trực tiếp nên điều kiện này luôn đúng. Với thư viện thực, một dependency tùy chọn có thể quyết định sự hiện diện của class.
- **@ConditionalOnMissingBean(GreetingService.class)** nhường quyền nếu người dùng đã cung cấp bean phù hợp.
- **@ConditionalOnProperty** tắt bean mặc định khi **demo.greeting.enabled=false**, nhưng cho phép khi property không khai báo.
- Phương thức **@Bean** chỉ được chọn khi các điều kiện liên quan đạt; việc chọn một bean definition không đồng nghĩa ngay tại đó factory method đã chạy.

**src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.academy.autoconfig.GreetingAutoConfiguration
~~~

File này **bắt buộc** đối với ví dụ: Boot cần biết lớp nào là ứng viên auto-configuration. Chỉ có **@AutoConfiguration** trên source mà không có file imports thì ví dụ không thể chứng minh cơ chế selector nạp lớp nằm ngoài component scan.

**src/main/java/dev/academy/app/DemoApplication.java**

~~~java
package dev.academy.app;

import dev.academy.api.GreetingService;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showSelectedGreeting(
            ObjectProvider<GreetingService> greetings) {
        return args -> {
            GreetingService service = greetings.getIfAvailable();
            System.out.println(service == null
                ? "selected=<none>"
                : "selected=" + service.greet("Mai"));
        };
    }
}
~~~

**ObjectProvider** giúp mẫu vẫn chạy khi cố ý không có GreetingService. Không inject trực tiếp một GreetingService bắt buộc vào constructor của class chính, vì trường hợp property tắt hoặc exclude toàn bộ auto-configuration sẽ làm startup thất bại vì thiếu bean.

**src/main/java/dev/academy/app/UserGreetingConfiguration.java**

~~~java
package dev.academy.app;

import dev.academy.api.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class UserGreetingConfiguration {

    @Bean
    GreetingService userGreetingService() {
        return name -> "User: " + name;
    }
}
~~~

Bean người dùng chỉ được đăng ký khi profile **custom** hoạt động; khi đó **@ConditionalOnMissingBean(GreetingService.class)** của cấu hình mặc định không đạt.

**src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
logging.level.root=OFF
~~~

Dòng logging này giúp output của ví dụ gọn. Để xem condition report ở phần chẩn đoán, cần bật logging trở lại bằng tham số phù hợp.

### 5.2. Build và thử bốn nhánh

Ở thư mục **enable-auto-demo**, dùng JDK 21 và Maven:

~~~bash
mvn -q -DskipTests package
~~~

**Trường hợp A: auto-configuration mặc định được chọn**

~~~bash
java -jar target/enable-auto-demo-0.0.1-SNAPSHOT.jar
~~~

Dòng do ứng dụng in:

~~~text
selected=Auto: Mai
~~~

**Vì sao?** **@SpringBootApplication** bật cơ chế auto-configuration; imports chứa **GreetingAutoConfiguration**; class **GreetingService** có mặt; không có bean người dùng ở profile mặc định; property enabled vắng mặt được cho phép bởi **matchIfMissing=true**. Spring đăng ký definition và tạo instance mặc định khi runner cần nó.

**Trường hợp B: property loại bean mặc định**

~~~bash
java -jar target/enable-auto-demo-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=false
~~~

Stdout:

~~~text
selected=<none>
~~~

**Vì sao?** Lớp GreetingAutoConfiguration vẫn là ứng viên và có thể được xử lý, nhưng điều kiện property trên phương thức **@Bean** không đạt. Không có GreetingService mặc định. Điều này **khác** với exclude toàn bộ lớp auto-configuration.

**Trường hợp C: bean người dùng được ưu tiên**

~~~bash
java -jar target/enable-auto-demo-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom
~~~

Stdout:

~~~text
selected=User: Mai
~~~

**Vì sao?** Profile custom đăng ký **userGreetingService**; điều kiện **@ConditionalOnMissingBean** của phương thức mặc định không đạt. Không phải Spring Boot dùng **@Primary** để chọn giữa hai bean cùng tồn tại: trong trường hợp này bean mặc định hoàn toàn không được đăng ký.

**Trường hợp D: exclude lớp auto-configuration**

~~~bash
java -jar target/enable-auto-demo-0.0.1-SNAPSHOT.jar --spring.autoconfigure.exclude=dev.academy.autoconfig.GreetingAutoConfiguration
~~~

Stdout:

~~~text
selected=<none>
~~~

**Vì sao?** Selector loại **GreetingAutoConfiguration** khỏi tập auto-configuration được áp dụng. Trong profile mặc định không có bean người dùng. Exclude nhánh auto-configuration **không tự xóa** một bean mà ứng dụng chủ động định nghĩa; nếu vừa exclude vừa bật profile custom thì vẫn nhận **selected=User: Mai**.

### 5.3. Một bảng tóm tắt điều kiện trong chính ví dụ

| Kịch bản | Auto-config class được phép xử lý? | Property match? | Có bean người dùng? | GreetingService được chọn |
| --- | --- | --- | --- | --- |
| A: mặc định | Có | Có, do matchIfMissing | Không | Bean mặc định |
| B: enabled=false | Có | Không | Không | Không có |
| C: custom profile | Có | Có | Có | Bean người dùng; default back off |
| D: exclude | Không | Không cần xét nhánh bị loại | Không | Không có |

Bảng áp dụng riêng cho các condition của **GreetingAutoConfiguration** trong bài. Với cấu hình khác, điều kiện có thể nằm ở cấp lớp, bean method hoặc cấu hình lồng nhau và cho kết quả khác.

## 6. Cách exclude auto-configuration: chọn đúng cấp độ

Trong Spring Boot, ba cách thông dụng để loại một **auto-configuration class**:

**Cách 1: exclude bằng class literal trên @SpringBootApplication**

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication(
    exclude = dev.academy.autoconfig.GreetingAutoConfiguration.class
)
public class DemoApplication {
}
~~~

Đoạn này minh họa annotation class; để chạy nguyên project mẫu phải giữ lại phương thức **main** và các thành phần khác. Tên lớp được exclude là public API được Spring Boot hỗ trợ trong phạm vi exclude.

**Cách 2: exclude bằng tên lớp khi không muốn tham chiếu class literal**

~~~java
@SpringBootApplication(
    excludeName = "dev.academy.autoconfig.GreetingAutoConfiguration"
)
public class DemoApplication {
}
~~~

Đoạn minh họa tương tự, không chứa imports/method main và không phải file độc lập. **excludeName** hữu ích khi code biên dịch không có tham chiếu trực tiếp tới class.

**Cách 3: dùng property**

~~~properties
spring.autoconfigure.exclude=dev.academy.autoconfig.GreetingAutoConfiguration
~~~

Property có thể đặt trong file cấu hình hoặc truyền qua dòng lệnh như ví dụ D. Có thể loại trừ nhiều auto-configuration class bằng danh sách tên đúng theo định dạng property.

Nếu đang dùng **@EnableAutoConfiguration** trực tiếp thay vì **@SpringBootApplication**, các thuộc tính **exclude** và **excludeName** cũng khả dụng ở đó.

**Phân biệt các thao tác:**

- **Exclude class auto-configuration**: loại cả nhánh import tương ứng.
- **Tắt một feature property**: chỉ ảnh hưởng các nhánh có condition đọc property đó.
- **Định nghĩa bean riêng**: có thể khiến default back off **nếu** nhánh mặc định dùng **@ConditionalOnMissingBean** phù hợp.
- **@Primary** và **@Qualifier**: giúp giải quyết injection khi có nhiều bean, không trực tiếp loại một auto-configuration khỏi danh sách ứng viên.

Chỉ exclude khi biết rõ cấu hình muốn loại; nhiều auto-configuration của Boot phối hợp với nhau. Loại một class có thể khiến các feature phụ thuộc không còn đủ điều kiện.

## 7. Kiểm chứng bằng condition evaluation report

Để trả lời “vì sao lớp X được chọn hoặc không?”, bật chẩn đoán condition. Với project mẫu đang đặt **logging.level.root=OFF**, hãy ghi đè mức log để báo cáo hiển thị:

~~~bash
java -jar target/enable-auto-demo-0.0.1-SNAPSHOT.jar --debug --logging.level.root=INFO
~~~

Bạn sẽ thấy log khởi động và một **CONDITIONS EVALUATION REPORT** với các phần về positive matches, negative matches và các mục không có condition, tùy phiên bản/cấu hình logging.

Tìm **GreetingAutoConfiguration** và **defaultGreetingService**. Ở trạng thái mặc định, condition class có thể đạt và condition bean method cũng đạt. Khi thêm **--demo.greeting.enabled=false**, nhánh condition của method có thể xuất hiện trong nhóm negative match với lý do property. Khi bật profile custom, **@ConditionalOnMissingBean** có thể cho biết đã tồn tại bean phù hợp. Khi dùng **spring.autoconfigure.exclude**, class được loại khỏi tập auto-config và có thể được liệt kê trong phần exclusions; không đọc một mục absent trong report rồi tự kết luận chi tiết mà chưa xem exclusions.

**Cẩn thận:** Báo cáo điều kiện cho biết **lý do match/không match**, không phải bằng chứng bean đã được khởi tạo hoặc external service đã kết nối thành công. Nếu sau khi match mà constructor, binding hoặc connection gây lỗi, cần đọc stack trace của **BeanCreationException**.

Với ứng dụng có **spring-boot-starter-actuator** và endpoint được cấu hình/phơi bày phù hợp, **/actuator/conditions** cho báo cáo dưới dạng JSON. Endpoint này không mặc nhiên công khai; cần điều chỉnh exposure và bảo vệ truy cập theo môi trường. **/actuator/beans** hữu ích để xem bean hiện được container nhận biết, nhưng không thay thế condition report khi truy tìm vì sao một nhánh bị loại.

### 7.1. Phân biệt bốn loại lỗi

| Triệu chứng | Khả năng chính | Hành động kiểm tra |
| --- | --- | --- |
| Lớp auto-config không xuất hiện như ứng viên | Sai/mất file imports, thiếu JAR, exclude | Xem runtime classpath, nội dung imports, exclusion |
| Lớp là ứng viên nhưng negative match | Thiếu class, property không đạt, môi trường web sai | Đọc lý do trong condition report |
| Lớp match nhưng bean method không được chọn | Bean người dùng đã có hoặc condition ở method khác | Xem condition ở chính method và bean definitions |
| Definition tồn tại nhưng ứng dụng không dùng được bean | Lỗi khởi tạo/dependency/binding/resource | Xem BeanCreationException, lifecycle, scope |

Đừng chỉnh dependency, property hoặc exclude ngẫu nhiên trước khi biết vấn đề nằm ở lớp nào của chuỗi quyết định.

## 8. Tình huống liên quan đến starter và các cấu hình khác nhau

**Tình huống 1: Có starter-web.** Starter đưa các thư viện phục vụ Spring MVC và server nhúng (theo cây dependency cụ thể) lên classpath. Khi Boot xử lý candidate tương ứng, **@ConditionalOnClass** và **@ConditionalOnWebApplication** có thể đạt nếu ngữ cảnh thích hợp; các condition khác còn quyết định bean nào được tạo. Starter **không mang nghĩa “bật toàn bộ auto-configuration bất kể điều kiện”**.

**Tình huống 2: Có starter-jdbc.** Các class JDBC giúp những candidate JDBC có cơ hội match. Nhưng để cấu hình DataSource hữu dụng cần driver, URL/embedded database hoặc các thiết lập phù hợp, và không bị bean người dùng thay thế. Thiếu điều kiện hoặc lỗi tài nguyên vẫn có thể khiến khởi động thất bại. Đọc condition report trước khi kết luận auto-config bị tắt.

**Tình huống 3: Cùng source, khác environment.** Tham số dòng lệnh, profile và nguồn property khác nhau có thể khiến cùng một class auto-configuration chọn bean khác nhau. Environment đã tổng hợp và giải quyết độ ưu tiên của property trước khi điều kiện đọc giá trị cuối cùng.

**Tình huống 4: Thêm bean riêng.** Nếu branch mặc định gắn **@ConditionalOnMissingBean** theo kiểu bean đang có, Spring Boot thường rút lui. Điều này cho phép người dùng tùy biến có chọn lọc; không cần đặt exclude cho mọi auto-configuration liên quan.

**Tình huống 5: Thứ tự các auto-config.** Nếu A cần bean mà B cung cấp, các khai báo thứ tự như **@AutoConfiguration(after = B.class)** có thể giúp điều kiện xét bean hoạt động theo thứ tự phù hợp. Đây là sắp xếp cách xử lý các cấu hình, không phải giải pháp ép startup instance B trước instance A nếu chúng không có dependency cần thiết.

## 9. Các hiểu nhầm thường gặp

| Nhận định sai | Giải thích chính xác |
| --- | --- |
| “@EnableAutoConfiguration tự động khởi tạo tất cả bean.” | Nó bật cơ chế tìm và áp dụng các auto-configuration phù hợp; còn condition, scope và lifecycle. |
| “@SpringBootApplication phải đi kèm @EnableAutoConfiguration riêng.” | Annotation tổng hợp đã chứa cơ chế auto-configuration. |
| “Auto-configuration giống @ComponentScan.” | Component scan tìm component theo package; auto-config dùng candidate imports và xét điều kiện. |
| “Có @AutoConfiguration trên class là đủ để Boot tự thấy.” | Class cần xuất hiện trong resource **AutoConfiguration.imports** nếu được cung cấp theo cơ chế này. |
| “Spring Boot 3 vẫn dùng key EnableAutoConfiguration trong spring.factories để nạp candidate mới.” | Spring Boot 3 dùng **AutoConfiguration.imports** cho candidate auto-configuration. |
| “Có class trên classpath thì chắc chắn có bean.” | Classpath là một điều kiện, còn property, bean, environment và các điều kiện khác. |
| “Property enabled=true vượt qua mọi condition.” | Không; các condition liên quan đều phải đạt. |
| “Có bean người dùng thì mọi bean mặc định bị xóa.” | Chỉ những nhánh có condition thích hợp mới back off. |
| “Positive match nghĩa là service đã kết nối thành công.” | Report phản ánh điều kiện, không bảo đảm khởi tạo và kết nối tài nguyên thành công. |
| “Thứ tự auto-configuration chính là thứ tự tạo object.” | Thứ tự đăng ký definition và thứ tự tạo bean instance là hai vấn đề. |
| “Exclude và property=false tương đương.” | Exclude bỏ cả auto-configuration class; property có thể chỉ ảnh hưởng một nhánh. |
| “Bật auto-config là đủ để scan bean từ package bất kỳ.” | Component scanning và các package chuyên biệt có phạm vi riêng. |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Một thư viện chứa file **AutoConfiguration.imports** liệt kê lớp **XAutoConfiguration**. Như vậy lớp X đã chắc chắn tạo bean chưa?

**Đáp án:** Chưa. Lớp mới là ứng viên; có thể bị exclude hoặc condition không đạt. Ngay cả khi definition đăng ký, việc tạo instance còn phụ thuộc lifecycle và có thể thất bại.

**Câu 2.** Bạn có **@SpringBootApplication** trên main class nhưng không khai báo **@EnableAutoConfiguration** riêng. Tự cấu hình có được bật không?

**Đáp án:** Có. **@SpringBootApplication** chứa **@EnableAutoConfiguration**.

**Câu 3.** Mặc định có **defaultGreetingService**, nhưng khi bật profile **custom** thì chỉ có **userGreetingService**. Tại sao?

**Đáp án:** Bean người dùng đã được khai báo trước khi auto-config xét điều kiện; **@ConditionalOnMissingBean(GreetingService.class)** không đạt nên default back off.

**Câu 4.** Chạy ứng dụng với **demo.greeting.enabled=false** và **spring.profiles.active=custom** thì có GreetingService không?

**Đáp án:** Có **userGreetingService**, vì condition property chỉ gắn với phương thức tạo default bean trong ví dụ. Bean người dùng không bị property đó tự động loại.

**Câu 5.** Exclude **GreetingAutoConfiguration** và không bật custom profile, nhưng vẫn có GreetingService mặc định từ class này được không?

**Đáp án:** Không. Class auto-configuration đã bị loại khỏi tập xử lý; không có bean do class đó cung cấp. Nếu có một bean từ nguồn khác thì cần đánh giá riêng.

**Câu 6.** Vì sao report có một positive match nhưng ứng dụng báo **BeanCreationException**?

**Đáp án:** Điều kiện chọn cấu hình và quá trình khởi tạo instance là hai giai đoạn. Match chỉ cho biết điều kiện phù hợp; constructor/factory method/dependency có thể lỗi khi tạo object.

**Câu 7.** Nếu muốn tắt đúng một auto-configuration, có cần tắt **@EnableAutoConfiguration** trên toàn ứng dụng không?

**Đáp án:** Không. Dùng **exclude**, **excludeName** hoặc **spring.autoconfigure.exclude** cho class cụ thể; nếu chỉ muốn điều chỉnh một feature, xem property chuyên biệt trước.

## 11. Kết luận thực hành

Mỗi lần cần giải thích vì sao Spring Boot đưa một bean vào ứng dụng, hãy lần theo chuỗi: **(1) @EnableAutoConfiguration đã bật chưa? (2) class auto-configuration có trong imports/runtime classpath không? (3) class có bị exclude không? (4) điều kiện ở cấp lớp và từng @Bean có đạt không? (5) bean definition được đăng ký chưa? (6) instance đã khởi tạo thành công chưa?**

**@EnableAutoConfiguration** là điểm mở đầu của cơ chế **lựa chọn cấu hình theo điều kiện**. **AutoConfigurationImportSelector** tìm và chọn các auto-configuration ứng viên; các condition phối hợp classpath, property, môi trường và bean do người dùng định nghĩa; cuối cùng Spring container tạo các instance cần thiết. Hiểu đầy đủ chuỗi này giúp bạn thay đổi cấu hình có chủ đích và dùng condition report để chẩn đoán chính xác.

### Tài liệu tham khảo

- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot 3.3, API **@EnableAutoConfiguration**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html
- Spring Boot 3.3, API **AutoConfigurationImportSelector**: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html
