# withUserConfiguration và bean do ứng dụng cung cấp khi kiểm thử auto-configuration

Trong Spring Boot, **auto-configuration** cung cấp bean mặc định để một thư viện hoặc starter “hoạt động ngay” khi ứng dụng chưa tự khai báo thành phần tương ứng. Nhưng khi ứng dụng đã cung cấp bean của chính mình, auto-configuration thường phải **nhường quyền (back off)**, thay vì âm thầm tạo thêm một bean cạnh tranh hoặc ghi đè cấu hình người dùng.

Công cụ chuyên dụng để kiểm thử hợp đồng này là `ApplicationContextRunner` cùng:

- `withConfiguration(AutoConfigurations.of(...))`: khai báo auto-configuration đang thử.
- **`withUserConfiguration(MyApplicationConfiguration.class)`**: đưa các lớp `@Configuration` chứa `@Bean` do **ứng dụng** định nghĩa vào test context.
- `withBean(...)`: mô phỏng một bean do ứng dụng cung cấp mà không cần tạo `@Configuration` riêng.
- `withPropertyValues(...)`: kiểm các lựa chọn property của ứng dụng.
- `run(context -> ...)`: tạo context độc lập, assert bean thực sự tồn tại/vắng mặt và đóng context sau khi callback hoàn tất.

Bài này thuộc nhóm **Kiểm thử auto-configuration** của **Spring Boot - testing**, tập trung vào ý nghĩa **withUserConfiguration và bean do ứng dụng cung cấp**. Ta sẽ kiểm mặc định, user bean override theo **kiểu**, thay thế từng phần, nhiều user beans, tên bean, `@Primary`, feature flag, khác biệt giữa **back-off** và **bean definition overriding**, vấn đề thứ tự đánh giá conditions và cách đọc `ConditionEvaluationReport`.

Phần thực hành là **một dự án Maven tự chứa dùng Java 17 + Spring Boot 3.5**. Một auto-configuration tạo `GreetingFormatter` và `GreetingService` mặc định, còn nhiều cấu hình ứng dụng giả lập các lựa chọn override. Bộ **14 JUnit Jupiter tests** chạy nhanh, **không cần Docker, Spring web server hoặc database**.

## 1. Vì sao phải thử với bean do ứng dụng cung cấp?

Hãy hình dung starter của thư viện cung cấp:

```text
Ứng dụng KHÔNG cấu hình gì:
    GreetingAutoConfiguration
        |
        +-- @ConditionalOnMissingBean(GreetingFormatter)
        |       +-- default GreetingFormatter
        |
        +-- @ConditionalOnMissingBean(GreetingService)
                +-- default GreetingService
                           |
                           +-- dùng default formatter

Ứng dụng khai báo @Bean GreetingFormatter của riêng mình:
    UserConfiguration
        |
        +-- @Bean customFormatter
                |
                v
    GreetingAutoConfiguration
        |
        +-- phát hiện GreetingFormatter đã có
        |       +-- KHÔNG tạo default greetingFormatter
        |
        +-- chưa có GreetingService
                +-- tạo default GreetingService
                       +-- inject customFormatter của ứng dụng
```

Hợp đồng quan trọng không chỉ là “context chạy được”:

1. **Mặc định**: nếu ứng dụng không cung cấp bean cùng kiểu, starter phải tạo bean mặc định đúng.
2. **Back-off**: nếu ứng dụng có bean phù hợp, starter phải **không tạo bean mặc định** của phần tương ứng.
3. **Giữ đúng bean**: context phải sử dụng **chính instance/config của ứng dụng**, không tạo instance mặc định rồi áp dụng `@Primary` để che cạnh tranh.
4. **Thay thế từng phần**: ứng dụng có thể chỉ tùy biến formatter, còn service mặc định tiếp tục được auto-config và phải kết nối đúng formatter đó.
5. **Không can thiệp bean không liên quan**: user bean kiểu khác không được làm default formatter biến mất.
6. **Feature flag**: tắt auto-configuration không đồng nghĩa xóa bean mà ứng dụng tự tạo.
7. **Đa nghĩa**: khi ứng dụng cung cấp **hai bean cùng kiểu**, auto config có thể back off nhưng một dependency yêu cầu một bean duy nhất vẫn có thể không resolve nếu không có `@Primary`/`@Qualifier`.

Đó là lý do một test chỉ assert `hasSingleBean(GreetingService.class)` **chưa đủ**. Nó cần kiểm **tên, type, identity và hành vi** của bean, đồng thời chứng minh default bean thật sự đã vắng mặt khi user bean xuất hiện.

## 2. `@ConditionalOnMissingBean` hoạt động thế nào?

Trong Spring Boot, khai báo cơ bản:

```java
@Bean
@ConditionalOnMissingBean(GreetingFormatter.class)
GreetingFormatter greetingFormatter() {
    return new PrefixGreetingFormatter("Hello");
}
```

Đây là snippet trong một auto-configuration, chưa phải chương trình độc lập. Điều kiện nói: **chỉ đăng ký bean mặc định nếu lúc đánh giá chưa có bean phù hợp kiểu `GreetingFormatter`** trong phạm vi tìm kiếm đã cấu hình.

Các điểm cần nhớ:

- `@ConditionalOnMissingBean(GreetingFormatter.class)` kiểm theo **kiểu bean**, không phải chỉ tên method `greetingFormatter`.
- Nếu người dùng đặt tên bean `customFormatter` nhưng kiểu `GreetingFormatter`, điều kiện vẫn có thể **không match** và auto config phải back off.
- Nếu đặt `@ConditionalOnMissingBean` lên `@Bean` mà **không cung cấp value/type/name/annotation**, Spring Boot mặc định lấy **kiểu trả về của method** làm đối tượng kiểm. Ví dụ `@Bean GreetingFormatter greetingFormatter()` kiểm `GreetingFormatter`.
- Nếu dùng `@ConditionalOnMissingBean(name = "greetingFormatter")`, điều kiện kiểm **tên bean**; một bean cùng kiểu nhưng tên khác **không đủ** để khiến điều kiện này back off. Vì thế chọn kiểu khi muốn cho app thay implementation theo interface.
- Theo Javadoc 3.5, phép kiểm phụ thuộc **bean definitions đã được xử lý tới thời điểm đánh giá**; các bean không là autowire/default candidates có semantics riêng. Không được hiểu điều kiện như một phép dò mọi bean “có thể xuất hiện trong tương lai”.
- Khi có parent/child contexts, thuộc tính `search` quyết định có xét parent hay không. Trên hệ phân cấp context phức tạp, test cần mô phỏng hierarchy phù hợp.
- Với nhiều bean conditions, order giữa các auto-configurations có thể cần `@AutoConfiguration(after = ...)` hoặc `@AutoConfigureAfter`.

