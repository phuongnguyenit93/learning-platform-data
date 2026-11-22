# Trình tự học auto-configuration: từ quan sát bean đến tự viết và kiểm chứng một thư viện

## Mục tiêu học tập và cách tiếp cận

Một cách học hiệu quả về **Spring Boot auto-configuration** là đi theo chiều từ **quan sát hành vi đang chạy** đến **giải thích nguyên nhân**, rồi mới **tự xây dựng** và **kiểm chứng**. Nếu bắt đầu ngay bằng việc chép một lớp có **@AutoConfiguration**, người học có thể tạo được bean nhưng chưa hiểu vì sao bean xuất hiện, khi nào nó biến mất, vì sao cấu hình người dùng được ưu tiên và liệu thư viện có được Spring Boot tự phát hiện trong ứng dụng khác hay không.

Bài thực hành này đưa người học qua sáu chặng:

1. **Quan sát:** chạy một ứng dụng Boot nhỏ, liệt kê bean hạ tầng và bean ứng dụng.
2. **Giải thích:** đọc condition evaluation, phân biệt component scanning, import auto-configuration và dependency trên classpath.
3. **Thiết kế:** xác định API, thuộc tính, điều kiện và chính sách nhường quyền của một thư viện.
4. **Hiện thực:** đóng gói lớp **@AutoConfiguration** và khai báo đúng **AutoConfiguration.imports**.
5. **Kiểm thử cô lập:** dùng **ApplicationContextRunner** để xác nhận mặc định, binding, tắt/bật và custom bean.
6. **Kiểm chứng tích hợp:** dùng thư viện trong một ứng dụng độc lập, kiểm tra bean thực tế, response và nội dung JAR.

Sau bài, người học có thể trả lời bằng **bằng chứng chạy được**: “Bean này do đâu sinh ra?”, “Điều kiện nào bật/tắt nó?”, “Ứng dụng có thể thay thế mặc định không?” và “Nếu một ứng dụng khác chỉ thêm dependency, Boot có tự nhận ra cấu hình của thư viện không?”.

**Bối cảnh ví dụ:** Java 21, Gradle 8.x và Spring Boot 3.3.x. Chúng ta xây một thư viện **greeter-autoconfigure** cung cấp đối tượng **Greeter** mặc định, một ứng dụng **demo-app** sử dụng đối tượng ấy và các kiểm thử JUnit 5. Tên “Greeter” là một tính năng nhỏ để tập trung vào cơ chế, không giả định đây là giải pháp cấu hình tổng quát cho production.

## Chặng 1 — Quan sát bean thật trong một ứng dụng Boot

### 1.1. Cần phân biệt nguồn gốc bean

Trong một ứng dụng Spring, bean có thể đến từ nhiều nguồn:

- Một class được component scanning tìm thấy, ví dụ **@Component** hoặc **@RestController** nằm trong package được quét.
- Một phương thức **@Bean** do ứng dụng khai báo.
- Một phương thức **@Bean** hoặc cấu hình được import từ thư viện, kể cả auto-configuration.
- Các cơ chế đăng ký bean khác của Spring, như một số BeanDefinitionRegistryPostProcessor.

Không thể nhìn vào việc “bean có tồn tại” để kết luận ngay “bean đó do auto-configuration tạo”. Phải quan sát **tên bean, loại bean, nguồn định nghĩa và báo cáo điều kiện**.

### 1.2. Thực hành quan sát hạ tầng Servlet trước

Tạo một ứng dụng Boot có **spring-boot-starter-web** và một class **@SpringBootApplication**. Trong class này, thêm đoạn sau để quan sát bean **DispatcherServlet**; đoạn là **một phần của class cấu hình**, không phải tệp Java độc lập:

~~~java
@Bean
ApplicationRunner inspectServlet(ApplicationContext context) {
    return args -> {
        String[] names =
            context.getBeanNamesForType(DispatcherServlet.class);
        Arrays.sort(names);
        System.out.println(
            "DispatcherServlet beans: " + Arrays.toString(names));
    };
}
~~~

Các import cần thiết:

~~~java
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.servlet.DispatcherServlet;
~~~

Trong một ứng dụng Spring Boot MVC thông thường với starter web và không đăng ký DispatcherServlet khác, dòng in dự kiến là:

~~~text
DispatcherServlet beans: [dispatcherServlet]
~~~

Điều này cho biết bean hạ tầng MVC đã xuất hiện. Nó **chưa đủ để chứng minh nguồn bean**, vì vậy cần tiếp tục xem báo cáo điều kiện ở chặng tiếp theo. Nếu ứng dụng tự khai báo servlet khác hoặc có cấu hình tùy biến, danh sách thực tế có thể khác.

### 1.3. Chụp một “mốc quan sát” trước khi can thiệp

Ghi lại trong sổ học:

| Câu hỏi | Bằng chứng cần thu thập |
| --- | --- |
| Bean nào tồn tại? | Tên và kiểu bean lấy từ ApplicationContext. |
| Bean có được Spring tạo đúng một lần theo kỳ vọng? | Số lượng bean theo kiểu và tên cụ thể. |
| Bean do người dùng viết hay do cấu hình nhập vào? | Nguồn bean definition hoặc báo cáo condition. |
| Thay đổi dependency/thuộc tính có làm thay đổi kết quả? | Kết quả trước và sau khi thay đổi một biến. |

Mục đích của chặng 1 là xây thói quen **quan sát context đang chạy** thay vì suy luận từ tên starter.

## Chặng 2 — Đọc điều kiện và hình thành giả thuyết

### 2.1. Đọc Condition Evaluation Report

Spring Boot tự cấu hình nhờ các lớp auto-configuration được nhập vào ứng dụng, sau đó đánh giá điều kiện như:

| Annotation | Câu hỏi hệ thống cần trả lời |
| --- | --- |
| **@ConditionalOnClass** | Class cần thiết có trên classpath không? |
| **@ConditionalOnBean** | Bean điều kiện có sẵn không? |
| **@ConditionalOnMissingBean** | Chưa có bean tương ứng do ứng dụng hoặc cấu hình khác cung cấp? |
| **@ConditionalOnProperty** | Thuộc tính có giá trị phù hợp không? |
| **@ConditionalOnWebApplication** | Đây có phải loại web application thích hợp? |

Bật debug của ứng dụng Boot:

~~~bash
gradle :demo-app:bootRun --args='--debug'
~~~

Nếu dùng Gradle Wrapper:

~~~bash
./gradlew :demo-app:bootRun --args='--debug'
~~~

Ở Windows PowerShell có thể dùng **.\gradlew.bat** thay **./gradlew**. Khi chạy ứng dụng thực tế, debug có thể hiển thị **Condition Evaluation Report**, gồm các mục thỏa mãn, không thỏa mãn và cấu hình bị loại trừ. Tìm nhóm điều kiện liên quan đến **DispatcherServlet** hay Web MVC, rồi ghi rõ **điều kiện nào match**. Tên class và nội dung báo cáo phụ thuộc phiên bản Spring Boot, nên không suy diễn tên mục báo cáo chỉ từ lý thuyết.

**Quan sát cần phân biệt:**

- **spring-boot-starter-web** mang các dependency cần thiết vào project.
- **Component scanning** tìm các thành phần do ứng dụng viết trong package được quét.
- **Auto-configuration** xem xét các lớp cấu hình ứng viên và chỉ áp dụng khi điều kiện phù hợp.
- **@SpringBootApplication** bao gồm cơ chế kích hoạt auto-configuration, nhưng không có nghĩa mọi lớp auto-configuration đều được áp dụng.

### 2.2. Thử nghiệm “đổi một điều kiện”

Trước khi viết thư viện, làm hai phép thử nhỏ:

1. Xem dependency tree và nhận diện các thành phần MVC/Jackson/Tomcat đi cùng starter web, ví dụ bằng lệnh **gradle :demo-app:dependencies --configuration runtimeClasspath**.
2. Thay đổi một thuộc tính đơn giản, như **server.port**, rồi quan sát server khởi động ở cổng mới. Với việc kiểm tra một bean bị thiếu, ưu tiên xem điều kiện thực tế thay vì liên tục thêm **@Bean** theo phỏng đoán.

Không nên loại dependency một cách tùy tiện chỉ để tạo lỗi khó kiểm soát. Mục tiêu là học mối liên hệ giữa **điều kiện → cấu hình có hiệu lực → bean/hành vi quan sát được**.

### 2.3. Điều kiện hoàn thành chặng 2

Người học giải thích được rằng “có dependency” không đồng nghĩa “chắc chắn có bean”, và biết tìm báo cáo điều kiện để xác định vì sao một auto-configuration có hoặc không có hiệu lực.

## Chặng 3 — Thiết kế một thư viện auto-configuration nhỏ

Chúng ta muốn thư viện tạo một bean **Greeter** với hành vi:

~~~text
Greeter.greet("Ada") → "Hello, Ada!"
~~~

Ứng dụng có thể điều chỉnh tiền tố:

~~~yaml
demo:
  greeting:
    prefix: "Xin chào"
~~~

để thu được:

~~~text
Greeter.greet("Ada") → "Xin chào, Ada!"
~~~

Các quy tắc thiết kế:

1. Khi ứng dụng có thư viện và chưa khai báo **Greeter**, tự cấu hình tạo **một bean Greeter mặc định**.
2. **demo.greeting.prefix** có giá trị mặc định **Hello** và có thể thay bằng cấu hình ngoài.
3. **demo.greeting.enabled=false** tắt bean mặc định do thư viện tạo; khi không khai báo, tính năng mặc định được bật.
4. Khi người dùng đã có **Greeter** của riêng mình, thư viện **nhường quyền** thay vì cố tạo bean thứ hai.
5. Thư viện cần được một ứng dụng khác **tự phát hiện từ JAR** mà không phải thêm **@Import** hoặc quét package nội bộ của thư viện.

