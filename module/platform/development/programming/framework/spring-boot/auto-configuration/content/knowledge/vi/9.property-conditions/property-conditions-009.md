# Phân biệt giá trị mặc định của @ConfigurationProperties và thuộc tính trong Environment

## 1. Tình huống dễ gây hiểu nhầm

Khi thiết kế Spring Boot Auto Configuration, ta thường vừa khai báo một lớp cấu hình bằng `@ConfigurationProperties`, vừa sử dụng `@ConditionalOnProperty` để bật hoặc tắt bean tự động.

Giả sử ứng dụng có cấu hình sau:

```java
@ConfigurationProperties(prefix = "demo.feature")
public class FeatureProperties {
    private boolean enabled = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

Không có `demo.feature.enabled` trong `application.properties` hoặc bất kỳ nguồn cấu hình nào khác. Sau khi Spring Boot tạo và bind `FeatureProperties`, giá trị `properties.isEnabled()` vẫn là `true` nhờ giá trị khởi tạo của trường Java. Nhưng nếu chạy:

```java
environment.getProperty("demo.feature.enabled");       // null
environment.containsProperty("demo.feature.enabled");  // false
```

kết quả lại cho biết thuộc tính **không tồn tại trong Environment**. Đây là hai phép hỏi về **hai nguồn sự thật khác nhau**:

- `FeatureProperties#getEnabled()` (trong ví dụ là `isEnabled()`) đọc **trạng thái của đối tượng Java sau binding**, có thể chứa giá trị mặc định do code đặt ra.
- `Environment#getProperty(...)` đọc **các PropertySource đã đăng ký** (như `application.yml`, biến môi trường, system properties, tham số dòng lệnh). Nó không đọc ngược field của `FeatureProperties` để bổ sung thuộc tính bị thiếu.

Tài liệu chính thức Spring Boot nói rõ: các giá trị mặc định được định nghĩa trong configuration properties **không phản ánh trở lại Environment**. Vì vậy, điều kiện `@ConditionalOnProperty` có thể cho kết quả khác giá trị getter của một bean `@ConfigurationProperties`.

## 2. Hai giai đoạn và hai loại "mặc định"

### 2.1. Giá trị từ Environment và quá trình binding

Dòng xử lý thông thường có thể hình dung như sau:

```text
application.properties / application.yml / env vars / JVM -D / CLI args
                            |
                            v
               Environment + các PropertySource
                    |                    |
                    v                    v
          Điều kiện bean          ConfigurationProperties Binder
          @ConditionalOnProperty             |
          kiểm tra key/value                 v
                                    đối tượng FeatureProperties
                                    (giữ default hoặc nhận override)
```

- `Environment` tổng hợp những giá trị cấu hình thực sự có trong các nguồn; nó áp dụng thứ tự ưu tiên nguồn và có thể trả về `null` khi key không hiện diện.
- `Binder` ánh xạ thuộc tính phù hợp từ `Environment` sang thành phần của đối tượng `@ConfigurationProperties`. Nếu không có giá trị cần bind, một trường đã khởi tạo trong Java có thể giữ nguyên default. Nếu có giá trị hợp lệ, binder cập nhật trường theo cách binding tương ứng.
- `@ConditionalOnProperty` thuộc cơ chế điều kiện khi Spring đăng ký cấu hình và bean definitions. Nó đánh giá giá trị từ `Environment`; nó **không gọi getter trên bean properties đã được bind** để ra quyết định.

Việc một giá trị mặc định nằm trong Java không làm cho tên thuộc tính tương ứng xuất hiện trong `Environment`.

### 2.2. Các nơi có thể đặt default

| Cách cung cấp mặc định | Ví dụ | Bean `@ConfigurationProperties` thấy gì nếu key thiếu? | `Environment` có key đó không? |
| --- | --- | --- | --- |
| Giá trị khởi tạo field Java | `private boolean enabled = true;` | `true` | Không, nếu không có nguồn khác |
| `@DefaultValue` cho constructor binding | `@DefaultValue("true") boolean enabled` | `true` | Không, nếu không có nguồn khác |
| Giá trị nguyên thủy Java khi không khởi tạo | `private boolean enabled;` | `false` | Không, nếu không có nguồn khác |
| Giá trị trong `application.properties` | `demo.feature.enabled=true` | `true` | Có |
| Default PropertySource được thêm vào Environment | `SpringApplication.setDefaultProperties(...)` | Giá trị được bind từ nguồn mặc định | Có |
| Placeholder fallback tại nơi dùng | `@Value("${demo.feature.enabled:true}")` | Không tự thay đổi bean properties khác | Không, nếu không có nguồn khác |

