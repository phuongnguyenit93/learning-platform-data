# AutoConfigurations.of và cấu hình cần được kiểm chứng trong Spring Boot Testing

## 1. Mục tiêu bài học

Spring Boot có một khả năng quan trọng: **auto-configuration**. Khi classpath có một thư viện, `Environment` chứa property phù hợp hoặc application chưa tự định nghĩa một bean cụ thể, Spring Boot có thể tự đăng ký các bean mặc định. Điều này làm ứng dụng dễ dùng, nhưng cũng tạo ra một nhóm lỗi khó phát hiện nếu chỉ kiểm bằng `@SpringBootTest` trên một bộ cấu hình duy nhất:

- Bean mặc định được tạo khi người dùng đã cung cấp custom bean, dẫn tới `NoUniqueBeanDefinitionException` hoặc chọn sai implementation.
- Bean đáng lẽ phải tắt khi `demo.notify.enabled=false` nhưng vẫn được tạo.
- Auto-configuration vô tình yêu cầu một optional library không có ở runtime.
- Bean phụ thuộc được tạo trước khi dependency đã được đăng ký.
- Cấu hình hoạt động khi chạy ứng dụng lớn nhưng fail trong một starter/library khác do bean ordering khác.
- Một test khởi động `ApplicationContext` và chỉ assert không có exception, không kiểm kết quả thật của conditions.
- Tester dùng `withUserConfiguration` để khai báo auto-config và mất tính đúng của ordering/conditional processing.
- File đăng ký auto-config trong `META-INF/spring/...AutoConfiguration.imports` bị thiếu, khiến ứng dụng thật không import class dù unit tests dùng explicit `AutoConfigurations.of(...)` vẫn xanh.

Để kiểm từng tổ hợp đầu vào có chủ đích, Spring Boot cung cấp **`ApplicationContextRunner`**; còn **`AutoConfigurations.of(...)`** tạo nhóm các class auto-configuration được đưa vào runner thông qua `withConfiguration(...)`.

Bài nằm trong nhóm **Kiểm thử auto-configuration** của module **Spring Boot – testing**, đúng chủ đề **AutoConfigurations.of và cấu hình cần được kiểm chứng**. Trọng tâm không phải tạo thật nhiều `@SpringBootTest` mà là **kiểm điều kiện và bean graph theo một test matrix nhỏ, tái lập được**.

Sau bài, bạn sẽ:

1. Hiểu khi nào dùng `AutoConfigurations.of` và khi nào dùng `withUserConfiguration`.
2. Tạo `ApplicationContextRunner` chỉ nạp các auto-configurations muốn kiểm, không khởi chạy full SpringApplication.
3. Kiểm `@ConditionalOnClass`, `@ConditionalOnMissingBean`, `@ConditionalOnBean`, `@ConditionalOnProperty`, `matchIfMissing` và `havingValue`.
4. Đặt nhiều auto-configurations trong `AutoConfigurations.of(...)` nhưng vẫn giữ semantics ordering chính thức.
5. Kiểm default beans, custom beans back-off, property enable/disable, dependency gating, user override và missing classpath.
6. Dùng `FilteredClassLoader` giả lập thiếu dependency mà không sửa project classpath thật.
7. Kiểm `ApplicationContext` khởi động thành công/thất bại, nhưng không đánh đồng điều đó với feature có hoạt động đúng.
8. Dùng `ConditionEvaluationReportLoggingListener` chẩn đoán vì sao một condition match hoặc không match.
9. Phân biệt **test runner trực tiếp import class** với **startup thực tế đọc AutoConfiguration.imports**.
10. Viết smoke test `@SpringBootTest` để bảo vệ tích hợp vào application.
11. Biết khi nào dùng `WebApplicationContextRunner`/`ReactiveWebApplicationContextRunner`, không dùng runner thường để giả lập servlet context.
12. Chạy một project minh họa đầy đủ bằng **Java 17, Spring Boot 3.3.5, Gradle, JUnit Jupiter, AssertJ**, không cần Docker, database hoặc HTTP server.

**Thông điệp cốt lõi:** Với auto-configuration, thứ bạn muốn kiểm không chỉ là **“context có start không?”** mà là **“đúng bean có xuất hiện/biến mất và cấu hình đúng trong từng hoàn cảnh hay không?”**.

## 2. Tự động cấu hình khác cấu hình thủ công như thế nào?

Spring Framework hỗ trợ khai báo bean qua `@Configuration` và `@Bean`:

~~~java
@Configuration(proxyBeanMethods = false)
class UserNotificationConfiguration {

    @Bean
    NotificationClient myClient() {
        return message -> "USER::" + message;
    }
}
~~~

Nếu ứng dụng import cấu hình này, bean được đăng ký vì developer **chủ động khai báo**.

Auto-configuration trong Spring Boot thường dùng `@AutoConfiguration` và các điều kiện:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.notify.optional.OptionalTransport")
@ConditionalOnProperty(
    prefix = "demo.notify",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
class NotifyAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationClient.class)
    NotificationClient notificationClient() {
        return message -> "READY::" + message;
    }
}
~~~

Trong ví dụ, bean mặc định chỉ nên xuất hiện khi **các điều kiện liên quan** thỏa:

- Optional marker class có trên classpath.
- Feature được bật; khi property không tồn tại, `matchIfMissing=true` cho phép bật theo default.
- Chưa có `NotificationClient` do user hoặc config khác khai báo trong phạm vi tìm kiếm.

Đây chính là phần dễ có lỗi: chỉ cần đảo một annotation, sai property name hoặc thứ tự đăng ký bean là hành vi khác đi.

### Thứ tự quyết định được nhìn nhận như thế nào?

Một cách hiểu:

~~~text
ApplicationContextRunner
  |
  +-- user-defined configurations / beans
  |       |
  |       v
  |    user NotificationClient có tồn tại?
  |
  +-- auto-configuration candidates
          |
          +-- @ConditionalOnClass
          +-- @ConditionalOnProperty
          +-- @ConditionalOnMissingBean
          |
          +-- default NotificationClient nếu phù hợp
          |
          +-- @ConditionalOnBean(NotificationClient)
                   |
                   +-- NotificationObservation nếu có client
~~~

Trong Spring Boot, các bean conditions kiểm những bean definitions đã được xử lý **tại thời điểm đánh giá**; vì vậy `@ConditionalOnMissingBean` và `@ConditionalOnBean` nên được đặt trên **auto-configuration** thay vì coi chúng là chính sách toàn cục bất kể registration order. `AutoConfigurations.of(...)` cùng `@AutoConfiguration(after=...)` giúp kiểm đúng thứ tự của các auto-configurations được chọn.

## 3. `AutoConfigurations.of(...)` chính xác là gì?

Import:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
~~~

API quan trọng:

~~~java
AutoConfigurations.of(
        NotifyAutoConfiguration.class,
        NotificationObservationAutoConfiguration.class)
~~~

Nó tạo một đối tượng chứa các classes **auto-configuration** cho một `ApplicationContextRunner`. Tập classes được sắp theo ordering semantics của auto-configuration, bao gồm metadata như `@AutoConfiguration(after=...)` hoặc `@AutoConfigureAfter`.

Mẫu chuẩn:

~~~java
private final ApplicationContextRunner runner =
    new ApplicationContextRunner()
        .withConfiguration(
            AutoConfigurations.of(
                NotifyAutoConfiguration.class,
                NotificationObservationAutoConfiguration.class));
~~~

Sau đó:

~~~java
runner.run(context -> {
    assertThat(context)
        .hasSingleBean(NotificationClient.class);
});
~~~

Đây là **các snippet sử dụng những classes do project mẫu khai báo** ở phần dưới; không phải standalone code.

### `AutoConfigurations.of` có phải lệnh khởi động Spring Boot?

**Không.** Nó không tự tạo ApplicationContext hoặc start application. `AutoConfigurations.of` chỉ cung cấp nhóm configuration classes; chính `ApplicationContextRunner.run(...)` mới dựng, refresh và đóng một context test cô lập.

### Có tự đọc file AutoConfiguration.imports không?