**Tại sao đặt ở auto-configuration?** Spring Boot cố ý xử lý auto-configurations **sau user-defined bean definitions**, giúp `@ConditionalOnMissingBean` nhìn thấy thành phần ứng dụng trước khi quyết định tạo default. Đặt điều kiện này vào một `@Configuration` thông thường được component scan tùy thứ tự có thể cho kết quả thiếu ổn định. Tài liệu Spring Boot khuyến nghị dùng `@ConditionalOnBean` và `@ConditionalOnMissingBean` chủ yếu trong auto-configurations.

### Kiểu trả về của `@Bean` cũng là dữ liệu đầu vào cho condition

Một sai lầm khó thấy:

```java
@Configuration(proxyBeanMethods = false)
class ApplicationConfiguration {
    @Bean
    Object customFormatter() {
        return new PrefixGreetingFormatter("APP");
    }
}
```

Dù runtime object triển khai `GreetingFormatter`, lúc đánh giá conditions BeanFactory có thể **chỉ biết return type `Object`** từ method signature trước khi instantiate. Vì vậy không nên làm method quá mất thông tin kiểu khi auto-config cần phát hiện bean theo interface/implementation. Khai báo `@Bean GreetingFormatter customFormatter()` là đủ cho contract thử ở bài này; trong thư viện thực, cung cấp kiểu return rõ và cụ thể nhất có thể theo khuyến nghị Spring Boot.

## 3. `withUserConfiguration` khác gì `withConfiguration` và `withBean`?

| API | Mục đích | Dùng khi |
|---|---|---|
| `withConfiguration(AutoConfigurations.of(AutoConfig.class))` | Đưa **auto-configuration** vào context theo ordering auto-config | Test default, conditions và dependencies của starter |
| **`withUserConfiguration(UserConfig.class)`** | Đưa `@Configuration`/`@Bean` **do ứng dụng cung cấp** vào context | Test custom bean được ưu tiên, auto backs off đúng |
| `withBean(MyInterface.class, () -> new Impl())` | Đăng ký trực tiếp một user bean qua supplier | Chỉ cần mô phỏng một bean, không cần `@Configuration` |
| `withPropertyValues("demo.x=y")` | Điều chỉnh `Environment` cho một run | Kiểm property conditions, prefix, feature flags |
| `withClassLoader(new FilteredClassLoader(...))` | Giả lập thiếu class trên classpath | Kiểm `@ConditionalOnClass`/missing class |
| `withInitializer(...)` | Khởi tạo bổ sung, report hoặc test context customization | Diagnostic conditions |
| `withParent(parentContext)` | Tạo hierarchy parent/child | Test visibility của bean từ parent context |
| `withAllowBeanDefinitionOverriding(boolean)` | Cho phép/cấm hai definitions **cùng tên** đè nhau | Test collision có chủ đích, **không thay back-off** |

**Hai điểm không được nhầm:**

- `withUserConfiguration(...)` **không phải lệnh “override bean definition”**; nó tạo bối cảnh ứng dụng đã khai báo bean để điều kiện auto config được đánh giá đúng. Với `@ConditionalOnMissingBean`, **default bean không được đăng ký**, nên không có ghi đè.
- `withConfiguration(...)` thường nhận `AutoConfigurations.of(...)`, không phải cứ truyền một `@Configuration` thường vào đó rồi mong nó được coi như user configuration. Cần giữ đúng role của từng cấu hình để thứ tự condition giống ứng dụng thực.

### Runner có thể tái sử dụng an toàn

`ApplicationContextRunner` là **immutable-style test builder**: `withUserConfiguration`, `withPropertyValues`, `withBean` trả **runner mới** với customizations bổ sung; runner gốc vẫn giữ base config.

```java
ApplicationContextRunner base = new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(GreetingAutoConfiguration.class));

ApplicationContextRunner withUser =
        base.withUserConfiguration(UserFormatterConfiguration.class);

withUser.run(context -> {
    // Bean do ứng dụng cung cấp; auto formatter back off.
});

base.run(context -> {
    // Vẫn không có user bean; default formatter được tạo.
});
```

Đây là snippet với các lớp giả định trong ví dụ phần 5. Chạy `run` sẽ tạo context mới rồi đóng tự động, nên bạn không cần gọi `@DirtiesContext` để reset một runner nhỏ. Không giữ bean lấy từ callback rồi sử dụng sau khi context đã đóng nếu bean có resources/lifecycle phụ thuộc context.

## 4. Ma trận xác minh back-off đúng nghĩa

| Test context | GreetingFormatter expected | GreetingService expected | Kết luận |
|---|---|---|---|
| Không user config | default formatter | default service | Auto-config hoạt động |
| User khai báo `GreetingFormatter customFormatter` | chỉ **customFormatter** | default service dùng custom | Back-off **theo kiểu** |
| `withBean(GreetingFormatter.class, supplier)` | chỉ bean từ supplier | default service dùng bean từ supplier | Bean trực tiếp cũng được tôn trọng |
| User chỉ khai báo `GreetingService customService` | default formatter vẫn có | chỉ **customService** | Back-off **từng bean** |
| User khai báo cả formatter + service | chỉ hai user beans | không default bean nào cùng kiểu | App toàn quyền lựa chọn |
| Có user bean kiểu `String` | default formatter vẫn có | default service vẫn có | Bean không liên quan không chặn auto |
| Property `demo.greeting.prefix=Bonjour` | default với prefix Bonjour | default service | Property config tác động default |
| Có user formatter + property prefix | user formatter giữ nguyên | service dùng user formatter | Default property không ghi đè user bean |
| Feature flag `demo.greeting.enabled=false` | không auto formatter | không auto service | Auto-config bị vô hiệu |
| Feature flag false + user formatter | user formatter vẫn tồn tại | không auto service | Tắt auto ≠ xóa app beans |
| User bean cùng **tên** default và cùng kiểu | user bean | default service | Back-off, không cần override definitions |
| Hai user formatters khác tên | hai formatters | default service có thể fail ambiguous injection | MissingBean không tự xử lý ambiguity |
| Hai user formatters, một `@Primary` | hai formatters | default service chọn primary | Primary giải quyết injection, không tạo back-off |
| Custom runner rồi run base runner | mỗi context theo customization riêng | độc lập | Runner base không bị mutate |

