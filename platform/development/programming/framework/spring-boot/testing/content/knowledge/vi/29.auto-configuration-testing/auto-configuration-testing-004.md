# withPropertyValues và ma trận điều kiện cấu hình

Trong nhóm **Kiểm thử auto-configuration** của module **Spring Boot - testing**, việc một bean được tạo hay không thường phụ thuộc vào nhiều điều kiện: property có tồn tại không, giá trị là `true` hay `false`, có bean người dùng định nghĩa sẵn không, có thư viện tùy chọn trên classpath không, hoặc ứng dụng là web/không web. Nếu chỉ khởi động một `@SpringBootTest` với cấu hình mặc định và thấy bean xuất hiện, ta chưa biết auto-configuration có **tắt đúng lúc**, **bật đúng giá trị**, **nhường chỗ cho custom bean** và **không rò cấu hình giữa các test case** hay không.

**`ApplicationContextRunner.withPropertyValues(...)`** cho phép đưa các cặp `key=value` vào `Environment` của **một test context nhỏ, mới**, sau đó kiểm tra bean có xuất hiện và cấu hình của bean có đúng không. Kết hợp nhiều lần chạy runner với **ma trận điều kiện**, ta có bằng chứng rõ ràng cho các nhánh `missing / false / true / invalid value / default / custom override` mà không phải dựng nguyên ứng dụng hoặc sửa cấu hình hệ thống thật.

Mục tiêu bài học:

1. Hiểu `ApplicationContextRunner`, `AutoConfigurations.of(...)`, `withConfiguration(...)` và `withPropertyValues(...)` làm gì.
2. Thiết kế ma trận cho `@ConditionalOnProperty` gồm `prefix`, `name`, `havingValue`, `matchIfMissing`; phân biệt **thuộc tính vắng mặt** với **thuộc tính có mặt nhưng giá trị rỗng/sai**.
3. Viết auto-configuration mẫu chỉ tạo `DeliveryClient` khi `lesson.delivery.enabled=true`, mặc định `transport=http` và **không có bean `DeliveryClient` người dùng cung cấp**.
4. Dùng `@ConfigurationProperties` để kiểm tra property binding độc lập với điều kiện tạo bean.
5. Dùng `withUserConfiguration(...)` để chứng minh `@ConditionalOnMissingBean` tự động back off.
6. Kiểm tra startup failure và đọc **ConditionEvaluationReport** khi khó hiểu vì sao điều kiện match hoặc không match.
7. Phân biệt `ApplicationContextRunner` với `@SpringBootTest`, `@TestPropertySource`, `@DynamicPropertySource` và các runner web/reactive.
8. Đọc đúng kết luận: một context nhỏ xanh chứng minh condition/bean registration trong cấu hình được dựng, **không chứng minh HTTP, broker, DB hoặc toàn bộ production wiring**.

Bài sử dụng **Java 17+, Spring Boot 3.5.x, JUnit Jupiter 5, AssertJ/JUnit assertions**. Phần thực hành có một module Java/Gradle hoàn chỉnh với auto-configuration và các JUnit tests; thêm một Java SE demo chạy bằng `javac/java` có stdout chính xác để hiểu logic ma trận (không thay thế Spring runner tests).

## 1. Auto-configuration thực sự là gì?

Spring Boot auto-configuration là các class `@AutoConfiguration` (hoặc cấu hình được Spring Boot nhập theo cơ chế phù hợp) chỉ đăng ký beans **khi các điều kiện được thỏa**. Mẫu phổ biến của một starter:

```text
Application startup
        |
        v
Spring Environment + user-defined beans + classpath
        |
        v
Auto-configuration condition evaluation
        |
        +-- Property enabled?
        +-- Optional library present?
        +-- Required bean present/absent?
        +-- Web application type appropriate?
        |
        v
Register default infrastructure beans
        |
        v
User application can inject/customize them
```

Một cấu hình thực tế có thể dùng:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "lesson.delivery",
        name = "enabled",
        havingValue = "true")
class DeliveryAutoConfiguration {
    // Các @Bean methods có điều kiện bổ sung.
}
```

Đây là **snippet**, chưa phải file runnable: cần imports, beans và các class thực tế. File hoàn chỉnh ở mục sau.

**Hai nguyên tắc:**

- Auto-configuration không phải cách cưỡng chế tạo bean bất kể ứng dụng muốn gì. Với `@ConditionalOnMissingBean`, default bean phải **nhường chỗ** cho bean người dùng.
- Condition evaluation chủ yếu xảy ra **khi tạo ApplicationContext**. Thay đổi một property sau khi context đã refresh **không có nghĩa Spring sẽ tự tạo/xóa bean** tương ứng. Muốn kiểm tra một cấu hình mới, tạo context mới qua runner.

Vì vậy một ma trận test phải có **một context riêng cho từng scenario**, thay vì gọi `System.setProperty(...)` trong khi cùng một Spring context đã khởi tạo.

## 2. ApplicationContextRunner tạo context thế nào?

Mẫu khởi tạo tối thiểu:

```java
private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(
                                DeliveryAutoConfiguration.class));
