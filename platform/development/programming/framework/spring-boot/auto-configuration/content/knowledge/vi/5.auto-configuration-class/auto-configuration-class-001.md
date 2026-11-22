# @AutoConfiguration và mối quan hệ với @Configuration

> **Module:** Spring Boot — auto-configuration, nhóm “Lớp tự cấu hình”. Bài giải thích bản chất Spring configuration của `@AutoConfiguration`, cách Spring Boot tìm và kích hoạt nó, những điểm khác với `@Configuration` thông thường, điều kiện tạo bean, thứ tự xử lý, `proxyBeanMethods=false` và cách tự viết/kiểm thử một auto-configuration. Ví dụ dùng Java 17, Spring Boot 3.5.7 và Maven.

## 1. Câu trả lời cốt lõi

**`@AutoConfiguration` là một annotation chuyên biệt của Spring Boot, được meta-annotate bằng `@Configuration(proxyBeanMethods = false)`.** Do đó, một class `@AutoConfiguration` cũng là một **configuration class của Spring**: nó có thể khai báo `@Bean`, chứa configuration lồng nhau, dùng `@Import` và gắn `@Conditional`.

Điểm khác biệt không nằm ở khả năng viết `@Bean`. Nó nằm ở **vai trò** và **con đường được nạp**:

- `@Configuration` thông thường biểu diễn cấu hình mà ứng dụng hoặc một thư viện **chủ động đưa vào context** qua component scan, `@Import` hoặc đăng ký trực tiếp.
- `@AutoConfiguration` biểu diễn cấu hình **mặc định có thể tự được áp dụng** khi ứng dụng bật `@EnableAutoConfiguration` (thường thông qua `@SpringBootApplication`), class được **liệt kê trong file imports** và các điều kiện phù hợp.
- Auto-configuration được thiết kế để **nhường chỗ cho cấu hình người dùng**, thường bằng `@ConditionalOnMissingBean`, và để chỉ kích hoạt khi classpath/property/context thích hợp.
- Spring Boot yêu cầu auto-configuration có cấu trúc và metadata nạp ứng viên riêng; chỉ gắn `@AutoConfiguration` lên class **không đủ** để nó tự xuất hiện trong ứng dụng khác.

Một nguyên tắc cần nhớ: **mỗi auto-configuration đều là configuration, nhưng không phải configuration nào cũng là auto-configuration**.

## 2. Quan hệ annotation: meta-annotation và ý nghĩa

