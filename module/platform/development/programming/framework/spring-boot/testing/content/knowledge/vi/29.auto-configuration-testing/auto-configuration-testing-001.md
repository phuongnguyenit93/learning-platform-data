# ApplicationContextRunner cho auto-configuration có phạm vi hẹp trong Spring Boot

## 1. Vì sao nên kiểm thử auto-configuration bằng một context rất nhỏ?

Khi xây Spring Boot starter hoặc auto-configuration cho một thư viện, nhiệm vụ chính không phải là kiểm tra một REST controller chạy trên Tomcat. Ta cần xác nhận **Spring có tạo bean hay không** trong từng điều kiện: thư viện tồn tại trên classpath, property được bật, người dùng đã tự định nghĩa bean, hay một bean phụ thuộc bị thiếu.

Ví dụ, một starter tự tạo `GreetingService` khi đồng thời thỏa:
- Ứng dụng có class `GreetingTransport` của thư viện tùy chọn.
- `demo.greeting.enabled=true`.
- Người dùng **chưa** tự cung cấp `GreetingService`.

Nếu dùng `@SpringBootTest` cho mỗi nhánh, Spring Boot có thể tải rất nhiều auto-configurations khác, tạo web server, datasource, security filter và các beans không liên quan. Test sẽ chậm, khó phân tích nguyên nhân và dễ bị ảnh hưởng bởi classpath test. **`ApplicationContextRunner`** được Spring Boot cung cấp để tạo **một `ApplicationContext` xác định, tối thiểu và mới cho từng ca**, rồi tự đóng context khi callback hoàn tất.

```text
ApplicationContextRunner
  + AutoConfigurations.of(GreetingAutoConfiguration.class)
  + test-only user configuration (tùy ca)
  + Environment property values (tùy ca)
  + FilteredClassLoader (tùy ca)
          |
          v
   START one narrow ApplicationContext
          |
          v
  Evaluate @ConditionalOnClass / @ConditionalOnProperty
  Evaluate @ConditionalOnMissingBean
  Register only requested configuration / beans
          |
          v
  callback: assert beans, values, failure, conditions
          |
          v
   CLOSE the context after the callback
```

**Bài học chính:** Đây là kiểm thử **điều kiện và kết quả auto-configuration**, không phải phép thử end-to-end của toàn ứng dụng. Mỗi lần `run(context -> ...)` có context riêng, nên có thể test nhiều phối hợp cấu hình mà không cần `@DirtiesContext` hay chia sẻ state của một `@SpringBootTest`.

Bài dùng **Java 17+, Spring Boot 3.5.x, Spring Framework 6.x, JUnit Jupiter, AssertJ**. Ví dụ có dự án Gradle đầy đủ với một auto-configuration tự tạo, file discovery metadata, service interface, một optional-class marker và nhiều test nhánh thực tế. Các ví dụ không cần Docker, network hoặc database.

## 2. Những khái niệm cần phân biệt

| Khái niệm | Vai trò | Sai lầm thường gặp |
|---|---|---|
| `@Configuration` | Cấu hình Spring thông thường | Coi nó tự được phát hiện như Boot auto-configuration trong mọi project |
| `@AutoConfiguration` | Đánh dấu class cấu hình dành cho cơ chế auto-configuration của Boot | Chỉ gắn annotation mà quên khai báo entry trong `AutoConfiguration.imports` |
| `@ConditionalOnClass` | Chỉ áp dụng khi class/library cần thiết có mặt | Dùng trực tiếp optional class ở nơi JVM phải load class trước khi condition chạy |
| `@ConditionalOnProperty` | Ràng buộc theo giá trị `Environment` | Nghĩ tồn tại property đồng nghĩa đã bật dù `havingValue` khác |
| `@ConditionalOnMissingBean` | Nhường quyền cho bean người dùng đã định nghĩa | Đánh giá condition trước khi user beans được biết đến |
| `@ConditionalOnBean` | Chỉ tạo bean khi một dependency bean đã được định nghĩa | Test dựa trên thứ tự registration không ổn định |
| `ApplicationContextRunner` | Tạo/đóng context nhỏ cho mỗi scenario | Mong nó tự khởi động mọi auto-configurations như `@SpringBootTest` |
| `AutoConfigurations.of(...)` | Nạp các auto-configurations được chỉ định trong runner | Nghĩ nó đồng nghĩa test file `AutoConfiguration.imports` |
| `withUserConfiguration(...)` | Nạp cấu hình bean của “người dùng ứng dụng” | Đặt custom beans trong auto-config rồi không test back-off |
| `withPropertyValues(...)` | Thêm property chỉ cho scenario hiện tại | Thay đổi system property toàn cục hoặc chia sẻ `Environment` |
| `FilteredClassLoader` | Giả lập thiếu class/package trên classpath | Xóa dependency thật khỏi build cho mọi test |
| `WebApplicationContextRunner` | Dùng khi condition yêu cầu Servlet web context | Dùng plain runner rồi thấy web-only configuration luôn fail |
| `ReactiveWebApplicationContextRunner` | Dùng khi condition yêu cầu Reactive web context | Nhầm với `WebApplicationContextRunner` servlet |
| `ConditionEvaluationReport` | Giải thích condition nào matched/negative | Đọc một exception thiếu context mà không xem condition report |

### 2.1. `ApplicationContextRunner` không phải `@SpringBootTest`

`@SpringBootTest` khởi động Spring Boot application theo cấu hình ứng dụng thực. Nó phù hợp kiểm thử các thành phần tích hợp nhau. Ngược lại, `ApplicationContextRunner` thường chỉ tạo một context chứa **auto-configurations và user configurations được khai báo tường minh**.

Điều này đem lại ba lợi ích:
1. **Tốc độ và độ cô lập:** Không cần HTTP server, datasource hoặc security khi không liên quan.
2. **Tính xác định:** Mỗi scenario có properties, classpath và bean definitions riêng.
3. **Chẩn đoán condition:** Dễ biết bean bị tạo/không tạo bởi điều kiện nào.

Nhưng cũng có giới hạn: test runner pass **không tự bảo đảm** tất cả auto-configurations của toàn Spring Boot app tương thích, metadata discovery trong JAR được đóng gói đúng, hay server thực có thể khởi động. Cần integration/smoke test bổ sung khi dự án yêu cầu các bảo đảm ấy.

## 3. API quan trọng của ApplicationContextRunner

Trong Spring Boot 3.5, import chính:

```java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
```

Tạo một runner nền:

```java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                GreetingAutoConfiguration.class));
```

Đây là fragment trong một JUnit class, với `GreetingAutoConfiguration` có thật. `ApplicationContextRunner` được cấu hình bằng các phương thức **trả một runner có cấu hình mở rộng**; không phải mỗi call tự chạy context.

### 3.1. Một workflow đọc được như một đặc tả

```java
runner
    .withPropertyValues(
        "demo.greeting.enabled=true",
        "demo.greeting.prefix=Xin chào")
    .run(context -> {
        assertThat(context)
            .hasSingleBean(GreetingService.class);

        GreetingService service =
            context.getBean(GreetingService.class);

        assertThat(service.greet("An"))
            .isEqualTo("Xin chào, An");
    });
```

