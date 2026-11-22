# @ConditionalOnClass, @ConditionalOnProperty và @ConditionalOnMissingBean

## 1. Mục tiêu của bài: chứng minh auto-configuration bật/tắt đúng điều kiện

Trong module **Spring Boot - testing**, nhóm **Kiểm thử auto-configuration**, việc một bean có mặt trong `ApplicationContext` không đơn giản chỉ vì ứng dụng có một class gắn `@Configuration`. Spring Boot thường đăng ký bean mặc định **có điều kiện** theo classpath, configuration properties và các bean mà người dùng đã khai báo.

Ba annotation cần làm chủ:

- **`@ConditionalOnClass`**: chỉ khớp khi một hoặc nhiều class được yêu cầu **tồn tại trên runtime classpath**.
- **`@ConditionalOnProperty`**: chỉ khớp khi giá trị property trong `Environment` đáp ứng quy tắc; `havingValue` và `matchIfMissing` quyết định trường hợp đặc biệt.
- **`@ConditionalOnMissingBean`**: chỉ khớp khi chưa có bean thỏa tiêu chí (thường theo type) trong các bean definitions đã được xử lý; mục đích phổ biến là **nhường chỗ cho cấu hình người dùng**.

Một auto-configuration thực tế thường muốn:

~~~text
optional library class có mặt?
        |
       không ------> không tạo bean mặc định
        |
        có
        |
feature property cho phép?
        |
       không ------> không tạo bean mặc định
        |
        có
        |
user đã khai báo bean cùng type?
        |
        có --------> dùng bean của user; default back off
        |
       không
        |
        v
tạo default bean
~~~

Không được coi test chỉ kiểm “context start được” là đã đủ. Cần kiểm tra cả **matched** và **not matched** cho mỗi điều kiện, các trường hợp nhiều điều kiện giao nhau, user override, classpath thiếu và nguyên nhân trong **ConditionEvaluationReport**.

Bài sử dụng **Java 17, Spring Boot 3.5.16, JUnit Jupiter, AssertJ, ApplicationContextRunner và FilteredClassLoader**, có project runnable với resource `AutoConfiguration.imports`, kiểm thử bảng chân trị property, sự vắng mặt của optional library, back-off bằng bean tùy biến, và một `@SpringBootTest` smoke test xác nhận cơ chế auto-discovery thực tế.

## 2. Auto-configuration không phải component scanning

`@AutoConfiguration` là loại Spring `@Configuration` chuyên cho cấu hình mặc định có thể áp dụng khi thư viện/starter được đưa vào ứng dụng. Đối với Spring Boot 3.5, các auto-configuration candidates được liệt kê trong resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng trong resource này là tên class đầy đủ, ví dụ:

~~~text
com.example.formatter.autoconfigure.FormatterAutoConfiguration
~~~

Trong ứng dụng gắn `@SpringBootApplication`, `@EnableAutoConfiguration` được kích hoạt ngầm và Boot đọc candidate list. Không cần và **không nên** `@ComponentScan` package chứa auto-configuration như một component bình thường, vì cách đó phá ý nghĩa load/order/condition của auto-configuration.

### Ba loại cấu hình cần phân biệt

| Loại | Nơi khai báo | Mục đích |
| --- | --- | --- |
| User `@Configuration` + `@Bean` | Ứng dụng sử dụng starter | Lựa chọn chủ động của ứng dụng |
| `@AutoConfiguration` | Thư viện/starter, được liệt kê trong `AutoConfiguration.imports` | Cung cấp default nếu điều kiện thỏa |
| Test `@TestConfiguration` | Test source set | Tạo bean/cấu hình phụ trợ cho một ca test |
| `ApplicationContextRunner` configuration | Trong JUnit, dùng `AutoConfigurations.of(...)` và `withUserConfiguration(...)` | Tạo context tối giản cho ma trận điều kiện |

Auto-configuration **không có quyền ưu tiên vượt user configuration**; về nguyên tắc user có thể khai báo implementation khác, và `@ConditionalOnMissingBean` cho default bean **back off** khi nhìn thấy user bean phù hợp.

**Lưu ý thứ tự:** điều kiện bean được đánh giá dựa trên các bean definitions đã được **xử lý tới thời điểm đó**, không phải quét toàn bộ những gì *sẽ* được đăng ký trong tương lai. Auto-configuration được xử lý sau user-defined configurations trong đường đi chuẩn; nếu cần bean từ auto-configuration khác, cân nhắc `@AutoConfiguration(after=...)`/`@AutoConfigureAfter` và kiểm thử thứ tự bằng runner.

## 3. @ConditionalOnClass: điều kiện là sự tồn tại của class, không phải bean

Một lớp thư viện có thể nằm trên runtime classpath nhưng **không có bean** nào thuộc loại đó trong Spring. Đây vẫn là một `@ConditionalOnClass` match. Ngược lại, bean factory có thể tạo bean theo cách khác nhưng class tùy chọn mà condition yêu cầu không thể load: condition **không match**.

~~~java
@ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
@Configuration(proxyBeanMethods = false)
class OptionalClientConfiguration {
    // Những bean phụ thuộc library tùy chọn nằm ở đây.
}
~~~

Đoạn trên chỉ là skeleton: không bao gồm vendor library, bean method hoặc package/imports. Dùng `name` khi muốn biểu diễn tên class bằng chuỗi và tránh tham chiếu compile-time. Với annotation trực tiếp lên một `@Configuration` class, Boot có thể đọc `value = OptionalClient.class` an toàn nhờ **ASM metadata** mà chưa nạp class tùy chọn.

### Bẫy quan trọng: đặt condition trên @Bean method trả về optional type

~~~java
// PHẢN VÍ DỤ: JVM có thể resolve return type trước
// khi method-level condition bảo vệ được nó.
@Bean
@ConditionalOnClass(OptionalClient.class)
OptionalClient optionalClient() {
    return new OptionalClient();
}
~~~

Đây là method không độc lập, và `OptionalClient` chỉ là class placeholder để giải thích. Nếu optional dependency **không tồn tại**, JVM có thể xử lý method return type / signatures trước lúc Spring đánh giá condition, dẫn tới `NoClassDefFoundError` hoặc lỗi metadata/reflection.

**Cách đúng:** tách một `static @Configuration` class riêng, đặt `@ConditionalOnClass` ở **class level**, rồi đặt các `@Bean` phụ thuộc optional type bên trong:

~~~java
@AutoConfiguration
public class MyAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.optional.OptionalClient")
    static class OptionalClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        OptionalClient optionalClient() {
            return new OptionalClient();
        }
    }
}
~~~

Đây là mẫu cú pháp mang tính nguyên lý; chưa có `OptionalClient` và imports nên **không phải tệp runnable** của demo. Trong demo bên dưới, `OptionalCodec` được tạo như lớp mô phỏng thư viện tùy chọn để `FilteredClassLoader` loại class khỏi test classpath có kiểm soát.

### value và name