Trong Spring Boot 3.5, khai báo của `@AutoConfiguration` có dạng khái niệm:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Configuration(proxyBeanMethods = false)
@AutoConfigureBefore
@AutoConfigureAfter
public @interface AutoConfiguration {
    // value, before, beforeName, after, afterName
}
```

Đây là **trích yếu cấu trúc annotation để giải thích**, không phải mã source tự biên dịch độc lập vì đã lược bỏ import, khai báo các phần tử và phần triển khai của thư viện.

- `@Configuration(proxyBeanMethods = false)` khiến class đánh dấu `@AutoConfiguration` trở thành configuration class được Spring xử lý; đồng thời cấu hình mặc định **không dùng proxy CGLIB để chặn lời gọi giữa các `@Bean` method**.
- `@AutoConfigureBefore`/`@AutoConfigureAfter` cung cấp metadata về thứ tự áp dụng auto-configuration.
- Các thuộc tính `before`/`after` tham chiếu class cấu hình khác; `beforeName`/`afterName` nhận tên class dạng chuỗi khi muốn tránh phụ thuộc trực tiếp vào kiểu có thể không tồn tại.
- `value` là alias của tên bean configuration từ `@Configuration`. Đây không phải tên file imports hoặc tên bean được tạo bởi từng method.

Bản chất meta-annotation có ý nghĩa thực tế: code xử lý `@Configuration` của Spring vẫn hiểu class `@AutoConfiguration`. Spring Boot bổ sung **quy trình chọn ứng viên, loại trừ, điều kiện và ordering**, chứ không phát minh một container khác để lưu bean.

### Nhận diện ba annotation thường nhầm

| Annotation | Ai cung cấp? | Vai trò | Tự đăng ký được bean của thư viện chỉ nhờ đánh dấu class? |
| --- | --- | --- | --- |
| `@Configuration` | Spring Framework | Khai báo class chứa bean definitions, import và cấu hình context | Không. Class vẫn cần được component scan, import hoặc đăng ký. |
| `@AutoConfiguration` | Spring Boot | Đánh dấu configuration có thể được Boot tự động áp dụng, có metadata thứ tự và convention | Không. Với auto-discovery chuẩn của Boot 3.x cần có tên class trong `AutoConfiguration.imports`. |
| `@EnableAutoConfiguration` | Spring Boot | Kích hoạt cơ chế chọn và nhập auto-configuration trong ứng dụng | Đây là annotation **bật hệ thống chọn ứng viên**, không phải annotation dành cho từng class auto-configuration. |

`@SpringBootApplication` bao gồm `@EnableAutoConfiguration`, `@ComponentScan` và `@SpringBootConfiguration`. Vì vậy một ứng dụng Spring Boot chuẩn vừa có thể quét component của ứng dụng, vừa nhập các auto-configuration trong dependency.

## 3. Cùng khai báo @Bean, khác cách đi vào ApplicationContext

### 3.1. `@Configuration` thông thường

```java
package com.example.app;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ApplicationSettings {

    @Bean
    public String applicationLabel() {
        return "my-app";
    }
}
```

Nếu class nằm trong phạm vi `@ComponentScan` của ứng dụng, Spring sẽ đăng ký class cấu hình và bean `applicationLabel`. Nó cũng có thể được đưa vào bằng `@Import(ApplicationSettings.class)` hoặc làm nguồn cấu hình của `AnnotationConfigApplicationContext`.

Nếu class nằm ngoài phạm vi scan, không được import và không được đăng ký bằng cách khác, **Spring không tự biết đến class đó** chỉ vì có `@Configuration`.

### 3.2. `@AutoConfiguration`

```java
package com.example.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class GreetingAutoConfiguration {

    @Bean
    public String greetingLabel() {
        return "default-greeting";
    }
}
```

Đây là một configuration class hợp lệ, nhưng **để được Boot tự tìm thấy theo cơ chế auto-configuration** nó phải được liệt kê trong tài nguyên:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung:

```text
com.example.autoconfigure.GreetingAutoConfiguration
```

Không cần chuyển `com.example.autoconfigure` vào `@ComponentScan`. Thực tế, tài liệu Spring Boot hướng dẫn giữ auto-configuration ở **package riêng, ngoài component scan**, đồng thời tránh cho auto-configuration tự bật component scan quét class khác.

Ví dụ trên giúp thấy cách khai báo tối thiểu; để phát hành một auto-configuration hữu ích, thường cần các condition để không áp đặt bean mặc định. Mục 6 sẽ viết bản có điều kiện và ví dụ chạy được.

### 3.3. Đừng nhầm `@Import` của Spring với file `AutoConfiguration.imports`

- `@Import(SomeConfiguration.class)`: một cấu hình **chủ động nhập** class được chỉ rõ; áp dụng cho cấu hình Spring nói chung.
- `AutoConfiguration.imports`: **resource text** trong JAR liệt kê các class mà Boot sẽ xét làm auto-configuration khi cơ chế `@EnableAutoConfiguration` hoạt động.
- Java `import com.example.X;`: chỉ làm tên kiểu trong source Java ngắn lại; nó **không phải** cơ chế đăng ký Spring bean.

## 4. Vòng đời từ class đến bean: năm chặng khác nhau

```text
@SpringBootApplication
  |
  +-- @ComponentScan
  |      \-- tìm @Configuration / @Component của ứng dụng theo package
  |
  \-- @EnableAutoConfiguration
         \-- AutoConfigurationImportSelector
              \-- ImportCandidates tìm các ...AutoConfiguration.imports
                   \-- lấy danh sách tên class ứng viên trên classpath
                        \-- loại trừ và lọc metadata/điều kiện
                             \-- xử lý các class @AutoConfiguration
                                  \-- đánh giá điều kiện ở class và @Bean
                                       \-- đăng ký bean definition phù hợp
                                            \-- tạo instance theo dependency
