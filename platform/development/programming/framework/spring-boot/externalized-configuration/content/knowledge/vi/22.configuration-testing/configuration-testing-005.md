# Ghi đè thuộc tính bằng @SpringBootTest(properties = ...)

## 1. Bài toán: kiểm tra ứng dụng với cấu hình riêng mà không sửa application.yml

Spring Boot cho phép tách cấu hình khỏi mã nguồn. Cùng một ứng dụng có thể hoạt động với endpoint, timeout, giới hạn thử lại hoặc cờ tính năng khác nhau tùy môi trường. Khi viết kiểm thử tích hợp, ta thường muốn xác nhận một bean hoạt động đúng **với một tập giá trị cụ thể** mà không cần sửa cấu hình đang dùng cho development hoặc production.

Ví dụ ứng dụng có `src/main/resources/application.yml`:

```yaml
notification:
  enabled: false
  sender-name: Default Sender
  max-attempts: 2
  timeout: 5s
```

Nhưng test muốn kiểm tra trường hợp:

```text
notification.enabled      = true
notification.sender-name  = Integration Test Sender
notification.max-attempts = 7
notification.timeout      = 250ms
```

Một cách dễ gặp nhưng không tốt là sửa tạm `application.yml` trước khi test rồi khôi phục sau. Cách này làm thay đổi trạng thái dự án, dễ tạo xung đột giữa các test, có thể khiến thay đổi vô tình được commit và không bảo đảm kết quả lặp lại trên CI.

Spring Boot cung cấp annotation:

```java
@SpringBootTest(properties = {
    "notification.enabled=true",
    "notification.sender-name=Integration Test Sender",
    "notification.max-attempts=7",
    "notification.timeout=250ms"
})
```

Những chuỗi `key=value` trong thuộc tính `properties` được thêm vào **Environment của ApplicationContext dùng cho test**. Chúng thường có ưu tiên cao hơn giá trị trong các file cấu hình thông thường, để khi context được tạo, những bean đọc các khóa tương ứng nhận giá trị test.

**Cần hiểu chính xác:** annotation này **không sửa file `application.yml`**, **không thay biến môi trường của cả máy**, và **không tự thay giá trị của mọi bean đã được tạo trước đó**. Nó thiết lập cấu hình cho **test context** trong quá trình khởi tạo.

Bài này tập trung vào cú pháp, cơ chế ghi đè, ảnh hưởng đến `Environment`, `@Value` và `@ConfigurationProperties`, các tương tác với profile/test properties khác, cách viết assertion và những bẫy thường gặp.

## 2. @SpringBootTest là gì?

`@SpringBootTest` nằm trong package:

```java
import org.springframework.boot.test.context.SpringBootTest;
```

Nó được dùng trên lớp kiểm thử để khởi động một Spring Boot `ApplicationContext` cho integration test. Khác với unit test chỉ gọi `new Service(...)`, kiểm thử này có thể dùng:

- Spring Boot auto-configuration.
- Component scanning và cấu hình chính của ứng dụng.
- Dependency injection bằng `@Autowired` hoặc constructor injection của test theo quy tắc Spring Test.
- `Environment` đã được chuẩn bị theo cơ chế của Spring Boot.
- Config Data như `application.yml` và file theo profile.
- Binder tạo object `@ConfigurationProperties`.
- Những bean được tạo có điều kiện theo property hoặc profile.

`@SpringBootTest` có các thuộc tính thông dụng:

| Thuộc tính | Mục đích |
| --- | --- |
| `properties` | Đưa các cặp `key=value` vào Environment của test |
| `value` | Alias của `properties` |
| `classes` | Chỉ định class cấu hình để khởi tạo context khi cần |
| `webEnvironment` | Quyết định có môi trường web, mock web hay server thực |
| `args` | Truyền application arguments cho Spring Boot |
| `useMainMethod` | Kiểm soát việc gọi `main` khi dựng test context, nếu phiên bản hỗ trợ |

Ví dụ tối thiểu:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = "demo.mode=test")
class DemoApplicationTest {

    @Test
    void contextStarts() {
        // Context được dựng với demo.mode=test.
    }
}
```

`@SpringBootTest` là annotation **cấp lớp**, không phải cách ghi đè property trực tiếp trên từng phương thức `@Test`. Muốn các bài test trong cùng một lớp dùng cấu hình khác nhau theo từng phương thức, cần tổ chức các context riêng hoặc chọn phương pháp khác phù hợp; không nên thay biến môi trường toàn cục ngay giữa các test.

### webEnvironment mặc định

Với ứng dụng web, `@SpringBootTest` mặc định dùng `WebEnvironment.MOCK`: tạo web application context/môi trường mô phỏng mà **không khởi động embedded server thật**. Khi bài học chỉ cần kiểm tra cấu hình và service thuần Java, có thể đặt:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "demo.mode=test"
)
```

`NONE` tạo context không có web environment. Điều đó giúp ví dụ không cần mở port và tránh phụ thuộc vào servlet/web layer.

Nếu test cần thực sự gửi HTTP tới server, dùng `RANDOM_PORT` cùng HTTP client/test framework phù hợp. Việc ghi đè property không tự làm server khởi động; lựa chọn `webEnvironment` mới quyết định mục đích của test.

## 3. Chuẩn bị dependency và cấu trúc project

Ví dụ thực hành hướng tới Spring Boot 3.x, Java 17 trở lên, JUnit Jupiter. Spring Boot 4 có thể khác ở một số auto-configuration package nhưng annotation `@SpringBootTest` và cơ chế `properties` vẫn tồn tại. Hãy dùng dependency và plugin được BOM/parent của project quản lý.

### 3.1. Maven

Trong `pom.xml`:

```xml
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
```

`spring-boot-starter-test` cung cấp hạ tầng test thông dụng, bao gồm JUnit Jupiter, AssertJ và Spring Test theo phiên bản Boot đang dùng. Nếu app cần web, database hoặc validation thì thêm starter riêng theo nhu cầu; bài minh họa không yêu cầu các dependency ấy.

### 3.2. Gradle Groovy DSL

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Với Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Các đoạn trên giả định project đã khai Spring Boot plugin và quản lý dependency đúng cách. Trong hệ thống nhiều module, đặt `spring-boot-starter-test` trong module chứa test.

### 3.3. Cấu trúc ví dụ

```text
notification-config-demo/
└── src/
    ├── main/
    │   ├── java/com/example/notification/
    │   │   ├── NotificationApplication.java
    │   │   ├── NotificationProperties.java
    │   │   └── NotificationPlanService.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/notification/
            ├── NotificationPropertiesOverrideTest.java
            └── NotificationDefaultsTest.java
```

Chúng ta tạo một ứng dụng chạy hoàn toàn trong bộ nhớ; không gọi API bên ngoài và không cần database thật. Nhờ đó người học tập trung vào **giá trị cấu hình có hiệu lực**, không bị lẫn với việc mock mạng hay transaction.

## 4. Định nghĩa cấu hình nền trong application.yml

Tạo `src/main/resources/application.yml`:

```yaml
notification:
  enabled: false
  sender-name: Default Sender
  max-attempts: 2
  timeout: 5s
```

Đây là nguồn Config Data thông thường của ứng dụng.

Các khóa có ý nghĩa:

| Khóa | Giá trị trong YAML | Kiểu mong muốn |
| --- | --- | --- |
| `notification.enabled` | `false` | `boolean` |
| `notification.sender-name` | `Default Sender` | `String` |
| `notification.max-attempts` | `2` | `int` |
| `notification.timeout` | `5s` | `Duration` |

Vì YAML nằm trong `src/main/resources`, nó có thể xuất hiện trên classpath của cả ứng dụng thường lẫn test; tuy nhiên giá trị có hiệu lực vẫn phụ thuộc những nguồn ưu tiên cao hơn trong `Environment`.

Không cần tạo một `application.yml` khác cho mỗi lớp test khi chỉ muốn ghi đè vài khóa. `@SpringBootTest(properties = ...)` phù hợp với một số override cụ thể, dễ nhìn ngay tại bài kiểm thử.

## 5. Tạo @ConfigurationProperties để quan sát binding

Tạo `NotificationProperties.java`:

```java
package com.example.notification;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        boolean enabled,
        String senderName,
        int maxAttempts,
        Duration timeout
) {}
```

Record Java được dùng để nhận cả bốn giá trị cấu hình. Binder của Spring Boot liên kết tên `sender-name` trong YAML với thành phần `senderName` của record theo relaxed binding.

Điểm cần nhớ:

- Java code làm việc với `properties.senderName()` chứ không cần tự tra cứu khóa văn bản trong YAML.
- `timeout` nhận đối tượng `Duration` thay vì chuỗi `"5s"`.
- `@ConfigurationProperties` không tự tạo bean khi chưa được đăng ký qua cơ chế phù hợp.
- Các tham số record ở đây là **dữ liệu cấu hình**, không phải nơi tiêm một `Repository`, `HttpClient` hoặc service nghiệp vụ.

### 5.1. Tạo service tiêu thụ properties

Tạo `NotificationPlanService.java`:

```java
package com.example.notification;

import java.time.Duration;

import org.springframework.stereotype.Service;

@Service
public class NotificationPlanService {

    private final NotificationProperties properties;

    public NotificationPlanService(
            NotificationProperties properties) {
        this.properties = properties;
    }

    public NotificationPlan currentPlan() {
        return new NotificationPlan(
                properties.enabled(),
                properties.senderName(),
                properties.maxAttempts(),
                properties.timeout()
        );
    }

    public record NotificationPlan(
            boolean enabled,
            String senderName,
            int maxAttempts,
            Duration timeout
    ) {}
}
```

`currentPlan()` chỉ trả object mô tả kế hoạch, **không gửi email hoặc gọi mạng**. Ta dùng nó để xác minh rằng không chỉ `Environment`, mà cả **service đã được Spring tiêm dependency** cũng nhìn thấy cấu hình mong đợi.

### 5.2. Đăng ký properties

Tạo `NotificationApplication.java`:

```java
package com.example.notification;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootApplication
@EnableConfigurationProperties(NotificationProperties.class)
public class NotificationApplication {

    public static void main(String[] args) {
        SpringApplication.run(NotificationApplication.class, args);
    }
}
```

`@EnableConfigurationProperties` đăng ký kiểu record để Spring Boot binder tạo bean phù hợp. Không cần thêm `@Component` lên record constructor-bound này.

Nhờ cấu trúc package, `@SpringBootTest` trong package `com.example.notification` thường tìm thấy `NotificationApplication` khi không chỉ định `classes`. Để ví dụ độc lập với quá trình tìm cấu hình, chúng ta sẽ chỉ rõ `classes = NotificationApplication.class` trong test.

## 6. Bài test chính: ghi đè bốn thuộc tính

Tạo `NotificationPropertiesOverrideTest.java`:

```java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;

@SpringBootTest(
    classes = NotificationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "notification.enabled=true",
        "notification.sender-name=Integration Test Sender",
        "notification.max-attempts=7",
        "notification.timeout=250ms"
    }
)
class NotificationPropertiesOverrideTest {

    @Autowired
    Environment environment;

    @Autowired
    NotificationProperties properties;

    @Autowired
    NotificationPlanService planService;

    @Test
    void environmentSeesTestValues() {
        assertThat(environment.getProperty("notification.enabled"))
                .isEqualTo("true");

        assertThat(environment.getProperty(
                "notification.sender-name"))
                .isEqualTo("Integration Test Sender");

        assertThat(environment.getProperty(
                "notification.max-attempts"))
                .isEqualTo("7");

        assertThat(environment.getProperty(
                "notification.timeout"))
                .isEqualTo("250ms");
    }

    @Test
    void configurationPropertiesAreBoundFromOverrides() {
        assertThat(properties.enabled()).isTrue();
        assertThat(properties.senderName())
                .isEqualTo("Integration Test Sender");
        assertThat(properties.maxAttempts()).isEqualTo(7);
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofMillis(250));
    }

    @Test
    void serviceReceivesTheSameEffectiveConfiguration() {
        NotificationPlanService.NotificationPlan plan =
                planService.currentPlan();

        assertThat(plan.enabled()).isTrue();
        assertThat(plan.senderName())
                .isEqualTo("Integration Test Sender");
        assertThat(plan.maxAttempts()).isEqualTo(7);
        assertThat(plan.timeout())
                .isEqualTo(Duration.ofMillis(250));
    }
}
```

Ba test có mục đích khác nhau:

1. **`environmentSeesTestValues`** kiểm tra property resolver của test `Environment`.
2. **`configurationPropertiesAreBoundFromOverrides`** kiểm tra Spring Boot Binder và chuyển kiểu.
3. **`serviceReceivesTheSameEffectiveConfiguration`** kiểm tra bean nghiệp vụ được inject đối tượng cấu hình đã bind.

Nếu chỉ assert `environment.getProperty(...)`, ta chưa chứng minh rằng record đã đăng ký đúng hoặc service dùng chính record đó. Nếu chỉ assert service, khi thất bại khó tách nguyên nhân giữa binding và logic service. Ví dụ kiểm tra cả ba giúp thấy luồng dữ liệu cấu hình.

## 7. Chạy test và quan sát kết quả

Với Maven wrapper:

```bash
./mvnw test
```

Với Gradle wrapper:

```bash
./gradlew test
```

Trên Windows có thể dùng `mvnw.cmd test` hoặc `gradlew.bat test` tùy hệ build. Đường dẫn/thư mục JAR không cần thiết vì test được chạy bởi build tool.

Khi ba test pass, ta có bằng chứng rằng **trong test context này**, các khóa được ghi đè như dự đoán.

Lưu ý:

- Test không làm thay đổi file `src/main/resources/application.yml`.
- `@SpringBootTest(properties=...)` chỉ có hiệu lực đối với context được tạo cho test có annotation đó, cùng các cơ chế kế thừa/caching của TestContext.
- Nếu chạy ứng dụng `NotificationApplication.main` bình thường mà không cung cấp override, nó vẫn có thể nhận `enabled=false`, `maxAttempts=2` và `timeout=5s` từ YAML.
- Test không chứng minh endpoint SMTP/email thật hoạt động, vì ví dụ không có giao tiếp bên ngoài.

**Câu cốt lõi:** Override trong annotation là một phần của **test setup**, không phải hành động sửa cấu hình lâu dài của ứng dụng.

## 8. Cú pháp properties: một chuỗi hay nhiều chuỗi?

`@SpringBootTest.properties` có kiểu **`String[]`**. Có thể khai một phần tử:

```java
@SpringBootTest(properties = "feature.mode=fast")
class FeatureModeTest {}
```

Hoặc nhiều phần tử:

```java
@SpringBootTest(properties = {
    "feature.enabled=true",
    "feature.mode=fast",
    "feature.limit=12"
})
class FeatureConfigurationTest {}
```

Mỗi phần tử đại diện cho một khai báo property dạng text. Trong bài học nên ưu tiên `key=value` để tránh nhập nhằng, vì đó là cú pháp được mô tả trực tiếp trong Javadoc `@SpringBootTest`.

**Không** đưa cả một file YAML nhiều cấp vào một phần tử và kỳ vọng annotation tự phân tích YAML:

```java
// Không nên hiểu chuỗi này là một YAML document:
@SpringBootTest(properties = "feature:\n  mode: fast")
```

Dạng phù hợp:

```java
@SpringBootTest(properties = "feature.mode=fast")
```

Khi nhiều khóa cấu hình, có cấu trúc collection/map dài hoặc cần chia sẻ giữa nhiều test, cân nhắc file `application-test.yml` hoặc `@TestPropertySource`, thay vì nhét hàng trăm dòng vào annotation.

### 8.1. Dấu cách và kiểu dữ liệu

```java
@SpringBootTest(properties = {
    "feature.label=Hello World",
    "feature.retry-count=4",
    "feature.enabled=false",
    "feature.timeout=1s"
})
```

Phần tử `"feature.label=Hello World"` có dấu cách trong value, nhưng vẫn là một `String` Java hợp lệ. Binder sau đó quyết định cách chuyển `"4"` sang `int` và `"1s"` sang `Duration`.

Nếu giá trị thực sự chứa dấu `=`, cần hiểu quy tắc parser của Java properties: thường dấu phân cách đầu tiên được dùng và phần còn lại thuộc về value trong cú pháp tương ứng. Không cố xây một parser YAML riêng bằng cách nối chuỗi; với payload phức tạp, sử dụng nguồn cấu hình hỗ trợ serialization rõ ràng.

### 8.2. Không trộn cú pháp application arguments

So sánh:

```java
@SpringBootTest(properties = "feature.mode=fast")
```

và:

```java
@SpringBootTest(args = "--feature.mode=fast")
```

Dạng đầu là **test property**. Dạng sau là **application argument** được chuyển cho ứng dụng theo API `args`. Chúng có thể khiến một khóa nhận giá trị tương tự nhưng đi qua hai cơ chế test setup khác nhau.

Đừng thêm `--` trước property trong `properties`:

```java
// Sai mục đích: phần này không phải tên canonical của property
@SpringBootTest(properties = "--feature.mode=fast")
```

Hãy dùng `feature.mode=fast` khi chọn `properties`. Dùng `args` khi mục tiêu là test chính cách ứng dụng xử lý command-line arguments.

## 9. Vì sao annotation override có tác dụng?

Spring Boot nạp các giá trị thông qua `Environment` và những `PropertySource` được sắp xếp có thứ tự. Khi Spring Test dựng `ApplicationContext`, các thuộc tính inline trong `@SpringBootTest(properties=...)` được thêm vào môi trường kiểm thử để những khóa đó có thể ghi đè giá trị từ file cấu hình thông thường.

Có thể hình dung:

```text
src/main/resources/application.yml
notification.max-attempts = 2
notification.timeout      = 5s
                   |
                   v
     Test Environment & PropertySources
                   ^
                   |
@SpringBootTest(properties = {
  notification.max-attempts = 7
  notification.timeout      = 250ms
})
                   |
                   v
           Giá trị có hiệu lực
maxAttempts = 7
timeout     = 250ms
                   |
                   v
       Binder tạo NotificationProperties
                   |
                   v
       NotificationPlanService nhận bean
```

Spring Boot không cần thay file YAML. Nó đưa một nguồn có ưu tiên thích hợp vào **test Environment** trước khi bean được bind và inject.

Đó là sự khác biệt giữa:

- **Thay nguồn cấu hình lúc dựng context:** các bean nhận giá trị mới ngay từ đầu.
- **Sửa `Environment` sau khi context đã chạy:** những bean đã bind hoặc inject thường không tự cập nhật.
- **Sửa `System.setProperty` toàn máy JVM:** có thể ảnh hưởng test khác và khó dọn sạch.
- **Sửa `application.yml` bằng code:** gây side effect lên tài nguyên của project.

`@SpringBootTest(properties=...)` giúp thiết lập một context dự đoán được mà không cần các giải pháp tác động toàn cục.

## 10. Ghi đè một phần: property không được liệt kê vẫn đến từ nguồn khác

Không bắt buộc ghi đè cả nhóm `notification.*`. Giả sử YAML vẫn là:

```yaml
notification:
  enabled: false
  sender-name: Default Sender
  max-attempts: 2
  timeout: 5s
```

Test chỉ đặt:

```java
@SpringBootTest(properties = {
    "notification.max-attempts=9"
})
```

Giá trị dự đoán:

| Thuộc tính | Giá trị có hiệu lực | Nguồn trong ví dụ |
| --- | --- | --- |
| `notification.enabled` | `false` | YAML |
| `notification.sender-name` | `Default Sender` | YAML |
| `notification.max-attempts` | `9` | Inline test property |
| `notification.timeout` | `5s` | YAML |

Spring không “thay toàn bộ nhóm `notification`” chỉ vì một key được override. Property resolution được thực hiện theo khóa và các quy tắc binding cho cấu trúc đích.