- `@ConditionalOnClass(OptionalCodec.class)` phù hợp khi class có trên **compile classpath**, và annotation đặt **trực tiếp lên @Configuration class**.
- `@ConditionalOnClass(name="com.example.optionalcodec.OptionalCodec")` phù hợp khi chỉ có string class name.
- Khi tạo **composed meta-annotation** tự chứa `@ConditionalOnClass`, tài liệu Boot khuyến nghị dùng `name`; cơ chế an toàn của class literal không tương đương ở meta-annotation.
- Nếu yêu cầu **nhiều classes** trong annotation, tất cả các class liệt kê đều phải tồn tại.
- `@ConditionalOnClass` không kiểm tra method behavior hoặc bean state, cũng không bảo đảm một optional client kết nối được tới server bên ngoài.

## 4. @ConditionalOnProperty: điều kiện theo Environment

Ví dụ:

~~~java
@ConditionalOnProperty(
        prefix = "training.formatter",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
~~~

Full property key là `training.formatter.enabled`. Quy tắc trên:

- Property **không tồn tại** → **match** vì `matchIfMissing=true`.
- `enabled=true` → match (so sánh chuỗi theo semantics của Boot).
- `enabled=false` → không match.
- `enabled=no`, `enabled=maybe`, chuỗi rỗng → không match với `havingValue="true"`.

**`matchIfMissing` chỉ xử lý trường hợp không có property**, không xử lý giá trị rỗng, `null` đến từ một cấu hình bất thường, hoặc value không hợp lệ bằng cách tự coi là missing.

### Bảng chân trị chính thức

Giả sử property **có mặt** trong Environment:

| Giá trị property | `havingValue=""` (mặc định) | `havingValue="true"` | `havingValue="false"` | `havingValue="foo"` |
| --- | --- | --- | --- | --- |
| `"true"` | Match | Match | Không | Không |
| `"false"` | **Không match** | Không | Match | Không |
| `"foo"` | Match | Không | Không | Match |
| `"no"` | Match | Không | Không | Không |

Nếu property **không có**, kết quả do `matchIfMissing`: mặc định `false` nên **không match**, trừ khi bật `matchIfMissing=true`. Khi không đặt `havingValue`, điều kiện **không có nghĩa bắt buộc property boolean true**: hầu hết các chuỗi khác `"false"` đều match. Đây là điểm nhiều test cần bắt lỗi.

Trong Spring Boot 3.5 còn có `@ConditionalOnBooleanProperty` với semantics boolean cụ thể; không thay thế tùy tiện mà không kiểm tra version và tính tương thích. Bài tập này tập trung `@ConditionalOnProperty` để thấy rõ quy tắc.

### prefix, name, value, nhiều key và cấu hình lạ

- `prefix="training.formatter"` và `name="enabled"` ghép thành key hoàn chỉnh.
- Dùng notation lower-case/kebab-case khi khai báo tên keys; tránh mơ hồ trong tài liệu.
- `value` là alias của `name`; không truyền cả hai với giá trị mâu thuẫn.
- Nếu `name={"enabled","ready"}` thì **tất cả** keys phải pass.
- `@ConditionalOnProperty` đọc `Environment` chứ không gọi setter trên `@ConfigurationProperties` object.
- Nó **không phù hợp để kiểm tra collections** như `items[0]` khi property `items` không được xác định trực tiếp; dùng custom `Condition` khi cần.
- Property đến từ CLI, environment variables, profiles hoặc test runner; **ưu tiên precedence** của nguồn cấu hình nếu có nhiều nguồn cho một key.

Dùng `havingValue="true"` cho feature flag rõ ràng để tránh bật tính năng khi property có giá trị `"maybe"` do typo.

## 5. @ConditionalOnMissingBean: default nhường chỗ cho bean của user

Một auto-configuration phổ biến:

~~~java
@Bean
@ConditionalOnMissingBean(TextFormatter.class)
TextFormatter textFormatter() {
    return new DefaultTextFormatter();
}
~~~

Đây là method minh họa, `DefaultTextFormatter` không thuộc demo runnable. Nếu trong context đã có một `TextFormatter` do user tạo, method này **không đăng ký default**. Nếu chưa có, method có thể tạo default (vẫn tùy các điều kiện class/property ở mức lớp cấu hình).

### Theo type hay theo name?

- `@ConditionalOnMissingBean(TextFormatter.class)` kiểm tra **type**; user bean tên `customFormatter` vẫn làm default back off.
- `@ConditionalOnMissingBean(name="textFormatter")` kiểm tra **bean name**, có semantics khác: bean khác type trùng name có thể ngăn default; bean cùng type khác name có thể không ngăn.
- Nếu đặt annotation trên `@Bean` method **mà không có value/type/name/annotation**, Boot mặc định dùng **return type của method** làm bean type để kiểm tra.
- `search` cho phép điều chỉnh xem có xét parent application contexts không.
- `ignored`/`ignoredType` và `parameterizedContainer` là các thuộc tính nâng cao, chỉ dùng khi thật sự có nhu cầu.
- Những bean definitions **không phải autowire candidates/default candidates** có thể được bỏ qua theo semantics của Boot 3.5.

### Vì sao @Primary chưa đủ?

`@Primary` giúp chọn một bean khi có nhiều candidates để autowire. Nó **không ngăn default bean được tạo**, không giải quyết mọi injection by name, getBeansOfType, lifecycle side effects và conflict không phù hợp. Nếu mục tiêu của starter là **không tạo default khi user đã thay**, `@ConditionalOnMissingBean` có ý nghĩa khác `@Primary`.

### Thời điểm đánh giá quan trọng hơn thứ tự gọi method

`@ConditionalOnMissingBean` xét definitions đã đăng ký trước đó, không đợi bean instance được `new`. Một bean `@Lazy` đã có definition vẫn có thể chặn auto default. Đừng kiểm tra thứ tự bằng cách gọi `getBean` trong constructor side effect; dùng `ApplicationContextRunner.withUserConfiguration` để thử cả trường hợp user bean tồn tại.

Nếu các auto-configurations khác cũng đăng ký cùng type, cần `after`/`before` được thiết kế rõ. Điều kiện bean phải được đặt ở nơi thực sự là **auto-configuration**, vì user-defined `@Configuration` thông thường không có bảo đảm registration order tương tự.

## 6. Ba điều kiện ghép nhau theo logic AND

Mẫu chính của bài:

~~~java
@AutoConfiguration
class FormatterAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(OptionalCodec.class)
    @ConditionalOnProperty(
        prefix = "training.formatter",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
    )
    static class EnabledFormatterConfiguration {

        @Bean
        @ConditionalOnMissingBean(TextFormatter.class)
        TextFormatter textFormatter() {
            OptionalCodec codec = new OptionalCodec();
            return codec::format;
        }
    }
}
~~~

Đây là **skeleton rút gọn** trước mẫu runnable chi tiết phía dưới (thiếu package/imports). Điều kiện trên cùng phạm vi có quan hệ **AND**: optional class phải có, feature phải bật/missing theo policy, và chưa có `TextFormatter` cùng type mới tạo default bean.