```

Ý nghĩa:

- `new ApplicationContextRunner()`: chuẩn bị builder cho context **không web**.
- `AutoConfigurations.of(...)`: đưa class auto-configuration vào theo cơ chế/order auto-config; không đồng nhất với cấu hình người dùng.
- `withConfiguration(...)`: gắn tập auto-config được test vào runner.
- `withPropertyValues("lesson.delivery.enabled=true")`: tạo biến thể runner với property tương ứng.
- `run(context -> { ... })`: tạo và refresh một `ApplicationContext`, chạy callback để assert, sau đó đóng context theo lifecycle của runner.
- `withUserConfiguration(CustomConfig.class)`: thêm cấu hình do người dùng cung cấp để xem auto-config có back off hay không.
- `withBean(...)`: tùy biến runner bằng một user bean trực tiếp khi không cần class cấu hình.
- `withClassLoader(...)`: mô phỏng một class/library bị thiếu; hữu ích cho `@ConditionalOnClass`.

**Điểm khác với full integration test:** `ApplicationContextRunner` không dùng nguyên một SpringBootApplication rồi quét toàn bộ business code mặc định. Nó tập trung vào một auto-configuration và các thành phần tối thiểu mà test khai báo; vì vậy nhanh và dễ cô lập.

Tài liệu Spring Boot ghi rõ context runner **không hoạt động khi test chạy như native image**. Với native/AOT cần kế hoạch kiểm thử riêng; không dùng runner xanh trên JVM để tuyên bố native registration/graal reflection đầy đủ.

## 3. withPropertyValues: cú pháp và hành vi cần hiểu

Cú pháp:

```java
runner.withPropertyValues(
        "lesson.delivery.enabled=true",
        "lesson.delivery.transport=http",
        "lesson.delivery.endpoint=https://demo.invalid/send"
).run(context -> {
    // Các assertions khi context còn sống.
});
```

Đây là **snippet** dùng `runner` đã cấu hình và cần imports.

**Các điểm kỹ thuật quan trọng:**

- Mỗi phần tử là một chuỗi dạng `name=value`; đây là các **test property pairs**.
- `withPropertyValues(...)` gắn property source vào môi trường context được runner tạo; bạn không cần ghi `application.properties`, sửa biến môi trường hay gọi `System.setProperty` toàn cục.
- Các giá trị property đưa vào test có thể override default property tương ứng từ những nguồn có độ ưu tiên thấp hơn; nếu nhiều lần cấu hình cùng một key, cần biết quy tắc ghi đè của runner trong trường hợp đó.
- Dùng **tên canonical kebab-case** như `lesson.delivery.enabled` và `lesson.delivery.transport`; Spring Boot có relaxed binding trong các ngữ cảnh, nhưng không nên thử với những alias ngẫu nhiên rồi phụ thuộc vào hành vi version.
- Khi cần thử **missing key**, **không truyền cặp đó** vào runner; đừng viết `key=null` rồi xem nó là Java null/vắng mặt. Chuỗi `"null"` là dữ liệu text.
- Khi cần thử **present-but-empty**, dùng `"lesson.delivery.transport="`; đây là khác biệt có chủ đích với missing.
- Không tạo danh sách properties dựa trên trạng thái global chia sẻ mà không reset; ma trận nên ghi rõ từng vector input.

**Context runner là builder**: các lời gọi tạo biến thể runner; thực hành an toàn là giữ một `private final ApplicationContextRunner runner` baseline rồi mỗi method gọi `runner.withPropertyValues(...).run(...)`. Không gán lại field baseline giữa các test hoặc trông chờ methods chạy theo thứ tự.

## 4. @ConditionalOnProperty: bảng chân trị

Một điều kiện:

```java
@ConditionalOnProperty(
        prefix = "lesson.delivery",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
```

Kiểm tra property full name `lesson.delivery.enabled`. Vì `havingValue="true"`, giá trị cần khớp “true” theo semantics string của Spring Boot; `false`, `0`, `off` hay giá trị trống **không được coi là true** ở condition này. Khi key không có, `matchIfMissing=false` khiến điều kiện không match.

Bảng minh họa:

| Property input | Có key? | `havingValue="true"` | Bean được tạo nếu điều kiện khác đạt? |
| --- | --- | --- | --- |
| Không truyền property | Không | Không match theo `matchIfMissing=false` | Không |
| `enabled=true` | Có | Match | Có |
| `enabled=TRUE` | Có | Match theo so sánh không phân biệt hoa thường | Có |
| `enabled=false` | Có | Không match | Không |
| `enabled=0` | Có | Không match | Không |
| `enabled=yes` | Có | Không match | Không |
| `enabled=` | Có | Không match | Không |
| `enabled=null` (literal text) | Có | Không match | Không |

**Đừng nhầm với `@ConditionalOnProperty` không khai báo `havingValue`.** Khi `havingValue=""` mặc định, điều kiện xét property có mặt và giá trị **không phải `false`**; một chuỗi lạ như `"maybe"` có thể vẫn match. Vì thế khi muốn một feature flag thực sự chỉ bật bằng `true`, hãy ghi `havingValue="true"` tường minh và test cả những giá trị khác.

**`matchIfMissing=true` không có nghĩa mọi giá trị rỗng đều được chấp nhận.** Nó chỉ định kết quả nếu **không tìm thấy property**. Nếu property có mặt với giá trị sai `havingValue`, điều kiện vẫn fail.

### Nếu có nhiều property names?

```java
@ConditionalOnProperty(
        prefix = "lesson.delivery",
        name = {"enabled", "secure"},
        havingValue = "true")
```

Đây là snippet. Với nhiều names, **tất cả** cần match; chỉ có `enabled=true` mà thiếu `secure` không đủ. Nếu cần logic `OR`, không cố giả định nhiều names nghĩa OR; dùng composition hoặc custom `Condition`/config structure phù hợp.

**Cảnh báo collection:** `@ConditionalOnProperty` không phải công cụ đáng tin để kiểm tra sự hiện diện của các property **collection-index keys** như `lesson.allowed[0]`. Nếu contract phụ thuộc collection, kiểm tra bằng typed properties/custom condition hoặc cơ chế tương ứng.

## 5. Thiết kế ma trận hai điều kiện: enabled × transport

Trong ví dụ chính, ta muốn:

- Toàn bộ auto-config chỉ hoạt động khi `lesson.delivery.enabled=true`.
- Bean mặc định HTTP được tạo nếu `transport` **không có** hoặc bằng `http`.
- Nếu `transport=grpc` hay empty, auto-config không tạo HTTP bean.
- Nếu người dùng đã khai báo một `DeliveryClient` thì `@ConditionalOnMissingBean` phải nhường chỗ.
- Nếu enabled=true và endpoint được cung cấp, `DeliveryProperties.endpoint` được bind và truyền vào bean.

Bảng:

| `enabled` | `transport` | User `DeliveryClient`? | Kỳ vọng bean |
| --- | --- | --- | --- |
| Missing | Missing | Không | Không có |
| false | Missing | Không | Không có |
| true | Missing | Không | HTTP mặc định |
| true | http | Không | HTTP mặc định |
| true | grpc | Không | Không có |
| true | empty | Không | Không có |
| 0 | http | Không | Không có |
| true | http | Có | **Custom bean**, không sinh HTTP default |
| false | http | Có | **Custom bean vẫn có** vì nó do user tạo |

Hàng cuối rất quan trọng. Một `@ConditionalOnProperty` áp trên **auto-config class** không được làm Spring xóa bean người dùng chỉ vì auto-config không match. Nó chỉ quyết định bean do auto-config cung cấp.

**Ma trận có giá trị hơn “test enabled=true”**: nó bảo vệ positive path, negative path, default, sai giá trị và precedence của cấu hình người dùng. Khi thêm một điều kiện mới, test matrix phải được cập nhật thay vì chỉ thêm một happy-path test.

## 6. Project Java 17 đầy đủ để tự chạy

Đây là một **module thư viện auto-configuration**, không cần web server, database hay một `@SpringBootApplication`. Bài dùng Gradle `java` plugin và Spring Boot BOM để các imports có cùng version.

```text
delivery-autoconfig/
├── build.gradle
├── src/main/
│   ├── java/example/delivery/
│   │   ├── DeliveryClient.java
│   │   ├── HttpDeliveryClient.java
│   │   ├── DeliveryProperties.java
│   │   ├── DeliveryAutoConfiguration.java
│   │   └── ConditionMatrixDemo.java
│   └── resources/META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── src/test/java/example/delivery/
    └── DeliveryAutoConfigurationTest.java
```

### 6.1. build.gradle

Tạo `build.gradle`:

```groovy
plugins {
    id 'java'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
            'org.springframework.boot:spring-boot-dependencies:3.5.0')
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    testImplementation platform(
            'org.springframework.boot:spring-boot-dependencies:3.5.0')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Giải thích:**

- `java` plugin đủ để compile Java library và chạy JUnit; không bắt buộc `org.springframework.boot` Gradle plugin vì bài không đóng gói ứng dụng executable bootJar.
- BOM Spring Boot 3.5.0 là một mốc tương thích của nhánh 3.5; trong dự án thật nên dùng bản vá 3.5.x mới nhất theo chính sách bảo mật và tương thích.
- `spring-boot-autoconfigure` cung cấp `@AutoConfiguration`, các condition annotations; phụ thuộc Spring context/core transitively.
- `spring-boot-starter-test` cung cấp JUnit Jupiter, Spring Boot test runner, assertions và các thư viện test phổ biến.
- `junit-platform-launcher` giúp Gradle JUnit Platform hoạt động ổn định theo version của BOM.
- Không cần Docker/Testcontainers, HTTP socket hoặc datasource để kiểm tra điều kiện tạo bean.

Nếu project sử dụng Spring Boot Gradle plugin sẵn, chỉ cần thêm dependencies phù hợp và không khai báo chồng nhiều BOM phiên bản khác nhau. Với Spring Boot 4.x, API/packages test modules và configuration có thể thay đổi; kiểm tra đúng tài liệu của version thực tế.

## 7. DeliveryClient.java: hợp đồng bean mặc định

Tạo `src/main/java/example/delivery/DeliveryClient.java`:

```java
package example.delivery;

public interface DeliveryClient {
    String endpoint();
}
```

Đây là một interface nhỏ, không thực hiện network IO. Nó đóng vai trò dependency mà auto-configuration có thể cung cấp mặc định hoặc người dùng tự định nghĩa. **Test nhận bean thành công không đồng nghĩa đã kết nối tới HTTP endpoint**; chủ đề chỉ là registration/property binding.

### HttpDeliveryClient.java

Tạo `src/main/java/example/delivery/HttpDeliveryClient.java`:

```java
package example.delivery;

public record HttpDeliveryClient(
        String endpoint) implements DeliveryClient {
}
```

Java record tự tạo constructor, accessor `endpoint()`, `equals/hashCode/toString`. Nó rất phù hợp để assertions kiểm tra property được bind vào bean. Việc dùng hostname `.invalid` trong ví dụ bảo đảm người đọc không hiểu nhầm URL demo là một service thật.

## 8. DeliveryProperties.java: binder riêng với condition

Tạo `src/main/java/example/delivery/DeliveryProperties.java`:

```java
package example.delivery;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "lesson.delivery")
public class DeliveryProperties {
    private String endpoint =
            "https://notification.invalid/send";

    public String getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }
}
```

Property được bind từ `Environment` khi `@EnableConfigurationProperties(DeliveryProperties.class)` được xử lý.

- Không khai báo `enabled` và `transport` trong class này vẫn **hoàn toàn hợp lệ**: điều kiện `@ConditionalOnProperty` đọc các keys trực tiếp từ `Environment`; `@ConfigurationProperties` chỉ bind các fields cần dùng.
- `endpoint` có default value. Khi không truyền `lesson.delivery.endpoint`, bean sẽ dùng `https://notification.invalid/send`.
- Nếu truyền `lesson.delivery.endpoint=https://custom.invalid/api`, binder gọi setter trước khi bean factory method nhận `DeliveryProperties`.
- Không nên dùng `@Value` hoặc đọc static system property từ constructor khi đã có typed configuration properties; typed binding dễ test và quản lý defaults hơn.
- Nếu có validation như `@NotBlank`, cần Jakarta Validation provider và `@Validated` trên properties; **ví dụ này không khai báo validation**, nên một endpoint rỗng có thể bind được. Không tuyên bố nó bị reject khi chưa viết rule.

**Binding khác điều kiện:** `@ConditionalOnProperty(enabled=true)` có thể match nhưng `endpoint` vẫn sai nghiệp vụ; muốn chặn URL lỗi, cần validation/configuration-specific tests riêng.

## 9. DeliveryAutoConfiguration.java: ba điều kiện phối hợp

Tạo `src/main/java/example/delivery/DeliveryAutoConfiguration.java`:

```java
package example.delivery;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "lesson.delivery",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
@EnableConfigurationProperties(DeliveryProperties.class)
public class DeliveryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(DeliveryClient.class)
    @ConditionalOnProperty(
            prefix = "lesson.delivery",
            name = "transport",
            havingValue = "http",
            matchIfMissing = true)
    DeliveryClient deliveryClient(
            DeliveryProperties properties) {
        return new HttpDeliveryClient(
                properties.getEndpoint());
    }
}
```

Ba lớp điều kiện:

1. **Class-level enabled:** nếu `lesson.delivery.enabled` không phải `true` hoặc missing, cả auto-configuration không match.
2. **Bean-level transport:** khi class enabled, `deliveryClient()` chỉ match nếu `lesson.delivery.transport` missing (vì `matchIfMissing=true`) hoặc có giá trị `http`.
3. **Bean-level missing bean:** nếu context đã có `DeliveryClient` do user định nghĩa, default bean không được tạo.

**Thứ tự với user configuration:** Spring Boot xử lý auto-configurations sau user-defined bean definitions. Đây là lý do `@ConditionalOnMissingBean` được dùng trong auto-config thay vì trong một cấu hình ứng dụng thông thường có thứ tự xử lý tùy ý. Khi viết test, dùng `withUserConfiguration(...)` để chứng minh user bean được đăng ký trước default.

**Không có method gọi mạng:** `new HttpDeliveryClient(...)` chỉ tạo object lưu endpoint string, vì vậy unit/context test kiểm tra chính xác registration và binding mà không cần fake HTTP server.

### 9.1. AutoConfiguration.imports

Tạo file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Nội dung file (một dòng):

```text
example.delivery.DeliveryAutoConfiguration
```

Trong Spring Boot 3.x, file metadata này giúp một **ứng dụng thực** sử dụng thư viện phát hiện auto-config qua cơ chế import của Boot.

**Quan trọng:** các tests dùng `AutoConfigurations.of(DeliveryAutoConfiguration.class)` **tường minh**, nên chúng vẫn có thể pass nếu bạn lỡ quên file `AutoConfiguration.imports`. Vì thế cần review/kiểm tra packaging resource ở pipeline module/starter; context runner test registration logic **không thay thế một smoke test discovery thực tế của artifact đã đóng gói**.

## 10. JUnit test class hoàn chỉnh: ma trận withPropertyValues

Tạo `src/test/java/example/delivery/DeliveryAutoConfigurationTest.java`:

```java
package example.delivery;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DeliveryAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    DeliveryAutoConfiguration.class));

    private record MatrixCase(
            String label,
            List<String> properties,
            boolean hasClient) {
    }

    @Test
    void propertyMatrixCoversMissingTrueFalseAndTransport() {
        List<MatrixCase> cases = List.of(
                new MatrixCase(
                        "enabled missing",
                        List.of(), false),
                new MatrixCase(
                        "enabled=false",
                        List.of(
                                "lesson.delivery.enabled=false"),
                        false),
                new MatrixCase(
                        "enabled=0",
                        List.of(
                                "lesson.delivery.enabled=0"),
                        false),
                new MatrixCase(
                        "enabled empty",
                        List.of(
                                "lesson.delivery.enabled="),
                        false),
                new MatrixCase(
                        "enabled=true, transport missing",
                        List.of(
                                "lesson.delivery.enabled=true"),
                        true),
                new MatrixCase(
                        "enabled=true, transport=http",
                        List.of(
                                "lesson.delivery.enabled=true",
                                "lesson.delivery.transport=http"),
                        true),
                new MatrixCase(
                        "enabled=true, transport=grpc",
                        List.of(
                                "lesson.delivery.enabled=true",
                                "lesson.delivery.transport=grpc"),
                        false),
                new MatrixCase(
                        "enabled=true, transport empty",
                        List.of(
                                "lesson.delivery.enabled=true",
                                "lesson.delivery.transport="),
                        false),
                new MatrixCase(
                        "enabled=false, transport=http",
                        List.of(
                                "lesson.delivery.enabled=false",
                                "lesson.delivery.transport=http"),
                        false));

        for (MatrixCase testCase : cases) {
            String[] pairs = testCase.properties()
                    .toArray(String[]::new);

            runner.withPropertyValues(pairs)
                    .run(context -> {
                        assertNull(
                                context.getStartupFailure(),
                                testCase.label());

                        boolean present =
                                context.getBeansOfType(
                                        DeliveryClient.class)
                                        .size() == 1;

                        assertEquals(
                                testCase.hasClient(),
                                present,
                                testCase.label());
                    });
        }
    }

    @Test
    void endpointIsBoundWhenAutoConfigurationEnabled() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=true",
                        "lesson.delivery.transport=http",
                        "lesson.delivery.endpoint="
                                + "https://custom.invalid/api")
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    DeliveryClient bean =
                            context.getBean(
                                    DeliveryClient.class);

                    assertEquals(
                            "https://custom.invalid/api",
                            bean.endpoint());

                    assertTrue(
                            bean instanceof HttpDeliveryClient);
                });
    }

    @Test
    void missingEndpointUsesDefaultFromProperties() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=true")
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    assertEquals(
                            "https://notification.invalid/send",
                            context.getBean(
                                    DeliveryClient.class)
                                    .endpoint());

                    assertEquals(
                            "https://notification.invalid/send",
                            context.getBean(
                                    DeliveryProperties.class)
                                    .getEndpoint());
                });
    }

    @Test
    void customUserBeanMakesDefaultBackOff() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=true",
                        "lesson.delivery.transport=http")
                .withUserConfiguration(
                        CustomDeliveryConfiguration.class)
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    assertEquals(
                            1,
                            context.getBeansOfType(
                                    DeliveryClient.class)
                                    .size());
                    assertEquals(
                            "memory://custom",
                            context.getBean(
                                    DeliveryClient.class)
                                    .endpoint());
                    assertFalse(
                            context.containsBean(
                                    "deliveryClient"));
                });
    }

    @Test
    void disabledAutoConfigurationDoesNotDeleteUserBean() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=false")
                .withUserConfiguration(
                        CustomDeliveryConfiguration.class)
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    assertEquals(
                            1,
                            context.getBeansOfType(
                                    DeliveryClient.class)
                                    .size());
                    assertEquals(
                            "memory://custom",
                            context.getBean(
                                    DeliveryClient.class)
                                    .endpoint());
                });
    }

    @Test
    void derivedRunnerDoesNotModifyBaseRunner() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=true")
                .run(context -> {
                    assertNull(context.getStartupFailure());
                    assertEquals(
                            1,
                            context.getBeansOfType(
                                    DeliveryClient.class)
                                    .size());
                });

        runner.run(context -> {
            assertNull(context.getStartupFailure());
            assertTrue(
                    context.getBeansOfType(
                            DeliveryClient.class)
                            .isEmpty());
        });
    }

    @Test
    void conditionReportContainsOurAutoConfiguration() {
        runner.withPropertyValues(
                        "lesson.delivery.enabled=false")
                .run(context -> {
                    assertNull(context.getStartupFailure());

                    ConditionEvaluationReport report =
                            ConditionEvaluationReport.get(
                                    context.getBeanFactory());

                    assertTrue(
                            report.getConditionAndOutcomesBySource()
                                    .keySet()
                                    .stream()
                                    .anyMatch(source ->
                                            source.contains(
                                                    "DeliveryAutoConfiguration")));
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomDeliveryConfiguration {

        @Bean
        DeliveryClient customDeliveryClient() {
            return () -> "memory://custom";
        }
    }
}
```

**Bảy JUnit test methods** trong class này kiểm tra **9 matrix scenarios + 6 hành vi bổ sung**. Đối với ma trận, một method lặp qua chín case và tạo một context khác nhau cho mỗi vector, chứ không phải 9 JUnit methods riêng.

### 10.1. Vì sao assertions đủ mạnh?

- `assertNull(context.getStartupFailure())` ngăn case “không có bean” xanh giả khi context thực ra không start được vì cấu hình lỗi.
- `getBeansOfType(DeliveryClient.class).size() == 1` bảo vệ việc có đúng một bean phù hợp; nếu có hai default beans vô tình được đăng ký, case positive cũng fail.
- Kiểm tra `endpoint()` xác nhận property **đã bind vào dependency**, không chỉ Environment chứa key.
- `CustomDeliveryConfiguration` là **user configuration**, nên `@ConditionalOnMissingBean` phải skip default bean.
- Case `enabled=false` + custom user bean chứng minh condition class không xóa bean độc lập của user.
- Baseline runner không đổi sau một `withPropertyValues(...)` tùy biến; từng `run(...)` có context riêng.
- `ConditionEvaluationReport` giúp biết condition framework đã evaluate config; nhưng assertion chỉ kiểm tra **có entry liên quan**, không kiểm tra text/ordering của diagnostic message phụ thuộc version.

### 10.2. Những gì test chưa chứng minh

- File `AutoConfiguration.imports` sẽ chắc chắn được đóng gói đúng trong jar và auto-discover trong một ứng dụng Spring Boot khác — cần artifact-level smoke test riêng.
- `HttpDeliveryClient` sẽ gửi HTTP request thành công — nó chỉ lưu endpoint string.
- `@ConfigurationProperties` với URL rỗng hoặc malformed sẽ bị validation chặn — ví dụ không có constraint URL.
- Tất cả Spring Boot auto-configurations khác trong một production app cũng tương thích — runner chỉ load các classes được khai báo.
- Native image/AOT behavior — docs Boot nêu ApplicationContextRunner không dùng cho native-image test.
- Các biến thể environment profiles, servlet/reactive context, classpath dependency — chúng là các trục khác cần test khi starter hỗ trợ.

## 11. Đọc đúng ma trận thay vì chỉ đếm test methods

Ma trận có 9 vectors trong **một test method**, vì mục tiêu là bảo đảm mọi case đều được chạy với cùng cấu trúc assertions. Nếu 1 case fail, message `testCase.label()` sẽ cho biết case nào lệch.

Có thể chuyển sang `@ParameterizedTest` để báo mỗi vector thành một test invocation riêng, nhưng khi dùng JUnit parameterized tests, cần quyết định:

- Có nên dùng `@MethodSource` tạo cấu hình values + expected result?
- Có cần mỗi vector report riêng trên CI?
- Có giữ context lifecycle riêng giữa invocations?
- Có cần kiểm thử cả exception/startupFailure, không chỉ bean tồn tại?
- Có tránh truyền chung mutable `Environment` hoặc một `ApplicationContext` đã refresh?

Cách vòng lặp trong code đơn giản, **không cần thêm JUnit ParameterizedTest APIs** ngoài starter-test. Nếu team muốn báo cáo riêng 9 invocations, chuyển thành `@ParameterizedTest(name = "{index} {0}")` với `@MethodSource`; nhưng phải tính đúng expected test count trong CI.

**Không test condition bằng cách thay property giữa hai assertions trong cùng callback**: sau khi context refresh, Spring không re-evaluate condition class/bean chỉ vì `Environment` đổi. Mỗi vector cần một `run(...)` mới.

## 12. Phân biệt withPropertyValues với ConfigurationProperties binding

Hai cơ chế phối hợp nhưng có mục đích khác nhau:

```text
withPropertyValues
       |
       v
Spring Environment
       |
       +-- @ConditionalOnProperty(enabled, transport)
       |       |
       |       +-- quyết định bean definition có được tạo
       |
       +-- @EnableConfigurationProperties
               |
               +-- binder -> DeliveryProperties.endpoint
                                   |
                                   v
                            new HttpDeliveryClient(endpoint)
```

Một test chỉ kiểm tra:

```java
assertEquals(
        "https://custom.invalid/api",
        context.getEnvironment()
               .getProperty("lesson.delivery.endpoint"));
```

**chưa kiểm tra binder**. Nó chỉ cho biết Environment đọc được property. Test thực cần kiểm tra `DeliveryProperties.getEndpoint()` hoặc một bean dùng property; bài đã làm cả hai trong các case khác nhau.

### Khi @ConfigurationProperties có validation

Nếu production bean có:

```java
@ConfigurationProperties("lesson.delivery")
@Validated
class DeliveryProperties {
    @NotBlank
    private String endpoint;
}
```

Đây là **snippet**, không phải phiên bản class runnable của bài. Nó cần Jakarta Validation provider, getters/setters/constructor và imports. Khi property thiếu/blank, startup có thể fail lúc binding/validation; test phải assert **`context.getStartupFailure() != null`** và kiểm tra causal chain phù hợp.

**Đừng áp tiêu chí validation giả định cho class không có rule**. Ví dụ chính cho phép endpoint bất kỳ dạng text: nó chỉ kiểm tra binding. Nếu muốn bảo đảm URL chuẩn, bổ sung rule, dependency và failure matrix rõ ràng.

### Ngữ nghĩa null/missing

`withPropertyValues("lesson.delivery.endpoint=null")` là chuỗi **bốn ký tự “null”**, không phải null Java. Nếu muốn thử endpoint bị thiếu, bỏ cặp key. Nếu muốn thử empty, dùng `"lesson.delivery.endpoint="`. Đây là ba cases khác nhau.

## 13. ConditionEvaluationReport: giải thích vì sao không có bean

Khi một scenario không tạo bean, có ít nhất ba khả năng:

1. Condition trên **auto-config class** không match (enabled false/missing).
2. Class match nhưng method `@Bean` bị `@ConditionalOnProperty(transport=http)` skip.
3. Cả hai properties match nhưng `@ConditionalOnMissingBean` thấy user bean, nên default back off.

Một cách điều tra từ runner là lấy `ConditionEvaluationReport`:

```java
runner.withPropertyValues(
        "lesson.delivery.enabled=false")
    .run(context -> {
        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(
                        context.getBeanFactory());

        report.getConditionAndOutcomesBySource()
                .forEach((source, outcomes) -> {
                    if (source.contains(
                            "DeliveryAutoConfiguration")) {
                        System.out.println(
                                source + ": " + outcomes);
                    }
                });
    });
```

Đây là **snippet sử dụng runner/imports của test class**; nó in diagnostic, không phải stdout cố định vì class names, conditions, log formatting và report ordering có thể khác theo Spring Boot version. Test thực ở mục 10 tránh assert toàn bộ câu diagnostic.

Spring Boot có `ConditionEvaluationReportLoggingListener` để log report khi test muốn đọc condition outcomes. Cấu hình cụ thể tùy version, ví dụ dùng `withInitializer(...)` và log level tương ứng. Không cần bật debug logging cho toàn bộ suite chỉ để kiểm tra một condition.

### Startup failure không giống condition không match

`context.getBeansOfType(...).isEmpty()` có thể đúng cả khi context fail; vì vậy test ma trận luôn assert **không có startup failure** trước. Khi cố ý kiểm tra invalid configuration, làm ngược lại:

```java
assertNotNull(context.getStartupFailure());
```

Đây là một **assertion minh họa**, chưa phải test lỗi đầy đủ; cần một cấu hình thật sự gây startup failure mới có ý nghĩa. Với failure test, inspect root cause/exception type thay vì hardcode nguyên message có thể thay đổi theo version.

## 14. withUserConfiguration, withBean và override behavior

`@ConditionalOnMissingBean` là hợp đồng quan trọng của starter: auto-config tạo bean mặc định, nhưng user có thể cung cấp implementation riêng.

Ví dụ trong class test đã có:

```java
@Configuration(proxyBeanMethods = false)
static class CustomDeliveryConfiguration {
    @Bean
    DeliveryClient customDeliveryClient() {
        return () -> "memory://custom";
    }
}
```

Runner:

```java
runner.withPropertyValues(
        "lesson.delivery.enabled=true")
    .withUserConfiguration(
        CustomDeliveryConfiguration.class)
    .run(context -> {
        assertEquals(
                1,
                context.getBeansOfType(
                        DeliveryClient.class).size());
        assertEquals(
                "memory://custom",
                context.getBean(
                        DeliveryClient.class).endpoint());
    });
```

Không phải `@Primary` đang “chọn” bean giữa hai candidates; **default bean không được tạo** vì `@ConditionalOnMissingBean`. Sự khác biệt quan trọng: nếu default vẫn tồn tại rồi chỉ @Primary chọn custom, các dependency inject theo name/collection có thể thấy thêm bean ngoài ý muốn.

Một lựa chọn thay thế khi không cần `@Configuration` class:

```java
runner.withPropertyValues(
        "lesson.delivery.enabled=true")
    .withBean(
        "customDeliveryClient",
        DeliveryClient.class,
        () -> (DeliveryClient) () -> "memory://custom")
    .run(context -> {
        assertEquals(
                "memory://custom",
                context.getBean(
                        DeliveryClient.class).endpoint());
    });
```

Đây là **snippet**: `withBean(name, type, supplier)` đăng ký user bean vào context. Tùy nhu cầu có thể dùng `withBean(DeliveryClient.class, supplier)`. Trong bài, test hoàn chỉnh ưu tiên `withUserConfiguration` vì nó mô phỏng rõ một application custom configuration mà starter thực tế sẽ gặp.

**Không nhầm với `@MockBean/@MockitoBean`:** những annotation đó có cơ chế override/mock trong Spring test context. Khi mục tiêu là kiểm tra auto-config back off trước một user-defined bean, dùng `withUserConfiguration` hoặc `withBean` dễ hiểu và sát hợp đồng hơn.

## 15. Ma trận property khi có defaults và precedence

Với `matchIfMissing=true` trên method transport:

| Enabled | Transport | Endpoint | Kết quả |
| --- | --- | --- | --- |
| true | Missing | Missing | HTTP bean + default endpoint |
| true | http | Missing | HTTP bean + default endpoint |
| true | http | Custom URL | HTTP bean + custom URL |
| true | grpc | Custom URL | Không có HTTP bean |
| false | http | Custom URL | Auto-config tắt |
| Missing | http | Custom URL | Auto-config tắt |

**Ba kiểu “default” không giống nhau:**

1. **Condition default:** `matchIfMissing=true` cho transport, quyết định có tạo bean khi key vắng.
2. **ConfigurationProperties default:** field `endpoint` được khởi tạo sẵn một giá trị trước khi bind.
3. **Application default property source:** một value nằm trong `application.properties`/env/source có precedence riêng.

Nếu một cấu hình thật có property được định nghĩa từ một nguồn khác (environment variable hoặc test config file), “missing” theo góc nhìn `withPropertyValues` chưa chắc là **missing toàn Environment**. Khi cần chứng minh thật sự không có key, bảo đảm các property sources khác trong test runner không tự cung cấp key ấy.

### Property override giữa các runner

Runner supports chaining:

```java
ApplicationContextRunner base =
        new ApplicationContextRunner()
                .withPropertyValues(
                        "lesson.delivery.enabled=false");

ApplicationContextRunner enabled =
        base.withPropertyValues(
                "lesson.delivery.enabled=true");
```

Đây là một **snippet độc lập về builder semantics**. Derived runner có thể áp value mới theo precedence của test property values; base vẫn giữ cấu hình ban đầu. Không mutate global System properties hoặc dùng static mutable field để tạo từng vector.

Khi matrix lớn, nên tạo base runner **không set flag chính**, rồi mỗi case cung cấp đầy đủ `enabled`/`transport` có chủ đích. Việc giữ value mặc định trong base dễ khiến một case “missing” thực ra vẫn có key từ base, làm test sai ngữ nghĩa.

## 16. withPropertyValues khác @TestPropertySource/@SpringBootTest

Ba công cụ không thay thế nhau hoàn toàn:

| Công cụ | Context/lifecycle | Phù hợp với |
| --- | --- | --- |
| `ApplicationContextRunner.withPropertyValues` | Context nhỏ, mỗi `run` dựng/đóng | Ma trận auto-config conditions, bean presence |
| `@SpringBootTest(properties=...)` | Spring TestContext, có thể cache context | Full application integration, nhiều beans/services |
| `@TestPropertySource(properties=...)` | TestContext property sources | Tùy chỉnh test context của Spring Test |
| `@DynamicPropertySource` | Static supplier tới TestContext Environment | JDBC URL/port động từ Testcontainers |
| `@ActiveProfiles` | TestContext active profiles | Profile-specific bean wiring |
| `@WebMvcTest`/`@DataJpaTest` | Test slices | Web/data behavior chuyên biệt |

Ví dụ `@SpringBootTest(properties = "lesson.delivery.enabled=true")` có thể kiểm tra auto-config được áp dụng trong **ứng dụng thật**, nhưng nếu bạn muốn thử 10 giá trị khác nhau bằng nhiều classes/annotations, context setup/cache có thể chậm và phức tạp hơn runner. Ngược lại, `ApplicationContextRunner` không tự dựng HTTP server hay repository stack trừ khi bạn cấu hình thêm.

**Trọng tâm của bài là test auto-configuration contract**, không phải chọn runner cho mọi integration test.

## 17. Classpath, web application và các trục điều kiện khác

Mới test `enabled × transport × customBean` chưa đủ khi auto-config có những điều kiện khác. Một bảng mở rộng:

| Trục | Condition thường gặp | Cách mô phỏng bằng runner |
| --- | --- | --- |
| Property | `@ConditionalOnProperty` | `withPropertyValues(...)` |
| User bean tồn tại | `@ConditionalOnBean` / `@ConditionalOnMissingBean` | `withUserConfiguration(...)`, `withBean(...)` |
| Classpath | `@ConditionalOnClass` / `@ConditionalOnMissingClass` | `withClassLoader(new FilteredClassLoader(...))` |
| Servlet web context | `@ConditionalOnWebApplication` | `WebApplicationContextRunner` |
| Reactive web context | Reactive variant | `ReactiveWebApplicationContextRunner` |
| Resource path | `@ConditionalOnResource` | Classloader/resource setup |
| Environment/profiles | `@Profile` hoặc custom conditions | `withPropertyValues("spring.profiles.active=...")` khi phù hợp |

### FilteredClassLoader là gì?

Spring Boot test hỗ trợ lọc một class khỏi classloader để mô phỏng “dependency tùy chọn không tồn tại”:

```java
runner.withClassLoader(
        new FilteredClassLoader(
                "com.example.optional.ExternalSdk"))
    .run(context -> {
        // Assert fallback khi SDK vắng.
    });
```

Đây là **snippet định hướng**, không thuộc test class runnable của bài vì ví dụ `DeliveryAutoConfiguration` không phụ thuộc ExternalSdk. Nó chỉ có ý nghĩa khi chính auto-config được test có `@ConditionalOnClass(name="com.example.optional.ExternalSdk")` hoặc condition liên quan. Không viết test luôn pass vì class giả định vốn chưa từng tồn tại trên classpath rồi cho rằng đã kiểm tra fallback.

**Lưu ý @ConditionalOnClass:** với optional dependencies, tránh để những types chỉ tồn tại khi dependency có mặt xuất hiện theo cách JVM phải load class quá sớm. Một pattern là tách nested configuration có `@ConditionalOnClass`; test classpath present/absent bằng runner thích hợp.

### Web context runner

Nếu auto-configuration phụ thuộc `ServletWebServerApplicationContext`/servlet environment, dùng:

```java
new WebApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(
                        SomeWebAutoConfiguration.class))
        .run(context -> {
            // Assertions theo web context.
        });
```

Đây là **snippet**, cần imports và class SomeWebAutoConfiguration thật. `ApplicationContextRunner` không web sẽ khiến `@ConditionalOnWebApplication` có thể không match dù production là servlet app; test pass negative branch không chứng minh positive branch trên web context.

Tương tự `ReactiveWebApplicationContextRunner` phù hợp reactive web condition. Chọn đúng loại context trước khi kết luận auto-configuration bị lỗi.

## 18. Bảng giá trị @ConditionalOnProperty: đọc kỹ havingValue

Theo semantics Spring Boot, truth table của `@ConditionalOnProperty` điển hình:

| Property thực | `havingValue=""` mặc định | `havingValue="true"` | `havingValue="false"` | `havingValue="foo"` |
| --- | --- | --- | --- | --- |
| `true` | Match | Match | Không | Không |
| `false` | Không | Không | Match | Không |
| `foo` | Match | Không | Không | Match |
| `""` (empty) | Match | Không | Không | Không |
| Missing | Theo matchIfMissing | Theo matchIfMissing | Theo matchIfMissing | Theo matchIfMissing |

**Lưu ý:** các giá trị trong bảng là **string property values**, không phải một logic binder chuyển mọi kiểu truthy/falsy như JavaScript. Nếu enabled="1" hoặc enabled="yes", điều kiện `havingValue="true"` không tự động nhận như true theo truthy semantics.

Tại sao test này quan trọng? Một starter có thể viết nhầm:

```java
@ConditionalOnProperty(
        prefix = "lesson.delivery",
        name = "enabled")
```

Nếu product requirement nói “chỉ bật khi `enabled=true`” mà một environment nhập `enabled=maybe`, conditional mặc định có thể vẫn match. Test `enabled=maybe` sẽ phát hiện khác biệt và buộc developer dùng `havingValue="true"` tường minh.

**Đừng nhầm matchIfMissing với default value trong @ConfigurationProperties.** MatchIfMissing được evaluate trên `Environment` trước/độc lập với object properties có initializer default. Một field `boolean enabled = true` trong Properties class **không tự bảo đảm** `@ConditionalOnProperty(enabled)` sẽ match khi Environment thiếu key.

## 19. Diagnosing: không nhầm property condition, bean backoff và startup error

Một checklist khi không thấy bean:

```text
No DeliveryClient bean?
        |
        +-- Did context start successfully?
        |      |
        |      +-- NO -> inspect getStartupFailure/cause
        |
        +-- Is lesson.delivery.enabled exactly true?
        |      |
        |      +-- NO -> class-level condition skipped
        |
        +-- Is transport missing or http?
        |      |
        |      +-- NO -> method-level condition skipped
        |
        +-- Is user DeliveryClient already present?
               |
               +-- YES -> @ConditionalOnMissingBean backed off
               +-- NO  -> check bean creation/binding/factory error
```

**Kiểm tra đúng tầng:**

- `context.getStartupFailure() == null` khi case dự kiến start thành công.
- `getBeansOfType(DeliveryClient.class)` để kiểm tra type.
- `context.containsBean("deliveryClient")` khi cần kiểm tra **bean name** của default method.
- `context.getBean(DeliveryProperties.class)` để kiểm tra binder.
- `ConditionEvaluationReport` để giải thích tại sao condition không match.
- Logger ở `INFO/DEBUG` khi cần xem diagnostics mà không đóng cứng wording của messages.

Một test chỉ làm `assertFalse(context.containsBean("deliveryClient"))` **chưa đủ** để chứng minh không có `DeliveryClient` vì user bean có thể mang tên khác. Tương tự, `getBean(DeliveryClient.class)` không chứng minh default HTTP bean nếu một custom bean đã back off default. Test cần chọn đúng contract.

## 20. Anti-pattern: sửa global System property giữa các test

Một ma trận viết kiểu:

```java
System.setProperty(
        "lesson.delivery.enabled", "true");
// Spring test ở nơi khác chạy trong cùng JVM...
System.clearProperty("lesson.delivery.enabled");
```

Đây là **anti-pattern minh họa**, vì global mutable property có thể bị test khác đọc cùng lúc, nhất là khi JUnit chạy song song. Nếu cleanup không chạy do assertion fail, global state còn rò sang test kế.

Ưu tiên `withPropertyValues` để gắn property vào **context của case**. Nếu thực sự cần thử System properties hoặc Env precedence thì có `withSystemProperties(...)` và các công cụ test system-property có lifecycle/restore rõ; đừng tự mutate mà không cleanup.

### Case isolated không có nghĩa không có tài nguyên ngoài context

Một `ApplicationContextRunner.run(...)` sẽ đóng context nhưng nếu `@Bean` method mở socket/thread pool không thuộc lifecycle/disposable bean contract, nó có thể vẫn rò. Với auto-config thực sự tạo HTTP clients, executors hoặc connection pools, nên test destroy callbacks/beans và fake external endpoints có chủ đích.

Đừng mở Docker chỉ để kiểm tra property flag, nhưng cũng đừng dùng runner thuần rồi tuyên bố dependency thực luôn kết nối được.

## 21. Làm sao QA ma trận mà không thiếu tổ hợp?

Với hai trục:

- Enabled: `missing / true / false / invalid`.
- Transport: `missing / http / grpc / empty`.

Có **4 × 4 = 16 tổ hợp** nếu test exhaustive toàn bộ. Khi thêm user bean absent/present, tổng số 32 scenarios. Không phải mọi project cần chạy trọn 32 nếu rule độc lập và không có tương tác; nhưng tối thiểu phải có:

- Mỗi nhánh enable/disable: missing, false, true, unexpected text/empty.
- Giá trị transport mặc định khi missing, đúng http, sai grpc, present-empty.
- User override trong enabled=true và disabled=false.
- Property binding endpoint khi enabled+transport match.
- Negative context thành công nhưng không có bean, chứ không phải startup fail.
- Report conditions khi một nhánh bất ngờ không match.
- Test standalone artifact discovery nếu bạn phát hành starter library.

**Nếu dùng pairwise testing** cho nhiều properties, giữ thêm các ca tương tác quan trọng giữa điều kiện và missing bean. “Có 20 test cases” không tự chứng minh phủ hết rule nếu mọi case đều enabled=true.

### Bảng trường hợp rủi ro nhất

| Lỗi vô tình khi sửa config | Test nào phát hiện? |
| --- | --- |
| Bỏ `havingValue="true"` | `enabled=0`/`enabled=maybe` negative |
| Đổi `matchIfMissing=false` thành true ở enabled | `enabled missing` negative |
| Đổi transport default thành disabled | `transport missing` positive |
| Bỏ `@ConditionalOnMissingBean` | User-override test xuất hiện 2 beans |
| Đổi prefix/name | Positive `enabled=true` không có bean |
| Không bật `@EnableConfigurationProperties` | Endpoint binding test fail (startup hoặc value sai) |
| Ignore endpoint value | Custom endpoint test fail |
| Vô tình dùng @Primary thay vì back-off | Assertion số bean=1 fail |
| Dùng wrong context type cho web condition | Positive web-runner scenario fail |
| Quên imports metadata trong starter JAR | Artifact-level discovery test fail |

**Trong bộ code chính**, matrix đã kiểm tra absent/false/0/empty/true + transport missing/http/grpc/empty. Nếu product requirement quan tâm `enabled=maybe`, hãy thêm một `MatrixCase` tương ứng; vì có `havingValue="true"`, kỳ vọng sẽ là false. Bài không tự nhận đã chạy mọi giá trị chuỗi có thể có.

## 22. Java 17 độc lập: mô hình ma trận có stdout chính xác

Một chương trình Java SE sau minh họa logic **chỉ dành cho hai điều kiện property cụ thể của ví dụ**, không khởi tạo ApplicationContext. Nó giúp người học thấy các case trước khi đối chiếu với JUnit Spring Boot.

Tạo `src/main/java/example/delivery/ConditionMatrixDemo.java`:

```java
package example.delivery;

public class ConditionMatrixDemo {

    private record Case(
            String name,
            String enabled,
            String transport) {
    }

    private static boolean shouldCreate(
            String enabled, String transport) {
        boolean on =
                "true".equalsIgnoreCase(enabled);
        boolean http =
                transport == null
                || "http".equalsIgnoreCase(transport);
        return on && http;
    }

    public static void main(String[] args) {
        Case[] cases = {
            new Case("missing enabled", null, null),
            new Case("disabled", "false", null),
            new Case("default transport", "true", null),
            new Case("http transport", "true", "http"),
            new Case("grpc transport", "true", "grpc")
        };

        for (Case testCase : cases) {
            System.out.println(
                    testCase.name() + ": "
                    + shouldCreate(
                            testCase.enabled(),
                            testCase.transport()));
        }
    }
}
```

Biên dịch và chạy với **JDK 17+**, không cần Gradle, Spring hoặc Docker:

```bash
javac -d out src/main/java/example/delivery/ConditionMatrixDemo.java
java -cp out example.delivery.ConditionMatrixDemo
```

Stdout **chính xác**:

```text
missing enabled: false
disabled: false
default transport: true
http transport: true
grpc transport: false
```

Đây là **mô hình Java thuần**, không phải implementation của Spring Boot `@ConditionalOnProperty`. Nó cố ý chỉ diễn đạt `enabled havingValue=true + transport havingValue=http matchIfMissing=true` của bài. Test Spring thật ở mục 10 mới chứng minh auto-configuration tương ứng tạo beans hay không.

Một khác biệt đáng nhớ: Java demo coi `null` của `Case.enabled` là “property missing”, nhưng trong Spring `withPropertyValues("key=null")` là **một chuỗi value “null”**, không phải missing. Vì vậy matrix Spring phải biểu diễn missing bằng **không đưa key** vào property pairs.

## 23. Cách chạy unit/context tests và đánh giá kết quả

Từ root của module có Gradle wrapper và JDK 17:

```bash
./gradlew test --tests example.delivery.DeliveryAutoConfigurationTest
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.delivery.DeliveryAutoConfigurationTest"
```

Kết quả kỳ vọng nếu Gradle dependencies/class files đúng như code:

- **7 JUnit test methods** trong `DeliveryAutoConfigurationTest`.
- Method `propertyMatrixCoversMissingTrueFalseAndTransport` tự tạo **9 independent contexts** tương ứng 9 matrix cases.
- Sáu methods còn lại kiểm tra endpoint binding/default, custom user bean/backoff, disabled auto-config vẫn giữ user bean, runner isolation và condition report.
- Không cần Docker, JDBC database, HTTP server hay external service.
- `ApplicationContextRunner` tự đóng context của mỗi `run(...)`; không cần `@DirtiesContext` để ép Spring TestContext cache reset.

**Không có stdout cố định cho Gradle/JUnit test runner** vì output phụ thuộc Gradle/JUnit/logger và số task up-to-date. Chỉ chương trình `ConditionMatrixDemo` có stdout chính xác ở mục 22. Đây là kết quả **được thiết kế và kỳ vọng**, không phải tuyên bố rằng đã chạy tests trên máy người đọc.

### Cách đọc failure của một scenario

Nếu `enabled=true,transport=grpc` bất ngờ có bean:

1. Kiểm tra annotation `@ConditionalOnProperty(transport)` ở **bean method** còn tồn tại không.
2. Kiểm tra property key prefix/name viết đúng không.
3. Lấy `ConditionEvaluationReport` và xem có condition match sai không.
4. Kiểm tra có user `DeliveryClient` từ config khác đang được đưa vào context không.
5. Không chữa bằng cách assert `containsBean("deliveryClient")==false` nếu vẫn có custom bean mà contract yêu cầu loại; hãy kiểm tra đúng invariant.

Nếu `enabled=true,transport=http` không có bean:

1. Kiểm tra context startup failure trước.
2. Kiểm tra class `DeliveryAutoConfiguration` có nằm trong `AutoConfigurations.of(...)` không.
3. Kiểm tra user bean có khiến default back off không.
4. Kiểm tra `@EnableConfigurationProperties` và `DeliveryProperties` bind lỗi/bean creation failure không.
5. Xem condition evaluation report thay vì đoán do Spring context cache.

## 24. Khi nào cần thêm @SpringBootTest hoặc test artifact discovery?

Context runner test rất phù hợp cho auto-config contract, nhưng một starter xuất bản ra ngoài còn có những ranh giới khác:

**A. Artifact discovery:** build jar và đảm bảo file `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` được đóng gói. Test bằng một ứng dụng consumer mẫu thực sự import artifact và assert bean xuất hiện theo config, không chỉ `AutoConfigurations.of` explicit.

**B. Full application wiring:** khi nhiều auto-configurations tương tác hoặc có component scanning/real service dependencies, có thể dùng `@SpringBootTest(properties=...)` để kiểm tra toàn bộ graph; không biến mọi matrix case thành full context nếu chi phí cao.

**C. External dependency:** nếu HTTP client thật mở network hoặc database driver cần DB, tách unit registration test khỏi integration test với WireMock/Testcontainers/service test double, kiểm tra connection/errors có chủ đích.

**D. Profile/override precedence:** khi môi trường triển khai có Helm/env/secret properties, cần test property sources/profile precedence tại application level, không chỉ một property map.

**E. Native/AOT:** runner không chạy dưới native image test; dùng build-time hints/integration/native test workflows phù hợp.

**F. Classpath optionality:** `@ConditionalOnClass` phải được kiểm tra khi dependency present và absent, không chỉ khi tất cả dependencies đang có trong test classpath.

**G. Auto-config ordering:** `@AutoConfigureBefore`/`@AutoConfigureAfter` hoặc bean conditions phụ thuộc config khác cần được kiểm tra trong tập `AutoConfigurations.of(A.class, B.class)` và user overrides phù hợp.

**H. Upgrade tests:** khi nâng Spring Boot, JUnit, starter dependency hoặc third-party library, chạy lại matrix và artifact discovery để phát hiện condition semantics/bean naming thay đổi.

## 25. Những lỗi thường gặp với withPropertyValues

**1. Chỉ test enabled=true.** Bỏ qua missing/false/invalid; annotation có thể bật sai khi người dùng không muốn.

**2. Quên havingValue="true" cho boolean-like flag.** Default `havingValue=""` không đồng nghĩa parse Boolean strict.

**3. Hiểu matchIfMissing như “value empty cũng match”.** Missing khác present-empty; phải test cả hai.

**4. Viết withPropertyValues("flag=null") để mô phỏng missing.** Đây là literal text, không phải property vắng.

**5. Chỉ kiểm tra getEnvironment().getProperty(...).** Không chứng minh bean binding/registration; assert bean thực.

**6. Không assert context.getStartupFailure()==null trong negative tests.** Context lỗi startup có thể làm getBeansOfType empty và test xanh giả.

**7. Chỉ kiểm tra tên bean.** User override có thể cùng type nhưng khác name; cần invariant theo type/identity.

**8. Coi @Primary là @ConditionalOnMissingBean.** @Primary chọn injection candidate nhưng không chặn default bean tồn tại.

**9. Đặt @ConditionalOnMissingBean vào cấu hình người dùng không có ordering rõ.** Thứ tự bean registration có thể ảnh hưởng condition; dùng auto-config contract và test user config trước.

**10. Tưởng @ConfigurationProperties field default tự bật @ConditionalOnProperty.** Condition đọc Environment; field initializer không tự tạo property source.

**11. Tưởng sửa Environment sau refresh là tạo/xóa bean.** Conditions thường chỉ được evaluate khi context được tạo.

**12. Reuse cùng một context cho nhiều vectors.** Matrix phải tạo contexts riêng để tách condition states.

**13. Dùng System.setProperty global giữa các tests và quên cleanup.** Flaky/rò properties khi chạy parallel; dùng runner scoped test properties.

**14. Dùng @SpringBootTest cho mọi vector mà không cần full app.** Startup chậm, môi trường phụ thuộc nhiều thứ không thuộc contract.

**15. Dùng ApplicationContextRunner không web để test @ConditionalOnWebApplication servlet.** Chọn WebApplicationContextRunner thích hợp.

**16. Mock cả auto-configured bean rồi nói đã test bean factory.** Mock có thể thay thế registration path; dùng real bean type và asserts đúng.

**17. Chỉ test presence, không kiểm tra default values.** Binder có thể bỏ qua endpoint mới; assert bean.endpoint() và Properties.getEndpoint().

**18. Không kiểm tra custom override.** Starter có thể tạo hai beans hoặc không nhường chỗ cho user-defined implementation.

**19. Đóng cứng full ConditionEvaluationReport output.** Chẩn đoán text/order không phải API contract ổn định qua mọi version.

**20. Quên AutoConfiguration.imports nhưng runner vẫn xanh.** Runner load class explicit; artifact discovery cần test riêng.

**21. Dùng FilteredClassLoader với tên class chưa từng có.** Test “classpath missing” tự nhiên pass nhưng không kiểm tra điều kiện present/absent thật.

**22. Cho rằng runner test chứng minh starter native-image compatible.** Cần native/AOT test riêng.

**23. Bỏ qua property alias/migration behavior.** Khi rename keys, test cả key cũ/mới nếu có backward-compatibility policy.

**24. Không kiểm tra invalid typed values/startup failure.** Nếu properties có enum/numeric validation, thêm failure matrix; đừng dùng matcher bean presence làm bằng chứng đủ.

**25. Không phân biệt điều kiện class với điều kiện @Bean.** Enabled=false skip config; transport=grpc chỉ skip HTTP bean method trong config enabled — ConditionEvaluationReport giúp phân biệt.

## 26. Checklist QA trước khi chốt bài

**Nguồn điều kiện:**

- Đã đọc chính xác `prefix/name/havingValue/matchIfMissing` của từng annotation?
- Có phân biệt missing, true, false, unexpected string và present-empty?
- Với nhiều property names, có hiểu AND thay vì OR?
- Có kiểm tra property collection-index condition nếu project dùng lists?
- Có phân biệt property trong Environment với field default của @ConfigurationProperties?

**Ma trận context runner:**

- Mỗi scenario có context riêng qua `run(...)`?
- Có một baseline runner không bị mutate?
- `AutoConfigurations.of(...)` có load đúng auto-config classes theo Boot mechanism?
- Có positive cases và negative cases?
- Negative cases có assert startup không lỗi trước khi kiểm tra thiếu bean?
- Có kiểm tra **bean count/type/identity** thay vì chỉ bean name?
- Có thử custom user bean/backoff khi enabled và khi disabled?
- Có kiểm tra binding endpoint/default?
- Có diagnostics ConditionEvaluationReport cho các case không match?

**Tính đúng đắn Java:**

- Tên file, package, class/imports và Gradle dependencies khớp nhau?
- `@ConfigurationProperties` được đăng ký bằng `@EnableConfigurationProperties`?
- `DeliveryClient` interface và `HttpDeliveryClient` record có implementation đúng?
- Test không cần server/DB/Docker nếu chỉ kiểm tra registration?
- Java SE demo có lệnh `javac/java` và stdout chính xác?
- Tests chỉ tuyên bố số lượng methods thật sự có trong source?
- Có phân biệt snippet không runnable với full source runnable?

**Mở rộng production:**

- Có `AutoConfiguration.imports` đóng gói trong artifact?
- Nếu app là servlet/reactive, đã dùng runner context đúng loại?
- Nếu condition phụ thuộc classpath, có class-present và class-absent tests?
- Nếu có bean validation/properties binding lỗi, đã assert startup failure/root cause?
- Nếu có nhiều auto-config modules, đã kiểm tra ordering/user overrides?
- Có test full application/smoke artifact khi cần thay vì chỉ tin context runner?
- Có giữ tài nguyên do beans tạo sạch sau callback và không rò global property?
- Không suy luận native/AOT behavior từ ApplicationContextRunner JVM test?

**Kết luận:** `ApplicationContextRunner.withPropertyValues(...)` là công cụ rất hiệu quả để kiểm tra **ma trận điều kiện auto-configuration**: mỗi input vector tạo một context ngắn sống, assertions kiểm tra startup, bean presence/type, default/custom binding và backoff. Với `@ConditionalOnProperty`, cần luôn phân biệt **missing**, **present but false/empty**, **havingValue** và **matchIfMissing**; với `@ConditionalOnMissingBean`, phải test user override. Context runner giúp bảo vệ starter contract nhanh và rõ, nhưng **không tự chứng minh artifact discovery, I/O của bean thật, full application wiring hoặc native-image behavior**.

## 27. Tài liệu tham khảo

- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): cách khai báo auto-config, imports metadata và kiểm thử bằng ApplicationContextRunner.
- [Spring Boot 3.5 — AbstractApplicationContextRunner API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/AbstractApplicationContextRunner.html): `withPropertyValues`, `withUserConfiguration`, `withBean`, `withClassLoader` và `run`.
- [Spring Boot 3.5 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): havingValue truth table, matchIfMissing, collection limitations.
- [Spring Boot 3.5 — Configuration Properties](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): Environment, relaxed binding và property source precedence.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest và test slice so với context runner.
- [Spring Boot 3.5 — ConditionEvaluationReport API](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): condition sources và outcomes.
- [JUnit 5 — User Guide](https://junit.org/junit5/docs/current/user-guide/): test lifecycle, assertions và parametrized tests.