Có một ngoại lệ kiến trúc cần nhớ: với **List** và một số cấu trúc collection, Spring Boot có những quy tắc thay thế/merge khác với map và scalar giữa các nguồn. Không áp dụng bảng scalar trên như lời khẳng định rằng mọi collection đều merge từng phần tử. Khi test danh sách hoặc Map, cần đọc quy tắc binder tương ứng.

### 10.1. Test dùng giá trị còn lại từ YAML

```java
@SpringBootTest(
    classes = NotificationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "notification.max-attempts=9"
)
class PartialOverrideTest {

    @Autowired
    NotificationProperties properties;

    @Test
    void changesOnlyChosenProperty() {
        assertThat(properties.enabled()).isFalse();
        assertThat(properties.senderName())
                .isEqualTo("Default Sender");
        assertThat(properties.maxAttempts()).isEqualTo(9);
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofSeconds(5));
    }
}
```

Trong snippet cần có imports tương tự test ở phần 6. Để giữ một example có thể chạy độc lập, đặt test trong package `com.example.notification` và khai báo các import đã trình bày.

## 11. So sánh với một test không override

Tạo một lớp riêng `NotificationDefaultsTest.java`:

```java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(
    classes = NotificationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class NotificationDefaultsTest {

    @Autowired
    NotificationProperties properties;

    @Test
    void readsFileValuesWhenNoTestOverrideIsDeclared() {
        assertThat(properties.enabled()).isFalse();
        assertThat(properties.senderName())
                .isEqualTo("Default Sender");
        assertThat(properties.maxAttempts()).isEqualTo(2);
        assertThat(properties.timeout())
                .isEqualTo(Duration.ofSeconds(5));
    }
}
```

Hai class test mô tả hai cấu hình:

```text
NotificationDefaultsTest:
  @SpringBootTest              -> YAML baseline

NotificationPropertiesOverrideTest:
  @SpringBootTest(properties)  -> test overrides + YAML baseline
```

Spring TestContext có cơ chế cache context. Vì tập cấu hình đã dùng để dựng context khác nhau, các test có cấu hình khác nhau thường nhận các context tương ứng thay vì trộn dữ liệu không rõ ràng.

Điều quan trọng hơn việc nhớ cách cache nội bộ là **không chủ động biến test thành một chương trình thay đổi global state**. Chọn cấu hình tường minh tại lớp test và để Spring TestContext quản lý lifecycle.

## 12. Ghi đè giá trị dùng trong @Value

Không phải ứng dụng nào cũng chỉ dùng `@ConfigurationProperties`. Một bean có thể đọc thuộc tính bằng `@Value`:

```java
package com.example.notification;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class SenderLabel {

    private final String value;

    public SenderLabel(
            @Value("${notification.sender-name}") String value) {
        this.value = value;
    }

    public String value() {
        return value;
    }
}
```

Với test:

```java
@SpringBootTest(properties = {
    "notification.sender-name=Sender From Test"
})
class SenderLabelTest {

    @Autowired
    SenderLabel senderLabel;

    @Test
    void valueAnnotationSeesTestProperty() {
        assertThat(senderLabel.value())
                .isEqualTo("Sender From Test");
    }
}
```

Vì `@Value` được xử lý khi bean khởi tạo, annotation test property đã được thêm vào môi trường trước đó nên bean có thể nhận giá trị override.

### 12.1. Giá trị mặc định ở @Value

Ví dụ:

```java
@Value("${notification.sender-name:Anonymous}")
String senderName;
```

Mặc định `Anonymous` chỉ dùng khi thuộc tính không có giá trị phù hợp theo cơ chế placeholder. Nếu YAML hoặc `@SpringBootTest(properties=...)` cung cấp khóa, bean lấy giá trị đã tìm thấy.

Đừng nhầm fallback `:Anonymous` của placeholder với test property có ưu tiên cao. Khi một nguồn test khai value rỗng, nó có thể ảnh hưởng behavior khác với việc khóa không tồn tại; các source thường coi `""` là một giá trị được cấp.

## 13. Ghi đè và @ConfigurationProperties constructor binding

Với record:

```java
@ConfigurationProperties(prefix = "payment")
public record PaymentProperties(
        URI gatewayUrl,
        Duration timeout,
        int maxAttempts
) {}
```

Cấu hình:

```yaml
payment:
  gateway-url: https://payment.example.invalid
  timeout: 3s
  max-attempts: 2
```

Test:

```java
@SpringBootTest(properties = {
    "payment.timeout=400ms",
    "payment.max-attempts=5"
})
```

Binder tạo record với `timeout=Duration.ofMillis(400)` và `maxAttempts=5`, trong khi `gatewayUrl` vẫn lấy từ YAML nếu không có nguồn ưu tiên cao hơn ghi đè.

Nếu người viết test đặt:

```java
@SpringBootTest(properties = "payment.max-attempts=not-a-number")
```

và Java yêu cầu `int`, test có thể thất bại **trong giai đoạn dựng context** do conversion error. Đây là một kết quả có ích khi kiểm tra tính đúng đắn của cấu hình, nhưng nó khác với một assertion thất bại sau khi test method chạy.

### 13.1. Đừng khai báo key sai tên rồi nghĩ đã override

`payment.max-attemtps` (sai chính tả) không phải tên canonical `payment.max-attempts`. Binder có thể bỏ qua một khóa không có đích trong một số cấu hình và vẫn lấy giá trị từ YAML cho trường đúng.

Nếu test luôn assert `properties.maxAttempts()` thay vì chỉ kiểm tra test method có chạy, nó giúp phát hiện việc override không thực sự có tác dụng.

Relaxed binding hỗ trợ các biến thể hợp lệ của tên thuộc tính; nó không tự sửa mọi lỗi chính tả.

## 14. Ghi đè thuộc tính điều khiển @ConditionalOnProperty

Một ứng dụng có thể bật/tắt bean dựa trên property:

```java
package com.example.notification;

public interface AuditSink {
    String channel();
}
```

Một implementation:

```java
package com.example.notification;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;

@Component
@ConditionalOnProperty(
    prefix = "audit",
    name = "enabled",
    havingValue = "true"
)
public class ConsoleAuditSink implements AuditSink {

    @Override
    public String channel() {
        return "console";
    }
}
```

Với YAML:

```yaml
audit:
  enabled: false
```

Bean `ConsoleAuditSink` không được tạo trong trường hợp điều kiện tương ứng không đạt.

Test bật bean:

```java
@SpringBootTest(
    classes = NotificationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "audit.enabled=true"
)
class AuditEnabledTest {

    @Autowired
    ApplicationContext context;

    @Test
    void createsAuditSinkWhenEnabled() {
        assertThat(context.getBeansOfType(AuditSink.class))
                .hasSize(1);
    }
}
```

Test tắt bean:

```java
@SpringBootTest(
    classes = NotificationApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "audit.enabled=false"
)
class AuditDisabledTest {

    @Autowired
    ApplicationContext context;

    @Test
    void omitsAuditSinkWhenDisabled() {
        assertThat(context.getBeansOfType(AuditSink.class))
                .isEmpty();
    }
}
```

Cần import `org.springframework.context.ApplicationContext` và các import test cơ bản như phần trước. Hai class phải nằm trong package có component scanning nhận được `ConsoleAuditSink`.

Khi `@ConditionalOnProperty` được đánh giá lúc dựng bean definitions/context, test property đã có mặt nên có thể thay đổi **cấu trúc bean trong context**, không chỉ giá trị của một trường.

### 14.1. Không nên thay cờ sau khi bean đã được tạo

Nếu một test làm:

```java
System.setProperty("audit.enabled", "true");
```

**sau khi** context được dựng với `audit.enabled=false`, điều đó không tự tạo thêm `ConsoleAuditSink`. Bean condition không phải một bộ lắng nghe các thay đổi property liên tục. Muốn thử hai trạng thái, dùng hai context test riêng hoặc một cơ chế test context được xây cho mục đích đó.

## 15. Precedence: khi giá trị bị khai ở nhiều nơi

Một giá trị cấu hình có thể đồng thời xuất hiện trong:

- `src/main/resources/application.yml`.
- `src/test/resources/application.yml` hoặc file cấu hình test khác trên classpath.
- `application-test.yml` khi active profile `test`.
- Biến môi trường của CI.
- Java system properties.
- Command-line/application arguments.
- `@SpringBootTest(properties=...)`.
- `@TestPropertySource`.
- `@DynamicPropertySource`.

Đối với bài học này, quy tắc quan trọng nhất:

**Giá trị được cấp bằng `@SpringBootTest(properties=...)` được thiết kế để có ưu tiên cao hơn những nguồn cấu hình thông thường như Config Data, biến môi trường và Java system properties trong test context.**

Ví dụ:

```text
application.yml:
  notification.max-attempts = 2

CI environment:
  NOTIFICATION_MAXATTEMPTS = 6

@SpringBootTest(properties):
  notification.max-attempts = 7

Kết quả của test trong điều kiện tương ứng:
  maxAttempts = 7
```

Sự khác biệt này cho phép test không phụ thuộc vào một biến môi trường được người phát triển hoặc pipeline thiết lập trước đó.

### 15.1. Đừng thuộc lòng một danh sách thứ tự duy nhất cho mọi annotation

`@TestPropertySource` và `@DynamicPropertySource` cũng có precedence cao; quan hệ ưu tiên khi nhiều cơ chế cùng khai **đúng một key** cần xét quy tắc của Spring TestContext, Spring Boot và phiên bản đang dùng.

Thực hành an toàn là:

1. Mỗi key cần override trong một test nên có **một nguồn test chịu trách nhiệm rõ ràng**.
2. Tránh đồng thời khai cùng key qua `@SpringBootTest(properties=...)`, `@TestPropertySource` và `@DynamicPropertySource` nếu không phải chủ đích test precedence.
3. Nếu bài test nhằm chứng minh precedence, hãy assert `Environment` và giá trị bean đã bind, không dựa vào suy đoán.
4. Khi nâng cấp Spring Boot/Spring Framework, kiểm chứng lại những test chồng lấn nguồn cấu hình.