Đọc bảng theo từng hàng độc lập: một số nguồn cấu hình khác có thể đã cung cấp key và ghi đè giá trị mặc định. `@Value` là cách inject giá trị cục bộ cho vị trí được gắn annotation, không biến fallback bên trong placeholder thành một PropertySource.

### 2.3. Constructor binding và `@DefaultValue`

Với Java 17+, có thể biểu diễn default bằng record:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.feature")
public record FeatureSettings(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("20") int batchSize
) {}
```

Khi đăng ký kiểu này bằng `@EnableConfigurationProperties(FeatureSettings.class)` hoặc `@ConfigurationPropertiesScan`, nếu không có hai key tương ứng, binder tạo đối tượng có `enabled() == true` và `batchSize() == 20`. Tuy nhiên `Environment#getProperty("demo.feature.enabled")` và `Environment#getProperty("demo.feature.batch-size")` vẫn có thể là `null`. Annotation `@DefaultValue` thuộc logic binder; nó không tự thêm dữ liệu vào `Environment`.

Phân biệt thêm: `@DefaultValue` có thể chịu quy tắc chuyển đổi kiểu của binder. Với mutable JavaBean, field initializer là một cách thường gặp; với record/constructor binding, `@DefaultValue` là cách khai báo trực tiếp cho tham số.

## 3. Hệ quả đối với @ConditionalOnProperty

`@ConditionalOnProperty` kiểm tra **thuộc tính có trong Environment**, với các tham số thường dùng:

- `prefix` + `name` xác định key, ví dụ `prefix = "demo.feature", name = "enabled"` tạo thành `demo.feature.enabled`.
- `havingValue = "true"` yêu cầu giá trị của key khớp với chuỗi `true` theo quy tắc của condition.
- Nếu không khai báo `havingValue`, condition mặc định khớp khi key **hiện diện** và giá trị **không bằng "false"**.
- `matchIfMissing = false` là mặc định: khi key không tồn tại, condition không khớp.
- `matchIfMissing = true`: khi key không tồn tại, condition vẫn khớp, dù `Environment#getProperty(...)` vẫn có thể trả về `null`.

Giả sử `FeatureProperties.enabled` có Java default là `true`. Hai annotation dưới đây **không tương đương**:

```java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true"
)
// Thiếu key: không khớp.
```

```java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
// Thiếu key: khớp.
```

Trường hợp thứ hai mô hình hóa đúng chính sách "mặc định bật, người dùng đặt false thì tắt" khi Java properties cũng có default là `true`.

### Bảng quyết định

Giả sử không có PropertySource khác ghi đè và lớp `FeatureProperties` chứa `private boolean enabled = true;`:

| Giá trị cấu hình thực sự cung cấp | `properties.isEnabled()` sau binding | `Environment#getProperty(...)` | `@ConditionalOnProperty(havingValue="true")` | Thêm `matchIfMissing=true` |
| --- | --- | --- | --- | --- |
| Không khai báo key | `true` | `null` | Không khớp | Khớp |
| `demo.feature.enabled=true` | `true` | `"true"` | Khớp | Khớp |
| `demo.feature.enabled=false` | `false` | `"false"` | Không khớp | Không khớp |

Lưu ý: `matchIfMissing` chỉ điều khiển tình huống **key thiếu**, không tự coi bất kỳ giá trị hiện diện nào là hợp lệ. Khi dùng `havingValue = "true"`, các giá trị không khớp vẫn khiến condition thất bại. Khi không khai báo `havingValue`, hành vi mặc định là so sánh chuỗi với `false`, không phải ép kiểu mọi giá trị sang boolean như binder.

**Điểm cần nhớ:** `matchIfMissing=true` chỉ thay đổi **kết quả điều kiện**, không sửa giá trị `Environment`, không đặt giá trị field của bean properties và không tự đăng ký key còn thiếu.

## 4. Ví dụ kiểm thử chạy được với Spring Boot 3.5 và Java 17

Ví dụ sau minh họa cùng lúc ba trạng thái: thuộc tính không được khai báo, được đặt `true` và được đặt `false`. Ta tạo hai loại bean để so sánh:

- `StrictFeature`: chỉ xuất hiện khi Environment có `demo.feature.enabled=true`.
- `DefaultOnFeature`: xuất hiện khi Environment có `true` **hoặc key thiếu** nhờ `matchIfMissing=true`.