Đây là fragment trong lớp test có imports, runner và interface/implementation. `withPropertyValues` đưa các key/value vào `Environment` của scenario; `run` khởi tạo context, cung cấp callback `AssertableApplicationContext`, rồi đóng context.

**Không giữ bean/context ra ngoài callback** để sử dụng sau `run`: chúng gắn với một context đã bị đóng. Nếu cần test các bước trên bean, hãy thực hiện assertions trong callback.

### 3.2. Các phương thức thường dùng

| API | Mục đích |
|---|---|
| `new ApplicationContextRunner()` | Khởi tạo runner |
| `.withConfiguration(AutoConfigurations.of(MyAutoConfiguration.class))` | Chọn đúng auto-config cần kiểm tra |
| `.withUserConfiguration(UserConfiguration.class)` | Đăng ký bean/cấu hình do ứng dụng cung cấp |
| `.withPropertyValues("feature.enabled=true")` | Mô phỏng environment/config properties |
| `.withClassLoader(new FilteredClassLoader(OptionalType.class))` | Giả lập class không có mặt |
| `.withInitializer(...)` | Thêm initialization hook, ví dụ condition report logger |
| `.run(context -> { ... })` | Tạo context riêng, assert bean/failure, tự đóng |
| `assertThat(context).hasSingleBean(Type.class)` | Kiểm tra có đúng một bean kiểu này |
| `assertThat(context).doesNotHaveBean(Type.class)` | Kiểm tra bean kiểu này không được tạo |
| `context.getBean(Type.class)` | Đọc bean để assert hành vi |
| `context.getStartupFailure()` | Lấy exception khi context khởi động thất bại |

Các assertions `hasSingleBean` và `doesNotHaveBean` là các tiện ích AssertJ dành cho `AssertableApplicationContext`, khác với chỉ gọi `context.getBeansOfType(...)` rồi đếm. Một test tốt thường assert **cả sự hiện diện/absence và hành vi/value**, không chỉ số bean.

## 4. Thiết kế mini auto-configuration có ba điều kiện

Ta tạo một auto-configuration cho chức năng greeting. Nó được bật **chỉ khi**:
- Có class `com.example.mini.optional.GreetingTransport`.
- Property `demo.greeting.enabled` có giá trị đúng `true`.
- Không có bean `GreetingService` khác.

Khi bật, bean được tạo từ property `demo.greeting.prefix`, mặc định `Hello`. Nếu user đã định nghĩa `GreetingService` trong application, auto-config **back off** mà không ghi đè.

```text
                       Auto-configuration được chỉ định
                                      |
                     Có GreetingTransport trên classpath?
                         /                   \
                       Không                 Có
                        |                     |
                   Không tạo bean      enabled == "true"?
                                          /         \
                                        Không        Có
                                         |           |
                                    Không tạo   Đã có user
                                      bean     GreetingService?
                                                /       \
                                              Có         Không
                                               |           |
                                          Back off    Tạo default
                                          user bean  GreetingService
```

Đây là **sơ đồ quyết định**, không phải một rule engine mới. Thứ tự và hành vi thực được Spring Boot conditions thực hiện trong giai đoạn registration/configuration. Ta kiểm chứng từng nhánh bằng test thay vì suy luận rằng annotation đã đúng.

## 5. Dự án Java 17+ / Spring Boot 3.5.x đầy đủ

### 5.1. Cấu trúc file

```text
build.gradle
src/main/java/com/example/demoapp/
    RunnerDemoApplication.java
src/main/java/com/example/mini/api/
    GreetingService.java
    DefaultGreetingService.java
src/main/java/com/example/mini/optional/
    GreetingTransport.java
src/main/java/com/example/mini/autoconfigure/
    GreetingAutoConfiguration.java
src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
src/test/java/com/example/mini/autoconfigure/
    GreetingAutoConfigurationTest.java
```

Trong project mẫu, marker `GreetingTransport` được đưa vào cùng source set để mọi thứ có thể biên dịch, chạy độc lập với các dependencies của Spring Boot. **Trong starter thực tế**, nó thường là class của **một thư viện tùy chọn ở module/JAR khác**, và auto-config module cần xử lý an toàn khi JAR tùy chọn không có. `FilteredClassLoader` trong test sẽ mô phỏng chính tình huống ấy.

Đặt application main ở package `com.example.demoapp`, còn auto-configuration ở `com.example.mini.autoconfigure`. Cách này giúp tránh để component scanning của demo app tự quét `GreetingAutoConfiguration`, nhờ đó chỉ cơ chế **auto-configuration imports** điều khiển registration trong app. Runner test sẽ đăng ký auto-config tường minh, độc lập với main class.

### 5.2. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` mang Spring Core/Boot auto-configuration infrastructure, còn starter-test cung cấp JUnit Jupiter/AssertJ/Spring Boot test runner. Annotation processor `spring-boot-autoconfigure-processor` có thể tạo condition metadata để hỗ trợ sàng lọc sớm, **không thay thế** file `AutoConfiguration.imports` và không bắt buộc cho logic runtime cốt lõi của ví dụ.

Ví dụ không phụ thuộc `starter-web`, `starter-data-jpa`, security, DB hoặc Testcontainers. Việc tránh các dependencies không liên quan cũng giúp minh họa đúng **phạm vi nhỏ** của `ApplicationContextRunner`.

### 5.3. Spring Boot main class

Tệp `src/main/java/com/example/demoapp/RunnerDemoApplication.java`:

```java
package com.example.demoapp;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RunnerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                RunnerDemoApplication.class, args);
    }
}
```

Main class cho phép chạy demo app bằng `bootRun` khi cần smoke test, nhưng các `ApplicationContextRunner` unit/integration tests **không khởi động main**. Vì không có web starter, main không tạo HTTP server.

### 5.4. Service contract

Tệp `src/main/java/com/example/mini/api/GreetingService.java`:

```java
package com.example.mini.api;

@FunctionalInterface
public interface GreetingService {

    String greet(String name);
}
```

Tệp `src/main/java/com/example/mini/api/DefaultGreetingService.java`:

```java
package com.example.mini.api;

import java.util.Objects;

public final class DefaultGreetingService
        implements GreetingService {

    private final String prefix;

    public DefaultGreetingService(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    @Override
    public String greet(String name) {
        return prefix + ", " + Objects.requireNonNull(name);
    }
}
```

Test kiểm tra cả loại bean lẫn kết quả chính xác, ví dụ `Hello, An` và `Xin chào, An`, không chỉ assert `ApplicationContext` đã start.

### 5.5. Optional-class marker

Tệp `src/main/java/com/example/mini/optional/GreetingTransport.java`:

```java
package com.example.mini.optional;

/**
 * Marker đại diện cho dependency tùy chọn trong ví dụ.
 */
public final class GreetingTransport {

    private GreetingTransport() {
    }
}
```

Trong ứng dụng thật, class này có thể là API/driver thực của một thư viện được auto-configuration hỗ trợ. Dùng tên class ở condition giúp tránh phụ thuộc cứng khi module optional vắng mặt.

### 5.6. Auto-configuration class