**Không trong bài test runner explicit này.** Khi gọi `AutoConfigurations.of(NotifyAutoConfiguration.class)`, bạn đã trực tiếp chỉ định candidate. Nếu file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` không tồn tại, runner vẫn có thể kiểm class đó thành công; ngược lại, full Boot startup có thể **không thấy** auto-configuration của starter. Do đó project mẫu có **hai tầng tests**:

- **Runner tests:** bảo vệ condition/bean wiring trong auto-config class.
- **Full Boot smoke test:** bảo vệ file imports và sự tích hợp khi application thực sự khởi động.

### Có tự quét toàn bộ classpath để auto-configure như app không?

**Không.** Runner được thiết kế để kiểm các classes bạn chỉ định, giữ scope nhỏ. Nó không thay toàn bộ `SpringApplication.run`, không mặc định chạy lifecycle của mọi `EnvironmentPostProcessor` và không tự tải mọi app/auto-configuration. Khi test phụ thuộc side effects từ SpringApplication bootstrap, bạn phải mô phỏng rõ bằng `withInitializer`, properties hoặc bổ sung một full-startup test.

### Có bảo đảm thứ tự khai báo trong `of(...)` giống thứ tự bean tạo không?

Phải phân biệt:

1. **Auto-config ordering:** `AutoConfigurations.of` sắp candidates theo auto-config semantics; không nhất thiết áp dụng theo thứ tự các arguments.
2. **Bean definition registration:** chịu ảnh hưởng configuration ordering và Spring processing.
3. **Bean instantiation:** phụ thuộc dependency graph, injection, lazy settings và `@DependsOn`, **không đồng nhất** với definition order.

Không dùng việc đổi vị trí hai class trong `AutoConfigurations.of(A.class, B.class)` như cách chữa một bean condition lỗi. Hãy khai báo `@AutoConfiguration(after=OtherAutoConfiguration.class)` khi có dependency ordering thật.

## 4. `ApplicationContextRunner` kiểm được những gì?

Import:

~~~java
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
~~~

Một runner tiêu chuẩn hoạt động theo chu trình:

~~~text
new ApplicationContextRunner()
  -> withConfiguration(AutoConfigurations.of(...))
  -> withUserConfiguration(UserConfig.class) [tùy test]
  -> withPropertyValues("demo.notify.enabled=false") [tùy test]
  -> withBean(...) [tùy test]
  -> withClassLoader(new FilteredClassLoader(...)) [tùy test]
  -> run(context -> { assert bean graph / errors / properties; })
  -> context đóng sau callback
~~~

Mỗi lần `run` tạo context mới được cấu hình theo runner hiện tại. Các builder methods như `withPropertyValues` trả **runner cấu hình mới** để có thể dùng base runner lặp lại. Điều này giúp các test methods độc lập, không cần gọi `SpringApplication.run()` mỗi lần.

### API hữu ích

| API | Vai trò | Trường hợp |
| --- | --- | --- |
| `withConfiguration(AutoConfigurations.of(...))` | Nạp auto-config candidates theo semantics Boot | Trọng tâm bài |
| `withUserConfiguration(UserConfig.class)` | Cấp cấu hình do người dùng khai báo | Test `@ConditionalOnMissingBean` back-off |
| `withBean(Type.class, supplier)` | Đăng ký trực tiếp một bean test | Kiểm override nhanh mà không tạo file config |
| `withPropertyValues("key=value")` | Thay `Environment` | Test feature flags/port/prefix |
| `withClassLoader(new FilteredClassLoader(...))` | Giả lập class không có trên classpath | Test `@ConditionalOnClass` |
| `withInitializer(...)` | Hook trước refresh | Report, custom setup |
| `withParent(...)` | Tạo context hierarchy | Bean search scopes, parent dependencies |
| `withAllowBeanDefinitionOverriding(...)` | Chỉnh bean-definition override policy cho một test | Hỗ trợ case có lý do; không dùng để che duplicate |
| `run(context -> ...)` | Tạo, kiểm, đóng context | Mỗi test case |
| `assertThat(context).hasSingleBean(...)` | Assert bean theo type | Default/back-off |
| `assertThat(context).doesNotHaveBean(...)` | Assert bean vắng mặt | Condition false |
| `assertThat(context).hasFailed()` | Assert startup failure | Config invalid |
| `context.getStartupFailure()` | Lấy Throwable khi context fail | Chẩn đoán root cause |

Với các auto-configurations bị ràng buộc bởi servlet/reactive web environment, dùng **`WebApplicationContextRunner`** hoặc **`ReactiveWebApplicationContextRunner`**; `ApplicationContextRunner` mặc định tạo một annotation-based non-web application context.

### Runner có là JUnit annotation không?

Không. Nó là một Java helper object dùng trong JUnit test method bình thường. Không cần `@SpringBootTest` hay `@ExtendWith(SpringExtension.class)` cho test chỉ dùng `ApplicationContextRunner`, vì runner tự dựng context trong callback. Điều này giữ chi phí test thấp.

### Runner có thể chạy trong native image không?

Theo tài liệu Spring Boot 3.3, **`ApplicationContextRunner` không hoạt động khi chạy các tests trong native image**. Đừng dùng runner results để khẳng định native build đã được kiểm; các native/AOT cases cần một luồng test/build tương thích riêng.

## 5. Điều kiện cần kiểm chứng: từng nhóm

### 5.1. `@ConditionalOnProperty`

Ví dụ:

~~~java
@ConditionalOnProperty(
    prefix = "demo.notify",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
~~~

Trạng thái cần test:

| `demo.notify.enabled` | `havingValue="true"` | `matchIfMissing=true` | Kỳ vọng |
| --- | --- | --- | --- |
| Không có | — | Được áp dụng | Bật |
| `true` | Match | — | Bật |
| `false` | Không match | — | Tắt |
| `yes` | Không khớp `true` theo giá trị string condition này | — | Tắt |
| `unexpected` | Không match | — | Tắt |
| Empty value | Không match | — | Tắt |

Khi **không có `havingValue`**, semantics mặc định của `@ConditionalOnProperty` là property **tồn tại và khác chuỗi `false`**; điều đó có thể gây bất ngờ nếu người học giả định boolean parser chấp nhận mọi giá trị. Khi muốn feature flag rõ ràng, dùng `havingValue="true"` và có cases phủ định.

**`matchIfMissing` không phải default value của một bean.** Nó chỉ quyết định **condition có match khi key vắng mặt hay không**. Khi bean được tạo, các property còn lại vẫn cần được bind/resolve đúng.

### 5.2. `@ConditionalOnClass`

~~~java
@ConditionalOnClass(
    name = "com.example.notify.optional.OptionalTransport")
~~~

Chỉ match nếu class tương ứng có trên classpath mà classloader của context nhìn thấy. Điều này hữu ích cho auto-configuration của thư viện optional như Redis, Kafka, HTTP client hoặc DB driver. **Test ở laptop vốn có mọi dependencies** có thể không phát hiện được thiếu-dependency case. Dùng `FilteredClassLoader` để tạo case âm tính.

### 5.3. `@ConditionalOnMissingBean`

~~~java
@Bean
@ConditionalOnMissingBean(NotificationClient.class)
NotificationClient notificationClient() {
    return message -> "READY::" + message;
}
~~~

Spring tạo **default bean** nếu không thấy bean target theo tìm kiếm tại thời điểm xử lý. Khi user tự định nghĩa `NotificationClient`, auto-config phải **back off**, không tạo thêm default. Assertions quan trọng:

- `hasSingleBean(NotificationClient.class)`.
- Client thực được lấy từ user-config, không phải từ default.
- Downstream bean có thể dùng đúng client do user cung cấp.

Test chỉ kiểm “context starts” có thể bỏ sót duplicate beans nếu không có bean nào yêu cầu injection theo type tại startup.

### 5.4. `@ConditionalOnBean`

~~~java
@Bean
@ConditionalOnBean(NotificationClient.class)
NotificationObservation notificationObservation(
        NotificationClient client) {
    return new NotificationObservation(client);
}
~~~

Nếu có client — default hoặc user-defined — observation bean được tạo; nếu không có, observation vắng mặt. Để tránh bean condition thấy thiếu dependency vì registration order, cấu hình observation dùng `@AutoConfiguration(after=NotifyAutoConfiguration.class)`.

### 5.5. `@ConditionalOnWebApplication`

Dùng khi chỉ muốn cấu hình servlet hoặc reactive web environment. Không kỳ vọng một `ApplicationContextRunner` non-web sẽ match condition servlet. Khi cần, dùng web runner và mô phỏng đúng classpath/environment. Không nên chỉ “import WebMvcAutoConfiguration” vào runner rồi kết luận đã tạo servlet `WebApplicationContext`.

### 5.6. `@ConditionalOnResource`, `@ConditionalOnMissingClass`, `@ConditionalOnExpression`

Các nhóm condition khác:

- `@ConditionalOnResource(resources="classpath:...")`: cần resource hiện hữu; test cả có/không resource.
- `@ConditionalOnMissingClass("...")`: kích hoạt khi class thiếu, phù hợp fallback implementations.
- `@ConditionalOnExpression`: dùng SpEL; thận trọng vì expression tham chiếu bean có thể khiến bean khởi tạo rất sớm, ảnh hưởng post-processing.
- `@ConditionalOnSingleCandidate`: cần một candidate rõ theo type/primary policy, không thay thế mọi `@Qualifier`.
- `@ConditionalOnJava`: phụ thuộc Java version.
- `@ConditionalOnCloudPlatform`: phụ thuộc platform signals; không dùng nhiều framework-specific assumptions.

Không nhất thiết thêm tất cả vào một lab. Bài tập sau phần runnable sẽ hướng dẫn tạo ma trận nhỏ tương ứng.

## 6. Test matrix trước khi viết source

Một auto-configuration ví dụ tên `NotifyAutoConfiguration` sẽ cung cấp `NotificationClient` mặc định. Auto-config thứ hai `NotificationObservationAutoConfiguration` tạo bean quan sát nếu `NotificationClient` đã tồn tại và có thể tắt riêng bằng property.

| # | Bối cảnh | `NotificationClient` | `NotificationObservation` | Giá trị đáng kiểm |
| ---: | --- | --- | --- | --- |
| 1 | Marker có; properties vắng mặt | Default 1 bean | Có 1 bean | `READY::hello` |
| 2 | Prefix custom | Default | Có | Prefix thật thay đổi |
| 3 | `enabled=true` | Default | Có | Explicit true match |
| 4 | `enabled=false` | Không có | Không có | Feature off |
| 5 | `enabled=yes` | Không có | Không có | `havingValue=true` chặn |
| 6 | `meter-enabled=false` | Default | Không có | Subfeature off |
| 7 | Optional marker bị filter khỏi classpath | Không có | Không có | Guard classpath |
| 8 | User-defined `NotificationClient` | Chỉ user bean | Có | Default back-off |
| 9 | `withBean(NotificationClient.class,...)` | Chỉ injected test bean | Có | Direct override |
| 10 | Disabled default + user client | User bean vẫn có | Có | Disabled auto-config không xóa user bean |
| 11 | Chỉ Observation auto-config, không có client | Không có | Không có | @ConditionalOnBean no-match |
| 12 | Chỉ Notify auto-config | Default | Không có | Runner scope tường minh |
| 13 | Broken user config | Context fail | Không có valid graph | Startup exception |
| 14 | Full Boot startup + imports file | Default | Có | Auto-discovery registration |

Đây là **test specification**, giúp từng bài test kiểm đúng một nguyên nhân. Nếu bạn tạo một test vừa tắt feature vừa filter classpath vừa add custom bean, kết quả “không có bean” không nói được condition nào đúng.

## 7. Project Java 17 + Spring Boot 3.3.5 + Gradle

Project minh họa tạo hai auto-configurations có ordering rõ, không yêu cầu networking. Nó có một application root **nằm ngoài package của auto-configuration** để đảm bảo class được load qua **AutoConfiguration.imports** thay vì tình cờ được component-scan.

### 7.1. Cây thư mục

~~~text
auto-config-testing-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── com/example/app/
    │   │   │   └── NotifyDemoApplication.java
    │   │   └── com/example/notify/
    │   │       ├── api/
    │   │       │   ├── NotificationClient.java
    │   │       │   └── NotificationObservation.java
    │   │       ├── optional/
    │   │       │   └── OptionalTransport.java
    │   │       └── autoconfigure/
    │   │           ├── NotifyAutoConfiguration.java
    │   │           └── NotificationObservationAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/example/notify/
        ├── NotificationAutoConfigurationTest.java
        └── BootAutoConfigurationSmokeTest.java
~~~

**Package placement có chủ đích:** `com.example.app` không scan package `com.example.notify` theo mặc định. Nếu xóa file `AutoConfiguration.imports`, full Boot smoke test phải thất bại, trong khi runner tests được chỉ định trực tiếp vẫn chạy. Đây là một phép kiểm chống **false confidence**.

Gradle Wrapper files là scripts/JAR được sinh bởi Gradle, không phải nội dung có thể biểu diễn toàn bộ bằng Markdown. Sau khi có Wrapper tương thích, những Java/resources ở dưới đủ cho demo `test`.

### 7.2. `settings.gradle`

~~~groovy
rootProject.name = 'auto-config-testing-lab'
~~~

### 7.3. `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`spring-boot-starter` cung cấp nền tảng Spring Boot/auto-configuration, không thêm web server/JPA/DB vào demo. `spring-boot-starter-test` cung cấp `ApplicationContextRunner`, JUnit Jupiter và AssertJ. `spring-boot-autoconfigure-processor` có thể tạo metadata hỗ trợ early filtering của auto-configurations; **nó không thay file `AutoConfiguration.imports`** và không được dùng làm bằng chứng rằng auto-config đã được đăng ký.