Bài test sẽ assert **kiểu, tên, behavior** và phản hồi khi startup fail; không coi “context chạy” là đủ.

## 5. Ví dụ Maven hoàn chỉnh: Java 17 + Spring Boot 3.5

Đây là ví dụ theo kiểu **starter/library**, không phải ứng dụng web: `ApplicationContextRunner` trực tiếp đưa auto config vào Spring context. Không cần main class `@SpringBootApplication` để chạy JUnit tests. Khi đóng gói starter thật, file `AutoConfiguration.imports` giúp ứng dụng bên ngoài khám phá auto config.

### 5.1. Cấu trúc thư mục

```text
greeting-autoconfigure-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/greeting/
    │   │   ├── GreetingFormatter.java
    │   │   ├── PrefixGreetingFormatter.java
    │   │   ├── GreetingService.java
    │   │   └── autoconfigure/
    │   │       └── GreetingAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/example/greeting/autoconfigure/
        └── GreetingAutoConfigurationTest.java
```

**Không tạo `@SpringBootApplication` trong cùng package rồi component scan trực tiếp auto-configuration** để test: một starter phải được Boot import theo cơ chế auto config chuẩn, thay vì dựa vào component scanning của ứng dụng. Runner `withConfiguration(AutoConfigurations.of(...))` xử lý nhập auto config trong test; file imports phục vụ module khi được sử dụng như dependency thật.

### 5.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>greeting-autoconfigure-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
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
</project>
```

`spring-boot-starter` cung cấp core Spring context + auto-configuration; `spring-boot-starter-test` đưa JUnit Jupiter và AssertJ cùng test runner utilities. Không thêm `spring-boot-maven-plugin` vì đây là **library jar không có main class**, không phải executable Boot app. Lệnh `mvn test` chạy JUnit tests; `mvn package` đóng gói jar thư viện theo Maven chuẩn.

### 5.3. Interface ứng dụng: `GreetingFormatter.java`

File **`src/main/java/com/example/greeting/GreetingFormatter.java`**:

```java
package com.example.greeting;

public interface GreetingFormatter {
    String format(String name);
}
```

Đây là contract mà ứng dụng có thể cung cấp implementation riêng. Auto-configuration chỉ nên đăng ký default nếu bean theo contract này chưa tồn tại.

### 5.4. Implementation mặc định: `PrefixGreetingFormatter.java`

File **`src/main/java/com/example/greeting/PrefixGreetingFormatter.java`**:

```java
package com.example.greeting;

import java.util.Objects;

public final class PrefixGreetingFormatter
        implements GreetingFormatter {

    private final String prefix;

    public PrefixGreetingFormatter(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    @Override
    public String format(String name) {
        return prefix + ", " + name;
    }
}
```

Các test phân biệt giá trị bằng prefix `Hello`, `Bonjour`, `APP`, `DIRECT`...; không phụ thuộc object identity hay system locale. Lớp không dùng `@Component` để việc tạo bean hoàn toàn do auto-config hoặc user config quyết định.

### 5.5. Service nghiệp vụ: `GreetingService.java`

File **`src/main/java/com/example/greeting/GreetingService.java`**:

```java
package com.example.greeting;

import java.util.Objects;

public final class GreetingService {

    private final GreetingFormatter formatter;

    public GreetingService(GreetingFormatter formatter) {
        this.formatter = Objects.requireNonNull(formatter);
    }

    public String greet(String name) {
        return formatter.format(name);
    }
}
```

Ta cố tình để constructor nhận **interface** `GreetingFormatter`: nếu ứng dụng khai báo hai beans loại đó mà không có `@Primary`/`@Qualifier`, Spring sẽ không thể quyết định dependency độc nhất khi tạo default `GreetingService`. Test negative sẽ chứng minh sự khác biệt giữa **back-off thành công** và **dependency injection vẫn thất bại**.

### 5.6. Auto-configuration cần thử

File **`src/main/java/com/example/greeting/autoconfigure/GreetingAutoConfiguration.java`**:

```java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingFormatter;
import com.example.greeting.GreetingService;
import com.example.greeting.PrefixGreetingFormatter;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.greeting",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingFormatter.class)
    GreetingFormatter greetingFormatter(
            @Value("${demo.greeting.prefix:Hello}") String prefix) {
        return new PrefixGreetingFormatter(prefix);
    }

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService(GreetingFormatter formatter) {
        return new GreetingService(formatter);
    }
}
```

Hợp đồng của cấu hình:

- `@AutoConfiguration`: Boot xem đây là cấu hình tự động, được xử lý trong giai đoạn auto config.
- `@ConditionalOnProperty` **ở mức class**: khi `demo.greeting.enabled=false`, **cả hai default bean methods không được nạp**. Nếu không khai property, `matchIfMissing=true` cho phép default.
- `@ConditionalOnMissingBean(GreetingFormatter.class)`: không tạo formatter nếu app có một formatter bean hợp lệ, bất kể tên bean ứng dụng đặt.
- `@ConditionalOnMissingBean(GreetingService.class)`: service mặc định chỉ được đăng ký nếu app chưa cung cấp service theo kiểu.
- `@Value("${demo.greeting.prefix:Hello}")`: prefix mặc định `Hello`; properties của ứng dụng chỉ cấu hình **default formatter**, không thay nội dung formatter user-defined.
- `GreetingService greetingService(GreetingFormatter formatter)`: tham số lấy từ context nên nhận custom user formatter nếu auto formatter đã back off.

**Lưu ý về return type:** ở đây `GreetingFormatter` là contract public và condition kiểm tường minh chính interface đó. Khi code thật có nhiều cấp kế thừa hoặc bean conditions tinh vi, ưu tiên khai báo `@Bean` return type đủ cụ thể (tránh `Object` hoặc interface quá rộng) theo khuyến nghị Spring Boot.

### 5.7. Auto-configuration imports

File đúng tên **`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**:

```text
com.example.greeting.autoconfigure.GreetingAutoConfiguration
```

File dùng **mỗi dòng một tên class đầy đủ**, không có dấu phẩy hay XML. Đây là cách Boot 3.x phát hiện auto-configuration khi jar được thêm như dependency vào ứng dụng. Một auto-config class **không được dựa vào component scan** để tìm thấy; `@Import` ứng dụng có thể cố tình đưa vào nhưng không đại diện cơ chế starter chuẩn. Trong test bằng runner, ta đưa class **tường minh** qua `AutoConfigurations.of`, nên bài không cần khởi động `SpringApplication`.

### 5.8. JUnit tests: 14 kịch bản về user configuration

File **`src/test/java/com/example/greeting/autoconfigure/GreetingAutoConfigurationTest.java`**:

```java
package com.example.greeting.autoconfigure;

import com.example.greeting.GreetingFormatter;
import com.example.greeting.GreetingService;
import com.example.greeting.PrefixGreetingFormatter;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.NoUniqueBeanDefinitionException;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            GreetingAutoConfiguration.class));

    @Test
    void noUserBeanCreatesBothDefaults() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(GreetingFormatter.class);
            assertThat(context).hasSingleBean(GreetingService.class);
            assertThat(context).hasBean("greetingFormatter");
            assertThat(context).hasBean("greetingService");

            assertThat(context.getBean(GreetingService.class)
                    .greet("Lan")).isEqualTo("Hello, Lan");
        });
    }

    @Test
    void userFormatterMakesOnlyFormatterDefaultBackOff() {
        runner.withUserConfiguration(UserFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasSingleBean(GreetingService.class);

                    assertThat(context).hasBean("customFormatter");
                    assertThat(context).doesNotHaveBean("greetingFormatter");
                    assertThat(context).hasBean("greetingService");

                    assertThat(context.getBean("customFormatter"))
                            .isSameAs(context.getBean(
                                    GreetingFormatter.class));
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("APP, Lan");
                });
    }

    @Test
    void withBeanRegistersUserBeanWithoutConfigurationClass() {
        runner.withBean(
                GreetingFormatter.class,
                () -> new PrefixGreetingFormatter("DIRECT"))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("DIRECT, Lan");
                });
    }

    @Test
    void userServiceMakesOnlyServiceDefaultBackOff() {
        runner.withUserConfiguration(UserServiceConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasSingleBean(GreetingService.class);
                    assertThat(context).hasBean("greetingFormatter");
                    assertThat(context).hasBean("customService");
                    assertThat(context).doesNotHaveBean("greetingService");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan"))
                            .isEqualTo("APP-SERVICE, Lan");
                });
    }

    @Test
    void userCanSupplyBothBeansAndKeepBothDefaultsOut() {
        runner.withUserConfiguration(BothUserBeansConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasSingleBean(GreetingService.class);

                    assertThat(context).hasBean("appFormatter");
                    assertThat(context).hasBean("appService");
                    assertThat(context).doesNotHaveBean("greetingFormatter");
                    assertThat(context).doesNotHaveBean("greetingService");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("APP-BOTH, Lan");
                });
    }

    @Test
    void unrelatedUserBeanDoesNotPreventDefaultBeans() {
        runner.withUserConfiguration(UnrelatedUserConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasBean("applicationMarker");
                    assertThat(context).hasBean("greetingFormatter");
                    assertThat(context).hasBean("greetingService");
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("Hello, Lan");
                });
    }

    @Test
    void propertyCustomizesDefaultWhenUserHasNotSuppliedIt() {
        runner.withPropertyValues("demo.greeting.prefix=Bonjour")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasBean("greetingFormatter");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("Bonjour, Lan");
                });
    }

    @Test
    void propertyForDefaultDoesNotReplaceUserFormatter() {
        runner.withPropertyValues("demo.greeting.prefix=Bonjour")
                .withUserConfiguration(UserFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).doesNotHaveBean("greetingFormatter");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("APP, Lan");
                });
    }

    @Test
    void disabledFeatureCreatesNoAutoBeans() {
        runner.withPropertyValues("demo.greeting.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(GreetingFormatter.class);
                    assertThat(context).doesNotHaveBean(GreetingService.class);
                });
    }

    @Test
    void disabledAutoConfigurationDoesNotDeleteUserBeans() {
        runner.withPropertyValues("demo.greeting.enabled=false")
                .withUserConfiguration(UserFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasBean("customFormatter");
                    assertThat(context).doesNotHaveBean(GreetingService.class);
                    assertThat(context.getBean(GreetingFormatter.class)
                            .format("Lan")).isEqualTo("APP, Lan");
                });
    }

    @Test
    void sameNameUserBeanBacksOffWithoutDefinitionOverride() {
        runner.withAllowBeanDefinitionOverriding(false)
                .withUserConfiguration(SameNameUserConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(GreetingFormatter.class);
                    assertThat(context).hasBean("greetingFormatter");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("SAME-NAME, Lan");
                });
    }

    @Test
    void twoUserFormattersWithoutPrimaryMakeServiceAmbiguous() {
        runner.withUserConfiguration(TwoFormattersConfig.class)
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context).getFailure()
                            .hasRootCauseInstanceOf(
                                    NoUniqueBeanDefinitionException.class);
                });
    }

    @Test
    void primaryChoosesInjectionButDoesNotRemoveOtherUserBean() {
        runner.withUserConfiguration(PrimaryFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).getBeans(GreetingFormatter.class)
                            .hasSize(2);
                    assertThat(context).doesNotHaveBean("greetingFormatter");
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("PRIMARY, Lan");
                });
    }

    @Test
    void userCustomizationDoesNotMutateBaseRunner() {
        runner.withUserConfiguration(UserFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context.getBean(GreetingService.class)
                            .greet("Lan")).isEqualTo("APP, Lan");
                });

        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasBean("greetingFormatter");
            assertThat(context.getBean(GreetingService.class)
                    .greet("Lan")).isEqualTo("Hello, Lan");
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFormatterConfig {
        @Bean
        GreetingFormatter customFormatter() {
            return new PrefixGreetingFormatter("APP");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserServiceConfig {
        @Bean
        GreetingService customService() {
            return new GreetingService(
                    new PrefixGreetingFormatter("APP-SERVICE"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BothUserBeansConfig {
        @Bean
        GreetingFormatter appFormatter() {
            return new PrefixGreetingFormatter("APP-BOTH");
        }

        @Bean
        GreetingService appService(GreetingFormatter formatter) {
            return new GreetingService(formatter);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UnrelatedUserConfig {
        @Bean
        String applicationMarker() {
            return "hello";
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class SameNameUserConfig {
        @Bean
        GreetingFormatter greetingFormatter() {
            return new PrefixGreetingFormatter("SAME-NAME");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class TwoFormattersConfig {
        @Bean
        GreetingFormatter firstFormatter() {
            return new PrefixGreetingFormatter("ONE");
        }

        @Bean
        GreetingFormatter secondFormatter() {
            return new PrefixGreetingFormatter("TWO");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class PrimaryFormatterConfig {
        @Bean
        @Primary
        GreetingFormatter primaryFormatter() {
            return new PrefixGreetingFormatter("PRIMARY");
        }

        @Bean
        GreetingFormatter secondaryFormatter() {
            return new PrefixGreetingFormatter("SECONDARY");
        }
    }
}
```

