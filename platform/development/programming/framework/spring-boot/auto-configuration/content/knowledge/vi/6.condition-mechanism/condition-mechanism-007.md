# ConfigurationCondition: phân biệt PARSE_CONFIGURATION và REGISTER_BEAN trong Spring Boot

## 1. Vấn đề: không phải mọi điều kiện đều nên được xét ở cùng một thời điểm

Spring Boot auto-configuration dựa rất nhiều vào các annotation `@Conditional...`. Chúng quyết định **một lớp cấu hình hoặc một bean có đủ điều kiện để được đăng ký vào Spring container hay không**. Nhưng “điều kiện được xét khi nào?” là câu hỏi quan trọng, bởi trước khi container hoàn tất xây dựng, thông tin có sẵn tại mỗi giai đoạn không giống nhau.

Hãy phân biệt hai trường hợp:

1. **Kiểm tra môi trường hoặc điều kiện có thể xác định sớm.** Ví dụ: một property có bật tính năng không, class phụ thuộc có tồn tại trên classpath không? Ta muốn biết trước khi Spring phân tích sâu cấu hình không phù hợp.
2. **Kiểm tra bean definition đã được đăng ký hay chưa.** Ví dụ: người dùng đã cung cấp một `PaymentGateway` chưa, để auto-configuration quyết định có tạo default hay không? Cần đợi đến khi những cấu hình liên quan đã được phân tích và các bean definitions thích hợp đã được xử lý.

Spring Framework biểu diễn sự khác biệt đó bằng interface:

```java
org.springframework.context.annotation.ConfigurationCondition
```

Nó kế thừa `Condition` và thêm phương thức `getConfigurationPhase()` để chọn **giai đoạn đánh giá**. Enum `ConfigurationCondition.ConfigurationPhase` có hai giá trị:

- `PARSE_CONFIGURATION`: đánh giá lúc **phân tích class `@Configuration`**.
- `REGISTER_BEAN`: đánh giá khi **đăng ký bean** (sau khi các configuration classes đã được phân tích).

Đây là cơ chế **lifecycle khi dựng bean definitions**. Nó **không** tương ứng với “trước constructor” và “sau constructor”, không phải hai phase runtime của ứng dụng, cũng không phải mức ưu tiên của bean.

## 2. Đi từ `Condition` tới `ConfigurationCondition`

### 2.1. `@Conditional` liên kết annotation với logic kiểm tra

Trong Spring Framework, `@Conditional` nhận một hay nhiều class triển khai `Condition`:

```java
@Conditional(SomeCondition.class)
@Configuration(proxyBeanMethods = false)
class FeatureConfiguration {
    // @Bean ...
}
```

Đây là đoạn mã minh họa, không phải chương trình biên dịch độc lập: `SomeCondition` cần được định nghĩa.

Hợp đồng cơ bản của `Condition`:

```java
public interface Condition {
    boolean matches(ConditionContext context,
                    AnnotatedTypeMetadata metadata);
}
```

Khi `matches(...)` trả `true`, điều kiện đó **khớp**. Khi trả `false`, phần tử cấu hình gắn `@Conditional` không đủ điều kiện được đăng ký theo ngữ cảnh áp dụng. Nếu có nhiều conditions, tất cả điều kiện cần thỏa.

Hai tham số quan trọng:

- `ConditionContext` cung cấp quyền truy cập `Environment`, `BeanDefinitionRegistry`, `ConfigurableListableBeanFactory` (khi có), `ResourceLoader` và `ClassLoader`. Mức độ sẵn sàng/cách sử dụng phụ thuộc **thời điểm** đánh giá.
- `AnnotatedTypeMetadata` cung cấp **metadata** của class hoặc phương thức được annotate. Có thể đọc attributes từ annotation qua API metadata thay vì cần tạo một bean.

Một `Condition` đơn thuần không có phương thức trả về phase cụ thể. Để chỉ rõ điều kiện chỉ được đánh giá ở thời điểm phù hợp đối với class `@Configuration`, triển khai `ConfigurationCondition`.

### 2.2. Hợp đồng bổ sung của `ConfigurationCondition`

Về mặt ý nghĩa:

```java
public interface ConfigurationCondition extends Condition {
    ConfigurationPhase getConfigurationPhase();
}
```

`ConfigurationPhase` là enum lồng trong `ConfigurationCondition`; nó có hai giá trị ở phần 1.

Ví dụ skeleton đúng cú pháp khi triển khai:

```java
import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

final class SampleCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
            ConditionContext context, AnnotatedTypeMetadata metadata) {
        return true;
    }
}
```

Đoạn trên là **class minh họa**; cần đặt trong một file Java/package phù hợp và không dùng nó làm điều kiện nghiệp vụ vì `matches` luôn đúng. Dù vậy, hai method thể hiện rõ: `getConfigurationPhase` chọn **khi nào xét**, `matches` quyết định **có khớp không**.

