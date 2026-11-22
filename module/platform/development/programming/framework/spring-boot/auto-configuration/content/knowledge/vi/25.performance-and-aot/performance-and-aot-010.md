# Kiểm chứng thư viện tự cấu hình trên JVM và native theo phạm vi hỗ trợ

## 1. Mục tiêu: kiểm tra thư viện trong ứng dụng thực sự tiêu thụ nó

Một thư viện Spring Boot auto-configuration có thể chạy tốt trên JVM nhưng thất bại khi ứng dụng được xử lý AOT hoặc biên dịch thành GraalVM Native Image. Nguyên nhân thường nằm ở khác biệt giữa runtime JVM và môi trường native: classpath được cố định khi build, một số thao tác reflection cần runtime hints, tài nguyên classpath có thể không được đóng gói nếu không được khai báo, và các condition quyết định bean được đánh giá trong quá trình AOT.

Vì vậy, kiểm chứng native không chỉ là chạy lại unit test với một cờ build khác. Cần chứng minh rằng thư viện được phát hiện từ artifact phân phối, auto-configuration được áp dụng trong đúng môi trường, AOT xử lý được context của ứng dụng tiêu thụ, các runtime hints cần thiết được sinh ra, và native executable thực hiện được hành vi mà thư viện công bố.

Bài học dùng **Spring Boot 3.3.13, Spring Framework 6.1.21, Java 17+ và Maven**. Phạm vi gồm:

1. Kiểm thử auto-configuration và điều kiện bean trên JVM.
2. Kiểm thử nội dung RuntimeHints mà thư viện đăng ký.
3. Tạo consumer project riêng để kiểm thử JAR thư viện đã đóng gói.
4. Chạy Spring AOT processing và kiểm tra generated application trên JVM.
5. Biên dịch và chạy native executable.
6. Chạy native integration tests bằng Native Build Tools.
7. Xác định chính xác phiên bản, dependency, hệ điều hành và kiến trúc mà thư viện tuyên bố hỗ trợ.

**Nguyên tắc:** unit tests trên JVM kiểm tra phần lớn hành vi; consumer integration tests kiểm tra cách thư viện được sử dụng; AOT/native tests tập trung vào những điểm có thể khác khi chạy native. Không được kết luận “native supported” chỉ vì code biên dịch hoặc unit tests trên JVM đều pass.

## 2. Phân biệt ba môi trường kiểm thử

| Môi trường | Cách chạy | Bằng chứng thu được | Giới hạn |
| --- | --- | --- | --- |
| JVM thông thường | `mvn test`, `ApplicationContextRunner`, `@SpringBootTest` | Điều kiện auto-configuration, bean mặc định/override, binding, logic service | Không chứng minh AOT code hay native reachability |
| JVM dùng AOT-generated code | Build với AOT, chạy `java -Dspring.aot.enabled=true -jar ...` | Generated initialization code có thể khởi động và chạy trên JVM | Không thay thế GraalVM native compilation/runtime |
| Native Image | Biên dịch bằng GraalVM/Native Build Tools, chạy binary hoặc native test | Reachability, reflection/resource hints, khởi động và hành vi trong native executable | Chỉ xác nhận tổ hợp version, dependency, OS/architecture đã thực sự kiểm thử |

Spring Boot khuyến nghị tiếp tục dùng JVM để phát triển phần lớn unit và integration tests vì thời gian build nhanh và IDE hỗ trợ tốt. Native testing nên tập trung vào những điểm khác biệt của native, ví dụ AOT processing, reflection, resources, proxies và serialization.

### 2.1. Vì sao phải có consumer application?

Auto-configuration library là artifact được ứng dụng khác đưa vào dependency graph. Bản thân library không xác định toàn bộ:

- Main application class và component scan.
- Các dependency thực tế có trên runtime classpath.
- Property sources và profile của ứng dụng.
- User-defined beans có làm auto-configuration back off hay không.
- Điều kiện nào khớp khi Spring AOT chuẩn bị BeanFactory.
- Các code path của thư viện mà ứng dụng thực sự gọi.

Vì vậy, kiểm thử thư viện trong module của chính nó là cần thiết nhưng chưa đủ. Nên có một **consumer project độc lập** phụ thuộc vào JAR đã được `install` hoặc publish, rồi kiểm thử auto-configuration qua đúng cơ chế discovery của Spring Boot.

Consumer project cũng là nơi phù hợp để chạy `process-aot`, `native:compile` và `nativeTest`. Native Image là artifact của ứng dụng hoàn chỉnh, không phải một phép biên dịch riêng cho JAR thư viện.

## 3. Spring AOT thay đổi điều gì?

### 3.1. AOT phân tích ApplicationContext ở build time

Spring AOT phân tích ApplicationContext trong quá trình build và tạo các tài nguyên tối ưu hóa, có thể bao gồm:

- Java source và bytecode được sinh.
- Bean registration/initialization code.
- Runtime hints cho reflection, resource loading, serialization và JDK proxies.
- Các tài nguyên hỗ trợ khởi tạo context trong native image.

AOT là bước bắt buộc để chạy Spring ApplicationContext trong GraalVM Native Image. Spring Boot Maven Plugin cung cấp `process-aot` cho application code và `process-test-aot` cho các JUnit 5 tests sử dụng Spring TestContext Framework.

### 3.2. Condition được đánh giá tại build time

Đây là khác biệt quan trọng nhất đối với auto-configuration library.

Trong quá trình AOT, BeanFactory được chuẩn bị đầy đủ và các condition được đánh giá. Ví dụ:

~~~java
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
@Bean
GreetingService greetingService() {
    return new DefaultGreetingService();
}
~~~

Nếu `acme.greeting.enabled=false` tại thời điểm AOT, bean definition có thể không được đưa vào generated application. Việc đổi property thành `true` khi native executable chạy không tự làm bean definition xuất hiện trở lại.

Các giới hạn cần nhớ:

- Classpath được cố định và xác định đầy đủ tại build time.
- Tập bean được tạo không thể tùy ý thay đổi ở runtime.
- `@Profile` và profile-specific configuration cần được chọn tại build time.
- Property ảnh hưởng đến sự hiện diện của bean qua `@Conditional` chỉ được xét tại build time.
- Các bean definition đăng ký bằng instance supplier hoặc singleton trực tiếp qua `registerSingleton` có giới hạn khi chuyển đổi AOT.

Nếu ứng dụng cần hai tập bean khác nhau theo môi trường, hãy build hai AOT/native artifacts với build-time environment tương ứng. Nếu chỉ cần bật/tắt hành vi khi ứng dụng đang chạy, cân nhắc giữ bean trong context và để bean đọc property runtime thay vì dùng property đó để loại bean khỏi context.

### 3.3. Classpath cũng bị cố định

Một dependency chỉ có trong máy developer hoặc test runtime nhưng không có trong dependency graph lúc build native sẽ không thể được nạp động sau khi binary đã được tạo.

Đối với thư viện auto-configuration:

- Khai báo dependency cần thiết đúng scope/runtime configuration.
- Tránh dựa vào classpath scanning hoặc class loading tùy ý mà không có thiết kế native tương ứng.
- Kiểm tra optional dependency qua `@ConditionalOnClass` và cấu trúc cấu hình an toàn khi class không tồn tại.
- Không dùng reflection hoặc proxy động mà không cung cấp hint phù hợp.
- Kiểm thử từng biến thể dependency mà thư viện tuyên bố hỗ trợ.

## 4. Runtime hints: cầu nối cho những thao tác native không thể suy ra tự động

### 4.1. Những trường hợp thường cần hint

Native Image sử dụng phân tích reachability để quyết định code và tài nguyên nào được đưa vào executable. Một số thao tác khó suy ra đầy đủ khi build, chẳng hạn:

- Reflection theo tên class, method hoặc constructor được tính ở runtime.
- Đọc tài nguyên classpath theo tên động.
- Java serialization.
- Tạo JDK dynamic proxy.
- Binding DTO qua reflection trong một số luồng JSON.

Spring AOT tự động suy ra nhiều hint từ các cấu trúc Spring quen thuộc. Tuy nhiên, thư viện có logic riêng hoặc sử dụng reflection/resource theo cách không thể phân tích tĩnh có thể cần khai báo bổ sung.

### 4.2. RuntimeHintsRegistrar

Spring Framework cung cấp `RuntimeHintsRegistrar` để thư viện đăng ký yêu cầu native:

~~~java
package com.acme.greeting.autoconfigure;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class GreetingRuntimeHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern(
            "templates/greeting.txt"
        );
    }
}
~~~

Ví dụ khai báo tài nguyên `templates/greeting.txt` phải có trong native image. API cũng hỗ trợ đăng ký reflection, serialization và JDK proxy khi thư viện thực sự cần.

Ví dụ đăng ký method cho reflection:

~~~java
Method method = ReflectionUtils.findMethod(
    GreetingTemplate.class,
    "render",
    String.class
);
hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
~~~

Ví dụ đăng ký proxy hoặc serialization:

~~~java
hints.proxies().registerJdkProxy(GreetingExtension.class);
hints.serialization().registerType(GreetingSnapshot.class);
~~~

Các đoạn trên là phần minh họa API; chỉ thêm hint cho type/member thực sự được thư viện sử dụng. Hint thừa có thể làm tăng kích thước image và che giấu những dependency động chưa được hiểu rõ.

### 4.3. Gắn hints vào auto-configuration

Một thư viện có thể kích hoạt registrar bằng `@ImportRuntimeHints` trên class cấu hình hoặc bean factory method:

~~~java
package com.acme.greeting.autoconfigure;

import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
@ImportRuntimeHints(GreetingRuntimeHints.class)
public class GreetingAutoConfiguration {
    // Các bean của thư viện.
}
~~~

Annotation `@ImportRuntimeHints` thuộc package `org.springframework.context.annotation` trong Spring Framework 6.1. Registrar được Spring AOT phát hiện và gọi trong quá trình build. Không cần tạo một bean `GreetingRuntimeHints` để gọi nó lúc ứng dụng khởi động.

### 4.4. Kiểm thử hints bằng RuntimeHintsPredicates

Có thể kiểm thử trực tiếp nội dung hint mà registrar khai báo:

~~~java
package com.acme.greeting.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingRuntimeHintsTests {

    @Test
    void registersGreetingTemplateResource() {
        RuntimeHints hints = new RuntimeHints();

        new GreetingRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.resource()
                .forResource("templates/greeting.txt")
        ).accepts(hints);
    }
}
~~~

Test này xác nhận registrar đã khai báo resource hint. Nó không chứng minh GraalVM đã đưa resource vào binary hoặc ứng dụng đã đọc được resource trong native runtime. Cần native integration test để kiểm chứng hai bước đó.

### 4.5. Khi nào dùng @RegisterReflectionForBinding?

Với DTO cần serialize/deserialize, Spring thường suy ra reflection hints từ các controller request/response model. Khi làm việc trực tiếp với `WebClient`, `RestClient` hoặc `RestTemplate`, một số kiểu dữ liệu có thể cần khai báo binding rõ ràng bằng `@RegisterReflectionForBinding`.

Với `@ConfigurationProperties`, Spring AOT tự tạo reflection hints cho nhiều trường hợp. Nested configuration properties không phải inner class cần được đánh dấu `@NestedConfigurationProperty` ở vị trí phù hợp để AOT nhận diện cấu trúc lồng và hỗ trợ binding trong native image.

### 4.6. Tracing agent và static hints

Nếu chưa biết thiếu hint nào, GraalVM Native Image tracing agent có thể ghi lại reflection, resource và proxy usage khi chạy ứng dụng trên JVM:

~~~bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config/ \
  -jar target/native-consumer-1.0.0.jar
~~~

Sau khi ứng dụng chạy, hãy gọi các luồng nghiệp vụ cần kiểm tra rồi dừng ứng dụng để agent ghi file cấu hình.

Lưu ý:

- Tracing agent chỉ ghi lại các code path đã thực sự được chạy.
- Nếu chạy test, output có thể chứa hint chỉ phục vụ JUnit/Mockito/test infrastructure.
- Đọc và lọc kết quả trước khi đưa vào thư viện.
- Không coi file agent sinh ra là bằng chứng đầy đủ cho mọi luồng runtime.

Nếu cần khai báo GraalVM JSON hints thủ công, đặt file trong `src/main/resources/META-INF/native-image/*/*/`. Tránh ghi đè thư mục metadata được Spring AOT sinh ra tại `META-INF/native-image/{groupId}/{artifactId}/`; dùng thư mục bổ sung riêng, ví dụ `META-INF/native-image/com.acme/greeting-additional-hints/`.

## 5. Xây dựng ma trận kiểm thử cho thư viện

Một bộ test có trách nhiệm nên phân chia theo mục tiêu:

| Nhóm kiểm thử | Vị trí nên đặt | Điều cần chứng minh |
| --- | --- | --- |
| JVM unit test | Module library | Logic thuần, formatter, parser, thuật toán và error handling |
| Auto-configuration test | Module library | Condition, default bean, user override, property missing/disabled |
| Runtime hints test | Module library | Registrar đã khai báo đúng reflection/resource/proxy/serialization hint |
| Consumer integration test | Consumer application | JAR thư viện được discovery và bean hoạt động qua Spring Boot |
| AOT JVM smoke test | Consumer application | Generated initialization code khởi động được |
| Native integration test | Consumer application | Context, bean và luồng nghiệp vụ hoạt động trong native image |
| Dependency/platform compatibility test | CI matrix | Tổ hợp Boot, JDK, GraalVM, dependency, OS/architecture được hỗ trợ |

Không cần đưa mọi unit test vào native image. Native compilation tốn thời gian và thường phù hợp với integration tests có Spring TestContext hoặc các luồng cần kiểm chứng native-specific.

### 5.1. Kiểm thử auto-configuration trên JVM bằng ApplicationContextRunner

Ví dụ một auto-configuration:

~~~java
package com.acme.greeting.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ImportRuntimeHints;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
@ImportRuntimeHints(GreetingRuntimeHints.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new ClasspathGreetingService();
    }
}
~~~

`GreetingService` là interface của thư viện:

~~~java
package com.acme.greeting.autoconfigure;

