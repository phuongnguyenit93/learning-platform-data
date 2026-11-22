# Dùng Java record cho cấu hình và đối tượng lồng nhau trong Spring Boot

## 1. Mục tiêu và bối cảnh

Spring Boot cho phép đưa cấu hình từ `application.yaml`, `application.properties`, biến môi trường, đối số dòng lệnh và các nguồn khác vào đối tượng Java thông qua `@ConfigurationProperties`. Nếu cấu hình gồm nhiều cấp như `demo.api.base-url`, `demo.retry.max-attempts` và một danh sách `demo.regions`, việc gắn nhiều `@Value` rải rác trong các service sẽ khó đọc, khó kiểm thử và khó quản lý khi schema thay đổi.

**Java record** là một lựa chọn gọn để mô tả dữ liệu cấu hình có cấu trúc. Record khai báo các thành phần dữ liệu ngay ở phần đầu, có constructor, accessor, `equals`, `hashCode` và `toString` do Java cung cấp. Spring Boot 3.3 có thể dùng **constructor binding** để tạo một record từ các property trong `Environment`; nếu record chứa các record con, Binder tiếp tục tạo cả đồ thị đối tượng lồng nhau.

Ví dụ đích của bài:

```yaml
demo:
  application-name: record-lab
  api:
    base-url: https://api.example.test
    connect-timeout: 2s
  retry:
    max-attempts: 3
    backoff: 250ms
```

Được biểu diễn bằng:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String applicationName,
        Api api,
        Retry retry
) {
    public record Api(URI baseUrl, Duration connectTimeout) {}

    public record Retry(int maxAttempts, Duration backoff) {}
}
```

Mục tiêu là hiểu **vì sao** các phần YAML lồng nhau có thể bind thành `record` lồng nhau, cách kiểm soát giá trị thiếu, kiểu dữ liệu, validation, danh sách/map, thứ tự ưu tiên và vòng đời bean.

Sau khi học, bạn có thể:

1. Mô tả cách `@ConfigurationProperties` sử dụng tên canonical kebab-case để bind vào record component camelCase.
2. Tạo record bất biến ở mức tham chiếu và các record con biểu diễn nhóm thuộc tính.
3. Đăng ký record đúng cách bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
4. Giải thích constructor binding khác JavaBean setter binding và field injection ở đâu.
5. Dùng `@DefaultValue` cho các tham số constructor/record component có fallback phù hợp.
6. Dùng Bean Validation trên root record và nested record, kể cả trường hợp thiếu cả nhóm thuộc tính.
7. Bind `Duration`, `URI`, boolean, danh sách và map, biết rõ ranh giới của tính bất biến.
8. Tự tạo project Java 21 / Spring Boot 3.3 / Gradle để quan sát kết quả.
9. Chạy profile, CLI, biến môi trường và các thử nghiệm cấu hình sai có thể lặp lại.
10. Chọn thiết kế config record phù hợp với ứng dụng thật, tránh lưu secret và object mutable không cần thiết.

**Phạm vi:** Spring Boot 3.3.x và Java 21. Các tên miền, nhãn và giá trị ví dụ không phải dịch vụ production.

## 2. Tại sao chọn record cho configuration properties?

Trước Java record, một class cấu hình theo cách JavaBean thường có nhiều trường, getter, setter và constructor mặc định:

```java
@ConfigurationProperties(prefix = "demo")
public class DemoProperties {
    private String applicationName;

    public String getApplicationName() {
        return applicationName;
    }

    public void setApplicationName(String applicationName) {
        this.applicationName = applicationName;
    }
}
```

Đây là **mutable JavaBean binding**: Spring tạo object và set property sau đó. Cách viết vẫn hợp lệ, nhất là khi cần mutable bean, nhưng với cấu hình chỉ được đọc sau khi ứng dụng khởi động, khả năng sửa setter không phải lúc nào cũng cần.

Record:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(String applicationName) {}
```

Có accessor:

```java
properties.applicationName()
```

chứ không phải accessor bean truyền thống `properties.getApplicationName()`.

### 2.1. Constructor binding thay vì setter binding

Khi binding vào record có một constructor chuẩn, Spring Boot biết tên các component và chuẩn bị giá trị cho constructor. Tư duy là:

```text
application.yaml + environment + CLI
               |
               v
        Spring Environment
               |
               v
  ConfigurationProperties Binder
               |
               v
   xác định demo.application-name
               |
               v
 new DemoProperties("record-lab")
               |
               v
 Spring bean được các service sử dụng
```

Không cần setter để đặt `applicationName`; giá trị được đưa vào **khi tạo instance**.

Điều này tạo ra một hợp đồng rõ: một record được tạo bằng những tham số nào, những tham số nào bắt buộc và những tham số nào có default.

### 2.2. Record không có nghĩa mọi thứ bên trong đều bất biến tuyệt đối

Các record component là trường `private final`. Bạn không thể gán lại `properties.applicationName()` hoặc thay cả `properties.api()` sau khi record đã được tạo.

Tuy nhiên, nếu một component chứa `List`, `Map`, mảng hoặc class mutable, **bản thân nội dung bên trong vẫn có thể thay đổi** nếu không có phòng vệ thêm.

Ví dụ:

```java
public record Options(List<String> regions) {}
```

Bên ngoài vẫn có thể sửa danh sách nếu chính `List` đó mutable. Để giảm rủi ro, có thể sao chép:

```java
public record Options(List<String> regions) {
    public Options {
        regions = regions == null ? List.of() : List.copyOf(regions);
    }
}
```

`List.copyOf` tạo một collection không thể sửa qua API `List` thông thường. Tính bất biến vẫn là **shallow** nếu phần tử bên trong là object mutable. Trong cấu hình, nên ưu tiên phần tử kiểu immutable như `String`, `URI`, `Duration`, enum hoặc record con.

## 3. Tên YAML và Java record component được nối với nhau như thế nào?

Spring Boot khuyên dùng **canonical kebab-case** trong tên property.

| YAML / property key | Record component |
| --- | --- |
| `demo.application-name` | `applicationName` |
| `demo.api.base-url` | `api.baseUrl` |
| `demo.api.connect-timeout` | `api.connectTimeout` |
| `demo.retry.max-attempts` | `retry.maxAttempts` |
| `demo.retry.backoff` | `retry.backoff` |
| `demo.regions` | `regions` |

Với YAML:

```yaml
demo:
  api:
    base-url: https://api.example.test
    connect-timeout: 2s
```

Binder đi theo từng cấp:

```text
demo
  |
  +-- api
        |
        +-- base-url        -> Api.baseUrl
        |
        +-- connect-timeout -> Api.connectTimeout
```

Dấu chấm tạo cấp property, còn gạch nối phân tách từ **trong một cấp**. Hai tên dưới đây không mô tả cùng schema:

```text
demo.api-base-url
demo.api.base-url
```

Khóa thứ nhất không có nhóm `api`; khóa thứ hai có một object con `api`. Muốn bind vào nested record `Api`, hãy dùng cấu trúc thứ hai.

### 3.1. Relaxed binding

Spring Boot Binder có quy tắc **relaxed binding**: cùng một ý nghĩa có thể nhận các biểu diễn tên khác nhau từ những nguồn cấu hình được hỗ trợ. Chẳng hạn, `application-name` trong YAML có thể bind vào `applicationName` của Java.

