# Thư viện, starter, thuộc tính và bean người dùng cùng quyết định cấu hình được chọn

## 1. Bài toán: vì sao cùng Spring Boot nhưng hai ứng dụng nhận cấu hình khác nhau?

Spring Boot **auto-configuration** tự đề xuất các bean và thiết lập phù hợp với ứng dụng tại thời điểm khởi động. Đề xuất đó có điều kiện, không phải cam kết rằng cứ thêm một thư viện là Spring Boot tạo mọi bean liên quan. Hai ứng dụng cùng phiên bản Spring Boot có thể nhận cấu hình khác nhau vì **dependency trên classpath**, **starter đã chọn**, **thuộc tính môi trường** và **bean do ứng dụng khai báo** khác nhau.

Ví dụ: một ứng dụng có thư viện JDBC nhưng không có cấu hình kết nối thích hợp có thể không tạo được DataSource; một ứng dụng khác có thư viện, có cấu hình kết nối và chưa khai báo DataSource riêng có thể dùng DataSource được auto-configure; còn ứng dụng đã khai báo DataSource riêng thường khiến nhánh tạo DataSource mặc định rút lui. Đừng suy từ việc có một dependency ra kết luận mọi bean chắc chắn tồn tại.

Phân biệt ba khái niệm:

- **Dependency/thư viện**: các JAR và class có trên runtime classpath, ví dụ Spring MVC, JDBC driver, Jackson. Chúng tạo ra khả năng kỹ thuật để một cấu hình hoạt động.
- **Starter**: dependency tiện dụng, gom các thư viện thường đi cùng một tính năng. Starter ảnh hưởng classpath theo cách gián tiếp; bản thân tên starter không phải một mệnh lệnh tạo bean.
- **Auto-configuration**: các lớp cấu hình của Spring Boot hoặc thư viện bên thứ ba, được phát hiện và xét điều kiện để đăng ký bean mặc định.
- **Thuộc tính và bean người dùng**: tín hiệu để bật/tắt/điều chỉnh nhánh cấu hình hoặc thay thế một phần mặc định bằng lựa chọn rõ ràng của ứng dụng.

Mục tiêu của bài là giải thích **sự kết hợp** của bốn nguồn thông tin trên trong quá trình lựa chọn cấu hình, rồi chứng minh bằng một ví dụ có thể chạy.

## 2. Cơ chế từ classpath đến bean thực tế

Ở ứng dụng dùng **@SpringBootApplication**, auto-configuration được bật thông qua **@EnableAutoConfiguration**. Spring Boot tìm các lớp auto-configuration ứng viên trong tệp **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** của các JAR liên quan (cơ chế áp dụng cho Spring Boot 3.x). Một ứng viên có thể mang điều kiện ở cấp lớp và ở từng phương thức **@Bean**.

Quá trình có thể hình dung như sau:

~~~text
Dependencies và starter
        |
        v
Runtime classpath: những class/thư viện thực sự có mặt
        |
        v
Phát hiện các auto-configuration ứng viên
        |
        v
Đánh giá điều kiện class / môi trường / property / bean
        |
        +-- Điều kiện không đạt --> Bỏ qua cấu hình hoặc bean tương ứng
        |
        +-- Điều kiện đạt -------> Đăng ký bean definition
                                      |
                                      v
                             Tạo và nối các bean theo dependency
~~~

Đây là sơ đồ khái niệm, không phải thứ tự thực thi tuyệt đối của từng điều kiện. Một lớp auto-configuration được xét đến **không đồng nghĩa** toàn bộ phương thức **@Bean** của nó đều được chọn. Cần phân biệt **đăng ký bean definition** với **khởi tạo instance**: annotation về thứ tự auto-configuration ảnh hưởng việc xử lý/đăng ký cấu hình, không tự quyết định thứ tự khởi tạo mọi instance.

Những điều kiện thường gặp:

| Điều kiện | Câu hỏi được kiểm tra | Hệ quả |
| --- | --- | --- |
| **@ConditionalOnClass** | Class bắt buộc có trên classpath không? | Thiếu class thì nhánh tương ứng không được chọn. |
| **@ConditionalOnMissingClass** | Class chỉ định có vắng mặt không? | Có thể chọn cấu hình thay thế khi thư viện không tồn tại. |
| **@ConditionalOnProperty** | Thuộc tính có giá trị phù hợp không? | Cho phép bật/tắt một nhánh cấu hình qua Environment. |
| **@ConditionalOnBean** | Đã có bean đúng kiểu hoặc tên theo điều kiện chưa? | Chỉ bật tính năng phụ thuộc vào bean đã có. |
| **@ConditionalOnMissingBean** | Chưa có bean phù hợp chưa? | Chỉ tạo mặc định khi ứng dụng chưa cung cấp lựa chọn riêng. |
| **@ConditionalOnWebApplication** | Ứng dụng có loại môi trường web yêu cầu không? | Phân nhánh cấu hình cho servlet/reactive khi thích hợp. |

Các điều kiện ở **cùng một nhánh** nhìn chung phải cùng thỏa mãn. Ví dụ, một phương thức tạo bean chỉ được đăng ký nếu class cần thiết tồn tại **và** property bật tính năng **và** chưa có bean cùng kiểu. Khi điều kiện đặt trên lớp cấu hình, toàn bộ nhóm bên trong có thể bị loại; điều kiện đặt trên một phương thức **@Bean** có thể chỉ loại phương thức đó.

### 2.1. Thư viện và starter thay đổi danh sách ứng viên khả thi

Khi thêm **spring-boot-starter-web** vào một ứng dụng Spring Boot 3.3, Maven/Gradle kéo theo các thư viện liên quan đến servlet web và Spring MVC. Các class vừa xuất hiện khiến nhiều điều kiện **@ConditionalOnClass** có khả năng đạt. Nếu ứng dụng thực sự thuộc loại servlet web, các điều kiện khác phù hợp và không có cấu hình người dùng ngăn cản, Spring Boot có thể cấu hình các thành phần MVC và web server tương ứng.

Nếu thêm **spring-boot-starter-jdbc**, class JDBC và Spring JDBC xuất hiện; Spring Boot có thêm cơ sở để cân nhắc cấu hình kết nối cơ sở dữ liệu. Nhưng cần URL/driver hay database nhúng thích hợp và các điều kiện còn lại. Có thư viện JDBC không phải bằng chứng rằng một DataSource dùng được đã tồn tại.

Một starter thường gom dependency, còn mã auto-configuration thường nằm trong các module auto-configure của Boot hoặc thư viện tương ứng. Không nên nhầm starter với một công tắc bất chấp mọi điều kiện. Đổi dependency có thể thay đổi **cả tập class lẫn loại ứng dụng suy ra từ classpath**. Chẳng hạn, khi cả Spring MVC và WebFlux cùng có trên classpath, Spring Boot thường chọn kiểu ứng dụng servlet mặc định; không thể suy rằng chỉ thêm WebFlux là toàn bộ ứng dụng tự chuyển sang reactive.

### 2.2. Property điều khiển lựa chọn và tinh chỉnh giá trị

Environment tổng hợp các nguồn thuộc tính như **application.properties**, **application.yml**, biến môi trường, tham số dòng lệnh và những nguồn khác. Một auto-configuration có thể dùng property theo hai cách khác nhau:

1. **Quyết định có tạo bean không**: ví dụ **@ConditionalOnProperty(prefix = "demo.greeting", name = "enabled", havingValue = "true", matchIfMissing = true)**.
2. **Chỉ thay đổi tham số của bean đã được chọn**: ví dụ **demo.greeting.prefix=Hello** thay đổi tiền tố câu chào mà không trực tiếp đổi điều kiện tạo bean.