Tệp `src/main/java/com/example/mini/autoconfigure/GreetingAutoConfiguration.java`:

```java
package com.example.mini.autoconfigure;

import com.example.mini.api.DefaultGreetingService;
import com.example.mini.api.GreetingService;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(
        name = "com.example.mini.optional.GreetingTransport")
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService(
            @Value("${demo.greeting.prefix:Hello}") String prefix) {
        return new DefaultGreetingService(prefix);
    }
}
```

**Phân tích chính xác:**

- `@AutoConfiguration` định danh cấu hình được Boot auto-config mechanism quản lý.
- `@ConditionalOnClass(name=...)` được đánh giá ở **class level** và dùng String tên type tùy chọn; nếu marker bị ẩn bởi `FilteredClassLoader`, class auto-config không được apply.
- `@ConditionalOnProperty(... havingValue="true", matchIfMissing=false)` nghĩa là property phải **có mặt và khớp giá trị true**. Thiếu property, false hoặc chuỗi khác đều không kích hoạt.
- `@ConditionalOnMissingBean(GreetingService.class)` giúp default bean **back off** trước một bean cùng type do người dùng định nghĩa.
- `@Value("${demo.greeting.prefix:Hello}")` dùng `Hello` khi property `demo.greeting.prefix` không được cung cấp. Property prefix không quyết định việc **bật** auto-config; `enabled` mới là cờ kích hoạt.

**Lưu ý classpath safety:** Nếu một `@Bean` method trả về trực tiếp một kiểu chỉ tồn tại trong optional dependency, JVM có thể cần load kiểu return trước khi condition trên method được đánh giá. Đối với trường hợp đó, hãy bọc phần optional beans trong một nested `@Configuration` được đánh dấu `@ConditionalOnClass` để cô lập class loading. Ví dụ này trả về `GreetingService` thuộc chính project nên không có rủi ro đó.

### 5.7. AutoConfiguration.imports cho production discovery

Tệp chính xác:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

**Nội dung tệp** (một fully qualified class name trên một dòng):

```text
com.example.mini.autoconfigure.GreetingAutoConfiguration
```

Đây là convention discovery của **Spring Boot 3.x**. Nếu xây JAR starter thực, file cần được đóng gói dưới `META-INF/spring/` của artifact. Khi `@SpringBootApplication` kích hoạt auto-configuration, Boot đọc danh sách này và cân nhắc conditions.

**Điểm cực kỳ quan trọng về QA:** Test `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(GreetingAutoConfiguration.class))` đăng ký class tường minh, **không tự chứng minh** file `AutoConfiguration.imports` hiện diện trong JAR. Vì thế:
- Dùng runner tests để kiểm tra logic conditions/beans thật.
- Có thêm metadata/JAR packaging check hoặc một smoke test auto-discovery của toàn application nếu starter sẽ được phát hành.
- Đừng coi một runner test pass là bằng chứng production consumer chắc chắn auto-import được.

Đây không phải `spring.factories` kiểu auto-configuration cũ. Trong Boot 3.x, khai báo auto-config bằng `AutoConfiguration.imports` là cách được tài liệu Boot hướng dẫn.

## 6. Lớp JUnit 5 đầy đủ với ApplicationContextRunner

Tệp `src/test/java/com/example/mini/autoconfigure/GreetingAutoConfigurationTest.java`:

```java
package com.example.mini.autoconfigure;

import com.example.mini.api.DefaultGreetingService;
import com.example.mini.api.GreetingService;
import com.example.mini.optional.GreetingTransport;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.logging
        .ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    GreetingAutoConfiguration.class));

    @Test
    void disabledWhenPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context)
                    .doesNotHaveBean(GreetingService.class);
        });
    }

    @Test
    void disabledWhenPropertyIsFalse() {
        runner.withPropertyValues(
                "demo.greeting.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void disabledWhenPropertyHasUnexpectedValue() {
        runner.withPropertyValues(
                "demo.greeting.enabled=enabled")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void enabledPropertyCreatesExactlyOneDefaultBean() {
        runner.withPropertyValues(
                "demo.greeting.enabled=true")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                    assertThat(context)
                            .hasBean("greetingService");

                    GreetingService service =
                            context.getBean(GreetingService.class);

                    assertThat(service)
                            .isInstanceOf(
                                    DefaultGreetingService.class);
                    assertThat(service.greet("An"))
                            .isEqualTo("Hello, An");
                });
    }

    @Test
    void customPrefixIsResolvedFromEnvironment() {
        runner.withPropertyValues(
                "demo.greeting.enabled=true",
                "demo.greeting.prefix=Xin chào")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                    assertThat(
                            context.getBean(GreetingService.class)
                                    .greet("An"))
                            .isEqualTo("Xin chào, An");
                });
    }

    @Test
    void userDefinedBeanWinsOverDefaultAutoBean() {
        runner.withUserConfiguration(
                CustomGreetingConfiguration.class)
                .withPropertyValues(
                    "demo.greeting.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                    assertThat(context)
                            .hasBean("customGreetingService");
                    assertThat(context)
                            .doesNotHaveBean("greetingService");

                    GreetingService service =
                            context.getBean(GreetingService.class);
                    assertThat(service.greet("An"))
                            .isEqualTo("Custom, An");
                });
    }

    @Test
    void optionalClassAbsentDisablesAutoConfiguration() {
        runner.withPropertyValues(
                "demo.greeting.enabled=true")
                .withClassLoader(
                        new FilteredClassLoader(
                                GreetingTransport.class))
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context)
                            .doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void optionalClassMissingDoesNotDeleteUserBean() {
        runner.withUserConfiguration(
                CustomGreetingConfiguration.class)
                .withPropertyValues(
                    "demo.greeting.enabled=true")
                .withClassLoader(
                        new FilteredClassLoader(
                                GreetingTransport.class))
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                    assertThat(context)
                            .hasBean("customGreetingService");
                    assertThat(context)
                            .doesNotHaveBean("greetingService");
                });
    }

    @Test
    void runnerVariantsDoNotLeakPropertiesBetweenRuns() {
        runner.withPropertyValues(
                "demo.greeting.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                });

        runner.run(context -> {
            assertThat(context)
                    .doesNotHaveBean(GreetingService.class);
        });
    }

    @Test
    void startupFailureCanBeAssertedWithoutFullBootTest() {
        runner.withUserConfiguration(
                FailingUserConfiguration.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(
                                    IllegalStateException.class);
                });
    }

    @Test
    void conditionReportCanBePrintedForDiagnosis() {
        runner.withPropertyValues(
                "demo.greeting.enabled=true")
                .withInitializer(
                    ConditionEvaluationReportLoggingListener
                        .forLogLevel(LogLevel.INFO))
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(GreetingService.class);
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return name -> "Custom, " + name;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class FailingUserConfiguration {

        @Bean
        String failingStartupBean() {
            throw new IllegalStateException(
                    "Intentional startup failure");
        }
    }
}
```

Bộ code trên thiết kế **11 ca `@Test`** trong một lớp, mỗi ca tạo một context riêng thông qua runner. Các imports `ApplicationContextRunner`, `AutoConfigurations`, `FilteredClassLoader`, `ConditionEvaluationReportLoggingListener` là những APIs đã được Spring Boot hướng dẫn chính thức cho auto-configuration testing.