```

Cần tách các mức sau:

1. **Có class trên classpath:** file `.class` hiện diện nhưng chưa chắc đã là ứng viên Spring.
2. **Có tên trong imports:** Spring Boot biết đến class như một ứng viên auto-configuration.
3. **Được xét áp dụng:** class không bị loại trừ và các điều kiện liên quan được đánh giá.
4. **Bean definition được đăng ký:** từng `@Bean` đủ điều kiện mới đóng góp bean definition.
5. **Bean instance được tạo:** Spring khởi tạo theo lifecycle và quan hệ dependency, thường khi context refresh (với singleton không lazy).

Không thể suy luận “có `@AutoConfiguration`” là “bean của nó luôn tồn tại”. Ngay cả một class được nhập thành công vẫn có thể có **0 bean nghiệp vụ được tạo** vì `@ConditionalOnMissingBean` hoặc điều kiện property/classpath không khớp.

Spring Boot có thể dùng metadata để loại các cấu hình không phù hợp sớm, nhưng việc chi tiết nào được xét ở bước nào là đặc điểm triển khai; nguyên lý cần nắm là **candidate ≠ configuration được áp dụng ≠ bean đã đăng ký**.

## 5. Vì sao auto-configuration thường phải có điều kiện?

Nếu một thư viện tạo bean mặc định vô điều kiện, ứng dụng có thể gặp lỗi nhiều bean cùng kiểu hoặc bị cấu hình ngoài ý muốn. Các annotation condition cho phép Spring Boot cung cấp mặc định hữu ích, đồng thời để người dùng tự cấu hình.

| Condition | Đặt ở đâu? | Ý nghĩa chính |
| --- | --- | --- |
| `@ConditionalOnClass(SomeApi.class)` | Thường cấp class/configuration lồng nhau | Chỉ áp dụng khi API/thư viện có trên classpath. |
| `@ConditionalOnMissingClass("...")` | Thường cấp class | Chỉ áp dụng khi class không có. |
| `@ConditionalOnBean(SomeType.class)` | Class hoặc method | Chỉ có hiệu lực khi một bean tương ứng đã được đăng ký và hiển thị cho điều kiện. |
| `@ConditionalOnMissingBean(SomeType.class)` | Thường cấp `@Bean` | **Back-off**: chỉ tạo bean mặc định nếu chưa có bean phù hợp. |
| `@ConditionalOnProperty(prefix = ..., name = ...)` | Class hoặc method | Chọn theo property trong `Environment`. |
| `@ConditionalOnWebApplication` | Class/configuration con | Chỉ áp dụng cho môi trường web phù hợp. |

Điều kiện có thể dùng trên cấu hình `@Configuration` thông thường; chúng **không độc quyền** của `@AutoConfiguration`. Tuy vậy, `@ConditionalOnBean` và `@ConditionalOnMissingBean` nhìn vào những bean definition **đã được xử lý tại thời điểm đánh giá**. Spring Boot đảm bảo auto-configuration được xử lý sau các định nghĩa cấu hình người dùng theo luồng chuẩn, nên loại điều kiện này **phù hợp nhất trong auto-configuration**.

**Back-off không phải một thao tác xóa bean.** Khi điều kiện `@ConditionalOnMissingBean` không khớp, Spring Boot **không đăng ký bean mặc định** từ method đó. Nếu người dùng đăng ký bean tương ứng, bean do người dùng vẫn còn nguyên.

### Điều kiện ở class khác điều kiện ở method

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.Client")
class VendorAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(name = "vendorAdapter")
    Object vendorAdapter() {
        return new Object();
    }
}
```

Đây là **đoạn minh họa**; thiếu import và class chưa được đăng ký trong imports. `@ConditionalOnClass` ở cấp class nếu không khớp sẽ ngăn cả cấu hình đó. Nếu cấp class khớp nhưng đã có bean tên `vendorAdapter`, chỉ method bean có điều kiện tương ứng nhường chỗ.

**Cẩn trọng với class không có trên classpath:** Một `@Bean` method có chữ ký trả về kiểu SDK tùy chọn có thể khiến JVM tải kiểu quá sớm. Khi phụ thuộc vào một API có thể vắng mặt, tách method sang nested `@Configuration(proxyBeanMethods=false)` được bảo vệ bởi `@ConditionalOnClass` ở cấp class.

## 6. Ví dụ đầy đủ: @AutoConfiguration cung cấp mặc định, @Configuration của ứng dụng thay thế

Bài thực hành dùng một interface `GreetingService`. Auto-configuration ở package ngoài root ứng dụng cung cấp bean mặc định, còn `@Configuration` của ứng dụng cung cấp bean riêng khi profile `custom` được bật.

### 6.1. Cấu trúc source

```text
configuration-relationship/
├── pom.xml
└── src
    ├── main
    │   ├── java/com/example
    │   │   ├── api/GreetingService.java
    │   │   ├── autoconfigure/GreetingAutoConfiguration.java
    │   │   ├── app/DemoApplication.java
    │   │   ├── app/UserGreetingConfiguration.java
    │   │   └── external/ExternalConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test
        └── java/com/example/testing
            ├── GreetingAutoConfigurationTest.java
            └── ApplicationWiringTest.java
```