Một user-defined bean `TextFormatter` có thể vẫn tồn tại **kể cả khi flag tắt hoặc optional class không có**, bởi điều kiện chỉ chi phối **auto default**, không tự xóa beans do user khai báo.

### Ma trận hành vi kỳ vọng

| Class `OptionalCodec` | Property | User `TextFormatter` | Kết quả trong context |
| --- | --- | --- | --- |
| Có | Thiếu | Không | Default `TextFormatter` |
| Có | `true` | Không | Default |
| Có | `false` | Không | Không có `TextFormatter` |
| Có | `foo` | Không | Không có default |
| Có | Thiếu | Có | **User bean**, không có default |
| Có | `false` | Có | User bean vẫn có |
| Không | Thiếu | Không | Không có default |
| Không | Thiếu | Có | User bean vẫn có |
| Không | `true` | Không | Không có default |

Đây là ma trận kiểm thử đáng tin hơn một `@SpringBootTest` duy nhất: nó tách từng nhánh và kết hợp, giúp pinpoint lỗi khi thay đổi code auto-config.

## 7. Vì sao ApplicationContextRunner phù hợp hơn @SpringBootTest cho ma trận điều kiện?

Spring Boot hỗ trợ `ApplicationContextRunner` trong `spring-boot-test`. Mỗi `run(...)` tạo một context **riêng cho scenario**, cho phép cấu hình:

~~~java
private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                    AutoConfigurations.of(FormatterAutoConfiguration.class)
                );
~~~

- `withConfiguration(AutoConfigurations.of(...))` đưa đúng auto-config under test vào runner, không cần khởi động cả ứng dụng.
- `withPropertyValues("training.formatter.enabled=false")` tạo kịch bản feature flag riêng.
- `withUserConfiguration(UserFormatterConfiguration.class)` đăng ký một user bean **trước** auto config, để test back-off.
- `withClassLoader(new FilteredClassLoader(OptionalCodec.class))` giả lập **class không có trên runtime classpath**.
- `run(context -> {...})` nhận một `AssertableApplicationContext`, dùng AssertJ để kiểm bean count/type/value; context được runner đóng sau callback.
- `withInitializer(ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))` hữu ích khi debug condition reasons.

**Không cần @SpringBootTest trên mỗi method.** Nếu test chỉ muốn kiểm bean definitions và properties, context tối giản chạy nhanh, dễ cô lập và ít bị các auto-configurations không liên quan ảnh hưởng.

`ApplicationContextRunner` **không hỗ trợ test native image runtime** theo Spring Boot documentation; Native/AOT smoke tests cần một phương pháp tương thích với native runtime. Nếu cần điều kiện servlet/reactive context, dùng `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` tương ứng.

### Test runner vẫn cần một smoke test autoload

Runner đặt auto config bằng tay qua `AutoConfigurations.of` nên nó không chứng minh rằng jar đã khai báo **đúng `AutoConfiguration.imports` resource**. Ta sẽ bổ sung `@SpringBootTest` với ứng dụng nằm ở package khác để xác minh Spring Boot thực sự tự nạp candidate từ resource.

## 8. Cấu trúc dự án Java 17 + Spring Boot 3.5.16

Ví dụ chạy được bằng Gradle Wrapper:

~~~text
settings.gradle
build.gradle

src/main/java/com/example/app/
    FormatterDemoApplication.java

src/main/java/com/example/formatter/api/
    TextFormatter.java

src/main/java/com/example/optionalcodec/
    OptionalCodec.java

src/main/java/com/example/formatter/autoconfigure/
    FormatterAutoConfiguration.java

src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports

src/test/java/com/example/formatter/autoconfigure/
    FormatterAutoConfigurationTests.java

src/test/java/com/example/app/
    FormatterApplicationSmokeTests.java
~~~

Các package được tách có chủ đích: `com.example.app` là vùng component scan của ứng dụng demo, còn auto-configuration ở `com.example.formatter.autoconfigure` được Spring Boot phát hiện qua `AutoConfiguration.imports`, **không phải do quét component**.

`OptionalCodec` hiện là một class được biên dịch **trong cùng project** để demo có thể chạy không cần thêm Maven module. Trong starter thật, nó sẽ nằm ở một **optional dependency** của thư viện bên ngoài; `FilteredClassLoader` mô phỏng dependency bị loại khỏi runtime classpath.

### settings.gradle

~~~groovy
rootProject.name = 'conditional-auto-configuration-demo'
~~~

### build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-test` cung cấp `ApplicationContextRunner`, `FilteredClassLoader`, JUnit Jupiter và AssertJ. Không cần HTTP server, database, Docker, Redis hoặc Kafka cho bài kiểm thử bean conditions. `Spring Boot 3.5.16` được pin để tránh nhầm imports/cơ chế với Boot 4.x khi học.

**Lưu ý:** Việc build có thể đòi repository/network để lấy dependencies và Gradle Wrapper đã được thiết lập. Mã được kiểm tra API và logic, nhưng kết quả test thực tế chỉ được khẳng định sau khi chạy suite.

## 9. Ứng dụng demo: component scan không chạm auto-config

**`src/main/java/com/example/app/FormatterDemoApplication.java`:**

~~~java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormatterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormatterDemoApplication.class, args);
    }
}
~~~

`@SpringBootApplication` ở package `com.example.app`; mặc định component scan chỉ nhìn package này và các subpackages. Class `com.example.formatter.autoconfigure.FormatterAutoConfiguration` ở package **anh em** không bị scan.

Nếu quên file `AutoConfiguration.imports`, ứng dụng `FormatterDemoApplication` sẽ **không có formatter bean mặc định**, và smoke test ở cuối bài FAIL; trong khi runner tests trực tiếp chỉ định auto config vẫn có thể PASS. Đây là lý do cần cả hai lớp kiểm thử.

## 10. Interface công khai và optional class

**`src/main/java/com/example/formatter/api/TextFormatter.java`:**

~~~java
package com.example.formatter.api;

@FunctionalInterface
public interface TextFormatter {
    String format(String input);
}
~~~

**`src/main/java/com/example/optionalcodec/OptionalCodec.java`:**

~~~java
package com.example.optionalcodec;

import java.util.Locale;
import java.util.Objects;

public final class OptionalCodec {

    public String format(String input) {
        Objects.requireNonNull(input, "input");
        return "CODEC:" + input.strip().toUpperCase(Locale.ROOT);
    }
}
~~~

`OptionalCodec` là **class mô phỏng một API thư viện bên ngoài**. Nó không phải Spring bean; sự tồn tại của class trên classpath **đủ** cho `@ConditionalOnClass` match. Cùng lúc, việc tạo bean `TextFormatter` còn tùy property và user bean khác.

Method `format` được cố ý thiết kế có output cụ thể, ví dụ:

~~~text
new OptionalCodec().format(" hello ") -> "CODEC:HELLO"
new OptionalCodec().format("  mixed case  ") -> "CODEC:MIXED CASE"
~~~

Đây là output suy ra từ source code, **không phải stdout đã chạy**. Không gọi `System.out.println` trong production code.

Dùng `Locale.ROOT` cho normalization thuộc kỹ thuật để kết quả không đổi theo `Locale.getDefault()` của CI; test auto-configuration tập trung vào điều kiện beans chứ không bị nhiễu từ locale.

## 11. Auto-configuration đầy đủ và ba điều kiện

**`src/main/java/com/example/formatter/autoconfigure/FormatterAutoConfiguration.java`:**

~~~java
package com.example.formatter.autoconfigure;

import com.example.formatter.api.TextFormatter;
import com.example.optionalcodec.OptionalCodec;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class FormatterAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(OptionalCodec.class)
    @ConditionalOnProperty(
            prefix = "training.formatter",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    static class OptionalCodecFormatterConfiguration {

        @Bean
        @ConditionalOnMissingBean(TextFormatter.class)
        TextFormatter textFormatter() {
            OptionalCodec codec = new OptionalCodec();
            return codec::format;
        }
    }
}
~~~

**Từng tầng hoạt động:**

1. `@AutoConfiguration` là candidate được Boot import theo metadata file.
2. `@Configuration(proxyBeanMethods=false)` là nested configuration tách vùng phụ thuộc `OptionalCodec`.
3. `@ConditionalOnClass(OptionalCodec.class)` bảo vệ **cả nested configuration** trước khi parser xử lý `@Bean` method bên trong.
4. `@ConditionalOnProperty(...havingValue="true",matchIfMissing=true)` bật default feature khi property là true **hoặc không khai báo**, chặn false/invalid.
5. `@ConditionalOnMissingBean(TextFormatter.class)` nhường chỗ cho user-defined bean cùng interface.
6. Trả về `TextFormatter` qua method `@Bean` giúp injection theo interface; class `OptionalCodec` chỉ được `new` khi cấu hình thực sự match.

**Không** để method trả về trực tiếp optional type trong một top-level configuration không được bảo vệ. Không đặt condition trên component scan bean rồi giả định auto-config ordering như Spring Boot candidate process.

### Nếu muốn mặc định tắt

Đổi `matchIfMissing=false` trong code auto-config và thay các test default. Đây là **thay đổi product contract**: property thiếu sẽ không tạo bean. Không sửa annotation mà vẫn giữ test `missingPropertyUsesDefault...` mong PASS.

## 12. Đăng ký candidate qua AutoConfiguration.imports

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:**

~~~text
com.example.formatter.autoconfigure.FormatterAutoConfiguration
~~~

File này:

- Có đúng đường dẫn và tên resource chuẩn cho Spring Boot 3.5.
- Mỗi dòng chứa **fully-qualified class name**, không phải tên bean.
- Không cần và không sử dụng file cũ `spring.factories` để đăng ký auto-config trong Boot 3.5.
- Có thể chứa comment bắt đầu bằng `#`, nhưng tránh typo/class được move mà quên sửa.
- Nên nằm trong **jar xuất bản** của starter/auto-config module, không chỉ nằm trong test resources.
- Không được thay bằng `@ComponentScan` hoặc `@Import` thông thường rồi kết luận cơ chế auto-discovery đã được test.

Runner tests dưới đây đưa auto-config vào context tường minh, nhưng smoke test `@SpringBootTest` cần file này để tự tìm thấy bean mặc định.

Nếu bạn phát hành một starter riêng, thông thường tách phần `autoconfigure` và phần `starter` dependency convenience, đánh dấu optional dependency hợp lý để client applications không bắt buộc kéo mọi thư viện tùy chọn.

## 13. ApplicationContextRunner tests — mã hoàn chỉnh

**`src/test/java/com/example/formatter/autoconfigure/FormatterAutoConfigurationTests.java`:**

~~~java
package com.example.formatter.autoconfigure;