Trong các trường hợp thông thường không có tranh chấp với một nguồn test ưu tiên cao khác, inline `properties` sẽ override những giá trị cùng tên ở file cấu hình ứng dụng.

## 16. @SpringBootTest(properties) và @ActiveProfiles("test")

`@ActiveProfiles` đến từ Spring Test:

```java
import org.springframework.test.context.ActiveProfiles;
```

Annotation này dùng để xác định profile hoạt động khi TestContext nạp application context.

Ví dụ:

```java
@ActiveProfiles("test")
@SpringBootTest(
    classes = NotificationApplication.class,
    properties = "notification.max-attempts=7"
)
class ProfilePlusOverrideTest {}
```

Tạo `src/test/resources/application-test.yml`:

```yaml
notification:
  enabled: false
  sender-name: Test Profile Sender
  max-attempts: 4
  timeout: 2s
```

Khi test dùng profile `test`:

- `senderName` có thể lấy `Test Profile Sender`.
- `timeout` có thể lấy `2s`.
- `maxAttempts` lấy `7` từ `@SpringBootTest.properties` vì key đó được override.
- `enabled` lấy giá trị từ profile hoặc nguồn khác có ưu tiên tương ứng.

Bảng:

| Key | File chung | File profile test | Inline override | Giá trị dự đoán |
| --- | --- | --- | --- | --- |
| `enabled` | false | false | Không | false |
| `sender-name` | Default Sender | Test Profile Sender | Không | Test Profile Sender |
| `max-attempts` | 2 | 4 | 7 | 7 |
| `timeout` | 5s | 2s | Không | 2s |

**Vai trò khác nhau:**

- `@ActiveProfiles("test")` chọn **một bộ cấu hình theo profile**, có thể chứa nhiều khóa và điều kiện bean.
- `@SpringBootTest(properties=...)` đưa **một số giá trị inline cụ thể** vào test Environment.

Hai cách bổ sung cho nhau. Không nên dùng `@ActiveProfiles` như một cách viết thay thế mọi property một lần, hoặc dùng hàng trăm inline property thay cho một profile test được chia sẻ giữa nhiều lớp.

### 16.1. Tại sao không nên gán spring.profiles.active tùy tiện?

Có người thử:

```java
@SpringBootTest(properties = "spring.profiles.active=test")
```

Trong một số trường hợp điều này có thể ảnh hưởng profile khi context được dựng, nhưng với Spring Test, `@ActiveProfiles` là công cụ được thiết kế chuyên để khai báo active profiles của test.

Khi mục tiêu là xác định profile cho context, ưu tiên `@ActiveProfiles("test")` để ý định rõ và TestContext quản lý thông tin cấu hình. Dùng inline property cho những giá trị nghiệp vụ cụ thể muốn override.

## 17. @SpringBootTest(properties) so với @TestPropertySource

`@TestPropertySource` là annotation của Spring TestContext:

```java
import org.springframework.test.context.TestPropertySource;
```

Nó có thể cấp inline properties hoặc chỉ định file properties riêng cho integration test.

Ví dụ inline:

```java
@SpringBootTest(classes = NotificationApplication.class)
@TestPropertySource(properties = {
    "notification.enabled=true",
    "notification.max-attempts=8"
})
class NotificationTestPropertySourceTest {}
```

Hoặc nạp file:

```java
@SpringBootTest(classes = NotificationApplication.class)
@TestPropertySource(
    locations = "classpath:/notification-fixture.properties"
)
class NotificationFixtureTest {}
```

`src/test/resources/notification-fixture.properties`:

```properties
notification.enabled=true
notification.sender-name=Fixture Sender
notification.max-attempts=8
notification.timeout=1s
```

So sánh:

| Cơ chế | Khi nào phù hợp? |
| --- | --- |
| `@SpringBootTest(properties=...)` | Vài giá trị cố định, gắn trực tiếp với lớp test Boot |
| `@TestPropertySource(properties=...)` | Muốn dùng cách khai test property của Spring Framework |
| `@TestPropertySource(locations=...)` | Một tệp test properties dùng lại ở nhiều test |
| `@ActiveProfiles("test")` | Một bộ giá trị và bean conditions theo profile |
| `@DynamicPropertySource` | Giá trị chỉ biết lúc runtime, như host/port Testcontainers |

Có thể kết hợp trong một dự án, nhưng nên tránh chồng chéo **cùng key** giữa các cơ chế mà không có lý do. Với câu hỏi “test này chỉ cần đổi timeout và max-attempts”, `@SpringBootTest(properties=...)` thường là lựa chọn ngắn gọn nhất.

## 18. So sánh với @DynamicPropertySource

Một số giá trị không biết được lúc biên dịch test:

- Port do Testcontainers cấp ngẫu nhiên.
- Endpoint của mock server chạy trong test.
- URL database chạy ở cổng động.
- Địa chỉ của broker thử nghiệm.
- Credential thử nghiệm được cấp bởi tài nguyên test ngắn hạn.

Với những trường hợp đó, `@DynamicPropertySource` là extension point phù hợp:

```java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

class IntegrationTestBase {

    @DynamicPropertySource
    static void registerDynamicProperties(
            DynamicPropertyRegistry registry) {
        registry.add(
            "external.service.port",
            () -> TestServerHolder.port()
        );
    }
}
```

`TestServerHolder` ở đây là lớp minh họa mà project phải tự định nghĩa để quản lý tài nguyên thử nghiệm; đây không phải class có sẵn của Spring.

So sánh với giá trị cố định:

```java
@SpringBootTest(properties = "external.service.port=9099")
```

Nếu port của mock server thay đổi sau mỗi lần chạy, hard-code `9099` sẽ khiến test dễ sai. `@DynamicPropertySource` cho phép cung cấp giá trị được xác định trong lifecycle test.

Spring Framework mô tả dynamic test properties có precedence cao hơn nhiều nguồn test tĩnh; vì vậy tránh khai đồng thời cùng key ở `@SpringBootTest.properties` và `@DynamicPropertySource` nếu không định kiểm tra behavior precedence.

### 18.1. Không lạm dụng dynamic property

Nếu chỉ cần:

```java
"feature.enabled=false"
"notification.max-attempts=1"
```

thì `@SpringBootTest(properties=...)` rõ ràng và dễ đọc hơn một supplier phức tạp. Dùng `@DynamicPropertySource` khi giá trị **phụ thuộc tài nguyên runtime**, không chỉ để đưa một literal string vào Environment.

## 19. @SpringBootTest(properties) không phải @TestPropertySource(locations)

Một ngộ nhận:

```java
@SpringBootTest(properties = "classpath:/my-test.properties")
```

Chuỗi ở đây **không phải chỉ thị nạp một tệp** theo cách `@TestPropertySource(locations=...)` hỗ trợ. `@SpringBootTest.properties` muốn danh sách **property inline**.

Nếu muốn nạp file reusable:

```java
@TestPropertySource(
    locations = "classpath:/my-test.properties"
)
```

hoặc sử dụng Config Data/profile của Spring Boot theo yêu cầu.

Nếu muốn inline:

```java
@SpringBootTest(properties = {
    "my.feature.enabled=true",
    "my.feature.name=test"
})
```

Đây là ranh giới cú pháp rất quan trọng: **file location** và **property declaration** là hai loại tham số khác nhau.

## 20. Ghi đè cho bean có @Value và bean đọc Environment trực tiếp

Giả sử một class đọc property ngay ở constructor:

```java
@Component
public class AuditPolicy {

    private final boolean enabled;

    public AuditPolicy(Environment env) {
        this.enabled = Boolean.parseBoolean(
            env.getProperty("audit.enabled", "false")
        );
    }

    public boolean enabled() {
        return enabled;
    }
}
```

Khi test có:

```java
@SpringBootTest(properties = "audit.enabled=true")
```

và context dựng bean sau khi test properties được thiết lập, `enabled` có thể là `true`.

Điều này cho thấy property override tác động lên **mọi thành phần tiêu thụ giá trị từ cùng test Environment** theo thời điểm của chúng:

- `Environment`: đọc khi gọi phương thức.
- `@Value`: thường tiêm khi tạo bean.
- `@ConfigurationProperties`: bind khi tạo/cập nhật bean theo cơ chế ứng dụng.
- `@ConditionalOnProperty`: thường ảnh hưởng quyết định đăng ký bean.
- `@Configuration` factory bean: có thể đọc cấu hình khi tạo hạ tầng.

**Không được suy ra rằng tất cả sẽ tự động refresh sau khi một property đổi lần nữa.** Annotation test chủ yếu chuẩn bị environment **trước khi context khởi tạo**.

## 21. Những property nào nên override trong test?

Một số nhóm thường hợp lý:

### 21.1. Cờ tính năng

```java
@SpringBootTest(properties = {
    "features.discount.enabled=true"
})
```

Kiểm tra bean điều kiện, hành vi service hoặc một nhánh nghiệp vụ cụ thể.

### 21.2. Giới hạn và timeout

```java
@SpringBootTest(properties = {
    "batch.max-items=25",
    "client.connect-timeout=100ms"
})
```

Test các trường giá trị có kiểu và logic sử dụng giá trị. Trong unit test không khởi động Spring, truyền object cấu hình trực tiếp vẫn nhanh hơn.

### 21.3. URL giả hoặc mock endpoint

```java
@SpringBootTest(properties = {
    "partner.endpoint=http://127.0.0.1:18080"
})
```

Chỉ dùng port cố định nếu test thực sự quản lý tài nguyên tương ứng và tránh xung đột. Với mock server cấp port ngẫu nhiên, dùng `@DynamicPropertySource`.

### 21.4. Tắt các scheduler hoặc công việc tự động

```java
@SpringBootTest(properties = {
    "app.scheduler.enabled=false",
    "app.outbound.enabled=false"
})
```