Với **@ConditionalOnProperty**, giá trị mặc định của annotation khi không đặt **havingValue** là: property **tồn tại** và không bằng chuỗi **false** thì điều kiện đạt. Khi đặt **havingValue = "true"**, chỉ giá trị phù hợp **true** mới đạt; **matchIfMissing = true** cho phép đạt khi property hoàn toàn không có. Không tự suy rằng mọi property dạng **enabled** đều mặc định bật: phải đọc điều kiện thực tế của tính năng đó.

Khi xác định giá trị property cuối cùng, phải xét **nguồn và độ ưu tiên của property**. Một tham số dòng lệnh có thể thay đổi giá trị đọc từ application.properties. Đổi property cũng không thể cứu một cấu hình đã bị loại vì class bắt buộc vắng mặt hoặc vì các điều kiện khác không đạt.

### 2.3. Bean người dùng và cơ chế rút lui

Với các cấu hình mặc định được bảo vệ bằng **@ConditionalOnMissingBean**, khi ứng dụng tự cung cấp bean phù hợp, Spring Boot **không đăng ký bean mặc định của nhánh đó**. Đây là khả năng tùy biến quan trọng: thay đổi đúng bean cần thiết mà không phải loại bỏ toàn bộ auto-configuration.

Ví dụ khái niệm:

~~~java
@Bean
DataSource customDataSource() {
    // Trả về DataSource do ứng dụng quản lý.
    // Đoạn này minh họa cơ chế; chưa phải chương trình chạy độc lập.
    return obtainConfiguredDataSource();
}
~~~

Khi Spring Boot xét một bean DataSource mặc định mang **@ConditionalOnMissingBean(DataSource.class)**, bean tự khai báo phù hợp có thể khiến mặc định rút lui. Tuy nhiên, **không phải mọi bean do auto-configuration tạo đều có @ConditionalOnMissingBean** và điều kiện có thể xét **kiểu**, **tên**, hoặc phạm vi tìm kiếm trong cây ApplicationContext. Vì vậy hãy kiểm tra điều kiện cụ thể trước khi dự đoán kết quả.

Không đánh đồng các cơ chế sau:

- **@ConditionalOnMissingBean**: quyết định **có đăng ký bean mặc định** hay không.
- **@Primary**: ưu tiên một bean khi **nhiều bean cùng kiểu đã tồn tại** và cần inject một bean; nó không tự ngăn việc đăng ký bean khác.
- **@Qualifier**: chọn đúng bean tại điểm inject; không thay thế logic điều kiện auto-configuration.
- **Ghi đè bean theo cùng tên**: có thể gây lỗi xung đột bean definition; bật **spring.main.allow-bean-definition-overriding** chỉ để che một xung đột không phải cách tùy biến mặc định nên ưu tiên.

Vì điều kiện bean dựa trên những bean definition đã được xử lý đến thời điểm xét, việc đặt **@ConditionalOnBean** hoặc **@ConditionalOnMissingBean** tùy tiện trên một **@Configuration** thông thường có thể làm kết quả lệ thuộc thứ tự. Khi viết auto-configuration, các điều kiện đó được khuyến nghị đặt trong các lớp auto-configuration, vốn được xử lý sau bean definition do ứng dụng khai báo.

## 3. Bảng quyết định: bốn yếu tố phối hợp ra sao?

Xét một tính năng giả định **GreetingService** có bean mặc định khi class API hiện diện, property bật và chưa có bean người dùng:

| Class cần thiết | Property enabled | Bean người dùng | Kết quả |
| --- | --- | --- | --- |
| Có | Không khai báo; điều kiện cho phép mặc định | Không | Đăng ký bean GreetingService mặc định. |
| Có | true | Không | Đăng ký bean mặc định. |
| Có | false | Không | Không đăng ký bean mặc định. |
| Có | true | Có | Bean người dùng được giữ; mặc định rút lui. |
| Có | false | Có | Nhánh mặc định tắt; bean người dùng vẫn có thể tồn tại vì property đó chỉ ràng buộc nhánh mặc định. |
| Không | true | Không | Nhánh cần class bị bỏ qua. |

