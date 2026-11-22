# Tổ hợp dependency có mặt hoặc vắng mặt với tính năng bật hoặc tắt

## 1. Hai điều kiện độc lập quyết định integration có hoạt động hay không

Một Spring Boot starter có thể tích hợp với thư viện bên ngoài như SDK thanh toán, client gửi thông báo, codec, driver hoặc adapter. Thư viện nền có thể là dependency tùy chọn, trong khi auto-configuration của starter vẫn nằm trên classpath ứng dụng.

Khi thiết kế và kiểm thử, cần trả lời hai câu hỏi riêng:

1. **Dependency có mặt trên runtime classpath không?** Đây là điều kiện kỹ thuật: JVM có thể nạp và sử dụng các class mà integration cần hay không.
2. **Người vận hành có bật tính năng không?** Đây là điều kiện cấu hình: ứng dụng có chủ ý sử dụng integration ở môi trường hiện tại hay không.

Có thư viện trên classpath không có nghĩa ứng dụng muốn bật tính năng. Ngược lại, property bật tính năng không thể làm class còn thiếu xuất hiện trên classpath.

Spring Boot cung cấp hai condition thường dùng:

- `@ConditionalOnClass`: chỉ áp dụng cấu hình khi class cần thiết hiện diện.
- `@ConditionalOnProperty`: chỉ áp dụng cấu hình khi property đạt giá trị yêu cầu.

Khi đặt cả hai trên cùng một auto-configuration hoặc nested configuration, chúng kết hợp theo phép **AND**: cả hai phải khớp thì cấu hình đó mới được áp dụng.

Ví dụ, integration audit cần thư viện `com.acme.audit.AuditClient` và property `app.audit.enabled=true`. Bean mặc định chỉ được đăng ký khi đồng thời có class và feature được bật.

## 2. Ma trận 2 × 2 cần kiểm thử

Giả sử chính sách của ví dụ là:

- Dependency `AuditClient` là tùy chọn.
- Feature được bật bằng `app.audit.enabled=true`.
- Nếu property không được khai báo, feature mặc định bật vì `matchIfMissing=true`.
- Nếu dependency thiếu, integration không được tạo dù property đang bật.

Ma trận chính:

| Dependency trên classpath | Feature property | Kết quả auto-configuration |
| --- | --- | --- |
| Có | `true` | Khớp cả hai điều kiện; tạo bean mặc định nếu chưa có bean user |
| Có | `false` | Property condition không khớp; không tạo bean mặc định |
| Không | `true` | Class condition không khớp; không tạo bean |
| Không | `false` | Cả hai condition không khớp; không tạo bean |

Có thể đọc ma trận theo hai trục:

- **Dependency có mặt:** property quyết định feature được bật hay tắt.
- **Dependency vắng mặt:** feature không thể hoạt động; bật property cũng không tạo ra dependency cần thiết.

Một trường hợp bổ sung phải được kiểm thử là property bị bỏ trống. Với `matchIfMissing=true`, class có mặt và property không khai báo vẫn tạo bean. Nếu chính sách sản phẩm là mặc định tắt, đặt `matchIfMissing=false` và kiểm thử kỳ vọng ngược lại.

### 2.1. Bốn trạng thái khác nhau về ý nghĩa

**Có dependency + bật feature:** đường chạy bình thường. Auto-configuration có thể tạo bean và ứng dụng có thể inject nó.

**Có dependency + tắt feature:** thư viện vẫn nằm trên classpath, nhưng bean integration không được đăng ký. Ứng dụng có thể dùng thư viện đó theo cách khác; property chỉ điều khiển auto-configuration đang xét.

**Thiếu dependency + bật feature:** class condition chặn integration. Ví dụ bên dưới chọn chính sách bỏ qua bean và cho context tiếp tục khởi động. Nếu sản phẩm yêu cầu bật feature mà thiếu thư viện phải là lỗi cấu hình, cần thiết kế kiểm tra fail-fast riêng và test startup failure.

**Thiếu dependency + tắt feature:** không có lý do để khởi tạo integration; bean không xuất hiện.

Không nên gộp hai trạng thái "không có bean" thành một kết luận duy nhất. Test cần biết bean vắng mặt vì property tắt hay vì thư viện không có. Nếu không phân biệt nguyên nhân, một starter có thể vô tình che giấu lỗi đóng gói dependency.

## 3. Cấu hình auto-configuration an toàn với dependency tùy chọn

Ví dụ dùng Spring Boot 3.5.0 và Java 17. Giả sử thư viện bên ngoài cung cấp interface `AuditClient`. Starter có thể tạo implementation mặc định khi class hiện diện và feature được bật.