Nhớ rằng `com.example.app`, `com.example.autoconfigure`, `com.example.api` và `com.example.external` là **các nhánh package khác nhau**.

### 6.2. Maven POM

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>configuration-relationship</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Ví dụ không cần web server. File imports được đặt trong cùng artifact để dễ học; khi phát triển starter dùng chung, bạn thường đóng gói auto-configuration vào module/JAR thư viện riêng.

### 6.3. Contract của thư viện

File `src/main/java/com/example/api/GreetingService.java`:

```java
package com.example.api;

@FunctionalInterface
public interface GreetingService {
    String greet();
}
```

### 6.4. Auto-configuration và bean mặc định

File `src/main/java/com/example/autoconfigure/GreetingAutoConfiguration.java`:

```java
package com.example.autoconfigure;

import com.example.api.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService defaultGreetingService() {
        return () -> "from-auto";
    }
}
```

Ở đây:

- `@AutoConfiguration` biến class thành configuration theo semantics của Spring và cung cấp metadata auto-configuration của Boot.
- `@ConditionalOnClass` thể hiện classpath condition; trong project mẫu, `GreetingService` luôn tồn tại nên điều kiện khớp.
- `@ConditionalOnProperty` cho phép tắt phần mặc định qua `demo.greeting.enabled=false`. Vì `matchIfMissing=true`, không khai báo property vẫn cho phép mặc định.
- `@ConditionalOnMissingBean(GreetingService.class)` tạo bean `defaultGreetingService` **chỉ khi chưa có bean kiểu `GreetingService`** từ ứng dụng hay nguồn phù hợp khác.
- Method khai báo kiểu trả về là `GreetingService`, đủ để condition kiểm tra đúng kiểu trong ví dụ. Trong tích hợp thực tế cần cân nhắc khai báo kiểu trả về cụ thể nhất có thể để metadata bean rõ ràng.

File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

```text
com.example.autoconfigure.GreetingAutoConfiguration
```

Khi chạy Spring Boot, file này là phần **bắt buộc cho discovery chuẩn**. Nếu xóa nó khỏi artifact, chỉ giữ annotation `@AutoConfiguration`, class ở package ngoài scan sẽ không tự được phát hiện.

### 6.5. Configuration do ứng dụng sở hữu

File `src/main/java/com/example/app/UserGreetingConfiguration.java`:

```java
package com.example.app;

import com.example.api.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("custom")
public class UserGreetingConfiguration {

    @Bean
    public GreetingService customGreetingService() {
        return () -> "from-user";
    }
}
```

Đây là `@Configuration` thông thường, được `@ComponentScan` tìm vì nằm trong `com.example.app`. Không có profile `custom`, class không được áp dụng. Khi bật profile, bean `customGreetingService` được khai báo **trước auto-configuration**, nên condition `@ConditionalOnMissingBean(GreetingService.class)` trên mặc định không khớp và back off.

Điểm khác nhau không phải bean của ứng dụng có tên giống bean mặc định: chúng có tên `customGreetingService` và `defaultGreetingService` khác nhau. Điều kiện ở đây xét theo **kiểu** `GreetingService`.

### 6.6. Một @Configuration nằm ngoài scan

File `src/main/java/com/example/external/ExternalConfiguration.java`:

```java
package com.example.external;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class ExternalConfiguration {

    @Bean
    public String externalMarker() {
        return "external-config";
    }
}
```

Class này có `@Configuration` nhưng thuộc `com.example.external`, ngoài cây scan từ `com.example.app`. Nó cũng không xuất hiện trong `AutoConfiguration.imports`. Vì vậy, bean `externalMarker` **không xuất hiện** trong context của ứng dụng mẫu. Có thể nạp class bằng `@Import(ExternalConfiguration.class)` nếu thực sự muốn, nhưng chỉ đặt nó trên classpath thì chưa đủ.

### 6.7. Ứng dụng chính và đầu ra

File `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.api.GreetingService;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(DemoApplication.class, args)) {

            Map<String, GreetingService> services =
                context.getBeansOfType(GreetingService.class);

            String message = services.isEmpty()
                ? "none"
                : services.values().iterator().next().greet();

            System.out.println("service.count=" + services.size());
            System.out.println("service.message=" + message);
            System.out.println(
                "default.exists=" + context.containsBean("defaultGreetingService")
            );
            System.out.println(
                "external.exists=" + context.containsBean("externalMarker")
            );
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml` với JDK 17 và Maven:

```bash
mvn -q spring-boot:run
```

Bốn dòng do chương trình in ra (không tính log startup của Spring Boot):

```text
service.count=1
service.message=from-auto
default.exists=true
external.exists=false
```

Giải thích: `@ComponentScan` tìm `UserGreetingConfiguration` nhưng profile `custom` không khớp; `GreetingAutoConfiguration` ở package ngoài scan vẫn được nạp qua file imports và tạo bean mặc định. `ExternalConfiguration` không được nạp theo đường nào.

### 6.8. Bật cấu hình người dùng để quan sát back-off

Chạy:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--spring.profiles.active=custom
```

Kết quả từ các dòng của chương trình:

```text
service.count=1
service.message=from-user
default.exists=false
external.exists=false
```

Profile `custom` khiến class `UserGreetingConfiguration` đóng góp bean vào context. Auto-configuration vẫn là ứng viên, nhưng method mặc định **không đăng ký bean** vì `@ConditionalOnMissingBean` thấy `GreetingService` đã có.

### 6.9. Tắt phần mặc định bằng property

Không bật profile custom; chạy:

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.greeting.enabled=false
```

Các dòng ứng dụng in:

```text
service.count=0
service.message=none
default.exists=false
external.exists=false
```

Đây là nhánh class-level `@ConditionalOnProperty` **không khớp**, khác với nhánh back-off khi người dùng khai báo bean. Nếu vừa bật profile custom vừa tắt default, bean của người dùng vẫn tồn tại: property thuộc về auto-configuration, không có tác dụng xóa configuration người dùng.

## 7. proxyBeanMethods=false: quan hệ thật với @Configuration

Spring Framework cho phép cấu hình `@Configuration(proxyBeanMethods = true)` (mặc định của `@Configuration`). Trong chế độ này, class có thể được Spring nâng cấp qua CGLIB để các lời gọi giữa các `@Bean` method được chặn, trả về bean do container quản lý theo semantics của method.

Ví dụ khái niệm khi `proxyBeanMethods=true`:

```java
@Configuration(proxyBeanMethods = true)
class FullModeConfig {
    @Bean
    Helper helper() {
        return new Helper();
    }

    @Bean
    Worker worker() {
        return new Worker(helper());
    }
}
```

**Đây là fragment minh họa, không phải file Java tự biên dịch** vì chưa định nghĩa `Helper`, `Worker` hoặc import annotation. Nếu `helper` là singleton, lời gọi `helper()` trong `worker()` được proxy xử lý để lấy bean singleton quản lý bởi Spring.