**Chú ý về cú pháp import Java trong tài liệu:** Trong code fence trên, import `ConditionEvaluationReportLoggingListener` được ngắt dòng để trình bày. Khi copy thành file Java, **phải dùng một dòng import duy nhất** như sau để biên dịch:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
```

Việc xuống dòng giữa các segment của qualified import trong Java có thể vẫn hợp lệ theo tokenization nếu whitespace tách token phù hợp, nhưng **đoạn một dòng ở trên rõ ràng và an toàn nhất**. Các import còn lại không phụ thuộc Spring Boot test extension hoặc Mockito mocking.

### 6.1. Tại sao 11 test này đủ cho phạm vi demo?

| Ca | Nhánh kiểm tra | Ý nghĩa |
|---|---|---|
| `disabledWhenPropertyIsMissing` | Property vắng | `matchIfMissing=false` thực sự có tác dụng |
| `disabledWhenPropertyIsFalse` | enabled=false | Không tạo bean ngoài ý muốn |
| `disabledWhenPropertyHasUnexpectedValue` | enabled khác true | `havingValue="true"` không bị hiểu là mọi giá trị khác false |
| `enabledPropertyCreatesExactlyOneDefaultBean` | Condition đồng thời đúng | Default bean được tạo, đúng type và behavior |
| `customPrefixIsResolvedFromEnvironment` | Property khác default | Environment value được inject |
| `userDefinedBeanWinsOverDefaultAutoBean` | User bean tồn tại | `@ConditionalOnMissingBean` back off |
| `optionalClassAbsentDisablesAutoConfiguration` | Library không có | `@ConditionalOnClass` âm tính |
| `optionalClassMissingDoesNotDeleteUserBean` | Library không có nhưng user bean tồn tại | Auto-config bị tắt nhưng user config không mất |
| `runnerVariantsDoNotLeakPropertiesBetweenRuns` | Các runner instances độc lập | Không rò property từ scenario trước |
| `startupFailureCanBeAssertedWithoutFullBootTest` | Bean initialization ném lỗi | Runner captures startup failure trong callback |
| `conditionReportCanBePrintedForDiagnosis` | Diagnostics | Log condition evaluation ở INFO khi cần |

Các assertions thuộc **Java/AssertJ** chứ không có stdout cố định. Một ca dùng logger condition report sẽ sinh log tùy logger config; **không** cung cấp một “expected console transcript” tự tạo vì log level, framework version và order phụ thuộc môi trường.

### 6.2. Điều gì chứng minh auto-config thật sự tạo đúng bean?

Một assertion `assertThat(context).hasSingleBean(GreetingService.class)` chỉ chứng minh số lượng/type. Kết hợp:
- `hasBean("greetingService")` cho tên bean mặc định.
- `isInstanceOf(DefaultGreetingService.class)` cho implementation.
- `service.greet("An") == "Hello, An"` cho behavior.
- Test custom bean xác nhận default bean vắng và custom bean vẫn hoạt động.

Đây là mức evidence phù hợp cho **bean creation/conditions**, dù vẫn chưa chứng minh HTTP/MQ/client external resource có thể kết nối thực.

## 7. Lỗi nhầm thường gặp: “Chỉ có một test @SpringBootTest là đủ”

Một `@SpringBootTest` với `demo.greeting.enabled=true` có thể pass, nhưng không trả lời:
- Khi không cấu hình property, default bean có bị tạo ngoài ý muốn không?
- Khi user đăng ký `GreetingService`, auto-config có back off hay báo bean ambiguity?
- Khi optional dependency không có, context có còn start được không?
- Khi đổi prefix property, bean có thực sự nhận giá trị mới?
- Khi bean init ném exception, test có xác nhận root cause chính xác?
- Khi chạy nhiều configurations, state có bị leak qua context cache?

`ApplicationContextRunner` giải quyết những trường hợp đó với các context nhỏ, không phải refresh một application lớn nhiều lần. **Đừng đẩy hết các nhánh điều kiện sang `@SpringBootTest`** nếu chỉ cần xác minh auto-configuration.

### 7.1. Cẩn thận khi test user bean back-off

Nếu bạn chỉ tự gọi trực tiếp factory method:

```java
GreetingAutoConfiguration configuration =
        new GreetingAutoConfiguration();

GreetingService service =
        configuration.greetingService("Hello");
```

Đây là đoạn minh họa trong một test có dependencies project. Nó **không** chạy `@ConditionalOnMissingBean`, không có condition evaluation, không có `Environment` resolution. Nó chỉ test một factory method Java.

Bằng chứng đúng là runner tạo context có `CustomGreetingConfiguration`, sau đó assert chỉ **một user bean**, không có default `greetingService`. Khi auto-configuration được nạp theo đúng cách, nó được xem xét sau user bean definitions, giúp điều kiện back-off có ý nghĩa.

### 7.2. Điều kiện classpath an toàn không phải mọi kiểu code đều an toàn

Dùng:

```java
@ConditionalOnClass(name = "com.example.optional.ExternalClient")
class ExternalClientAutoConfiguration {
}
```

Đây là fragment minh họa. Đánh giá class condition từ annotation metadata cho phép Spring Boot không phải load optional class trực tiếp. Nhưng nếu method parameter/return types, static initializers hoặc field signatures của auto-config **bắt buộc JVM load class optional quá sớm**, startup vẫn có thể lỗi `NoClassDefFoundError` dù condition đã khai báo.

Mẫu an toàn hơn:

```java
@AutoConfiguration
public class OptionalClientAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.example.optional.ExternalClient")
    static class ExternalClientConfiguration {
        // @Bean methods có thể tham chiếu ExternalClient
        // bên trong class cấu hình chỉ được nạp nếu class có mặt.
    }
}
```

Đây là đoạn minh họa không dùng library thật. Với optional modules phức tạp, xây separate `@Configuration` nested classes để cô lập class loading, rồi test branch absent bằng `FilteredClassLoader`.

## 8. @ConditionalOnProperty: chính xác hơn một boolean giả định

Spring Boot `@ConditionalOnProperty` có semantics cần đọc đúng:
- Nếu **không khai báo `havingValue`**, mặc định condition match khi property có mặt và không phải chuỗi `false` (không đơn giản là `Boolean.parseBoolean`).
- Với `havingValue="true"`, chỉ giá trị tương ứng true mới match theo điều kiện.
- `matchIfMissing=true` cho phép condition match khi property vắng; bài cố ý dùng `false`.
- Dùng nhiều `name` trong một annotation yêu cầu **tất cả** named properties thỏa.
- Với các property collection/indexed, `@ConditionalOnProperty` không phải bộ so khớp mọi entry trong Binder; cần custom condition nếu logic phức tạp.

Vì vậy test thiếu, false, true và giá trị không mong đợi rất hữu ích. Chỉ có ca `true` sẽ bỏ sót một auto-config vô tình bật khi thiếu property.

### 8.1. Có nên dùng @ConfigurationProperties thay @Value?

Trong starter lớn, `@ConfigurationProperties` thường phù hợp hơn `@Value`:
- Có type-safe binding, default values và validation.
- Có metadata hỗ trợ autocomplete.
- Dễ tách tên property, giá trị mặc định và constraint khỏi bean factory method.
- Hỗ trợ các kiểu `Duration`, `DataSize`, enums và collections theo Spring Boot binder.

Ví dụ **minh họa** về kiểu property object:

```java
@ConfigurationProperties(prefix = "demo.greeting")
public class GreetingProperties {