### 3.1. Đặt class condition ở nested configuration

```java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.audit.AuditClient")
    @ConditionalOnProperty(
            prefix = "app.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    static class AuditClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AuditClient auditClient() {
            return new DefaultAuditClient();
        }
    }
}
```

Đây là snippet kiến trúc. `AuditClient` và `DefaultAuditClient` thuộc thư viện ví dụ, không phải class Spring Boot.

Nested configuration quan trọng vì auto-configuration bên ngoài không cần trực tiếp tham chiếu optional type trong method signature. Spring Boot có thể đọc metadata của nested configuration và bỏ qua nó khi class không có trên classpath.

Không đặt method có return type là optional class ngay trên cấu hình gốc rồi chỉ gắn `@ConditionalOnClass` lên chính `@Bean` method. JVM có thể phải nạp/kiểm tra kiểu trả về và method references trước khi method condition được áp dụng. Khi dependency thực sự vắng mặt, điều đó có thể dẫn tới lỗi linkage. Tách cấu hình con là cách cô lập reference tới optional type.

### 3.2. Vai trò của từng annotation

| Annotation | Câu hỏi | Tác động khi không khớp |
| --- | --- | --- |
| `@ConditionalOnClass` | Thư viện cần thiết có trên classpath không? | Bỏ qua nested configuration |
| `@ConditionalOnProperty` | Feature có được bật theo property không? | Bỏ qua nested configuration |
| `@ConditionalOnMissingBean` | Ứng dụng đã cung cấp bean thay thế chưa? | Không tạo bean mặc định |

`@ConditionalOnMissingBean` là điều kiện thứ ba trong ví dụ. Nó cho phép ứng dụng tự cung cấp `AuditClient`; khi đó auto-configuration không tạo thêm bean mặc định. Điều kiện này không thay thế classpath condition hay feature flag.

### 3.3. Hiểu chính xác havingValue và matchIfMissing

Với khai báo:

```java
@ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
```

kết quả là:

| Giá trị `app.audit.enabled` | Condition |
| --- | --- |
| `true` | Khớp |
| `false` | Không khớp |
| `yes` | Không khớp với `havingValue="true"` |
| Không khai báo | Khớp vì `matchIfMissing=true` |

Nếu bỏ `havingValue`, property hiện diện và khác `false` có thể được xem là khớp. Với feature flag boolean, nên ghi rõ `havingValue="true"` để hợp đồng dễ đọc và tránh chấp nhận các giá trị không mong muốn.

`matchIfMissing` là quyết định sản phẩm, không phải chi tiết trang trí:

- `true`: thiếu property được hiểu là bật theo mặc định.
- `false`: thiếu property được hiểu là không bật.

Hãy chọn một chính sách và viết test cho trường hợp property vắng mặt. Không suy luận default từ giá trị khởi tạo của một `@ConfigurationProperties` object; condition đọc `Environment`, còn binder khởi tạo object là cơ chế khác.

## 4. Viết test theo ma trận bằng ApplicationContextRunner

`ApplicationContextRunner` giúp tạo context nhỏ cho từng tổ hợp. Ta nạp đúng auto-configuration cần kiểm tra, thay đổi property và classloader theo từng test, sau đó xác nhận bean có hoặc không có.

Các lợi ích chính:

- Mỗi lần `run(...)` tạo một context riêng và đóng context sau callback.
- Không cần khởi động toàn bộ ứng dụng hoặc web server.
- Có thể thay property theo từng test.
- Có thể giả lập dependency bị thiếu bằng `FilteredClassLoader`.
- Assertion tập trung vào kết quả đăng ký bean và điều kiện.

### 4.1. Cấu trúc project

```text
audit-feature-matrix/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── example/
    │           ├── AuditClient.java
    │           └── AuditAutoConfiguration.java
    └── test/
        └── java/
            └── example/
                └── AuditAutoConfigurationTests.java
```

Trong starter thực tế, class auto-configuration còn được đăng ký trong file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Test dưới đây truyền trực tiếp class vào `AutoConfigurations.of(...)`, vì mục tiêu là kiểm thử điều kiện của class đó.

### 4.2. Tệp pom.xml

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
    <artifactId>audit-feature-matrix</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-autoconfigure` cung cấp annotation và condition cho code cấu hình. `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ, `ApplicationContextRunner` và `FilteredClassLoader`.

### 4.3. Tệp src/main/java/example/AuditClient.java

```java
package example;

public interface AuditClient {
    String serviceName();
}
```

### 4.4. Tệp src/main/java/example/AuditAutoConfiguration.java