Với biến môi trường, dạng phổ biến tương ứng là:

```text
demo.application-name   -> DEMO_APPLICATIONNAME
demo.api.base-url       -> DEMO_API_BASEURL
demo.retry.max-attempts -> DEMO_RETRY_MAXATTEMPTS
```

Khi chuyển từ canonical name sang biến môi trường: thay dấu chấm bằng `_`, loại bỏ gạch nối `-`, rồi đổi sang chữ hoa. Không tùy ý đặt thêm `_` giữa hai từ trong cùng một thành phần của tên.

Nên giữ một cách viết canonical trong YAML, tài liệu và lệnh CLI; còn biến môi trường tuân theo quy tắc của nguồn tương ứng.

### 3.2. Record component không cần setter

Với class truyền thống, nhiều framework trông chờ setter. Ở đây Binder dùng constructor của record. Do đó các component có thể là `final` và các nhóm cấu hình bên trong vẫn được xây dựng thành nested record mới.

Đây là một điểm khác với việc gắn `@Value` lên nhiều field instance. `@Value` thường giải quyết một placeholder; `@ConfigurationProperties` giải quyết **cả nhóm thuộc tính**, hỗ trợ conversion, binding collection và validation của cấu trúc.

## 4. Nested record: dùng cây đối tượng thay vì class phẳng

Giả sử ứng dụng cần cấu hình tên, một API client, một chính sách retry và các nhãn vùng.

Một thiết kế phẳng có thể là:

```java
public record FlatSettings(
        String applicationName,
        URI apiBaseUrl,
        Duration apiConnectTimeout,
        int retryMaxAttempts,
        Duration retryBackoff
) {}
```

Nó chạy được, nhưng khi có nhiều nhóm thuộc tính hoặc nhiều backend sẽ trở nên dài. Thay bằng record lồng nhau:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String applicationName,
        Api api,
        Retry retry
) {
    public record Api(
            URI baseUrl,
            Duration connectTimeout
    ) {}

    public record Retry(
            int maxAttempts,
            Duration backoff
    ) {}
}
```

Cách dùng:

```java
URI apiUrl = demoProperties.api().baseUrl();
int attempts = demoProperties.retry().maxAttempts();
```

`Api` và `Retry` là các **nested records**. Trong Java, member record khai báo bên trong một class/record là một kiểu lồng nhau và về mặt ngữ nghĩa không giữ tham chiếu ẩn đến instance bên ngoài. Không cần viết `static` trước từ khóa `record`.

Điều đó **không mâu thuẫn** với việc không nên tiêm cấu hình vào `static field`. Nested record là **kiểu dữ liệu**, còn mỗi đối tượng `new Api(...)` hay `new Retry(...)` vẫn là instance có component riêng. Spring Boot không tiêm vào một biến global static ở đây.

### 4.1. Có cần dùng một record cho mọi nhóm?

Không bắt buộc. Bạn có thể tách:

```java
public record ApiSettings(URI baseUrl, Duration connectTimeout) {}
```

thành một type riêng và dùng nó làm component của record gốc. Việc binding theo constructor vẫn thực hiện được khi schema phù hợp.

Tuy nhiên, nested record trong record gốc giúp người đọc thấy rõ nhóm nào **thuộc riêng** cấu hình đó. Nếu một kiểu được dùng chung nhiều nơi hoặc có hàng loạt quy tắc phức tạp, tách class/record riêng thường dễ bảo trì hơn.

## 5. Đăng ký record với Spring Boot đúng cách

`@ConfigurationProperties(prefix = "demo")` định nghĩa prefix binding, nhưng bản thân annotation đó chưa nhất thiết đăng ký một bean. Với cấu trúc Spring Boot, có hai cách thông dụng:

### 5.1. Quét bằng `@ConfigurationPropertiesScan`

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class RecordBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RecordBindingApplication.class, args);
    }
}
```

Spring Boot tìm các type có `@ConfigurationProperties` trong phạm vi scan, đăng ký bean và bind chúng khi context được tạo. Đây là lựa chọn thuận tiện khi project có nhiều lớp configuration properties.

### 5.2. Đăng ký tường minh bằng `@EnableConfigurationProperties`

```java
@SpringBootApplication
@EnableConfigurationProperties(DemoProperties.class)
public class RecordBindingApplication {
    public static void main(String[] args) {
        SpringApplication.run(RecordBindingApplication.class, args);
    }
}
```

Cách này hợp khi muốn biết rõ danh sách các type cấu hình được đăng ký. **Chọn một cách phù hợp cho bài lab**; không cần dùng cả hai chỉ để tạo cùng một bean.

### 5.3. Tránh `@Component` trên record cấu hình constructor-bound

Bạn có thể gặp đoạn mã:

```java
@Component
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(String applicationName) {}
```

Đây **không phải cách nên dùng** cho constructor binding. Nếu bean được tạo bằng một cơ chế Spring bean thông thường như `@Component`, các tham số constructor có thể được hiểu như dependency cần autowire thay vì là các thuộc tính cần bind. Spring Boot yêu cầu constructor binding được đăng ký bằng cơ chế hỗ trợ configuration properties như scan hoặc `@EnableConfigurationProperties`, không phải tạo bean thông qua `@Component` hay một `@Bean` factory method thông thường rồi mong Binder tự sử dụng constructor theo cách đó.

**Dùng `@ConfigurationProperties` + `@ConfigurationPropertiesScan`** cho record của bài này.

### 5.4. Có cần `@ConstructorBinding` trên record?

Trong Spring Boot 3.3, nếu một type cấu hình có một constructor tham số phù hợp, constructor binding được suy ra tự động. Một record thông thường có canonical constructor nên **không cần** thêm `@ConstructorBinding` để bật tính năng.

Annotation `@ConstructorBinding` trong Spring Boot 3 được dùng ở **constructor** khi cần chỉ rõ constructor binding trong trường hợp có nhiều constructor hoặc có sự mơ hồ. Không dựa vào các ví dụ cũ của Spring Boot 2.x dùng annotation này trên class rồi sao chép nguyên si vào project Boot 3.3.

Nếu dùng class thường thay vì record, parameter names phải có mặt để Binder biết tên từng tham số. Java record đã mô tả component names theo cấu trúc ngôn ngữ. Với class constructor thường, cấu hình build để giữ tên tham số (`-parameters`) có thể cần được xem xét theo phiên bản/framework.

## 6. Ứng dụng mẫu: Record Configuration Observer

Ta tạo một ứng dụng console gồm:

- Một root record `DemoProperties`.
- Hai nested records `Api` và `Retry`.
- Một danh sách `regions`.
- Một map `labels`.
- Fallback bằng `@DefaultValue`.
- Validation qua Jakarta Bean Validation.
- Một `ApplicationRunner` in những giá trị không nhạy cảm sau khi binder hoàn tất.

Cấu trúc:

```text
record-binding-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/recordbinding/
    │   │   ├── RecordBindingApplication.java
    │   │   └── DemoProperties.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-dev.yaml
    └── test/
        └── java/dev/example/recordbinding/
            └── DemoPropertiesTest.java
```

