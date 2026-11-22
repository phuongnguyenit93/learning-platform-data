# Lọc ứng viên auto-configuration trước khi xử lý đầy đủ cấu hình trong Spring Boot

## 1. Vấn đề: số lượng ứng viên lớn nhưng ứng dụng chỉ cần một phần

Một ứng dụng Spring Boot có thể đưa nhiều starter và thư viện vào classpath. Mỗi JAR có thể công bố các class auto-configuration ứng viên thông qua tài nguyên:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Danh sách ứng viên có thể lớn hơn nhiều so với số cấu hình thực sự áp dụng. Chẳng hạn một auto-configuration tích hợp JDBC không nên được xử lý đầy đủ nếu runtime hoàn toàn không có API JDBC cần thiết. Việc phân tích mọi class ứng viên như cấu hình đầy đủ, rồi mới phát hiện rằng điều kiện classpath không thỏa mãn, sẽ làm tăng công việc khởi động.

Spring Boot vì vậy có cơ chế **lọc sớm ứng viên** (*early auto-configuration filtering*). Ý tưởng là sử dụng **tên lớp và metadata điều kiện được chuẩn bị từ trước** để loại những ứng viên chắc chắn không phù hợp, trước khi cần đọc và xử lý đầy đủ cấu trúc class cấu hình của chúng.

Điểm cần phân biệt ngay: **lọc ứng viên** là một bước tối ưu hóa trong quá trình chọn auto-configuration. Nó không đồng nghĩa với việc bỏ qua mọi phép đánh giá điều kiện, và không được hiểu thành “hễ class có mặt thì bean được tạo”.

### Sau bài học có thể trả lời

- Một tên lớp trong **AutoConfiguration.imports** đã là một bean hay chưa?
- Spring Boot quyết định bỏ một ứng viên ngay ở giai đoạn đầu bằng cách nào?
- **AutoConfigurationImportFilter**, **AutoConfigurationMetadata** và **spring-boot-autoconfigure-processor** đóng vai trò gì?
- Vì sao **@ConditionalOnClass** ở cấp class phù hợp với lọc sớm, còn **@ConditionalOnMissingBean** cần biết trạng thái bean của context?
- Cách chứng minh ứng viên bị bỏ qua khi dependency tùy chọn biến mất và xuất hiện khi dependency có mặt?
- Nếu một ứng viên không tạo bean, nên kiểm tra file imports, exclude, classpath hay condition report trước?

Bài thực hành dùng **Java 21, Gradle và Spring Boot 3.3.x**, kèm một ví dụ thư viện và ứng dụng tiêu thụ tách package.

## 2. Toàn cảnh từ khám phá đến đăng ký bean

Luồng khái quát:

~~~text
JAR trên classpath
      |
      v
Đọc AutoConfiguration.imports
→ Danh sách tên class ứng viên
      |
      v
Loại trùng / loại exclude theo cấu hình
      |
      v
Bộ lọc sớm (AutoConfigurationImportFilter)
+ metadata điều kiện khi có
      |
      +----------------------+
      |                      |
  Bị loại sớm          Ứng viên còn lại
  Không import                |
                              v
                 Chọn/sắp xếp các auto-configuration
                              |
                              v
                 Xử lý annotation, @Configuration,
                 điều kiện ở các giai đoạn phù hợp
                              |
                       +------+------+
                       |             |
                     Match       Không match
                       |             |
                       v             v
                  Bean definition   Bỏ qua bean/
                  có thể đăng ký    cấu hình tương ứng
                       |
                       v
                  Context tạo bean theo vòng đời
~~~

Sơ đồ cố ý giản lược nhiều giai đoạn xử lý của Spring. Trong Spring Boot 3.3, **AutoConfigurationImportSelector** tham gia chọn các auto-configuration qua cơ chế **DeferredImportSelector**. Khi chọn ứng viên, selector có thể áp dụng import filter trước lúc các configuration class được xử lý đầy đủ.

Cần phân biệt các khái niệm:

| Thuật ngữ | Vai trò | Điều nó **không** chứng minh |
| --- | --- | --- |
| **Candidate discovery** | Thu thập tên class từ **AutoConfiguration.imports** | Chưa có nghĩa class tạo bean. |
| **Exclusion** | Loại class do ứng dụng yêu cầu exclude | Không có nghĩa class/bytecode biến mất khỏi JAR. |
| **Early filtering** | Loại class ứng viên chắc chắn không phù hợp dựa trên thông tin sẵn có | Không thay thế mọi condition về bean/property/runtime. |
| **Condition evaluation** | Quyết định cấu hình hoặc phương thức bean có phù hợp hay không | Không đồng nghĩa mọi class đều phải được nạp ngay từ đầu. |
| **Bean registration/creation** | Đăng ký định nghĩa và tạo instance theo Spring container | Thứ tự tạo bean không chỉ do thứ tự dòng imports. |

Đây là **nhiều tầng lựa chọn**, không phải một biểu thức if duy nhất.

## 3. AutoConfigurationImportSelector chọn và lọc ứng viên

Trong Spring Boot 3.3, **AutoConfigurationImportSelector** là thành phần phối hợp việc chọn các class auto-configuration. Khi auto-configuration được bật thông qua **@EnableAutoConfiguration** (thường nằm trong **@SpringBootApplication**), selector tìm danh sách ứng viên rồi thực hiện những xử lý cần thiết.

Có thể hiểu các bước chính như sau:

1. Kiểm tra auto-configuration có đang được bật hay không.
2. Đọc tên class ứng viên từ các tài nguyên **AutoConfiguration.imports** trên classpath.
3. Loại tên trùng và xử lý tập auto-configuration bị **exclude**.
4. Áp dụng các **AutoConfigurationImportFilter** để loại ứng viên không thỏa điều kiện được kiểm tra sớm.
5. Hoàn thiện tập class import và để Spring tiếp tục xử lý cấu hình, condition, bean definitions.

Tên các phương thức và chi tiết triển khai có thể thay đổi giữa những phiên bản Spring Boot, nhưng ý nghĩa của bước lọc trước khi import class cấu hình là trọng tâm của bài này.

### 3.1. Exclude khác gì filter?

Ứng dụng có thể chủ động loại trừ một auto-configuration:

~~~java
@SpringBootApplication(
    excludeName = "com.example.greeting.autoconfigure.OptionalGreetingAutoConfiguration"
)
public class DemoApplication {
}
~~~

Đây là **đoạn minh họa cú pháp annotation trong một class**, chưa phải chương trình Java hoàn chỉnh. Cấu hình loại trừ cũng có thể dùng property **spring.autoconfigure.exclude** khi phù hợp. Exclude thể hiện **quyết định rõ ràng của ứng dụng** không sử dụng cấu hình đó.

Ngược lại, import filter có thể bỏ một ứng viên vì **điều kiện không thỏa mãn**, ví dụ một class tích hợp tùy chọn hoàn toàn không tồn tại. Khi dependency xuất hiện, bộ lọc có thể để lại ứng viên trong danh sách và các condition khác tiếp tục quyết định.

Exclude không phải cách sửa thiếu dependency ngẫu nhiên. Với thư viện do chính mình viết, hãy định nghĩa condition đúng thay vì yêu cầu mọi ứng dụng tiêu thụ tự lập danh sách exclude.

## 4. AutoConfigurationImportFilter hoạt động như thế nào?

Spring Boot 3.3 cung cấp giao diện **org.springframework.boot.autoconfigure.AutoConfigurationImportFilter**. Một import filter nhận danh sách tên class ứng viên và metadata, rồi trả về một mảng boolean theo từng vị trí:

~~~java
boolean[] match(
    String[] autoConfigurationClasses,
    AutoConfigurationMetadata autoConfigurationMetadata
);
~~~

Đây là **chữ ký phương thức của API**, không phải chương trình Java độc lập. Mỗi vị trí **true** nghĩa là ứng viên ở vị trí tương ứng **được giữ lại ở bước lọc đó**; **false** nghĩa là **không import** ứng viên ấy qua bộ lọc. Mảng kết quả phải có **cùng số phần tử** với mảng ứng viên đầu vào.

Ví dụ tư duy (không phải output thực tế của Spring Boot):

~~~text
Ứng viên đầu vào:
[CoreAutoConfiguration, OptionalGreetingAutoConfiguration]

Bộ lọc kiểm tra sự hiện diện của OptionalFeature:

Có OptionalFeature:
[true, true]

Không có OptionalFeature:
[true, false]
~~~

Nhận được **true** không có nghĩa mọi điều kiện về bean, property và ứng dụng đều thỏa mãn. Nó chỉ có nghĩa bộ lọc cụ thể **không loại ứng viên ở giai đoạn này**.

### 4.1. Filter có thể được đăng ký ở đâu?

Trong Spring Boot 3.3, phần mở rộng **AutoConfigurationImportFilter** được tìm bằng cơ chế **spring.factories**. Đây là một điểm phân biệt dễ nhầm:

- **AutoConfiguration.imports**: đăng ký **các class auto-configuration ứng viên**.
- **META-INF/spring.factories**: có thể đăng ký **các implementation của AutoConfigurationImportFilter** và một số SPI Spring Boot khác.
- **META-INF/spring-autoconfigure-metadata.properties**: chứa **metadata điều kiện được annotation processor sinh ra** để hỗ trợ lọc sớm.

Ba tệp có nhiệm vụ khác nhau. Không đặt class auto-configuration vào spring.factories với mong muốn Boot 3.x tự phát hiện nó theo cơ chế imports mới, và cũng không đưa tên filter vào AutoConfiguration.imports như thể đó là class @AutoConfiguration.

Một thư viện thông thường **không cần tự viết AutoConfigurationImportFilter**. Cách được khuyến nghị cho phần lớn trường hợp là khai báo **@ConditionalOnClass**, các condition phù hợp và bật annotation processor. SPI filter riêng chỉ thích hợp khi có yêu cầu tiên quyết mà các condition chuẩn không giải quyết tốt.

### 4.2. Tại sao lọc sớm có thể nhanh hơn?

Đầu vào của bộ lọc chủ yếu là **tên class dạng chuỗi** và metadata về các điều kiện đã được thu thập trước. Nhờ đó, một số ứng viên có thể bị loại **trước khi phải đọc bytecode của class auto-configuration ấy** để xử lý cấu hình đầy đủ.

Điều này giảm khối lượng phân tích class và điều kiện vào lúc startup, đặc biệt trong ứng dụng chứa nhiều tích hợp tùy chọn. Tuy nhiên hiệu quả thực tế phụ thuộc số lượng ứng viên, điều kiện, classpath và runtime. Không nên khẳng định mọi ứng dụng đều có mức tăng tốc cố định hoặc rằng Spring Boot không đọc bất kỳ bytecode nào trong suốt quá trình khởi động.