    private boolean enabled;
    private String prefix = "Hello";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getPrefix() {
        return prefix;
    }

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }
}
```

Đây là Java class minh họa nếu đặt trong file `GreetingProperties.java` và import `org.springframework.boot.context.properties.ConfigurationProperties`. Nó **không nằm trong project runnable ở mục 5**, vì project dùng `@Value` đơn giản để tập trung vào conditional logic.

Nếu chuyển sang `@ConfigurationProperties`, đăng ký nó rõ ràng (ví dụ `@EnableConfigurationProperties(GreetingProperties.class)` trong auto-config), và bổ sung test `withPropertyValues` kiểm tra binder type conversion/validation. Đừng chỉ add annotation lên POJO rồi tin bean sẽ tự xuất hiện trong một `ApplicationContextRunner` không quét components.

## 9. @ConditionalOnBean, @ConditionalOnMissingBean và thứ tự

Hai condition này phụ thuộc **những bean definitions đã được Spring biết tới tại thời điểm evaluation**. Với auto-configurations, Boot sắp xếp chúng sau user configurations và áp dụng ordering metadata khi cần.

```java
@AutoConfiguration(after = DependencyAutoConfiguration.class)
class FeatureAutoConfiguration {
    // Tạo bean phụ thuộc một bean do DependencyAutoConfiguration tạo.
}
```

Đây là fragment minh họa; cần class `DependencyAutoConfiguration` và imports phù hợp. Với Boot auto-config modules thật, có thể dùng `@AutoConfiguration(before=...)`/`after=...` hoặc `beforeName`/`afterName` để điều chỉnh thứ tự định nghĩa, **không** phải thứ tự khởi tạo instance của mọi bean.

**Quan trọng:** `AutoConfigurations.of(A.class,B.class)` làm các auto-configurations trong runner được sắp xếp theo cách Boot làm trong ứng dụng; đừng phụ thuộc thứ tự tham số bằng tay khi code production dùng ordering annotations.

### 9.1. Mẫu test dependency bean

Với một auto-config chỉ cần bean `SomeClient` khi có `SomeTransport`, thường nên có hai cases:
1. Context **không có `SomeTransport`** → không tạo `SomeClient`.
2. `withUserConfiguration(TransportConfiguration.class)` đăng ký `SomeTransport` → tạo một `SomeClient`.

Nên assert bean type và dependency thực, thay vì chỉ test `applicationContext.containsBeanDefinition("someClient")`. Nếu user có **nhiều** candidates, condition `@ConditionalOnSingleCandidate` hoặc `@Primary` có thể quyết định chọn bean; hãy test ambiguity/primary semantics nếu auto-config phụ thuộc một candidate.

## 10. @ConditionalOnClass: mô phỏng thiếu dependency bằng FilteredClassLoader

Không cần xóa một dependency khỏi `build.gradle` rồi sửa lại giữa các test. `FilteredClassLoader` là helper của Boot để **ẩn class/package khỏi classloader dùng bởi runner**:

```java
runner
    .withClassLoader(
        new FilteredClassLoader(GreetingTransport.class))
    .withPropertyValues(
        "demo.greeting.enabled=true")
    .run(context -> {
        assertThat(context)
            .doesNotHaveBean(GreetingService.class);
    });
```

Tình huống này quan trọng với starter hỗ trợ optional libraries như:
- `DataSource`/JDBC driver.
- Kafka producer/consumer client.
- Redis client.
- OpenTelemetry hoặc tracing provider.
- Jackson module, HTTP client implementation.
- Micrometer registry.
- Cache provider hoặc messaging SDK.

Không phải mọi thư viện đều cần `FilteredClassLoader`. Chỉ dùng khi **sự có mặt/vắng mặt class** là một phần của condition contract. Nếu bạn chỉ cần test một property, `withPropertyValues` đủ và dễ hiểu hơn.

### 10.1. Tránh test sai với classpath thực của runner

Nếu optional dependency không nằm trên test classpath, **positive case** không thể chứng minh bean được tạo vì condition classpath vắng. Ngược lại, nếu luôn có dependency, bạn khó chứng minh **negative case** trừ khi filter classloader.

Trong ví dụ, ta có marker class thật để positive case chạy, và `FilteredClassLoader(GreetingTransport.class)` để negative case chạy trên **cùng một build**, không phải hai môi trường Gradle khác nhau. Đây là thế mạnh của `ApplicationContextRunner`.

### 10.2. Class loading không đồng nghĩa class được dùng thành công

`@ConditionalOnClass` chỉ kiểm tra class có mặt. Nó **không** chứng minh:
- JDBC driver kết nối được database.
- Kafka broker reachable.
- External SDK key hợp lệ.
- Bean đã được khởi tạo đầy đủ trong mọi case nếu còn custom conditions.
- Version binary của dependency tương thích ở mọi method call.

Các vấn đề ấy cần thêm bean initialization assertions, contract tests hoặc integration tests với resource thật. Không biến classpath check thành một tuyên bố end-to-end.

## 11. Khác biệt giữa plain, Servlet và Reactive context runner

`ApplicationContextRunner` mặc định tạo một **context không có giả định web**. Nếu auto-config có:

```java
@ConditionalOnWebApplication(
        type = ConditionalOnWebApplication.Type.SERVLET)
```

thì plain runner thường **không kích hoạt** branch Servlet. Sử dụng:

```java
WebApplicationContextRunner webRunner =
        new WebApplicationContextRunner()
                .withConfiguration(
                    AutoConfigurations.of(
                        MyServletAutoConfiguration.class));
```

Hoặc với reactive web context:

```java
ReactiveWebApplicationContextRunner reactiveRunner =
        new ReactiveWebApplicationContextRunner()
                .withConfiguration(
                    AutoConfigurations.of(
                        MyReactiveAutoConfiguration.class));