`useJUnitPlatform()` giúp Gradle chạy tests JUnit Jupiter.

### 7.4. `NotifyDemoApplication.java`

**`src/main/java/com/example/app/NotifyDemoApplication.java`**

~~~java
package com.example.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class NotifyDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotifyDemoApplication.class, args);
    }
}
~~~

Nhờ `@SpringBootApplication`, Spring Boot sẽ đọc auto-configuration imports trong dependencies/resource path khi khởi động. Không thêm `@ComponentScan("com.example.notify")` chỉ để các auto-config classes được tìm thấy; như vậy có thể che lỗi file registration bị thiếu.

### 7.5. `NotificationClient.java`

**`src/main/java/com/example/notify/api/NotificationClient.java`**

~~~java
package com.example.notify.api;

@FunctionalInterface
public interface NotificationClient {

    String format(String message);
}
~~~

Đây là interface nhỏ để test điều kiện bean, không thực sự gửi email/SMS và không có network side effects. Chọn tên `NotificationClient` để dễ liên hệ tới auto-config của library/starter.

### 7.6. `NotificationObservation.java`

**`src/main/java/com/example/notify/api/NotificationObservation.java`**

~~~java
package com.example.notify.api;

public record NotificationObservation(
        NotificationClient client) {

    public String sample() {
        return client.format("probe");
    }
}
~~~

Java 17 hỗ trợ `record`. Bean `NotificationObservation` phụ thuộc trực tiếp vào `NotificationClient`, giúp test biết nó sử dụng **default client** hay **user-provided client**.

### 7.7. `OptionalTransport.java`

**`src/main/java/com/example/notify/optional/OptionalTransport.java`**

~~~java
package com.example.notify.optional;

public final class OptionalTransport {

    private OptionalTransport() {
    }
}
~~~

Class này là **marker giả lập một optional dependency**. Trong project thực, marker có thể là `org.postgresql.Driver`, một SDK client class hoặc class do thư viện third-party cung cấp. Bài dùng marker cùng project để ví dụ tự chứa và có thể dùng `FilteredClassLoader` mô phỏng absent class.

**Tại sao không dùng `Class.forName` bên trong @Bean factory?** Nếu auto-config không guard class đúng, thiếu library có thể làm context fail trước khi điều kiện được đánh giá. Đặt `@ConditionalOnClass` ở class level và tách type-dependent nested config nếu cần là pattern an toàn hơn.

## 8. Auto-configuration thứ nhất: chỉ tạo default client khi điều kiện đúng

**`src/main/java/com/example/notify/autoconfigure/NotifyAutoConfiguration.java`**

~~~java
package com.example.notify.autoconfigure;

import com.example.notify.api.NotificationClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(
    name = "com.example.notify.optional.OptionalTransport")
@ConditionalOnProperty(
    prefix = "demo.notify",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true)
public class NotifyAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NotificationClient.class)
    NotificationClient notificationClient(
            @Value("${demo.notify.prefix:READY}") String prefix) {

        return message -> prefix + "::" + message;
    }
}
~~~

### Lý giải design choices

- `@AutoConfiguration`: xác định class là auto-configuration candidate.
- `@ConditionalOnClass(name=...)`: dùng chuỗi tên đầy đủ, không ép JVM phải load optional class qua method signature. Khi marker thiếu, **toàn bộ auto-config bị loại**.
- `@ConditionalOnProperty(...enabled...)`: property mặc định vắng mặt vẫn cho phép bật; explicit `false` chặn; `havingValue="true"` ngăn chuỗi bất kỳ như `yes` được coi là bật.
- `@Bean @ConditionalOnMissingBean(NotificationClient.class)`: nếu ứng dụng đã tự khai báo một `NotificationClient`, auto-config nhường quyền.
- `@Value("${demo.notify.prefix:READY}")`: prefix default là `READY` nếu không có property, tùy biến được trong runner.
- Bean trả về type interface `NotificationClient`, đủ thông tin để Spring kiểm candidate theo type.
- Bean không làm I/O khi khởi tạo; runner tests tập trung vào **bean graph/condition semantics**, không phụ thuộc mạng.

### Bẫy `@ConditionalOnClass` trên @Bean method

Đặt một bean method có return type từ optional library **mà class thực tế không có** có thể khiến JVM phải resolve method signature trước khi condition được áp dụng. Với optional classes, pattern phù hợp là:

~~~java
@AutoConfiguration
class ExternalTransportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.ExternalClient")
    static class ExternalClientConfiguration {

        // Bean methods tham chiếu ExternalClient
        // chỉ được định nghĩa trong nested config
        // khi class tương ứng có sẵn.
    }
}
~~~

Đây là **snippet thiết kế**, không phải Java runnable độc lập vì chưa có actual external client bean/method. Mục đích là tránh làm classload một type không có trước khi condition có thể bảo vệ.

### `matchIfMissing` không đồng nghĩa default prefix

Hai defaults khác nhau:

- Không có `demo.notify.enabled` → auto-config vẫn được bật vì `matchIfMissing=true`.
- Không có `demo.notify.prefix` → parameter bean factory nhận `READY` nhờ `@Value` default.

Một test nên kiểm cả hai để phát hiện việc sửa nhầm condition hoặc property resolution.

## 9. Auto-configuration thứ hai: chỉ tạo observer khi đã có client

**`src/main/java/com/example/notify/autoconfigure/NotificationObservationAutoConfiguration.java`**

~~~java
package com.example.notify.autoconfigure;

import com.example.notify.api.NotificationClient;
import com.example.notify.api.NotificationObservation;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration(after = NotifyAutoConfiguration.class)
@ConditionalOnProperty(
    prefix = "demo.notify",
    name = "meter-enabled",
    havingValue = "true",
    matchIfMissing = true)
public class NotificationObservationAutoConfiguration {

    @Bean
    @ConditionalOnBean(NotificationClient.class)
    NotificationObservation notificationObservation(
            NotificationClient client) {

        return new NotificationObservation(client);
    }
}
~~~

### Tại sao dùng `after`?

`NotificationObservation` phụ thuộc bean `NotificationClient`. Nếu observation auto-config được xử lý **trước** notification auto-config, `@ConditionalOnBean(NotificationClient.class)` có thể không match vì bean definition chưa xuất hiện. `@AutoConfiguration(after=NotifyAutoConfiguration.class)` diễn đạt rõ dependency ordering giữa **definitions**.

Lưu ý:

- `after` không có nghĩa `NotificationClient` object luôn được instantiate hoàn tất trước khi mọi auto-config class được parse; bean instantiation và definition ordering là hai khái niệm khác nhau.
- `@ConditionalOnBean` ở bean method nghĩa **chỉ observer bean** được guard; class config vẫn có thể được đăng ký dù không có client.
- `demo.notify.meter-enabled=false` tắt observer mà **không tắt NotificationClient**.
- `demo.notify.enabled=false` tắt default client nhưng **không có quyền tự xóa user bean**; nếu user vẫn cung cấp NotificationClient và meter-enabled=true, observation bean có thể vẫn xuất hiện. Đây là semantics cần test, không phải lỗi.

### Không dùng bean definition overriding để “bắt custom thắng”

Một design sai có thể định nghĩa cả default bean và custom bean cùng tên rồi bật:

~~~properties
spring.main.allow-bean-definition-overriding=true
~~~