Bảng chỉ mô tả các điều kiện của ví dụ này, **không phải quy tắc cho mọi auto-configuration**. Nó cho thấy bốn tín hiệu không cạnh tranh theo một thứ tự ưu tiên tuyến tính; chúng cùng được đưa vào các biểu thức điều kiện. Nếu một điều kiện bắt buộc không đạt, nhánh đó không được chọn dù các điều kiện khác đạt.

## 4. Ví dụ chạy được: classpath + property + bean tùy biến

Ví dụ độc lập dưới đây dùng **Java 21, Maven và Spring Boot 3.3.13**. Dự án cố ý nhỏ: một API GreetingService, một auto-configuration được khai báo đúng cơ chế imports, một ứng dụng chạy, và một bean người dùng chỉ xuất hiện khi bật profile **custom**. Thư viện chính **spring-boot-starter** cung cấp Spring Boot core/autoconfigure; lớp API nằm ngay trong dự án, vì vậy **@ConditionalOnClass(GreetingService.class)** luôn đạt trong các lệnh chạy này. Khi phát triển thư viện thật, điều kiện kiểu class có ý nghĩa đặc biệt khi một API là dependency tùy chọn.

Cấu trúc dự án:

~~~text
auto-config-choice/
├── pom.xml
└── src/main/
    ├── java/dev/example/
    │   ├── api/GreetingService.java
    │   ├── autoconfig/GreetingAutoConfiguration.java
    │   └── app/
    │       ├── DemoApplication.java
    │       └── CustomGreetingConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

**Tệp pom.xml**

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
    <groupId>dev.example</groupId>
    <artifactId>auto-config-choice</artifactId>
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

**Tệp src/main/java/dev/example/api/GreetingService.java**

~~~java
package dev.example.api;

@FunctionalInterface
public interface GreetingService {
    String greet(String name);
}
~~~

**Tệp src/main/java/dev/example/autoconfig/GreetingAutoConfiguration.java**

~~~java
package dev.example.autoconfig;

import dev.example.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

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
    GreetingService greetingService(Environment environment) {
        String prefix = environment.getProperty(
            "demo.greeting.prefix", "Hello"
        );
        return name -> prefix + ", " + name;
    }
}
~~~

Ba điều kiện ở đây có vai trò khác nhau: **@ConditionalOnClass** xác nhận API trên classpath; **@ConditionalOnProperty** chọn có tạo bean mặc định hay không; **@ConditionalOnMissingBean** nhường quyền cho bean do ứng dụng khai báo. Thuộc tính **demo.greeting.prefix** chỉ thay đổi cách bean mặc định hoạt động.

**Tệp src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**

~~~text
dev.example.autoconfig.GreetingAutoConfiguration
~~~

Đây là đăng ký auto-configuration cho Spring Boot 3.x. Đừng bỏ tệp này: chỉ đặt **@AutoConfiguration** lên một lớp chưa đủ để lớp đó tự được phát hiện. Trong ví dụ, **dev.example.autoconfig** nằm ngoài vùng component scan mặc định của ứng dụng **dev.example.app**; lớp auto-configuration được import theo cơ chế trên, tránh phụ thuộc vào quét component.

**Tệp src/main/java/dev/example/app/DemoApplication.java**

~~~java
package dev.example.app;

import dev.example.api.GreetingService;
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
    ApplicationRunner showGreeting(
            ObjectProvider<GreetingService> services) {
        return args -> {
            GreetingService service = services.getIfAvailable();
            System.out.println(service == null
                ? "service=<none>"
                : "service=" + service.greet("Linh"));
        };
    }
}
~~~