```

Hai đoạn ở trên là **minh họa**, cần:
- Import `org.springframework.boot.test.context.runner.WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner`.
- Có class auto-config thật và dependencies Servlet/WebFlux liên quan.
- Có assert trong `run(...)` để kiểm tra bean/condition.

Dùng **đúng loại context** là cần thiết vì `@ConditionalOnWebApplication` có thể kiểm tra context type, scope, environment, và không nên bị ép “pass” bằng mock một bean không liên quan.

### 11.1. Khi nào không cần web runner?

Nếu auto-configuration chỉ tạo `GreetingService`, JSON serializer, clock abstraction hoặc một client không phụ thuộc servlet/reactive web context, `ApplicationContextRunner` thường là chính xác nhất. Thêm web runner có thể tải nhiều hạ tầng không cần thiết, kéo test ra ngoài phạm vi nhỏ ban đầu.

Nếu auto-config cần `MockMvc`/controller mapping/HTTP filter chain, bạn đang kiểm tra phạm vi web sâu hơn; cân nhắc `WebApplicationContextRunner`, `@WebMvcTest` hoặc `@SpringBootTest` theo mục tiêu.

## 12. Chẩn đoán condition bằng ConditionEvaluationReport

Một lỗi thường gặp: context khởi động được nhưng bean **không xuất hiện**. Điều đó có thể do:
- `@ConditionalOnClass` không match.
- `@ConditionalOnProperty` vắng hoặc sai giá trị.
- Đã có user bean khiến `@ConditionalOnMissingBean` back off.
- Nhiều candidates khiến `@ConditionalOnSingleCandidate` không match.
- `@ConditionalOnWebApplication` chạy trong context type sai.
- Auto-configuration không được thêm vào runner.
- Bean bị exclude bởi một điều kiện ở nested configuration class.

**Đừng sửa test bằng cách `@Import` bừa bean mong đợi** rồi assert tồn tại, vì như vậy có thể bypass chính condition cần kiểm tra.

### 12.1. Bật condition report log cho một scenario

Spring Boot có `ConditionEvaluationReportLoggingListener`. Dùng trong runner:

```java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(GreetingAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener
            .forLogLevel(LogLevel.INFO))
    .withPropertyValues(
        "demo.greeting.enabled=false")
    .run(context -> {
        assertThat(context)
            .doesNotHaveBean(GreetingService.class);
    });
```

Đây là fragment JUnit với static imports và class demo. Listener được Spring Boot hướng dẫn chính thức để in kết quả evaluation ở INFO/DEBUG. Đừng gửi condition report đầy đủ vào mỗi test ở CI khi nó quá dài; chỉ bật ở các ca debug hoặc logging level phù hợp.

### 12.2. Hiểu “positive matches” và “negative matches”

Trong report:
- **Positive match**: condition của một configuration đã thỏa.
- **Negative match**: condition không thỏa, với thông điệp lý do.
- Một class-level condition không match có thể làm **toàn class auto-config bị bỏ qua**, không chỉ một `@Bean`.
- `@ConditionalOnMissingBean` âm tính **có thể là hành vi đúng**, vì người dùng đã tự đăng ký bean.

Không coi “negative matches” là một danh sách bug. Một starter tốt cố ý **không tạo bean** khi property disabled, dependency vắng hoặc user override — và cần test các negative branches ấy.

### 12.3. Startup failure khác bean không được tạo

**Hai kết quả rất khác:**

- Context khởi động bình thường, `GreetingService` **không tồn tại** vì condition không match: một hành vi expected.
- Context **khởi động thất bại**, ví dụ constructor/factory method ném exception, bean ambiguity, config binding error: cần kiểm tra `getStartupFailure()` và root cause.

`ApplicationContextRunner.run` cho phép callback quan sát startup failure thay vì khiến test class fail ngay ở giai đoạn Spring test context bootstrap như một `@SpringBootTest` không start được.

Ví dụ `startupFailureCanBeAssertedWithoutFullBootTest` trong code trên kiểm tra `hasFailed()` và root cause `IllegalStateException` được tạo có chủ đích bởi `FailingUserConfiguration`. Nó không tự biến startup failure thành hành vi “auto-config disabled”; hai trạng thái phải được tách rạch ròi.

## 13. Test matrix giúp bao phủ mọi condition mà không nhân đôi code

Với ba điều kiện chính, ma trận cơ bản:

| Class `GreetingTransport` | enabled | User `GreetingService` | Kỳ vọng |
|---|---|---|---|
| Có | Không khai báo | Không | Không có bean |
| Có | false | Không | Không có bean |
| Có | giá trị khác true | Không | Không có bean |
| Có | true | Không | **Một DefaultGreetingService** |
| Có | true | Có | **Một custom bean**, default back off |
| Không | true | Không | Không có bean |
| Không | true | Có | **Một custom bean**, auto-config bị tắt |
| Có | true + custom prefix | Không | Default bean có prefix từ Environment |
| Có | true rồi scenario mới không property | Không | Hai contexts độc lập, không rò property |

Ma trận này tập trung vào **outcomes có ý nghĩa** chứ không tạo mọi tổ hợp vô ích. Với starter thực, mở rộng theo:
- Có một dependency bean hay nhiều candidates.
- `@Primary` có/không.
- Property enabled vắng/false/true/malformed.
- Class có/không.
- Servlet vs Reactive vs non-web context.
- Native-image vs JVM behavior nếu sản phẩm cần hỗ trợ.
- Cấu hình external clients missing/broken credentials.
- Custom bean từ ứng dụng thay thế default.

**Tránh kiểm thử implementation detail quá cứng:** Đôi khi bean name được xem là public contract (ví dụ `"taskExecutor"`), lúc đó assert tên là hợp lý. Nếu tên chỉ là chi tiết nội bộ, ưu tiên assert **type, số lượng và behavior** để tránh tests fail khi refactor không làm đổi chức năng.

## 14. Runner immutability và cô lập giữa các ca

Các phương thức `withPropertyValues`, `withUserConfiguration`, `withClassLoader` thường tạo **bản sao cấu hình runner** rồi trả về để chain. Vì vậy:

```java
ApplicationContextRunner base =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    GreetingAutoConfiguration.class));

base.withPropertyValues(
        "demo.greeting.enabled=true")
    .run(ctx -> assertThat(ctx)
        .hasSingleBean(GreetingService.class));

base.run(ctx -> assertThat(ctx)
        .doesNotHaveBean(GreetingService.class));