Điều đó có thể che xung đột cấu hình thay vì giải quyết. `@ConditionalOnMissingBean` dùng để auto-config **back off theo type** khi user bean có mặt, đúng mục đích của starter. Test cần chứng minh **chỉ một bean theo type** và instance đó là user bean, không chỉ kiểm một bean name.

## 10. Đăng ký auto-configuration với Spring Boot

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.example.notify.autoconfigure.NotifyAutoConfiguration
com.example.notify.autoconfigure.NotificationObservationAutoConfiguration
~~~

Mỗi dòng là một fully qualified class name. Spring Boot 3.3 dùng resource **`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`** để phát hiện auto-configurations trong libraries. Đây không phải `spring.factories` kiểu đăng ký auto-configuration của các phiên bản Boot cũ.

### Vì sao không để component scan tìm classes?

Auto-configurations thuộc library nên có package riêng, không bị ứng dụng scan như ordinary components. Khi library được thêm vào classpath, Boot lựa chọn candidates từ imports file, kiểm conditions và auto-config ordering. Nếu auto-config vô tình được scan như một `@Configuration` thông thường, điều kiện bean/ordering có thể được xử lý sai so với semantics của auto-config được dự tính.

Trong lab, `NotifyDemoApplication` thuộc `com.example.app`, còn `NotifyAutoConfiguration` thuộc `com.example.notify.autoconfigure` nên **không nằm dưới package scan** của app. Bằng chứng integration tốt là smoke test start Boot và thấy client/observation beans mà **không dùng @Import hai configs bằng tay**.

### Kiểm file imports có gì khác runner?

`ApplicationContextRunner.withConfiguration(AutoConfigurations.of(...))` cho các classes có mặt **trực tiếp**, bất kể imports file. Chỉ `@SpringBootTest`/`SpringApplication.run` với Boot auto-configuration discovery mới bao phủ đường đăng ký bằng resource. Vì vậy:

- Runner test pass + Boot smoke test pass: vừa condition behavior, vừa auto-discovery.
- Runner test pass + Boot smoke fail: nghi thiếu imports, wrong class names, configuration scan/order, resource packaging hoặc differences ở app context.
- Runner test fail: condition/configuration wiring chưa đạt contract, chưa cần đổ lỗi packaging.

## 11. JUnit runner tests: toàn bộ test matrix

**`src/test/java/com/example/notify/NotificationAutoConfigurationTest.java`**

~~~java
package com.example.notify;

