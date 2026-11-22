# Phân biệt giai đoạn phân tích cấu hình và giai đoạn đăng ký bean trong Spring Boot

> **Bối cảnh:** Spring Boot — auto-configuration, nhóm **Cơ chế điều kiện**. Bài trình bày sự khác biệt giữa lúc Spring **phân tích một configuration class** và lúc Spring **đăng ký bean definition**, giải thích khi nào điều kiện có thể chặn cả lớp cấu hình, khi nào chỉ chặn một bean, vì sao `@ConditionalOnBean`/`@ConditionalOnMissingBean` phải xét những bean đã biết, và cách viết kiểm thử xác nhận điều đó. Ví dụ hoàn chỉnh sử dụng Java 17, Maven và Spring Boot 3.5.7.

## 1. Câu trả lời ngắn gọn

Trong quá trình khởi tạo Spring ApplicationContext, có ít nhất ba sự kiện **khác nhau**:

1. **Phân tích cấu hình (configuration parsing):** Spring đọc nguồn cấu hình, nhận diện `@Configuration`, `@Import`, `@ComponentScan`, các cấu hình lồng nhau và điều kiện có thể quyết định liệu **có nên tiếp tục phân tích một configuration class** hay không.
2. **Đăng ký bean definition (bean definition registration):** Spring chuyển thông tin từ các class cấu hình và `@Bean` method thành các định nghĩa bean trong bean factory. Các điều kiện cần nhìn thấy **bean definitions đã đăng ký** có thể được xét ở giai đoạn này.
3. **Khởi tạo bean instance (bean instantiation):** Spring gọi factory method hoặc constructor để tạo đối tượng, inject dependency và chạy lifecycle callback. Đối với singleton không lazy, điều này thường diễn ra khi context refresh, **sau** phần lớn công việc đọc và đăng ký bean definition.

Hai giai đoạn đầu là chủ đề chính. **Đăng ký bean definition không đồng nghĩa tạo bean instance.** Một bean definition có thể tồn tại dù object chưa được khởi tạo; một class `@AutoConfiguration` có thể được xét nhưng cuối cùng không đăng ký bean ứng dụng nào vì condition không khớp.

Spring Framework cho phép một điều kiện tự khai báo thời điểm thích hợp thông qua `ConfigurationCondition.ConfigurationPhase`, gồm hai giá trị:

- `PARSE_CONFIGURATION`: áp dụng trong khi phân tích configuration class.
- `REGISTER_BEAN`: áp dụng khi đăng ký bean definition.

Cặp giá trị này không thay thế toàn bộ lifecycle của ApplicationContext; đây là **hai thời điểm đánh giá condition trong quá trình xử lý configuration**.

## 2. Tại sao cần tách hai giai đoạn?

Giả sử thư viện cung cấp mặc định:

```java
@Bean
@ConditionalOnMissingBean(MessagePort.class)
public DefaultMessagePort defaultMessagePort() {
    return new DefaultMessagePort();
}
```

Đây là **đoạn minh họa**, cần định nghĩa `MessagePort`, `DefaultMessagePort` và một class cấu hình mới chạy được. Để quyết định đăng ký bean `defaultMessagePort`, Spring Boot phải biết đã có bean nào cùng kiểu `MessagePort` hay chưa.

Ngay khi Spring lần đầu đọc một class configuration, chưa chắc tất cả các định nghĩa bean do ứng dụng khai báo đã được xử lý. Nếu kiểm tra “missing bean” quá sớm, Spring có thể kết luận sai rằng chưa có bean của người dùng và đăng ký một mặc định gây trùng lặp.

Ngược lại, điều kiện kiểm tra sự có mặt của một API trên classpath, ví dụ `@ConditionalOnClass(name="com.vendor.sdk.Client")`, thường có thể loại bỏ một class cấu hình sớm mà không cần chờ bean definitions được đăng ký. Loại bỏ sớm giúp tránh xử lý sâu cấu hình gắn với thư viện không có mặt.

Đây là lý do không thể nói mọi `@Conditional` đều “chạy cùng một lúc”.

## 3. Tổng quan pipeline cấu hình

Sơ đồ dưới đây là mô hình khái niệm; Spring có nhiều vòng và bộ xử lý phụ tùy nguồn bean, chẳng hạn registry post-processors, component scanning và import selectors.

```text
SpringApplication.run(...)
         |
         v
Tạo Environment, chuẩn bị ApplicationContext
         |
         v
Đọc nguồn cấu hình ứng dụng
         |
         v
ConfigurationClassPostProcessor
         |
         +-- ConfigurationClassParser
         |      |
         |      +-- nhận diện configuration class / @Import / @ComponentScan
         |      +-- xét các condition ở PARSE_CONFIGURATION khi phù hợp
         |      +-- loại cấu hình không đủ điều kiện để phân tích tiếp
         |      +-- chọn/đọc auto-configuration đã được import
         |
         +-- ConfigurationClassBeanDefinitionReader
                |
                +-- xét các condition ở REGISTER_BEAN khi phù hợp
                +-- đăng ký bean definition từ class / @Bean method
                +-- điều kiện bean có thể xét các definition đã biết
         |
         v
BeanFactoryPostProcessor / BeanPostProcessor và các bước khác
         |
         v
Khởi tạo singleton, inject dependency, lifecycle, runner...
```