Không được hiểu `ConfigurationCondition` là một annotation mới để gắn trực tiếp lên class. Đây là **Java interface** mà một class triển khai; annotation được gắn lên class cấu hình vẫn là `@Conditional(...)` hoặc các composed annotations của Spring Boot.

## 3. Hai phase theo đúng Javadoc Spring Framework

| Đặc điểm | `PARSE_CONFIGURATION` | `REGISTER_BEAN` |
| --- | --- | --- |
| Thời điểm chính | Khi Spring **parse** một `@Configuration` class | Khi Spring **đăng ký** regular bean definition, sau bước parse |
| Câu hỏi nên hỏi | “Có cần đưa cấu hình này vào cây cấu hình không?” | “Với definitions đã xử lý, có nên thêm bean này không?” |
| Dữ liệu phù hợp | `Environment`, classpath, metadata/configuration-independent facts | `BeanDefinitionRegistry`, sự hiện diện của bean definitions đã được xử lý |
| Nếu không khớp trên config class | Config class có thể bị loại ngay ở bước parse | Không có tác dụng chặn **bước parse** class; có thể ngăn đăng ký phần beans/config tương ứng sau đó |
| Ví dụ ý tưởng | Bật/tắt cả integration theo property hoặc classpath | Back-off theo bean mà ứng dụng đã cung cấp |
| Không đồng nghĩa | Tạo singleton sớm | Chạy constructor, dependency injection hoặc ApplicationRunner |

Javadoc của `PARSE_CONFIGURATION`: điều kiện cần đánh giá khi `@Configuration` class được parse; nếu không khớp **ở thời điểm đó**, class cấu hình không được thêm vào quá trình parse.

Javadoc của `REGISTER_BEAN`: điều kiện cần đánh giá khi thêm regular (không phải `@Configuration`) bean; điều kiện này **không ngăn việc phân tích cấu hình**, và tại thời điểm đánh giá, các `@Configuration` classes đã được parse.

**Nuance quan trọng:** không suy ra rằng mọi bean trong ứng dụng đã được **khởi tạo** tại `REGISTER_BEAN`, hoặc registry đã bao gồm mọi bean sẽ được đăng ký bởi các extension muộn hơn. “Đã parse config classes” và “đã có mọi bean instance” là hai sự kiện khác nhau. Với các bean-dependent conditions, Spring Boot nhắc rằng chỉ những bean definitions **đã được xử lý cho tới thời điểm đánh giá** mới được nhìn thấy.

### 3.1. Sơ đồ tư duy (không phải toàn bộ lifecycle nội bộ)

```text
@SpringBootApplication / @Configuration / auto-config candidates
                         |
                         v
           Phân tích configuration metadata
                         |
          PARSE_CONFIGURATION conditions
                  /             \
              false             true
               |                 |
          Bỏ config       Tiếp tục phân tích
                               |
                               v
                   Xác định các bean definitions
                               |
                 REGISTER_BEAN conditions
                        /             \
                    false             true
                     |                 |
            Không thêm bean      Thêm bean definition
                     \                 /
                      \               /
                       v             v
                      BeanFactory / Bean registry
                                |
                                v
                   Tạo các bean instances, DI,
                  post-processing và chạy ứng dụng
```

Sơ đồ mô tả **hai cửa quyết định logic**. Không coi đó là trình tự tuyến tính cứng cho mọi implementation, vì Spring còn có component scanning, imports, registry post-processors, điều kiện lồng, scoped beans và các bước tối ưu riêng của Boot.

### 3.2. Chọn phase dựa theo dữ liệu đầu vào

Một kiểm tra chỉ đọc `Environment` có thể an toàn ở parse phase. Trái lại, kiểm tra “container đã có bean X?” thường **không** phù hợp với parse phase vì nhiều bean definitions chưa được thêm vào registry.

Ví dụ **không nên**:

```java
@Override
public ConfigurationPhase getConfigurationPhase() {
    return ConfigurationPhase.PARSE_CONFIGURATION;
}

@Override
public boolean matches(ConditionContext context,
                       AnnotatedTypeMetadata metadata) {
    return context.getBeanFactory() != null
            && context.getBeanFactory().containsBean("userGateway");
}
```

Đây là đoạn minh họa cố tình đặt bean lookup ở **phase quá sớm**, không phải một condition chạy độc lập. Tại thời điểm parse, `userGateway` có thể chưa được đăng ký hoặc thậm chí chưa được tạo. Condition có nguy cơ cho kết quả false dù application cuối cùng có bean tương ứng.

Nếu mục tiêu thật sự là kiểm tra bean, thường nên dùng `@ConditionalOnBean`, `@ConditionalOnMissingBean` do Boot cung cấp, hoặc condition có phase phù hợp ở bước đăng ký. Đừng viết condition thủ công để sao chép một tính năng đã có trong Boot.

## 4. Liên hệ với các condition quen thuộc của Spring Boot

### 4.1. Điều kiện theo classpath