public interface GreetingService {
    String greet(String name);
}
~~~

Implementation đọc template từ classpath:

~~~java
package com.acme.greeting.autoconfigure;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

public final class ClasspathGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        ClassPathResource resource =
            new ClassPathResource("templates/greeting.txt");

        try (InputStream input = resource.getInputStream()) {
            String prefix = StreamUtils.copyToString(
                input,
                StandardCharsets.UTF_8
            ).trim();

            return prefix + ", " + name;
        }
        catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }
}
~~~

Tài nguyên `src/main/resources/templates/greeting.txt` có nội dung:

~~~text
Hello
~~~

Đăng ký auto-configuration trong JAR bằng file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung file:

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

### 5.2. Test condition và user override

Đặt test trong module `greeting-autoconfigure`:

~~~java
package com.acme.greeting.autoconfigure;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    GreetingAutoConfiguration.class
                )
            );

    @Test
    void createsDefaultServiceWhenEnabled() {
        this.contextRunner
            .withPropertyValues("acme.greeting.enabled=true")
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(GreetingService.class);

                assertThat(context.getBean(GreetingService.class)
                    .greet("Ada"))
                    .isEqualTo("Hello, Ada");
            });
    }

    @Test
    void doesNotCreateServiceWhenDisabled() {
        this.contextRunner
            .withPropertyValues("acme.greeting.enabled=false")
            .run(context ->
                assertThat(context)
                    .doesNotHaveBean(GreetingService.class)
            );
    }

    @Test
    void backsOffWhenUserProvidesService() {
        this.contextRunner
            .withPropertyValues("acme.greeting.enabled=true")
            .withUserConfiguration(CustomGreetingConfiguration.class)
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(GreetingService.class);

                assertThat(context.getBean(GreetingService.class)
                    .greet("Ada"))
                    .isEqualTo("Custom, Ada");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return name -> "Custom, " + name;
        }
    }
}
~~~

Các test này xác nhận behavior trên JVM:

- Property bật và không có user bean: starter tạo default service.
- Property tắt: service không được đăng ký.
- Có user bean: default service back off và custom implementation được dùng.

Đây là các kiểm thử nhanh, cô lập, thích hợp chạy thường xuyên trong quá trình phát triển.

## 6. Consumer application: kiểm tra artifact thư viện đã đóng gói

### 6.1. Vì sao consumer cần là project riêng?

Nếu test chạy trực tiếp trong module thư viện, classloader có thể sử dụng `target/classes` và resource source thay vì JAR đã phát hành. Consumer project riêng giúp xác nhận:

- Auto-configuration imports resource có trong JAR.
- Dependency runtime được resolve đúng.
- Ứng dụng phát hiện cấu hình qua `@SpringBootApplication`.
- `@ConditionalOnProperty` và `@ConditionalOnMissingBean` có kết quả mong đợi.
- Resource trong dependency JAR có thể được đọc.

### 6.2. Consumer POM

Project `native-consumer` dùng Spring Boot 3.3.13 và dependency tới library đã được `install`:

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
    <artifactId>native-consumer</artifactId>
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
            <groupId>com.acme</groupId>
            <artifactId>greeting-autoconfigure</artifactId>
            <version>1.0.0</version>
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

            <plugin>
                <groupId>org.graalvm.buildtools</groupId>
                <artifactId>native-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Hai plugin trong `build/plugins` là cần thiết: `spring-boot-maven-plugin` xử lý AOT/application packaging, còn `native-maven-plugin` cung cấp native image goals. `spring-boot-starter-parent` quản lý version plugin và cung cấp cấu hình cho các profile `native`, `nativeTest`.

### 6.3. Cấu hình build-time

File `src/main/resources/application.properties` của consumer:

~~~properties
acme.greeting.enabled=true
~~~

Property này phải có giá trị phù hợp khi `process-aot` chạy, vì condition quyết định bean được đánh giá ở build time. Nếu build-time property là `false`, generated application có thể không chứa default service.

### 6.4. Main application

File `src/main/java/com/example/consumer/NativeConsumerApplication.java`:

~~~java
package com.example.consumer;

import com.acme.greeting.autoconfigure.GreetingService;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NativeConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            NativeConsumerApplication.class,
            args
        );
    }

    @Bean
    CommandLineRunner printGreeting(GreetingService service) {
        return args -> System.out.println(service.greet("Ada"));
    }
}
~~~

Package ứng dụng là `com.example.consumer`; auto-configuration nằm trong `com.acme.greeting.autoconfigure`. Component scan mặc định không cần quét package thư viện. Boot phát hiện thư viện qua `AutoConfiguration.imports`.

### 6.5. Consumer integration test

File `src/test/java/com/example/consumer/GreetingNativeIntegrationTests.java`:

~~~java
package com.example.consumer;