import com.example.notify.api.NotificationClient;
import com.example.notify.api.NotificationObservation;
import com.example.notify.autoconfigure.NotifyAutoConfiguration;
import com.example.notify.autoconfigure.NotificationObservationAutoConfiguration;
import com.example.notify.optional.OptionalTransport;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class NotificationAutoConfigurationTest {

    // Cố ý truyền observer trước client, để test xác nhận
    // @AutoConfiguration(after=...) quyết định ordering,
    // không dựa vào thứ tự truyền tham số.
    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                NotificationObservationAutoConfiguration.class,
                NotifyAutoConfiguration.class));

    @Test
    void defaultAutoConfigurationCreatesBothBeans() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(
                    NotificationClient.class);
            assertThat(context).hasSingleBean(
                    NotificationObservation.class);

            NotificationClient client =
                    context.getBean(NotificationClient.class);

            assertThat(client.format("hello"))
                    .isEqualTo("READY::hello");
            assertThat(context
                    .getBean(NotificationObservation.class)
                    .sample())
                    .isEqualTo("READY::probe");
        });
    }

    @Test
    void customPropertyIsInjectedIntoDefaultClient() {
        runner
            .withPropertyValues("demo.notify.prefix=TEST")
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context
                        .getBean(NotificationClient.class)
                        .format("message"))
                        .isEqualTo("TEST::message");
                assertThat(context
                        .getBean(NotificationObservation.class)
                        .sample())
                        .isEqualTo("TEST::probe");
            });
    }

    @Test
    void explicitTrueEnablesDefaultClient() {
        runner
            .withPropertyValues("demo.notify.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context).hasSingleBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void explicitFalseDisablesDefaultClient() {
        runner
            .withPropertyValues("demo.notify.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void unexpectedFlagValueDoesNotCountAsTrue() {
        runner
            .withPropertyValues("demo.notify.enabled=yes")
            .run(context -> {
                assertThat(context).doesNotHaveBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void disablingMeterDoesNotDisableClient() {
        runner
            .withPropertyValues(
                "demo.notify.meter-enabled=false")
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
                assertThat(context
                        .getBean(NotificationClient.class)
                        .format("x"))
                        .isEqualTo("READY::x");
            });
    }

    @Test
    void missingOptionalClassDisablesAutoConfiguration() {
        runner
            .withClassLoader(
                new FilteredClassLoader(OptionalTransport.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void userDefinedClientMakesDefaultBackOff() {
        runner
            .withUserConfiguration(CustomUserConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context).hasSingleBean(
                        NotificationObservation.class);

                NotificationClient custom =
                    context.getBean(
                        "customNotificationClient",
                        NotificationClient.class);

                assertThat(context
                        .getBean(NotificationClient.class))
                        .isSameAs(custom);
                assertThat(custom.format("hello"))
                        .isEqualTo("USER::hello");
                assertThat(context
                        .getBean(NotificationObservation.class)
                        .sample())
                        .isEqualTo("USER::probe");
            });
    }

    @Test
    void withBeanRegistersOverrideWithoutExtraConfig() {
        runner
            .withBean(
                NotificationClient.class,
                () -> message -> "REGISTERED::" + message)
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context
                        .getBean(NotificationClient.class)
                        .format("x"))
                        .isEqualTo("REGISTERED::x");
                assertThat(context
                        .getBean(NotificationObservation.class)
                        .sample())
                        .isEqualTo("REGISTERED::probe");
            });
    }

    @Test
    void disabledDefaultDoesNotDeleteUserClient() {
        runner
            .withPropertyValues("demo.notify.enabled=false")
            .withUserConfiguration(CustomUserConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context).hasSingleBean(
                        NotificationObservation.class);

                assertThat(context
                        .getBean(NotificationObservation.class)
                        .sample())
                        .isEqualTo("USER::probe");
            });
    }

    @Test
    void observerAloneRequiresAnExistingClient() {
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                NotificationObservationAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void baseClientAloneDoesNotCreateObserver() {
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                NotifyAutoConfiguration.class))
            .run(context -> {
                assertThat(context).hasSingleBean(
                        NotificationClient.class);
                assertThat(context).doesNotHaveBean(
                        NotificationObservation.class);
            });
    }

    @Test
    void startupFailureCanBeAssertedAndDiagnosed() {
        runner
            .withUserConfiguration(BrokenUserConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasRootCauseInstanceOf(
                            IllegalStateException.class);
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomUserConfiguration {

        @Bean
        NotificationClient customNotificationClient() {
            return message -> "USER::" + message;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class BrokenUserConfiguration {

        @Bean
        Integer deliberatelyBroken() {
            throw new IllegalStateException(
                    "simulated invalid user configuration");
        }
    }
}
~~~

### 11.1. Vì sao intentionally đảo thứ tự trong `AutoConfigurations.of`?

Test runner truyền `NotificationObservationAutoConfiguration` trước `NotifyAutoConfiguration`, mặc dù observation phụ thuộc client. Khi dùng `AutoConfigurations.of(...)`, Spring Boot sắp candidates theo auto-config ordering, trong đó annotation `after=NotifyAutoConfiguration.class` có nghĩa. Điều cần bảo vệ là observer xuất hiện khi client xuất hiện; đừng suy luận bean instantiation bằng thứ tự arguments trong Java.

Nếu bỏ `@AutoConfiguration(after=...)` ở branch thí nghiệm, hãy chạy test default và quan sát: bean condition `@ConditionalOnBean` có thể thấy thiếu client và observer không xuất hiện. Đó là **regression có thể phát hiện**, không phải cơ sở để dựa vào “may mắn Spring xử lý theo đúng thứ tự hôm nay”.

### 11.2. Vì sao mỗi method chạy một context?

Runner là một builder có `withConfiguration(...)` chung. Mỗi `run(context -> ...)` dựng một context độc lập và đóng nó sau callback, giúp không lẫn property enabled của test trước hoặc bean injected của test sau. Các assertions dùng `context` trong scope callback. **Không giữ bean reference rồi dùng sau khi callback kết thúc** nếu bean phụ thuộc resources bị đóng.

### 11.3. Test default và explicit true

Hai cases khác nhau:

- `defaultAutoConfigurationCreatesBothBeans`: không truyền `demo.notify.enabled` và vẫn phải có bean → bảo vệ `matchIfMissing=true`.
- `explicitTrueEnablesDefaultClient`: property có mặt, giá trị `true` và condition match → bảo vệ explicit opt-in.

Nếu developer vô tình đổi `matchIfMissing=false`, test default phải fail trong khi explicit true test vẫn pass. Nếu vô tình đổi `havingValue="false"`, explicit false/true tests sẽ phát hiện.

### 11.4. Test negative property

`demo.notify.enabled=false` không cho tạo default client. Vì không có client nào khác, observation bean cũng không nên có. Test vừa kiểm class-level condition vừa kiểm downstream bean condition.

Đối với `demo.notify.enabled=yes`, `havingValue="true"` buộc condition không match. Nếu bạn bỏ `havingValue`, semantics mặc định của `@ConditionalOnProperty` có thể match `yes` vì chuỗi đó khác `false`, test sẽ đỏ. Đây là một negative case có ích.

### 11.5. Subfeature property

`demo.notify.meter-enabled=false` chỉ ngăn observer, không làm mất client. Nếu class-level property được đặt nhầm trên `NotifyAutoConfiguration` thay vì observation config, test sẽ phát hiện client bị tắt ngoài ý muốn.

### 11.6. Missing classpath thật sự được mô phỏng

`FilteredClassLoader(OptionalTransport.class)` làm class được liệt kê **không còn visible đối với runner classloader**. Vì `@ConditionalOnClass(name=...)` là guard của `NotifyAutoConfiguration`, condition phải fail và không có default client. Observer cũng vắng mặt vì không có NotificationClient.

Không xóa JAR/cập nhật Gradle chỉ để test một case thiếu class; FilteredClassLoader giúp kiểm nhanh và tái lập. Với optional dependency của một library thật, hãy chọn **đúng class quyết định điều kiện**, không filter toàn bộ Spring package khiến test fail vì framework class bị mất.

### 11.7. User override: logic quan trọng của starter

`CustomUserConfiguration` cung cấp `NotificationClient customNotificationClient()`. Khi runner gọi `withUserConfiguration(...)`, bean user được đăng ký trước auto-config, do đó `@ConditionalOnMissingBean(NotificationClient.class)` phải back off.

Assertions cần xác nhận **chỉ có một bean** và **đúng instance user bean**:

~~~java
assertThat(context).hasSingleBean(NotificationClient.class);
assertThat(context.getBean(NotificationClient.class))
        .isSameAs(context.getBean(
                "customNotificationClient",
                NotificationClient.class));
~~~

Nếu bạn chỉ assert `context.containsBean("customNotificationClient")`, default bean thứ hai vẫn có thể tồn tại mà test không phát hiện. Nếu application autowires type, duplicate có thể gây ambiguous injection; vì vậy `hasSingleBean` là điều kiện thiết yếu.

### 11.8. `withBean` vs `withUserConfiguration`

`withBean(NotificationClient.class, supplier)` là cách test nhanh một bean được user cung cấp mà không viết một `@Configuration` class. Nó tốt để kiểm bean back-off theo type.

`withUserConfiguration(CustomUserConfiguration.class)` phù hợp khi cần kiểm:

- `@Bean` method return type và qualifiers.
- Configuration class/conditional metadata.
- Một nhóm custom beans liên quan.
- User configuration order khi kết hợp nhiều auto-configurations.
- Autowiring logic được biểu diễn giống một application.

Không dùng `withBean` để kết luận rằng một `@Configuration` phức tạp của sản phẩm sẽ tự được scan/đăng ký; runner không thể kiểm discovery ngoài phạm vi đã cấp.

### 11.9. Khi user bean còn tồn tại dù default feature disabled

`demo.notify.enabled=false` chỉ tắt `NotifyAutoConfiguration`. Nó không xóa `CustomUserConfiguration`. Nếu user vẫn đăng ký client, `NotificationObservationAutoConfiguration` nhìn thấy bean và có thể tạo observer theo property riêng.

Điều này không phải “feature flag bị hỏng” nếu contract của starter được thiết kế như vậy. Nếu mong `enabled=false` chặn **cả observer**, cần điều kiện tổng thể rõ trên observation auto-config hoặc một composite condition. Viết test matrix theo đặc tả thực của sản phẩm, không áp một ý nghĩa mơ hồ lên một key.

### 11.10. Kiểm startup failure có giá trị gì?

`BrokenUserConfiguration` cố ý ném exception khi Spring tạo bean. Runner vẫn gọi callback để test có thể assert `hasFailed()` và `getStartupFailure()`. Đây là cách bảo vệ behavior lỗi config, không khẳng định auto-config ứng dụng có thể phục hồi tự động.

**Không catch exception trong test để coi context khởi động thành công.** Chỉ assert failure khi case **cố ý kiểm fail-fast**. Trong trường hợp thường, nên assert `hasNotFailed()` kết hợp bean graph; chỉ “không fail” vẫn chưa đủ.

## 12. Smoke test: file imports và SpringBootApplication thật

Runner tests ở trên không kiểm `AutoConfiguration.imports`. Vì vậy cần một smoke test rất nhỏ nạp một Spring Boot application root ngoài auto-config package.

**`src/test/java/com/example/notify/BootAutoConfigurationSmokeTest.java`**

~~~java
package com.example.notify;

import com.example.app.NotifyDemoApplication;
import com.example.notify.api.NotificationClient;
import com.example.notify.api.NotificationObservation;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = NotifyDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "demo.notify.enabled=true",
        "demo.notify.meter-enabled=true",
        "demo.notify.prefix=BOOT"
    })
class BootAutoConfigurationSmokeTest {

    @Autowired
    private NotificationClient notificationClient;

    @Autowired
    private NotificationObservation notificationObservation;

    @Test
    void bootAutoDiscoversTheImportedConfigurations() {
        assertThat(notificationClient.format("hello"))
                .isEqualTo("BOOT::hello");

        assertThat(notificationObservation.sample())
                .isEqualTo("BOOT::probe");
    }
}
~~~

### Vì sao smoke test này khác runner test?

`@SpringBootTest` khởi động Spring Boot application thật. `NotifyDemoApplication` ở `com.example.app`, không scan `com.example.notify` classes. Vì project có file `AutoConfiguration.imports`, Spring Boot mới tự biết `NotifyAutoConfiguration` và `NotificationObservationAutoConfiguration` là candidates.

Nếu xóa file imports, `NotificationClient` và `NotificationObservation` sẽ không xuất hiện trong context này, khiến test fail ngay khi injection. Trong khi đó runner tests có thể vẫn xanh vì đã explicit `AutoConfigurations.of(...)`. **Hai tests bảo vệ hai lỗi khác nhau.**

### Khi nào smoke test còn cần nhiều hơn?

Trong một published starter/library, thực tế cần thêm:

- Build JAR và xác minh imports file nằm đúng path bên trong artifact.
- Dùng một minimal consumer app riêng để kiểm auto-discovery khi phụ thuộc JAR như dependency, không chỉ test trong cùng module.
- Kiểm không vô tình được component scan.
- Kiểm package name/imports của shaded/fat JAR và version metadata.
- Kiểm conditions trên classpath có/không external dependencies, không chỉ marker cùng module.
- Khi dùng Spring Boot AOT/native, thêm test/build riêng vì runner không chạy trong native image.

Lab giới hạn một module để người học dễ chạy, nhưng khái niệm phân tách auto-config module/starter/consumer app vẫn có giá trị khi chuyển sang dự án thực.

## 13. Chạy Gradle và đọc kết quả

Bộ mẫu có:

| Class | Số method `@Test` | Phạm vi |
| --- | ---: | --- |
| `NotificationAutoConfigurationTest` | 13 | Properties, classpath, default/back-off, dependency ordering, failure |
| `BootAutoConfigurationSmokeTest` | 1 | Boot startup auto-discovery qua imports |
| **Tổng** | **14** | Test condition riêng + integration smoke |

Linux/macOS:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Chạy riêng:

~~~bash
./gradlew test --tests 'com.example.notify.NotificationAutoConfigurationTest'
./gradlew test --tests 'com.example.notify.BootAutoConfigurationSmokeTest'
~~~

Với project có Gradle Wrapper, JDK17 và dependencies tải thành công, **kỳ vọng 14 JUnit methods pass**. Đây là **kết quả dự kiến từ mã nguồn**, không phải khẳng định test đã được chạy trên máy người học.

Báo cáo Gradle thường ở:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.notify.NotificationAutoConfigurationTest.xml
    └── TEST-com.example.notify.BootAutoConfigurationSmokeTest.xml
~~~

Không có `System.out.println` trong code test, nên **không có stdout nghiệp vụ cố định**. Nếu Gradle trả `UP-TO-DATE` hoặc `FROM-CACHE`, task có thể được reuse. Khi chẩn đoán regression:

~~~bash
./gradlew test --rerun-tasks
~~~

Nếu chưa có Wrapper nhưng máy đã cài Gradle thích hợp, có thể tạo:

~~~bash
gradle wrapper --gradle-version 8.8 --distribution-type bin
~~~

Sau đó lưu Wrapper scripts/JAR theo policy repository. Không tự nâng Boot/Spring Security/Testcontainers của dự án thật chỉ để đồng bộ tutorial.

### Vì sao test runners không dùng `@SpringBootTest`?

`ApplicationContextRunner` đã đủ dựng/đóng một context nhỏ với các auto-configs được chỉ định. Dùng `@SpringBootTest` trên **từng test matrix case** sẽ nạp nhiều unrelated configurations, tăng startup cost và khiến kết quả phụ thuộc toàn bộ app environment, dễ che condition logic. Full Boot smoke test chỉ kiểm phần mà runner **không thể kiểm độc lập**: imports/discovery và wiring thực.

## 14. Tại sao `AutoConfigurations.of` quan trọng với nhiều classes?

Giả sử một starter có:

~~~text
CoreClientAutoConfiguration
          |
          v
MetricsAutoConfiguration
          |
          v
TracingAutoConfiguration
          |
          v
WebAdapterAutoConfiguration
~~~

`CoreClient` tạo primary client, `Metrics` chỉ chạy nếu có client, `Tracing` chỉ chạy nếu có OpenTelemetry trên classpath và `WebAdapter` chỉ chạy trong servlet/reactive environment phù hợp.

Nếu trong test bạn dùng:

~~~java
new ApplicationContextRunner()
    .withUserConfiguration(
        CoreClientAutoConfiguration.class,
        MetricsAutoConfiguration.class);
~~~

thì bạn đã đối xử auto-configurations như **user configuration**. Khi conditions phụ thuộc registration ordering, kết quả có thể không phản ánh tình huống auto-config thật. Chọn:

~~~java
new ApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        CoreClientAutoConfiguration.class,
        MetricsAutoConfiguration.class));