Các tên `ConfigurationClassPostProcessor`, `ConfigurationClassParser` và `ConfigurationClassBeanDefinitionReader` thuộc cơ chế xử lý cấu hình của Spring Framework; chúng giải thích nguồn gốc của sự phân biệt hai giai đoạn. Không nên coi sơ đồ là một cam kết thứ tự tuyệt đối cho mọi loại bean/extension hay cho mọi phiên bản Spring.

### Điều phải hiểu về “parse”

Phân tích cấu hình không chỉ đơn giản đọc text của một file Java. Java class đã được biên dịch; Spring dùng metadata annotation/class để phát hiện cấu hình, các import, scan và điều kiện. Một condition ở giai đoạn phân tích có thể khiến Spring **không tiếp tục xử lý** nội dung của một configuration class nhất định.

### Điều phải hiểu về “register”

Đăng ký định nghĩa bean không nhất thiết làm chạy code business trong method `@Bean` ngay thời điểm đó. Spring có thể ghi lại tên method, kiểu trả về và các metadata khác để gọi method khi cần tạo instance. Vì thế điều kiện theo bean cần dựa trên định nghĩa/metadata khả dụng, không thể giả định mọi bean đã có instance.

### Điều phải hiểu về “instantiate”

Mặc dù nhiều singleton được tạo trong lần refresh, một bean đánh dấu `@Lazy` có thể được tạo muộn hơn. Scope prototype tạo instance theo yêu cầu. Do đó “đăng ký” và “khởi tạo” không được nhập làm một bước.

## 4. API ConfigurationCondition nói chính xác điều gì?

Spring Framework có interface:

```java
org.springframework.context.annotation.ConfigurationCondition
```

Nó mở rộng interface `Condition` và thêm phương thức:

```java
ConfigurationPhase getConfigurationPhase();
```

Đây là **chữ ký rút gọn**, không phải class Java độc lập. Enum lồng bên trong interface có các giá trị `PARSE_CONFIGURATION` và `REGISTER_BEAN`.

Khi một condition implements `ConfigurationCondition`, nó công bố **phase mà Spring nên xét condition đó**. Phương thức `matches(ConditionContext, AnnotatedTypeMetadata)` vẫn quyết định điều kiện đúng hay sai.

Ví dụ cú pháp rút gọn:

```java
public final class ParseGate implements ConfigurationCondition {
    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return true;
    }
}
```

Đây là **fragment**, cần thêm các import của Spring. Class hoàn chỉnh sẽ xuất hiện ở phần thực hành.

**Quan trọng:** `@Conditional` bản thân chỉ liệt kê class condition; **không ghi phase**. Phase có thể đến từ việc condition implements `ConfigurationCondition`. Những condition chỉ implements `Condition` không có ràng buộc phase chuyên biệt như vậy; Spring có thể đánh giá chúng tại các điểm xử lý tương ứng.

### Phase không phải thứ tự bean instance

Một condition `REGISTER_BEAN` không đồng nghĩa “chạy sau khi singleton được tạo”. Nó chỉ xác định giai đoạn xử lý **định nghĩa bean**. Một condition `PARSE_CONFIGURATION` có thể bị loại sớm nhưng điều đó không đồng nghĩa class Java bị xóa khỏi classpath.

## 5. Liên hệ với điều kiện Spring Boot

Các annotation tiện dụng của Spring Boot dựa trên hạ tầng `@Conditional`:

| Annotation/điều kiện | Thông tin cần đọc | Điểm đáng nhớ |
| --- | --- | --- |
| `@ConditionalOnClass` | Classpath/metadata lớp | Có thể lọc cấu hình sớm khi API phụ thuộc vắng mặt; thích hợp đặt ở class cấu hình. |
| `@ConditionalOnMissingClass` | Sự vắng mặt của class | Tương tự nhóm điều kiện classpath, không cần có bean instance. |
| `@ConditionalOnBean` | Những bean definitions/loại bean đã biết | Phụ thuộc việc bean phù hợp đã được xử lý khi condition chạy. |
| `@ConditionalOnMissingBean` | Sự thiếu bean phù hợp ở thời điểm đánh giá | Dùng cho mặc định có cơ chế **back-off**, đặc biệt trong auto-configuration. |
| `@ConditionalOnSingleCandidate` | Tập bean ứng viên phù hợp | Thường cần biết các bean definitions đã đăng ký. |
| `@ConditionalOnProperty` | `Environment`/property | Có thể áp dụng trên class hoặc method; không nên tự động quy mọi property condition vào một phase bất biến. |
| `@Profile` | Active profiles | Chặn định nghĩa theo profile; không có nghĩa bean được tạo rồi mới loại bỏ. |

Trong Spring Boot, các condition dựa trên classpath và các condition dựa trên bean không nhất thiết cùng thời điểm xử lý. Đặc biệt:

- Điều kiện lớp như `@ConditionalOnClass` phù hợp với quyết định **có nên xem xét một cấu hình yêu cầu một SDK nhất định**.
- Các condition dựa trên bean như `@ConditionalOnBean` và `@ConditionalOnMissingBean` cần sự tồn tại (hoặc vắng mặt) của những **bean definitions đã được xử lý**; tài liệu Boot cảnh báo các condition này chỉ thấy những bean đã được xét tới thời điểm đó.
- Điều kiện trên **configuration class** có thể ảnh hưởng toàn bộ bean definitions bên trong; điều kiện trên **`@Bean` method** chủ yếu ảnh hưởng bean từ method đó.
- Không đồng nhất vị trí annotation với phase một cách máy móc: phase do **loại condition và hạ tầng xử lý** quyết định. Trong ví dụ dưới đây, phase được khai báo tường minh để minh họa không mập mờ.

## 6. Ví dụ runnable: một cổng ở parse phase, một cổng ở register phase

Ta xây dựng một Spring Boot application có một class auto-configuration. Nó khai báo:

- `@Conditional(ParseGate.class)` **trên class** với phase `PARSE_CONFIGURATION`: nếu property `demo.phase.parse.enabled=false`, class cấu hình bị chặn từ sớm.
- `@Conditional(RegisterGate.class)` **trên `@Bean` method** với phase `REGISTER_BEAN`: class có thể đã được phân tích nhưng bean mặc định không được đăng ký nếu property `demo.phase.register.enabled=false`.
- `@ConditionalOnMissingBean(MessagePort.class)` trên cùng method: mặc định chỉ được đăng ký khi ứng dụng chưa cung cấp một bean `MessagePort` tương đương.

Ví dụ cố ý tạo **các condition tự viết có phase rõ ràng** để tách hai giai đoạn. Nó không khẳng định toàn bộ condition có sẵn của Spring Boot dùng chính xác các class/gates này.

### 6.1. Cấu trúc project

```text
configuration-phases-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/phase/
    │   │   ├── api/MessagePort.java
    │   │   ├── autoconfigure/DefaultMessagePort.java
    │   │   ├── autoconfigure/ParseGate.java
    │   │   ├── autoconfigure/RegisterGate.java
    │   │   ├── autoconfigure/PhaseAutoConfiguration.java
    │   │   └── app/PhaseApplication.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/dev/example/phase/check/
        ├── PhaseAutoConfigurationTest.java
        └── PhaseApplicationTest.java
```

Application class nằm trong `dev.example.phase.app`. Auto-configuration nằm ở nhánh package khác và được nạp qua file imports, không phụ thuộc component scan ứng dụng.

### 6.2. Maven POM

`pom.xml`:

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
    <groupId>dev.example</groupId>
    <artifactId>configuration-phases-demo</artifactId>
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

Không có web server hay database trong demo, giúp tập trung vào vòng đời cấu hình của Spring.

### 6.3. Định nghĩa hợp đồng bean

`src/main/java/dev/example/phase/api/MessagePort.java`:

```java
package dev.example.phase.api;

@FunctionalInterface
public interface MessagePort {
    String message();
}
```

Bean mặc định tại `src/main/java/dev/example/phase/autoconfigure/DefaultMessagePort.java`:

```java
package dev.example.phase.autoconfigure;

import dev.example.phase.api.MessagePort;

public final class DefaultMessagePort implements MessagePort {
    @Override
    public String message() {
        return "from-default";
    }
}
```

Không dùng `@Component` vì bean sẽ được đăng ký bằng `@Bean` có điều kiện.

### 6.4. Condition ở parse phase

`src/main/java/dev/example/phase/autoconfigure/ParseGate.java`:

```java
package dev.example.phase.autoconfigure;

import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class ParseGate implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment().getProperty(
            "demo.phase.parse.enabled",
            Boolean.class,
            true
        );
    }
}
```

Khi `demo.phase.parse.enabled=false`, condition không khớp tại giai đoạn parsing nên Spring không tiếp tục xử lý cấu hình có annotation tương ứng. Nó **không tạo một bean rồi xóa bean đó**.

Giá trị thứ ba của `getProperty` là default `true`, vì vậy không khai báo property sẽ cho phép cấu hình. Thực hành production nên kiểm tra lỗi đánh máy hoặc giá trị boolean không hợp lệ theo chính sách của ứng dụng.

### 6.5. Condition ở registration phase

`src/main/java/dev/example/phase/autoconfigure/RegisterGate.java`:

```java
package dev.example.phase.autoconfigure;

import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class RegisterGate implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    ) {
        return context.getEnvironment().getProperty(
            "demo.phase.register.enabled",
            Boolean.class,
            true
        );
    }
}
```

Ở đây, method `matches(...)` kiểm tra property giống cách của `ParseGate`, nhưng **thời điểm đánh giá** khác do `getConfigurationPhase()`. Hai condition được cố tình tách thành hai class để minh họa thiết kế.

### 6.6. Class auto-configuration kết hợp hai phase

`src/main/java/dev/example/phase/autoconfigure/PhaseAutoConfiguration.java`:

```java
package dev.example.phase.autoconfigure;

import dev.example.phase.api.MessagePort;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration
@Conditional(ParseGate.class)
public class PhaseAutoConfiguration {

    @Bean
    @Conditional(RegisterGate.class)
    @ConditionalOnMissingBean(MessagePort.class)
    public DefaultMessagePort defaultMessagePort() {
        return new DefaultMessagePort();
    }
}
```

**Đọc theo thứ tự ý nghĩa:**

1. Spring Boot biết đến `PhaseAutoConfiguration` vì imports file khai báo class này.
2. Trong giai đoạn xử lý cấu hình, `ParseGate` phải cho phép class tiếp tục.
3. Trong giai đoạn đăng ký bean method, `RegisterGate` phải cho phép đăng ký `defaultMessagePort`.
4. `@ConditionalOnMissingBean(MessagePort.class)` chỉ cho phép mặc định nếu bean `MessagePort` thích hợp chưa tồn tại trong ngữ cảnh đánh giá.
5. Nếu cả ba điều kiện khớp, Spring đăng ký bean definition với chữ ký `DefaultMessagePort`, rồi container mới tạo instance theo lifecycle.

**Phân biệt phạm vi annotation:** Nếu `ParseGate` ở cấp class không khớp, mọi method bên trong class này đều không được xử lý theo đường đó. Nếu chỉ `RegisterGate` trên method không khớp, class vẫn là một configuration được phân tích; một method `@Bean` khác không mang gate đó vẫn có thể đóng góp bean.

### 6.7. Đăng ký ứng viên auto-configuration

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung chính xác:

```text
dev.example.phase.autoconfigure.PhaseAutoConfiguration
```

Đặt file imports dưới `src/main/resources` để Maven đưa nó vào classpath runtime. Không thêm `@ComponentScan` của application lên package `autoconfigure`; mục tiêu là thử đúng con đường auto-configuration.

### 6.8. Application có thể chạy từ command line

`src/main/java/dev/example/phase/app/PhaseApplication.java`:

```java
package dev.example.phase.app;

import dev.example.phase.api.MessagePort;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class PhaseApplication {

    public static void main(String[] args) {
        try (ConfigurableApplicationContext context =
                 SpringApplication.run(PhaseApplication.class, args)) {

            MessagePort port =
                context.getBeanProvider(MessagePort.class).getIfAvailable();

            System.out.println("port.present=" + (port != null));
            System.out.println(
                "port.message=" + (port == null ? "none" : port.message())
            );
        }
    }
}
```

Chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q spring-boot:run
```

Hai dòng do chương trình in ra (bỏ qua log startup):

```text
port.present=true
port.message=from-default
```

Lúc này, parse gate và register gate đều mặc định `true`, chưa có bean `MessagePort` nào khác nên bean mặc định xuất hiện.

### 6.9. Thử tắt tại parse phase

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.phase.parse.enabled=false
```

Hai dòng ứng dụng in:

```text
port.present=false
port.message=none
```

**Giải thích:** `ParseGate` không khớp ngay trong quá trình phân tích `PhaseAutoConfiguration`. Configuration class không đóng góp phương thức `@Bean` vào quy trình tạo bean definitions theo nhánh này.

### 6.10. Thử tắt tại registration phase

```bash
mvn -q spring-boot:run -Dspring-boot.run.arguments=--demo.phase.register.enabled=false
```

Hai dòng ứng dụng in:

```text
port.present=false
port.message=none
```

Cùng kết quả **không có bean**, nhưng nguyên nhân khác: class auto-configuration có thể đã được parse, còn method `defaultMessagePort` bị ngăn đăng ký khi condition `REGISTER_BEAN` không khớp.

**Không nên dùng sự vắng mặt của bean để suy ra phase nào đã chặn nó.** Cần biết condition đặt ở đâu và/hoặc xem condition outcomes khi debug.

## 7. Bảng so sánh chi tiết hai phase

| Tiêu chí | PARSE_CONFIGURATION | REGISTER_BEAN |
| --- | --- | --- |
| Mục tiêu chính | Quyết định có tiếp tục phân tích một configuration class không | Quyết định có đăng ký định nghĩa bean tương ứng không |
| Thông tin sẵn có điển hình | Metadata annotation, classpath, environment và nguồn cấu hình hiện tại | Metadata cấu hình cùng bean definitions đã được đăng ký đến lúc đó |
| Ví dụ trong demo | `@Conditional(ParseGate.class)` ở cấp `PhaseAutoConfiguration` | `@Conditional(RegisterGate.class)` ở `defaultMessagePort()` |
| Khi điều kiện sai | Bỏ qua phân tích configuration class liên quan | Không đăng ký bean definition được bảo vệ |
| Đã tạo bean instance trước đó? | Không phải ý nghĩa của phase | Không phải ý nghĩa của phase |
| Có được đọc bean definitions không? | Không nên giả định mọi bean user đã sẵn có | Có thể dùng thông tin bean definitions đã biết; không bao hàm các bean sẽ xuất hiện sau |
| Trường hợp ứng dụng | Bỏ sớm cấu hình khi phụ thuộc không thỏa | Điều kiện phụ thuộc vào bean đã đăng ký hoặc yêu cầu riêng của bean method |