import com.example.formatter.api.TextFormatter;
import com.example.optionalcodec.OptionalCodec;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class FormatterAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    FormatterAutoConfiguration.class
                            )
                    );

    @Test
    void missingPropertyUsesDefaultBecauseMatchIfMissingIsTrue() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(TextFormatter.class);
            assertThat(context.getBean(TextFormatter.class)
                    .format(" hello ")).isEqualTo("CODEC:HELLO");
        });
    }

    @Test
    void explicitTrueCreatesDefaultBean() {
        runner.withPropertyValues(
                "training.formatter.enabled=true"
        ).run(context -> {
            assertThat(context).hasSingleBean(TextFormatter.class);
            assertThat(context.getBean(TextFormatter.class)
                    .format("demo")).isEqualTo("CODEC:DEMO");
        });
    }

    @Test
    void trueValueMatchIsCaseInsensitive() {
        runner.withPropertyValues(
                "training.formatter.enabled=TRUE"
        ).run(context -> {
            assertThat(context).hasSingleBean(TextFormatter.class);
        });
    }

    @Test
    void falseFlagRemovesOnlyTheAutoDefaultBean() {
        runner.withPropertyValues(
                "training.formatter.enabled=false"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(TextFormatter.class);
        });
    }

    @Test
    void invalidValueDoesNotAccidentallyEnableFeature() {
        runner.withPropertyValues(
                "training.formatter.enabled=maybe"
        ).run(context -> {
            assertThat(context).doesNotHaveBean(TextFormatter.class);
        });
    }

    @Test
    void presentButEmptyValueIsNotTheSameAsMissingProperty() {
        runner.withPropertyValues(
                "training.formatter.enabled="
        ).run(context -> {
            assertThat(context).doesNotHaveBean(TextFormatter.class);
        });
    }

    @Test
    void userProvidedFormatterMakesAutoDefaultBackOff() {
        runner.withUserConfiguration(UserFormatterConfig.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(TextFormatter.class);

                    TextFormatter formatter =
                            context.getBean(TextFormatter.class);
                    assertThat(formatter.format("abc"))
                            .isEqualTo("USER:abc");

                    assertThat(context)
                            .doesNotHaveBean("textFormatter");
                    assertThat(context.getBean("customFormatter"))
                            .isSameAs(formatter);
                });
    }

    @Test
    void userBeanStillExistsEvenWhenAutoFlagIsFalse() {
        runner.withUserConfiguration(UserFormatterConfig.class)
                .withPropertyValues(
                        "training.formatter.enabled=false"
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(TextFormatter.class);
                    assertThat(context.getBean(TextFormatter.class)
                            .format("abc")).isEqualTo("USER:abc");
                });
    }

    @Test
    void unrelatedBeanDoesNotCauseFormatterToBackOff() {
        runner.withUserConfiguration(UnrelatedConfig.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(TextFormatter.class);
                    assertThat(context).hasSingleBean(OtherService.class);
                    assertThat(context.getBean(TextFormatter.class)
                            .format(" hi ")).isEqualTo("CODEC:HI");
                });
    }

    @Test
    void missingOptionalClassMeansNoAutoFormatter() {
        runner.withClassLoader(
                new FilteredClassLoader(OptionalCodec.class)
        ).run(context -> {
            assertThat(context).doesNotHaveBean(TextFormatter.class);
            assertThat(context).doesNotHaveBean("textFormatter");
        });
    }

    @Test
    void userFormatterDoesNotDependOnOptionalCodec() {
        runner.withUserConfiguration(UserFormatterConfig.class)
                .withClassLoader(
                        new FilteredClassLoader(OptionalCodec.class)
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(TextFormatter.class);
                    assertThat(context.getBean(TextFormatter.class)
                            .format("abc")).isEqualTo("USER:abc");
                });
    }

    @Test
    void absentPropertyDoesNotMatchWhenMatchIfMissingIsDefault() {
        new ApplicationContextRunner()
                .withUserConfiguration(StrictPropertyConfig.class)
                .run(context -> {
                    assertThat(context.containsBean("strictSignal"))
                            .isFalse();
                });
    }

    @Test
    void defaultHavingValueMatchesNonFalseStrings() {
        new ApplicationContextRunner()
                .withUserConfiguration(StrictPropertyConfig.class)
                .withPropertyValues("training.strict.enabled=yes")
                .run(context -> {
                    assertThat(context.containsBean("strictSignal"))
                            .isTrue();
                    assertThat(context.getBean("strictSignal"))
                            .isEqualTo("STRICT");
                });
    }

    @Test
    void defaultHavingValueRejectsStringFalse() {
        new ApplicationContextRunner()
                .withUserConfiguration(StrictPropertyConfig.class)
                .withPropertyValues("training.strict.enabled=false")
                .run(context -> {
                    assertThat(context.containsBean("strictSignal"))
                            .isFalse();
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFormatterConfig {
        @Bean("customFormatter")
        TextFormatter myFormatter() {
            return value -> "USER:" + value.strip();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UnrelatedConfig {
        @Bean
        OtherService otherService() {
            return new OtherService();
        }
    }

    static class OtherService {
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "training.strict",
            name = "enabled"
    )
    static class StrictPropertyConfig {
        @Bean
        String strictSignal() {
            return "STRICT";
        }
    }
}
~~~

**14 JUnit test methods** trong lớp runner, chia thành hai nhóm: 11 ca thử ba điều kiện của `FormatterAutoConfiguration` và 3 ca thử semantics **mặc định** của `@ConditionalOnProperty` bằng `StrictPropertyConfig`.

### Tại sao viết riêng StrictPropertyConfig?

Auto-config chính dùng `havingValue="true", matchIfMissing=true`. Nếu chỉ kiểm nó, rất dễ hiểu nhầm rằng mọi `@ConditionalOnProperty` đều mặc định “chỉ true” hoặc mặc định bật khi missing. Ba test cuối xác nhận:

- Missing key → không match (mặc định `matchIfMissing=false`).
- Present `"yes"` → match với `havingValue=""` mặc định vì không phải `false`.
- Present `"false"` → không match.

`StrictPropertyConfig` là cấu hình test nằm ở lớp test, không đăng ký thành auto-config candidate trong `AutoConfiguration.imports`. Nó chỉ được load khi runner cụ thể gọi `withUserConfiguration(StrictPropertyConfig.class)`.

### Tại sao dùng FilteredClassLoader?

Trong project demo, `OptionalCodec` luôn tồn tại trên regular test classpath. `FilteredClassLoader(OptionalCodec.class)` mô phỏng việc user **không có optional library** trong runtime của ứng dụng. Nhờ nested `@Configuration` và class-level `@ConditionalOnClass`, context không phải instantiate default bean phụ thuộc `OptionalCodec` và có thể khởi động bình thường.

Không có lý do test phải xóa dependency ra khỏi `build.gradle` rồi build lại giữa các methods; `FilteredClassLoader` mô phỏng đúng case classpath variant mà không tạo nhiều Gradle modules.

### Vì sao không dùng @MockBean để thay user bean?

`@MockitoBean`/`@MockBean` thường phục vụ injection mocks trong `@SpringBootTest`. Với auto-config test, mục tiêu là **bean definition thực được user đăng ký**, vì vậy `withUserConfiguration` và một `@Bean TextFormatter` đơn giản phản ánh back-off rõ hơn, không làm context cache chậm và không cần Mockito interaction verification.

## 14. Full Spring Boot smoke test: kiểm imports file và autoload

**`src/test/java/com/example/app/FormatterApplicationSmokeTests.java`:**

~~~java
package com.example.app;

import com.example.formatter.api.TextFormatter;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = FormatterDemoApplication.class,
        properties = "training.formatter.enabled=true"
)
class FormatterApplicationSmokeTests {

    @Autowired
    TextFormatter formatter;

    @Test
    void applicationAutoDiscoversFormatterFromImportsResource() {
        assertThat(formatter.format(" hello "))
                .isEqualTo("CODEC:HELLO");
    }
}
~~~

Khi `AutoConfiguration.imports` hợp lệ, Boot nạp `FormatterAutoConfiguration`, class `OptionalCodec` có trên classpath, flag true, chưa có user `TextFormatter` nên bean mặc định được tạo. Test autowire `TextFormatter` và kiểm tra kết quả.

Nếu bạn **chỉ chạy ApplicationContextRunner tests**, resource imports sai/thiếu có thể không được phát hiện vì runner đã chỉ định class auto-config trực tiếp. Smoke test giúp đóng khoảng trống đó.

Đây là **1 JUnit test method** nữa; tổng **15 ca JUnit** ở hai test classes, bao phủ cả **condition matrix** và **real auto-configuration discovery path**. Không có network I/O, JDBC hay Kafka trong sample.

## 15. Hướng dẫn đọc ma trận QA từ test results

| Tình huống | Test | Kỳ vọng |
| --- | --- | --- |
| Optional class có; flag thiếu; user bean không có | `missingPropertyUsesDefaultBecauseMatchIfMissingIsTrue` | 1 default bean |
| Flag true | `explicitTrueCreatesDefaultBean` | Default hoạt động |
| Flag TRUE | `trueValueMatchIsCaseInsensitive` | Match |
| Flag false | `falseFlagRemovesOnlyTheAutoDefaultBean` | Không có formatter |
| Flag maybe | `invalidValueDoesNotAccidentallyEnableFeature` | Không có formatter |
| Key có mặt nhưng value rỗng | `presentButEmptyValueIsNotTheSameAsMissingProperty` | Không có formatter |
| User bean khác tên | `userProvidedFormatterMakesAutoDefaultBackOff` | 1 user formatter, không có default |
| Flag tắt + user bean | `userBeanStillExistsEvenWhenAutoFlagIsFalse` | User bean vẫn có |
| Bean không liên quan | `unrelatedBeanDoesNotCauseFormatterToBackOff` | Default vẫn tạo |
| Lọc bỏ OptionalCodec | `missingOptionalClassMeansNoAutoFormatter` | Không có formatter |
| Lọc OptionalCodec + user bean | `userFormatterDoesNotDependOnOptionalCodec` | User bean vẫn có |
| Property thiếu với default matchIfMissing | `absentPropertyDoesNotMatchWhenMatchIfMissingIsDefault` | Không có strictSignal |
| Property yes với default havingValue | `defaultHavingValueMatchesNonFalseStrings` | strictSignal có |
| Property false với default havingValue | `defaultHavingValueRejectsStringFalse` | strictSignal không có |
| Full Spring Boot auto-discovery | `applicationAutoDiscoversFormatterFromImportsResource` | Formatter có và format đúng |

**Đây là expected behavior theo API và mã nguồn**; chưa phải kết quả Gradle/JUnit đã được chạy trên một máy cụ thể.

### Tại sao test negative cases quan trọng?

Một auto-config bug nghiêm trọng có thể làm default bean xuất hiện **khi class optional không tồn tại** hoặc khi feature đã bị tắt, gây `NoClassDefFoundError`, bean ambiguity hay kết nối ngoài ý muốn. Chỉ test positive path sẽ không phát hiện.

Đồng thời, điều kiện match **không bảo đảm bean hoạt động đúng**: nó mới kiểm được việc cấu hình. Smoke test format một chuỗi giúp nối conditional definition với service behavior tối thiểu.

## 16. ConditionEvaluationReport để tìm nguyên nhân positive/negative match

Khi bean vắng mặt, thường phải trả lời **“condition nào không match?”** thay vì đoán một property/bean đang được load.

Spring Boot có `ConditionEvaluationReport` và `ConditionEvaluationReportLoggingListener`. Với `ApplicationContextRunner`, có thể gắn initializer:

~~~java
ApplicationContextRunner debugRunner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                FormatterAutoConfiguration.class
                        )
                )
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO)
                );