Bạn có thể khởi tạo project qua Spring Initializr, chọn Java 21, Gradle và phiên bản Spring Boot 3.3.x, rồi thêm các file bên dưới. Dùng Gradle Wrapper do project sinh ra.

### 6.1. `settings.gradle`

```groovy
rootProject.name = 'record-binding-lab'
```

### 6.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` mang vào cơ chế Bean Validation để những annotation như `@NotBlank`, `@NotNull`, `@Min`, `@Max`, `@NotEmpty` được kiểm tra khi bind config.

Nếu dự án hiện có dùng version catalog hoặc convention plugin, giữ quy ước quản lý version của repository đó. Đoạn trên minh họa một project độc lập, không ép mọi repository phải dùng cùng file build.

### 6.3. `application.yaml`

```yaml
spring:
  main:
    web-application-type: none

demo:
  application-name: "record-lab"
  api:
    base-url: "https://api.example.test"
    connect-timeout: 1200ms
  retry:
    backoff: 400ms
  regions:
    - ap-southeast-1
    - eu-west-1
  labels:
    team: education
    tier: sandbox
```

Lưu ý `demo.retry.max-attempts` **không có trong file này**: ta sẽ cấp default từ record.

`api.base-url` được chuyển thành `URI`, `connect-timeout` và `backoff` thành `Duration`, `regions` thành `List<String>` và `labels` thành `Map<String,String>`.

Những tên miền `example.test` trong lab là tên minh họa; ứng dụng không gửi request HTTP tới chúng.

### 6.4. Root record và nested records

`src/main/java/dev/example/recordbinding/DemoProperties.java`:

```java
package dev.example.recordbinding;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @NotBlank String applicationName,
        @Valid @NotNull Api api,
        @Valid @NotNull Retry retry,
        @NotEmpty List<String> regions,
        Map<String, String> labels
) {
    // Compact constructor: giữ một bản sao bất biến của collection.
    public DemoProperties {
        regions = regions == null ? List.of() : List.copyOf(regions);
        labels = labels == null ? Map.of() : Map.copyOf(labels);
    }

    public record Api(
            @NotNull URI baseUrl,
            @DefaultValue("2s") @NotNull Duration connectTimeout
    ) {}

    public record Retry(
            @DefaultValue("3") @Min(1) @Max(10) int maxAttempts,
            @DefaultValue("250ms") @NotNull Duration backoff
    ) {}
}
```

Giải thích từng phần:

1. `@ConfigurationProperties(prefix = "demo")` chỉ ra toàn bộ record được cấp giá trị từ nhóm khóa `demo.*`.
2. `@Validated` yêu cầu Spring Boot thực hiện validation với validator được cấu hình trong context.
3. `@NotBlank applicationName` yêu cầu tên có nội dung.
4. `@Valid @NotNull Api api` vừa yêu cầu nhóm `api` tồn tại vừa cho phép validation lan vào nested record.
5. `@Valid @NotNull Retry retry` tương tự cho nhóm `retry`.
6. `@DefaultValue("2s")` cho `connectTimeout` có tác dụng khi thuộc tính con này không được cung cấp trong quá trình binding một `Api`.
7. `@DefaultValue("3")` cho `maxAttempts` cấp giá trị 3 khi property không xuất hiện.
8. `@Min(1)` và `@Max(10)` giới hạn số lần thử hợp lệ từ 1 đến 10.
9. `List.copyOf` và `Map.copyOf` tránh lưu trực tiếp collection mutable vào record.
10. Nếu cả nhóm `api`/`retry` không được bind và không có default ở **cấp nested component**, thành phần root tương ứng có thể là `null`, rồi `@NotNull` sẽ báo cấu hình thiếu.

Trong compact constructor, Java gán lại những biến tham số `regions` và `labels` trước khi constructor kết thúc. Các trường record sẽ nhận bản sao đó. Đây là cách phòng vệ đơn giản phù hợp với collection chứa `String`.

Một lưu ý: `Map.copyOf` và `List.copyOf` không chấp nhận phần tử/giá trị `null`; với schema cấu hình cần giữ giá trị `null`, bạn phải xây quy tắc normalize khác thay vì sao chép như ví dụ.

### 6.5. Main class và ApplicationRunner

`src/main/java/dev/example/recordbinding/RecordBindingApplication.java`:

```java
package dev.example.recordbinding;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
@ConfigurationPropertiesScan
public class RecordBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(RecordBindingApplication.class, args);
    }

    @Bean
    ApplicationRunner report(DemoProperties properties,
                             Environment environment) {
        return args -> {
            System.out.println("=== RECORD CONFIGURATION ===");
            System.out.println("activeProfiles = "
                    + String.join(",", environment.getActiveProfiles()));
            System.out.println("applicationName = "
                    + properties.applicationName());
            System.out.println("api.baseUrl = "
                    + properties.api().baseUrl());
            System.out.println("api.connectTimeout = "
                    + properties.api().connectTimeout());
            System.out.println("retry.maxAttempts = "
                    + properties.retry().maxAttempts());
            System.out.println("retry.backoff = "
                    + properties.retry().backoff());
            System.out.println("regions = " + properties.regions());
            System.out.println("labels = " + properties.labels());
        };
    }
}
```

Ứng dụng chạy console; vì cấu hình `spring.main.web-application-type=none`, nó không mở web server. Các giá trị đã được bind vào record trước khi runner được gọi. `ApplicationRunner` chỉ in các thuộc tính giả lập, không truy xuất secret.

Sơ đồ runtime:

```text
                Environment
                     |
           prefix = "demo"
                     |
                     v
         DemoProperties record
         /        |         \
      Api       Retry      collections
     /   \      /    \       /     \
   URI Duration int Duration List    Map
                     |
                     v
         @Validated + @Valid
                     |
                     v
       Spring bean được inject
                     |
                     v
           ApplicationRunner
```

## 7. Chạy lần 1: cấu hình nền và giá trị mặc định

Từ gốc project:

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Những dòng chính dự kiến:

```text
=== RECORD CONFIGURATION ===
activeProfiles =
applicationName = record-lab
api.baseUrl = https://api.example.test
api.connectTimeout = PT1.2S
retry.maxAttempts = 3
retry.backoff = PT0.4S
regions = [ap-southeast-1, eu-west-1]
labels = {team=education, tier=sandbox}
```

`PT1.2S` và `PT0.4S` là cách `Duration.toString()` hiển thị 1,2 giây và 0,4 giây. Thứ tự key khi in `Map` không phải điều cần kiểm thử; hãy xem tên key và giá trị tương ứng.

**Điểm quan sát quan trọng nhất:** `retry.maxAttempts` có giá trị `3` dù YAML không chứa `max-attempts`, nhờ `@DefaultValue("3")` ở record component.

### 7.1. Nếu bỏ cấu hình `api.connect-timeout`

Sửa `application.yaml`:

```yaml
demo:
  application-name: "record-lab"
  api:
    base-url: "https://api.example.test"
  retry:
    backoff: 400ms
  regions:
    - ap-southeast-1
  labels:
    team: education
```

Chạy lại. `api.connectTimeout()` dự kiến là `PT2S` nhờ:

```java
@DefaultValue("2s") Duration connectTimeout
```