Điều kiện `@ConditionalOnProperty` có thể được gắn trên cả class lẫn method. Nó dùng Environment; bài học này không kết luận một annotation property luôn thuộc duy nhất một phase. Với condition tự viết, cách đúng để yêu cầu phase cụ thể là implements `ConfigurationCondition`.

## 8. Phân tích sâu: tại sao condition dựa trên bean còn phụ thuộc thứ tự?

Xét hai auto-configuration:

```java
@AutoConfiguration
class ProviderAutoConfiguration {
    @Bean
    MessagePort messagePort() {
        return () -> "provider";
    }
}

@AutoConfiguration(after = ProviderAutoConfiguration.class)
@ConditionalOnBean(MessagePort.class)
class ConsumerAutoConfiguration {
    @Bean
    MessageMonitor messageMonitor(MessagePort port) {
        return new MessageMonitor(port);
    }
}
```

**Đây là fragments minh họa**, cần định nghĩa `MessagePort`, `MessageMonitor`, imports và các import Java mới chạy độc lập.

Các điều kiện như `@ConditionalOnBean` không có khả năng “nhìn thấy tương lai”: nó chỉ có thể xét các bean đã được xử lý tại thời điểm condition chạy. Nếu cấu hình consumer được xem xét trước định nghĩa provider, condition có thể không khớp dù đến cuối quá trình startup sẽ có bean `MessagePort`.

Spring Boot cung cấp metadata thứ tự thông qua `@AutoConfiguration(after=...)`, `before`, `afterName`, `beforeName` và annotation ordering tương ứng. Ordering đảm bảo **thứ tự xử lý configuration**, không đảm bảo thứ tự tạo instance.

### Vì sao nên dùng @ConditionalOnMissingBean ở auto-configuration?

Trong luồng Spring Boot thông dụng, bean definitions do ứng dụng chủ động khai báo được xử lý trước auto-configuration. Khi Spring Boot xét `@ConditionalOnMissingBean(MessagePort.class)` trong auto-configuration, nó có cơ hội nhận biết user bean đã khai báo để **nhường chỗ**.

Ví dụ, nếu ứng dụng có:

```java
@Configuration(proxyBeanMethods = false)
class UserConfiguration {
    @Bean
    MessagePort userMessagePort() {
        return () -> "user";
    }
}
```

Đây là fragment độc lập với mã thực hành (chưa có package/import). Khi user bean đã được đăng ký, mặc định của auto-configuration có thể back off. Điều kiện đó **không xóa bean nào đã tồn tại**; nó ngăn việc đăng ký định nghĩa bean mặc định từ đầu.

Đặt `@ConditionalOnMissingBean` bừa bãi trong cấu hình thường có thể dẫn đến bất ngờ nếu cấu hình khác được đăng ký sau. Đây là lý do tài liệu Boot đặc biệt khuyên sử dụng các bean conditions loại này trong auto-configuration.

## 9. Kiểm thử hai giai đoạn và back-off

`ApplicationContextRunner` tạo context nhỏ để kiểm tra nhánh điều kiện mà không cần chạy cả ứng dụng. Các test sau có thể chạy cùng Maven POM ở trên.

File `src/test/java/dev/example/phase/check/PhaseAutoConfigurationTest.java`:

```java
package dev.example.phase.check;

import dev.example.phase.api.MessagePort;
import dev.example.phase.autoconfigure.DefaultMessagePort;
import dev.example.phase.autoconfigure.PhaseAutoConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class PhaseAutoConfigurationTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(PhaseAutoConfiguration.class)
            );

    @Test
    void registersDefaultWhenBothPhasesAllowIt() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(MessagePort.class);
            assertThat(context).hasSingleBean(DefaultMessagePort.class);
            assertThat(context.getBean(MessagePort.class).message())
                .isEqualTo("from-default");
        });
    }

    @Test
    void blocksConfigurationAtParsePhase() {
        runner.withPropertyValues("demo.phase.parse.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(MessagePort.class);
                assertThat(context).doesNotHaveBean(DefaultMessagePort.class);
            });
    }

    @Test
    void blocksDefaultBeanAtRegistrationPhase() {
        runner.withPropertyValues("demo.phase.register.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(MessagePort.class);
                assertThat(context).doesNotHaveBean(DefaultMessagePort.class);
            });
    }

    @Test
    void userBeanMakesMissingBeanConditionBackOff() {
        runner.withUserConfiguration(UserMessageConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(MessagePort.class);
                assertThat(context).doesNotHaveBean(DefaultMessagePort.class);
                assertThat(context.getBean(MessagePort.class).message())
                    .isEqualTo("from-user");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserMessageConfiguration {
        @Bean
        MessagePort userMessagePort() {
            return () -> "from-user";
        }
    }
}
```

Cấu hình dành cho test `UserMessageConfiguration` nằm trong package `dev.example.phase.check`, **không thuộc cây component scan của application** ở `dev.example.phase.app`. Nó chỉ được `withUserConfiguration(...)` đăng ký khi test nhánh back-off, tránh ảnh hưởng tình cờ tới các test khác.