Cả hai cùng sử dụng một lớp `FeatureProperties` có Java default là `true`. Điều này làm lộ rõ việc object default và condition default là hai quyết định độc lập.

Cấu trúc thư mục:

```text
parameter-default-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── PropertyDefaultAndConditionTest.java
```

**Tệp `pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>parameter-default-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**Tệp `src/test/java/example/PropertyDefaultAndConditionTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class PropertyDefaultAndConditionTest {

    @ConfigurationProperties(prefix = "demo.feature")
    public static class FeatureProperties {
        private boolean enabled = true;

        public boolean isEnabled() {
            return this.enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }

    record StrictFeature() {}

    record DefaultOnFeature() {}

    @AutoConfiguration
    @EnableConfigurationProperties(FeatureProperties.class)
    static class FeatureAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true"
        )
        StrictFeature strictFeature() {
            return new StrictFeature();
        }

        @Bean
        @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
        )
        DefaultOnFeature defaultOnFeature() {
            return new DefaultOnFeature();
        }
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner().withConfiguration(
            AutoConfigurations.of(FeatureAutoConfiguration.class)
        );

    @Test
    void missingEnvironmentKeyDoesNotEraseJavaDefault() {
        runner.run(context -> {
            assertThat(context.getEnvironment()
                .containsProperty("demo.feature.enabled")).isFalse();
            assertThat(context.getEnvironment()
                .getProperty("demo.feature.enabled")).isNull();

            assertThat(context).hasSingleBean(FeatureProperties.class);
            assertThat(context.getBean(FeatureProperties.class)
                .isEnabled()).isTrue();

            assertThat(context).doesNotHaveBean(StrictFeature.class);
            assertThat(context).hasSingleBean(DefaultOnFeature.class);
        });
    }

    @Test
    void explicitTrueIsVisibleToBothBinderAndCondition() {
        runner.withPropertyValues("demo.feature.enabled=true")
            .run(context -> {
                assertThat(context.getEnvironment()
                    .getProperty("demo.feature.enabled"))
                    .isEqualTo("true");

                assertThat(context.getBean(FeatureProperties.class)
                    .isEnabled()).isTrue();

                assertThat(context).hasSingleBean(StrictFeature.class);
                assertThat(context).hasSingleBean(DefaultOnFeature.class);
            });
    }

    @Test
    void explicitFalseOverridesJavaDefaultAndDisablesFeatures() {
        runner.withPropertyValues("demo.feature.enabled=false")
            .run(context -> {
                assertThat(context.getEnvironment()
                    .getProperty("demo.feature.enabled"))
                    .isEqualTo("false");

                assertThat(context.getBean(FeatureProperties.class)
                    .isEnabled()).isFalse();

                assertThat(context).doesNotHaveBean(StrictFeature.class);
                assertThat(context).doesNotHaveBean(DefaultOnFeature.class);
            });
    }
}
```

Chạy tại thư mục chứa `pom.xml`, với JDK 17+ và Maven:

```bash
mvn test
```

**Kết quả mong đợi:** cả ba bài kiểm thử JUnit đều pass, Maven báo build thành công; test không in một chuỗi stdout riêng bằng `System.out.println`. Có thể kiểm tra kết quả trong log Surefire hoặc tệp báo cáo `target/surefire-reports`. Ví dụ dùng `ApplicationContextRunner` để tạo ApplicationContext riêng cho từng ca và tránh phụ thuộc vào cấu hình có sẵn của ứng dụng thật.

Giải thích từng ca:

1. **Thiếu key:** `Environment` xác nhận không tồn tại `demo.feature.enabled`. Binder giữ field initializer `enabled=true`. `StrictFeature` không được tạo vì mặc định `matchIfMissing=false`; `DefaultOnFeature` được tạo vì đã khai báo `matchIfMissing=true`.
2. **Có key `true`:** Environment có chuỗi `"true"`; binder chuyển sang boolean `true`; cả hai condition đều khớp.
3. **Có key `false`:** Environment có chuỗi `"false"`; binder ghi đè default Java thành `false`; cả hai condition đều không khớp.

Ví dụ đặt `@ConditionalOnProperty` trực tiếp trên từng phương thức `@Bean`, còn `@EnableConfigurationProperties` đăng ký bean cấu hình riêng. Như vậy ta kiểm chứng được rằng bean properties vẫn tồn tại ngay cả khi một bean nghiệp vụ bị điều kiện chặn.

## 5. Làm sao để chính sách default nhất quán?

### Cách A — Đồng bộ Java default và matchIfMissing (thường phù hợp với starter)

Nếu tính năng có default là **bật**, cặp khai báo có chủ đích là:

```java
// Trong @ConfigurationProperties:
private boolean enabled = true;