debugRunner.withPropertyValues(
        "training.formatter.enabled=false"
).run(context -> {
    assertThat(context).doesNotHaveBean(TextFormatter.class);
});
~~~

Đây là snippet **minh họa nằm ngoài project runnable chính**; cần imports:

~~~java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
~~~

Nó đưa report vào logger, không nhất thiết làm report hiển thị nếu logging level hoặc test runner capture chưa cho phép. Test **không nên assert raw text logs** vì message/format có thể thay đổi theo minor versions. Có thể inspect `ConditionEvaluationReport` programmatically hoặc bật Boot debug khi cần.

Trong một Spring Boot application thực, tham số `--debug` có thể giúp in condition evaluation report ở startup; Spring Boot Actuator `conditions` endpoint cũng hữu ích nếu Actuator được thêm/bật và được bảo vệ phù hợp. Không expose internal conditions/config/secrets ra public chỉ để debug test.

### Dùng report để xác định đúng nhánh

- `OnClassCondition`: thiếu `OptionalCodec` hoặc một dependency transitive.
- `OnPropertyCondition`: key thiếu/false/maybe, hoặc property source precedence không như tưởng.
- `OnBeanCondition`: user bean `TextFormatter` đã đăng ký, nên default back off.
- Bean condition match mà context startup FAIL: có thể là exception trong `@Bean` method hoặc dependency khác, không phải condition false.

**Một negative test nên kiểm không có bean và context startup thành công**. Nếu lỗi `NoClassDefFoundError` khiến context không start, test phải FAIL chứ không được coi “không có bean” là đúng một cách ngầm định.

## 17. Thứ tự xử lý bean definitions và các auto-configurations khác

`@ConditionalOnMissingBean` là một **snapshot của definitions đã biết** tại thời điểm condition được đánh giá. Nếu auto-config A tạo `Service`, auto-config B cũng muốn tạo `Service` khi chưa có, thứ tự candidates có thể quyết định bean nào được tạo.

Có thể chỉ rõ:

~~~java
@AutoConfiguration(after = OtherAutoConfiguration.class)
public class MyAutoConfiguration {
    // @ConditionalOnMissingBean trên @Bean method.
}
~~~

Đây là skeleton, không thuộc project runnable; `OtherAutoConfiguration` phải tồn tại. Với auto-config library độc lập có thể dùng `afterName` bằng tên đầy đủ để giảm compile dependency. Thứ tự **đăng ký bean definitions** khác thứ tự **khởi tạo bean instances**; `@DependsOn` giải quyết thứ tự khởi tạo, không thay thứ tự điều kiện của auto-config classes.

### Khi user bean trả về interface quá tổng quát

Ví dụ user viết:

~~~java
@Bean
Object myFormatter() {
    return (TextFormatter) value -> value;
}
~~~

Đoạn này là phản ví dụ minh họa. Condition evaluation chỉ nhìn thấy thông tin type có sẵn tại registration time. Khi `@Bean` method trả `Object`, framework có thể không suy ra rằng nó thực chất tạo `TextFormatter`, khiến default bean vẫn được đăng ký và tạo ambiguity hoặc override bất ngờ.

**Hãy khai báo return type chính xác nhất có thể**, tối thiểu là interface `TextFormatter` hoặc concrete type thích hợp. Với `@ConditionalOnMissingBean` ở bean factory, việc type được công bố trong method signature là một phần quan trọng của contract.

## 18. @ConditionalOnClass khi optional library có bản không tương thích

`@ConditionalOnClass` chỉ kiểm sự hiện diện class theo tên; nó **không xác minh API binary compatibility hoặc method contract**. Nếu class tồn tại nhưng version không có method đang gọi, bean creation có thể fail bằng `NoSuchMethodError`. Nếu class tồn tại nhưng transitive dependency vắng mặt, có thể gặp linkage error.

Vì vậy trong starter thật cần:

1. Quản lý dependency versions tương thích bằng BOM/constraint.
2. Kiểm thử matrix classpath với **library present** và **library absent**.
3. Nếu hỗ trợ nhiều major versions, thêm integration tests cho binary compatibility.
4. Không dùng `@ConditionalOnClass` để đoán service bên ngoài đang reachable.
5. Tránh trả optional class type từ bean method trong configuration không được bảo vệ.
6. Khi cần khác biệt theo classpath, dùng `FilteredClassLoader` hoặc dependency variants trong CI, không sửa jar classpath tùy tiện trong cùng JVM runtime.

Một class có mặt nhưng bean không tồn tại là tình huống bình thường; cần phân biệt rõ `@ConditionalOnClass` với `@ConditionalOnBean`. Nếu bean phụ thuộc phải có trước, dùng bean conditions với order thích hợp, không ép class condition thay nghĩa.

## 19. @ConditionalOnProperty và Spring Profiles

Property đến từ `Environment`, có thể khác nhau theo `application.properties`, YAML, profile-specific config, environment variables, command-line args hoặc inline test properties.

Ví dụ:

~~~properties
# application.properties
training.formatter.enabled=true
~~~

Và trong test:

~~~java
runner.withPropertyValues(
        "training.formatter.enabled=false"
).run(context -> {
    assertThat(context).doesNotHaveBean(TextFormatter.class);
});
~~~

Trong `ApplicationContextRunner`, `withPropertyValues` tạo property sources cho scenario đó, không phải chỉnh system properties của cả JVM. Điều này tốt hơn `System.setProperty(...)` trong tests chạy song song.

### Relaxed binding không phải cách để viết key tùy ý

Spring Boot có quy tắc binding properties, nhưng đừng mặc định mọi biến thể dấu gạch/underscore/case đều được `@ConditionalOnProperty` hiểu giống `@ConfigurationProperties` trong mọi environment. Khai báo full key chuẩn trong annotation, dùng tên kebab-case và test đúng property sources đang sử dụng. Nếu dùng env variable, kiểm integration behavior cụ thể.

### Flag bật thiếu mặc định hay mặc định tắt?

- `matchIfMissing=true` phù hợp với một default feature đã được thiết kế **bật** khi user không cấu hình.
- `matchIfMissing=false` an toàn khi feature chỉ được bật bằng explicit opt-in, ví dụ một integration có chi phí/side effect đáng kể.
- `havingValue="true"` tránh nhận các chuỗi lạ như `maybe` là true theo default semantics.
- Khi property có nhiều giá trị enum, viết `havingValue="foo"` hay custom condition có validation rõ; không giả mọi text đều boolean.

Trong code demo đã chọn **default ON** để minh họa matchIfMissing, nhưng kiến trúc production có thể cần **default OFF** tùy tính năng.

## 20. @ConditionalOnMissingBean, @Primary và override trong Spring Boot 3.5

Một user muốn thay formatter:

~~~java
@Configuration(proxyBeanMethods = false)
class MyFormatterConfiguration {
    @Bean
    TextFormatter customFormatter() {
        return value -> "CUSTOM:" + value;
    }
}
~~~

Đây là snippet có thể được đặt trong application, cần imports và package. Trong trường hợp Spring Boot load user config trước auto-config, `@ConditionalOnMissingBean(TextFormatter.class)` không tạo formatter mặc định.

Khác nhau:

| Cơ chế | Có tạo bean default hay không? | Công dụng chính |
| --- | --- | --- |
| `@ConditionalOnMissingBean` trên auto bean | Không khi đã có candidate phù hợp | Back-off extension point |
| `@Primary` trên user bean | Default có thể vẫn tồn tại | Giải quyết autowire nhiều candidates |
| `spring.main.allow-bean-definition-overriding=true` | Cho phép ghi đè definition trùng tên trong một số tình huống | Không thay thế thiết kế back-off |
| `@ConditionalOnProperty` false | Không tạo default trong scope bị điều kiện chặn | Feature flag/conditional module |

Bật bean definition overriding để che một auto-config sai có thể làm test không nhận ra duplicate configurations, và không bảo đảm một bean khác tên nhưng cùng type được xử lý như mong muốn. Đúng hơn là sửa `@ConditionalOnMissingBean` và kiểm test user override.

### Với @MockBean/@MockitoBean trong test

Bean overrides có thể ảnh hưởng kết quả `@ConditionalOnMissingBean` và context cache key. Nếu mục tiêu bài là kiểm auto-default có back off, dùng **user `@Bean` thật** như `withUserConfiguration` rõ ràng hơn. Dùng mock khi bạn thật sự kiểm tương tác giữa components; đừng biến logic điều kiện thành một Mockito interaction test không kiểm bean definitions.

## 21. Đặt @Conditional ở class hay @Bean method?

| Vị trí | Hiệu lực | Khi nên dùng |
| --- | --- | --- |
| `@ConditionalOnClass` trên auto-config/nested `@Configuration` | Có thể loại toàn bộ cấu hình trước khi method types được xử lý | **Ưu tiên cho optional dependencies** |
| `@ConditionalOnProperty` trên `@Configuration` | Không đăng ký các beans thuộc configuration khi flag không match | Cả nhóm beans cùng feature |
| `@ConditionalOnProperty` trên một `@Bean` | Chỉ chặn bean method đó | Feature ở phạm vi một bean |
| `@ConditionalOnMissingBean` trên một `@Bean` | Chặn default cụ thể nếu bean ứng viên đã có | **Bean-specific user override** |
| `@ConditionalOnMissingBean` trên auto-config class | Chặn cả config khi condition không match | Khi mọi beans trong config phụ thuộc cùng absence |

Trong sample, class điều kiện và bean method được phối hợp có chủ đích:

~~~text
Nested configuration:
  OnClass OptionalCodec
  AND OnProperty training.formatter.enabled true/missing
      |
      v
@Bean textFormatter:
  OnMissingBean TextFormatter
      |
      v
register formatter
~~~

Đừng đặt `@ConditionalOnMissingBean(TextFormatter.class)` trên toàn auto-config nếu auto-config còn khai báo những bean khác vẫn cần thiết khi user override formatter. Mức độ đặt annotation nên theo đúng phạm vi tính năng mà bạn muốn tắt.

## 22. Vì sao ApplicationContextRunner nhanh, nhưng không đủ cho mọi test?

`ApplicationContextRunner` tập trung vào một cấu hình với một tập bean nhỏ, không khởi động toàn bộ application. Vì vậy:

- Rất phù hợp để chạy **matrix property/classpath/user beans**.
- Không nên dùng để khẳng định JPA schema, HTTP routes, Kafka broker, Redis connection hoặc Actuator endpoint production hoạt động.
- Không tự chứng minh một `AutoConfiguration.imports` resource đúng (đã có smoke test).
- Khi chạy nhiều auto-config classes tương tác, cần đưa chúng vào `AutoConfigurations.of(A.class, B.class)`, dùng ordering thực.
- Nếu auto-config chỉ dành cho web, cần `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` tương ứng.
- Khi chạy native image, ApplicationContextRunner không hỗ trợ theo docs; cần bổ sung smoke/AOT tests.

### Context được đóng sau runner callback

Một runner callback nên chỉ assert và không lưu `ApplicationContext` ra ngoài để dùng sau khi callback kết thúc. Các resource/beans thuộc context được đóng sau chạy. Đừng tạo một singleton/port random trong static field rồi chờ runner tự quản lý vòng đời ngoài context.

### Thử các context errors

Khi purposely cấu hình thiếu dependency mà context **phải fail**, có thể assert `context.getStartupFailure()` (thay vì bỏ qua exception). Nhưng với `@ConditionalOnClass` optional library vắng mặt, **kỳ vọng là context start thành công và bean mặc định vắng**, không phải test “được phép fail khi khởi động”.

## 23. Các lỗi thường gặp và hướng sửa