Đừng hiểu default trong record là một file cấu hình mới. Đó là giá trị do Binder sử dụng khi không có giá trị cụ thể cho tham số đang được bind.

### 7.2. Nếu bỏ toàn bộ `api`

Nếu YAML không có cả nhóm `demo.api`, giá trị của root component `api` có thể là `null`. Với `@NotNull` ở root và validation đã bật, ứng dụng sẽ từ chối khởi động thay vì để service gọi `properties.api().baseUrl()` rồi nhận `NullPointerException`.

Default cho **component con** `connectTimeout` không tự quyết định rằng nhóm cha `Api` phải được tạo khi toàn bộ subtree thiếu. Muốn một nhóm nested là tùy chọn nhưng vẫn có instance với default, xem mục `@DefaultValue` cho nested object ở phần sau.

## 8. Chạy lần 2: file theo profile

Tạo `src/main/resources/application-dev.yaml`:

```yaml
demo:
  application-name: "record-lab-dev"
  api:
    connect-timeout: 500ms
  retry:
    max-attempts: 5
  regions:
    - local
    - integration
  labels:
    tier: development
```

Chạy:

macOS/Linux:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Các giá trị dự kiến thay đổi:

```text
activeProfiles = dev
applicationName = record-lab-dev
api.baseUrl = https://api.example.test
api.connectTimeout = PT0.5S
retry.maxAttempts = 5
retry.backoff = PT0.4S
regions = [local, integration]
```

Vì file dev chỉ ghi đè một vài khóa, `api.base-url` và `retry.backoff` vẫn đến từ cấu hình nền. Danh sách `regions` trong ví dụ được thay bằng danh sách dev; không nên giả định danh sách sẽ được nối thêm phần tử giữa các nguồn cấu hình có độ ưu tiên khác nhau.

Với map, việc merge/override có thể diễn ra theo từng key theo quy tắc Binder. `labels.tier` từ dev có thể thay giá trị của key đó, còn `labels.team` từ file nền vẫn được giữ. Nếu cần thay **toàn bộ** map bằng một nguồn, phải thiết kế cấu hình và cách binding theo đúng yêu cầu, không suy luận từ hành vi thay thế list.

## 9. Chạy lần 3: CLI và biến môi trường

Cùng một record nhận giá trị hiệu lực từ nhiều nguồn, không phụ thuộc vào việc giá trị đến từ YAML hay CLI.

### 9.1. Đối số dòng lệnh

macOS/Linux:

```bash
./gradlew bootRun --args='--demo.application-name=from-cli --demo.retry.max-attempts=7'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--demo.application-name=from-cli --demo.retry.max-attempts=7"
```

Kỳ vọng:

```text
applicationName = from-cli
retry.maxAttempts = 7
```

Các thuộc tính khác tiếp tục được bind theo giá trị hiệu lực từ những nguồn còn lại. Không cần sửa record khi chuyển từ YAML sang CLI.

### 9.2. Biến môi trường

Trong Bash:

```bash
DEMO_APPLICATIONNAME=from-env \
DEMO_RETRY_MAXATTEMPTS=6 \
./gradlew bootRun
```

Trong PowerShell:

```powershell
$env:DEMO_APPLICATIONNAME = "from-env"
$env:DEMO_RETRY_MAXATTEMPTS = "6"
.\gradlew.bat bootRun
Remove-Item Env:DEMO_APPLICATIONNAME
Remove-Item Env:DEMO_RETRY_MAXATTEMPTS
```

Kỳ vọng tên ứng dụng `from-env` và số lần thử `6`, miễn là không có nguồn ưu tiên cao hơn cùng khai báo các khóa đó.

Quy tắc canonical tương ứng:

```text
demo.application-name  <-> DEMO_APPLICATIONNAME
demo.retry.max-attempts <-> DEMO_RETRY_MAXATTEMPTS
demo.api.base-url       <-> DEMO_API_BASEURL
```

Dùng `DEMO_RETRY_MAX_ATTEMPTS` thay cho `DEMO_RETRY_MAXATTEMPTS` có thể tạo ý nghĩa phân cấp khác. Tránh tự suy ra tên biến môi trường từ camelCase trong Java nếu có thể bắt đầu từ tên canonical trong tài liệu.

### 9.3. Chạy JAR độc lập

Build:

```bash
./gradlew bootJar
java -jar build/libs/record-binding-lab-0.0.1-SNAPSHOT.jar \
  --demo.retry.max-attempts=4
```

PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build\libs\record-binding-lab-0.0.1-SNAPSHOT.jar --demo.retry.max-attempts=4
```

Sau khi đóng gói, record và cấu hình nền được đem theo trong JAR; giá trị có thể được ghi đè bằng nguồn runtime phù hợp. Nếu project đổi tên hoặc phiên bản, thay đường dẫn bằng tên JAR thực tế.

## 10. Validation trên record và nested record

Một record có kiểu giúp giảm lỗi gọi setter tùy ý, nhưng không tự đảm bảo mọi giá trị **hợp lệ về nghiệp vụ**. Ví dụ `maxAttempts=-5` vẫn là một `int` và có thể được chuyển kiểu thành công; lỗi của nó nằm ở quy tắc nghiệp vụ.

Bean Validation cung cấp các constraint:

```java
@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @NotBlank String applicationName,
        @Valid @NotNull Api api,
        @Valid @NotNull Retry retry,
        @NotEmpty List<String> regions
) {
    public record Api(
            @NotNull URI baseUrl,
            @NotNull Duration connectTimeout
    ) {}

    public record Retry(
            @Min(1) @Max(10) int maxAttempts,
            @NotNull Duration backoff
    ) {}
}
```

- `@Validated` trên root type kích hoạt cơ chế validation cho configuration properties.
- `@Valid` trên nested component yêu cầu validator đi sâu vào object con.
- `@NotNull` trên `api` hoặc `retry` bảo đảm không mất toàn bộ nhóm.
- `@NotBlank` áp dụng với `String`.
- `@NotEmpty` phù hợp với danh sách bắt buộc có ít nhất một phần tử.
- `@Min`, `@Max` giới hạn giá trị số.

Trong project mẫu, ràng buộc trên record đã được dùng cùng `spring-boot-starter-validation`.

### 10.1. Thử một giá trị sai

Chạy:

```bash
./gradlew bootRun --args='--demo.retry.max-attempts=0'
```

Giá trị `0` có thể được chuyển thành `int`, nhưng không qua được `@Min(1)`. Khi binding và validation được thực hiện, Spring Boot sẽ báo lỗi cấu hình và context có thể không khởi động. Đây là hành vi mong muốn cho một cấu hình bắt buộc.

Tương tự, thử:

```bash
./gradlew bootRun --args='--demo.application-name='
```

Chuỗi rỗng không thỏa `@NotBlank`.

### 10.2. Thử lỗi chuyển kiểu

```bash
./gradlew bootRun --args='--demo.api.connect-timeout=not-a-duration'
```

Ở đây binder không thể chuyển chuỗi thành `Duration`, nên sẽ phát sinh lỗi binding trước khi ứng dụng chạy bình thường. Cần phân biệt **lỗi chuyển kiểu** với **lỗi validation**: `not-a-duration` không có kiểu hợp lệ, còn `0` ở `maxAttempts` có kiểu hợp lệ nhưng vi phạm ràng buộc.

### 10.3. Khi một nested object vắng mặt hoàn toàn

Hai trường hợp khác nhau:

```yaml
demo:
  api:
    base-url: https://api.example.test