Đây là những **key do ứng dụng định nghĩa** trong ví dụ; chúng không tự có hiệu lực trong Spring nếu code của dự án chưa đọc và sử dụng chúng. Một dòng inline property không làm vô hiệu hóa một scheduler hoặc client bất kỳ khi ứng dụng không có cấu hình/điều kiện tương ứng.

### 21.5. Cấu hình test-specific

```java
@SpringBootTest(properties = {
    "app.test-mode=true",
    "app.display-label=Integration Example"
})
```

Nên ghi rõ khóa nào chỉ dùng trong test và tránh khiến logic production phụ thuộc vào các “cờ test” không có mô hình rõ ràng.

## 22. Xác nhận giá trị bằng Environment và Binder

Khi một test fail vì giá trị bất ngờ, không nên kết luận ngay rằng `@SpringBootTest.properties` bị bỏ qua. Hãy quan sát hai lớp:

```java
@Autowired Environment env;

@Autowired NotificationProperties props;
```

Rồi assert:

```java
assertThat(env.getProperty("notification.max-attempts"))
    .isEqualTo("7");

assertThat(props.maxAttempts())
    .isEqualTo(7);
```

Nếu Environment là `7` nhưng record là `2` hoặc `0`, có thể cần xem:

1. `NotificationProperties` đã được đăng ký chưa?
2. Có đang inject đúng bean `NotificationProperties` không?
3. Tên prefix, tên trường và cách relaxed binding có đúng không?
4. Có bean khác đọc/configure giá trị sớm theo cách riêng không?
5. Có nhiều context và test đang assert trên context khác không?
6. Có logic custom binding hoặc refresh khiến thời điểm quan sát khác nhau không?

Nếu cả Environment lẫn record đều không nhận `7`, kiểm tra chính tả khóa, annotation test trên class nào và nguồn test khác có ghi đè hay không.

### 22.1. Không in mọi PropertySource ra log

Đôi khi developer định in toàn bộ `Environment` hoặc mọi key/value để debug. Điều này có thể làm lộ secret từ CI, database credentials hoặc token. Nên in tên nguồn và một số key vô hại đã chọn lọc, hoặc dùng assertion cho giá trị kiểm thử đã biết.

```java
assertThat(env.getProperty("notification.max-attempts"))
        .isEqualTo("7");
```

Đối với token, nên dùng một **sentinel giả** và tránh log giá trị thật của hệ thống.

## 23. Giá trị rỗng và property chưa khai báo

Có sự khác biệt giữa:

```java
@SpringBootTest(properties = "demo.label=")
```

và **không** khai `demo.label` ở annotation.

Trường hợp đầu cung cấp một giá trị text rỗng cho khóa `demo.label`. Nguồn inline có thể thắng giá trị khác từ YAML. Trường hợp sau để resolver tìm tiếp ở những nguồn còn lại.

Ví dụ YAML:

```yaml
demo:
  label: Default Label
```

Test:

```java
@SpringBootTest(properties = "demo.label=")
```

Có thể khiến `Environment.getProperty("demo.label")` trả chuỗi rỗng, không phải `Default Label`. Đây là đặc điểm của **property resolution theo thứ tự ưu tiên**.

Nếu giá trị bắt buộc không rỗng, cần validation phù hợp, ví dụ `@NotBlank` trong `@ConfigurationProperties` với Jakarta Validation provider. Việc YAML có default không tự sửa một chuỗi rỗng được cấp từ nguồn ưu tiên cao hơn.

### 23.1. Trường hợp null và thiếu property

`@SpringBootTest.properties` là tập chuỗi; nó không phải API chuẩn để khai một `null` literal có cùng ngữ nghĩa với “không có property”. Viết:

```java
@SpringBootTest(properties = "demo.label=null")
```

thường tạo chuỗi văn bản `"null"`, **không có nghĩa** loại bỏ khóa khỏi `Environment`. Để test “khóa vắng mặt”, cần kiểm soát những nguồn cấu hình đang cấp khóa hoặc dùng môi trường test tối giản.

## 24. Ghi đè dữ liệu dạng List và Map

Với giá trị đơn như `int`, `boolean`, `String`, `Duration`, một chuỗi `key=value` thường đơn giản. Với List/Map, phải lưu ý cú pháp binding.

Ví dụ class:

```java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
    List<String> destinations,
    Map<String, String> handlers
) {}
```

Có thể cấp các entry theo tên property:

```java
@SpringBootTest(properties = {
    "routing.destinations[0]=primary",
    "routing.destinations[1]=secondary",
    "routing.handlers[/api/v1]=orders"
})
```

Những mục List dùng chỉ số `[0]`, `[1]`. Với Map key chứa slash `/`, bracket notation bảo toàn key literal `/api/v1` khi binder xử lý.

Lưu ý:

- Trong Java string của `@SpringBootTest.properties` không cần bao ngoặc vuông của Map key bằng dấu nháy YAML, vì đây không phải tài liệu YAML.
- Danh sách có quy tắc binding và override riêng; không nên đoán rằng index `0` từ một nguồn sẽ tự merge với index `1` từ nguồn khác theo mọi tình huống.
- Nếu configuration phức tạp hoặc rất dài, file `application-test.yml` thường dễ đọc hơn nhiều string inline.

### 24.1. Khi Map key chứa dấu chấm

Với `Map<String, Object>`, viết:

```java
"routing.options[feature.beta]=on"
```

để tránh việc dấu chấm trong key bị hiểu như một cấp thuộc tính lồng nhau. Với `Map<String,String>`, có một số trường hợp dấu chấm đã được binder giữ khi không có ngoặc; nhưng dùng `[feature.beta]` làm ý định key literal rõ ràng hơn.

## 25. Validation: test property sai có thể làm context không khởi động

Giả sử một lớp cấu hình có ràng buộc:

```java
import jakarta.validation.constraints.Min;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        @Min(1) int maxAttempts
) {}
```

Nếu test khai:

```java
@SpringBootTest(properties = {
    "notification.max-attempts=0"
})
class InvalidNotificationPropertiesTest {}
```

và Spring Boot được cấu hình với validation provider thích hợp, context có thể **không khởi động** vì `@Min(1)` không đạt. Khi đó test không vào method để assert các giá trị bình thường.

Đây là kết quả dự kiến nếu mục tiêu là kiểm tra ứng dụng từ chối cấu hình sai, nhưng **`@SpringBootTest` không phải lúc nào cũng là công cụ tiện nhất để assert một startup failure**: annotation tự dựng context trước khi chạy test method.

Một cách thích hợp hơn cho các tình huống “một trường sai phải gây lỗi khởi động” là `ApplicationContextRunner`, được thiết kế để bạn quan sát context có startup failure hay không mà không khiến toàn bộ lớp test tự thất bại trước khi vào assertion.

## 26. Kiểm thử trường hợp cấu hình không hợp lệ bằng ApplicationContextRunner

Ví dụ:

```java
package com.example.notification;

import static org.assertj.core.api.Assertions.assertThat;

import jakarta.validation.constraints.Min;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.context.PropertyPlaceholderAutoConfiguration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;

class ValidationFailureTest {

    @Validated
    @ConfigurationProperties(prefix = "limits")
    record LimitProperties(@Min(1) int maxItems) {}

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(LimitProperties.class)
    static class LimitConfig {}

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(LimitConfig.class);

    @Test
    void rejectsZero() {
        runner.withPropertyValues("limits.max-items=0")
            .run(context ->
                assertThat(context.getStartupFailure()).isNotNull()
            );
    }
}
```

Để hoạt động như mong muốn, context test cần có một Jakarta Validation provider và integration của Spring Boot được thiết lập đúng, ví dụ qua `spring-boot-starter-validation` trong project.

`PropertyPlaceholderAutoConfiguration` trong đoạn imports không cần thiết cho test chính này; có thể bỏ import để ví dụ gọn. Trọng tâm là `ApplicationContextRunner.withPropertyValues(...)` cung cấp test properties và callback nhận kết quả dựng context.

**Phân biệt hai mục tiêu:**

- `@SpringBootTest(properties=...)`: khởi động context thành công với **cấu hình hợp lệ** rồi kiểm tra bean/hành vi.
- `ApplicationContextRunner`: thuận tiện khi muốn kiểm tra nhiều cấu hình thành công và **cấu hình gây startup failure**.

Đừng để một test kỳ vọng lỗi startup dùng `@SpringBootTest` rồi assert trong method khi method đó không bao giờ được chạy.

## 27. Context caching: vì sao nhiều test dùng chung ApplicationContext?

Spring TestContext Framework có context cache. Nếu nhiều lớp test có cùng cấu hình context tương thích, framework có thể tái sử dụng context thay vì khởi tạo từ đầu, giúp test suite nhanh hơn.

Thông tin cấu hình test có thể ảnh hưởng cache key, ví dụ:

- Class cấu hình được tải.
- Active profiles.
- Inline test properties.
- Test property source locations.
- Context customizers, bao gồm những nguồn dynamic hoặc test-specific.
- Parent context, loader và các lựa chọn khác theo TestContext.

Do đó hai lớp:

```java
@SpringBootTest(properties = "app.mode=A")
class ModeATest {}
```

và:

```java
@SpringBootTest(properties = "app.mode=B")
class ModeBTest {}
```

thường không chia sẻ một context giống hệt nhau, vì cấu hình test khác biệt.

Tuy nhiên, **không nên biến cache thành cơ chế quản lý trạng thái nghiệp vụ**. Nếu một test đổi state của singleton bean, cache có thể khiến test khác thấy ảnh hưởng khi chúng chia sẻ context. Tách test state, reset dữ liệu hoặc dùng công cụ thích hợp; không dựa vào việc đổi một inline property để xử lý mọi dạng state leakage.

### 27.1. Dùng @DirtiesContext khi nào?

`@DirtiesContext` báo rằng context đã bị làm bẩn và không nên được tái sử dụng theo cách thông thường.

Không cần gắn `@DirtiesContext` cho mọi lớp chỉ vì chúng dùng `@SpringBootTest(properties=...)`. Cấu hình inline khác nhau đã góp phần xác định context phù hợp.