## 5. Metadata giúp lọc trước mà không cần xử lý class đầy đủ

Spring Boot có annotation processor **spring-boot-autoconfigure-processor**. Khi module thư viện được biên dịch, processor có thể thu thập thông tin điều kiện trên auto-configuration và sinh tài nguyên:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Ví dụ về **ý nghĩa** của metadata là lưu rằng class **OptionalGreetingAutoConfiguration** yêu cầu class **com.example.optionalapi.OptionalFeature** hiện diện. Một bộ lọc sớm có thể dùng thông tin ấy để loại cấu hình khi class tùy chọn không có trên classpath.

Đây là metadata **dành cho auto-configuration**. Đừng nhầm với:

~~~text
META-INF/spring-configuration-metadata.json
~~~

Tệp JSON thứ hai hỗ trợ tài liệu/gợi ý cấu hình từ **@ConfigurationProperties** trong IDE; nó không có cùng chức năng với metadata điều kiện dùng cho early filtering.

### 5.1. Bộ lọc cần gì từ metadata?

**AutoConfigurationMetadata** cung cấp khả năng tra cứu dữ liệu được processor tạo ra theo tên class và key metadata. Bộ lọc có thể đọc dữ liệu này mà chưa phải phân tích toàn bộ class như một cấu hình Spring.

Không phải mọi điều kiện trên bean hay mọi property runtime đều có thể quyết định chắc chắn chỉ từ metadata tĩnh. Một ứng viên không được loại sớm vẫn có thể **không match** khi Spring đánh giá condition trong context.

### 5.2. Nếu thiếu metadata thì sao?

Thiếu **spring-autoconfigure-metadata.properties** thường ảnh hưởng **tối ưu hóa lọc sớm**, không tự nó biến một cấu hình có điều kiện thành vô điều kiện. Spring vẫn có cơ chế xử lý annotation/condition trong các giai đoạn sau.

Điều này khác với việc thiếu **AutoConfiguration.imports**: nếu resource imports không có, class auto-configuration của thư viện có thể **không được tìm thấy làm ứng viên** trong ứng dụng tiêu thụ.

| Tệp thiếu | Hệ quả đáng chú ý |
| --- | --- |
| **AutoConfiguration.imports** | Thiếu đường đăng ký class ứng viên của thư viện. |
| **spring-autoconfigure-metadata.properties** | Mất cơ hội lọc sớm nhờ metadata; logic condition vẫn cần được áp dụng khi xử lý cấu hình. |
| **spring-configuration-metadata.json** | Chủ yếu mất gợi ý/tài liệu property cho IDE, nếu đây là metadata được dự định cung cấp. |

Không nên diễn giải một context test pass là đủ chứng minh cả ba tài nguyên đều được đóng gói đúng.

## 6. Ví dụ project: một ứng viên luôn xét, một ứng viên phụ thuộc class tùy chọn

Ta tạo ba module:

~~~text
early-filter-lab/
├── settings.gradle
├── build.gradle
├── optional-api/
│   ├── build.gradle
│   └── src/main/java/com/example/optionalapi/
│       └── OptionalFeature.java
├── greeter-autoconfigure/
│   ├── build.gradle
│   ├── src/main/java/com/example/greeter/
│   │   ├── BaseMarker.java
│   │   ├── GreetingService.java
│   │   └── autoconfigure/
│   │       ├── BaseAutoConfiguration.java
│   │       └── OptionalGreetingAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/greeter/autoconfigure/
│       └── AutoConfigurationConditionsTest.java
└── demo-app/
    ├── build.gradle
    └── src/main/java/com/example/demo/
        └── DemoApplication.java
~~~

**optional-api** chỉ chứa một class đóng vai trò điều kiện classpath. **greeter-autoconfigure** khai báo hai ứng viên. **demo-app** tiêu thụ thư viện và quan sát bean trước/sau khi thêm optional-api vào runtime.

### 6.1. Build Gradle dùng Java 21 và Spring Boot 3.3.13

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'early-filter-lab'
include 'optional-api', 'greeter-autoconfigure', 'demo-app'
~~~

Tệp **build.gradle** ở root:

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'io.spring.dependency-management'

    group = 'com.example'
    version = '1.0.0'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    repositories {
        mavenCentral()
    }

    dependencyManagement {
        imports {
            mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.13'
        }
    }

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
~~~

Phiên bản **3.3.13** được cố định **để mô tả và kiểm chứng đúng API trong bài**, không phải tuyên bố bản Spring Boot mới nhất. Gradle cần môi trường JDK 21/Gradle tương thích và mạng tới Maven Central khi tải dependency lần đầu.

Tệp **optional-api/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
}
~~~

Tệp **greeter-autoconfigure/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation project(':optional-api')
}
~~~

**Giải thích:** Processor nằm ở configuration **annotationProcessor** nên tham gia biên dịch, không trở thành dependency runtime của ứng dụng. **optional-api** chỉ là **testImplementation** ở module autoconfigure; mã production của module này không yêu cầu optional-api, vì dùng tên class dạng chuỗi trong annotation điều kiện.

Tệp **demo-app/build.gradle**:

~~~groovy
plugins {
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':greeter-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

Đây là cấu hình ứng dụng **chưa có optional-api ở runtime**. Trong lần thử thứ hai, ta sẽ thêm dependency này có chủ đích.

### 6.2. Định nghĩa class tùy chọn

Tệp **optional-api/src/main/java/com/example/optionalapi/OptionalFeature.java**:

~~~java
package com.example.optionalapi;

public final class OptionalFeature {

    private OptionalFeature() {
    }
}
~~~

Đây là class marker, không tự tạo bean hoặc hành vi nghiệp vụ. Sự có mặt của class này trên **runtimeClasspath** là dữ kiện cho điều kiện **@ConditionalOnClass**.

### 6.3. Định nghĩa bean types của thư viện

Tệp **greeter-autoconfigure/src/main/java/com/example/greeter/BaseMarker.java**:

~~~java
package com.example.greeter;

public record BaseMarker(String name) {
}
~~~

Tệp **greeter-autoconfigure/src/main/java/com/example/greeter/GreetingService.java**:

~~~java
package com.example.greeter;

public final class GreetingService {

    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Các class này nằm trong JAR thư viện nên **luôn có thể tồn tại trên classpath** khi ứng dụng khai báo greeter-autoconfigure.

### 6.4. Ứng viên không có điều kiện classpath tùy chọn

Tệp **greeter-autoconfigure/src/main/java/com/example/greeter/autoconfigure/BaseAutoConfiguration.java**:

~~~java
package com.example.greeter.autoconfigure;

import com.example.greeter.BaseMarker;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class BaseAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(BaseMarker.class)
    public BaseMarker baseMarker() {
        return new BaseMarker("core");
    }
}
~~~

Cấu hình này không yêu cầu optional-api. Nếu ứng dụng chưa cung cấp BaseMarker, bean mặc định **baseMarker** được tạo trong cả hai thí nghiệm.

### 6.5. Ứng viên được bảo vệ bởi điều kiện classpath

Tệp **greeter-autoconfigure/src/main/java/com/example/greeter/autoconfigure/OptionalGreetingAutoConfiguration.java**:

~~~java
package com.example.greeter.autoconfigure;

import com.example.greeter.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(name = "com.example.optionalapi.OptionalFeature")
public class OptionalGreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new GreetingService();
    }
}
~~~

**Đọc điều kiện:**

- **@ConditionalOnClass** ở **cấp class**: chỉ xét cấu hình Greeting khi class **OptionalFeature** có thể được tìm thấy.
- **@ConditionalOnMissingBean** ở **cấp phương thức @Bean**: kể cả khi classpath hợp lệ, chỉ tạo GreetingService mặc định nếu ứng dụng chưa cung cấp bean tương ứng.
- **name = "..."** cho phép nêu class tùy chọn bằng FQCN dạng chuỗi, không cần import type đó để biên dịch thư viện.

Đặt classpath condition ở cấp auto-configuration là lựa chọn thuận lợi để annotation processor có thể tạo metadata cho bước lọc sớm. Nếu chỉ đặt condition trên **một phương thức @Bean**, nó không có cùng nghĩa “loại cả auto-configuration class khỏi danh sách ứng viên”.

**Lưu ý nâng cao:** Nếu method signature, field hoặc nested config của auto-configuration tham chiếu trực tiếp tới type tùy chọn, JVM/Spring có thể cần giải quyết type ở thời điểm khác. Thực tế nên dùng cấu hình lồng riêng, có **@ConditionalOnClass** thích hợp, để cách ly những phương thức phụ thuộc thư viện tùy chọn. Ví dụ này không cần vì GreetingService không tham chiếu OptionalFeature.

### 6.6. Công bố hai ứng viên trong tệp imports

Tệp **greeter-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**:

~~~text
com.example.greeter.autoconfigure.BaseAutoConfiguration
com.example.greeter.autoconfigure.OptionalGreetingAutoConfiguration
~~~

Cả hai tên lớp đều là **ứng viên ban đầu**. Việc xuất hiện một dòng trong imports **không** nghĩa class sẽ vượt qua điều kiện hoặc tạo bean.

Ở thời điểm biên dịch thư viện, processor cố gắng sinh metadata cho điều kiện của OptionalGreetingAutoConfiguration. Ứng dụng thực tế có thể dùng metadata ấy để loại sớm ứng viên nếu OptionalFeature vắng mặt.

## 7. Kiểm thử điều kiện trong context nhỏ

Tệp **greeter-autoconfigure/src/test/java/com/example/greeter/autoconfigure/AutoConfigurationConditionsTest.java**:

~~~java
package com.example.greeter.autoconfigure;

import com.example.greeter.BaseMarker;
import com.example.greeter.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationConditionsTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    BaseAutoConfiguration.class,
                    OptionalGreetingAutoConfiguration.class));

    @Test
    void createsBothBeansWhenOptionalClassIsAvailable() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(BaseMarker.class);
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context.getBean(GreetingService.class).greet("An"))
                .isEqualTo("Xin chào, An!");
        });
    }

    @Test
    void skipsGreetingWhenOptionalClassIsHidden() {
        runner.withClassLoader(
            new FilteredClassLoader("com.example.optionalapi")
        ).run(context -> {
            assertThat(context).hasSingleBean(BaseMarker.class);
            assertThat(context).doesNotHaveBean(GreetingService.class);
        });
    }

    @Test
    void usesApplicationGreetingServiceWhenProvided() {
        runner.withUserConfiguration(CustomGreetingConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(GreetingService.class);
                assertThat(context.getBean(GreetingService.class).greet("An"))
                    .isEqualTo("Xin chào, An!");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return new GreetingService();
        }
    }
}
~~~

**Ý nghĩa ba test:**