Bộ kiểm chứng tương ứng sẽ bao gồm: bean mặc định, binding property, nhường quyền cho custom bean, tắt bằng property, discovery từ JAR và gọi endpoint thật.

### 3.1. Khi nào thư viện này nên dùng auto-configuration?

Auto-configuration phù hợp khi một **thư viện tái sử dụng được** muốn tự cấu hình hạ tầng hoặc bean tiện ích với các default dựa trên dependency và môi trường. Nếu một bean chỉ dành riêng cho một ứng dụng, **@Configuration** và **@Bean** trong chính ứng dụng có thể đơn giản và rõ ràng hơn.

Trong ví dụ này, Greeter là bean đơn giản nhằm tạo một bài thực nghiệm dễ đo lường; giá trị thực sự của bài học nằm ở **quy trình đăng ký, điều kiện, override và kiểm thử**.

## Chặng 4 — Xây dựng project Gradle nhiều module và thư viện

Toàn bộ mã ở phần này tạo nên một ví dụ **chạy được như project hoàn chỉnh**, không yêu cầu đọc mã nguồn từ bài học khác.

### 4.1. Cấu trúc cuối cùng

~~~text
auto-config-workshop/
├── settings.gradle
├── build.gradle
├── greeter-autoconfigure/
│   ├── build.gradle
│   ├── src/main/java/com/example/greeter/
│   │   └── Greeter.java
│   ├── src/main/java/com/example/greeter/autoconfigure/
│   │   ├── GreetingProperties.java
│   │   └── GreetingAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/greeter/autoconfigure/
│       └── GreetingAutoConfigurationTests.java
└── demo-app/
    ├── build.gradle
    ├── src/main/java/com/example/demo/
    │   ├── DemoApplication.java
    │   └── GreetingController.java
    └── src/main/resources/application.yml
~~~

Tệp **settings.gradle**:

~~~groovy
rootProject.name = 'auto-config-workshop'
include 'greeter-autoconfigure', 'demo-app'
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

**Giải thích:** Root dùng BOM của Spring Boot để các module cùng quản lý phiên bản thư viện. Java toolchain dùng JDK 21. Chúng ta **không áp dụng Boot plugin lên module thư viện**, vì thư viện cần JAR bình thường, không phải executable bootJar. Plugin Boot chỉ áp dụng ở ứng dụng tiêu thụ.

Tệp **greeter-autoconfigure/build.gradle**:

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

**Giải thích:** Thư viện dùng annotation và API của Spring Boot để tạo auto-configuration; configuration processor cung cấp metadata cho property khi đóng gói. Dependency test bao gồm JUnit 5, AssertJ và lớp hỗ trợ **ApplicationContextRunner**. Thư viện không cần starter web hay máy chủ HTTP để kiểm thử bean của chính nó.

Tệp **demo-app/build.gradle**:

~~~groovy
plugins {
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':greeter-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Ở đây ứng dụng tiêu thụ chỉ thêm **dependency tới thư viện**, ngoài starter web phục vụ REST. Không có **@Import(GreetingAutoConfiguration.class)** và không khai báo component scan tới package của thư viện.

### 4.2. Viết kiểu dữ liệu công khai của thư viện

Tệp **greeter-autoconfigure/src/main/java/com/example/greeter/Greeter.java**:

~~~java
package com.example.greeter;

import java.util.Objects;

public record Greeter(String prefix) {

    public Greeter {
        Objects.requireNonNull(prefix, "prefix");
    }

    public String greet(String name) {
        return prefix + ", " + name + "!";
    }
}
~~~

Đây là Java record hợp lệ trên Java 21. Constructor không cho phép **prefix=null**; còn định dạng lời chào giữ nguyên để kiểm thử có thể xác nhận kết quả cụ thể.

### 4.3. Định nghĩa thuộc tính cấu hình

Tệp **greeter-autoconfigure/src/main/java/com/example/greeter/autoconfigure/GreetingProperties.java**:

~~~java
package com.example.greeter.autoconfigure;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.greeting")
public class GreetingProperties {

    private String prefix = "Hello";

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
~~~

**@ConfigurationProperties** bind thuộc tính **demo.greeting.prefix** vào object. Giá trị mặc định **Hello** được dùng khi người dùng không thiết lập prefix. Trong ví dụ này ta dùng JavaBean getter/setter để cơ chế binding dễ quan sát.

Không đưa **@Component** lên GreetingProperties: đối tượng này sẽ được đăng ký chủ động bởi lớp auto-configuration qua **@EnableConfigurationProperties**, không phụ thuộc component scan của ứng dụng.

### 4.4. Viết lớp auto-configuration

Tệp **greeter-autoconfigure/src/main/java/com/example/greeter/autoconfigure/GreetingAutoConfiguration.java**:

~~~java
package com.example.greeter.autoconfigure;

import com.example.greeter.Greeter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(GreetingProperties.class)
@ConditionalOnProperty(
    prefix = "demo.greeting",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(Greeter.class)
    public Greeter greeter(GreetingProperties properties) {
        return new Greeter(properties.getPrefix());
    }
}
~~~

Chính sách ở đây có thể đọc theo thứ tự:

1. **@AutoConfiguration** biểu thị một cấu hình ứng viên dành cho cơ chế auto-configuration.
2. **@EnableConfigurationProperties** đăng ký lớp property khi cấu hình được áp dụng.
3. **@ConditionalOnProperty** bật cấu hình khi **enabled=true** hoặc chưa có thuộc tính; nếu **enabled=false**, cấu hình này không áp dụng.
4. **@ConditionalOnMissingBean(Greeter.class)** tránh đăng ký bean Greeter mặc định khi context đã có Greeter do người dùng cung cấp.
5. Phương thức **greeter(...)** lấy prefix từ configuration properties và tạo đối tượng mặc định.

**Quan trọng:** **@AutoConfiguration** chỉ định đặc tính lớp. Để Boot tìm lớp từ một JAR bên ngoài, cần đăng ký tên lớp vào tài nguyên imports ở bước tiếp theo.

Trong một thư viện lớn, bạn có thể thêm điều kiện classpath như **@ConditionalOnClass** khi thư viện phụ thuộc một API tùy chọn. Với ví dụ này **Greeter** là class luôn được đóng gói cùng JAR, nên thêm **@ConditionalOnClass(Greeter.class)** chỉ làm điều kiện thừa và dễ khiến người học hiểu nhầm cơ chế.

### 4.5. Đăng ký discovery qua AutoConfiguration.imports

Tạo chính xác tệp:

~~~text
greeter-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung **một dòng đầy đủ tên class**:

~~~text
com.example.greeter.autoconfigure.GreetingAutoConfiguration
~~~

Spring Boot 3.x đọc các tên auto-configuration trong tệp này từ các JAR trên classpath. Nhờ đó, một ứng dụng tiêu thụ có thể kích hoạt cấu hình bằng **dependency**, không cần quét package **com.example.greeter.autoconfigure**.

Nếu quên tệp imports, thử nghiệm **ApplicationContextRunner** với explicit auto-configuration vẫn có thể chạy tốt, nhưng **ứng dụng tiêu thụ sẽ không tự phát hiện cấu hình**. Đó là lý do cần cả hai lớp kiểm chứng: test điều kiện ở chặng 5 và test discovery thực tế ở chặng 6.

### 4.6. Những phần thư viện cần đóng gói

JAR thư viện cần chứa ít nhất:

- Class công khai **com.example.greeter.Greeter**.
- Class **GreetingProperties** và **GreetingAutoConfiguration**.
- Tài nguyên **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**.
- Metadata property được annotation processor sinh ra, nếu processor được bật và chạy thành công.

Không dùng **@ComponentScan** trong lớp auto-configuration chỉ để tìm mọi bean của thư viện; hãy định nghĩa/import những bean cần thiết một cách có chủ đích. Package của auto-configuration cũng nên tách khỏi package ứng dụng tiêu thụ để dễ chứng minh discovery thực sự đi qua imports.

## Chặng 5 — Kiểm chứng điều kiện bằng ApplicationContextRunner

### 5.1. Vì sao test theo context nhỏ?

**ApplicationContextRunner** giúp xây dựng một **ApplicationContext tối giản** rồi chạy auto-configuration cần kiểm tra. Nó phù hợp cho test điều kiện vì không cần khởi động cả web server. Test có thể tùy biến property, bean người dùng và cấu hình ứng viên, sau đó khẳng định số lượng bean và hành vi.

Điểm giới hạn cần nhớ: gọi **AutoConfigurations.of(GreetingAutoConfiguration.class)** trong test là **chỉ định trực tiếp** cấu hình cần test. Nó kiểm tra logic cấu hình **nhưng không chứng minh tệp AutoConfiguration.imports đã được đóng gói đúng**. Phần discovery phải được kiểm chứng riêng ở chặng 6.

### 5.2. Viết đầy đủ bốn kiểm thử thiết yếu

Tệp **greeter-autoconfigure/src/test/java/com/example/greeter/autoconfigure/GreetingAutoConfigurationTests.java**:

~~~java
package com.example.greeter.autoconfigure;

import com.example.greeter.Greeter;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(GreetingAutoConfiguration.class));

    @Test
    void createsDefaultGreeter() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(Greeter.class);
            assertThat(context.getBean(Greeter.class).greet("Ada"))
                .isEqualTo("Hello, Ada!");
        });
    }

    @Test
    void bindsCustomPrefix() {
        runner.withPropertyValues(
            "demo.greeting.prefix=Xin chào"
        ).run(context -> {
            assertThat(context).hasSingleBean(Greeter.class);
            assertThat(context.getBean(Greeter.class).greet("Ada"))
                .isEqualTo("Xin chào, Ada!");
        });
    }

    @Test
    void backsOffWhenApplicationProvidesGreeter() {
        runner.withUserConfiguration(UserGreeterConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(Greeter.class);
                assertThat(context.getBean(Greeter.class).greet("Ada"))
                    .isEqualTo("Custom, Ada!");
            });
    }

    @Test
    void doesNotCreateGreeterWhenDisabled() {
        runner.withPropertyValues(
            "demo.greeting.enabled=false"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(Greeter.class);
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserGreeterConfiguration {

        @Bean
        Greeter customGreeter() {
            return new Greeter("Custom");
        }
    }
}
~~~

### 5.3. Chạy kiểm thử và diễn giải bằng chứng

Từ thư mục root của project:

~~~bash
gradle :greeter-autoconfigure:test
~~~

Khi Gradle Wrapper được cài cho project, có thể dùng **./gradlew :greeter-autoconfigure:test**. Khi build thành công, Gradle báo task test thành công; nội dung console phụ thuộc tùy chọn Gradle và test logging, vì vậy **không nên giả lập một bản stdout cố định**.

Đọc bốn kiểm thử như bốn tình huống kiểm soát:

| Trường hợp | Thao tác | Kết luận có thể kiểm chứng |
| --- | --- | --- |
| Mặc định | Không truyền property hoặc bean riêng | Context có một Greeter, trả **Hello, Ada!**. |
| Thay cấu hình | Truyền **demo.greeting.prefix=Xin chào** | Greeter trả **Xin chào, Ada!**. |
| Người dùng cung cấp bean | Thêm class **UserGreeterConfiguration** | Chỉ một Greeter; đối tượng người dùng được sử dụng. |
| Tắt tính năng | Truyền **demo.greeting.enabled=false** | Không có Greeter do auto-configuration tạo. |

Đối với trường hợp tùy biến, điều được chứng minh là **tập bean chỉ có một Greeter do người dùng cung cấp**. Đây là bằng chứng thực tế cho **@ConditionalOnMissingBean** của thư viện. Đối với trường hợp disabled, kiểm thử không yêu cầu controller nào sử dụng Greeter nên context có thể chạy hợp lệ dù bean không tồn tại.

### 5.4. Mở rộng kiểm thử khi thư viện lớn hơn

Với một thư viện thực tế, có thể cần thêm:

- **@ConditionalOnClass**: chạy test trong classloader loại bỏ class tùy chọn để chứng minh không tạo bean khi dependency vắng mặt.
- **@ConditionalOnBean**: tạo hoặc bỏ bean tiên quyết và xác minh nhánh tương ứng.
- **@ConditionalOnWebApplication**: dùng runner phù hợp cho Servlet/Reactive/non-web context, không dùng một context loại bất kỳ.
- **Auto-configuration ordering**: dùng **before/after** khi nhiều auto-configuration thực sự phụ thuộc thứ tự.
- **Failure diagnostics**: xác minh trường hợp cấu hình người dùng sai báo lỗi hữu ích, thay vì nuốt lỗi hoặc silently tạo bean khác.

Chỉ bổ sung điều kiện khi có yêu cầu cụ thể; không thêm hàng loạt annotation để “trông giống starter”. Mỗi điều kiện phải có nguyên nhân và test tương ứng.

## Chặng 6 — Chạy ứng dụng tiêu thụ để chứng minh discovery từ JAR

### 6.1. Viết ứng dụng độc lập với package auto-configuration

Tệp **demo-app/src/main/java/com/example/demo/DemoApplication.java**:

~~~java
package com.example.demo;

import com.example.greeter.Greeter;
import java.util.Arrays;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.web.servlet.DispatcherServlet;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner inspectBeans(ApplicationContext context) {
        return args -> {
            String[] servletNames =
                context.getBeanNamesForType(DispatcherServlet.class);
            String[] greeterNames =
                context.getBeanNamesForType(Greeter.class);

            Arrays.sort(servletNames);
            Arrays.sort(greeterNames);

            System.out.println("DispatcherServlet beans: "
                + Arrays.toString(servletNames));
            System.out.println("Greeter beans: "
                + Arrays.toString(greeterNames));
        };
    }
}
~~~