```java
package example;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class AuditAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "example.AuditClient")
    @ConditionalOnProperty(
            prefix = "app.audit",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
    )
    static class AuditClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(AuditClient.class)
        AuditClient auditClient() {
            return new DefaultAuditClient("catalog-service");
        }
    }

    private record DefaultAuditClient(String serviceName)
            implements AuditClient {
    }
}
```

Trong ứng dụng thật, `AuditClient` thường đến từ dependency tùy chọn. Ở project demo này, interface được đặt trong `src/main/java` để project biên dịch được; `FilteredClassLoader` sẽ ẩn class khỏi context test để giả lập ứng dụng không có thư viện.

### 4.5. Tệp src/test/java/example/AuditAutoConfigurationTests.java

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AuditAutoConfiguration.class)
                    );

    @Test
    void dependencyPresentAndFeatureEnabledCreatesBean() {
        runner.withPropertyValues("app.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditClient.class);

                    AuditClient client = context.getBean(AuditClient.class);
                    assertThat(client.serviceName())
                            .isEqualTo("catalog-service");
                });
    }

    @Test
    void dependencyPresentAndFeatureDisabledSkipsBean() {
        runner.withPropertyValues("app.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean("auditClient");
                });
    }

    @Test
    void dependencyMissingAndFeatureEnabledSkipsBean() {
        runner.withClassLoader(new FilteredClassLoader(AuditClient.class))
                .withPropertyValues("app.audit.enabled=true")
                .run(context -> {
                    assertThat(context).doesNotHaveBean("auditClient");
                });
    }

    @Test
    void dependencyMissingAndFeatureDisabledSkipsBean() {
        runner.withClassLoader(new FilteredClassLoader(AuditClient.class))
                .withPropertyValues("app.audit.enabled=false")
                .run(context -> {
                    assertThat(context).doesNotHaveBean("auditClient");
                });
    }

    @Test
    void missingPropertyUsesTheDocumentedDefault() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AuditClient.class);
        });
    }
}
```

### 4.6. Chạy test

Tại thư mục có `pom.xml`, dùng JDK 17+ và Maven:

```bash
java -version
mvn -version
mvn test
```

**Kết quả mong đợi:** năm test JUnit pass và Maven kết thúc bằng `BUILD SUCCESS` nếu dependency tải thành công. Code không gọi `System.out.println`, vì vậy không có stdout nghiệp vụ cố định. Báo cáo chi tiết được ghi trong `target/surefire-reports`.

Đây là kết quả kỳ vọng từ code mẫu, chưa phải kết quả chạy thực tế. Khi áp dụng vào project, hãy chạy test với dependency và phiên bản đúng của starter.

## 5. Đọc kết quả test và ConditionEvaluationReport

Bốn test đầu tiên tương ứng trực tiếp với ma trận 2 × 2:

| Test | Class bị ẩn? | Property | Kết quả |
| --- | --- | --- | --- |
| `dependencyPresentAndFeatureEnabledCreatesBean` | Không | `true` | Có bean |
| `dependencyPresentAndFeatureDisabledSkipsBean` | Không | `false` | Không có bean |
| `dependencyMissingAndFeatureEnabledSkipsBean` | Có | `true` | Không có bean |
| `dependencyMissingAndFeatureDisabledSkipsBean` | Có | `false` | Không có bean |

Test thứ năm kiểm tra default property. Vì `matchIfMissing=true`, khi dependency hiện diện nhưng key chưa khai báo, bean mặc định vẫn được tạo.

Không chỉ assert context khởi động thành công. Hãy assert bean theo tên hoặc type và kiểm tra giá trị quan trọng. Một context có thể khởi động bình thường dù auto-configuration đã bị bỏ qua hoàn toàn.

### 5.1. Vì sao dùng tên bean trong test thiếu class?

Ở test dependency thiếu, `AuditClient` không khả dụng đối với classloader của context. Vì vậy, assertion `doesNotHaveBean("auditClient")` tránh phải yêu cầu context resolve lại kiểu optional đó. Ở test dependency có mặt, có thể assert theo type và kiểm tra hành vi bean.

### 5.2. Xem lý do condition khớp hoặc không khớp

Khi test không có kết quả như mong đợi, có thể thêm listener để in `ConditionEvaluationReport`:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO)
                )
                .withConfiguration(
                        AutoConfigurations.of(AuditAutoConfiguration.class)
                );
```

Báo cáo giúp xác định condition nào khớp, condition nào không khớp và lý do. Nó hữu ích khi nhiều class conditions hoặc property conditions kết hợp với nhau. Trong test thường ngày, chỉ bật listener khi cần chẩn đoán để log không quá dài.