```

Hai calls trên không dùng chung một `ApplicationContext`, và `base` không bị `withPropertyValues` của scenario trước sửa thành enabled=true. Đó là lý do có thể đặt runner thành `private final` field trong lớp test rồi tạo nhiều biến thể dễ đọc.

**Điểm cần nhớ:** Tính cô lập context không tự biến mọi dependency thành stateless. Nếu bean code viết vào **static mutable fields, file chung, singleton ngoài Spring, system properties, database dùng chung**, những side effects ấy vẫn có thể rò giữa runs. `ApplicationContextRunner` đóng Spring context, không xóa tùy ý mọi external resource.

Nếu một auto-config tạo thread pool, scheduler hoặc client TCP, bảo đảm bean có shutdown lifecycle (`DisposableBean`, `@PreDestroy`, AutoCloseable được Spring nhận diện, hoặc custom destroy method). Runner đóng context sau callback, nên resource cleanup có thể được kiểm tra khi cần.

## 15. AutoConfigurations.of và thứ tự của nhiều auto-configurations

Nhiều starters có phụ thuộc giữa các auto-configurations:
- Metrics auto-config cần registry.
- Repository auto-config cần datasource.
- HTTP client auto-config cần codec/client factory.
- Cache auto-config phụ thuộc cache provider.
- Security filter registration phụ thuộc security infrastructure.

Trong runner, có thể đưa nhiều classes vào `AutoConfigurations.of(A.class, B.class)`; Spring Boot áp dụng ordering metadata như trong application. Nếu condition bean phụ thuộc vào bean từ auto-config khác, dùng `@AutoConfiguration(after=...)` hoặc `before=...` khi cần.

**Đừng nhầm ordering của auto-config bean definitions với thứ tự bean instantiation**. `@DependsOn` hoặc constructor injection giải quyết quan hệ khởi tạo, còn `@AutoConfiguration(after=...)` chủ yếu ảnh hưởng thứ tự **định nghĩa/evaluate conditions**.

Một test good practice:
1. Runner chỉ có dependent auto-config → xác nhận không tạo bean nếu dependency không có.
2. Runner có cả dependency auto-config và dependent auto-config → xác nhận bean được tạo.
3. Runner có custom user bean thay thế dependency → xác nhận back-off/conditional behavior đúng.
4. Kiểm tra condition report khi kết quả khác dự kiến.

Khi `@ConditionalOnBean` được đặt trên class configuration ứng dụng thông thường thay vì auto-config, evaluation có thể diễn ra trước một số bean definitions cần thiết. Đó là lý do tài liệu Boot khuyến nghị những bean conditions chủ yếu dùng trong **auto-configuration** nơi ordering được kiểm soát.

## 16. Test failures: đừng “sửa” bằng cách tăng phạm vi không cần thiết

Một số failure modes:

| Triệu chứng | Nguyên nhân có thể | Khắc phục |
|---|---|---|
| `doesNotHaveBean` dù đã bật property | Optional class bị filter/vắng, user context sai, condition khác âm tính | Xem classpath và ConditionEvaluationReport |
| `hasSingleBean` fail vì có 2 beans | `@ConditionalOnMissingBean` thiếu/sai type, custom beans register quá muộn | Đặt conditional đúng, test back-off |
| Default bean vẫn được tạo khi disabled | `@ConditionalOnProperty` sai prefix/name/havingValue | Test missing/false/nontrue |
| Property prefix luôn “Hello” | Đọc sai key hoặc `@Value` không có property | Assert `withPropertyValues` ảnh hưởng bean behavior |
| FilteredClassLoader không làm condition âm tính | Condition đặt ở nơi sai, name sai hoặc test vẫn load class qua đường khác | Đặt class-level condition, xem report |
| `NoClassDefFoundError` khi optional lib vắng | Method/field ký tham chiếu optional class được load quá sớm | Nested conditional configuration |
| Custom user bean không thắng | User config không được thêm vào runner, bean type không match | `withUserConfiguration` đúng class, type |
| Test runner pass nhưng starter không auto-activate trong app | Thiếu/sai `AutoConfiguration.imports` trong JAR | Kiểm tra resources/JAR packaging và smoke test |
| Startup failure khi thiếu configuration property | Bean không thể resolve/bind property bắt buộc | Assert `getStartupFailure`, validate/define defaults |
| `@ConditionalOnWebApplication` luôn không match | Dùng plain ApplicationContextRunner cho web-only config | WebApplicationContextRunner/Reactive...Runner |
| Test pass khi chạy riêng, fail khi chạy suite | System properties/static mutable state/external resources bị chia sẻ | Mỗi scenario dùng runner, tránh global side effects |
| Đổi auto-config ordering làm bean biến mất | `@ConditionalOnBean` được đánh giá trước dependency | @AutoConfiguration after/before và test hai classes |
| Context khởi động rất chậm | Runner vô tình import toàn bộ app/all auto-configurations | Chỉ `AutoConfigurations.of` những class liên quan |
| Native executable test có runtime khác | ApplicationContextRunner không hỗ trợ chạy tests trong native image | Test trên JVM, bổ sung native smoke tests nếu cần |
| Logs ConditionEvaluationReport quá dài | Listener bật INFO cho mọi test | Chỉ bật khi debug ca đặc biệt |
| Bean được tạo nhưng lỗi khi gọi service | Condition chỉ kiểm tra class/property, không test external client | Bổ sung integration test theo dependency thật |
| `@SpringBootTest` report lỗi khó tìm | Khởi động nhiều auto-configs không liên quan | Tách runner tests cho condition-specific logic |

### 16.1. Những anti-pattern cần tránh

**Anti-pattern 1 — gọi factory method trực tiếp.** Điều này bỏ qua Spring conditional evaluation.

**Anti-pattern 2 — dùng `@SpringBootTest` cho mọi tổ hợp enabled/disabled.** Việc khởi tạo toàn bộ app làm test chậm và nhiễu hơn.

**Anti-pattern 3 — assert một bean bằng name rồi bỏ type/behavior.** Có thể lấy nhầm một bean cùng tên nhưng khác implementation nếu cấu hình phức tạp.

**Anti-pattern 4 — mock chính auto-config class.** Test một mock không kiểm tra điều kiện hoặc registration của auto-configuration thật.

**Anti-pattern 5 — cắt bỏ optional dependency khỏi toàn bộ build để kiểm tra missing-class.** Dùng `FilteredClassLoader` để kiểm tra cả positive/negative cases trong cùng test suite.

**Anti-pattern 6 — nhầm runner test với discovery test.** `AutoConfigurations.of` đã đưa class vào runner trực tiếp, không đọc file imports như deployment bình thường.

**Anti-pattern 7 — giữ bean sau callback.** Context đã đóng, bean có thể giữ resource không còn hợp lệ.

**Anti-pattern 8 — kỳ vọng runner là native-image test runner.** Boot docs nêu `ApplicationContextRunner` không hoạt động khi chạy tests **trong native image**; nếu native là yêu cầu, test auto-config logic trên JVM và có native smoke tests tương ứng.

## 17. Khi nào chuyển sang @SpringBootTest hoặc Testcontainers?

`ApplicationContextRunner` mạnh ở câu hỏi **“Bean nào được đăng ký khi có điều kiện X?”**. Khi câu hỏi chuyển thành **“Ứng dụng thật có hoạt động end-to-end không?”**, cần thay test level:

| Mục tiêu | Công cụ |
|---|---|
| Bean được tạo khi enabled property = true | ApplicationContextRunner |
| Bean bị bỏ khi optional class thiếu | FilteredClassLoader + runner |
| User bean override được default | withUserConfiguration + runner |
| Context lỗi khi binding sai | Runner + getStartupFailure |
| Servlet-only/Reactive-only conditional | WebApplicationContextRunner/ReactiveWebApplicationContextRunner |
| Starter JAR được auto-discover đúng | Metadata/package check và @SpringBootTest smoke test |
| JDBC repository tương tác PostgreSQL thật | @DataJpaTest/@SpringBootTest + Testcontainers |
| Filter chain/Security integration hoạt động | @WebMvcTest hoặc @SpringBootTest + MockMvc |
| HTTP endpoint chạy qua server socket | @SpringBootTest(RANDOM_PORT) + HTTP client |
| Kafka/Redis/external SDK thật kết nối | Integration test với service test container |
| Native image startup với auto-config | Native-image integration/smoke test riêng |

Tách hai mức **không trùng lặp vô ích**: runner tests cho branches nhanh, full integration cho một vài đường chính có rủi ro production. Đừng biến một starter nhỏ thành hàng chục full-context tests chỉ để kiểm tra `@ConditionalOnProperty`.

## 18. Phiên bản và phạm vi hỗ trợ

Trong Spring Boot **3.5.x**, những imports chính thuộc các packages:

```java
org.springframework.boot.test.context.runner.ApplicationContextRunner
org.springframework.boot.test.context.runner.WebApplicationContextRunner
org.springframework.boot.test.context.runner.ReactiveWebApplicationContextRunner
org.springframework.boot.test.context.FilteredClassLoader
org.springframework.boot.autoconfigure.AutoConfigurations
org.springframework.boot.autoconfigure.AutoConfiguration
org.springframework.boot.autoconfigure.condition.ConditionalOnProperty
org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean
org.springframework.boot.autoconfigure.condition.ConditionalOnClass
org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener
```

Đây là **danh sách tên fully-qualified để tra cứu**, không phải các `import` Java độc lập hợp lệ vì không có từ khóa `import`. Chú ý Spring Boot 4.x đã tổ chức lại các module/packages test và auto-config một số khu vực; không copy nguyên imports Boot 3.5 vào Boot 4 mà không đối chiếu API chính thức/BOM phiên bản của project.

Từ Boot 3.0, dùng file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` để khai báo danh sách auto-configurations, không dựa vào cách đăng ký auto-configuration bằng `spring.factories` của thế hệ cũ.