~~~

Đây là snippet cần classes do project thực cung cấp; tên `CoreClientAutoConfiguration`/`MetricsAutoConfiguration` chỉ minh họa kiến trúc. Nguyên tắc: dùng **AutoConfigurations** cho config đóng vai trò auto-config, dùng **withUserConfiguration** cho config do người dùng ứng dụng cung cấp.

### Cần kiểm từng auto-config hay tất cả cùng lúc?

Cả hai, tùy mục tiêu:

- Test **một class riêng** để biết chính xác condition của nó, giảm noise.
- Test **nhóm liên quan** để xác nhận dependency ordering và bean graph hợp tác.
- Thêm **full Boot smoke** để biết imports/discovery đúng.
- Tránh nhét toàn bộ Boot auto-configurations vào mỗi runner test chỉ vì dễ gọi một list dài.

### Khi thêm `@AutoConfiguration(afterName=...)`

Nếu auto-config của bạn cần chạy sau class có thể không tồn tại hoặc thuộc một optional artifact, `afterName` cho phép tham chiếu tên class bằng String thay vì hard-link class. Đây là dependency ordering của auto-config, không tự tạo class/bean. Cần test cả trường hợp optional config có và không có nếu thứ tự có ảnh hưởng.

## 15. ConditionEvaluationReport: vì sao bean không xuất hiện?

Khi một test `doesNotHaveBean` pass, có thể bạn vẫn muốn biết lý do:

- Missing optional class?
- `enabled=false`?
- `@ConditionalOnMissingBean` không match vì user đã cung cấp bean?
- `@ConditionalOnBean` không thấy dependency?
- Wrong classpath, missing imports?
- Property name typo hoặc value unexpected?

Spring Boot có **`ConditionEvaluationReport`** để hiển thị các conditions match/not matched. Trong runner tests, có thể bật logging:

~~~java
import org.springframework.boot.autoconfigure.logging
        .ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

new ApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        NotifyAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener
            .forLogLevel(LogLevel.INFO))
    .withPropertyValues("demo.notify.enabled=false")
    .run(context -> {
        assertThat(context)
            .doesNotHaveBean(NotificationClient.class);
    });
~~~

Đây là **snippet minh họa trong một test method có imports thích hợp**. `ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)` được Spring Boot 3.3 hỗ trợ. Log có thể hiển thị positive/negative matches, nhưng **đừng hardcode nguyên văn log như assertion lâu dài**: thông điệp/format có thể đổi khi version thay đổi.

### Những điều nên nhìn trong report

- Class `NotifyAutoConfiguration` nằm trong report hay không.
- `OnClassCondition` có match marker hay không.
- `OnPropertyCondition` thấy property/value nào.
- `OnBeanCondition` đang tìm type/name gì, có candidate nào.
- Condition failed do class không có hay do property false?
- Auto-config class không có trong report vì chưa được import? Kiểm imports file/runner candidate list trước khi tìm lỗi BeanFactory.

**Bẫy:** Nếu custom log report xuất hiện và nói condition matched, điều đó không tự chứng minh bean đã được instantiate hay business feature hoạt động. Vẫn cần `hasSingleBean` và assertions trên bean behavior.

### Debug bằng startup failure

~~~java
runner.withUserConfiguration(BrokenUserConfiguration.class)
    .run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure())
            .hasRootCauseInstanceOf(IllegalStateException.class);
    });
~~~

Với tests cần chẩn đoán root cause, `getStartupFailure()` có thể cho Throwable gốc/traversal. Không tự catch và bỏ exception để test xanh.

## 16. Những lỗi thiết kế thường gặp với auto-configuration

| Lỗi | Tác động | Test phát hiện |
| --- | --- | --- |
| Không có `AutoConfiguration.imports` | App không tự nạp auto-config | `BootAutoConfigurationSmokeTest` |
| Dùng `withUserConfiguration` thay `AutoConfigurations.of` | Ordering khác production | Runner test auto-config dependencies |
| Quên `@ConditionalOnMissingBean` | Trùng user/default beans | `userDefinedClientMakesDefaultBackOff` |
| Điều kiện @ConditionalOnMissingBean theo wrong type | User override không có tác dụng | hasSingleBean + isSameAs |
| Quên `matchIfMissing=true` | Feature mặc định bị tắt | `defaultAutoConfigurationCreatesBothBeans` |
| Quên `havingValue="true"` | `enabled=yes` vẫn có thể match | `unexpectedFlagValueDoesNotCountAsTrue` |
| Sai property prefix/name | Setting không có hiệu lực | explicit true/false + prefix tests |
| Meter enabled property đặt nhầm core config | Tắt metric làm mất client | `disablingMeterDoesNotDisableClient` |
| Không có @ConditionalOnClass | Context có thể fail khi missing library | `missingOptionalClassDisablesAutoConfiguration` |
| ConditionalOnClass đặt lên method tham chiếu missing type | Classload có thể fail trước condition | Tách nested @Configuration + FilteredClassLoader |
| Sai ordering giữa auto-configs | Observer không thấy client | Default graph + observer tests |
| @ConditionalOnBean chỉ xét bean chưa đăng ký | Condition no-match ngoài ý muốn | `@AutoConfiguration(after=...)` + runner tests |
| Quên test user bean khi default disabled | Hiểu sai semantics feature flag | `disabledDefaultDoesNotDeleteUserClient` |
| Test chỉ assert context non-null | Bean graph sai nhưng test xanh | `hasSingleBean`, `doesNotHaveBean` |
| Runner test xanh nhưng app fail | Runner không thực hiện full SpringApplication bootstrap | Full Boot smoke + consumer app test |
| Sửa imports package/class name | App mất auto-config | Full Boot smoke |
| Condition report không có config class | Candidate chưa được load | Kiểm of/imports, không chỉ condition |
| Bật global bean overriding để né lỗi | Che duplicate definitions | Back-off tests theo type |
| Bean method return type quá chung | Condition không nhận ra candidate type | Kiểm explicit return type và user override |
| Property value/case/empty bất ngờ | Không match đúng | Property matrix |
| Native test chạy runner | Unsupported native image workflow | AOT/native test riêng |
| Context runner dùng cho servlet conditional | Web condition false | WebApplicationContextRunner |
| Test dùng system properties toàn JVM | Rò state giữa tests | withPropertyValues |
| Quá nhiều auto-configurations trong runner | Chậm, khó chẩn đoán | Giới hạn candidates, smoke riêng |
| Dùng import order thủ công để sửa bug | Dễ đổi khi refactor | AutoConfiguration before/after metadata |

### Phân biệt lỗi behavior và lỗi harness

Nếu test fail vì `NotificationObservation` không có, kiểm:

1. Runner có đưa cả hai classes vào `AutoConfigurations.of` chưa?
2. `NotifyAutoConfiguration` có match class/property chưa?
3. `NotificationClient` đã tồn tại theo BeanFactory chưa?
4. `NotificationObservationAutoConfiguration` có `after` đúng chưa?
5. Meter-enabled property có bị tắt không?
6. Observation bean method có condition theo đúng type không?
7. Runner dùng classloader/parent context nào?
8. Có test-only user bean nào ngoài dự kiến?
9. Có startup failure bị bỏ qua?
10. Có vô tình dùng `withUserConfiguration` cho auto-config?

Nếu chỉ smoke test fail, kiểm imports/discovery/package scanning và full app environment trước khi thay logic chính.

## 17. Trật tự đăng ký bean và quyền override

Một auto-configuration tốt thường cung cấp defaults, không áp đặt user choice. `@ConditionalOnMissingBean` cho phép user khai báo bean custom theo type. Một số điểm cần ghi nhớ:

- Condition dựa trên **bean definitions đã được xử lý**, không phải kiểm lại vĩnh viễn sau mọi registrations.
- User configuration cần được đăng ký trước auto-config để back-off hoạt động đúng theo pattern Boot.
- `AutoConfigurations.of` sắp candidates theo semantics auto-config; đừng dùng raw class array order làm hợp đồng.
- Bean `@Primary` hoặc `@Qualifier` giải quyết selection khi nhiều candidates, nhưng **không phải thay thế** cho back-off semantics.
- `spring.main.allow-bean-definition-overriding=true` cho phép một số bean definitions trùng name được ghi đè, không đảm bảo đúng behavior theo type.
- Trong multi-module projects, dependency graph và imports file có thể thay đổi khi thêm starter khác; nên test tổ hợp liên quan và failure path.
- `@ConditionalOnSingleCandidate` có thể xem primary bean và candidate selection, cần test nhiều beans khi dùng.

### Bẫy method return type

Ví dụ:

~~~java
@Bean
Object externalClient() {
    return new VendorClient();
}
~~~

Khi Spring đánh giá `@ConditionalOnBean(VendorClient.class)` dựa trên metadata bean definition, nó có thể không thấy chính xác type trả về do signature quá chung. Nên khai báo return type cụ thể nhất phù hợp:

~~~java
@Bean
VendorClient externalClient() {
    return new VendorClient();
}
~~~

Đây là snippets minh họa, **chưa có class VendorClient**, không thuộc project chạy được. Khi optional class chưa có trên classpath, cần tách nested configuration như phần 8 thay vì để signature gây NoClassDefFoundError.

## 18. `@ConfigurationProperties` và validation trong auto-config tests

Project mẫu dùng `@Value` cho prefix để giảm source size. Với starter thực, một nhóm properties nên có type-safe `@ConfigurationProperties`:

~~~java
@ConfigurationProperties(prefix = "demo.notify")
public record NotifyProperties(
        boolean enabled,
        String prefix,
        Duration timeout) {
}
~~~