`@ConditionalOnClass` dùng để kiểm tra một class có nằm trên classpath không:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.sdk.ExternalClient")
class ExternalClientAutoConfiguration {
    // ...
}
```

Đây là đoạn mã minh họa. Thông tin classpath thường hữu ích **trước khi phân tích hoặc load những cấu hình tùy chọn**. Spring Boot có cơ chế filter class-based conditions sớm bằng metadata; vì vậy điều kiện theo class là ví dụ tự nhiên cho mối quan tâm ở parse phase.

Không nên tuyên bố rằng mọi condition theo class đều chỉ được xét đúng một lần hoặc thông qua một phương thức duy nhất; Boot có thể tối ưu cả ở giai đoạn lọc candidate. Điều quan trọng là **khả năng đánh giá sớm khi chỉ dựa vào classpath/metadata**.

### 4.2. Điều kiện theo bean definitions

`@ConditionalOnMissingBean` cần biết những bean đã được khai báo:

```java
@Bean
@ConditionalOnMissingBean(PaymentGateway.class)
PaymentGateway defaultGateway() {
    return new InMemoryPaymentGateway();
}
```

Đây là đoạn mã minh họa, các kiểu `PaymentGateway` và `InMemoryPaymentGateway` cần được định nghĩa trong project. Spring Boot dùng `OnBeanCondition` với **phase `REGISTER_BEAN`** cho nhóm điều kiện cần kiểm tra bean.

Tài liệu Boot cảnh báo: `@ConditionalOnBean` và `@ConditionalOnMissingBean` chỉ biết những definitions đã được xử lý cho tới thời điểm đánh giá. Do đó chúng được khuyến nghị sử dụng **trong auto-configuration**, để configuration do người dùng khai báo được xử lý trước và default có thể nhường chỗ.

Đây là lý do:
- Chọn phase **không phải thay đổi priority/`@Order`**.
- `REGISTER_BEAN` không tự bảo đảm hai auto-config bất kỳ được xét theo thứ tự bạn muốn; vẫn cần `@AutoConfiguration(after = ...)` hoặc `afterName` nếu condition của auto-config B phụ thuộc definitions từ auto-config A.
- Nếu một bean được thêm muộn bởi cơ chế riêng, condition đã đánh giá trước đó không tự “đánh giá lại” để xóa/thay bean đã đăng ký.

### 4.3. Đặt điều kiện ở class hay method?

`@Conditional` có thể gắn trên class cấu hình hoặc `@Bean` method. Nhưng **phase mà condition yêu cầu phải tương thích với vị trí sử dụng**.

| Vị trí | Cách hiểu hợp lý |
| --- | --- |
| `@Conditional(ParseGateCondition.class)` trên `@Configuration` class | Chọn có parse cả class hay không |
| `@Conditional(RegisterGateCondition.class)` trên `@Configuration` class | Cho phép class được parse, rồi quyết định phần đăng ký ở phase phù hợp |
| `@Conditional(RegisterGateCondition.class)` trên `@Bean` method | Kiểm tra khi đăng ký factory bean |
| `@Conditional(ParseGateCondition.class)` trên `@Bean` method | Không phải cách phù hợp để chặn parse toàn class; có nguy cơ condition không được đánh giá như bạn nghĩ |
| `@ConditionalOnMissingBean` trên auto-config hoặc method | Dùng logic về bean đang được đăng ký, nên cần xem thứ tự definition |

Với mục tiêu “loại bỏ cả cấu hình không cần thiết ngay từ đầu”, đặt parse condition **trên class cấu hình**. Với mục tiêu “có bean người dùng thì không tạo default”, đặt condition bean-related tại auto-config phù hợp, thường ở `@Bean` method.

### 4.4. `Condition` thuần có giống `ConfigurationCondition` không?

Không. `Condition` chỉ nêu hàm `matches`; `ConfigurationCondition` còn chỉ rõ giai đoạn khi condition được áp dụng cho `@Configuration`. Một custom `Condition` không triển khai `ConfigurationCondition` không cung cấp lựa chọn phase cụ thể, và Spring có thể đánh giá nó ở nhiều thời điểm liên quan tới cấu hình. Không viết code với giả định `matches` chắc chắn chỉ chạy một lần.

## 5. Ví dụ Maven hoàn chỉnh: tự viết hai ConfigurationCondition

Ví dụ sau dùng **Java 17+**, **Spring Boot 3.3.13** và Maven. Hai condition được đặt trên **hai lớp auto-configuration**:

- `ParseGateCondition` chỉ chạy ở `PARSE_CONFIGURATION`, đọc property `demo.parse-enabled` và quyết định liệu cấu hình `ParseCheckedAutoConfiguration` có được đưa qua bước parse.
- `RegistryGateCondition` chỉ chạy ở `REGISTER_BEAN`, kiểm tra registry có **bean definition tên `userMarker`** hay chưa. Điều kiện này minh họa việc dùng thông tin **đăng ký bean**, không gọi `getBean(...)` để tạo bean instance.
- `DemoApplication` khai báo `userMarker` theo property `demo.marker-enabled`. Nhờ auto-config được xử lý sau cấu hình ứng dụng, `RegistryGateCondition` quan sát bean definition của ứng dụng trong kịch bản bình thường.
- Runner in xem hai bean `parseProof`, `registerProof` có thực sự tồn tại không. Ta chạy bốn tổ hợp property để nhận diện rõ hai phase.

**Phạm vi demo:** hai custom conditions giúp học cơ chế. Trong code sản phẩm, kiểm tra property/bean đơn giản nên ưu tiên `@ConditionalOnProperty` và `@ConditionalOnBean` có sẵn, trừ khi bạn thật sự cần điều kiện đặc thù.

### 5.1. Cấu trúc project

```text
configuration-condition-demo/
├── pom.xml
└── src/main/
    ├── java/com/example/
    │   ├── app/
    │   │   ├── DemoApplication.java
    │   │   └── UserMarker.java
    │   └── autoconfig/
    │       ├── ParseGateCondition.java
    │       ├── RegistryGateCondition.java
    │       ├── ParseCheckedAutoConfiguration.java
    │       └── RegisterCheckedAutoConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