```

và:

```yaml
demo:
  # không có nhóm api
  retry:
    max-attempts: 3
```

Trường hợp đầu có thể tạo một `Api` với `connectTimeout` lấy từ `@DefaultValue("2s")`. Trường hợp sau **không nhất thiết tạo Api**. Với `@NotNull` trên root `api`, ứng dụng được yêu cầu phát hiện thiếu nhóm bắt buộc.

Đây là lý do thiết kế validation cần xét cả **toàn bộ nhóm nested** chứ không chỉ các thuộc tính bên trong.

## 11. `@DefaultValue` và constructor binding

Trong JavaBean binding, một class mutable đôi khi đặt default bằng cách khởi tạo field:

```java
private int maxAttempts = 3;
```

Với record constructor binding, **không có setter** để ghi đè một field instance đã có default theo cùng cách đó. Spring Boot có annotation `@DefaultValue` cho các tham số constructor/record components.

Ví dụ:

```java
public record Retry(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("250ms") Duration backoff
) {}
```

Khi key không được cung cấp và Binder tạo một `Retry`, `maxAttempts` có thể nhận `3`, `backoff` nhận `Duration` 250 mili giây. Binder thực hiện conversion dựa trên kiểu đích.

### 11.1. Default cho cả một nested object

Nếu một nhóm cấu hình **có thể vắng mặt**, nhưng bạn vẫn muốn tạo nested record từ các default bên trong, có thể khai báo `@DefaultValue` không có tham số ở **component của object cha**:

```java
@ConfigurationProperties(prefix = "feature")
public record FeatureProperties(
        @DefaultValue Security security
) {
    public record Security(
            @DefaultValue("false") boolean enabled,
            @DefaultValue("public") String mode
    ) {}
}
```

Khi thiếu toàn bộ nhóm `feature.security`, `@DefaultValue` không có nội dung trên component `security` cho phép Binder tạo object nested bằng những default phù hợp. Nếu component kiểu nested phải có dữ liệu bắt buộc không có default, cần thiết kế validation thay vì khởi tạo một object thiếu thông tin rồi dùng nó.

Phân biệt ba tình huống:

| Tình huống | Thiết kế |
| --- | --- |
| Một tham số primitive/string có fallback rõ | `@DefaultValue("3")` |
| Một nested object có thể vắng mặt nhưng vẫn cần instance default | `@DefaultValue` trên nested component |
| Một nhóm cấu hình bắt buộc phải khai báo | `@NotNull` và `@Valid`, không che thiếu bằng default |

Không biến tất cả cấu hình bắt buộc thành optional chỉ để ứng dụng luôn khởi động.

### 11.2. Default ở record và fallback của placeholder

Hai cách:

```java
@DefaultValue("3") int maxAttempts
```

và:

```java
@Value("${demo.retry.max-attempts:3}") int maxAttempts
```

không hoàn toàn đồng nhất về nơi áp dụng.

`@DefaultValue` thuộc hợp đồng **binding** của constructor parameter; placeholder fallback thuộc điểm tham chiếu `${...}`. Đối với một nhóm property được dùng ở nhiều service, nên tập trung default ở type cấu hình hoặc file nền để tránh mỗi service tự đưa ra fallback khác nhau.

## 12. Nested records và collections

Cấu hình thực tế thường có danh sách hoặc map ngoài các property đơn.

### 12.1. Danh sách đơn giản

YAML:

```yaml
demo:
  regions:
    - ap-southeast-1
    - eu-west-1
```

Java:

```java
public record DemoProperties(List<String> regions) {}
```

Cả `List<String>` là một component. Spring Boot có thể bind dữ liệu danh sách từ YAML hoặc từ các index notation trong `.properties`:

```properties
demo.regions[0]=ap-southeast-1
demo.regions[1]=eu-west-1
```

Khi cấu hình danh sách xuất hiện ở nhiều property sources, cần hiểu cơ chế ưu tiên và thay thế danh sách của Spring Boot. Đừng mặc định nó sẽ gộp phần tử từ mọi file thành một danh sách dài hơn.

### 12.2. Map đơn giản

YAML:

```yaml
demo:
  labels:
    team: education
    tier: sandbox
```

Record component:

```java
Map<String, String> labels
```

Truy cập:

```java
String team = demoProperties.labels().get("team");
```

Map phù hợp khi tên key linh hoạt hơn một schema record cứng, chẳng hạn tên vùng hoặc nhãn do người vận hành quy định. Nhưng nếu các key có ý nghĩa cố định như `baseUrl` và `connectTimeout`, nested record thường rõ hơn vì nó mô tả schema và kiểu của từng giá trị.

### 12.3. Map có giá trị là record con

Một ví dụ nâng cao:

```yaml
integrations:
  clients:
    billing:
      base-url: https://billing.example.test
      connect-timeout: 1s
    inventory:
      base-url: https://inventory.example.test
      connect-timeout: 2s
```

Java:

```java
@ConfigurationProperties(prefix = "integrations")
public record IntegrationsProperties(
        Map<String, Client> clients
) {
    public record Client(
            URI baseUrl,
            Duration connectTimeout
    ) {}
}
```

Binder có thể tạo map với key `billing` và `inventory`, mỗi value là một `Client` record. Mẫu này phù hợp khi số lượng tên client phụ thuộc triển khai nhưng mỗi client có cùng cấu trúc.

Đối với map key chứa dấu chấm, dấu slash hoặc ký tự đặc biệt, cần chú ý cú pháp map binding của Spring Boot và ký hiệu bracket để bảo toàn tên key. Với bài lab cơ bản, dùng key chữ thường và chữ cái đơn giản để tập trung vào record binding.

### 12.4. Tính bất biến của collection nested

Ngay cả khi map chính không sửa được, value bên trong có thể là class mutable nếu bạn dùng class thông thường. Đối với một graph cấu hình mong muốn ổn định sau startup, nên ưu tiên record con và các type value bất biến.

Nếu bạn cần bổ sung hoặc xóa client ở runtime, đó thường không còn là bài toán “immutable config snapshot” đơn thuần; hãy thiết kế một service quản lý trạng thái riêng, với quy tắc concurrency và refresh, thay vì cố sửa record cấu hình.

## 13. Record compact constructor: dùng đến đâu là hợp lý?

Compact constructor hữu ích cho những invariant không thể bỏ qua:

```java
public record Retry(int maxAttempts, Duration backoff) {
    public Retry {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be positive");
        }
        if (backoff == null || backoff.isNegative()) {
            throw new IllegalArgumentException(
                    "backoff must not be negative");
        }
    }
}
```

Cách này có ưu điểm là một instance `Retry` không thể được tạo với các giá trị trái điều kiện constructor. Tuy nhiên, khi dùng cho configuration properties, exception thủ công thường cung cấp thông điệp ít cấu trúc hơn so với Bean Validation.

**Đề xuất tổ chức trách nhiệm:**

- Conversion kiểu cơ bản: để Spring Boot Binder thực hiện.
- Default constructor parameters: dùng `@DefaultValue` hoặc file cấu hình nền.
- Kiểm tra constraint khai báo được: dùng Jakarta Validation.
- Invariant phức tạp không biểu đạt được bằng annotation: cân nhắc compact constructor, custom validator hoặc service kiểm tra cấu hình lúc startup.
- Copy collection: compact constructor thích hợp nếu muốn bảo vệ shallow immutability.

Không nhét các hoạt động I/O, truy cập network hoặc lấy Spring bean vào constructor của record cấu hình. Record nên là dữ liệu; service mới là nơi thực hiện side effect.

## 14. `@ConfigurationPropertiesScan` và package layout

Mã chính đặt ở:

```text
dev.example.recordbinding.RecordBindingApplication
```

và record cấu hình đặt ở:

```text
dev.example.recordbinding.DemoProperties
```

nên `@ConfigurationPropertiesScan` trên main class có thể phát hiện `DemoProperties` theo phạm vi package phù hợp.

Nếu bạn chuyển record sang một package nằm **ngoài vùng scan**, bean có thể không được đăng ký. Khi đó, chọn một cách hợp lệ:

```java
@ConfigurationPropertiesScan(
        basePackages = "dev.example.configuration"
)
```

hoặc:

```java
@EnableConfigurationProperties(DemoProperties.class)
```

Không sửa bằng cách thêm `@Component` bừa vào record constructor-bound.

Khi record không có bean trong context, lỗi thường xảy ra tại injection point của service, ví dụ:

```text
No qualifying bean of type DemoProperties
```

Đây là vấn đề **đăng ký bean**, khác với lỗi **binding** hoặc **validation**. Phân loại lỗi đúng giúp xử lý nhanh.

## 15. Đọc record trong service

Một service tốt không cần biết cấu hình được ghi trong YAML, profile, CLI hay Kubernetes environment:

```java
package dev.example.recordbinding;