**Phạm vi bài:** code kiểm tra auto-configuration JVM theo Boot 3.5.x. Không claim đã chạy Gradle build, không claim compatibility ở một Boot 4 patch cụ thể, và không giả định một native binary sẽ chạy `ApplicationContextRunner`.

## 19. Chạy test và quan sát output

Nếu project có Gradle wrapper:

Linux/macOS:

```bash
./gradlew test --tests "com.example.mini.autoconfigure.GreetingAutoConfigurationTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.mini.autoconfigure.GreetingAutoConfigurationTest"
```

Nếu dùng Maven wrapper với `pom.xml` và dependencies/BOM tương đương:

```bash
./mvnw -Dtest=GreetingAutoConfigurationTest test
```

Windows PowerShell:

```powershell
.\mvnw.cmd -Dtest=GreetingAutoConfigurationTest test
```

Để chạy demo application theo `build.gradle` đã có `SpringBootApplication` main:

```bash
./gradlew bootRun --args='--demo.greeting.enabled=true'
```

Lệnh `bootRun` **không chạy JUnit tests**, và demo app không in greeting bởi vì nó không có runner gọi `GreetingService`; nó chỉ khởi động Spring context. Dùng `test` task để kiểm chứng assertions.

**Kết quả dự kiến** trong môi trường đúng: JUnit tìm và chạy 11 methods, các nhánh condition trên và root failure assertion phù hợp với code mẫu. Đây là **expected behavior, không phải stdout thực**. Phải đọc `build/reports/tests/test/index.html` (Gradle) hoặc `target/surefire-reports/` (Maven), kiểm tra số methods thực chạy, không bị `SKIPPED`, `NO-SOURCE` hoặc cấu hình test runner bỏ qua.

### 19.1. Khi nào cần javac/java?

Các ví dụ `ApplicationContextRunner` yêu cầu Spring Boot/Test/AssertJ/JUnit classes trên classpath. Vì vậy `javac` và `java` đơn lẻ không phải cách tiện lợi để biên dịch toàn project; sử dụng **Gradle/Maven với dependency management**. Nếu tách riêng `DefaultGreetingService` và `GreetingService` thành Java thuần thì có thể dùng `javac`, nhưng việc đó **không kiểm tra conditional auto-configuration** của Spring.

## 20. Checklist QA trước khi chốt một auto-configuration

- [ ] Xác định chính xác các conditions cần kiểm tra; không lấy mọi auto-config của application vào runner.
- [ ] Có `ApplicationContextRunner` nền với `AutoConfigurations.of(...)`.
- [ ] Có test property thiếu, false và true theo `havingValue/matchIfMissing`.
- [ ] Có test một property tùy biến thực sự được inject/bind vào bean.
- [ ] Có positive test assert bean **type, name và behavior** khi contract yêu cầu.
- [ ] Có negative test không có bean khi condition không thỏa.
- [ ] Có user-provided bean test qua `withUserConfiguration`, chứng minh `@ConditionalOnMissingBean` back off.
- [ ] Khi optional dependency liên quan, có `FilteredClassLoader` test absent-class scenario.
- [ ] Có test startup failure bằng `getStartupFailure()` nếu binding/initializer có thể lỗi.
- [ ] Dùng đúng `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` khi condition là web-only.
- [ ] Các runner scenarios không chia sẻ `Environment`/beans và không giữ resource sau callback.
- [ ] Auto-config production đã được liệt kê trong `AutoConfiguration.imports`, được đóng gói đúng JAR.
- [ ] Không nhầm `AutoConfigurations.of` runner test với production discovery verification.
- [ ] Đọc ConditionEvaluationReport khi không hiểu vì sao bean không tạo.
- [ ] Với nhiều auto-config, có ordering tests cho `@ConditionalOnBean` và user bean override.
- [ ] Tránh optional dependency class-loading lỗi trước condition check.
- [ ] Không coi “test runner xanh” là bằng chứng DB/HTTP/Kafka resource reachable.
- [ ] Nếu cần native-image support, có test/smoke strategy riêng vì runner không dùng trong native-image tests.
- [ ] Chạy JUnit bằng build tool và đọc reports trước khi tuyên bố runtime PASS.

## 21. Tài liệu chuẩn để tham khảo

- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): `@AutoConfiguration`, conditions, `ApplicationContextRunner`, `AutoConfigurations`, `FilteredClassLoader`, test user bean overrides và `ConditionEvaluationReportLoggingListener`.
- [Spring Boot 3.5 — ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): runner constructors/configuration.
- [Spring Boot 3.5 — FilteredClassLoader Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/FilteredClassLoader.html): lọc classpath cho test.
- [Spring Boot — @ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): behavior back-off, search strategy và điều kiện trên definitions.
- [Spring Boot — @ConditionalOnProperty Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): semantics `havingValue`, `matchIfMissing`, property names.
- [Spring Boot — ConditionEvaluationReportLoggingListener](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): condition diagnostics.
- [Spring Framework — Testing](https://docs.spring.io/spring-framework/reference/testing.html): Spring TestContext với test contexts và runners.
- [JUnit Jupiter — User Guide](https://docs.junit.org/current/user-guide/): assertions, lifecycle và test reports.

**Kết luận:** `ApplicationContextRunner` cho phép kiểm thử auto-configuration với **một context nhỏ cho mỗi scenario**, không cần khởi động toàn bộ Spring Boot application. Hãy kiểm tra cả hai phía của `@ConditionalOnProperty`, `@ConditionalOnClass` và `@ConditionalOnMissingBean` bằng `withPropertyValues`, `FilteredClassLoader`, `withUserConfiguration`, rồi assert bean thực sự có/không có cùng hành vi của nó. Đừng nhầm `AutoConfigurations.of` với kiểm tra discovery metadata; hãy bổ sung kiểm tra `AutoConfiguration.imports` và smoke test khi phát hành starter. Kết hợp những runner tests nhanh này với một số integration tests có chọn lọc để bảo vệ cả **điều kiện tạo bean** lẫn **hành vi ứng dụng thật**.