App ở `com.example.app`, còn auto-config ở `com.example.autoconfig`: package auto-config **nằm ngoài phạm vi component scanning mặc định** của app. Các classes auto-config được Boot tìm bằng imports file chứ không phải component scan.

### 5.2. `pom.xml`

```xml
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
    <artifactId>configuration-condition-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
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
```

### 5.3. `src/main/java/com/example/app/UserMarker.java`

```java
package com.example.app;

public record UserMarker(String source) {
}
```

`UserMarker` là record Java 17. Nó tồn tại để phân biệt **định nghĩa một bean** với **tạo một object instance**. Bài demo sẽ kiểm tra `containsBeanDefinition` theo tên, không đụng đến record instance trong custom condition.

### 5.4. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo",
            name = "marker-enabled",
            havingValue = "true",
            matchIfMissing = true)
    UserMarker userMarker() {
        return new UserMarker("application");
    }

    @Bean
    ApplicationRunner report(ApplicationContext context) {
        return args -> {
            System.out.println("USER_MARKER="
                    + context.containsBean("userMarker"));
            System.out.println("PARSE_PROOF="
                    + context.containsBean("parseProof"));
            System.out.println("REGISTER_PROOF="
                    + context.containsBean("registerProof"));
        };
    }
}
```

Phương thức `userMarker()` được đăng ký khi `demo.marker-enabled=true` hoặc property vắng mặt, do `matchIfMissing=true`. Runner không bắt buộc phải nhận `UserMarker`, nên app vẫn có thể khởi động khi bean này vắng mặt.

**Không dùng `@ConditionalOnProperty` làm ví dụ custom `ConfigurationCondition`**: nó chỉ giúp ứng dụng bật/tắt sự tồn tại của marker. Hai implementation custom nằm trong hai file tiếp theo.

### 5.5. `src/main/java/com/example/autoconfig/ParseGateCondition.java`

```java
package com.example.autoconfig;

import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class ParseGateCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.PARSE_CONFIGURATION;
    }

    @Override
    public boolean matches(
            ConditionContext context, AnnotatedTypeMetadata metadata) {
        return Boolean.parseBoolean(
                context.getEnvironment()
                       .getProperty("demo.parse-enabled", "false"));
    }
}
```

Điều kiện đọc `Environment`, không phụ thuộc bean registry. Nếu property là `true`, `matches` trả true. Nếu false hoặc vắng mặt, trả false.

Chọn `PARSE_CONFIGURATION` phù hợp vì ta muốn quyết định **cả class cấu hình** có nên tham gia parse không, và thông tin cần thiết đã có đủ sớm.

**Chú ý boolean parsing:** `Boolean.parseBoolean` trả true cho chuỗi `"true"` (không phân biệt hoa/thường); giá trị khác trả false. Đây là quy ước của **demo**, không phải tất cả dạng biểu thức property condition được Spring Boot hỗ trợ.

### 5.6. `src/main/java/com/example/autoconfig/RegistryGateCondition.java`

```java
package com.example.autoconfig;

import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.context.annotation.ConfigurationCondition;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class RegistryGateCondition implements ConfigurationCondition {

    @Override
    public ConfigurationPhase getConfigurationPhase() {
        return ConfigurationPhase.REGISTER_BEAN;
    }

    @Override
    public boolean matches(
            ConditionContext context, AnnotatedTypeMetadata metadata) {
        ConfigurableListableBeanFactory factory = context.getBeanFactory();
        return factory != null
                && factory.containsBeanDefinition("userMarker");
    }
}
```

Điểm quan trọng không phải class `UserMarker` đã có instance. `containsBeanDefinition("userMarker")` chỉ kiểm tra **metadata định nghĩa bean theo tên** tại thời điểm xét. Nó không gọi phương thức `userMarker()` và không kích hoạt tạo bean.

Tại `REGISTER_BEAN`, Spring Framework đã parse các configuration classes; trong auto-configuration, bean definitions từ app thường đã được xử lý nên cách kiểm tra này quan sát được marker trong demo.

**Giới hạn thiết kế:** code này chỉ kiểm tra **đúng tên bean `userMarker` trong BeanFactory hiện tại**. Nó không phải bản sao hoàn chỉnh của `@ConditionalOnBean(UserMarker.class)`: điều kiện tích hợp của Boot có hỗ trợ type matching, parent/child contexts, bean annotations và nhiều lựa chọn khác. Trong thư viện thực tế nên ưu tiên built-in condition khi đủ dùng.

### 5.7. `src/main/java/com/example/autoconfig/ParseCheckedAutoConfiguration.java`

```java
package com.example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration
@Conditional(ParseGateCondition.class)
public class ParseCheckedAutoConfiguration {