import com.acme.greeting.autoconfigure.GreetingService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class GreetingNativeIntegrationTests {

    @Autowired
    private GreetingService greetingService;

    @Test
    void autoConfiguredServiceCanLoadLibraryResource() {
        assertThat(greetingService)
            .isNotNull();

        assertThat(greetingService.greet("Ada"))
            .isEqualTo("Hello, Ada");
    }
}
~~~

Test này chạy trong consumer context, dùng dependency JAR và resource của thư viện. Khi chạy trên JVM, nó xác nhận discovery, bean creation và resource loading trong môi trường JVM thông thường. Khi được xử lý bởi test AOT và chạy trong native image, nó còn kiểm chứng generated test context và resource hint.

## 7. Quy trình build và kiểm chứng theo từng lớp

### 7.1. Bước 1 — Build/install library và chạy JVM tests

Trong thư mục `greeting-autoconfigure`:

~~~bash
mvn clean install
~~~

Kết quả mong đợi:

- Library compile thành công.
- `GreetingAutoConfigurationTests` pass.
- `GreetingRuntimeHintsTests` pass.
- Artifact `com.acme:greeting-autoconfigure:1.0.0` được cài vào local Maven repository.

Nếu library có nhiều module, build các module cần thiết theo thứ tự dependency.

### 7.2. Bước 2 — Chạy consumer JVM tests

Trong thư mục `native-consumer`:

~~~bash
mvn clean test
~~~

Kết quả mong đợi:

- Consumer context khởi động.
- Auto-configuration được tìm thấy từ JAR dependency.
- Bean `GreetingService` được đăng ký.
- `templates/greeting.txt` được đọc thành công.
- Assertion trả về `Hello, Ada`.

Nếu test thất bại, kiểm dependency tree, version artifact được resolve và nội dung `AutoConfiguration.imports` trong JAR trước khi chuyển sang AOT.

### 7.3. Bước 3 — Sinh AOT assets và đóng gói executable JAR

Với Maven, `spring-boot-starter-parent` cung cấp profile `native`. Khi hai plugin đã được khai báo trong consumer POM, profile này kích hoạt `process-aot` và cung cấp cấu hình phù hợp cho Native Build Tools.

Chạy:

~~~bash
mvn -Pnative clean package
~~~

Lệnh này tạo executable JAR có generated AOT assets. Thư mục generated thường có cấu trúc:

~~~text
target/
├── native-consumer-1.0.0.jar
└── spring-aot/
    └── main/
        ├── classes/
        ├── resources/
        └── sources/
~~~

Đường dẫn và số lượng file generated có thể thay đổi theo cấu hình plugin. Không nên assert tên class generated nội bộ như một public contract của thư viện.

### 7.4. Bước 4 — Chạy AOT-generated code trên JVM

Trước khi biên dịch native image, chạy executable JAR trên JVM nhưng bật AOT initialization:

~~~bash
java -Dspring.aot.enabled=true -jar target/native-consumer-1.0.0.jar
~~~

Dòng do chương trình mẫu in ra:

~~~text
Hello, Ada
~~~

Đây là phép kiểm tra có giá trị vì nó chạy generated AOT code trên JVM. Nếu AOT-generated context thiếu bean, sai condition hoặc thiếu một phần generated initialization, lỗi có thể xuất hiện trước khi phải chờ native compilation.

**Lưu ý:** JAR phải được build với AOT assets, ví dụ qua `mvn -Pnative clean package`. Chạy JAR build thông thường với `spring.aot.enabled=true` không chứng minh AOT đã được tạo.

### 7.5. Bước 5 — Biên dịch native executable

Nếu đã cài GraalVM Native Image và Native Build Tools, trong consumer project chạy:

~~~bash
mvn -Pnative native:compile
~~~

Native executable được tạo trong thư mục `target/`. Tên file thường theo artifact name; trên Windows có thể có đuôi `.exe`.

Chạy trên Linux/macOS:

~~~bash
./target/native-consumer
~~~

Chạy trên Windows PowerShell:

~~~powershell
.\target\native-consumer.exe
~~~

Dòng do chương trình mẫu in ra:

~~~text
Hello, Ada
~~~

Nếu build native thất bại, phân loại lỗi theo nhóm:

- AOT không xử lý được một bean definition hoặc cấu hình.
- Thiếu reflection/resource/proxy/serialization hint.
- Dependency bên thứ ba chưa có reachability metadata.
- Dependency hoặc class chỉ tồn tại ở compile/test scope.
- Native compiler, toolchain, OS hoặc architecture không phù hợp.

Không thêm hint rộng một cách mù quáng chỉ để làm build pass. Hãy xác định code path và loại metadata đang thiếu.

### 7.6. Bước 6 — Chạy Spring native integration tests

Spring Boot 3.3 hỗ trợ AOT processing cho JUnit 5 tests dùng Spring TestContext Framework. `process-test-aot` sinh `ApplicationContextInitializer` code cho các test context phù hợp.