## 6. Chính sách khi feature được bật nhưng dependency bị thiếu

Ma trận phía trên chọn chính sách **graceful skip**: dependency không có thì integration không được đăng ký, kể cả khi property là `true`. Đây là hành vi phù hợp khi integration thực sự tùy chọn và ứng dụng có thể hoạt động mà không cần nó.

Một sản phẩm khác có thể yêu cầu **fail fast**: người dùng đã chủ động bật feature nhưng thiếu thư viện thì startup phải thất bại với thông báo rõ ràng. Hai chính sách có ý nghĩa vận hành khác nhau:

| Chính sách | Dependency thiếu + property `true` | Phù hợp khi |
| --- | --- | --- |
| Graceful skip | Không tạo bean; context vẫn có thể chạy | Feature tùy chọn, ứng dụng có fallback hoặc không dùng integration |
| Fail fast | Context thất bại với lỗi cấu hình rõ ràng | Feature được bật là yêu cầu bắt buộc để ứng dụng hoạt động đúng |

Nếu chọn fail fast, đừng để lỗi xuất hiện ngẫu nhiên dưới dạng `NoClassDefFoundError` khi một bean khác được khởi tạo. Hãy thiết kế kiểm tra cấu hình có chủ đích, không tham chiếu optional type trong class cần nạp sớm, và viết test riêng xác nhận startup failure cùng thông báo hữu ích.

Không nên viết test yêu cầu fail-fast trong khi cấu hình chỉ có `@ConditionalOnClass`: annotation đó được thiết kế để bỏ qua nhánh khi class vắng mặt. Test phải phản ánh chính sách đã chọn.

## 7. Kết hợp với bean do người dùng cung cấp

Hai điều kiện classpath và property quyết định nested configuration có được áp dụng hay không. `@ConditionalOnMissingBean` lại quyết định có tạo bean mặc định trong cấu hình đó không.

Ví dụ, ứng dụng có thể tự cung cấp `AuditClient`:

```java
@Configuration(proxyBeanMethods = false)
class UserAuditConfiguration {

    @Bean
    AuditClient customAuditClient() {
        return () -> "custom-audit";
    }
}
```

Khi dependency có mặt, feature bật và user bean đã được đăng ký, auto-configuration không tạo `auditClient` mặc định. Bean user vẫn tồn tại.

Cần phân biệt:

- Feature property tắt bean do auto-configuration tạo.
- `@ConditionalOnMissingBean` cho phép bean user thay thế bean mặc định.
- Classpath condition ngăn cấu hình tích hợp được áp dụng khi dependency thiếu.

Không dùng feature flag như một cơ chế xóa mọi bean cùng kiểu trong context. Nó chỉ điều khiển configuration/bean được gắn condition đó.

## 8. Những lỗi thường gặp khi kiểm thử tổ hợp dependency và feature flag

1. **Chỉ test dependency có mặt và feature bật.** Cấu hình có thể hoạt động ở happy path nhưng chưa chứng minh nhánh tắt hoặc dependency vắng mặt.
2. **Cho rằng property true đảm bảo feature chạy.** Property không thêm thư viện vào classpath; class condition vẫn có thể không khớp.
3. **Cho rằng dependency có mặt tự bật feature.** Feature flag có thể mặc định tắt nếu `matchIfMissing=false`.
4. **Không quyết định rõ default khi property thiếu.** Đặt `matchIfMissing` có chủ đích và có test cho key vắng mặt.
5. **Dùng `@ConditionalOnClass` trên `@Bean` method nhưng optional type nằm trong return signature.** Tách nested configuration để tránh class loading trước khi method condition được áp dụng.
6. **Chỉ kiểm tra số lượng bean.** Assert cả bean name/type và hành vi quan trọng để biết đúng bean nào được tạo.
7. **Dùng cùng một context cho nhiều tổ hợp.** Mỗi scenario cần context riêng; dùng nhiều lần `runner.with...().run(...)`.
8. **Dùng mock thay cho classpath filtering.** Mock bean kiểm tra dependency injection; nó không mô phỏng thư viện bị thiếu. Dùng `FilteredClassLoader` cho nhánh classpath.
9. **Không kiểm tra property có giá trị lạ.** Với `havingValue="true"`, giá trị như `yes` không tương đương `true`; thêm test nếu cấu hình có thể nhận giá trị không chuẩn.
10. **Để auto-configuration tự quét quá rộng trong test.** Dùng `AutoConfigurations.of(...)` để nạp nhóm cần kiểm tra và tránh điều kiện không liên quan.
11. **Không kiểm tra condition report khi test thất bại.** `ConditionEvaluationReport` giúp tìm condition không khớp.
12. **Nhầm bean user với bean mặc định.** Khi kiểm tra back-off, xác nhận bean user tồn tại và bean mặc định không được đăng ký.
13. **Kết luận graceful skip là fail-fast.** Nếu yêu cầu startup thất bại khi dependency thiếu, cần một chính sách và test riêng.
14. **Chỉ test trong module autoconfigure có dependency test luôn hiện diện.** Bổ sung test classpath bằng `FilteredClassLoader` và, nếu cần, một consumer sample thật sự không khai báo optional dependency.