### 5.9. Đối chiếu từng test với yêu cầu

| Test method | Input của context | Expected và điều đã chứng minh |
|---|---|---|
| `noUserBeanCreatesBothDefaults` | Chỉ auto-config | Hai default beans; behavior `Hello, Lan` |
| `userFormatterMakesOnlyFormatterDefaultBackOff` | `withUserConfiguration(UserFormatterConfig.class)` | Không có bean tên `greetingFormatter`, chỉ custom formatter; service mặc định dùng custom |
| `withBeanRegistersUserBeanWithoutConfigurationClass` | `withBean(GreetingFormatter.class, supplier)` | Bean trực tiếp cũng làm default back off |
| `userServiceMakesOnlyServiceDefaultBackOff` | User-provided service | Default formatter còn; default service nhường custom service |
| `userCanSupplyBothBeansAndKeepBothDefaultsOut` | Cả hai user beans | Không có default, service dùng user formatter |
| `unrelatedUserBeanDoesNotPreventDefaultBeans` | `String applicationMarker` | Bean khác kiểu không ảnh hưởng default |
| `propertyCustomizesDefaultWhenUserHasNotSuppliedIt` | Prefix property | Default nhận giá trị Bonjour |
| `propertyForDefaultDoesNotReplaceUserFormatter` | User formatter + Bonjour | User bean giữ hiệu lực, không bị property default ghi đè |
| `disabledFeatureCreatesNoAutoBeans` | Enabled=false | Không có hai auto beans |
| `disabledAutoConfigurationDoesNotDeleteUserBeans` | Enabled=false + custom user formatter | User bean vẫn tồn tại, auto service vắng |
| `sameNameUserBeanBacksOffWithoutDefinitionOverride` | Same name, override=false | Context vẫn start do back-off, không cần định nghĩa bị ghi đè |
| `twoUserFormattersWithoutPrimaryMakeServiceAmbiguous` | Hai formatters, không primary | Startup fail do dependency ambiguous; condition đã nhường nhưng chưa đủ |
| `primaryChoosesInjectionButDoesNotRemoveOtherUserBean` | Hai formatters, một primary | Cả hai user beans còn; service dùng primary |
| `userCustomizationDoesNotMutateBaseRunner` | Run user rồi run base | Hai contexts độc lập, không bị contamination |

**14 tests** chỉ dùng `ApplicationContextRunner`; không dùng `@SpringBootTest`, không mở web server. Runner tự đóng context sau callback. Test nhiều formatter mong **startup fail** vẫn **PASS** khi fail đúng root cause, không được hiểu đó là lỗi không mong muốn của JUnit.

### 5.10. Chạy và xác minh

Yêu cầu JDK 17+, Maven, không cần Docker:

```bash
mvn test
```

Hoặc chạy một class:

```bash
mvn -Dtest=GreetingAutoConfigurationTest test
```

Với POM và mã nguồn như trên, dự kiến Maven Surefire báo **Tests run: 14, Failures: 0, Errors: 0**. Case có chủ đích làm context fail sẽ được assert `hasFailed()` và root cause, nên vẫn là JUnit PASS.

Đây là ví dụ được rà soát theo API **Spring Boot 3.5.0 + Java 17**, **không phải khẳng định đã thực thi Maven trong quá trình soạn bài**. Khi áp dụng vào module thực, chạy test trên CI để kiểm compatibility với dependencies và classpath đang có.

## 6. Làm sao chắc chắn bean do ứng dụng được chọn?

Không nên chỉ viết:

```java
assertThat(context).hasSingleBean(GreetingFormatter.class);
```

Assertion trên có thể PASS trong **cả hai trường hợp**: context có default formatter hoặc context có custom formatter. Muốn chứng minh **back-off**, test đủ ba lớp:

1. **Bean count/type**: đúng một bean của kiểu quan tâm.
2. **Bean name/identity**: có `customFormatter` và **không có `greetingFormatter`** (nếu tên mặc định đã biết).
3. **Behavior hoặc instance**: gọi service phải cho `APP, Lan`; `context.getBean("customFormatter")` trùng object `context.getBean(GreetingFormatter.class)`.