Lạm dụng `@DirtiesContext` làm tăng số lần tạo context và khiến bộ test chậm hơn. Chỉ dùng khi test thật sự làm thay đổi trạng thái context mà không thể dọn sạch bằng một cách rẻ hơn hoặc phù hợp hơn.

## 28. Tránh System.setProperty trong kiểm thử chạy song song

Cách viết:

```java
@Test
void something() {
    System.setProperty("notification.max-attempts", "7");
    // ...
}
```

có nhiều nguy cơ:

1. System properties là trạng thái **chia sẻ trong JVM**.
2. Các test chạy song song có thể ghi đè giá trị của nhau.
3. Nếu quên dọn, test sau có thể bị ảnh hưởng.
4. Nếu Spring context đã được khởi tạo trước test method, thay đổi có thể đến quá muộn.
5. Một bean `@ConfigurationProperties` đã tạo không tự được bind lại.
6. Việc kiểm tra thứ tự test vô tình trở thành yếu tố quyết định.

`@SpringBootTest(properties=...)` thường phù hợp hơn khi cần xác định một số giá trị cho **quá trình khởi tạo context của một lớp test**. Nó làm test setup có tính khai báo và hạn chế side effect toàn cục.

Nếu bắt buộc test một API đọc system property trực tiếp ngoài Spring, cần quản lý scope và rollback state một cách rõ ràng; đây là bài toán khác với Spring Boot externalized configuration.

## 29. Khi có nhiều lớp test với các override tương tự

Một codebase có thể có nhiều test cùng cần:

```java
"app.scheduler.enabled=false"
"app.outbound.enabled=false"
"notification.timeout=100ms"
```

Có thể tổ chức theo ba cách:

### 29.1. Inline từng lớp

Phù hợp khi có 1–3 khóa riêng cho từng test:

```java
@SpringBootTest(properties = {
    "app.scheduler.enabled=false",
    "notification.timeout=100ms"
})
class NotificationServiceTest {}
```

Ưu điểm: đọc lớp test là thấy ngay cấu hình. Nhược điểm: lặp khai báo khi nhiều lớp.

### 29.2. Profile test dùng chung

Tạo `src/test/resources/application-test.yml` và dùng:

```java
@ActiveProfiles("test")
@SpringBootTest
class NotificationServiceTest {}
```

Phù hợp khi có một bộ cấu hình test chung. Nếu một lớp cần thêm vài override, vẫn có thể kết hợp `properties`.

### 29.3. Composed annotation cho chính sách chung

Java cho phép định nghĩa annotation test riêng:

```java
import java.lang.annotation.Retention;
import java.lang.annotation.Target;
import org.springframework.boot.test.context.SpringBootTest;

import static java.lang.annotation.ElementType.TYPE;
import static java.lang.annotation.RetentionPolicy.RUNTIME;

@Target(TYPE)
@Retention(RUNTIME)
@SpringBootTest(properties = {
    "app.scheduler.enabled=false",
    "app.outbound.enabled=false"
})
public @interface SafeIntegrationTest {
}
```

Sau đó:

```java
@SafeIntegrationTest
class ApplicationSafetyTest {}
```

Cách này giúp chuẩn hóa cấu hình common baseline cho nhiều test. Nhưng đừng đặt tất cả property của mọi module vào một annotation quá lớn; test khó biết mình thực sự phụ thuộc vào những giá trị nào.

Nếu cần thay giá trị riêng của một lớp test dùng composed annotation, cần hiểu cách các annotation kế thừa và được xử lý trong TestContext. Không nên giả định việc đặt hai `@SpringBootTest` ở cùng cấp hoặc hai annotation meta cùng loại sẽ tự merge theo thứ tự trực giác.

## 30. Khi nào không nên dùng @SpringBootTest?

`@SpringBootTest` có thể tải nhiều auto-configuration và bean hơn mức cần thiết. Dùng nó để kiểm tra logic Java thuần thường làm test chậm không cần thiết.

### 30.1. Unit test service không cần Spring

```java
@Test
void planUsesProvidedProperties() {
    NotificationProperties props =
        new NotificationProperties(
            true,
            "Unit Sender",
            3,
            Duration.ofSeconds(1)
        );

    NotificationPlanService service =
        new NotificationPlanService(props);

    assertThat(service.currentPlan().maxAttempts())
        .isEqualTo(3);
}
```

Đây là unit test; không cần `@SpringBootTest` hay file YAML vì mục tiêu chỉ là logic service.

### 30.2. Test binder/auto-configuration nhỏ

`ApplicationContextRunner` có thể tạo context nhỏ, cấp properties và kiểm tra điều kiện. Phù hợp cho nhiều tổ hợp cấu hình có trạng thái pass/fail.

### 30.3. Test MVC slice

Nếu chỉ kiểm tra controller, `@WebMvcTest` cùng mock dependency có thể phù hợp hơn một full context. Nhưng nếu mục tiêu là xác nhận binder, service và wiring đầy đủ, `@SpringBootTest` hợp lý.

**Quy tắc lựa chọn:** dùng công cụ nhẹ nhất vẫn kiểm tra đúng điều cần chứng minh. Với bài học này, `@SpringBootTest(properties=...)` được chọn có chủ đích để test cấu hình **trong một Spring Boot context**.

## 31. Ghi đè thuộc tính để tránh gọi dịch vụ thật

Một mục tiêu rất thực tế là giữ integration test không vô tình liên hệ tài nguyên production.

Ví dụ trong ứng dụng có:

```yaml
partner:
  endpoint: https://partner.example.invalid
```

Test có thể khai:

```java
@SpringBootTest(properties = {
    "partner.endpoint=http://127.0.0.1:18080",
    "partner.outbound.enabled=false"
})
```

Nhưng **một property override không đảm bảo code sẽ không gọi mạng**. Điều đó chỉ đúng nếu bean/client thật sự đọc `partner.outbound.enabled` và tôn trọng cơ chế tắt kết nối.

Các chiến lược bảo vệ bổ sung:

- Dùng fake adapter hoặc mock bean cho client khi test logic.
- Nếu cần HTTP integration test, dùng mock server quản lý lifecycle và cổng rõ ràng.
- Sử dụng port ngẫu nhiên và `@DynamicPropertySource` khi cần.
- Không đặt endpoint production hoặc token production trong fixture test.
- Kiểm tra ApplicationRunner/CommandLineRunner không thực thi tác vụ thật khi context khởi động.
- Không giả định `webEnvironment=NONE` sẽ ngăn những bean bất kỳ mở kết nối chủ động: nó chỉ không tạo web environment cho ứng dụng.

Test có cấu hình đúng vẫn cần kiến trúc isolation để không gây side effect lên hệ thống bên ngoài.

## 32. Một số tên property có ảnh hưởng tới giai đoạn khởi động sớm

`@SpringBootTest(properties=...)` được thêm khi dựng test context, trước nhiều bước binding và bean creation. Vì vậy nó phù hợp cho nhiều thuộc tính khởi động.

Ví dụ:

```java
@SpringBootTest(properties = {
    "spring.main.banner-mode=off",
    "logging.level.com.example.notification=DEBUG"
})
```

Tuy nhiên, các thuộc tính được Spring Boot sử dụng ở những giai đoạn rất sớm có thể có đặc thù về thời điểm áp dụng. Nếu mục tiêu test một behavior bootstrap đặc biệt như Config Data location/import, logging initialization hoặc custom `SpringApplication` builder, không nên suy đoán mọi property inline có cùng effect như một đối số được truyền trước khi `SpringApplication` bắt đầu.

Hãy đọc tài liệu version đang dùng và viết integration test chuyên cho behavior khởi động ấy. Ví dụ bài này tập trung vào **giá trị được bean tiêu thụ trong context**, nơi inline test properties là cơ chế chuẩn.

### 32.1. main method không nhất thiết được gọi

Theo `@SpringBootTest` hiện đại, khi không chỉ định `useMainMethod`, test context thường được dựng mà không tự gọi phương thức `main` của ứng dụng. Nếu `main` thiết lập thêm profiles hoặc default properties theo code, behavior của test có thể khác so với khi chạy JAR.

Khi cần kiểm tra chính logic ở `main`, có thể chọn một giá trị `useMainMethod` phù hợp với phiên bản đang dùng, ví dụ `SpringBootTest.UseMainMethod.ALWAYS`. Không dùng nó chỉ để kiểm tra vài property override thông thường.

## 33. Ghi đè cùng khóa trong nhiều lớp và kế thừa test

Một base test có thể khai cấu hình chung:

```java
@SpringBootTest(properties = {
    "notification.enabled=false",
    "notification.timeout=1s"
})
abstract class BaseNotificationIntegrationTest {}
```

Lớp con dùng kế thừa test configuration theo quy tắc của Spring TestContext. Nhưng cần lưu ý rằng **annotation inheritance và merging không đồng nghĩa** với việc mọi `String[] properties` từ hai annotation cùng tên luôn được nối lại theo ý muốn.

Nếu một lớp con phải có override khác, cách ổn định là:

- Dùng profile test chung + inline override trên lớp con.
- Hoặc tách thành một composed annotation được thiết kế rõ.
- Hoặc đặt `@SpringBootTest` trực tiếp với tập properties hoàn chỉnh cho từng lớp.
- Tránh lồng nhiều meta-annotation không rõ mức ưu tiên.

Quan trọng hơn hết: mỗi test nên dễ xác định **tập cấu hình thực sự đã nạp**. Nếu phải truy ngược qua nhiều tầng inheritance chỉ để biết `timeout` là bao nhiêu, cấu trúc test đang quá khó bảo trì.

## 34. Khi có @Nested test classes

JUnit Jupiter hỗ trợ `@Nested` để nhóm test. Với Spring TestContext, những annotation hoặc test configuration có thể được kế thừa từ outer class theo các quy tắc của framework và phiên bản.

Đừng mặc định mỗi nested class tự có một `ApplicationContext` mới với override riêng chỉ vì nằm trong một inner class.

Nếu hai tình huống cần hai context khác hẳn:

```text
Case A: notification.enabled=true
Case B: notification.enabled=false
```