1. Vì **optional-api** nằm trong **testImplementation**, context test thường nhìn thấy OptionalFeature. Hai bean mặc định có mặt.
2. **FilteredClassLoader** che package optional-api; Bean BaseMarker vẫn có mặt, còn GreetingService mặc định không được tạo vì điều kiện classpath không thỏa mãn.
3. Khi có bean GreetingService do người dùng khai báo, **@ConditionalOnMissingBean** khiến auto-configuration nhường quyền. Trong demo, bean riêng có cùng hành vi để giảm code; bằng chứng của back off là **hasSingleBean**, không phải chuỗi trả về khác.

Chạy:

~~~bash
gradle :greeter-autoconfigure:test
~~~

Nếu project có Gradle Wrapper, dùng **./gradlew :greeter-autoconfigure:test** hoặc **.\gradlew.bat :greeter-autoconfigure:test** trên Windows.

**Giới hạn bằng chứng của test:** Ta đã chỉ định trực tiếp **AutoConfigurations.of(...)**. Các test này rất tốt để kiểm chứng **logic @ConditionalOnClass và @ConditionalOnMissingBean**, nhưng **không tự chứng minh import filter đã loại class dựa trên metadata trong bước AutoConfigurationImportSelector**, và cũng chưa chứng minh JAR chứa imports. Muốn kiểm chứng đường đi discovery và filtering thật, cần bước tiếp theo.

## 8. Chạy một ứng dụng tiêu thụ không import cấu hình thủ công

Tệp **demo-app/src/main/java/com/example/demo/DemoApplication.java**:

~~~java
package com.example.demo;

import com.example.greeter.BaseMarker;
import com.example.greeter.GreetingService;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner inspect(ApplicationContext context) {
        return args -> {
            boolean hasBase =
                !context.getBeansOfType(BaseMarker.class).isEmpty();
            boolean hasGreeting =
                !context.getBeansOfType(GreetingService.class).isEmpty();

            System.out.println("BaseMarker present: " + hasBase);
            System.out.println("GreetingService present: " + hasGreeting);
        };
    }
}
~~~

Chú ý package ứng dụng **com.example.demo** khác package thư viện **com.example.greeter.autoconfigure**. **@SpringBootApplication** mặc định quét package của ứng dụng và các package con; nó **không quét package auto-configuration bên ngoài**. Ứng viên được phát hiện qua tệp imports của thư viện.

### 8.1. Lần chạy A: optional-api vắng mặt

Giữ **demo-app/build.gradle** chưa khai báo dependency tới optional-api, rồi chạy:

~~~bash
gradle :demo-app:bootRun
~~~

Hai dòng do ApplicationRunner in ra dự kiến:

~~~text
BaseMarker present: true
GreetingService present: false
~~~

Có thể có nhiều log Spring Boot và Gradle khác trước/sau hai dòng này. **Không có GreetingService** bởi class **OptionalFeature** vắng mặt. Candidate được tìm từ imports, nhưng điều kiện cấp class không phù hợp; với metadata được sinh đúng, Spring Boot có thể loại sớm ứng viên.

Để quan sát thêm thông tin điều kiện, chạy:

~~~bash
gradle :demo-app:bootRun --args='--debug'
~~~

Tìm nhóm liên quan **OptionalGreetingAutoConfiguration** trong báo cáo điều kiện, nếu được hiển thị ở luồng báo cáo của phiên bản và tình huống đó. Không được mặc định rằng mọi ứng viên bị loại ở bước import filter đều xuất hiện dưới cùng một hình thức với cấu hình đã được xử lý đầy đủ.

### 8.2. Lần chạy B: thêm dependency tùy chọn

Trong **demo-app/build.gradle**, bổ sung đúng một dòng trong block dependencies:

~~~groovy
runtimeOnly project(':optional-api')
~~~

**Đây là một dòng cần thêm vào build.gradle ở chặng này**, không phải toàn bộ tệp để ghi đè. Lúc chạy ứng dụng, OptionalFeature hiện diện trên **runtimeClasspath**. Lặp lại:

~~~bash
gradle :demo-app:bootRun
~~~

Hai dòng dự kiến:

~~~text
BaseMarker present: true
GreetingService present: true
~~~

Sự thay đổi này minh họa mối liên hệ:

~~~text
Không có OptionalFeature
→ @ConditionalOnClass không thỏa mãn
→ OptionalGreetingAutoConfiguration bị loại/bỏ qua
→ Không có GreetingService mặc định

Có OptionalFeature
→ Không bị loại bởi điều kiện classpath
→ Kiểm tra tiếp điều kiện @ConditionalOnMissingBean
→ Có GreetingService mặc định nếu chưa có bean thay thế
~~~

Đây là cách học có kiểm chứng. Không dùng việc “log ít hơn” làm bằng chứng hiệu năng tuyệt đối; thời gian khởi động chịu ảnh hưởng bởi cache, JVM warm-up, thiết bị, dependency tải lần đầu và nhiều yếu tố khác.

### 8.3. Thêm exclude để so sánh

Khi **optional-api** đã có mặt, có thể thử loại trừ ứng viên bằng tham số:

~~~bash
gradle :demo-app:bootRun --args='--spring.autoconfigure.exclude=com.example.greeter.autoconfigure.OptionalGreetingAutoConfiguration'
~~~

Ứng dụng lại dự kiến in **GreetingService present: false** dù class OptionalFeature đang có mặt. Đây là kết quả của **exclude rõ ràng** do ứng dụng yêu cầu. Nó khác nguyên nhân “class không có trong runtime classpath”. Sau thử nghiệm, chạy lại không có exclude để trở về cấu hình bình thường.