Dùng **ObjectProvider** để kiểm tra trường hợp cố ý tắt bean mặc định mà không khiến ứng dụng lỗi vì thiếu dependency cần inject. Trong các tình huống chạy dưới đây chỉ có tối đa một GreetingService. Với nhiều bean cùng kiểu, **getIfAvailable()** có thể báo lỗi không phân giải được bean duy nhất; khi đó cần quy tắc chọn bean phù hợp.

**Tệp src/main/java/dev/example/app/CustomGreetingConfiguration.java**

~~~java
package dev.example.app;

import dev.example.api.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class CustomGreetingConfiguration {

    @Bean
    GreetingService customGreetingService() {
        return name -> "Xin chào, " + name;
    }
}
~~~

Chỉ khi profile **custom** được kích hoạt, ứng dụng khai báo bean GreetingService riêng. Lúc đó nhánh mặc định trong GreetingAutoConfiguration không đạt **@ConditionalOnMissingBean(GreetingService.class)**.

**Tệp src/main/resources/application.properties**

~~~properties
spring.main.banner-mode=off
logging.level.root=OFF
~~~

Hai dòng này giúp stdout của bài tập rõ ràng; chúng không phải điều kiện của GreetingService. Khi muốn xem log chẩn đoán, hãy tạm bỏ **logging.level.root=OFF**.

### 4.1. Build và quan sát bốn trường hợp

Yêu cầu: **JDK 21**, **Maven 3.9+**, có khả năng tải dependency từ Maven Central. Mở terminal tại thư mục **auto-config-choice**:

~~~bash
mvn -q -DskipTests package
~~~

Chạy mặc định, chưa khai báo **demo.greeting.enabled** và chưa bật profile custom:

~~~bash
java -jar target/auto-config-choice-0.0.1-SNAPSHOT.jar
~~~

Dòng stdout do chương trình in ra:

~~~text
service=Hello, Linh
~~~

Lý do: class GreetingService có trên classpath, **matchIfMissing=true** cho phép property enabled vắng mặt, chưa có bean người dùng. Auto-configuration đăng ký bean mặc định.

Đổi **thuộc tính cấu hình giá trị**, vẫn giữ bean mặc định:

~~~bash
java -jar target/auto-config-choice-0.0.1-SNAPSHOT.jar --demo.greeting.prefix=Hi
~~~

Dòng stdout:

~~~text
service=Hi, Linh
~~~

Lý do: tham số dòng lệnh cung cấp tiền tố mới cho **Environment**. Các điều kiện chọn bean không đổi.

**Tắt nhánh tạo bean mặc định**:

~~~bash
java -jar target/auto-config-choice-0.0.1-SNAPSHOT.jar --demo.greeting.enabled=false
~~~

Dòng stdout:

~~~text
service=<none>
~~~

Lý do: property không đạt **havingValue=true**; không có bean tự khai báo trong profile mặc định.

**Bật bean người dùng**:

~~~bash
java -jar target/auto-config-choice-0.0.1-SNAPSHOT.jar --spring.profiles.active=custom
~~~

Dòng stdout:

~~~text
service=Xin chào, Linh
~~~

Lý do: **CustomGreetingConfiguration** được nạp, đăng ký GreetingService; **@ConditionalOnMissingBean** không đạt nên bean mặc định rút lui. Nếu chạy đồng thời **--spring.profiles.active=custom** và **--demo.greeting.enabled=false**, vẫn có kết quả của bean người dùng: property chỉ hạn chế nhánh mặc định, không tự tắt cấu hình người dùng.

Không thể mô phỏng việc thiếu class GreetingService chỉ bằng cách xóa một dependency trong dự án ví dụ, vì chính source của ứng dụng và auto-configuration đang tham chiếu API đó khi biên dịch. Trong thư viện độc lập, **@ConditionalOnClass** phát huy ý nghĩa khi ứng dụng tiêu thụ có thể có hoặc không có dependency tùy chọn.

### 4.2. Nếu muốn nhìn cả starter và classpath thay đổi