### Test integration: xác minh đường nạp imports

File `src/test/java/dev/example/phase/check/PhaseApplicationTest.java`:

```java
package dev.example.phase.check;

import dev.example.phase.api.MessagePort;
import dev.example.phase.app.PhaseApplication;
import dev.example.phase.autoconfigure.DefaultMessagePort;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = PhaseApplication.class,
    properties = {
        "demo.phase.parse.enabled=true",
        "demo.phase.register.enabled=true"
    }
)
class PhaseApplicationTest {

    @Autowired
    ApplicationContext context;

    @Test
    void importsConfigurationFromClasspathResource() {
        assertThat(context.getBean(MessagePort.class))
            .isInstanceOf(DefaultMessagePort.class);
        assertThat(context.containsBean("defaultMessagePort")).isTrue();
    }
}
```

Chạy:

```bash
mvn -q test
```

Kỳ vọng **5 test pass** với file và mã nguồn như trên: 4 test `ApplicationContextRunner` và 1 test `@SpringBootTest`. Test thứ năm không dùng `AutoConfigurations.of(...)` để cung cấp cấu hình theo cách thủ công; nó khởi động `PhaseApplication` nhằm kiểm chứng file `AutoConfiguration.imports` thực sự được sử dụng. Các ví dụ test không khẳng định số lần `matches(...)` được Spring gọi, bởi chi tiết nội bộ này có thể khác tùy phiên bản.

**Giới hạn quan trọng:** Hai test có kết quả “không có MessagePort” ở parse và register phase **không tự chứng minh phase đã chạy**; phase được xác định bằng `ConfigurationCondition.getConfigurationPhase()` và vị trí đặt annotation. Chúng kiểm chứng kết quả quan sát được tương ứng. Nếu muốn quan sát sâu thời điểm gọi, có thể thêm logging vào `matches(...)` trong môi trường demo, nhưng không dùng số dòng log như một hợp đồng ổn định.

## 10. Điều kiện ở class và điều kiện ở @Bean method

Ngoài phase, **vị trí annotation** cũng quyết định phạm vi ảnh hưởng.

### Condition ở class

```java
@Configuration(proxyBeanMethods = false)
@Conditional(FeaturePresentCondition.class)
class FeatureConfiguration {
    @Bean
    FeatureClient featureClient() {
        return new FeatureClient();
    }

    @Bean
    FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
```

Đây là fragment (các kiểu `Feature...` chưa được định nghĩa). Nếu điều kiện ở class không khớp tại điểm xử lý của nó, cả cấu hình không được áp dụng qua đường này; hai method bên trong không được đóng góp bean definitions.

### Condition ở method

```java
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {
    @Bean
    @Conditional(FeaturePresentCondition.class)
    FeatureClient featureClient() {
        return new FeatureClient();
    }

    @Bean
    FeatureMetrics featureMetrics() {
        return new FeatureMetrics();
    }
}
```

Ở đây condition chỉ bảo vệ method `featureClient()`. Nếu nó không khớp, method `featureMetrics()` vẫn có thể đăng ký bean definition, trừ các condition/dependency khác. Ví dụ chỉ minh họa phạm vi; việc `featureMetrics()` có thể khởi tạo thành công còn phụ thuộc code và dependency thật.

**Không nên áp đặt condition `PARSE_CONFIGURATION` lên một method `@Bean` rồi kỳ vọng nó hoạt động y hệt condition ở class:** parse phase là khái niệm gắn với phân tích configuration class, trong khi `@Bean` method chủ yếu được xử lý khi đăng ký định nghĩa. Nếu cần chặn cả nhóm bean sớm, đặt parse-phase condition lên class cấu hình hoặc nested configuration class.

## 11. Khái niệm dễ nhầm khác: @Conditional, @Profile, @Lazy và @DependsOn

| Cơ chế | Quyết định điều gì? | Không đồng nghĩa với |
| --- | --- | --- |
| `@Conditional` / `ConfigurationCondition` | Có xử lý cấu hình hoặc đăng ký bean definition tương ứng không | Không phải cơ chế khởi tạo bean sớm/muộn theo nhu cầu. |
| `@Profile("dev")` | Định nghĩa chỉ được đăng ký khi profile phù hợp | Không tạo bean rồi xóa lúc runtime. |
| `@Lazy` | Chậm khởi tạo instance ở các tình huống được hỗ trợ | Không làm bean definition biến mất. |
| `@DependsOn` | Thứ tự phụ thuộc khởi tạo và hủy trong những tình huống phù hợp | Không điều khiển giai đoạn parse configuration. |
| `@AutoConfiguration(after=...)` | Thứ tự xử lý giữa các auto-configuration | Không bảo đảm instance bean có thứ tự tương tự. |
| `@Order` / `@Priority` | Ưu tiên/thứ tự cho các cơ chế hỗ trợ annotation này | Không phải thay thế chung cho ordering auto-configuration. |

Đặc biệt, nếu condition `REGISTER_BEAN` trả về false, nó loại **bean definition** liên quan; `@Lazy` chỉ làm trì hoãn **bean instance** mà định nghĩa vẫn có trong context. Đó là hai tầng thiết kế khác nhau.