## 9. Kiểm tra metadata được sinh và resource đóng gói

Chạy task biên dịch và đóng gói module thư viện:

~~~bash
gradle :greeter-autoconfigure:jar
~~~

Với group và version ở ví dụ, tệp JAR dự kiến nằm ở:

~~~text
greeter-autoconfigure/build/libs/greeter-autoconfigure-1.0.0.jar
~~~

Liệt kê entry:

~~~bash
jar tf greeter-autoconfigure/build/libs/greeter-autoconfigure-1.0.0.jar
~~~

Hãy tìm:

~~~text
com/example/greeter/autoconfigure/BaseAutoConfiguration.class
com/example/greeter/autoconfigure/OptionalGreetingAutoConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-autoconfigure-metadata.properties
~~~

**Lưu ý:** Resource metadata được sinh bởi annotation processor khi compile. Nếu không thấy **spring-autoconfigure-metadata.properties**, kiểm tra **annotationProcessor** có được cấu hình đúng, Gradle compile có chạy và JAR có lấy đầu ra generated resources của compiler hay không. Không tự tạo thủ công một tệp metadata suy đoán để làm cho test pass.

Nếu hệ thống có **unzip**, có thể đọc entry metadata:

~~~bash
unzip -p greeter-autoconfigure/build/libs/greeter-autoconfigure-1.0.0.jar META-INF/spring-autoconfigure-metadata.properties
~~~

Đầu ra chính xác tùy processor và phiên bản, nhưng hãy tìm thông tin liên quan đến **OptionalGreetingAutoConfiguration** và điều kiện classpath **OptionalFeature**. Metadata là dữ liệu do công cụ sinh ra; không coi thứ tự, định dạng từng dòng hay tên key ngẫu nhiên quan sát được là API bất biến cho ứng dụng nghiệp vụ.

Đọc luôn resource imports trong JAR để chắc hai FQCN có mặt. Một kiểm thử trực tiếp import class có thể pass ngay cả khi JAR thiếu file imports.

### Hai loại metadata rất dễ nhầm

| Tài nguyên | Tạo bởi | Vai trò |
| --- | --- | --- |
| **AutoConfiguration.imports** | Tác giả thư viện khai báo | Chỉ ra những class auto-configuration ứng viên. |
| **spring-autoconfigure-metadata.properties** | **spring-boot-autoconfigure-processor** | Cung cấp metadata điều kiện cho lọc sớm. |
| **spring-configuration-metadata.json** | **spring-boot-configuration-processor** | Hỗ trợ khám phá/gợi ý các property cấu hình. |

Bài này không tạo @ConfigurationProperties nên không cần thêm configuration processor chỉ để minh họa import filtering.

## 10. Phân biệt điều kiện kiểm tra sớm và điều kiện kiểm tra muộn

Lọc sớm hiệu quả nhất khi điều kiện **có thể xác định bằng thông tin sẵn có** trước lúc Spring phải xây dựng toàn bộ bean definitions.

| Điều kiện hoặc yếu tố | Có thể dùng để quyết định sớm? | Cách hiểu đúng |
| --- | --- | --- |
| **@ConditionalOnClass** trên auto-configuration class | Thường có thể dùng metadata classpath để lọc sớm | Class vắng mặt → có thể loại ngay; class có mặt → vẫn phải xem điều kiện khác. |
| **@ConditionalOnMissingClass** | Có thể dùng thông tin classpath cho các trường hợp được processor/filter hỗ trợ | Phải xác minh logic condition của phiên bản đang dùng. |
| **@ConditionalOnBean** | Cần biết những bean definitions đã được đăng ký | Không suy ra an toàn chỉ từ danh sách class trong JAR. |
| **@ConditionalOnMissingBean** | Cần biết trạng thái context và thứ tự xử lý phù hợp | Không phải phép kiểm tra “JAR có class hay không”. |
| **@ConditionalOnProperty** | Phụ thuộc Environment và semantics của thuộc tính | Không đồng nhất với một classpath metadata lookup; thời điểm đánh giá tùy cơ chế. |
| **@ConditionalOnWebApplication** | Phụ thuộc web application context / loại ứng dụng | Không đơn giản bằng việc class ở thư viện đã được đặt trong imports. |
| **Exclude** | Có thể loại trong quá trình chọn ứng viên | Đây là lựa chọn cấu hình rõ ràng của ứng dụng, không phải điều kiện bean. |

Đặc biệt, **@ConditionalOnMissingBean** dùng để cho cấu hình mặc định **nhường quyền** (*back off*) khi người dùng đã tạo bean. Điều kiện đó không thể được xử lý đúng bằng cách đếm dependency classpath, vì cùng một classpath nhưng hai ứng dụng có thể có những bean definition khác nhau.

### 10.1. Vì sao không đưa mọi condition vào import filter?

Nếu một filter cố gắng tự tạo context hoặc đọc bean chưa được đăng ký, nó có thể quyết định sai. Lọc sớm phải **thận trọng**: loại ứng viên chỉ khi có cơ sở chắc chắn rằng nó không phù hợp với những thông tin ở giai đoạn hiện tại.

**Thiết kế tốt** thường đặt classpath condition ở lớp auto-configuration, dùng bean/property conditions nơi thích hợp và để Spring Boot thực hiện đúng cơ chế của từng điều kiện.

## 11. Khi nào cần viết AutoConfigurationImportFilter tùy chỉnh?