Tệp **demo-app/src/main/java/com/example/demo/GreetingController.java**:

~~~java
package com.example.demo;

import com.example.greeter.Greeter;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final Greeter greeter;

    public GreetingController(Greeter greeter) {
        this.greeter = greeter;
    }

    @GetMapping("/greet")
    public String greet(
        @RequestParam(defaultValue = "Ada") String name
    ) {
        return greeter.greet(name);
    }
}
~~~

Tệp **demo-app/src/main/resources/application.yml**:

~~~yaml
demo:
  greeting:
    prefix: "Xin chào"
~~~

**Điểm then chốt:** Package ứng dụng là **com.example.demo**, trong khi auto-configuration ở **com.example.greeter.autoconfigure**. Component scanning mặc định từ **DemoApplication** không quét package bên ngoài. Nếu Greeter xuất hiện trong context, nó được kết nối qua cơ chế thư viện đã khai báo, cụ thể là resource **AutoConfiguration.imports** và điều kiện Spring Boot, không nhờ component scan tình cờ.

### 6.2. Chạy và quan sát

Từ root:

~~~bash
gradle :demo-app:bootRun
~~~

Khi ứng dụng khởi động thành công với cấu hình mặc định, hai dòng kiểm tra bean có nội dung dự kiến:

~~~text
DispatcherServlet beans: [dispatcherServlet]
Greeter beans: [greeter]
~~~