Đây là snippet API tổng quát, **không phải project runnable**. Khi dùng trong auto-configuration, cần đăng ký/bind properties qua `@EnableConfigurationProperties(NotifyProperties.class)` hoặc cơ chế binding phù hợp; có thể dùng `@Validated`, `@NotBlank`, `@DurationUnit`, cấu hình defaults và validation dependencies.

Các cases quan trọng:

1. Không có property: default được áp dụng theo contract.
2. `prefix=TEST`: bind đúng.
3. `timeout=250ms`: bind Duration đúng đơn vị.
4. `timeout=not-a-duration`: fail startup với exception binding phù hợp.
5. `prefix=""` nếu forbidden: fail validation.
6. Bean chưa được tạo khi feature disabled: properties có cần validate không?
7. Config overlaid từ profiles/ENV có precedence đúng khi chạy app thật?
8. Metadata của custom properties được generate để IDE hỗ trợ?
9. Không dùng namespace `spring.*` cho keys của third-party starter; chọn prefix riêng do team sở hữu.

**Đừng dùng một runner test với property bind thành công rồi coi như đã kiểm ConfigData/profile precedence ở full SpringApplication.** Khi tính năng phụ thuộc `application.yml`, bootstrap/profile loading, nên có thêm smoke/integration tests.

## 19. Simulating web and reactive contexts

Khi auto-config có:

~~~java
@ConditionalOnWebApplication(
    type = ConditionalOnWebApplication.Type.SERVLET)
~~~

thì một **non-web** `ApplicationContextRunner` sẽ không match. Đây là behavior đúng, không phải bug. Dùng:

~~~java
new WebApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        WebAdapterAutoConfiguration.class))
    .run(context -> {
        // Assert servlet-specific beans.
    });
~~~

Snippet này cần `WebAdapterAutoConfiguration` và web dependencies, **không thuộc project runnable**. Với WebFlux/reactive:

~~~java
new ReactiveWebApplicationContextRunner()
    .withConfiguration(AutoConfigurations.of(
        ReactiveAdapterAutoConfiguration.class))
    .run(context -> {
        // Assert reactive-specific beans.
    });
~~~

Việc tạo một web context và có servlet classes trên classpath không tự động kiểm HTTP request handling, filters, CORS hay network server ports. Nếu muốn kiểm endpoints, dùng MockMvc/WebTestClient/real HTTP tests phù hợp. Runner ở đây chỉ nhằm kiểm **conditional bean registration**.

### Classpath distinctions

`@ConditionalOnWebApplication` không đồng nghĩa `@ConditionalOnClass(DispatcherServlet.class)`. Có library servlet class nhưng context không phải servlet web app thì web condition có thể không match. Ngược lại, multi-stack apps có cả MVC và WebFlux trên classpath cần hiểu lựa chọn application type của Spring Boot; test context cần phản ánh đúng runtime scenario.

## 20. Kiểm configuration exclusions

Trong Spring Boot, người dùng có thể exclude auto-configurations qua:

~~~java
@SpringBootApplication(
    exclude = NotifyAutoConfiguration.class)
class SomeApplication {
}
~~~

Đây là snippet minh họa; class có thể không chạy độc lập. Exclude thuộc application auto-configuration discovery, **không giống** việc bỏ class khỏi `AutoConfigurations.of` trong runner. Test runner chỉ nạp candidates bạn truyền; nếu bỏ class đi, bean biến mất là một điều hiển nhiên, chưa chứng minh `@SpringBootApplication(exclude=...)` của app thật hoạt động đúng.

Nếu starter có requirement “người dùng có thể exclude”, hãy thêm một Boot startup integration test riêng với exclude và assert không có bean. Khi chạy full Boot app, các auto-config khác có thể phụ thuộc bean đó; cần kiểm hậu quả của exclude với bean graph, không chỉ một class.

## 21. Auto-configuration metadata vs imports

Hai tài nguyên dễ nhầm:

| Tài nguyên | Mục đích |
| --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Liệt kê auto-configuration classes để Boot khám phá |
| `META-INF/spring-autoconfigure-metadata.properties` | Metadata tối ưu filter early theo conditions, thường được annotation processor tạo |
| `META-INF/spring-configuration-metadata.json` | Hỗ trợ IDE/configuration property metadata |
| `META-INF/spring.factories` | Cơ chế metadata đa mục đích có lịch sử; **không dùng làm chỗ đăng ký @AutoConfiguration Boot 3.3** |
| `application.yml`/`application.properties` | Giá trị configuration của app, không phải list class auto-config |

Một runner explicit có thể pass dù **không có imports file**; vì vậy smoke test trong bài bảo vệ registration. Tương tự, thiếu auto-config metadata tối ưu thường không tự ngăn auto-configuration hoạt động (khi imports/conditions vẫn đúng), nhưng có thể ảnh hưởng hiệu năng startup.

### Vì sao phải kiểm packaged JAR?

Khi library được publish, resources có thể bị đóng gói sai, bị merge sai trong shaded JAR hoặc lọc bởi build pipeline. Developer test trong source module có thể nhìn thấy imports file nhưng consumer dependency không có. Với starter production:

- Build artifact.
- Liệt kê JAR contents hoặc dùng consumer app minimal.
- Kiểm auto-config classes được discovered mà không cần import thủ công.
- Kiểm properties metadata/resource paths sau packaging.
- Kiểm conditional dependencies được đánh dấu optional đúng và library absent behavior an toàn.
- Kiểm Boot versions supported theo release matrix.

Không cần mở trực tiếp packaged JAR trong bài Step 4 này; đây là một **bài tập CI mở rộng**, không phải phần connector Google Sheets.

## 22. Không tạo tác động phụ trong config test

`ApplicationContextRunner` tạo và đóng context; nếu auto-config tạo thread pools, JDBC clients, HTTP clients, cloud SDK hoặc broker connections, mỗi test có thể mở tài nguyên thật, làm suite chậm hoặc phụ thuộc môi trường. Để tests có tính cô lập:

1. Khi kiểm conditional bean registration, chọn implementation **in-memory** hoặc mock/fake ở boundary không cần I/O.
2. Với bean tạo connection bắt buộc, có thể dùng test-specific fake connector hoặc Testcontainers với scope rõ.
3. Không để runner lấy credentials thật từ environment CI; inject test properties.
4. Kiểm bean destruction `@PreDestroy`/`AutoCloseable` khi có lifecycle resources.
5. Tránh caching static clients giữa contexts.
6. Không mutate `System.setProperty` rồi quên restore.
7. Nếu cần external system, tách **condition tests** nhanh khỏi **integration tests** chậm.
8. Không để user configuration gọi production endpoint trong `@Bean`.
9. Dùng diagnostics khi startup fail, không auto retry vô hạn.
10. Khi app có metrics/tracing exporters, tắt hoặc redirect tới fake test collector.

Lab dùng `NotificationClient` như một formatter không network để mọi condition test chạy offline.

## 23. Bẫy context hierarchy và `@ConditionalOnBean`

`ApplicationContextRunner.withParent(...)` có thể tạo context hierarchy. Bean conditions có tham số `search` xác định cách tìm parent/ancestors. Ví dụ một parent context đã đăng ký `NotificationClient`, child auto-config có thể back off, tùy `SearchStrategy`.

Nếu starter được dùng trong hệ thống có parent/child contexts (web management contexts, test context hierarchies), cần test:

- Bean cùng type ở parent, child không có.
- Có `SearchStrategy.CURRENT` vs `SearchStrategy.ALL` theo contract.
- Bean cùng name nhưng khác type trong child.
- Một primary bean ở parent và một regular bean ở child.
- Conditions có kiểm ancestor đúng không?
- Khi child chỉ thấy bean qua parent, downstream dependency injection dùng bean nào?
- `@ConditionalOnSingleCandidate` behavior khi có multiple candidates.

**Không mở rộng lab này sang hierarchy nếu feature chưa yêu cầu**; thêm tests tương ứng khi sản phẩm thật dùng multi-context architecture.

## 24. Anti-patterns và cách sửa

### Anti-pattern A — Chỉ kiểm không có exception

~~~java
runner.run(context -> {
    assertThat(context).hasNotFailed();
});
~~~

Điều này không chứng minh default client đã tồn tại, prefix đã bind đúng hoặc custom bean back-off. Sửa bằng `hasSingleBean` + functional behavior.

### Anti-pattern B — Auto-config được nạp như user config

~~~java
new ApplicationContextRunner()
    .withUserConfiguration(
        NotifyAutoConfiguration.class);
~~~

Có thể bỏ qua ordering semantics và làm bean condition khác runtime. Dùng `withConfiguration(AutoConfigurations.of(...))`.

### Anti-pattern C — Tắt tất cả conditions để test pass

Loại bỏ `@ConditionalOnClass` hoặc `@ConditionalOnMissingBean` có thể khiến full context load thành công trong một môi trường cụ thể, nhưng sẽ fail trong consumer classpath khác. Tạo negative tests thay vì xóa guard.

### Anti-pattern D — Chỉ test mặc định

~~~java
runner.run(ctx ->
    assertThat(ctx).hasSingleBean(NotificationClient.class));
~~~

Nếu default có bean nhưng `enabled=false` vẫn tạo, test không phát hiện. Thêm property false, user override, missing class và meter disabled.

### Anti-pattern E — Dùng live system properties

~~~java
System.setProperty("demo.notify.enabled", "false");
~~~

JVM-global state có thể rò sang tests khác và không được restore khi exception. Dùng `runner.withPropertyValues("demo.notify.enabled=false")` cho từng case.

### Anti-pattern F — Filter class sai

Nếu bạn filter `org.springframework.*` thay vì optional library class, test fail vì framework thiếu chứ không chứng minh guard của starter. Chỉ filter đúng marker/third-party type cần kiểm.