import java.net.URI;
import java.time.Duration;

import org.springframework.stereotype.Service;

@Service
public class ApiPolicyService {

    private final DemoProperties properties;

    public ApiPolicyService(DemoProperties properties) {
        this.properties = properties;
    }

    public URI baseUrl() {
        return properties.api().baseUrl();
    }

    public Duration timeout() {
        return properties.api().connectTimeout();
    }

    public int maxAttempts() {
        return properties.retry().maxAttempts();
    }
}
```

Service chỉ biết một **typed contract**: `DemoProperties`. Điều này giúp hạn chế nhiều chuỗi `${...}` rải rác, giảm việc mỗi service tự suy đoán default và làm cho unit test dễ kiểm soát.

Trong unit test thuần Java, có thể tạo cấu hình một cách tường minh:

```java
DemoProperties props = new DemoProperties(
        "unit-test",
        new DemoProperties.Api(
                URI.create("https://api.example.test"),
                Duration.ofSeconds(1)),
        new DemoProperties.Retry(
                2, Duration.ofMillis(100)),
        List.of("local"),
        Map.of("team", "tests"));

ApiPolicyService service = new ApiPolicyService(props);
```

Test này **không cần Spring context**, nên nhanh và độc lập với cơ chế Config Data. Nó kiểm tra logic service với một đối tượng cấu hình cụ thể, không kiểm tra Binder.

Ngược lại, integration test với `@SpringBootTest` phù hợp để kiểm tra việc Spring Boot đọc cấu hình và tạo record qua constructor binding.

## 16. Kiểm thử binding bằng Spring Boot Test

`src/test/java/dev/example/recordbinding/DemoPropertiesTest.java`:

```java
package dev.example.recordbinding;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.application-name=from-test",
        "demo.api.base-url=https://test.example.test",
        "demo.retry.max-attempts=8"
})
class DemoPropertiesTest {

    @Autowired
    DemoProperties properties;

    @Test
    void bindsRootAndNestedRecords() {
        assertEquals("from-test", properties.applicationName());
        assertEquals(URI.create("https://test.example.test"),
                properties.api().baseUrl());
        assertEquals(8, properties.retry().maxAttempts());
        assertEquals(Duration.ofMillis(400),
                properties.retry().backoff());
        assertTrue(properties.regions().contains("ap-southeast-1"));
    }
}
```

Chạy:

macOS/Linux:

```bash
./gradlew test
```

PowerShell:

```powershell
.\gradlew.bat test
```

Trong ví dụ này, file `application.yaml` cung cấp những khóa không ghi đè, như `demo.retry.backoff` và `demo.regions`; test properties ghi đè ba khóa được liệt kê. Spring Boot vẫn phải tạo cả root record và nested records, convert `URI`/`Duration` rồi chạy validation.

### 16.1. Một test không thay thế mọi trường hợp lỗi

Nên bổ sung những trường hợp có ý nghĩa với ứng dụng:

- Một nhóm bắt buộc `demo.api` bị thiếu.
- `demo.retry.max-attempts=0` vi phạm `@Min(1)`.
- Duration không đúng định dạng.
- Một danh sách bắt buộc rỗng.
- Cấu hình theo profile `dev` tạo record khác cấu hình nền.
- Tên biến môi trường và CLI ánh xạ tới tên canonical mong muốn.
- Các dữ liệu nhạy cảm không bị in ra log, `toString` hoặc endpoint.

Test lỗi khởi động cần cách tạo context phù hợp, ví dụ `ApplicationContextRunner`, để kỳ vọng failure mà không làm toàn bộ test suite ngừng theo lỗi context. Với khóa đơn giản, `@SpringBootTest` dùng cho đường thành công là đủ để làm quen.

## 17. Phân biệt bốn loại lỗi thường gặp

| Triệu chứng | Nguyên nhân điển hình | Cách bắt đầu xử lý |
| --- | --- | --- |
| Không inject được `DemoProperties` | Bean không được đăng ký / ngoài vùng scan | Xem `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties` |
| Lỗi bind `base-url` sang `URI` hoặc `connect-timeout` sang `Duration` | Giá trị không thể convert theo kiểu đích | Kiểm tra giá trị gốc và cú pháp |
| Lỗi `@NotBlank`, `@NotNull`, `@Min` | Giá trị chuyển kiểu được nhưng sai constraint, hoặc nhóm nested thiếu | Kiểm tra validation ở root và nested |
| Kết quả khác file YAML vừa sửa | Profile, environment, CLI hoặc location khác đang ghi đè | Kiểm tra `Environment` và thứ tự nguồn |

Cũng cần phân biệt **lỗi tên property** với lỗi validation. Nếu YAML dùng `demo.api-base-url` thay vì `demo.api.base-url`, Binder không tự đưa khóa phẳng đó vào nested record `Api`. `api.baseUrl` có thể thiếu dù bạn nhìn thấy chuỗi URL trong file.

### 17.1. Vì sao một nested record bị `null`?

Các nguyên nhân cần xét:

1. Chưa khai báo bất kỳ property nào dưới prefix nested đó.
2. Viết sai tên nhóm, ví dụ `demo.client` nhưng record khai báo `api`.
3. File được đặt ở location không được nạp.
4. Profile chứa file cấu hình chưa được bật.
5. `spring.config.location` đã thay đổi tập location mặc định.
6. Một nguồn ưu tiên cao hơn làm thay đổi hoặc xóa ý nghĩa cấu hình dự kiến.
7. Chưa thêm `@DefaultValue` trên nested component nếu muốn object mặc định khi không có toàn bộ subtree.

Với nhóm bắt buộc, `@NotNull` cùng `@Valid` giúp fail fast thay vì đến khi service gọi method nested mới lỗi.

### 17.2. Vì sao `@DefaultValue` không áp dụng như kỳ vọng?

Kiểm tra giá trị thực sự có **vắng mặt** không. `@DefaultValue` dành cho trường hợp không có giá trị cần bind; nó không phải cơ chế thay thế mọi chuỗi rỗng hoặc dữ liệu sai định dạng.

Ví dụ, `demo.retry.max-attempts=garbage` không nên được âm thầm chuyển về 3. Binder không thể convert dữ liệu hiện có thành `int`, nên lỗi conversion là điều phù hợp.

Nếu một nested subtree hoàn toàn thiếu, default trên một component **bên trong nested record** chưa chắc đủ để tạo cả nested record. Hãy nhìn vào component kiểu nested tại record cha.

## 18. Record và profile: cùng schema, nhiều giá trị

Một điểm mạnh của typed config record là **schema không phải thay đổi** theo môi trường.

File nền:

```yaml
demo:
  api:
    base-url: https://api.example.test