Hai dòng trên là **dòng tự in của ApplicationRunner**; chúng có thể nằm giữa các dòng log khác. Tên bean trong ví dụ xuất phát từ tên phương thức **dispatcherServlet** của cấu hình Boot và **greeter** của thư viện; ứng dụng có tùy biến có thể cho kết quả khác.

Gọi endpoint ở terminal thứ hai:

~~~bash
curl -s "http://localhost:8080/greet?name=Ada"
~~~

Response body dự kiến:

~~~text
Xin chào, Ada!
~~~

**Đây là body HTTP**, không phải toàn bộ stdout của lệnh bootRun hoặc curl trong mọi môi trường. Lời chào có dấu tiếng Việt được trả từ giá trị **demo.greeting.prefix** trong application.yml. Nếu server đổi cổng hoặc cổng 8080 đang bị chiếm, dùng đúng cổng được cấu hình khi gọi API.

### 6.3. Kiểm tra JAR đã chứa khai báo auto-configuration

Đóng gói thư viện bằng task **jar**, không cần bootJar:

~~~bash
gradle :greeter-autoconfigure:jar
~~~

Kiểm tra danh sách entry:

~~~bash
jar tf greeter-autoconfigure/build/libs/greeter-autoconfigure-1.0.0.jar
~~~

Trong danh sách phải có các đường dẫn:

~~~text
com/example/greeter/Greeter.class
com/example/greeter/autoconfigure/GreetingAutoConfiguration.class
com/example/greeter/autoconfigure/GreetingProperties.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

**Lý do phải kiểm tra:** Test **ApplicationContextRunner** có thể truyền class cấu hình trực tiếp nên vẫn pass nếu quên khai báo imports. Việc thấy đúng file nằm trong JAR cộng với ứng dụng tiêu thụ tự chạy thành công là bằng chứng mạnh hơn cho đường đi thực tế **JAR trên classpath → Boot discovery → condition → bean → API**.

### 6.4. Chứng minh cơ chế nhường quyền trong ứng dụng tiêu thụ

Sau khi thấy kết quả mặc định, thêm tệp **demo-app/src/main/java/com/example/demo/CustomGreeterConfiguration.java**:

~~~java
package com.example.demo;

import com.example.greeter.Greeter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomGreeterConfiguration {

    @Bean
    public Greeter customGreeter() {
        return new Greeter("Custom");
    }
}
~~~

Khởi động lại ứng dụng. Kết quả quan sát dự kiến:

~~~text
Greeter beans: [customGreeter]
~~~

Endpoint trả:

~~~text
Custom, Ada!
~~~

Điều này có nghĩa bean **customGreeter** do người dùng khai báo được đăng ký, còn phương thức **greeter** của auto-configuration không tạo bean mặc định khi điều kiện **@ConditionalOnMissingBean(Greeter.class)** không thỏa mãn. Nhờ vậy ứng dụng có quyền thay đổi hành vi mà không sửa mã thư viện.

Nếu giữ class custom này mà sau đó đổi **demo.greeting.enabled=false**, endpoint vẫn có thể chạy vì **customGreeter** do người dùng cung cấp; property chỉ tắt cấu hình mặc định của thư viện. Muốn thử trường hợp “không có Greeter”, kiểm thử nó bằng **ApplicationContextRunner** hoặc tách controller khỏi dependency bắt buộc, tránh nhầm lỗi khởi động do controller cần Greeter với lỗi auto-configuration.

### 6.5. Phân biệt các tầng kiểm chứng

| Tầng | Công cụ | Điều được xác nhận | Giới hạn |
| --- | --- | --- | --- |
| Kiểm tra code | Đọc annotation, property, class | Thiết kế logic và default dự định | Chưa biết runtime thực thi ra sao. |
| Test context cô lập | ApplicationContextRunner | Bean tạo/không tạo đúng theo condition | Explicit import không tự kiểm tra file imports. |
| Kiểm tra artifact | jar tf | Class và resource đã đóng gói | Chưa chứng minh runtime áp dụng cấu hình. |
| Test ứng dụng tiêu thụ | bootRun + quan sát bean | Boot thực sự phát hiện và đăng ký bean | Mới bao phủ một môi trường và classpath cụ thể. |
| Test hành vi | curl + thay property/bean | Đầu ra đổi đúng khi người dùng tùy biến | Cần thêm test ứng dụng cho trường hợp production. |