Với `@Configuration(proxyBeanMethods = false)`, Spring **không chặn lời gọi trực tiếp** đến `helper()` theo cách đó. Lời gọi Java bình thường có thể tạo một instance mới, ngoài bean singleton đã đăng ký. Vì vậy mẫu thiết kế tương thích với false là **inject dependency làm tham số `@Bean` method**:

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {
    @Bean
    Helper helper() {
        return new Helper();
    }

    @Bean
    Worker worker(Helper helper) {
        return new Worker(helper);
    }
}
```

Đây cũng là fragment dùng các lớp minh họa `Helper` và `Worker`. Spring giải quyết tham số `Helper helper` từ context, thay vì code gọi trực tiếp method `helper()`.

**`@AutoConfiguration` có `proxyBeanMethods=false` theo định nghĩa annotation.** Bởi vậy, khi thiết kế auto-configuration, đừng viết mã dựa vào interception giữa các method `@Bean`. Dùng dependency injection qua tham số/constructor sẽ đơn giản hơn, tránh instance thừa và làm rõ graph phụ thuộc.

Một số điểm cần nhớ:

- `proxyBeanMethods=false` **không có nghĩa** Spring vô hiệu singleton scope. Bean do container quản lý vẫn tuân theo scope của nó; chỉ lời gọi trực tiếp `@Bean` method từ Java không được proxy chặn như full configuration mode.
- Nó khác với proxy tạo ra do `@Transactional`, AOP hoặc Spring Security; những proxy đó phục vụ semantics khác.
- `@Configuration(proxyBeanMethods=false)` vẫn là configuration class hợp lệ, không trở thành class thường.
- Với auto-configuration có nhiều bean phụ thuộc nhau, truyền tham số method là lựa chọn an toàn và dễ kiểm thử.

## 8. @AutoConfiguration và quy tắc thứ tự xử lý

Auto-configuration thường cần xét sau một auto-configuration khác, ví dụ cấu hình metrics phụ thuộc vào một client đã được đăng ký. Spring Boot hỗ trợ:

```java
@AutoConfiguration(after = ClientAutoConfiguration.class)
public class MetricsAutoConfiguration {
    // ...
}
```

Đây là **fragment minh họa**; `ClientAutoConfiguration` là tên đại diện và chưa có import. Nếu không muốn phụ thuộc trực tiếp vào class khác, có thể dùng:

```java
@AutoConfiguration(
    afterName = "com.vendor.client.ClientAutoConfiguration"
)
public class MetricsAutoConfiguration {
    // ...
}
```

Với `before`/`beforeName` thì ngược lại; sử dụng các cơ chế dedicated như `@AutoConfigureBefore`, `@AutoConfigureAfter` hoặc `@AutoConfigureOrder` khi phù hợp.

**Ordering auto-configuration chỉ điều khiển thứ tự xử lý cấu hình/đăng ký bean definition.** Nó không quyết định thứ tự khởi tạo instance bean sau đó; thứ tự tạo bean dựa trên dependency, scope và `@DependsOn`.

Các điều kiện `@ConditionalOnBean`/`@ConditionalOnMissingBean` dựa trên bean đã được xử lý nên thứ tự auto-configuration có thể ảnh hưởng kết quả condition nếu nhiều cấu hình mặc định đóng góp những bean liên quan. Vì vậy, cần xác định rõ dependency giữa các auto-configuration nếu thực sự có quan hệ.

Không dùng thứ tự dòng trong `AutoConfiguration.imports` như hợp đồng quyết định thứ tự runtime của bean.

## 9. Kiểm thử auto-configuration đúng ngữ cảnh

Trước tiên viết test riêng cho auto-configuration thay vì khởi động toàn bộ ứng dụng. `ApplicationContextRunner` tạo các context nhỏ với tập cấu hình được chỉ định, rất phù hợp để thử nhánh mặc định, nhánh back-off và nhánh property.

File `src/test/java/com/example/testing/GreetingAutoConfigurationTest.java`:

```java
package com.example.testing;

import com.example.api.GreetingService;
import com.example.autoconfigure.GreetingAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner().withConfiguration(
            AutoConfigurations.of(GreetingAutoConfiguration.class)
        );

    @Test
    void createsDefaultWhenUserBeanMissing() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasBean("defaultGreetingService");
            assertThat(context.getBean(GreetingService.class).greet())
                .isEqualTo("from-auto");
        });
    }

    @Test
    void backsOffWhenUserBeanExists() {
        runner.withUserConfiguration(UserProvidedConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context).doesNotHaveBean("defaultGreetingService");
                assertThat(context.getBean(GreetingService.class).greet())
                    .isEqualTo("from-user-test");
            });
    }

    @Test
    void propertyCanDisableAutoConfiguration() {
        runner.withPropertyValues("demo.greeting.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(GreetingService.class);
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserProvidedConfiguration {
        @Bean
        GreetingService userGreetingService() {
            return () -> "from-user-test";
        }
    }
}
```

Class test nằm trong `com.example.testing`, **ngoài package scan của ứng dụng `com.example.app`**. Nested `UserProvidedConfiguration` chỉ được `ApplicationContextRunner` đưa vào ở test thứ hai, tránh tình huống test configuration vô tình bị component scan khi khởi động ứng dụng thật.

Thêm test tích hợp để kiểm chứng đường nạp imports và phạm vi scan.

File `src/test/java/com/example/testing/ApplicationWiringTest.java`:

```java
package com.example.testing;

import com.example.api.GreetingService;
import com.example.app.DemoApplication;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = DemoApplication.class)
class ApplicationWiringTest {

    @Autowired
    ApplicationContext context;