// Trên bean cần bật khi key thiếu:
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
```

Ngược lại, nếu default là **tắt**, field để `false` (hoặc Java default cho primitive boolean) và điều kiện thường để `matchIfMissing=false`. Đây là lựa chọn dễ đọc khi tính năng chỉ cần hành vi mặc định tại vị trí ra quyết định.

Điều này yêu cầu người bảo trì giữ hai chỗ khai báo thống nhất. Nếu một bên đổi default mà bên kia không đổi, các nhánh auto configuration có thể đi lệch nhau.

### Cách B — Đưa default vào nguồn cấu hình của Environment

Khi nhiều thành phần khác nhau đều phải đọc được default qua `Environment`, cần đăng ký default **thành một nguồn cấu hình thực sự**. Ví dụ trong ứng dụng:

```properties
# src/main/resources/application.properties
demo.feature.enabled=true
```

Khi file này được nạp, `environment.containsProperty("demo.feature.enabled")` có thể trả về `true` và `getProperty(...)` trả về `"true"`, trừ khi nguồn ưu tiên cao hơn ghi đè. Một cách khác cho ứng dụng do bạn khởi tạo là cung cấp default properties:

```java
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(DemoApplication.class);
        application.setDefaultProperties(Map.of("demo.feature.enabled", "true"));
        application.run(args);
    }
}
```

Đây là đoạn ví dụ **độc lập về ý tưởng** cho ứng dụng chính, không phải tệp thứ ba bắt buộc trong bài test ở mục 4. `setDefaultProperties` thêm một nguồn có mức ưu tiên mặc định; các nguồn cấu hình có độ ưu tiên cao hơn có thể ghi đè.

Hạn chế thực tế: một thư viện auto configuration không nên tùy tiện thay đổi Environment của ứng dụng sử dụng nó. Khi viết starter, `matchIfMissing` thường thể hiện default của condition gọn và đúng phạm vi hơn.

### Cách C — Dùng fallback ngay nơi đọc Environment

Với code cần đọc một giá trị bất kể key có được cấu hình hay không, có thể chủ động đặt fallback:

```java
boolean enabled = environment.getProperty(
    "demo.feature.enabled", Boolean.class, true
);
```

Trường hợp không có thuộc tính, câu lệnh trên trả về `true`. Nó **không đăng ký** `demo.feature.enabled` vào Environment. Với `@Value` cũng tương tự: `@Value("${demo.feature.enabled:true}")` dùng fallback cho vị trí inject đó.

Nếu định viết một `Condition` riêng, hãy quyết định rõ fallback dựa trên Environment; không cố gắng lấy default bằng cách khởi tạo sớm bean `@ConfigurationProperties` trong quá trình đánh giá điều kiện.

## 6. Các ngộ nhận thường gặp

1. **"Field đã khởi tạo `true` thì `@ConditionalOnProperty` phải thấy `true`."** Sai: field default thuộc object, condition đọc Environment. Nếu key thiếu, phải quyết định chính sách bằng `matchIfMissing` hoặc nguồn cấu hình thực sự.
2. **"`@DefaultValue("true")` trong record sẽ tự đưa key vào Environment."** Sai: annotation áp dụng trong lúc constructor binding, không tạo PropertySource.
3. **"`@Value("${demo.feature.enabled:true}")` chứng minh key tồn tại."** Sai: placeholder có fallback có thể tạo một giá trị inject ngay khi `getProperty("demo.feature.enabled")` vẫn `null`.
4. **"`@ConditionalOnProperty` mặc định chỉ khớp khi giá trị là boolean `true`."** Không chính xác: nếu `havingValue` để mặc định, điều kiện khớp khi key hiện diện và không bằng chuỗi `false`. Với công tắc boolean, viết `havingValue = "true"` giúp ý định rõ ràng.
5. **"`matchIfMissing=true` tương đương gán `enabled=true` vào bean."** Sai: thuộc tính này chỉ cho biết xử lý điều kiện thế nào khi key vắng mặt; nó không tham gia binding bean.
6. **"Giá trị `false` là thiếu key."** Sai: `demo.feature.enabled=false` là một key **có mặt** với giá trị `false`. `matchIfMissing=true` không ép điều kiện khớp trong trường hợp đó.
7. **"Thay đổi field bean properties lúc runtime sẽ tự tạo/hủy bean đã có điều kiện."** Không: điều kiện auto configuration được đánh giá lúc xây dựng context; thay đổi đối tượng sau đó không tự kích hoạt lại quá trình đăng ký bean.
8. **"Bất kỳ giá trị hiển thị trong `@ConfigurationProperties` đều là giá trị được khai báo trong application.yml."** Không: đó có thể là default do code đặt, kết quả chuyển đổi kiểu khi binding hoặc giá trị từ các PropertySource khác.
9. **"Dùng cùng default cho mọi bối cảnh mà không cần nghĩ tới nguồn."** Nếu code cần xuất giá trị qua Environment cho phần khác đọc, một field initializer có thể không đủ. Chọn cơ chế theo nơi tiêu thụ giá trị, đặc biệt đối với những condition cần hoạt động sớm trong vòng đời context.

## 7. Checklist khi sửa một auto configuration

1. **Xác định tên key đúng:** ví dụ `demo.feature.enabled`, đồng bộ giữa `@ConfigurationProperties(prefix="demo.feature")` và `@ConditionalOnProperty(prefix="demo.feature", name="enabled")`.
2. **Xác định mong muốn khi key thiếu:** bật, tắt hoặc phụ thuộc điều kiện khác; đặt `matchIfMissing` tương ứng.
3. **Kiểm tra default khi binder tạo object:** giá trị khởi tạo field hoặc `@DefaultValue` có thực sự phù hợp chính sách hay không?
4. **Phân biệt "thiếu", "true", "false":** viết kiểm thử cả ba trạng thái. Có thể thêm test cho giá trị không hợp lệ nếu config chịu validation hoặc được chuyển đổi theo kiểu boolean.
5. **Kiểm tra nguồn cấu hình thực tế:** `application.yml`, env var, CLI, test `withPropertyValues`, hoặc default properties có thể đưa key vào Environment mà không cần sửa lớp Java.
6. **Tránh phụ thuộc vào bean khi tính điều kiện:** điều kiện nên dựa trên thông tin có sẵn tại giai đoạn đăng ký bean; bean properties chưa chắc đã được khởi tạo/bind ở thời điểm đó.
7. **Ghi rõ hợp đồng của starter:** nếu thiếu thuộc tính mà tính năng mặc định bật, document cả giá trị object và cách condition chọn nhánh.

## 8. Câu hỏi tự kiểm tra

**Câu 1:** `FeatureProperties.enabled` mặc định `true`, không có `demo.feature.enabled`. `Environment#getProperty("demo.feature.enabled")` là gì?  
**Đáp án:** `null`; đối tượng đã bind vẫn có thể có `enabled=true`.