thì hai lớp test độc lập là giải pháp dễ đọc nhất cho người mới. Nếu cần test linh hoạt trong cùng source file, `ApplicationContextRunner` cung cấp mô hình per-scenario phù hợp hơn nhiều bài test `@SpringBootTest` chồng chéo cấu hình.

## 35. Khi test báo "Failed to load ApplicationContext"

Một số nguyên nhân liên quan đến cấu hình override:

### 35.1. Chuỗi property không đúng cấu trúc

```java
@SpringBootTest(properties = "notification.timeout:")
```

Nếu mong muốn `notification.timeout=100ms` mà lại khai value rỗng hoặc thiếu, binder có thể lỗi hoặc nhận kết quả khác dự đoán. Hãy dùng `key=value`.

### 35.2. Giá trị không chuyển kiểu được

```java
@SpringBootTest(properties = "notification.max-attempts=seven")
```

Không chuyển `seven` sang `int`. Sửa dữ liệu test hoặc dùng kiểu phù hợp.

### 35.3. Bean được tạo có điều kiện bị tắt

```java
@SpringBootTest(properties = "audit.enabled=false")
```

Nếu service khác có constructor yêu cầu `AuditSink` nhưng bean này chỉ được tạo khi audit enabled, context có thể lỗi vì thiếu dependency. Cần tổ chức condition/optional dependency hợp lý hoặc cung cấp fake bean thích hợp cho test.

### 35.4. Cấu hình khởi tạo thật kết nối ra ngoài

Test có thể fail vì một client khởi động kết nối database, broker hoặc API. Ghi đè property không tự mock external dependency. Dùng mock/fake server, testcontainer hoặc cấu hình tắt khởi tạo theo kiến trúc đã thiết kế.

### 35.5. Class cấu hình không được tìm thấy

Nếu test nằm ngoài package của app hoặc không có `@SpringBootConfiguration` phù hợp, có thể dùng:

```java
@SpringBootTest(classes = NotificationApplication.class)
```

để chỉ rõ ứng dụng cần dựng.

### 35.6. Test dùng lại bean state đã bị thay đổi

Khi context được cache, singleton giữ state do test trước thay đổi có thể ảnh hưởng test sau. Giữ test độc lập hoặc dọn state; không nhầm đây là lỗi precedence của `@SpringBootTest.properties`.

### 35.7. Sai profile hoặc nguồn khác có ưu tiên cao

Kiểm tra `@ActiveProfiles`, `@TestPropertySource`, `@DynamicPropertySource`, command-line args test và custom context initializers. Đừng mặc định một chuỗi trong annotation là nơi duy nhất có thể khai key.

### 35.8. Test chạy thật sự ở sai module

Với dự án nhiều module, một test có thể không nạp file `application.yml` mà người đọc đang mở. Hãy xác định test runtime classpath, package cấu hình và main configuration đúng module.

## 36. Cách chẩn đoán có hệ thống

Khi test dự đoán `maxAttempts=7` nhưng nhận `2`:

1. Xem annotation trên **đúng lớp test đang được chạy**.
2. Xem string có đúng là `"notification.max-attempts=7"` không.
3. Xem class `@ConfigurationProperties(prefix="notification")` có field `maxAttempts` không.
4. Xem Spring Boot đã đăng ký properties bean chưa.
5. Assert `Environment.getProperty("notification.max-attempts")`.
6. Assert `NotificationProperties.maxAttempts()`.
7. Nếu Environment đúng nhưng bean sai, kiểm tra binding, bean instance và thời điểm khởi tạo.
8. Nếu Environment sai, tìm `@TestPropertySource`, `@DynamicPropertySource` hoặc nguồn test khác khai cùng khóa.
9. Kiểm tra test context caching và những thay đổi global state do các test khác thực hiện.
10. Không sửa `application.yml` trước khi tìm rõ nguồn gốc.

Một test nhỏ như:

```java
@Test
void investigatesOnlyRelevantProperty() {
    assertThat(environment.getProperty(
            "notification.max-attempts")).isEqualTo("7");

    assertThat(properties.maxAttempts()).isEqualTo(7);
}
```

thường hữu ích hơn việc in tất cả biến môi trường hoặc bật log DEBUG toàn bộ application.

## 37. Bảng so sánh các cách cấp giá trị cho test

| Cách | Phạm vi | Điểm mạnh | Hạn chế |
| --- | --- | --- | --- |
| `@SpringBootTest(properties=...)` | Test Boot context của lớp | Ngắn gọn, dễ thấy override | Không phù hợp tập cấu hình quá lớn |
| `@TestPropertySource(properties=...)` | Spring TestContext | Hữu ích cho inline properties theo Spring Test | Có thể chồng chéo với inline Boot |
| `@TestPropertySource(locations=...)` | Spring TestContext | Dùng file fixture tái sử dụng | Cần quản lý resource location |
| `@ActiveProfiles("test")` | Test context profile | Dùng chung bộ cấu hình và bean condition | Không thay trực tiếp từng khóa nếu file thiếu |
| `@DynamicPropertySource` | Test context với value runtime | Phù hợp random port/Testcontainers | Phải quản lý lifecycle resource |
| `ApplicationContextRunner.withPropertyValues(...)` | Context nhỏ tạo theo scenario | Test nhiều tổ hợp, startup failures | Không mặc định kiểm tra toàn bộ app |
| `System.setProperty(...)` | Toàn JVM | Kiểm tra API đọc system property trực tiếp | Dễ rò state, ảnh hưởng test khác |
| Sửa `application.yml` bằng tay | Source file | Không khuyến nghị cho automation | Dễ gây xung đột và tạo side effect |

Khi yêu cầu chỉ là “gắn hai hoặc ba giá trị test khác với file chính”, `@SpringBootTest(properties=...)` rất hợp lý.

## 38. Các lỗi thường gặp và cách tránh

### 38.1. Viết properties dưới dạng YAML

Không khai chuỗi nested YAML bên trong annotation; dùng tên khóa chấm và `=`.

### 38.2. Thêm -- vào trước key

`--demo.mode=fast` phù hợp với command-line argument, không phải tên property muốn cấp qua `properties`.

### 38.3. Nghĩ annotation sửa application.yml

Nó thêm test property source; file không bị chỉnh sửa. Test hoàn tất không để lại “giá trị mới” trong source.

### 38.4. Chỉ assert một string từ Environment

Điều đó không chứng minh service đang dùng đúng bean. Nên test typed properties hoặc hành vi bean tiêu thụ.

### 38.5. Dùng sai key hoặc sai prefix

`notification.max-attmpts` không tự khớp `maxAttempts`. Kiểm tra tên khóa canonical.

### 38.6. Hiểu nhầm default từ @Value

Nếu một nguồn test khai khóa với chuỗi rỗng, nó khác với việc không khai khóa và để fallback xử lý.

### 38.7. Mong List luôn merge từng phần tử

Spring Boot có quy tắc riêng cho collection giữa nguồn cấu hình; hãy test kết quả binding thực tế thay vì suy đoán.

### 38.8. Mong @SpringBootTest khởi động server thật

Mặc định `MOCK` không tự mở port. Dùng `RANDOM_PORT` khi cần HTTP thật; `NONE` khi không cần web.

### 38.9. Viết tất cả test trong một context rồi đổi property giữa chừng

`@ConfigurationProperties` record/bean đã tạo không tự rebind. Tách context hoặc dùng runner cho nhiều scenario.

### 38.10. Dùng @DirtiesContext mọi nơi

Không cần khi chỉ có cấu hình test tường minh; có thể gây lãng phí thời gian khởi tạo.

### 38.11. Thay property bằng System.setProperty sau khi autowire

Quá muộn với nhiều bean và có nguy cơ ảnh hưởng các test khác trong cùng JVM.

### 38.12. Test kết nối môi trường thật

Một override khác endpoint không bảo đảm tắt mọi connection. Dùng fake hoặc test resource rõ ràng, không cấp credential production.

### 38.13. Bỏ qua profile test

Một file `application-test.yml` chỉ có hiệu lực khi profile tương ứng được kích hoạt theo cơ chế Boot. Dùng `@ActiveProfiles` khi cần kiểm tra profile.

### 38.14. Chồng chéo @TestPropertySource và @DynamicPropertySource

Nếu cùng khóa được khai ở hai nơi, cần hiểu precedence; thường nên tránh và chỉ có một nguồn sở hữu.

### 38.15. Dùng @SpringBootTest chỉ để test một phép cộng

Full context không cần thiết cho logic thuần Java. Chọn unit test hoặc lightweight runner.

### 38.16. Giả định test startup failure có thể được assert trong method

`@SpringBootTest` dựng context trước method; nếu lỗi binding lúc startup, method có thể không chạy. Dùng `ApplicationContextRunner` để kiểm tra failure dự kiến.

### 38.17. Cho rằng property sai kiểu sẽ tự dùng default YAML

Một giá trị sai kiểu từ nguồn ưu tiên cao hơn có thể làm context fail, không tự fallback xuống file YAML. Đây là cơ chế giúp fail fast.

### 38.18. Log tất cả giá trị cấu hình khi debug

Không in toàn bộ `Environment` hoặc `@ConfigurationProperties` chứa secret. Dùng giả lập và assertion có mục tiêu.

## 39. Bài tập 1: ghi đè một thuộc tính

Cho YAML:

```yaml
catalog:
  enabled: false
  max-items: 100
```

Và record:

```java
@ConfigurationProperties(prefix = "catalog")
public record CatalogProperties(boolean enabled, int maxItems) {}
```

Hãy viết `@SpringBootTest(properties="catalog.max-items=25")` và assert:

```text
enabled  = false
maxItems = 25
```

Giải thích vì sao `enabled` vẫn là `false` trong khi `maxItems` được override.

## 40. Bài tập 2: nhiều thuộc tính với kiểu khác nhau

Cho:

```yaml
reports:
  title: Daily Report
  batch-size: 50
  flush-interval: 2s
```

Yêu cầu test title `"Test Report"`, batch size `10`, flush interval `500ms`.