Phần lớn tác giả starter chỉ cần:

1. Đăng ký lớp **@AutoConfiguration** trong **AutoConfiguration.imports**.
2. Dùng các condition chuẩn như **@ConditionalOnClass**, **@ConditionalOnMissingBean**, **@ConditionalOnProperty**.
3. Bật **spring-boot-autoconfigure-processor** để sinh metadata lọc sớm.
4. Test các nhánh có/không có dependency tùy chọn, custom bean và ứng dụng tiêu thụ.

**AutoConfigurationImportFilter** là SPI mức thấp. Bạn chỉ nên cân nhắc tự triển khai khi điều kiện **có thể kiểm tra sớm một cách an toàn**, mang tính hệ thống và không có annotation/condition chuẩn phù hợp.

Nếu thực sự viết filter, lưu ý contract của API:

- Nhận danh sách tên class, có thể có phần tử null khi các bộ lọc nối tiếp nhau xử lý.
- Không sửa trực tiếp mảng class ứng viên.
- Trả mảng boolean **cùng độ dài** và map đúng theo chỉ số.
- Đừng nạp hàng loạt class hoặc khởi tạo bean trong bước lọc, vì làm vậy mất ý nghĩa tối ưu hóa.
- Đăng ký filter ở **META-INF/spring.factories** theo key của **AutoConfigurationImportFilter**, còn auto-configuration class vẫn đi qua **AutoConfiguration.imports**.
- Viết test về loại đúng ứng viên, giữ đúng ứng viên và không làm sai khi metadata thiếu hoặc ứng viên null.

Không biến SPI filter thành cơ chế tùy chỉnh nghiệp vụ theo request/user. Nó diễn ra lúc bootstrap context, không phải khi xử lý từng HTTP request.

## 12. Chẩn đoán khi ứng viên không tạo bean

### Trường hợp A — Thư viện trên classpath nhưng class không được xem là ứng viên

Kiểm tra JAR có tài nguyên **AutoConfiguration.imports** và FQCN đúng không. **@AutoConfiguration** trên Java class tự nó chưa đủ để một thư viện ngoài được khám phá. Cần xác nhận runtimeClasspath của ứng dụng thực sự có JAR đó, và không có custom packaging ghi đè resource.

### Trường hợp B — Có imports nhưng bị loại vì class tùy chọn thiếu

Dùng lệnh Gradle ở đúng module để kiểm tra dependency:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
~~~

Nếu optional-api không có, **@ConditionalOnClass(name=...)** không match. Có thể xác minh class thực tế bằng một **ClassLoader** trong runtime hoặc kiểm tra dependency graph; không dựa hoàn toàn vào việc source của một module khác có class đó.

### Trường hợp C — Class tùy chọn có mặt nhưng bean vẫn thiếu

Bước lọc sớm không đảm bảo mọi bean được tạo. Kiểm tra:

- Có **@ConditionalOnMissingBean** nào back off vì ứng dụng đã khai báo bean không?
- Có **@ConditionalOnProperty** bị tắt do property/profile không?
- Loại ApplicationContext có phù hợp không?
- Configuration có bị exclude không?
- Có lỗi trong phương thức @Bean hoặc dependency của bean khi context khởi tạo không?

Dùng Condition Evaluation Report với **--debug** để tìm lý do condition không match. Nếu ứng viên đã bị loại rất sớm, thông tin báo cáo có thể khác với trường hợp class cấu hình đã được xử lý sau import.

### Trường hợp D — Không thấy metadata dù code có @ConditionalOnClass

Kiểm tra processor có được thêm qua **annotationProcessor** trong module autoconfigure thực sự được biên dịch. Kiểm tra output biên dịch và JAR đã phát hành; phân biệt **spring-autoconfigure-metadata.properties** với metadata của **@ConfigurationProperties**.

Thiếu metadata không phải lý do hợp lý để tự bỏ qua condition. Lỗi chức năng và vấn đề tối ưu hóa cần được chẩn đoán riêng.

### Trường hợp E — Thời gian khởi động không cải thiện rõ rệt

Lọc sớm tránh một phần công việc, nhưng tổng startup còn phụ thuộc classpath, reflection, bean creation, I/O, database, logging và warm-up JVM. Không có một mốc thời gian cố định áp dụng cho mọi project.

Nếu tối ưu hiệu năng, dùng benchmark lặp lại có điều kiện kiểm soát, đo **startup time** và số auto-configuration/bean được xử lý. Không đo bằng một lần chạy đầu tiên ngay sau khi Gradle vừa tải dependency.

## 13. Thí nghiệm mở rộng để chứng minh đã hiểu

**Thí nghiệm 1 — Không có metadata:** Tạo một bản build thực nghiệm không chạy **spring-boot-autoconfigure-processor** nhưng vẫn có imports và class điều kiện. So sánh hành vi có/không có OptionalFeature. Điều kiện chức năng vẫn cần được thực thi đúng; khác biệt mong đợi nằm ở khả năng dùng metadata để lọc sớm, không phải ở kết quả bean.

**Thí nghiệm 2 — Thay đổi vị trí condition:** Đưa điều kiện classpath từ cấp class xuống cấp phương thức **@Bean**. Giải thích tại sao điều này không còn cùng semantics “loại cả candidate sớm”; đo và quan sát dựa trên báo cáo thực tế.