## 12. Lỗi thường gặp và cách chẩn đoán

### Lỗi A — “Class auto-configuration nằm trên classpath thì mọi @Bean chắc chắn có”

Không đúng. Class có thể chưa được khai báo trong `AutoConfiguration.imports`, có thể bị exclude, hoặc có condition ở parse/register phase không khớp. Kiểm tra đúng đường nạp cấu hình trước khi kiểm tra method.

### Lỗi B — “Bean bị mất nghĩa là method đã chạy rồi trả null”

Thông thường, nếu `@Conditional` trên method không khớp, **factory method không được gọi** và định nghĩa bean không được đăng ký. Khác với method được gọi rồi trả về `null` (vốn là trường hợp riêng). Không dùng `null` để mô phỏng một condition mà không hiểu semantics.

### Lỗi C — “@ConditionalOnBean thấy bean mà cấu hình sau này sẽ đăng ký”

Điều kiện loại này dựa trên bean definitions **đã được xử lý**, không nhìn thấy mọi bean tương lai. Kiểm tra vị trí condition, thứ tự auto-configuration, kiểu trả về method `@Bean` và nguồn đăng ký bean. Nếu hai auto-configuration phụ thuộc nhau, dùng ordering có chủ đích.

### Lỗi D — “Đã khai báo @Bean trả Object, nhưng condition kiểm tra concrete type vẫn phải thấy”

Spring có thể chỉ suy ra kiểu `Object` từ chữ ký trước khi instance được tạo. Khai báo return type đủ cụ thể khi muốn condition theo concrete type phát hiện bean, hoặc thay điều kiện theo abstraction đã công bố.

### Lỗi E — “Đã disable bean bằng condition nhưng bean vẫn có”

Kiểm tra bean có được đăng ký qua **đường khác** không: component scan, `@Import`, cấu hình người dùng, auto-configuration khác hoặc bean definition registrar. Một condition trên một nguồn định nghĩa không xóa cùng loại bean do nguồn khác đăng ký.

### Lỗi F — “Thay đổi property trong lúc runtime thì auto-configuration tự chạy lại”

Các điều kiện điều khiển đăng ký bean được đánh giá trong quá trình xây dựng context. Thay đổi property của một context đã chạy **không tự động** gây re-parse/re-register bean definitions. Cần cơ chế refresh/rebuild có chủ đích nếu chức năng thực sự hỗ trợ cấu hình động.

### Lỗi G — “REGISTER_BEAN là sau khi singleton đã khởi tạo”

Không. Đây vẫn là giai đoạn xử lý **bean definition**. Tránh thực hiện kết nối mạng, đọc dữ liệu nặng hoặc tác dụng phụ từ `Condition.matches(...)`. Các condition nên nhẹ, quyết định dựa trên metadata/environment/context hiện có.

### Lỗi H — “Test điều kiện bằng @SpringBootTest luôn đơn giản nhất”

Integration test có thể chứa nhiều bean/auto-configuration khác và làm khó xác định nguyên nhân. Với một auto-configuration cụ thể, `ApplicationContextRunner` giúp cô lập class, bean, property và kết quả condition. Sau đó thêm một integration test để bắt lỗi đóng gói imports và scan thực tế.

### Lỗi I — “@ConditionalOnClass trên method @Bean với kiểu SDK vắng mặt luôn an toàn”

Class chứa method có thể phải được load/inspect trước khi condition trên method được xét, gây lỗi do chữ ký nhắc đến class tùy chọn không có mặt. Cách an toàn hơn thường là nested `@Configuration(proxyBeanMethods=false)` mang `@ConditionalOnClass` ở class-level và chứa những method dùng kiểu SDK đó.

## 13. Debug: phân biệt vì sao cấu hình và bean không xuất hiện

Spring Boot có **Condition Evaluation Report** giúp theo dõi các condition có positive/negative match. Chạy demo với:

```bash
mvn spring-boot:run -Dspring-boot.run.arguments=--debug
```

Khi dùng `demo.phase.parse.enabled=false`, class-level `ParseGate` không khớp. Khi dùng `demo.phase.register.enabled=false`, condition trên bean method không khớp. Khi có user-provided `MessagePort`, `@ConditionalOnMissingBean` sẽ back off. Cả ba trường hợp có thể dẫn tới việc **không thấy bean mặc định**, nhưng nguyên nhân khác nhau.

Ngoài log:

1. Xem class auto-configuration có được liệt kê trong `AutoConfiguration.imports` không.
2. Kiểm tra các property từ `Environment` và active profiles.
3. Kiểm tra điều kiện được đặt **trên class hay method**.
4. Đọc kiểu trả về khai báo của `@Bean` và tên bean.
5. Đọc condition outcomes trong report thay vì suy luận chỉ từ exception.
6. Khi cần, xem danh sách bean definitions với `ConfigurableListableBeanFactory`; nó phản ánh điều đã đăng ký, không nói đầy đủ mọi lần condition được gọi.

Actuator có endpoint `conditions` và `beans` khi thêm dependency, expose đúng và áp dụng kiểm soát truy cập. Không nên mở endpoint chẩn đoán rộng rãi trên production.