Đoạn annotation:

```java
@SpringBootTest(properties = {
    "reports.title=Test Report",
    "reports.batch-size=10",
    "reports.flush-interval=500ms"
})
```

Hãy assert `String`, `int` và `Duration.ofMillis(500)` sau binding. Nếu Java có `Duration flushInterval` mà test khai `five-hundred-ms`, hãy dự đoán kiểu lỗi.

## 41. Bài tập 3: kết hợp @ActiveProfiles với override

Tạo:

```yaml
# application.yml
worker:
  queue: default
  batch-size: 100
```

```yaml
# application-test.yml
worker:
  queue: test
  batch-size: 25
```

Test:

```java
@ActiveProfiles("test")
@SpringBootTest(properties = "worker.batch-size=5")
```

Dự đoán:

```text
worker.queue      = test
worker.batch-size = 5
```

Viết giải thích theo đúng thứ tự: chọn profile, xác định nguồn Config Data, áp dụng inline test override, rồi binder tạo bean.

## 42. Bài tập 4: cờ điều kiện bean

Có:

```java
@Component
@ConditionalOnProperty(
    prefix = "feature",
    name = "enabled",
    havingValue = "true"
)
class FeatureClient {}
```

Viết hai lớp test với properties:

```java
"feature.enabled=true"
"feature.enabled=false"
```

Hãy assert bean có mặt ở trường hợp bật và vắng mặt ở trường hợp tắt. Không dùng `System.setProperty` bên trong một test method để thử đổi trạng thái.

## 43. Bài tập 5: vì sao test không độc lập?

Một test A thay `System.setProperty("worker.batch-size", "5")` nhưng không khôi phục. Test B dùng YAML default và đôi khi nhận 5 thay vì 100.

Hãy nêu:

- Vì sao system properties chia sẻ trên JVM.
- Vì sao thứ tự chạy test có thể làm kết quả thay đổi.
- Cách chuyển test A sang `@SpringBootTest(properties=...)`.
- Cách giữ B không phụ thuộc global state.
- Khi nào cần dọn state hoặc dùng test context độc lập.

## 44. Bài tập 6: test startup failure

Record:

```java
@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
    @Min(1) int batchSize
) {}
```

Muốn xác nhận `worker.batch-size=0` bị từ chối khi binding có validation.

Hỏi:

1. Vì sao viết `@SpringBootTest(properties=...)` rồi chờ một `@Test` method assert startup failure có thể không đúng cách?
2. Làm sao sử dụng `ApplicationContextRunner.withPropertyValues("worker.batch-size=0")`?
3. Vì sao project cần validation provider phù hợp?
4. Điều gì xảy ra nếu thay `0` bằng `abc` khi field là `int`?

## 45. Bài tập 7: khi có Testcontainers

Một database test được Testcontainers cấp JDBC URL khác nhau mỗi lần chạy.

Hãy giải thích vì sao:

```java
@SpringBootTest(properties = {
    "spring.datasource.url=jdbc:postgresql://localhost:5432/test"
})
```

có thể không phù hợp nếu container thực sự được bind cổng ngẫu nhiên, và vì sao `@DynamicPropertySource` hoặc cơ chế service connection dành riêng cho Spring Boot/Testcontainers phù hợp hơn.

Không sử dụng URL/credential của database production trong test chỉ để cho setup “dễ chạy”.

## 46. Bài tập 8: phát hiện annotation sai

Đoạn sau có những vấn đề gì?

```java
@SpringBootTest(properties = {
    "--mail.host=localhost",
    "mail.timeout: 2s",
    "classpath:/integration.properties"
})
```

Gợi ý:

- `--mail.host=localhost` là cú pháp command-line argument, không phải key canonical cho `properties`.
- `mail.timeout: 2s` có thể được xem theo quy tắc Java properties, nhưng chọn `mail.timeout=2s` rõ ràng hơn cho API `@SpringBootTest`.
- `classpath:/integration.properties` không phải cú pháp nạp file bằng `properties`. Dùng `@TestPropertySource(locations=...)` nếu muốn file fixture.

Hãy viết lại annotation ngắn gọn với mục tiêu cụ thể.

## 47. Bài tập 9: kiểm thử typed configuration

Cho:

```java
@ConfigurationProperties(prefix = "image")
public record ImageProperties(
        URI endpoint,
        Duration timeout,
        int maxRetries
) {}
```

Test:

```java
@SpringBootTest(properties = {
    "image.endpoint=https://image.example.invalid/api",
    "image.timeout=750ms",
    "image.max-retries=4"
})
```

Hãy viết ba assertion sử dụng `URI.create(...)`, `Duration.ofMillis(750)` và `int 4`. Tại sao kiểm tra typed object có ý nghĩa hơn việc chỉ xác nhận ba chuỗi tồn tại trong `Environment`?

## 48. Bài tập 10: đánh giá độ cô lập

Một bài integration test có:

```java
@SpringBootTest(properties = {
    "external.service.enabled=false"
})
```

nhưng constructor của một bean vẫn mở socket tới hệ thống ngoài.

Hãy phân tích:

- Vì sao một key không được code sử dụng không thể tắt connection?
- Cách sửa bean configuration để cờ có hiệu lực.
- Khi nào cần fake adapter hoặc mock server.
- Vì sao `webEnvironment=NONE` không đồng nghĩa cấm mọi network request.
- Vai trò của integration test trong việc phát hiện side effect của application startup.

## 49. Checklist khi viết test dùng properties

Một checklist ngắn khi chuẩn bị bài kiểm thử:

1. **Có thực sự cần Spring Boot context không?** Nếu không, dùng unit test.
2. **Đúng test class chưa?** `@SpringBootTest` là annotation cấp lớp.
3. **Đúng app configuration chưa?** Chỉ rõ `classes` nếu cần.
4. **Đúng cú pháp chưa?** Dùng `"key=value"`; không đưa `--` hoặc đường dẫn file vào `properties`.
5. **Đúng tên canonical chưa?** Ví dụ `notification.max-attempts`.
6. **Chỉ ghi đè những khóa cần thiết?** Để các khóa khác lấy từ nguồn bình thường.
7. **Đang dùng profile nào?** `@ActiveProfiles` nếu cần.
8. **Có nguồn test động khác cùng key không?** Giảm chồng chéo.
9. **Bean có được đăng ký và binding không?** Kiểm tra typed properties.
10. **Test có side effect bên ngoài không?** Sử dụng fake/mock server và dữ liệu giả.
11. **Có cần web server thật không?** Dùng `NONE` hoặc mặc định `MOCK` cho test cấu hình.
12. **Có startup failure dự kiến không?** Cân nhắc `ApplicationContextRunner`.
13. **Có làm bẩn singleton context không?** Dọn state; không lạm dụng `@DirtiesContext`.
14. **Có phụ thuộc giá trị của máy CI không?** Override cho test hoặc dùng fixture tường minh.
15. **Có thể chẩn đoán khi test fail không?** Assert cả `Environment` và bean đã bind.
16. **Có vô tình log secret không?** Chỉ dùng dữ liệu thử nghiệm an toàn.

Nếu những điểm này được giải quyết, một test `@SpringBootTest(properties=...)` thường có tính lặp lại cao hơn cách sửa file cấu hình thủ công hoặc thay đổi trạng thái toàn JVM.

## 50. Tổng kết

`@SpringBootTest(properties = ...)` là cách **cấp các thuộc tính test có tính khai báo** trong lúc Spring Boot dựng một `ApplicationContext` cho kiểm thử tích hợp.

Cú pháp cốt lõi:

```java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "notification.enabled=true",
        "notification.max-attempts=7",
        "notification.timeout=250ms"
    }
)
class NotificationConfigurationTest {
    // @Test và các assertion
}
```

Luồng:

```text
application.yml / application-test.yml / env / ...
                         |
                         v
              Test Environment
                         ^
                         |
          @SpringBootTest(properties)
                         |
                         v
               Giá trị có hiệu lực
                         |
               +---------+---------+
               |         |         |
               v         v         v
          Environment  @Value  @ConfigurationProperties
                                     |
                                     v
                                Service bean
```

Những điều phải ghi nhớ:

1. **Không sửa file `application.yml`.** Giá trị override nằm trong test context.
2. **Dùng chuỗi `key=value`**, một hoặc nhiều phần tử của `String[]`.
3. **Test properties thường thắng cấu hình ứng dụng thông thường**, bao gồm YAML, biến môi trường và system properties khi không có nguồn test ưu tiên cao khác.
4. **Ghi đè theo khóa**, không cần khai toàn bộ nhóm properties; với List/Map cần hiểu quy tắc binding riêng.
5. **Giá trị test được Binder chuyển kiểu** sang `Duration`, `URI`, `int`, `boolean` hoặc kiểu khác phù hợp.
6. **Có thể ảnh hưởng bean conditions** như `@ConditionalOnProperty` vì test property được áp dụng trong lúc context khởi tạo.
7. **`@ActiveProfiles`, `@TestPropertySource` và `@DynamicPropertySource` phục vụ những nhu cầu liên quan nhưng khác nhau**; tránh trộn cùng key không chủ đích.
8. **Không dùng `System.setProperty` để thay cấu hình của một context đã dựng**, nhất là trong test chạy song song.
9. **Dùng `ApplicationContextRunner` để kiểm tra startup failure có chủ đích**, thay vì để `@SpringBootTest` thất bại trước khi vào test method.
10. **Chọn test scope phù hợp:** full context để kiểm tra wiring/binding, unit test cho logic Java, test slice cho một lớp chức năng.

Khi dùng đúng, `@SpringBootTest(properties=...)` giúp biến một tình huống cấu hình thành **một bài kiểm thử tái lập được**: người đọc thấy ngay điều kiện đầu vào, Spring Boot dựng bean với những giá trị ấy và assertion xác nhận hành vi mong đợi.

### Tài liệu tham khảo chính thức

- [Spring Boot — SpringBootTest annotation API](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/SpringBootTest.html)
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html)
- [Spring Framework — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