```java
assertThat(context).hasSingleBean(GreetingFormatter.class);
assertThat(context).hasBean("customFormatter");
assertThat(context).doesNotHaveBean("greetingFormatter");
assertThat(context.getBean("customFormatter"))
        .isSameAs(context.getBean(GreetingFormatter.class));
assertThat(context.getBean(GreetingService.class).greet("Lan"))
        .isEqualTo("APP, Lan");
```

Snippet lấy từ test có user formatter của phần 5. Nếu auto-config được thay đổi để luôn tạo default bean bên cạnh user bean, ít nhất một assertion về count/vắng bean sẽ fail; nếu service tiêm nhầm default, assertion behavior sẽ fail.

### User bean theo tên khác nhưng cùng kiểu

`@ConditionalOnMissingBean(GreetingFormatter.class)` đánh giá **kiểu**. Vì vậy bean user tên `customFormatter` vẫn đủ làm default `greetingFormatter` nhường chỗ. Đây là contract chuẩn của các starter cung cấp default implementation qua interface.

**Không viết nhầm**:

```java
@Bean
@ConditionalOnMissingBean(name = "greetingFormatter")
GreetingFormatter greetingFormatter() {
    return new PrefixGreetingFormatter("Hello");
}
```

Nếu ứng dụng khai báo `@Bean GreetingFormatter customFormatter()`, bean tên `greetingFormatter` chưa có nên điều kiện theo tên có thể tạo **thêm default formatter**. Lúc đó hai beans cùng kiểu gây ambiguous injection nếu không có primary/qualifier. Nếu mục tiêu cho phép thay theo interface, chọn condition theo kiểu thích hợp.

### User bean theo tên trùng default

Trong test `SameNameUserConfig`, user cũng khai báo method `greetingFormatter()`. Do condition theo type phát hiện bean của ứng dụng, auto **không đăng ký definition cùng tên**. Điều đó là **back-off**, không phải Spring ghi đè bean cùng tên. Ta cố tình cấu hình `withAllowBeanDefinitionOverriding(false)` để chứng minh startup vẫn thành công.

Nếu bỏ `@ConditionalOnMissingBean` và để hai definitions trùng tên, context thường gặp lỗi kiểu `BeanDefinitionOverrideException` khi overriding không được phép. Bật `spring.main.allow-bean-definition-overriding=true` chỉ để test xanh có thể che một starter vi phạm hợp đồng, không phải cách sửa đúng.

## 7. Nhiều user beans: back-off và autowiring là hai bài kiểm khác nhau

Một tình huống đáng học:

```java
@Configuration(proxyBeanMethods = false)
class MultipleFormatters {
    @Bean
    GreetingFormatter first() {
        return new PrefixGreetingFormatter("ONE");
    }

    @Bean
    GreetingFormatter second() {
        return new PrefixGreetingFormatter("TWO");
    }
}
```

Tại thời điểm condition, đã có bean `GreetingFormatter` nên default formatter **back off thành công**. Tuy nhiên auto service nhận một `GreetingFormatter` trong constructor, còn context đang có **hai lựa chọn**. Nếu không có `@Primary`, `@Qualifier` hoặc tên parameter có thể phân giải rõ, context có thể fail `NoUniqueBeanDefinitionException`.

Điều này **không chứng minh @ConditionalOnMissingBean bị hỏng**; nó chứng minh contract của người dùng đã tạo dependency ambiguity. Thư viện có thể:

- Chỉ hoạt động khi có đúng một candidate (dùng điều kiện phù hợp, ví dụ `@ConditionalOnSingleCandidate` ở nơi cần).
- Cho người dùng chỉ định `@Primary` hoặc `@Qualifier`.
- Chấp nhận và xử lý collection/map các beans khi business logic thực sự cần nhiều implementation.
- Đưa ra error message/diagnostic rõ, không chọn tùy ý theo thứ tự đăng ký.

Trong test `PrimaryFormatterConfig`, Spring giữ **cả hai user beans**, default formatter vẫn back off, còn service nhận bean `@Primary`. `@Primary` **không** phải điều kiện làm auto bean biến mất; **@ConditionalOnMissingBean** mới chịu trách nhiệm back-off.

### Đừng lạm dụng `@Primary` để che lỗi của auto-configuration

Nếu auto config tạo default formatter **cùng lúc** với custom formatter, `@Primary` giúp injection chọn một bean nhưng vẫn còn **hai beans**. Các consumer dùng `List<GreetingFormatter>` hoặc `Map<String,GreetingFormatter>` sẽ nhìn thấy cả hai; behavior có thể khác production expectation. Với starter cho phép user override theo kiểu, test nên yêu cầu **chỉ có user bean** khi custom đã hiện diện.

## 8. Property conditions và thứ tự ưu tiên

Một property có thể điều chỉnh default, nhưng không nên **ghi đè đối tượng do ứng dụng tự tạo**:

```text
Runner:
  withPropertyValues("demo.greeting.prefix=Bonjour")
  + auto-config only
  -> greetingFormatter("Bonjour")
  -> greetingService uses formatter("Bonjour")

Runner:
  withUserConfiguration(UserFormatterConfig.class)
  withPropertyValues("demo.greeting.prefix=Bonjour")
  -> customFormatter("APP")
  -> no default greetingFormatter bean
  -> greetingService uses customFormatter("APP")
```

Điểm cần test là **giá trị và loại bean thực sự được dùng**, không chỉ Environment có một property. Nếu app chọn implementation riêng, property chỉ dành cho default implementation có thể không còn tác dụng.

### Feature flag ở class-level

`@ConditionalOnProperty(prefix="demo.greeting", name="enabled", havingValue="true", matchIfMissing=true)` trên class auto-config:

- **Property vắng** → auto-config được phép hoạt động.
- `demo.greeting.enabled=true` → auto-config được phép hoạt động.
- `demo.greeting.enabled=false` → auto-config class không tạo default formatter/service.
- User config vẫn được đăng ký độc lập với auto-config, vì không nằm bên trong class đó.

Đừng hiểu “disable starter” là “xóa mọi bean của ứng dụng cùng type”. Spring không tự xóa `@Bean` của người dùng chỉ vì một auto-configuration class được condition off.