Ví dụ dùng **spring-boot-starter** cố định để cô lập hiệu ứng property/bean. Trong dự án thật, có thể so sánh cây dependency trước và sau khi thêm một starter:

~~~bash
mvn dependency:tree
~~~

Khi thay đổi dependency, kiểm tra class nào được kéo vào runtime classpath và condition nào trở thành khả thi. **Không suy trực tiếp** rằng tất cả tính năng của starter đã được khởi tạo; kết luận cần dựa trên condition report và bean thực tế.

## 5. Chẩn đoán: tại sao Spring Boot chọn hoặc bỏ qua cấu hình?

Khi ứng dụng chạy nhưng bean kỳ vọng không tồn tại, hãy kiểm tra theo thứ tự:

1. **Classpath**: dependency có nằm trong runtime classpath không? Có bị exclude, nhầm scope, xung đột phiên bản hay thiếu driver không? Dùng cây dependency để xác nhận.
2. **Đã bật auto-configuration chưa?** Ứng dụng có **@SpringBootApplication** hoặc **@EnableAutoConfiguration**? Lớp auto-configuration tùy biến có nằm trong tệp imports đúng tên không?
3. **Điều kiện ở cấp lớp**: thiếu class, sai kiểu ứng dụng web, chưa có resource hay property cần thiết?
4. **Điều kiện ở cấp phương thức @Bean**: có bean người dùng cùng kiểu/tên làm **@ConditionalOnMissingBean** không đạt? Còn một điều kiện khác cản trở không?
5. **Giá trị Environment cuối cùng**: property thật sự là gì sau khi áp dụng profile, biến môi trường, config import và tham số dòng lệnh?
6. **Bean đã đăng ký hay lỗi lúc khởi tạo?** Hai trường hợp khác nhau. Điều kiện đạt không đảm bảo mọi bước kết nối tài nguyên, binding hay khởi tạo đều thành công.

Trong một ứng dụng thông thường, khởi động với **--debug** để bật báo cáo đánh giá điều kiện trong log:

~~~bash
java -jar target/auto-config-choice-0.0.1-SNAPSHOT.jar --debug
~~~

**Lưu ý với ví dụ trên**: hãy xóa/tạm tắt **logging.level.root=OFF** để thấy log chẩn đoán. Condition evaluation report phân nhóm **positive matches** (điều kiện đạt), **negative matches** (điều kiện không đạt), và thông tin những cấu hình không đặt condition. Tìm tên lớp **GreetingAutoConfiguration** và phương thức tạo bean để thấy lý do cụ thể.

Nếu ứng dụng dùng **spring-boot-starter-actuator** và có HTTP endpoint được cấu hình/phơi bày phù hợp, **/actuator/conditions** cho phép đọc báo cáo dạng JSON. Endpoint này không tự mở công khai chỉ vì đã thêm Actuator: cần quan tâm cấu hình exposure và bảo mật. Đây là công cụ kiểm chứng, không phải lý do để mở endpoint nhạy cảm tùy tiện trên môi trường công khai.

### 5.1. Lỗi suy luận thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “Đã thêm starter nên chắc chắn có bean X.” | Starter cung cấp dependency; bean còn tùy các điều kiện và khả năng khởi tạo. |
| “Đặt property=true chắc chắn bật mọi thứ.” | Property chỉ tác động đúng các condition và binding đọc nó; thiếu class hay bean cần thiết vẫn có thể chặn. |
| “Đặt property=false sẽ xóa cả bean do ứng dụng tự tạo.” | Thường property chỉ loại nhánh auto-configuration gắn condition ấy; bean tự khai báo có vòng đời riêng. |
| “Có bean cùng kiểu thì Boot luôn rút lui.” | Chỉ rút lui ở nhánh có condition thích hợp, thường là **@ConditionalOnMissingBean**. |
| “Đánh dấu @Primary là đã tắt bean mặc định.” | @Primary giải quyết ưu tiên inject, không phải cơ chế chặn đăng ký. |
| “Ứng dụng đã start nghĩa là mọi auto-configuration đều match.” | Nhiều nhánh bị loại là bình thường; condition report giải thích từng nhánh. |
| “Auto-configuration được chọn thì thứ tự tạo bean phải giống thứ tự file imports.” | Thứ tự đăng ký và thứ tự khởi tạo là hai vấn đề; dependency giữa các bean ảnh hưởng thứ tự khởi tạo. |
| “Lớp @AutoConfiguration tự động được quét ở bất kỳ package nào.” | Với Spring Boot 3.x, auto-configuration tùy biến cần được đăng ký trong file imports và tránh quét component thông thường. |