    @Bean
    String parseProof() {
        return "parsed";
    }
}
```

`@Conditional(ParseGateCondition.class)` nằm **trên class**, không phải `@Bean` method. Nếu property tắt, điều kiện parse false nên cấu hình này không tiếp tục tham gia với bean `parseProof`. Nếu property bật, class đủ điều kiện phân tích và bean definition có thể được đăng ký.

`@AutoConfiguration` trong Boot 3.3 mang `@Configuration(proxyBeanMethods=false)`. Code không gọi chéo `@Bean` methods, nên hoàn toàn phù hợp.

### 5.8. `src/main/java/com/example/autoconfig/RegisterCheckedAutoConfiguration.java`

```java
package com.example.autoconfig;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration(after = ParseCheckedAutoConfiguration.class)
@Conditional(RegistryGateCondition.class)
public class RegisterCheckedAutoConfiguration {

    @Bean
    String registerProof() {
        return "registered";
    }
}
```

`@Conditional(RegistryGateCondition.class)` cũng nằm trên **class**, nhưng yêu cầu `REGISTER_BEAN`:

- Nó không ngăn Spring tiến hành **parse class** ở phase đầu.
- Khi đến đăng ký bean definitions, `RegistryGateCondition` xét registry đã có `userMarker` chưa.
- Nếu không có marker, không đăng ký bean `registerProof`; nếu có, bean này được phép đăng ký.

`@AutoConfiguration(after = ParseCheckedAutoConfiguration.class)` chỉ giúp mô tả ordering giữa hai auto-config; **không bắt buộc để kiểm tra `userMarker`** trong demo vì marker đến từ cấu hình ứng dụng. Không nhầm `after` với thứ tự khởi tạo bean instances.

### 5.9. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
demo.parse-enabled=false
demo.marker-enabled=true
```

`demo.parse-enabled` và `demo.marker-enabled` là properties **của demo**, không phải tên cấu hình chuẩn riêng của Spring Boot. `spring.main.web-application-type=none` khiến runner chạy rồi app kết thúc; `logging.level.root=OFF` giúp output ít log hơn.