Một tính năng chỉ được coi là **đã kiểm chứng** khi có bằng chứng phù hợp từ các tầng mà nó ảnh hưởng. Nếu chỉ dựa vào một bài test trực tiếp import class, có thể bỏ sót lỗi packaging. Nếu chỉ thấy endpoint chạy, chưa chắc đã kiểm tra đầy đủ nhánh disabled và back off.

## Cách đọc kết quả khi một thí nghiệm thất bại

### Tình huống A: Test context pass nhưng demo-app thiếu Greeter

Kiểm tra lần lượt:

1. **demo-app** có dependency tới **greeter-autoconfigure** ở runtimeClasspath không?
2. JAR thư viện có đúng tệp **AutoConfiguration.imports** không?
3. Nội dung tệp có đúng fully qualified class name không, không sai package/chính tả?
4. Có exclude auto-configuration, profile/property disabled hoặc bean có sẵn nào làm thay đổi kết quả không?
5. Condition Evaluation Report nói cấu hình không được import hay có import nhưng điều kiện không match?

Đây là tình huống phổ biến nhất để phân biệt **test unit cho cấu hình** với **tính năng discovery của JAR**.

### Tình huống B: Bean tồn tại nhưng sai tiền tố lời chào

Kiểm tra **demo.greeting.prefix** có viết đúng prefix/key không; kiểm tra file cấu hình có được ứng dụng nạp không; kiểm tra nguồn cấu hình có độ ưu tiên cao hơn đang ghi đè không. Trong thư viện, chắc chắn phương thức tạo bean dùng **properties.getPrefix()** thay vì một chuỗi hard-code.

### Tình huống C: Có hai bean Greeter, controller báo ambiguous

Đọc tên và nguồn đăng ký của cả hai bean. Xác nhận custom bean có đúng kiểu **Greeter** mà **@ConditionalOnMissingBean** đang kiểm tra, và lớp auto-configuration không bị khai báo như class cấu hình ứng dụng theo cách khác. Không chữa lỗi bằng **@Primary** một cách máy móc trước khi hiểu vì sao có hai bean.

### Tình huống D: Test “disabled” pass nhưng demo-app không khởi động

Khi property **enabled=false**, auto-configuration không tạo Greeter. Nếu **GreetingController** yêu cầu Greeter bắt buộc và không có bean thay thế, ứng dụng sẽ không đáp ứng dependency. Đây là hành vi hợp lý; cần thiết kế feature toggle và consumer cho nhất quán. Kiểm thử “bean vắng mặt” và kiểm thử “toàn ứng dụng khởi động thành công” là hai mục tiêu khác nhau.

### Tình huống E: Có @AutoConfiguration nhưng không được tự phát hiện

Chỉ thêm annotation vào class là chưa đủ cho thư viện Spring Boot 3.x. Phải đảm bảo file **META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports** có trong JAR và liệt kê đúng tên class. Không giả định class bên ngoài package được quét sẽ được component scanning tìm ra.

### Tình huống F: Khi thêm custom bean, default vẫn được tạo

Kiểm tra chính xác kiểu bean, tên bean, điều kiện **@ConditionalOnMissingBean**, thời điểm các bean definition được xử lý và cách cấu hình được import. Với thư viện tự cấu hình, dùng **@AutoConfiguration** và cơ chế imports để giữ thứ tự xử lý thích hợp tương đối với cấu hình người dùng. Không giải quyết bằng cách bật ghi đè bean definition toàn cục.

## Những nguyên tắc thiết kế thư viện cần giữ sau bài

**Thứ nhất, tự cấu hình là một hợp đồng rõ ràng.** Hãy công bố bean nào có thể được tạo, thuộc tính nào điều khiển, mặc định gì, khi nào back off và điều kiện phụ thuộc gì. Người dùng không nên phải đọc source chỉ để biết cách vô hiệu hóa tính năng.

**Thứ hai, tách API và implementation khi thư viện lớn.** Một thư viện production có thể có module core, module autoconfigure và module starter. Starter là cách phân phối dependency; module autoconfigure cung cấp bean có điều kiện; core sở hữu API và nghiệp vụ. Bài tập gộp API Greeter vào module autoconfigure cho ngắn gọn. Khi phát triển thật, cân nhắc tách các module để consumer không phụ thuộc trực tiếp implementation ngoài ý muốn.

**Thứ ba, dùng thuộc tính cho khác biệt cấu hình phổ biến.** Các thay đổi như prefix, endpoint, timeout, feature enablement nên có tên property rõ và mặc định an toàn. Chỉ yêu cầu bean tùy chỉnh khi cần thay hành vi mà property không biểu đạt được.