Nếu product yêu cầu tắt cả feature ở service layer, thiết kế và test thêm điều kiện ở nơi sử dụng user bean, không hy vọng auto-config property tự quyết định mọi component.

## 9. ConditionEvaluationReport: tìm lý do auto bean được tạo hay không

Khi test fail, hãy xem **conditions**, thay vì tăng số assertion theo cảm tính. Spring Boot cung cấp `ConditionEvaluationReport`, và trong unit test có thể bật listener chính thức:

```java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

ApplicationContextRunner debugRunner = new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(GreetingAutoConfiguration.class))
        .withInitializer(
                ConditionEvaluationReportLoggingListener
                        .forLogLevel(LogLevel.INFO));
```

Đây là snippet không độc lập (cần class `GreetingAutoConfiguration` của ví dụ). Khi gọi `debugRunner.withUserConfiguration(...).run(...)`, Spring Boot có thể in report tại log level chỉ định. Bật trên test cần chẩn đoán; không spam log toàn CI trong mọi lượt chạy.

Có thể xem programmatically từ một context **đã start**:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    if (source.contains("GreetingAutoConfiguration")) {
        System.out.println(source + " -> " + outcomes.isFullMatch());
    }
});
```

Đây là snippet cần import `org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport` và biến `context` trong callback của runner. Tên source thường có class/method, nhưng format/chi tiết message có thể thay đổi giữa Spring Boot patch versions. Test **không nên phụ thuộc nguyên văn điều kiện** hoặc tên log message khi chỉ cần chứng minh bean count/identity/behavior.

### Đọc report theo thứ tự

1. **Property condition**: `demo.greeting.enabled` có match không?
2. **Missing-bean condition**: có bean nào khiến `GreetingFormatter` hoặc `GreetingService` default back off?
3. **Type information**: user `@Bean` method khai kiểu gì? Có return type quá rộng không?
4. **Scope và candidate**: bean nằm ở child/parent context? Có excluded/non-default/autowireCandidate settings không?
5. **Auto-configuration order**: dependency config nào chạy trước? Có component scan vô tình đăng ký class auto config quá sớm không?
6. **Beans thực tế**: `context.getBeanNamesForType(...)` hoặc AssertJ assertions nói gì?
7. **Startup failure**: dùng `assertThat(context).hasFailed()` và `getFailure()` thay vì gọi `getBean(...)` trên failed context.

Một report có negative match do `@ConditionalOnMissingBean` **có thể là đúng thiết kế**: nó chứng minh auto-config đã nhường user bean, không phải test failure.

## 10. Những điều `ApplicationContextRunner` chưa kiểm thay cho full ứng dụng

`ApplicationContextRunner` chủ yếu dùng cho **non-web test context** nhỏ. Nó rất phù hợp để thử bean registration và conditions, nhưng không đồng nghĩa:

- Một project thật đã import đúng starter jar khi chạy `SpringApplication` với mọi classpath/dependency và profiles.
- HTTP servlet/reactive context đúng nếu auto-config phụ thuộc web runtime.
- User component scanning, conditional scan, BeanFactoryPostProcessors từ các modules khác được mô phỏng đầy đủ.
- Database, Redis, Kafka, OAuth2 hoặc external services được kết nối thật.
- Ahead-of-time native image support: tài liệu Spring Boot nêu rõ `ApplicationContextRunner` **không dùng được khi chạy test trong native image**.
- Full application startup thành công với tất cả auto-configurations khác.

**Khi nào đổi runner?**

| Nhu cầu | Công cụ |
|---|---|
| Bean conditions không phụ thuộc web | `ApplicationContextRunner` |
| Auto-config yêu cầu servlet web context | `WebApplicationContextRunner` |
| Auto-config yêu cầu reactive WebFlux context | `ReactiveWebApplicationContextRunner` |
| Kiểm auto-configuration trong ứng dụng thật, profiles, dependency graph | `@SpringBootTest`, test slice phù hợp |
| Kiểm library hoạt động khi được import từ artifact thật | Consumer/sample application integration test |
| Kiểm classpath không có một dependency | `FilteredClassLoader` kết hợp runner |
| Kiểm readiness của DB/broker | Testcontainers hoặc service integration tests |

Đừng dùng `@SpringBootTest` đầy đủ cho **mỗi** tổ hợp user bean/property nhỏ nếu runner đã mô phỏng đúng; chi phí startup cao và các auto-configurations khác có thể che vấn đề. Ngược lại, đừng chỉ dựa vào runner rồi tuyên bố đã kiểm toàn bộ hoạt động của starter trong consumer app thật.

## 11. Các lỗi hay gặp với `withUserConfiguration`

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Dùng `withConfiguration` cho lớp user như auto config | Thứ tự điều kiện có thể không như app | Dùng `withUserConfiguration` cho `@Bean` của app |
| Đặt `@ConditionalOnMissingBean` vào config scan thông thường | Condition đánh giá trước khi đủ bean defs | Đặt trong auto-config được Boot load đúng thứ tự |
| Chỉ assert `hasSingleBean` | Không biết bean là default hay user | Assert thêm tên, identity, behavior |
| Kiểm missing bean theo **name** khi cần replace theo **type** | User bean tên khác không khiến default back off | Dùng `@ConditionalOnMissingBean(GreetingFormatter.class)` |
| User `@Bean Object ...` trả đúng implementation | Type inference có thể không thấy type thật sớm | Khai báo return type cụ thể/đúng contract |
| Dựa vào `@Primary` để xem như đã back off | Default bean vẫn tồn tại cạnh user | Assert default bean **vắng**, số lượng đúng |
| Hai user beans cùng type không qualifier | Dependency ambiguous | Dùng `@Primary`/`@Qualifier` hoặc thiết kế multi-bean |
| Bật bean-definition overriding để test pass | Che bean collision | Sửa condition và thứ tự config |
| Dùng `@MockBean`/`@MockitoBean` thay toàn bộ user config | Không chứng minh declaration/return type của app | Dùng `withUserConfiguration`/`withBean` để test conditional registration |
| Không kiểm property disabled + user bean | Có thể kết luận nhầm feature flag xóa app bean | Test user bean độc lập với auto feature flag |
| Sử dụng component scan để tìm auto-config | Auto config có thể được xử lý sai thứ tự | Dùng AutoConfiguration.imports và AutoConfigurations.of |
| Dùng `@DirtiesContext` sau mỗi runner test | Chậm, không giải quyết điều kiện gốc | Runner tạo/đóng context mỗi lần |
| Giữ context bean bên ngoài callback và dùng sau close | Lifecycle/resource đã đóng | Assert trong `run(context ->...)` |
| Test web-only config bằng non-web runner | `@ConditionalOnWebApplication` không match | WebApplicationContextRunner/Reactive runner |
| Không xem startup failure khi context fail | Test lỗi mơ hồ | `assertThat(context).getFailure()`, ConditionEvaluationReport |
| Tưởng auto config luôn thắng app config | User bean có thể bị tạo thêm/ghi đè | Back-off đúng semantics là **app wins** |

## 12. Câu hỏi tự kiểm

**Câu 1:** Auto config dùng `@ConditionalOnMissingBean(GreetingFormatter.class)`. Ứng dụng khai báo `@Bean GreetingFormatter customFormatter()`. Bean mặc định `greetingFormatter` có nên xuất hiện không?

**Đáp án:** Không. Condition nhắm **type**, không phụ thuộc bean name; phải có đúng custom formatter nếu không có bean khác cùng kiểu.

**Câu 2:** Ứng dụng tự tạo `GreetingFormatter`, nhưng không tạo `GreetingService`. Có nên tạo default service không?

**Đáp án:** Có, nếu condition của service match; default service phải inject custom formatter. Đây là **partial override** đúng chuẩn.

**Câu 3:** `withUserConfiguration` có tự bật bean definition overriding không?

**Đáp án:** Không. Nó đăng ký cấu hình do người dùng cung cấp; auto configuration điều kiện back-off ngăn tạo definition xung đột. Ghi đè cùng tên là cơ chế khác.

**Câu 4:** Hai user beans cùng type, không có `@Primary`. Auto formatter đã back off nhưng startup fail. Có chứng minh back-off sai không?

**Đáp án:** Không. Back-off đã nhường. Lỗi còn lại là **dependency injection ambiguity** khi default service cần một formatter duy nhất.

**Câu 5:** `demo.greeting.enabled=false` nhưng ứng dụng có `@Bean GreetingFormatter customFormatter()`. Bean custom có bị xóa không?

**Đáp án:** Không. Feature flag đang đặt ở **auto-config class**, không phải user config.

**Câu 6:** Đổi `@Bean GreetingFormatter customFormatter()` thành `@Bean Object customFormatter()` có an toàn cho condition detection không?

**Đáp án:** Không chắc. Spring Boot dựa vào bean definitions/type metadata; return type quá rộng khiến điều kiện thiếu thông tin. Khai báo kiểu phù hợp.

**Câu 7:** Vì sao cần test tên/identity bên cạnh value?

**Đáp án:** Cùng một output có thể đến từ default hoặc user bean. Assert identity/name chứng minh user implementation thực sự được dùng, không phải chỉ tình cờ cùng kết quả.

## 13. Checklist QA cho starter auto-configuration

- [ ] Tôi xác định chính xác interface/type mà ứng dụng được quyền cung cấp.
- [ ] Auto-configuration dùng `@AutoConfiguration` và được đăng ký bằng file `AutoConfiguration.imports` trong library jar.
- [ ] `@ConditionalOnMissingBean` nhắm đúng type/name/annotation, không nhầm name với type.
- [ ] Bean conditions đặt ở nơi có thứ tự xử lý hợp lý sau user bean definitions.
- [ ] `@Bean` methods khai return type đủ rõ để condition detect chính xác.
- [ ] Runner base có `withConfiguration(AutoConfigurations.of(...))`.
- [ ] User override được đưa qua **`withUserConfiguration`** hoặc `withBean` theo mục tiêu.
- [ ] Test mặc định: không user bean → tạo đúng defaults.
- [ ] Test override một phần: custom formatter → auto service vẫn tạo và dùng custom formatter.
- [ ] Test override service riêng: default formatter vẫn có, service default nhường.
- [ ] Test cả hai user beans: không có defaults trùng kiểu.
- [ ] Test feature flag/property ở cả default-only và custom-bean mode.
- [ ] Test user bean không liên quan không chặn auto bean.
- [ ] Test type vs name: custom bean khác tên vẫn làm default back off.
- [ ] Không dùng bean-definition overriding hay `@Primary` để che duplicated default.
- [ ] Có negative test nhiều user candidates nếu service cần injection duy nhất.
- [ ] Assert **count, name, identity và behavior**, không chỉ context starts.
- [ ] Runner customizations không mutate base và contexts được đóng sau run.
- [ ] Khi context fail, kiểm `getFailure()`/root cause, không đoán từ console.
- [ ] Xem `ConditionEvaluationReport` nếu điều kiện match/unmatch ngoài dự kiến.
- [ ] Với web-only config, dùng đúng web runner; native image cần kiểm theo luồng riêng.
- [ ] Chạy `mvn test` trên JDK 17+ và kiểm test thực trong consumer app nếu phát hành starter.

**Kết luận:** `withUserConfiguration` là cách mô phỏng chính xác **bean do ứng dụng cung cấp** trong một test auto-configuration. Khi starter tuân thủ `@ConditionalOnMissingBean`, cấu hình của ứng dụng sẽ **được ưu tiên**, còn default bean **không được đăng ký**. Test tốt phải chứng minh cả **back-off đúng**, **injection đúng implementation**, **property conditions** và **failure khi user config ambiguous**; đừng nhầm back-off với ghi đè bean cùng tên.

### Tài liệu chính thức

- [Spring Boot 3.5 — Creating Your Own Auto-configuration; Testing Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.5 — ApplicationContextRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.5 — AbstractApplicationContextRunner và withUserConfiguration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html)
- [Spring Boot 3.5 — ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.5 — ApplicationContextAssert Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/assertj/ApplicationContextAssert.html)