### 5.10. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.autoconfig.ParseCheckedAutoConfiguration
com.example.autoconfig.RegisterCheckedAutoConfiguration
```

Đây là danh sách **hai auto-config candidates** trong Spring Boot 3.x. Tên class phải chính xác và tệp phải được đóng gói trong runtime classpath; chỉ có `@AutoConfiguration` trên class không thay thế việc công bố candidate trong imports file.

### 5.11. Biên dịch và chạy bốn trường hợp

Đứng tại thư mục có `pom.xml`:

```bash
mvn -q -DskipTests package
java -jar target/configuration-condition-demo-1.0.0.jar
```

**Trường hợp A — mặc định:** `demo.parse-enabled=false`, `demo.marker-enabled=true`:

```text
USER_MARKER=true
PARSE_PROOF=false
REGISTER_PROOF=true
```

- Parse condition false: không có `parseProof`.
- Bean definition `userMarker` hiện diện: register condition true, có `registerProof`.

**Trường hợp B — bật parse condition:**

```bash
java -jar target/configuration-condition-demo-1.0.0.jar --demo.parse-enabled=true
```

Stdout từ runner:

```text
USER_MARKER=true
PARSE_PROOF=true
REGISTER_PROOF=true
```

- Parse class được chấp nhận vì property true.
- Register condition vẫn true vì marker có definition.

**Trường hợp C — tắt marker:**

```bash
java -jar target/configuration-condition-demo-1.0.0.jar --demo.marker-enabled=false
```

Stdout:

```text
USER_MARKER=false
PARSE_PROOF=false
REGISTER_PROOF=false
```

- Parse gate vẫn false theo property mặc định.
- Không có bean definition `userMarker`, nên register gate false.

**Trường hợp D — bật parse, tắt marker:**

```bash
java -jar target/configuration-condition-demo-1.0.0.jar --demo.parse-enabled=true --demo.marker-enabled=false
```

Stdout:

```text
USER_MARKER=false
PARSE_PROOF=true
REGISTER_PROOF=false
```

- Một phase cho phép class parse, phase kia ngăn phần bean registration của class khác.
- Hai điều kiện **độc lập**: thay một property không tự sửa kết quả của condition còn lại.

Tổng hợp:

| parse-enabled | marker-enabled | `parseProof` | `registerProof` |
| --- | --- | --- | --- |
| false | true | Không | Có |
| true | true | Có | Có |
| false | false | Không | Không |
| true | false | Có | Không |

Các dòng trên chỉ tính output của `ApplicationRunner`, không bao gồm log môi trường. Đây là **kết quả được suy luận từ source demo**; nếu bạn thay source, dependency, property hoặc tên bean, hãy kiểm tra lại bằng cách chạy thực tế.

## 6. Điều cần chú ý khi viết custom ConfigurationCondition

### 6.1. Condition phải ít tác dụng phụ

`matches(...)` nên trả lời một phép kiểm tra dựa trên metadata, `Environment`, registry hoặc resource; không nên mở kết nối cơ sở dữ liệu, tạo thread, gọi API mạng, ghi file hoặc đăng ký bean thủ công từ trong condition.

Đừng gọi `context.getBeanFactory().getBean(SomeType.class)` chỉ để xem bean có tồn tại; nó có thể **kích hoạt khởi tạo bean** và làm rối vòng đời. Nếu cần thông tin về definitions, dùng API như `containsBeanDefinition` khi thích hợp hoặc sử dụng built-in Boot conditions.

### 6.2. Không suy luận rằng register phase biết “mọi thứ”

`REGISTER_BEAN` xảy ra khi registry đang được xây dựng. Các bean definitions **đã được xử lý** có thể quan sát được, nhưng definitions từ auto-config khác hoặc extension muộn hơn có thể chưa hiện diện. Vì vậy:

- Đối với **user bean**, auto-config thường có lợi thế được xử lý sau cấu hình ứng dụng.
- Đối với **bean từ auto-config A** mà B phụ thuộc, phải cân nhắc ordering `before/after`.
- Đối với **bean sẽ được đăng ký động về sau**, condition không thể nhìn thấy một future definition ở thời điểm hiện tại.
- Đối với **parent contexts**, logic type-based search có thể khác logic `containsBeanDefinition` local.

### 6.3. Condition trên class có thể quyết định phạm vi rộng

Khi gắn `@Conditional` lên `@Configuration`, Spring xử lý cả các `@Bean` và những khai báo cấu hình liên quan dưới tác động condition. Nếu chỉ một factory bean cần điều kiện riêng, đặt condition **trực tiếp trên method `@Bean`** có thể rõ ràng hơn.

Ví dụ:

```java
@AutoConfiguration
public class CacheAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CacheClient.class)
    CacheClient cacheClient() {
        return new DefaultCacheClient();
    }

    @Bean
    CacheMetrics cacheMetrics() {
        return new CacheMetrics();
    }
}
```

Đây là đoạn **minh họa**, chưa khai báo các kiểu `CacheClient`, `DefaultCacheClient`, `CacheMetrics` nên không phải project runnable. Nếu condition missing-bean nằm ở method `cacheClient()`, bean `cacheMetrics()` không bị tắt chỉ vì user đã cung cấp `CacheClient`. Nếu condition được đặt ở cấp class, phạm vi ảnh hưởng sẽ rộng hơn.

### 6.4. Không dùng phase để sửa thứ tự khởi tạo bean

`PARSE_CONFIGURATION`, `REGISTER_BEAN` thuộc thời điểm **xây dựng bean definitions**. Còn thứ tự tạo bean instances liên quan dependency injection, `@DependsOn`, scope và lifecycle callbacks. `@AutoConfiguration(after = ...)` chủ yếu điều khiển thứ tự áp dụng auto-config và đăng ký definitions, không bảo đảm thứ tự gọi constructors.

Nếu muốn bean A sử dụng bean B, hãy khai báo dependency qua constructor hoặc tham số `@Bean`; không sửa phase condition để tạo instance B sớm hơn.

### 6.5. Không dùng phase để thay thế property conditions

Nếu chỉ cần “bật khi `feature.enabled=true`”, `@ConditionalOnProperty` của Spring Boot thường đơn giản hơn tự viết `ConfigurationCondition`. Viết custom condition khi cần logic đặc thù, ví dụ kiểm tra metadata phức hợp, nhiều resource hoặc quan hệ registry chưa có annotation tích hợp phù hợp.

### 6.6. Ghi nhận kết quả điều kiện cho khả năng chẩn đoán

Custom class chỉ implements `ConfigurationCondition` có thể không tạo thông điệp điều kiện chi tiết như các Spring Boot conditions chuẩn. Với auto-config do thư viện cung cấp, có thể xem xét sử dụng `SpringBootCondition` hoặc tích hợp `ConditionMessage`/`ConditionOutcome` khi cần xuất báo cáo hữu ích. Nhưng không nên mở rộng implementation chỉ để có log trong một ví dụ giải thích phase cơ bản.

Trong demo, kiểm tra ba boolean trên runner là quan sát được **kết quả của việc đăng ký bean**, không phải bằng chứng trực tiếp về số lần `matches` được gọi.

## 7. Những lỗi thường gặp

| Hiện tượng | Sai sót | Cách sửa |
| --- | --- | --- |
| Condition kiểm tra bean trả false dù cuối cùng context có bean | Đánh giá ở parse phase quá sớm hoặc auto-config chưa được sắp thứ tự | Dùng `REGISTER_BEAN` khi thích hợp; xem ordering và built-in bean conditions |
| `@Conditional` trên `@Bean` không chặn cả class | Nhầm phạm vi method với class | Nếu cần bỏ cả configuration, đặt parse condition trên class |
| `@Conditional` dùng một `ConfigurationCondition` phase parse trực tiếp trên method `@Bean` | Phase không phù hợp vị trí | Đặt parse condition ở configuration class |
| Tưởng `REGISTER_BEAN` nghĩa là singleton đã được tạo | Nhầm definition với instance | Quan sát `containsBeanDefinition`, tránh gọi `getBean` trong condition |
| Dùng `context.getBeanFactory().getBean(...)` trong condition | Có thể kích hoạt tạo bean quá sớm | Kiểm tra metadata/definitions hoặc dùng Boot conditions |
| Lớp auto-config đúng nhưng không bao giờ được xét | Thiếu/sai `AutoConfiguration.imports` hoặc bị exclude | Kiểm tra JAR, file imports và exclusion |
| Chỉ có user bean cùng type nhưng custom condition tìm theo một tên khác | Logic đang kiểm tra tên, không kiểm tra type | Chuyển sang `@ConditionalOnBean(value=...)` hoặc tra type đúng |
| Cả hai condition đều trả true nhưng app vẫn không có bean | Có thể còn condition khác, sai package, lỗi tạo bean hoặc registration | Xem lỗi context, candidates và các điều kiện khác |
| Tắt parse gate nhưng kỳ vọng beans trong class vẫn xuất hiện | Cả config bị bỏ qua ở phase parse | Bật property hoặc tách các beans không liên quan sang config khác |
| Condition không khớp nhưng chạy ở thời điểm khác khi sửa source | Không hiểu phase và vị trí annotation | Xác định `getConfigurationPhase`, chỗ đặt `@Conditional` và thời điểm Spring xử lý |
| Tên marker khác dự kiến | `containsBeanDefinition("userMarker")` kiểm tra **name chính xác** | Kiểm tra tên `@Bean`, alias và local/parent context |
| Custom condition gọi dịch vụ bên ngoài, làm startup chậm/không ổn định | Điều kiện có side effect | Giữ condition nhẹ, dựa trên metadata/environment/registry |

## 8. Chẩn đoán điều kiện trong ứng dụng thật

Nếu một auto-configuration không tạo bean mong đợi, kiểm tra theo thứ tự:

1. **Candidate:** class `@AutoConfiguration` có nằm trong `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` của JAR không? Có bị loại trừ không?
2. **Class-level conditions:** classpath/property/web mode có đáp ứng không? Điều kiện sớm có làm cả configuration class bị loại không?
3. **Method-level conditions:** bean mặc định có `@ConditionalOnMissingBean` hoặc `@ConditionalOnProperty` ở chính factory method không?
4. **Bean definitions tại thời điểm xét:** user bean có được đăng ký không, method trả type nào, tên bean nào, có profile hoặc property làm method bị loại không?
5. **Ordering:** auto-config được xét sau những auto-config cung cấp bean dependency cần thiết chưa?
6. **Condition phase:** custom condition có lựa chọn phase phù hợp với thông tin nó sử dụng không?
7. **Bean creation:** nếu condition match mà startup vẫn lỗi, xem dependency resolution, circular dependencies, bean post-processing và constructor exceptions.

Spring Boot hỗ trợ `--debug` để in *Condition Evaluation Report*. Với ví dụ demo đã tắt root logging, cần override:

```bash
java -jar target/configuration-condition-demo-1.0.0.jar --debug --logging.level.root=DEBUG
```

`/actuator/conditions` cũng cung cấp báo cáo khi thêm Actuator và cấu hình exposure phù hợp; không nên mặc định mở endpoint này cho mọi truy cập bên ngoài.

**Phân biệt thông điệp log:** “không match” có thể là hành vi đúng thiết kế, không phải lỗi. Một custom `ConfigurationCondition` tự viết có thể thiếu lời giải thích chi tiết nếu không tích hợp API báo cáo của Boot.

## 9. Những ngộ nhận cần loại bỏ

| Ngộ nhận | Vì sao sai? |
| --- | --- |
| “PARSE và REGISTER là hai thời điểm tạo bean instances.” | Chúng thuộc **xử lý cấu hình và bean definitions**, chưa phải lifecycle instances. |
| “PARSE_CONFIGURATION có thể an toàn kiểm tra mọi bean của app.” | Khi parse, các definitions liên quan có thể chưa được đăng ký. |
| “REGISTER_BEAN khiến condition được đánh giá lại mỗi lần bean được sử dụng.” | Nó liên quan **đăng ký definitions**; không phải callback runtime cho mọi `getBean`. |
| “Nếu condition REGISTER false thì Spring chưa hề parse config class.” | Register condition không ngăn bước parse ban đầu; nó tác động ở bước đăng ký. |
| “Custom Condition implements interface là đủ, không cần đặt `@Conditional`.” | Condition phải được nối vào một annotation/configuration element để Spring biết cần xét. |
| “Chỉ cần `getConfigurationPhase` trả REGISTER thì auto-config B luôn nhìn thấy beans của A.” | Cần xét thứ tự auto-config và liệu bean A đã được xử lý chưa. |
| “`@ConditionalOnClass` và `@ConditionalOnBean` kiểm tra giống nhau.” | Cái đầu kiểm tra **sự hiện diện Java class**, cái sau kiểm tra **bean** trong context. |
| “`@Conditional` trên method có thể thay thế parse condition trên class.” | Phạm vi và giai đoạn khác; method-level không tự chặn parse cả class. |
| “Gọi `getBean()` trong condition là cách vô hại để kiểm tra.” | Có thể tạo bean instance quá sớm, gây side effects và lifecycle issues. |
| “Mọi condition phải trả cùng kết quả trong mọi lần gọi.” | Context có thể khác theo thời điểm; condition nên thiết kế đúng phase, ít side effects. |

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một điều kiện chỉ kiểm tra `Environment` thường phù hợp với `PARSE_CONFIGURATION`?

**Trả lời:** Vì property/environment đã sẵn sàng tương đối sớm và có thể dùng để quyết định có parse cả configuration class không, thay vì chờ bean registry.

**Câu 2.** Vì sao kiểm tra `containsBeanDefinition("userMarker")` cần cân nhắc `REGISTER_BEAN`?

**Trả lời:** Vì cần quan sát bean definition đã được thêm vào registry; ở parse phase có thể chưa được xử lý.

**Câu 3.** Nếu `ParseGateCondition` false trên `ParseCheckedAutoConfiguration`, bean `parseProof` có được đăng ký không?

**Trả lời:** Không, config class không được tiếp tục phân tích theo nhánh này.

**Câu 4.** Nếu `RegistryGateCondition` false trên `RegisterCheckedAutoConfiguration`, có thể kết luận Spring chưa parse class này không?

**Trả lời:** Không. Phase register không chặn bước parse; nó có thể ngăn phần định nghĩa bean được đăng ký về sau.

**Câu 5.** `getConfigurationPhase()` có làm thay đổi `@AutoConfiguration(after=...)` không?

**Trả lời:** Không. Phase chọn **loại thời điểm đánh giá**; `after` sắp thứ tự giữa các auto-configuration definitions.

**Câu 6.** Nếu demo có `demo.parse-enabled=true` và `demo.marker-enabled=false`, runner sẽ in gì?

**Trả lời:**

```text
USER_MARKER=false
PARSE_PROOF=true
REGISTER_PROOF=false
```

**Câu 7.** Khi user có `PaymentGateway` riêng, loại điều kiện Boot nào nên dùng để default back off?

**Trả lời:** Thường dùng `@ConditionalOnMissingBean(PaymentGateway.class)` trong auto-config, thay vì viết custom `Condition` dò tên bean bằng tay.

**Câu 8.** Một condition có thể gọi external HTTP API ở `matches` không?

**Trả lời:** Có thể viết Java làm vậy, nhưng **không nên**: nó khiến startup chịu network side effects, khó kiểm thử và không phù hợp nhiệm vụ gọn nhẹ của điều kiện đăng ký cấu hình.

## 11. Tài liệu tham khảo

- [Spring Framework 6.1 — ConfigurationCondition](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.html): interface, `getConfigurationPhase` và mục đích lựa chọn thời điểm xét.
- [Spring Framework 6.1 — ConfigurationCondition.ConfigurationPhase](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html): định nghĩa `PARSE_CONFIGURATION` và `REGISTER_BEAN`, bao gồm phạm vi parse class và đăng ký bean.
- [Spring Framework 6.1 — Conditional](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Conditional.html): điều kiện gắn lên class hoặc `@Bean` method.
- [Spring Boot 3.3 — ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html): giới hạn “bean definitions đã được xử lý tới thời điểm xét”, lý do nên dùng trong auto-config.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): imports file, class conditions, bean conditions và ordering giữa auto-configs.

**Kết luận:** `PARSE_CONFIGURATION` quyết định **có đưa một `@Configuration` class đi tiếp trong quá trình phân tích không**, còn `REGISTER_BEAN` quyết định **có nên thêm những bean definitions thích hợp sau bước parse không**. Chọn phase theo loại dữ liệu condition cần dùng; nếu phụ thuộc sự hiện diện của bean, ưu tiên điều kiện tích hợp của Spring Boot và luôn cân nhắc thứ tự bean definitions đã được xử lý.