    @Test
    void importsAutoConfigurationButDoesNotScanExternalConfig() {
        assertThat(context.getBean(GreetingService.class).greet())
            .isEqualTo("from-auto");
        assertThat(context.containsBean("defaultGreetingService")).isTrue();
        assertThat(context.containsBean("externalMarker")).isFalse();
    }
}
```

Test này dự kiến chạy với **profile mặc định** (không ép profile `custom` từ môi trường hay Maven). Khi chạy trong CI có profile custom kích hoạt sẵn, cần đặt profile cụ thể cho test để kỳ vọng phản ánh đúng ngữ cảnh.

Chạy từ thư mục project:

```bash
mvn -q test
```

Kết quả kỳ vọng: **4 test pass** (3 nhánh runner và 1 test integration). Lệnh `mvn -q test` thường không in thông tin dài khi thành công; xem báo cáo Surefire trong `target/surefire-reports` nếu cần đối chiếu số test.

**Phân biệt hai mục tiêu kiểm thử:**

- `ApplicationContextRunner` với `AutoConfigurations.of(...)` kiểm tra chính xác hành vi của cấu hình được cung cấp; nó **không chứng minh** file imports đã được đóng gói đúng.
- `@SpringBootTest` khởi động ứng dụng thật với `@EnableAutoConfiguration` và phát hiện file imports; nó giúp bắt lỗi tài nguyên `.imports` thiếu, package scan quá rộng hoặc bean được đăng ký ngoài mong đợi.

## 10. Khi cần tùy biến hoặc loại trừ auto-configuration

Ba hành động khác nhau:

| Mục đích | Cách làm | Hệ quả |
| --- | --- | --- |
| Giữ auto-configuration nhưng thay bean mặc định | Tự khai báo `@Bean GreetingService` và để `@ConditionalOnMissingBean` back off | User bean tồn tại; default bean không đăng ký. |
| Giữ class ứng viên nhưng tắt theo property được thiết kế | `demo.greeting.enabled=false` | Condition property trên auto-configuration không khớp. |
| Loại hẳn một auto-configuration khỏi tập được áp dụng | `@SpringBootApplication(exclude=GreetingAutoConfiguration.class)` hoặc `spring.autoconfigure.exclude=com.example.autoconfigure.GreetingAutoConfiguration` | Boot không áp dụng auto-configuration đó; không có nghĩa xóa bean tự khai báo. |

Một class `@Configuration` thông thường không nằm trong danh sách auto-configuration thì **không nên dùng cơ chế `spring.autoconfigure.exclude` để điều khiển nó**. Hãy dùng `@Profile`, `@Conditional`, cấu hình scan/import hoặc cơ chế phù hợp với chính nguồn đăng ký class.

Cũng đừng xem `@Primary` là cơ chế back-off: nó chỉ ảnh hưởng việc lựa chọn bean trong autowiring khi có nhiều bean tương ứng; nó không ngăn method `@Bean` khác đăng ký bean.

### Kiểm tra bằng Condition Evaluation Report

Chạy:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Condition Evaluation Report giúp xác định điều kiện nào khớp, không khớp và vì sao. Với profile custom, một negative match của `@ConditionalOnMissingBean(GreetingService.class)` là **hành vi mong muốn**, vì bean do người dùng cung cấp đã được đăng ký.

Nếu có Spring Boot Actuator với endpoint `/actuator/conditions` được expose và bảo vệ phù hợp, có thể đọc condition outcomes từ runtime. Endpoint này không mặc định mở công khai qua HTTP.

## 11. Lỗi thường gặp khi nhầm @Configuration và @AutoConfiguration

| Nhận định chưa đúng | Cách hiểu chính xác |
| --- | --- |
| “`@AutoConfiguration` không phải `@Configuration`.” | Nó là một specialized configuration annotation, meta-annotated bằng `@Configuration(proxyBeanMethods=false)`. |
| “Chỉ cần đặt `@AutoConfiguration` lên class trong JAR là Boot tự tìm thấy.” | Phải đăng ký class trong `AutoConfiguration.imports` theo cơ chế chuẩn. |
| “Mọi class có `@Configuration` đều là auto-configuration.” | Class thường được tìm bằng scan, import hoặc đăng ký trực tiếp; không tự tham gia candidate selection của Boot. |
| “Bean trong auto-configuration luôn được tạo.” | Điều kiện class/bean/property có thể không khớp hoặc auto-configuration có thể bị exclude. |
| “Thêm `@ComponentScan` package của thư viện để thấy auto-configuration.” | Cách chuẩn là sử dụng imports; auto-configuration nên nằm ngoài component scan. |
| “`proxyBeanMethods=false` làm mất singleton.” | Singleton vẫn do Spring quản lý; chỉ bỏ interception của các lời gọi trực tiếp giữa `@Bean` methods. |
| “Ordering của auto-configuration là ordering khởi tạo các bean.” | Thứ tự xử lý cấu hình và thứ tự tạo instance bean là hai khái niệm khác nhau. |
| “Có bean người dùng thì Boot xóa bean mặc định.” | Nếu có `@ConditionalOnMissingBean`, bean mặc định không được đăng ký từ đầu. |
| “Thêm `@Primary` chắc chắn khiến auto-configuration nhường chỗ.” | `@Primary` không thay thế điều kiện back-off. |
| “`@ConditionalOnMissingBean` luôn nhìn thấy mọi bean dù đăng ký về sau.” | Điều kiện dựa trên những bean definitions đã được xử lý đến thời điểm đánh giá. |

## 12. Checklist khi tự viết một lớp auto-configuration

1. Xác định **contract** mà thư viện cung cấp và bean mặc định nào có thể được thay bởi ứng dụng.
2. Đặt lớp trong package **riêng của autoconfigure module**, tránh nằm trong phạm vi component scan ứng dụng.
3. Dùng `@AutoConfiguration`; nếu cần tích hợp thư viện tùy chọn, đặt `@ConditionalOnClass` ở vị trí an toàn.
4. Đăng ký tên đầy đủ của class trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` của JAR.
5. Đặt `@ConditionalOnMissingBean` theo kiểu/tên phù hợp trên các bean mặc định, cân nhắc property cho phép người dùng bật/tắt.
6. Viết các `@Bean` method theo kiểu **dependency injection qua tham số**, vì `proxyBeanMethods=false`.
7. Chỉ định `before`/`after` nếu có ràng buộc thực sự với một auto-configuration khác; đừng dùng thứ tự để bù cho dependency bean thiếu.
8. Kiểm thử bằng `ApplicationContextRunner`: có default, user bean back-off, property/classpath condition không khớp.
9. Kiểm thử integration với Spring Boot app để xác nhận **đã đóng gói file imports** và bean đúng phạm vi component scan.
10. Kiểm tra Condition Evaluation Report khi behavior khác kỳ vọng, và xem tên bean/kiểu bean cụ thể.