```

File dev:

```yaml
demo:
  api:
    base-url: http://localhost:8089
```

Với profile dev, cả hai vẫn bind vào:

```java
DemoProperties.Api(URI baseUrl, Duration connectTimeout)
```

Dữ liệu từ nguồn nào được ưu tiên là việc của Externalized Configuration; object Java vẫn mang cùng kiểu và accessor.

Điều này tránh các đoạn mã kiểu:

```java
if (isDev) {
    return devUrl;
}
return prodUrl;
```

chỉ để chọn một giá trị cấu hình. Một service có thể dùng `properties.api().baseUrl()` cho mọi profile, còn người vận hành chọn giá trị từ nguồn cấu hình có thứ tự và quyền quản lý phù hợp.

Không dùng profile như cơ chế bảo vệ secret. Một file profile trong JAR vẫn có thể bị đọc từ artifact; credentials nên đến từ nguồn bảo mật được quản lý, không nhúng vào source hoặc `toString` của record.

## 19. Có nên ghi log cả record bằng `toString()` không?

Java record tự tạo `toString()` gồm tên kiểu và giá trị các component. Ví dụ:

```java
System.out.println(properties);
```

có thể cho đầu ra dễ đọc, nhưng đây là **rủi ro nếu record chứa credential hoặc token**. Khi một record lồng nhau chứa secret, `toString()` của root có thể in cả những giá trị đó.

Trong lab, chỉ các khóa giả lập được đưa ra console. Với production:

- Không tự động log nguyên record configuration properties.
- Không đưa `Environment`, Actuator `env`/`configprops` hay config object lên endpoint công khai.
- Cân nhắc tách nhóm secrets khỏi nhóm được phép hiển thị.
- Nếu cần xác minh một thiết lập, chỉ log những khóa nằm trong allowlist và được phê duyệt hiển thị.
- Kiểm soát quyền đọc file và biến môi trường chứa secret.
- Không dùng `String` hoặc record là lý do để bỏ qua cơ chế quản trị secret.

Record giúp rõ hợp đồng dữ liệu, không tự tạo tính bảo mật cho dữ liệu bên trong.

## 20. Bảng so sánh record, POJO và `@Value`

| Tiêu chí | Record + `@ConfigurationProperties` | Mutable POJO + `@ConfigurationProperties` | Nhiều `@Value` |
| --- | --- | --- | --- |
| Đọc nhóm property có cấu trúc | Rất phù hợp | Rất phù hợp | Dễ phân tán |
| Constructor binding | Tự nhiên | Có thể, tùy constructor | Chủ yếu từng tham số |
| Cần setter | Không | Thường có trong JavaBean binding | Không bắt buộc |
| Nested object | Nested record hoặc class | Nested class hoặc object | Phải tự quản lý nhiều chuỗi |
| Type conversion | Có | Có | Có nhưng không thay thế toàn bộ Binder |
| Validation có cấu trúc | Hợp | Hợp | Khó tập trung |
| Trạng thái instance sau binding | Record không gán lại component | Có thể mutable | Tùy class |
| Phòng vệ collection | Cần cân nhắc `List.copyOf` | Cần cân nhắc | Tùy object |
| Unit test không cần Spring | Tạo record qua constructor | Tạo POJO | Cần tách dependency phù hợp |
| Khuyến nghị | Schema config ổn định, đọc nhiều | Cần mutable bean hoặc ràng buộc framework | Một vài giá trị đơn lẻ |

Không phải lúc nào record cũng là lựa chọn duy nhất. Khi hệ thống yêu cầu dynamic refresh với chiến lược thay đổi trạng thái cụ thể, cần cân nhắc vòng đời object và cách consumers nhận bản cập nhật. Record thường đại diện tốt cho **snapshot cấu hình** tại thời điểm binding.

## 21. Những nhầm lẫn phổ biến

### “Record không có constructor nên Spring không biết tạo thế nào”

Record có canonical constructor do Java cung cấp. Constructor đó nhận các record components theo thứ tự khai báo. Spring Boot binder dựa trên metadata record và constructor binding để cấp giá trị.

### “Phải thêm `@ConstructorBinding` lên mọi record”

Không trong Spring Boot 3.3 cho record thông thường có một constructor phù hợp. Nếu đọc tài liệu cũ dùng annotation ở cấp class, kiểm tra lại API của Boot 3 trước khi sao chép.

### “Thêm `@Component` giúp Spring tìm record dễ hơn”

Đối với constructor-bound `@ConfigurationProperties`, đây không phải cách đăng ký đúng. Dùng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.

### “Nested record có chữ `static` ngầm nên không bind được”

Nested record là một **type** có thể được tạo nhiều instance; không phải một static field để Spring tiêm giá trị. Binder tạo nested object bằng constructor như các record khác.

### “Nếu có default cho nested field, thiếu cả nested object vẫn ổn”

Không nên giả định như vậy. Nếu toàn bộ subtree vắng mặt, nested component ở root có thể là null. Xác định object bắt buộc hay tùy chọn và dùng `@NotNull` hoặc `@DefaultValue` ở cấp nested component cho đúng.

### “Record bất biến tuyệt đối cả Map và List”

Bản thân component là final, nhưng collection có thể mutable. Dùng `List.copyOf`/`Map.copyOf` hoặc value types bất biến khi cần bảo vệ snapshot.

### “Thêm file dev là record sẽ tự nhận giá trị dev”

Không. File `application-dev.yaml` được dùng khi profile `dev` đang hoạt động. Cần bật profile bằng một nguồn hợp lệ.

### “Map và list từ nhiều nguồn luôn được merge giống nhau”

Không. Cơ chế bind collection có quy tắc riêng: lists thường được thay thế theo nguồn được chọn, maps có thể merge theo key. Hãy đọc đúng quy tắc cho kiểu collection và thử với file/profile thực tế.

### “Bean config record là singleton global giống static”

Spring singleton thông thường là một bean trong phạm vi **ApplicationContext**. Static field là trạng thái của class/JVM. Một cấu hình record được đăng ký là bean không đồng nghĩa nó trở thành biến global static.

### “Sửa YAML trong lúc chạy sẽ tự thay một record đang được sử dụng”

Không mặc định. Cơ chế Config Data thông thường bind cấu hình khi khởi động. Dynamic refresh nếu có là một cơ chế riêng và có thể cần tạo/đổi instance và làm mới các consumers. Không coi record như một live view của file.

## 22. Checklist triển khai configuration record

Trước khi đưa một nhóm cấu hình mới vào ứng dụng thật:

1. Đặt prefix rõ ràng và không trùng nhóm cấu hình của framework hoặc thư viện khác.
2. Dùng tên property canonical kebab-case trong tài liệu.
3. Dùng nested record cho các nhóm có schema cụ thể; dùng map khi tập key thực sự động.
4. Xác định nhóm nào bắt buộc và nhóm nào optional.
5. Dùng `@DefaultValue` khi default có ý nghĩa nghiệp vụ, không che thiếu cấu hình quan trọng.
6. Thêm `@Validated` ở root và `@Valid` tại nested components nếu cần kiểm tra sâu.
7. Đăng ký record bằng `@ConfigurationPropertiesScan` hoặc `@EnableConfigurationProperties`.
8. Giữ cấu hình không cần thiết phải mutable ở dạng snapshot ổn định; copy collections nếu cần.
9. Inject record vào service bằng constructor; tránh service tự tìm cùng khóa qua `Environment` ở nhiều nơi.
10. Kiểm thử ít nhất một cấu hình nền, một profile override và một lỗi validation quan trọng.
11. Không in toàn bộ cấu hình hoặc secret qua `toString` và endpoint.
12. Khi cần dynamic refresh, thiết kế vòng đời cập nhật rõ ràng thay vì tự ý mutate config state.

## 23. Bài tập tự kiểm tra

### Bài 1. Từ YAML sang nested record

Cho YAML:

```yaml
mail:
  sender:
    display-name: "System"
    reply-to: "noreply@example.test"
  retry:
    max-attempts: 4
    delay: 1s