**Câu 2:** Trên `@Bean` có `@ConditionalOnProperty(prefix="demo.feature", name="enabled", havingValue="true")`. Bean có được tạo khi key thiếu?  
**Đáp án:** Không, vì `matchIfMissing` mặc định là `false`.

**Câu 3:** Thêm `matchIfMissing=true` và người dùng cấu hình `demo.feature.enabled=false`. Điều kiện có khớp?  
**Đáp án:** Không. `false` là giá trị hiện diện, không phải trường hợp thiếu key.

**Câu 4:** `@DefaultValue("true")` có giúp `@ConditionalOnProperty` đọc được `true` từ Environment không?  
**Đáp án:** Không. `@DefaultValue` chỉ cung cấp default cho binding.

**Câu 5:** Muốn `Environment#getProperty(...)` cũng trả về một default khi thiếu cấu hình từ người dùng, cần làm gì?  
**Đáp án:** Đưa default vào một `PropertySource` thực sự, ví dụ giá trị trong `application.properties` hoặc default properties của ứng dụng. Gọi `getProperty(key, type, default)` chỉ cung cấp fallback ở lần đọc đó; nó không thay đổi Environment.

## Tài liệu tham khảo chính thức

- Spring Boot Reference — Externalized Configuration, **Default Values** và **@DefaultValue and Binding**: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Creating Your Own Auto-configuration, **Property Conditions**: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot API — `ConditionalOnProperty` (Spring Boot 3.5): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html

**Ghi nhớ:** giá trị mặc định trong `@ConfigurationProperties` thuộc **đối tượng sau binding**. `@ConditionalOnProperty` dựa trên **thuộc tính của Environment**, vì thế muốn đồng bộ hành vi khi key thiếu phải chọn `matchIfMissing` thích hợp hoặc đưa default vào một PropertySource thực sự.