Nếu consumer dùng `spring-boot-starter-parent` và đã khai báo cả `spring-boot-maven-plugin` lẫn `native-maven-plugin`, có thể chạy profile `nativeTest`:

~~~bash
mvn -PnativeTest test
~~~

Trong profile này:

1. Test context được phân tích để xác định ApplicationContext cần thiết.
2. AOT xử lý các context test và sinh assets.
3. GraalVM tạo native test image.
4. JUnit TestEngine được đưa vào image cùng danh sách test được phát hiện.
5. Native image chạy test và báo kết quả.

`GreetingNativeIntegrationTests` là ví dụ test Spring TestContext phù hợp với luồng này. Các unit tests thuần như test registrar hoặc test parser nên tiếp tục chạy trên JVM; không cần ép mọi test vào native image.

Native tests mất nhiều thời gian hơn JVM tests. Có thể chạy thường xuyên trên CI nightly hoặc một pipeline riêng, trong khi JVM tests chạy ở mọi pull request.

## 8. Kiểm tra đúng điều kiện build-time và runtime

### 8.1. Property nào được dùng lúc AOT?

Trong ví dụ, `acme.greeting.enabled=true` nằm trong `application.properties` của consumer. Khi `process-aot` tạo BeanFactory, condition khớp và default `GreetingService` được đưa vào generated context.

Nếu build với:

~~~properties
acme.greeting.enabled=false
~~~

condition không khớp; bean có thể không xuất hiện trong AOT output. Khi chạy native binary, đặt property thành `true` không làm Spring quay lại xử lý toàn bộ auto-configuration để tạo bean mới.

### 8.2. Feature flag cần thay đổi lúc runtime

Nếu yêu cầu sản phẩm là bật/tắt tính năng sau khi deploy, hãy cân nhắc thiết kế:

- Đưa bean service vào context ổn định ở build time.
- Bind property runtime vào `@ConfigurationProperties`.
- Để service đọc giá trị runtime và quyết định hành vi trong method.
- Chỉ dùng `@ConditionalOnProperty` khi quyết định có/không có bean thực sự có thể cố định cho artifact.

Nếu muốn các deployment có tập bean khác nhau, build native artifacts riêng với profile/property build-time tương ứng và kiểm thử từng artifact.

### 8.3. Profile và classpath

`@Profile` và dependency classpath cũng tham gia quyết định build-time. Nếu consumer có nhiều profile:

- Chọn profile trước khi chạy `process-aot`.
- Không mong đợi native binary tự nạp một profile mới để tạo bean definition chưa được generated.
- Build/test từng profile được hỗ trợ.
- Ghi rõ profile và dependency set trong support matrix.

## 9. Đánh giá dependency và phạm vi hỗ trợ native

### 9.1. Native support là thuộc tính của dependency graph

Một auto-configuration có thể chỉ dùng API Spring được hỗ trợ native, nhưng dependency mà bean tạo ra có thể dùng reflection hoặc resource loading động mà chưa có hints. Khi đó toàn bộ consumer app vẫn có thể thất bại khi biên dịch native.

Spring Boot không cung cấp sẵn hints cho mọi thư viện bên thứ ba; hệ sinh thái GraalVM Reachability Metadata cung cấp metadata cho nhiều dependency. Cần xác nhận dependency version cụ thể có native metadata hay không.

### 9.2. Ma trận hỗ trợ nên được công bố

Ví dụ bảng support matrix cho thư viện:

| Thành phần | Phạm vi đã kiểm thử theo tài liệu Boot 3.3.13 | Cần ghi rõ trong CI |
| --- | --- | --- |
| Spring Boot | 3.3.13 | Minor/patch line và version tối thiểu |
| Spring Framework | 6.1.21 trở lên theo yêu cầu Boot 3.3.13 | Version thực tế được dependency management chọn |
| Java | 17 đến 23 | JDK vendor và patch cụ thể |
| GraalVM Community | 22.3 trở lên | Distribution, patch và native-image version |
| Native Build Tools | 0.10.6 | Plugin version thực tế |
| Maven | 3.6.3 trở lên | Maven wrapper/version của CI |
| Gradle | 7.x từ 7.5 hoặc 8.x | Wrapper version thực tế |
| OS/architecture | Chỉ target đã build và chạy | Linux x64, Linux ARM64, Windows x64… theo thực tế |

Bảng là yêu cầu nền tảng theo tài liệu Spring Boot 3.3.13, không phải lời tuyên bố rằng thư viện mẫu đã được chạy trên mọi tổ hợp. Hãy điền kết quả thực tế của CI.