**Ghi chú về log của condition tự viết:** Các condition có thể được gọi hơn một lần tùy quá trình xử lý; bài không giả định mọi class đều chỉ có một lần check. Điều quan trọng là phase/địa điểm check và tác động lên bean definition.

## 14. Quy tắc thiết kế condition và auto-configuration

- **Classpath trước, bean sau:** Khi thư viện phụ thuộc SDK tùy chọn, đặt classpath condition ở cấp class/nested configuration để loại các cấu hình không hợp lệ càng sớm càng phù hợp.
- **Bean condition ở chỗ đúng:** Ưu tiên `@ConditionalOnBean`/`@ConditionalOnMissingBean` trong auto-configuration, khi phần lớn cấu hình user đã được xét.
- **Back-off là chính sách:** Xác định bean type/name mà user được phép thay, không dùng condition mơ hồ.
- **Không giả định object đã tạo:** Condition dựa trên metadata, environment và registry phù hợp; tránh side effects/khởi tạo sớm.
- **Phạm vi condition rõ ràng:** Điều kiện trên class chặn nhiều bean, điều kiện trên method chặn một bean; đặt nơi diễn đạt đúng ranh giới tính năng.
- **Ordering có ý nghĩa:** Nếu consumer auto-configuration phụ thuộc bean definitions do provider auto-configuration đăng ký, dùng `after`/`before` khi cần, không mặc định dựa vào thứ tự file imports.
- **Bean return type đủ cụ thể:** Chữ ký method giúp condition dựa trên kiểu phân giải bean mà không cần gọi factory method.
- **Kiểm thử từng nhánh:** Có test cho điều kiện class sai, condition method sai, user bean back-off và default thành công.
- **Tách hai tầng API:** `@Conditional` quyết định registration; `@Lazy`/scope quyết định phần lớn thời điểm instantiation.
- **Chẩn đoán theo chứng cứ:** Kết hợp condition report, bean definitions, classpath resource và tests thay vì chỉ nhìn số lượng bean cuối cùng.

## 15. Câu hỏi tự kiểm tra

1. Khi `ConfigurationCondition.getConfigurationPhase()` trả `PARSE_CONFIGURATION`, condition chủ yếu được xét khi nào? **Trong quá trình phân tích configuration class**.
2. Khi trả `REGISTER_BEAN`, nó có nghĩa là factory method đã chạy và trả instance chưa? **Không**. Nó thuộc giai đoạn xử lý bean definition.
3. Vì sao `@ConditionalOnMissingBean(MessagePort.class)` có thể phụ thuộc thứ tự? **Vì nó chỉ xét các bean definitions đã được xử lý tại thời điểm đánh giá**, không nhìn thấy bean tương lai.
4. `@ConditionalOnClass` và `@ConditionalOnMissingBean` có hoàn toàn cùng loại thông tin đầu vào không? **Không**: một bên classpath/metadata, bên kia bean definitions.
5. Nếu class-level condition không khớp, những `@Bean` method của class đó có được xử lý như thường không? **Không** theo con đường cấu hình bị chặn.
6. Nếu condition trên một `@Bean` method không khớp, bean từ các method khác cùng configuration có nhất thiết bị loại không? **Không**.
7. Bean definition đã được đăng ký có chắc instance đã được tạo không? **Không**; có thể chưa qua instantiation hoặc là lazy/prototype.
8. `@Lazy` làm Spring bỏ qua đăng ký bean definition? **Không**; nó chủ yếu tác động thời điểm tạo instance.
9. Hai lệnh tắt demo tại parse/register phase đều in `port.present=false`. Có thể dùng stdout để kết luận chúng cùng phase không? **Không**; output giống nhau không đồng nghĩa lý do giống nhau.
10. Khi muốn một bean mặc định nhường chỗ cho user bean, nên làm gì? **Dùng `@ConditionalOnMissingBean` phù hợp ở auto-configuration và kiểm thử nhánh back-off**.
11. Khi điều kiện theo type không nhận bean dù sau startup thấy instance đúng class, kiểm tra gì? **Declared return type, thời điểm đăng ký, proxy và các bean definitions khả dụng**.
12. Muốn kiểm thử nhanh điều kiện và back-off trong một context nhỏ, API nào phù hợp? **`ApplicationContextRunner`**.

## Nguồn chính thức

- [Spring Framework API — ConfigurationCondition](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html): `getConfigurationPhase()` và phân biệt parse/register.
- [Spring Framework API — ConfigurationCondition.ConfigurationPhase](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html): `PARSE_CONFIGURATION` và `REGISTER_BEAN`.
- [Spring Framework Reference — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): configuration classes và `@Bean`.
- [Spring Boot 3.5 API — ConditionalOnBean](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): matching dựa trên bean definitions được xử lý.
- [Spring Boot 3.5 API — ConditionalOnMissingBean](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnMissingBean.html): semantics back-off và thời điểm điều kiện.
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): registration qua imports, condition, test với `ApplicationContextRunner` và ordering.
- [Spring Boot Reference — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): exclude và Condition Evaluation Report.