**Thí nghiệm 3 — Có custom bean:** Cung cấp GreetingService từ ứng dụng trước khi auto-configuration tạo bean. Xác minh chỉ còn một bean và phân biệt nguyên nhân back off với nguyên nhân thiếu OptionalFeature.

**Thí nghiệm 4 — Exclude rõ ràng:** Giữ OptionalFeature trên classpath nhưng exclude OptionalGreetingAutoConfiguration. Giải thích vì sao kết quả bean giống trường hợp thiếu class nhưng **nguyên nhân khác nhau**.

**Thí nghiệm 5 — Kiểm tra JAR:** Xóa tạm imports trong một nhánh thử nghiệm. Chạy lại test trực tiếp AutoConfigurations.of và chạy demo-app. Nêu được vì sao test condition vẫn có thể pass nhưng ứng dụng tiêu thụ không tự khám phá cấu hình.

Chỉ thay đổi **một yếu tố** trong mỗi thí nghiệm để truy nguyên nguyên nhân từ bằng chứng, rồi khôi phục source trước khi chuyển sang bài tiếp theo.

## 14. Các lỗi hiểu sai cần tránh

**“Mỗi dòng trong AutoConfiguration.imports đều được khởi tạo thành bean.”** Không đúng. Mỗi dòng chỉ công bố class ứng viên, và class đó có thể bị exclude, bị lọc sớm, không match condition hoặc không khai báo bean.

**“Lọc sớm và @ConditionalOnMissingBean là một cơ chế.”** Không đúng. Lọc sớm dựa trên thông tin đủ chắc tại thời điểm chọn class; MissingBean xét bean definitions của Spring context.

**“Có @ConditionalOnClass thì chắc chắn có bean.”** Không đúng. Đó là một điều kiện có thể cần, chưa đủ. Các condition khác và logic tạo bean vẫn áp dụng.

**“spring-autoconfigure-metadata.properties là nơi đăng ký candidates.”** Không đúng. Danh sách ứng viên nằm trong **AutoConfiguration.imports**. Metadata conditions phục vụ lọc nhanh.

**“Thiếu metadata làm @ConditionalOnClass không còn tác dụng.”** Không đúng. Cơ chế đánh giá condition không được thay thế bởi metadata; mất metadata chủ yếu làm giảm khả năng tối ưu hóa trước import.

**“Để lọc candidate chỉ cần viết @ComponentScan hẹp hơn.”** Không đúng. Component scan là đường phát hiện thành phần khác. Auto-configuration của thư viện được công bố qua imports và xử lý bằng import selector/conditions.

**“Muốn tắt một bean thì phải viết AutoConfigurationImportFilter tùy chỉnh.”** Thông thường không cần. Sử dụng **@ConditionalOnProperty**, **@ConditionalOnMissingBean** hoặc exclude theo hợp đồng tích hợp.

**“Một phép test với AutoConfigurations.of là bằng chứng về lọc sớm.”** Chưa đủ. Nó kiểm tra điều kiện khi đưa class vào context trực tiếp; để chứng minh đường discovery/import filtering cần chạy consumer khởi động theo cơ chế imports.

## 15. Checklist kết thúc bài

- [ ] Giải thích được sự khác nhau giữa **ứng viên**, **import**, **condition match** và **bean đã tạo**.
- [ ] Nêu được nhiệm vụ của **AutoConfigurationImportSelector** và **AutoConfigurationImportFilter**.
- [ ] Phân biệt ba tài nguyên **AutoConfiguration.imports**, **spring-autoconfigure-metadata.properties** và **spring-configuration-metadata.json**.
- [ ] Đặt **@ConditionalOnClass** ở cấp class để biểu thị một integration phụ thuộc classpath.
- [ ] Dùng **@ConditionalOnMissingBean** đúng mục đích nhường quyền cho bean người dùng.
- [ ] Build được JAR có đủ class, imports và metadata processor.
- [ ] Chạy test context khi OptionalFeature có mặt và bị ẩn.
- [ ] Chạy demo-app với optional-api vắng mặt và có mặt, quan sát sự khác biệt.
- [ ] Chứng minh exclude rõ ràng khác với thiếu class tùy chọn.
- [ ] Không diễn giải test condition trực tiếp như bằng chứng tuyệt đối về tối ưu hóa startup.
- [ ] Biết cách dùng **--debug**, dependency graph và kiểm tra JAR để chẩn đoán nguyên nhân.

## Kết luận

**Lọc ứng viên trước khi xử lý đầy đủ cấu hình** giúp Spring Boot tránh phân tích những auto-configuration không thể phù hợp với runtime hiện tại. Danh sách ban đầu đến từ **AutoConfiguration.imports**; các **AutoConfigurationImportFilter** có thể sử dụng thông tin như classpath và **metadata do spring-boot-autoconfigure-processor sinh** để loại sớm các class ứng viên.

Ứng viên còn lại vẫn phải đi qua các điều kiện phù hợp và cơ chế đăng ký/tạo bean của Spring. Khi thiết kế thư viện, hãy công bố class đúng trong imports, khai báo condition ở mức phù hợp, bật processor để tối ưu hóa và kiểm chứng cả test cô lập lẫn ứng dụng tiêu thụ thực. Đó là cách hiểu được **tại sao một cấu hình bị bỏ qua, bị loại sớm hoặc thực sự sinh bean**, thay vì chỉ đoán từ dependency.

## Tài liệu tra cứu

- [AutoConfigurationImportFilter — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportFilter.html)
- [AutoConfigurationImportSelector — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html)
- [Spring Boot reference — Developing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