## 9. Checklist trước khi phát hành starter có integration tùy chọn

- [ ] Xác định thư viện nào là dependency bắt buộc và thư viện nào là optional.
- [ ] Chọn tên feature property rõ ràng và tài liệu hóa giá trị mặc định.
- [ ] Đặt `@ConditionalOnClass` để bảo vệ integration cần thư viện ngoài.
- [ ] Đặt `@ConditionalOnProperty` để điều khiển feature theo cấu hình.
- [ ] Cô lập optional type trong nested configuration khi cần.
- [ ] Đặt `@ConditionalOnMissingBean` nếu ứng dụng được phép thay bean mặc định.
- [ ] Kiểm thử đủ bốn tổ hợp dependency có/không và feature bật/tắt.
- [ ] Kiểm thử riêng trường hợp property không khai báo.
- [ ] Kiểm thử bean user và hành vi back-off nếu starter hỗ trợ override.
- [ ] Quyết định dependency thiếu khi feature bật là graceful skip hay fail fast.
- [ ] Kiểm tra condition report khi kết quả không như mong đợi.
- [ ] Kiểm tra runtime classpath của consumer thực tế; test classloader không thay thế kiểm tra dependency graph đã publish.
- [ ] Chạy test trên phiên bản Spring Boot được starter hỗ trợ.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao phải kiểm thử cả classpath và feature property?  
**Đáp án:** Classpath cho biết integration có thể được nạp; property cho biết ứng dụng có muốn bật nó. Đây là hai điều kiện độc lập.

**Câu 2.** Dependency có mặt và property `false` thì điều gì xảy ra?  
**Đáp án:** Class condition khớp nhưng property condition không khớp, nên bean mặc định của integration không được tạo.

**Câu 3.** Dependency thiếu nhưng property `true` thì `@ConditionalOnClass` có cho bean xuất hiện không?  
**Đáp án:** Không. Class condition không khớp; property không thể thay thế dependency còn thiếu.

**Câu 4.** `matchIfMissing=true` có nghĩa gì?  
**Đáp án:** Khi property không có trong Environment, property condition vẫn khớp. Đây là chính sách mặc định bật trong ví dụ.

**Câu 5.** Vì sao dùng nested configuration cho optional dependency?  
**Đáp án:** Nó cô lập method signature và reference tới optional type, cho phép class condition loại bỏ cấu hình trước khi JVM phải nạp các kiểu đó.

**Câu 6.** `FilteredClassLoader` dùng để làm gì?  
**Đáp án:** Giả lập một class hoặc package không có trên classpath của context test để kiểm tra nhánh `@ConditionalOnClass`.

**Câu 7.** `@ConditionalOnMissingBean` có giống `@ConditionalOnClass` không?  
**Đáp án:** Không. Một condition kiểm tra classpath; condition còn lại kiểm tra bean đã có trong BeanFactory.

**Câu 8.** Nếu dependency thiếu nhưng feature được bật mà sản phẩm yêu cầu startup thất bại, chỉ dùng `@ConditionalOnClass` có đủ không?  
**Đáp án:** Không. `@ConditionalOnClass` sẽ bỏ qua cấu hình. Cần thiết kế fail-fast riêng và test startup failure.

## Tài liệu tham khảo chính thức

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, class/property/bean conditions và testing: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 API — `ConditionalOnClass`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.5 API — `ConditionalOnProperty`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.5 API — `FilteredClassLoader`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.5 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Boot 3.5 Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html

**Ghi nhớ:** Hãy kiểm thử hai trục riêng: dependency có/không và feature bật/tắt. `@ConditionalOnClass` bảo vệ khả năng nạp integration; `@ConditionalOnProperty` thể hiện lựa chọn vận hành. Chỉ khi cả hai condition khớp, auto-configuration mới tạo bean mặc định; kiểm thử đủ ma trận giúp phát hiện lỗi classpath và cấu hình trước khi phát hành starter.