| Dấu hiệu | Nguyên nhân khả dĩ | Cách sửa |
| --- | --- | --- |
| Bean vẫn xuất hiện khi property `false` | Condition không nằm đúng scope hoặc key sai | Kiểm annotation/key, test negative case |
| Flag `maybe` vô tình bật | Không có `havingValue="true"` | Dùng havingValue rõ |
| Property thiếu nhưng bean vẫn được tạo | `matchIfMissing=true` chủ ý | Xác định default-on contract, đổi nếu muốn |
| Property thiếu khiến bean không tạo | Default `matchIfMissing=false` | Set true nếu default-on |
| Optional class vắng nhưng context fail linkage | Method return type phụ thuộc optional class chưa được bảo vệ | Tách nested configuration với class-level condition |
| Optional class có nhưng no bean | Class condition chỉ xét classpath, bean/property conditions khác | Xem ConditionEvaluationReport |
| User tạo bean khác tên nhưng default vẫn tạo | Điều kiện đang xét **name** thay vì type | Dùng `@ConditionalOnMissingBean(TargetType.class)` |
| User bean return type `Object` | Type metadata thiếu, default có thể đăng ký | Dùng return type chính xác |
| User bean đã khai báo nhưng default vẫn tạo | Auto-config order sai/condition đặt trong user config | Đảm bảo user config trước, auto-config ordering |
| `@Primary` user bean vẫn khiến có 2 beans | @Primary không xóa default | Thêm/fix OnMissingBean |
| Runner test PASS, ứng dụng thật không có bean | Thiếu `AutoConfiguration.imports` | Kiểm resource path và `@SpringBootTest` smoke |
| Auto-config bị quét qua component scanning | Đặt chung dưới root scan | Tách package, dùng imports |
| FilteredClassLoader không loại đúng class | Lọc sai package/type/loader | Chỉ định chính xác optional type |
| Context crash vì thiếu transitive library | Class có nhưng method/supertype không load được | Kiểm dependency graph/binary compatibility |
| Test fail khi đổi profile | Property precedence thay đổi | Set scenario property rõ và test theo profile |
| Condition report có negative match nhưng test không hiểu | Đọc sai điều kiện cùng scope | Xem OnClass/OnProperty/OnBean outcomes |
| `@ConditionalOnProperty` trên list | Indexed collection không match như mong đợi | Dùng custom Condition hoặc metadata logic riêng |
| Có bean mock nên default back off bất ngờ | Test overrides được tính vào bean definitions | Dùng real @Bean config cho condition test |
| Spring Boot 4 test imports không khớp | Package/versions khác 3.5 | Pin target version, migrate có kiểm chứng |

Không tăng `@SpringBootTest` scope chỉ để tránh hiểu điều kiện. Một runner test nhỏ với class/property/user config rõ ràng thường cho diagnostic tốt hơn.

## 24. Checklist QA trước khi phát hành starter/auto-configuration

- [ ] `@AutoConfiguration` có tên class chính xác trong `META-INF/spring/...AutoConfiguration.imports`?
- [ ] Auto-config không bị đăng ký ngoài ý muốn qua `@ComponentScan`?
- [ ] Optional class condition dùng class-level `@Configuration` isolation khi bean method phụ thuộc library?
- [ ] Đã test class present và class absent bằng `FilteredClassLoader`?
- [ ] Đã test flag missing, true, false, invalid và empty?
- [ ] `havingValue`, `matchIfMissing` phản ánh đúng default-on/default-off contract?
- [ ] Có hiểu `havingValue=""` mặc định khác `havingValue="true"`?
- [ ] Không dùng `@ConditionalOnProperty` như condition đáng tin cho indexed lists?
- [ ] Có test user bean **khác tên nhưng cùng type** khiến default back off?
- [ ] Có test user bean vẫn tồn tại khi auto flag off/class optional absent?
- [ ] Có test unrelated bean không ảnh hưởng default?
- [ ] `@Bean` method công bố return type đủ chính xác cho bean condition?
- [ ] Không dùng `@Primary` để thay cơ chế conditional back-off?
- [ ] Các auto-configs phụ thuộc nhau có order rõ?
- [ ] Context startup success và bean absence được assert riêng?
- [ ] Có `ConditionEvaluationReport`/debug procedure khi no match?
- [ ] Có một smoke test bảo đảm imports resource auto-discovery thật?
- [ ] Nếu web/reactive-only, dùng đúng context runner?
- [ ] Test không phụ thuộc OS locale, network, database hay port nếu không cần?
- [ ] Code examples được review Java 17 và Spring Boot 3.5, không tự tuyên bố đã compile/run?
- [ ] Đã phân biệt compile-time optional class với runtime classpath filtering?
- [ ] Có kiểm thử binary compatibility khi hỗ trợ nhiều optional library versions?

## 25. Lệnh chạy và kết quả dự kiến

Với JDK 17+, Gradle Wrapper đã có trong project:

~~~bash
./gradlew test --tests "com.example.formatter.autoconfigure.FormatterAutoConfigurationTests"
./gradlew test --tests "com.example.app.FormatterApplicationSmokeTests"
./gradlew test
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.formatter.autoconfigure.FormatterAutoConfigurationTests"
.\gradlew.bat test --tests "com.example.app.FormatterApplicationSmokeTests"
.\gradlew.bat test
~~~

Có **15 JUnit test methods** trong hai lớp: 14 runner tests và 1 smoke test. Trạng thái kỳ vọng:

~~~text
default/missing flag + OptionalCodec present -> CODEC:HELLO
training.formatter.enabled=true           -> default bean
training.formatter.enabled=false          -> no default bean
training.formatter.enabled=maybe          -> no default bean
user TextFormatter present                -> USER:abc (default backs off)
OptionalCodec hidden by FilteredClassLoader -> no default bean
Property not set + default matchIfMissing -> no strictSignal
Property present and "yes" + default havingValue -> strictSignal
Application smoke test with imports file  -> CODEC:HELLO
~~~

Đây là **đầu ra kỳ vọng theo phân tích code**, không phải stdout đã thu thập từ một lần chạy. Sample không `System.out.println`, nên không có stdout cố định. **Mã chưa được compile hoặc chạy Gradle/JUnit trong quá trình biên soạn**; để kiểm chứng cần tải dependencies, có Gradle Wrapper và JDK 17.

**Tổng kết:** Muốn kiểm thử auto-configuration đúng, hãy tạo **context riêng cho từng tổ hợp classpath, property và user bean**. `@ConditionalOnClass` nên bảo vệ nested configuration phụ thuộc optional library; `@ConditionalOnProperty` cần truth table và policy thiếu property rõ ràng; `@ConditionalOnMissingBean` dùng để auto-default back off theo bean definitions đã đăng ký. `ApplicationContextRunner` và `FilteredClassLoader` kiểm ma trận nhanh; một `@SpringBootTest` smoke test kiểm **AutoConfiguration.imports** thực sự hoạt động.

### Tài liệu chính thức

- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.5.16 — @ConditionalOnClass Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot 3.5.16 — @ConditionalOnProperty Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.5.16 — @ConditionalOnMissingBean Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html)
- [Spring Boot 3.5.16 — ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html)
- [Spring Framework 6.2 — Core @Conditional and @Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html)