## 13. Câu hỏi tự kiểm tra

1. Tại sao `@AutoConfiguration` cũng xử lý được `@Bean`? **Vì nó được meta-annotate bằng `@Configuration`.**
2. Có file `GreetingAutoConfiguration.class` trong dependency nhưng thiếu imports; Boot có tự tìm thấy theo auto-discovery chuẩn không? **Không.**
3. `@Configuration` ở ngoài phạm vi scan và không được import có tạo bean không? **Không**, trừ khi được đăng ký qua cơ chế khác.
4. Trong demo, không bật profile custom, `defaultGreetingService` có tồn tại không? **Có**, vì các điều kiện khớp.
5. Bật profile custom, bean mặc định có bị tạo rồi thay thế không? **Không**. Điều kiện `@ConditionalOnMissingBean` không khớp nên method mặc định không được đăng ký.
6. Tắt `demo.greeting.enabled` nhưng bật `custom`, có mất bean người dùng không? **Không**, property chỉ áp dụng cho class auto-configuration được gắn điều kiện.
7. Với `@AutoConfiguration`, việc gọi trực tiếp method `@Bean` từ một method `@Bean` khác có chắc trả về singleton container không? **Không**; dùng tham số injection để lấy bean quản lý.
8. Thêm `@AutoConfiguration(after = OtherAutoConfiguration.class)` có bảo đảm bean của mình tạo instance sau bean kia không? **Không**. Nó chi phối thứ tự xử lý cấu hình, không phải lifecycle instance.
9. Có thể dùng `@ConditionalOnProperty` trên `@Configuration` thông thường không? **Có**; các điều kiện không bị giới hạn riêng cho auto-configuration.
10. Khi integration test pass nhưng `ApplicationContextRunner` test fail vì thiếu user bean, nên kiểm tra gì? **Context runner chỉ nạp các cấu hình chỉ định**; cần thêm `withUserConfiguration(...)` khi test nhánh back-off.

## Nguồn chính thức

- [Spring Boot 3.5 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html): định nghĩa annotation, `@Configuration(proxyBeanMethods=false)`, `before/after`.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): cơ chế imports, cách tổ chức class, condition, ordering và kiểm thử.
- [Spring Boot 3.5 API — EnableAutoConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/EnableAutoConfiguration.html): kích hoạt, exclusion và ý nghĩa của base package.
- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): cấu hình mặc định và back-off.
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): `@Configuration`, `@Bean`, `@Import` và semantics của configuration.