**Thứ tư, điều kiện phải có nguyên nhân.** **@ConditionalOnMissingBean** phục vụ khả năng override; **@ConditionalOnProperty** phục vụ tùy chọn bật/tắt. Không thêm **@ConditionalOnClass** khi class luôn nằm trong cùng JAR và không thật sự tùy chọn.

**Thứ năm, tránh rò rỉ component scan ra ngoài.** Cấu hình thư viện nên đăng ký bean qua các phương thức có chủ đích và **AutoConfiguration.imports**. Không yêu cầu mọi ứng dụng thêm **scanBasePackages** tới package nội bộ để thư viện hoạt động.

**Thứ sáu, phải kiểm chứng cả packaging và runtime.** Test logic condition có thể pass trong khi file imports thất lạc. Kiểm tra classpath/JAR và chạy một ứng dụng tiêu thụ khác package là bước thiết yếu.

**Thứ bảy, tách bài học về chức năng và vận hành.** Demo này chứng minh auto-configuration, chưa chứng minh chất lượng production về bảo mật, cấu hình bí mật, hiệu năng, tương thích nhiều phiên bản, concurrency, logging hay binary compatibility. Các vấn đề ấy cần được đánh giá riêng khi thư viện được phát hành.

## Checklist tự đánh giá theo thứ tự học

Đánh dấu sau khi thật sự có bằng chứng, không chỉ sau khi đọc lý thuyết:

- [ ] Liệt kê được ít nhất một bean hạ tầng Boot và xác định nguồn đăng ký của nó.
- [ ] Đọc được Positive/Negative Matches trong Condition Evaluation Report của ứng dụng thực tế.
- [ ] Giải thích được sự khác nhau giữa starter, component scanning và auto-configuration.
- [ ] Mô tả rõ API, property, default và điều kiện back off trước khi viết code.
- [ ] Biên dịch được JAR thư viện chứa **Greeter**, **GreetingProperties** và **GreetingAutoConfiguration**.
- [ ] Kiểm tra có đúng tài nguyên **AutoConfiguration.imports** trong JAR.
- [ ] Chạy pass test tạo bean mặc định, thay prefix, custom bean và disabled.
- [ ] Chạy được demo-app không dùng **@Import** trực tiếp vào auto-configuration.
- [ ] Quan sát được bean Greeter và response HTTP như mong đợi.
- [ ] Thêm custom bean và chứng minh default bean nhường quyền.
- [ ] Giải thích được vì sao test cô lập không thay thế kiểm chứng discovery qua JAR.

## Bài tập mở rộng để chứng minh đã hiểu

1. **Đổi điều kiện:** chuyển **matchIfMissing=true** thành **false**. Dự đoán test nào thay đổi trước khi chạy; cập nhật test để khẳng định chính sách mới. Sau khi học xong, khôi phục thiết kế gốc.
2. **Thêm thuộc tính:** thêm **suffix** vào **GreetingProperties**, chỉnh Greeter và kiểm chứng giá trị mặc định lẫn giá trị tùy chỉnh bằng test.
3. **Thiếu imports:** tạm loại bỏ tài nguyên imports trong một nhánh thực nghiệm; chạy lại ApplicationContextRunner và demo-app, giải thích vì sao kết quả khác nhau.
4. **Thêm classpath condition thật:** nếu thư viện mới có dependency tùy chọn, tạo test classloader phù hợp để xác minh bean được bỏ qua khi dependency biến mất.
5. **Đóng gói thành starter:** tách core, autoconfigure và starter để ứng dụng tiêu thụ có thể chỉ chọn một starter dependency; kiểm tra rằng startup/discovery vẫn đúng.

Mỗi lần thay đổi **một yếu tố**, ghi dự đoán → chạy → quan sát → kết luận. Quy trình này giúp người học phân biệt nguyên nhân và hiện tượng thay vì chỉ sửa code đến khi “chạy được”.

## Tổng kết

Trình tự học đúng bản chất auto-configuration bắt đầu từ **quan sát bean hiện hữu**, tiếp đến **đọc các điều kiện tạo bean**, rồi **thiết kế hợp đồng mặc định**, **đăng ký cấu hình thư viện**, **kiểm thử bằng context nhỏ** và cuối cùng **chạy một ứng dụng tiêu thụ để chứng minh discovery thực tế**.

Bài tập Greeter cung cấp một chuỗi bằng chứng khép kín: thư viện xuất bản **AutoConfiguration.imports**, Boot nhập **GreetingAutoConfiguration**, điều kiện kiểm soát việc tạo bean **Greeter**, property cấu hình hành vi, bean người dùng có thể thay mặc định, và cả test lẫn ứng dụng chạy thật xác nhận kết quả. Khi nắm được đường đi này, người học có nền tảng để đọc và viết auto-configuration cho các thư viện hạ tầng phức tạp hơn.