Spring Boot 3.3.13 yêu cầu Java 17 và tương thích tới Java 23; yêu cầu native image gồm GraalVM 22.3 trở lên và Native Build Tools 0.10.6. Maven tối thiểu là 3.6.3; Gradle hỗ trợ dòng 7.x (từ 7.5) và 8.x. Dependency bên thứ ba có thể có yêu cầu riêng hoặc cao hơn.

### 9.3. Native image phụ thuộc target platform

Native executable được tạo cho hệ điều hành và kiến trúc mục tiêu. Không suy ra binary build trên Linux x64 có thể chạy trên Windows hoặc ARM64.

Với thư viện có tuyên bố hỗ trợ native:

- Build trên từng target platform quan trọng.
- Chạy binary trên target đó.
- Kiểm resource, file path, charset, TLS, native library và dependency có hành vi phụ thuộc OS.
- Lưu build logs và version toolchain để tái tạo kết quả.
- Không tuyên bố hỗ trợ platform chỉ dựa trên việc native compilation ở một platform khác thành công.

## 10. Những lỗi thường gặp khi chuyển auto-configuration sang native

| Lỗi / hiểu nhầm | Vì sao xảy ra | Cách xử lý |
| --- | --- | --- |
| JVM tests pass nên native chắc chắn pass | JVM cho phép một số reflection/resource lookup động không có trong native | Thêm hints tests, AOT smoke test và native integration test |
| Chỉ test library module | Không kiểm consumer dependency graph và main application | Dùng consumer project độc lập phụ thuộc JAR đã publish |
| `@ConditionalOnProperty` được kỳ vọng thay đổi bean sau deploy | Condition đã được đánh giá khi AOT tạo BeanFactory | Đặt property ở build time hoặc chuyển feature decision vào runtime service |
| AOT build dùng sai profile | Bean definitions của profile khác không được sinh | Chọn profile trước khi process AOT và build artifact riêng |
| Resource có trong JAR JVM nhưng mất trong native | Resource không được đưa vào native image reachability set | Đăng ký resource hint và chạy native test |
| Reflection hoạt động trên JVM nhưng fail native | GraalVM không biết thành viên nào được gọi qua reflection | Đăng ký chính xác reflection hints |
| Proxy động không được tạo | Proxy interface không được khai báo cho native | Đăng ký JDK proxy hint |
| JSON DTO không bind trong native | Reflection metadata cho kiểu lồng hoặc kiểu động thiếu | Kiểm `@RegisterReflectionForBinding`, nested configuration properties và hints |
| Thêm hint cho toàn bộ package | Tăng reachability và che giấu nguyên nhân thật | Đăng ký đúng type/member/resource cần dùng |
| Chỉ dùng tracing agent rồi copy mọi file output | Agent có thể ghi cả test infrastructure và code path không thuộc sản phẩm | Lọc, review và test lại từng hint |
| Dependency thứ ba không có reachability metadata | Native compiler không thấy reflection/resource cần thiết của dependency | Kiểm version, metadata repository và hỗ trợ từ vendor |
| Native test được chạy bằng JVM Surefire | Chỉ chạy JVM test, chưa tạo native test image | Dùng profile `nativeTest` hoặc Gradle `nativeTest` |
| Build native trên một OS rồi công bố hỗ trợ tất cả OS | Native binary gắn với target platform | CI matrix build và run từng target được hỗ trợ |

## 11. Quy trình QA trước khi công bố thư viện native-compatible

1. **Xác định support matrix:** Spring Boot, Java, GraalVM, Native Build Tools, build tool, OS và architecture.
2. **Build artifact library:** chạy compile/test, kiểm imports resource và đóng gói JAR.
3. **Kiểm thử auto-configuration trên JVM:** condition match/no-match, default bean, custom bean override, property missing và classpath optional.
4. **Kiểm thử runtime hints:** dùng `RuntimeHintsPredicates` cho resource/reflection/proxy/serialization mà thư viện tự đăng ký.
5. **Kiểm consumer project:** phụ thuộc JAR đã install/publish và chạy `@SpringBootTest`.
6. **Chạy application AOT:** dùng đúng profile và property build-time; xử lý mọi lỗi generation.
7. **Chạy AOT trên JVM:** `spring.aot.enabled=true` để kiểm generated initialization.
8. **Build native image:** dùng đúng GraalVM/Native Build Tools version và target platform.
9. **Chạy native smoke/integration test:** xác nhận bean, resource và luồng nghiệp vụ quan trọng.
10. **Kiểm tra dependency metadata:** xác định dependency bên thứ ba có native reachability support.
11. **Lưu bằng chứng:** build logs, test reports, artifact checksum, toolchain version và target platform.
12. **Công bố giới hạn:** nêu rõ version/feature/platform đã kiểm chứng; không mở rộng tuyên bố vượt bằng chứng CI.

## 12. Bài tập tự kiểm tra