## 6. Tình huống thực hành để tự kiểm tra hiểu biết

**Tình huống A.** Thư viện cần thiết đã có, property bật, không có bean người dùng, nhưng một bean vẫn vắng mặt. Hãy kiểm tra cả điều kiện **@ConditionalOnWebApplication**, **@ConditionalOnBean**, tên bean và report: ba tín hiệu đầu không bảo đảm nhánh cuối cùng đạt.

**Tình huống B.** Ứng dụng tự tạo một bean cùng kiểu, rồi bật thêm property của cấu hình mặc định. Nếu method mặc định có **@ConditionalOnMissingBean** theo kiểu đó, bean mặc định vẫn không được tạo; property bật không vượt qua điều kiện còn thiếu.

**Tình huống C.** Sau khi thêm một starter, ứng dụng đổi hành vi dù mã nguồn nghiệp vụ không thay đổi. Hãy so sánh **dependency tree**, classpath thực tế, **positive/negative matches**, property cuối cùng và tập bean. Đó là cách xác định sự thay đổi đến từ thư viện kéo theo hay điều kiện khác.

**Tự kiểm tra nhanh:**

1. Trong ví dụ chạy được, thay **demo.greeting.prefix=Bonjour** nhưng giữ **demo.greeting.enabled=false**, kết quả gì? **service=<none>**, vì đổi giá trị tiền tố không tạo lại bean bị loại.
2. Bật profile **custom**, đồng thời đặt **demo.greeting.prefix=Bonjour**, kết quả gì? **service=Xin chào, Linh**, vì bean người dùng không đọc property prefix của nhánh mặc định.
3. Tại sao **@ConditionalOnMissingBean** không tương đương **@Primary**? Một cái quyết định đăng ký bean; cái còn lại giúp lựa chọn giữa những bean đã tồn tại.

## 7. Ghi nhớ khi thiết kế và vận hành

Đối với mỗi bean có vẻ “được Spring Boot tự tạo”, hãy đặt câu hỏi theo chuỗi: **(1) class nào trên classpath? (2) auto-configuration ứng viên nào có thể được xét? (3) property/loại ứng dụng/bean hiện có thỏa các condition không? (4) bean definition nào được đăng ký? (5) khởi tạo thành công không?** Cách đọc này giải thích vì sao thêm dependency, đổi starter, sửa property hoặc khai báo bean đều có thể thay đổi cấu hình cuối cùng.

Ưu tiên dùng property được framework công bố để tinh chỉnh hành vi; khai báo bean riêng khi cần thay đổi cách xây dựng bean; chỉ exclude hẳn auto-configuration khi thực sự muốn loại cả nhánh và hiểu các bean liên quan. Với thư viện tự viết, đặt điều kiện class tại cấp cấu hình hợp lý, đặt điều kiện thiếu bean để cho phép người dùng tùy biến, và đăng ký auto-configuration bằng file imports của Spring Boot 3.x.

### Tài liệu đối chiếu

- Spring Boot, *Auto-configuration*: https://docs.spring.io/spring-boot/reference/using/auto-configuration.html
- Spring Boot, *Creating Your Own Auto-configuration*: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot 3.3, *Conditions Evaluation Report*: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