### Anti-pattern G — Assert bean name, không kiểm type

~~~java
assertThat(context).hasBean("notificationClient");
~~~

Một bean khác cùng type có thể cùng tồn tại, gây ambiguity. Dùng `hasSingleBean(NotificationClient.class)` và, với user override, `isSameAs(customBean)`.

### Anti-pattern H — Bật bean overriding thay back-off

`spring.main.allow-bean-definition-overriding=true` không tự bảo vệ user customization contract. Sửa `@ConditionalOnMissingBean` và kiểm cả custom/default branches.

### Anti-pattern I — Assert exact condition report text

Các log message của OnBean/OnClass conditions có thể đổi qua Spring Boot patch/minor versions. Dùng report để chẩn đoán; assertions dài hạn nên kiểm **bean graph/behavior**.

### Anti-pattern J — Không kiểm imports file

Runner tests explicit `of` vẫn xanh nếu resource discovery thiếu. Thêm full Boot smoke test hoặc minimal consumer integration test.

### Anti-pattern K — Muốn kiểm servlet condition bằng runner thường

`ApplicationContextRunner` non-web không match `@ConditionalOnWebApplication(SERVLET)`. Dùng `WebApplicationContextRunner` và dependencies web tương ứng.

### Anti-pattern L — Nói đã kiểm native image

Spring Boot docs nói ApplicationContextRunner không hoạt động trong native image tests. Nếu app phải dùng GraalVM native, thêm AOT/native smoke tests thích hợp.

## 25. Bài tập thực hành

**Bài A — bỏ matchIfMissing:** Trong `NotifyAutoConfiguration`, tạm đổi `matchIfMissing=false`. Test default phải fail, explicit enabled=true vẫn pass. Giải thích semantics absent property.

**Bài B — đổi havingValue:** Bỏ `havingValue="true"` nhưng giữ enabled property. Test `enabled=yes` sẽ cho thấy sự khác nhau giữa default property matching và value-specific matching.

**Bài C — đổi prefix:** Tạm thay `demo.notify.prefix` bằng `demo.notify.label` trong `@Value`, chạy test custom prefix. Assertion `TEST::message` phải fail.

**Bài D — xóa @ConditionalOnMissingBean:** Runner với `CustomUserConfiguration` sẽ có nhiều NotificationClient beans hoặc startup failure. Phân tích vì sao user override không còn an toàn.

**Bài E — thêm bean user:** Viết một class `@Configuration(proxyBeanMethods=false)` có `@Bean NotificationClient` trả `CUSTOM::...`. Dùng `withUserConfiguration` và verify single bean + observer sample.

**Bài F — với withBean:** Đăng ký `NotificationClient` bằng `runner.withBean(...)` nhưng không tạo @Configuration; kiểm default back-off.

**Bài G — giả lập thiếu SDK:** Filter `OptionalTransport` bằng `FilteredClassLoader`. Nếu xóa `@ConditionalOnClass` khỏi auto-config, kiểm test thay đổi ra sao.

**Bài H — thứ tự auto-configs:** Tạm bỏ `after=NotifyAutoConfiguration.class` và đảo order arguments như runner gốc. Quan sát điều kiện observer; xác định khi nào thứ tự ảnh hưởng bean definition.

**Bài I — meter-enabled false:** Chỉ tắt subfeature; bảo đảm client vẫn tồn tại. Viết test khác bật meter true.

**Bài J — disabled default + custom bean:** Chứng minh `demo.notify.enabled=false` không tự xóa user bean. Nếu contract thật muốn disabled toàn bộ, thay đổi conditions ở observer và cập nhật tests.

**Bài K — missing imports:** Xóa/đổi path `AutoConfiguration.imports` trong một branch. Runner test có thể vẫn xanh, nhưng `BootAutoConfigurationSmokeTest` phải đỏ. Hoàn nguyên file.

**Bài L — packaging:** Tạo một Gradle multi-module demo gồm `notify-autoconfigure`, `notify-starter` và `sample-consumer`, chạy consumer test dùng JAR như dependency và kiểm auto-discovery.

**Bài M — report:** Bật `ConditionEvaluationReportLoggingListener.forLogLevel(INFO)` cho enabled=false, quan sát OnPropertyCondition report. Bật lại và so sánh. Không assert exact log text.

**Bài N — startup failure:** Tạo một @Bean cố ý throw để `context.getStartupFailure()` có root cause; test chỉ nhận startup failure là expected khi case đó được thiết kế.

**Bài O — @ConfigurationProperties:** Thêm properties class dùng Duration và validation, viết cases valid/invalid. Kiểm binder failure khi value không đúng format.

**Bài P — servlet branch:** Tạo `@ConditionalOnWebApplication(SERVLET)` auto-config riêng, dùng `WebApplicationContextRunner` và so sánh với `ApplicationContextRunner`.

**Bài Q — parent context:** Cấp NotificationClient ở parent, kiểm `@ConditionalOnMissingBean(search=...)` và downstream injection theo strategy mong muốn.

**Bài R — bean return type:** Đổi @Bean return type từ interface phù hợp sang Object, quan sát OnBean conditions. Viết regression test để chặn method signatures quá chung.

**Bài S — test no native:** Lên kế hoạch AOT/native smoke test riêng; không coi runner tests là native coverage.

**Bài T — manual mutation:** Tạm phá property/backoff/class guard/imports/ordering, xác nhận từng nhóm test fail có ý nghĩa; hoàn nguyên tất cả.

## 26. Checklist trước khi merge auto-configuration

- [ ] Auto-config classes có `@AutoConfiguration` đúng Boot version?
- [ ] Các classes được đăng ký trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`?
- [ ] Package auto-config không bị component scan tình cờ?
- [ ] Runner dùng `withConfiguration(AutoConfigurations.of(...))`?
- [ ] User configs dùng `withUserConfiguration`, không gộp nhầm với auto-config?
- [ ] Có test default property absent và explicit true/false?
- [ ] `@ConditionalOnProperty` có `havingValue/matchIfMissing` khớp contract?
- [ ] Configurable prefix/timeout giá trị thực được assertion?
- [ ] Optional classpath guard có negative case với `FilteredClassLoader`?
- [ ] Default bean có `@ConditionalOnMissingBean` để user có thể override?
- [ ] Có `hasSingleBean` và instance identity cho override?
- [ ] Downstream auto-config có `@ConditionalOnBean` và ordering rõ?
- [ ] Có test tắt subfeature không vô tình tắt core feature?
- [ ] Có test user bean tồn tại khi default auto-config disabled?
- [ ] Context startup success/failure được assert theo ý định?
- [ ] Có xem ConditionEvaluationReport khi negative case khó hiểu?
- [ ] Có test chỉ một auto-config class khi muốn isolate condition?
- [ ] Có test nhóm liên quan để bảo vệ after/before ordering?
- [ ] Có Boot smoke test bảo vệ imports discovery ngoài runner explicit?
- [ ] Nếu build starter, có consumer app test dùng JAR như dependency?
- [ ] Không bật global bean overriding để che duplicate?
- [ ] Không dùng system properties thay runner config gây rò test state?
- [ ] Nếu auto-config phụ thuộc servlet/reactive context, có web runner phù hợp?
- [ ] Tests không mở external network/DB thật ngoài phạm vi?
- [ ] Không khẳng định runner coverage cho native image?
- [ ] JDK17/Boot3.3.5/BOM dependencies tương thích?
- [ ] Có negative tests hoặc mutation test chứng minh guard hoạt động?
- [ ] Không viết mã bất định/placeholder trong project runnable?
- [ ] CI report cho thấy JUnit test methods chạy thực tế?

## 27. Tài liệu tham khảo

Các link bên dưới là tài liệu chính thức Spring Boot; code mẫu cố định **Spring Boot 3.3.5**, trong khi trang reference 3.3 có thể hiển thị patch mới nhất của cùng minor line. Khi dùng Spring Boot 3.4+, 3.5+ hoặc 4.x, kiểm lại API/module names và condition semantics phù hợp với BOM thực tế.

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): conventions, conditional annotations, auto-config imports, `ApplicationContextRunner`, `AutoConfigurations.of`, `FilteredClassLoader`, condition evaluation reporting, ordering.
- [Spring Boot 3.3 — AutoConfigurations Java API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html): `of(Class<?>...)`, sorting and merge semantics.
- [Spring Boot 3.3 — ApplicationContextRunner Java API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html): test context runner và methods.
- [Spring Boot 3.3 — ConditionEvaluationReportLoggingListener](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): factory `forLogLevel(LogLevel.INFO)`.
- [Spring Boot 3.3 — @ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): `havingValue`, `matchIfMissing`, prefix/name.
- [Spring Boot 3.3 — @ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): bean conditions/back-off.
- [Spring Boot 3.3 — @ConditionalOnClass](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html): missing classpath behavior and class metadata.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@SpringBootTest`, focused context tests and test slices.
- [Spring Framework — @Configuration and @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/basic-concepts.html): registration and bean factories.
- [JUnit Jupiter — User Guide](https://docs.junit.org/5.10.2/user-guide/): test methods and lifecycle.
- [AssertJ — Assertions](https://assertj.github.io/doc/): assertThat, root causes, instance identity.

**Ghi nhớ:** `AutoConfigurations.of` dành cho **auto-configuration classes** trong `ApplicationContextRunner`, còn `withUserConfiguration` dùng cho cấu hình ứng dụng muốn override defaults. Hãy kiểm cả **có bean**, **không có bean**, **đúng instance user bean**, **giá trị property**, **classpath guard**, **dependency ordering** và **startup failure**. Runner tests nhanh, nhưng không thể thay full Boot smoke test kiểm **AutoConfiguration.imports**; kết hợp cả hai để ngăn auto-configuration regression trong starter/library.