**Câu 1.** Vì sao `ApplicationContextRunner` tests trên JVM chưa đủ để tuyên bố auto-configuration native-compatible?  
**Đáp án:** Chúng kiểm tra condition và bean behavior trên JVM, nhưng chưa kiểm AOT-generated code, native reachability, reflection hints hoặc resource inclusion.

**Câu 2.** Spring AOT đánh giá `@ConditionalOnProperty` ở thời điểm nào?  
**Đáp án:** Trong build-time AOT processing khi BeanFactory được chuẩn bị. Property ảnh hưởng bean presence cần được đặt đúng lúc build.

**Câu 3.** Nếu `acme.greeting.enabled=false` khi process AOT, sau đó đặt property thành true lúc chạy native image thì bean có tự xuất hiện không?  
**Đáp án:** Không. Bean definition bị loại trong AOT output; runtime property không làm Spring tái phân tích auto-configuration.

**Câu 4.** `RuntimeHintsRegistrar` dùng để làm gì?  
**Đáp án:** Đăng ký yêu cầu reflection, resources, serialization và JDK proxies cho AOT/native image.

**Câu 5.** `RuntimeHintsPredicates` test pass có chứng minh native binary chạy đúng không?  
**Đáp án:** Không. Nó chứng minh registrar khai báo hint như mong muốn. Cần native compile và native runtime test để kiểm image cuối cùng.

**Câu 6.** Vì sao native integration test nên đặt trong consumer application?  
**Đáp án:** Vì native image được tạo từ ứng dụng hoàn chỉnh với dependency graph, main configuration, properties, profile và auto-configuration discovery thực tế.

**Câu 7.** Lệnh Maven nào chạy AOT-generated JAR trên JVM?  
**Đáp án:** Build JAR có AOT assets, sau đó chạy `java -Dspring.aot.enabled=true -jar target/...jar`.

**Câu 8.** Maven command nào chạy native tests với Spring Boot parent và Native Build Tools đã khai báo?  
**Đáp án:** `mvn -PnativeTest test`.

**Câu 9.** Vì sao không nên copy toàn bộ output tracing agent vào library?  
**Đáp án:** Output có thể chứa hint của test infrastructure hoặc code path không cần thiết; cần review, lọc và kiểm chứng.

**Câu 10.** Có thể công bố native support cho Windows ARM64 nếu CI chỉ build Linux x64 không?  
**Đáp án:** Không. Cần build và chạy trên target OS/architecture được công bố hoặc có bằng chứng kiểm thử tương đương đáng tin cậy.

## 13. Ghi nhớ và tài liệu tham khảo

- JVM tests kiểm tra phần lớn logic và condition; consumer tests kiểm tra artifact được sử dụng như ứng dụng thực.
- AOT xử lý ApplicationContext ở build time; condition và classpath quyết định tập bean cố định cho artifact.
- `RuntimeHintsRegistrar` và `@ImportRuntimeHints` khai báo những reflection/resource/proxy/serialization requirements mà Spring không thể tự suy ra.
- `RuntimeHintsPredicates` kiểm tra nội dung hints; native executable tests mới xác nhận kết quả trong GraalVM.
- Consumer application là nơi kiểm thử native có giá trị nhất cho auto-configuration library.
- `mvn -Pnative clean package` tạo AOT assets; `spring.aot.enabled=true` cho phép kiểm generated code trên JVM; `mvn -Pnative native:compile` tạo native executable; `mvn -PnativeTest test` chạy native tests.
- Điều kiện `@Conditional` ảnh hưởng bean presence phải được cấu hình tại build time; runtime feature toggles cần thiết kế riêng.
- Native support phải được công bố theo ma trận version, dependency và target platform đã thực sự kiểm thử.

Tài liệu chính thức Spring Boot 3.3.13 / Spring Framework 6.1:

1. [Testing GraalVM Native Images](https://docs.spring.io/spring-boot/3.3/how-to/native-image/testing-native-applications.html) — chiến lược JVM tests và native tests.
2. [Ahead-of-Time Processing — Maven Plugin 3.3.13](https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html) — `process-aot`, `process-test-aot`, native và nativeTest profiles.
3. [Advanced Native Images Topics](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html) — RuntimeHintsRegistrar, @ImportRuntimeHints, tracing agent và known limitations.
4. [Spring Framework Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html) — điều kiện build-time, generated assets và runtime hints.
5. [Spring Boot 3.3.13 System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html) — Java, Maven, Gradle, GraalVM và Native Build Tools versions.
6. [Spring Boot 3.3 Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html) — parent POM, plugin và native profile.
7. [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html) — auto-configuration structure and testing.
8. [Spring Boot 3.3.13 — RuntimeHintsRegistrar Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/aot/hint/RuntimeHintsRegistrar.html).
9. [Spring Boot 3.3.13 — RuntimeHintsPredicates Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/aot/hint/predicate/RuntimeHintsPredicates.html).
10. [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata) — native metadata cho dependency bên thứ ba.