```

Hãy tạo `@ConfigurationProperties(prefix = "mail")` record có hai nested records `Sender` và `Retry`. Chọn kiểu Java thích hợp cho email (ví dụ `String`) và thời gian (`Duration`). Giải thích vì sao `reply-to` bind vào `replyTo`.

### Bài 2. Thiếu nhóm nested

Một record gốc khai báo `@Valid @NotNull Client client`, nhưng YAML không có bất kỳ key `client.*` nào. Dự đoán điều gì sẽ xảy ra khi validation hoạt động. Nếu nhóm client thực sự optional, bạn sẽ thiết kế default ở cấp nào?

### Bài 3. Default theo constructor

Record:

```java
public record Retry(
        @DefaultValue("3") int maxAttempts,
        @DefaultValue("500ms") Duration backoff
) {}
```

Nếu file chỉ cung cấp `retry.backoff=1s`, giá trị `maxAttempts` là gì? Nếu file cung cấp `retry.max-attempts=not-number`, có nên chuyển về 3 hay báo lỗi?

### Bài 4. Collection và tính bất biến

Giả sử record chứa `List<String> regions`. Vì sao `record` không tự làm `regions` trở thành list bất biến? Bạn có thể chỉnh compact constructor thế nào để không giữ tham chiếu list mutable?

### Bài 5. Profile thay đổi map/list

File nền có:

```yaml
demo:
  regions: [a, b]
  labels:
    team: alpha
    tier: base
```

File dev có:

```yaml
demo:
  regions: [local]
  labels:
    tier: dev
```

Dự đoán sự khác nhau về cách bind list và map khi `dev` hoạt động. Nêu lý do không nên cho rằng cả hai collection đều nối/gộp theo một quy tắc duy nhất.

### Bài 6. Đăng ký record

Vì sao `@Component` không phải lựa chọn phù hợp để đăng ký constructor-bound config record? Hãy viết một trong hai cách dùng scan hoặc enable properties.

### Bài 7. Typed configuration service

Cho `ApiPolicyService` đang dùng nhiều `@Value` để lấy URL, timeout và retry count. Hãy viết lại service nhận duy nhất `DemoProperties` qua constructor và đọc các component cần thiết.

### Bài 8. Bảo vệ dữ liệu

Nếu nested record chứa `apiToken`, vì sao không nên dùng `logger.info("{}", properties)` để debug? Cách nào giúp xác minh binding mà không làm lộ bí mật?

**Gợi ý đối chiếu:**

1. `Sender(String displayName, String replyTo)` và `Retry(int maxAttempts, Duration delay)`; relaxed binding nối kebab-case với camelCase.
2. Với `@NotNull` và validation, thiếu nhóm bắt buộc cần bị phát hiện; nhóm optional có thể dùng nested `@DefaultValue` và default thành phần phù hợp.
3. `maxAttempts=3` khi thiếu; giá trị sai định dạng cần báo lỗi conversion.
4. Record giữ reference final, không tự khóa object được tham chiếu; dùng `List.copyOf`.
5. List thường lấy danh sách từ nguồn ưu tiên phù hợp, map có thể kết hợp key theo quy tắc Binder.
6. Scan hoặc enable properties đăng ký record theo cơ chế constructor binding của Spring Boot.
7. Service nhận `DemoProperties` và gọi `api().baseUrl()`, `api().connectTimeout()`, `retry().maxAttempts()`.
8. `toString()` của record có thể bao gồm token; chỉ hiển thị khóa cho phép và trạng thái an toàn.

## 24. Kết luận

`@ConfigurationProperties` kết hợp Java record là cách biểu diễn cấu hình Spring Boot theo kiểu dữ liệu rõ ràng và dễ sử dụng. Một record gốc mô tả **schema**, nested record biểu diễn **nhóm cấu hình**, constructor binding tạo **snapshot cấu hình có kiểu**, còn `@DefaultValue` và Bean Validation giúp thể hiện **fallback và ràng buộc** ngay tại hợp đồng dữ liệu.

Điều quan trọng nhất không phải giảm số dòng Java, mà là phân tách trách nhiệm:

```text
Nguồn cấu hình / ưu tiên    -> Spring Environment
Chuyển tên và kiểu dữ liệu  -> ConfigurationProperties Binder
Cấu trúc và default        -> Record + nested records
Ràng buộc đầu vào          -> Bean Validation
Nghiệp vụ sử dụng          -> Service nhận bean qua constructor
```

Khi một giá trị không đúng mong đợi, hãy xác định lần lượt: property có thực sự được nạp không, tên canonical và prefix có khớp không, profile và nguồn ưu tiên nào đang áp dụng, object nested đã được tạo chưa, conversion và validation có thành công không. Thiết kế đó giúp cấu hình rõ ràng hơn khi ứng dụng tăng số lượng môi trường triển khai hoặc số nhóm property.

### Tài liệu tham khảo

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html), đặc biệt *Type-safe Configuration Properties*, *Constructor Binding*, *Nested Properties*, *Relaxed Binding*, *Validation*.
- [Spring Boot 3.3 — Profiles](https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html), cách sử dụng cấu hình theo profile.
- [Java Language Specification — Record Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10), cấu trúc và ngữ nghĩa của Java records.