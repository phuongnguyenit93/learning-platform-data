# Chạy từ IDE, bootRun và java -jar với cùng hợp đồng cấu hình

## 1. Mục tiêu bài học

Một ứng dụng Spring Boot thường được chạy theo nhiều cách trong vòng đời phát triển:

- **Từ IDE:** lập trình viên bấm Run/Debug để phát triển và đặt breakpoint.
- **Bằng Gradle `bootRun`:** nhóm phát triển chạy ứng dụng từ terminal hoặc script tự động.
- **Bằng `java -jar`:** nhóm vận hành chạy executable JAR đã đóng gói, gần với cách triển khai thực tế.

Mỗi cách chạy khác nhau về **trình khởi chạy, classpath, thư mục làm việc, cách truyền tham số và môi trường tiến trình**. Tuy nhiên, chúng có thể — và nên — sử dụng **cùng một hợp đồng cấu hình**.

“Hợp đồng cấu hình” ở đây nghĩa là:

1. Ứng dụng công bố **cùng một tập tên thuộc tính**, chẳng hạn `delivery.endpoint`, `delivery.timeout`, `delivery.max-attempts` và `delivery.enabled`.
2. Các thuộc tính được liên kết vào **cùng kiểu Java** như `URI`, `Duration`, `int` và `boolean`.
3. Giá trị bắt buộc, giá trị mặc định, validation và cách xử lý lỗi **không thay đổi theo trình khởi chạy**.
4. Sự khác biệt giữa dev, test và production đến từ **giá trị của nguồn cấu hình** và profile có hiệu lực, không phải từ việc viết ba bộ logic đọc thuộc tính khác nhau.
5. Có thể xác minh ứng dụng thực sự nhìn thấy giá trị nào trong từng lần chạy.

Ví dụ tổng quát:

```text
                         CÙNG HỢP ĐỒNG
                   delivery.endpoint: URI
                   delivery.timeout: Duration
                   delivery.max-attempts: int
                   delivery.enabled: boolean
                                |
                 +--------------+--------------+
                 |              |              |
                IDE          bootRun         java -jar
                 |              |              |
                 +--------------+--------------+
                                |
                         Spring Environment
                                |
                   ConfigurationProperties Binder
                                |
                    DeliveryProperties bean
                                |
                         DeliveryService
```

**Ý chính:** không viết nhánh kiểu “nếu chạy từ IDE thì đọc khóa A, nếu chạy JAR thì đọc khóa B”. Hãy để Spring Boot xử lý nguồn cấu hình và thống nhất tên thuộc tính cùng quy tắc binding.

## 2. Những điều thay đổi và không thay đổi

| Khía cạnh | IDE | Gradle bootRun | java -jar |
| --- | --- | --- | --- |
| Cách khởi động | Run configuration của IDE | Task Gradle chạy ứng dụng | JVM chạy executable JAR |
| Classpath | Class output/resources của dự án | Runtime classpath của task | Class và dependency trong JAR |
| Program arguments | Trường Program arguments | `--args=...` của `bootRun` | Tham số sau đường dẫn JAR |
| JVM system properties | Trường VM options | Cấu hình JVM của task, hoặc theo cách Gradle truyền cho tiến trình app | `-Dkey=value` **trước** `-jar` |
| Environment variables | Trường Environment của Run configuration hoặc môi trường thừa kế | Môi trường tiến trình Gradle và Java app, nếu không bị sửa | Môi trường shell/service khởi chạy |
| Working directory | Do Run configuration quyết định | Theo cấu hình Gradle task, thường là project directory | Thư mục hiện tại của shell/service |
| Config Data trên classpath | Từ nguồn build của dự án | Từ classpath chạy của Gradle | Từ tài nguyên đã đóng gói trong JAR |
| Profile/ưu tiên nguồn | Theo Spring Environment | Theo Spring Environment | Theo Spring Environment |
| `@ConfigurationProperties`/validation | Cùng logic | Cùng logic | Cùng logic |

Khác biệt lớn nhất thường là **đầu vào thực tế** của quá trình chạy, không phải việc Spring Boot có một binder riêng cho IDE và một binder khác cho JAR.

Trong cả ba trường hợp, Spring Boot vẫn có thể đọc `application.yml` trên classpath, nhận môi trường, tham số dòng lệnh và những vị trí cấu hình bổ sung phù hợp.

## 3. Xây một hợp đồng cấu hình duy nhất

Giả sử ứng dụng có dịch vụ gửi thông báo. Chúng ta dùng tiền tố `delivery`.

Các khóa:

| Khóa chuẩn | Kiểu Java | Bắt buộc? | Ý nghĩa |
| --- | --- | --- | --- |
| `delivery.endpoint` | `URI` | Có | Endpoint gửi yêu cầu |
| `delivery.timeout` | `Duration` | Có | Thời gian chờ |
| `delivery.max-attempts` | `int` | Giá trị dương | Số lần được thử |
| `delivery.enabled` | `boolean` | Có mặc định | Bật/tắt tính năng |
| `delivery.channel` | `String` | Có | Tên kênh thông báo |

Tên được dùng ở dạng **lowercase, kebab-case**. Đây là dạng nên dùng trong YAML/Properties và tài liệu hợp đồng của Spring Boot.

Trong mã Java, thuộc tính thường có dạng camelCase, ví dụ `maxAttempts`. Binder hỗ trợ relaxed binding để liên kết các biến thể tên hợp lệ, nhưng không tự sửa mọi lỗi đánh máy.

### 3.1. Định nghĩa record cấu hình

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotNull URI endpoint,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts,
        @DefaultValue("true") boolean enabled,
        @NotBlank String channel) {
}
```

Điểm cần nhớ:

- `@ConfigurationProperties(prefix = "delivery")` định nghĩa một nhóm thuộc tính.
- `@NotNull` yêu cầu `endpoint` và `timeout` phải có giá trị.
- `@Min(1)` yêu cầu `maxAttempts` ít nhất là 1.
- `@DefaultValue("true")` cung cấp mặc định cho `enabled` nếu thuộc tính không có trong những nguồn binder đang xem xét.
- `@NotBlank` loại bỏ `null`, chuỗi rỗng hoặc chỉ chứa khoảng trắng cho `channel`.
- Record có constructor binding; không cần setter cho các thành phần.

Với Spring Boot 3.x, nhóm annotation validation trên dùng package `jakarta.validation.*`; dự án thường cần `spring-boot-starter-validation` để thực thi Bean Validation.

Đây là **một hợp đồng cấu hình duy nhất**, được dùng bất kể ứng dụng khởi chạy theo cách nào.

### 3.2. Đăng ký ConfigurationProperties

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Đặt record trong package được `@ConfigurationPropertiesScan` quét.

Có thể dùng `@EnableConfigurationProperties(DeliveryProperties.class)` thay thế nếu muốn đăng ký tường minh. Không cần gắn `@Component` lên record chỉ để Spring tự phát hiện nó qua component scanning thông thường.

## 4. Chuẩn bị các file cấu hình dùng chung

Trong dự án Java/Gradle:

```text
src/
  main/
    java/
      com/example/configdemo/
        ConfigDemoApplication.java
        DeliveryProperties.java
        DeliveryService.java
        DeliveryConfigPrinter.java
    resources/
      application.yml
      application-dev.yml
      application-prod.yml
build.gradle
settings.gradle
gradlew
gradlew.bat
```

### 4.1. Cấu hình mặc định

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: config-demo

delivery:
  endpoint: "https://delivery.example.invalid"
  timeout: 5s
  max-attempts: 3
  enabled: true
  channel: "default"
```

Đây là cấu hình cơ sở có các khóa phù hợp với record. Endpoint dùng miền `example.invalid` để minh họa; chương trình không cần thực sự kết nối tới địa chỉ ấy trong bài học.

### 4.2. Cấu hình dev

```yaml
# src/main/resources/application-dev.yml
delivery:
  timeout: 2s
  max-attempts: 2
  channel: "development"
```

Tệp dev chỉ định những giá trị khác với mặc định. Các khóa khác như `delivery.endpoint` và `delivery.enabled` có thể giữ giá trị từ tệp chung nếu không nguồn ưu tiên cao hơn ghi đè.

### 4.3. Cấu hình production

```yaml
# src/main/resources/application-prod.yml
delivery:
  timeout: 10s
  max-attempts: 5
  channel: "production"
```

Trong triển khai thật, endpoint production, token và secret có thể được cấp từ biến môi trường hoặc hệ thống secret thay vì đóng gói thẳng vào JAR. Nội dung ở đây chỉ minh họa profile-specific configuration.

**Không tự đặt `spring.profiles.active: prod` trong tệp `application-prod.yml`.** Profile nên được kích hoạt từ một nguồn cho phép ở giai đoạn chuẩn bị cấu hình, như tham số khởi chạy hoặc environment variable.

## 5. Tạo service đọc cấu hình đã được liên kết

```java
package com.example.configdemo;

import org.springframework.stereotype.Service;

@Service
public class DeliveryService {

    private final DeliveryProperties properties;

    public DeliveryService(DeliveryProperties properties) {
        this.properties = properties;
    }

    public boolean canSend() {
        return properties.enabled()
                && properties.maxAttempts() >= 1;
    }

    public String describe() {
        return "endpoint=" + properties.endpoint()
                + ", timeout=" + properties.timeout()
                + ", maxAttempts=" + properties.maxAttempts()
                + ", enabled=" + properties.enabled()
                + ", channel=" + properties.channel();
    }
}
```

Ở đây `DeliveryService` không quan tâm ứng dụng được chạy từ IDE, `bootRun` hay JAR. Nó chỉ nhận `DeliveryProperties` qua constructor injection.

Điều này giảm rủi ro có ba chỗ đọc cấu hình khác nhau:

```java
// Không nên đặt kiểu logic này trong service:
if (isIdeRun()) {
    // Đọc file dev riêng.
} else if (isGradleRun()) {
    // Đọc một tên biến khác.
} else {
    // Đọc đường dẫn tương đối của JAR.
}
```

Hãy xem trình khởi chạy là cách tạo tiến trình Java, còn Spring Environment là cơ chế cấp giá trị cấu hình cho ứng dụng.

## 6. Quan sát cấu hình thực tế khi chạy

Để học và kiểm tra kỹ thuật, tạo một runner in **những giá trị minh họa không nhạy cảm**.

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DeliveryConfigPrinter implements ApplicationRunner {

    private final DeliveryProperties properties;
    private final Environment environment;

    public DeliveryConfigPrinter(
            DeliveryProperties properties,
            Environment environment) {
        this.properties = properties;
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("activeProfiles="
                + String.join(",", environment.getActiveProfiles()));
        System.out.println("endpoint=" + properties.endpoint());
        System.out.println("timeout=" + properties.timeout());
        System.out.println("maxAttempts=" + properties.maxAttempts());
        System.out.println("enabled=" + properties.enabled());
        System.out.println("channel=" + properties.channel());
    }
}
```

Đối với cấu hình cơ sở và không kích hoạt profile riêng, kết quả minh họa:

```text
activeProfiles=
endpoint=https://delivery.example.invalid
timeout=PT5S
maxAttempts=3
enabled=true
channel=default
```

Với profile dev:

```text
activeProfiles=dev
endpoint=https://delivery.example.invalid
timeout=PT2S
maxAttempts=2
enabled=true
channel=development
```

Với profile prod:

```text
activeProfiles=prod
endpoint=https://delivery.example.invalid
timeout=PT10S
maxAttempts=5
enabled=true
channel=production
```

Cú pháp `PT5S` và `PT2S` là kết quả biểu diễn `Duration` theo dạng ISO-8601, không phải chuỗi nguyên gốc `5s` hay `2s` của YAML.

**Không in bean cấu hình đầy đủ trong hệ thống thật nếu bean chứa mật khẩu, token hoặc khóa truy cập.** Chỉ log tên thuộc tính, trạng thái cần thiết hoặc giá trị không nhạy cảm.

## 7. Chuẩn bị build.gradle cho bootRun và bootJar

`bootRun` là task do **Spring Boot Gradle plugin** cung cấp. Nếu dự án chỉ áp dụng plugin `java` mà không có plugin Spring Boot phù hợp, task `bootRun` có thể không tồn tại.

Khung minh họa Groovy DSL:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<compatible-version>'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đoạn trên là **khung cấu trúc**, cố ý để placeholder version thay vì giả định phiên bản Spring Boot/Gradle đang dùng của dự án. Trong dự án thật, thay chúng bằng các phiên bản tương thích đã được quản lý trong build hiện có, hoặc sử dụng cấu hình plugin chính thức tương ứng. Không nên chép nguyên placeholder vào file rồi kỳ vọng Gradle chạy được.

Nếu dự án đã có `build.gradle`, thường chỉ cần kiểm tra plugin Spring Boot và dependency validation; không cần viết lại cả file.

Với Spring Boot plugin đã cấu hình phù hợp, các task thường có:

```text
bootRun    chạy ứng dụng qua Gradle
bootJar    đóng gói executable JAR
build      thực hiện lifecycle build, gồm kiểm thử và đóng gói theo cấu hình
```

Chạy:

```bash
./gradlew tasks
```

để tìm các task hiện diện trong dự án. Trên Windows PowerShell, dùng `.\gradlew.bat tasks`.

## 8. Cách 1 — chạy từ IDE

Với IntelliJ IDEA, Eclipse/STS hoặc VS Code có hỗ trợ Java/Spring Boot, bạn thường tạo một **Run configuration** trỏ tới lớp main:

```java
com.example.configdemo.ConfigDemoApplication
```

Các trường thông dụng có thể được gọi bằng những tên như:

| Trường cấu hình chạy | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Main class | `com.example.configdemo.ConfigDemoApplication` | Điểm bắt đầu |
| Program arguments | `--spring.profiles.active=dev` | Tham số truyền vào `main(String[] args)` |
| VM options | `-Dspring.profiles.active=dev` | Java system property của JVM |
| Environment variables | `DELIVERY_MAXATTEMPTS=4` | Biến môi trường của tiến trình |
| Working directory | Thư mục dự án/module | Gốc tương đối khi đọc file ngoài classpath |
| Module/classpath | Module chứa ứng dụng | Class và resource khi Run |

Tên và vị trí giao diện khác nhau theo IDE/extension. Điều quan trọng là phân biệt **Program arguments**, **VM options** và **Environment variables**; chúng không cùng một loại đầu vào.

### 8.1. IDE Program arguments

Trong Run configuration, đặt:

```text
--spring.profiles.active=dev --delivery.max-attempts=4
```

Khi IDE gọi main class, các đối số này được chuyển vào `SpringApplication.run(..., args)`.

Nếu không có nguồn khác với mức ưu tiên cao hơn, ứng dụng dùng profile dev, nhưng `delivery.max-attempts=4` từ chương trình sẽ ghi đè `max-attempts: 2` của tệp dev.

Kết quả:

```text
activeProfiles=dev
timeout=PT2S
maxAttempts=4
channel=development
```

### 8.2. IDE VM options

Nếu thay vào đó đặt:

```text
-Dspring.profiles.active=dev -Ddelivery.max-attempts=4
```

ở trường VM options, IDE sẽ cấp **Java system properties** cho JVM.

Khác biệt kỹ thuật:

- `--spring.profiles.active=dev` là tham số ứng dụng do Spring Boot xử lý như command-line property.
- `-Dspring.profiles.active=dev` là tùy chọn của JVM, tạo system property.

Trong Spring Boot mặc định, **command-line arguments thường có độ ưu tiên cao hơn Java system properties**. Vì vậy không nên đưa cùng một khóa với hai giá trị khác nhau rồi nghĩ chúng tương đương hoàn toàn.

### 8.3. IDE Environment variables

Ví dụ thiết lập:

```text
SPRING_PROFILES_ACTIVE=dev
DELIVERY_MAXATTEMPTS=4
```

Biến môi trường phải được truyền vào **chính tiến trình Java mà IDE khởi chạy**. Đặt biến trong một cửa sổ terminal không có nghĩa một IDE đã mở trước đó sẽ tự thấy biến ấy.

Nếu IDE hỗ trợ trường Environment, hãy khai báo trực tiếp ở đó để tránh khác biệt về quá trình thừa kế môi trường từ shell.

### 8.4. IDE Working directory

Một số IDE dùng thư mục dự án làm working directory; trường hợp khác dùng thư mục module hoặc đường dẫn do người dùng chọn.

Nếu cấu hình ngoài JAR nằm tại:

```text
./config/application.yml
```

thì dấu `./` phụ thuộc vào working directory của tiến trình. Chạy IDE với working directory khác có thể khiến ứng dụng không tìm được cùng tệp mà `java -jar` đang dùng.

Không nên dựa vào một đường dẫn tương đối chưa được xác định trong hợp đồng triển khai.

## 9. Cách 2 — chạy bằng Gradle bootRun

Khi dự án dùng Spring Boot Gradle plugin, có thể chạy ứng dụng bằng:

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

`bootRun` khởi chạy ứng dụng Java bằng classpath runtime được Gradle xây dựng cho ứng dụng. Ở chế độ phát triển, nó thường dùng class output và resource của module thay vì chạy executable JAR đã đóng gói.

### 9.1. Truyền program arguments qua --args

Với Gradle, cách thông dụng:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

Muốn thêm override:

```bash
./gradlew bootRun \
  --args='--spring.profiles.active=dev --delivery.max-attempts=4'
```

Dấu gạch chéo ngược dùng để nối dòng trong shell theo kiểu Linux/macOS. Nếu copy sang Windows PowerShell, có thể đặt toàn bộ lệnh trên một dòng:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev --delivery.max-attempts=4"
```

Lưu ý vị trí tham số:

- `--args=...` là tùy chọn dành cho task kiểu JavaExec/bootRun của Gradle.
- Chuỗi bên trong `--args` chứa các đối số ứng dụng thực tế, chẳng hạn `--delivery.max-attempts=4`.

Không nên viết:

```bash
./gradlew bootRun --delivery.max-attempts=4
```

và kỳ vọng Gradle tự hiểu đó là tham số của ứng dụng. Gradle sẽ cố xử lý nó như một tham số của chính Gradle nếu cú pháp không đúng.

### 9.2. Biến môi trường khi bootRun

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=dev \
DELIVERY_MAXATTEMPTS=4 \
./gradlew bootRun
```

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:DELIVERY_MAXATTEMPTS = "4"
.\gradlew.bat bootRun
```

Những biến này nằm trong môi trường tiến trình Gradle và thông thường được tiến trình Java do task khởi chạy thừa hưởng, trừ khi task hoặc script chủ động thay đổi môi trường của tiến trình con.

Với PowerShell, những giá trị đặt bằng `$env:...` tồn tại trong phiên shell đó và được thừa kế bởi những chương trình con khởi chạy từ shell. Không nên kỳ vọng chúng tự lan sang mọi IDE hoặc terminal khác.

### 9.3. Program arguments khác Gradle JVM arguments

Một điểm nhầm phổ biến:

```bash
./gradlew -Ddelivery.max-attempts=4 bootRun
```

Tùy chọn `-D...` ở lệnh Gradle có thể thiết lập **system property cho tiến trình Gradle**, không nhất thiết chuyển thành cùng system property ở **JVM ứng dụng** do task `bootRun` tạo ra.

Nếu muốn cung cấp giá trị cấu hình cho ứng dụng một cách đơn giản và rõ ràng, ưu tiên:

```bash
./gradlew bootRun --args='--delivery.max-attempts=4'
```

Hoặc cấu hình `systemProperty`/`jvmArgs` trên task `bootRun` trong `build.gradle` một cách tường minh nếu cần JVM system property.

Ví dụ:

```groovy
tasks.named('bootRun') {
    systemProperty 'delivery.max-attempts', '4'
}
```

Đoạn này cố định giá trị khi chạy qua task, nên **không nên dùng cho cấu hình thay đổi theo môi trường** trừ khi có cơ chế cấp giá trị phù hợp. Tránh “đóng đinh” production config trong Gradle chỉ để thuận tiện chạy local.

## 10. Cách 3 — chạy executable JAR bằng java -jar

Đối với Gradle, đóng gói bằng:

```bash
./gradlew clean bootJar
```

Trên Windows:

```powershell
.\gradlew.bat clean bootJar
```

Executable JAR thường được tạo trong:

```text
build/libs/
```

Tên file phụ thuộc tên dự án, version và cấu hình của task. Ví dụ một artifact có thể mang tên:

```text
build/libs/config-demo-1.0.0.jar
```

Không giả định tên này luôn đúng trong dự án thật; hãy liệt kê output của `build/libs/` sau khi build.

### 10.1. Chạy không truyền tham số

```bash
java -jar build/libs/config-demo-1.0.0.jar
```

Nếu JAR chứa `application.yml` trong classpath và không có nguồn khác ghi đè, ứng dụng nhận cấu hình cơ sở.

### 10.2. Truyền program arguments

```bash
java -jar build/libs/config-demo-1.0.0.jar \
  --spring.profiles.active=dev \
  --delivery.max-attempts=4
```

Trên PowerShell, dùng một dòng:

```powershell
java -jar .\build\libs\config-demo-1.0.0.jar --spring.profiles.active=dev --delivery.max-attempts=4
```

Ở đây hai đối số sau tên JAR được chuyển vào `main(String[] args)` của ứng dụng và được `SpringApplication.run(..., args)` xử lý theo cơ chế mặc định.

**Quan trọng:** đối số ứng dụng đặt **sau** đường dẫn JAR.

### 10.3. Truyền Java system properties

```bash
java -Dspring.profiles.active=dev \
     -Ddelivery.max-attempts=4 \
     -jar build/libs/config-demo-1.0.0.jar
```

`-D...` là tùy chọn JVM, nên phải đặt **trước `-jar`** khi muốn JVM xử lý chúng như Java system properties.

Nếu viết:

```bash
java -jar build/libs/config-demo-1.0.0.jar \
  -Ddelivery.max-attempts=4
```

thì phần `-Ddelivery.max-attempts=4` nằm **sau** JAR không còn là JVM option theo quy tắc gọi `java`. Nó trở thành đối số truyền vào ứng dụng; Spring Boot không coi nó là Java system property một cách tự động.

Đây là lỗi thường gặp khi chuyển cấu hình từ ô VM options trong IDE sang lệnh shell.

### 10.4. Truyền environment variables

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=dev \
DELIVERY_MAXATTEMPTS=4 \
java -jar build/libs/config-demo-1.0.0.jar
```

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:DELIVERY_MAXATTEMPTS = "4"
java -jar .\build\libs\config-demo-1.0.0.jar
```

Nếu dùng systemd, container hoặc một nền tảng triển khai khác, environment variables phải được khai báo trong chính **cấu hình của service/container**. Việc người vận hành chạy `export` trong một terminal khác không bảo đảm tiến trình dịch vụ do hệ thống quản lý nhận biến ấy.

## 11. Ba cách chạy, cùng một ví dụ cụ thể

Yêu cầu: chạy ứng dụng ở profile `dev`, đặt `delivery.max-attempts=4` và vẫn sử dụng `delivery.timeout=2s` từ `application-dev.yml`.

### IDE

Trong Program arguments:

```text
--spring.profiles.active=dev --delivery.max-attempts=4
```

### Gradle bootRun

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --delivery.max-attempts=4'
```

### java -jar

```bash
java -jar build/libs/config-demo-1.0.0.jar \
  --spring.profiles.active=dev \
  --delivery.max-attempts=4
```

Khi ba cách đều khởi chạy **cùng mã và những nguồn cấu hình có hiệu lực tương đương**, kết quả của `DeliveryProperties` phải tương đương:

```text
endpoint=https://delivery.example.invalid
timeout=PT2S
maxAttempts=4
enabled=true
channel=development
```

Kết quả này là **kỳ vọng theo dữ liệu đã khai báo trong bài**, không phải cam kết rằng mọi IDE hoặc CI của mọi dự án đều có classpath và biến môi trường giống nhau. Nếu kết quả khác, kiểm tra nguồn/đối số thực sự được truyền vào tiến trình.

## 12. Thống nhất hợp đồng không có nghĩa giống hệt nguồn dữ liệu

Ba cách chạy có thể cấp giá trị từ các nguồn khác nhau mà vẫn tuân theo cùng hợp đồng.

Ví dụ:

| Cách chạy | Nguồn cho `delivery.max-attempts` | Giá trị |
| --- | --- | --- |
| IDE | Program arguments | `4` |
| bootRun | Biến môi trường `DELIVERY_MAXATTEMPTS` | `4` |
| java -jar | Đối số `--delivery.max-attempts=4` | `4` |

Bản chất hợp đồng vẫn là:

```text
delivery.max-attempts -> int maxAttempts, tối thiểu 1
```

Các nguồn chỉ khác cách biểu diễn và vận chuyển giá trị.

Cùng một hợp đồng cho phép nhóm vận hành thay đổi cơ chế cấp cấu hình mà **không sửa code nghiệp vụ**.

Tuy nhiên, không nên cố định rằng “IDE luôn dùng program arguments”, “Gradle luôn dùng environment variable” hoặc “JAR luôn dùng CLI”. Cả ba cách chạy đều có thể dùng nhiều nguồn của Spring Boot; hãy chọn quy ước phù hợp với môi trường và mô tả rõ trong tài liệu triển khai.

## 13. Thứ tự ưu tiên khi một khóa xuất hiện nhiều lần

Giả sử:

```yaml
# application.yml
delivery:
  max-attempts: 3
```

```yaml
# application-dev.yml
delivery:
  max-attempts: 2
```

Và khi chạy ứng dụng:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --delivery.max-attempts=8
```

Trong Spring Boot thông thường, đối số ứng dụng `--delivery.max-attempts=8` được ưu tiên hơn giá trị thuộc Config Data trong tệp dev. Kết quả là `8`.

Điều này không thay đổi giữa IDE và `bootRun` nếu chúng cấp cùng command-line property.

Một sơ đồ đơn giản:

```text
application.yml           delivery.max-attempts = 3
application-dev.yml       delivery.max-attempts = 2
command-line arguments    delivery.max-attempts = 8
                                     |
                                     v
                              Giá trị có hiệu lực
                                     8
                                     |
                                     v
                              DeliveryProperties
```

**Cẩn trọng:** thứ tự ưu tiên hoàn chỉnh của Spring Boot còn có nhiều nguồn khác như test properties, system properties, environment variables và các nguồn đặc biệt. Bài học chỉ nêu những quan hệ liên quan để so sánh ba cách khởi chạy. Khi cần giải quyết xung đột cụ thể, hãy kiểm tra những PropertySource thực tế.

## 14. Profile được kích hoạt theo cùng một hợp đồng

Spring Boot dùng profile để nạp các tài liệu hoặc cấu hình dành cho môi trường thích hợp.

Ví dụ:

```yaml
# application-dev.yml
delivery:
  channel: "development"
```

Kích hoạt profile bằng một trong các cơ chế:

**IDE Program arguments**

```text
--spring.profiles.active=dev
```

**bootRun**

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

**JAR**

```bash
java -jar app.jar --spring.profiles.active=dev
```

Hoặc dùng biến môi trường:

```text
SPRING_PROFILES_ACTIVE=dev
```

Cả ba cách đều sử dụng cùng tên cấu hình chuẩn `spring.profiles.active`, không phải ba loại “IDE profile”, “Gradle profile” và “JAR profile” độc lập.

### 14.1. Profile mặc định

Nếu không khai báo active profile, Spring Boot có cơ chế default profile (thường là tên `default`) để xử lý các tình huống phù hợp. `Environment#getActiveProfiles()` có thể trả về một mảng trống khi không có profile nào được kích hoạt tường minh.

**Không nên in `getActiveProfiles()` rỗng rồi kết luận Spring không nạp `application.yml`.** Tệp cơ sở vẫn có thể được nạp bình thường.

### 14.2. Không trộn profile và cách chạy

Một JAR production vẫn có thể chạy profile `dev` nếu cấu hình khởi động của nó yêu cầu như vậy; điều này không phụ thuộc vào việc artifact được xây bằng `bootJar`.

Ngược lại, IDE cũng có thể chạy với profile `prod` khi muốn kiểm tra đường đi của cấu hình production — nếu dữ liệu cần thiết và quyền truy cập tương ứng được cấp an toàn.

Profile là **một thuộc tính cấu hình của lần khởi động**, không phải nhãn tự động suy ra từ công cụ khởi chạy.

## 15. Biến môi trường: cách đặt tên chuẩn

Spring Boot có cơ chế ánh xạ tên property sang environment variable.

Với dạng tên chuẩn:

```text
delivery.max-attempts
```

một dạng môi trường tiêu biểu là:

```text
DELIVERY_MAXATTEMPTS
```

Quy tắc thường dùng là:

1. Dấu chấm `.` thành dấu gạch dưới `_`.
2. Dấu gạch ngang `-` bị bỏ.
3. Chữ được chuyển thành chữ hoa.

Những ví dụ:

| Khóa Spring Boot | Environment variable |
| --- | --- |
| `delivery.endpoint` | `DELIVERY_ENDPOINT` |
| `delivery.timeout` | `DELIVERY_TIMEOUT` |
| `delivery.max-attempts` | `DELIVERY_MAXATTEMPTS` |
| `delivery.enabled` | `DELIVERY_ENABLED` |
| `delivery.channel` | `DELIVERY_CHANNEL` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |

Ví dụ với Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=dev \
DELIVERY_TIMEOUT=3s \
DELIVERY_MAXATTEMPTS=4 \
./gradlew bootRun
```

Khi binder liên kết `DeliveryProperties`, nó có thể lấy `timeout=3s` từ environment thay vì `2s` của tệp dev, vì environment variables có ưu tiên cao hơn Config Data trong cách cấu hình Spring Boot thông thường.

**Lưu ý:** `DELIVERY_MAX_ATTEMPTS` không nhất thiết tương đương `DELIVERY_MAXATTEMPTS` trong mọi cách ánh xạ tên của Spring Boot. Nên tuân theo dạng chuẩn của tài liệu và xác nhận giá trị có hiệu lực bằng một test thực tế.

## 16. Program arguments, VM options và environment khác nhau

Đây là điểm dễ sai nhất khi chuyển một Run configuration từ IDE sang shell.

| Cơ chế | Cách viết | Vị trí |
| --- | --- | --- |
| Program argument | `--delivery.timeout=4s` | Sau tên JAR hoặc trong Program arguments |
| Java system property | `-Ddelivery.timeout=4s` | Trước `-jar` hoặc trong VM options |
| Environment variable | `DELIVERY_TIMEOUT=4s` | Môi trường của tiến trình |
| Config Data | `delivery.timeout: 4s` | YAML/Properties được nạp |

Ví dụ JVM command chuẩn:

```bash
java -Ddelivery.timeout=4s \
     -jar app.jar \
     --delivery.max-attempts=5
```

Trong dòng lệnh này:

- `delivery.timeout` được cấp dưới dạng Java system property;
- `delivery.max-attempts` được cấp dưới dạng command-line property.

Nếu ứng dụng cho phép command-line properties theo cấu hình mặc định, chúng thường có mức ưu tiên cao hơn Java system properties khi **cùng một khóa** xuất hiện ở hai nguồn.

Mấu chốt là **không phải mọi từ khóa đứng sau `java` đều do Spring Boot đọc giống nhau**.

## 17. Thư mục làm việc và file cấu hình bên ngoài JAR

Một trong những nguyên nhân thường gặp của tình huống “chạy IDE được nhưng `java -jar` không đọc đúng cấu hình” là **working directory**.

Giả sử có:

```text
workspace/
  config/
    application.yml
  app/
    build/
      libs/
        config-demo-1.0.0.jar
```

Nếu shell đang đứng ở `workspace/` rồi chạy:

```bash
java -jar app/build/libs/config-demo-1.0.0.jar
```

thì đường dẫn `./config/application.yml` có thể được Spring Boot xét theo các vị trí mặc định bên ngoài classpath, tùy cơ chế Config Data và cách bố trí.

Nhưng nếu chuyển thư mục:

```bash
cd app
java -jar build/libs/config-demo-1.0.0.jar
```

thì `./config/` bây giờ trỏ tới:

```text
workspace/app/config/
```

không còn là thư mục `workspace/config/`.

Điều này giải thích vì sao **cùng một JAR** nhưng chạy từ hai working directory khác nhau có thể nhận hai tập cấu hình khác nhau.

### 17.1. Khuyến nghị cho nhóm

Trong tài liệu triển khai, cần xác định:

- Thư mục làm việc được phép.
- Cấu hình ngoài JAR có nằm dưới `./config/` hay không.
- Đường dẫn được cấp qua environment hay command-line property.
- Cách chạy từ service/container có đặt working directory phù hợp không.
- Cơ chế dự phòng khi file không tồn tại.

Không nên dựa vào “trên máy tôi chạy được” khi working directory không được chuẩn hóa.

## 18. Dùng spring.config.additional-location để thống nhất file bên ngoài

Khi muốn bổ sung một thư mục cấu hình ngoài những vị trí mặc định, Spring Boot hỗ trợ:

```text
spring.config.additional-location
```

Ví dụ đặt cấu hình tại:

```text
/opt/config-demo/runtime-config/application.yml
```

Trên Linux/macOS, chạy:

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/opt/config-demo/runtime-config/
```

Với directory location, dấu `/` cuối đường dẫn có ý nghĩa: Spring Boot xem đó là thư mục và có thể tìm tệp `application.*` thích hợp theo quy tắc Config Data.

Từ khóa `optional:` cho phép ứng dụng tiếp tục khi địa điểm cấu hình không tồn tại trong những trường hợp cơ chế Config Data cho phép, thay vì thất bại chỉ vì thiếu location.

**Phân biệt:**

- `spring.config.location` thay thế những vị trí tìm kiếm mặc định theo cơ chế được Boot định nghĩa.
- `spring.config.additional-location` thêm vị trí bên cạnh các vị trí chuẩn.

Nếu mục đích là bổ sung cấu hình ngoài JAR **mà vẫn giữ tệp mặc định trên classpath**, `additional-location` thường phù hợp hơn.

### 18.1. Dùng cùng một location qua ba cách chạy

Nếu IDE, `bootRun` và `java -jar` cùng cần đọc một thư mục, hãy truyền cùng một giá trị location:

**IDE Program arguments**

```text
--spring.config.additional-location=optional:file:/opt/config-demo/runtime-config/
```

**bootRun**

```bash
./gradlew bootRun \
  --args='--spring.config.additional-location=optional:file:/opt/config-demo/runtime-config/'
```

**JAR**

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/opt/config-demo/runtime-config/
```

Đây là ví dụ đường dẫn Linux. Trên Windows, dùng đường dẫn hợp lệ với Windows và cú pháp URL/Config Data phù hợp, đồng thời lưu ý quote khi đường dẫn có khoảng trắng.

Nếu chỉ muốn tránh khác biệt working directory, **đường dẫn tuyệt đối** thường dễ suy luận hơn đường dẫn `./runtime-config/`.

### 18.2. Cấu hình phải được cấp đủ sớm

Các thuộc tính như `spring.config.location`, `spring.config.additional-location` hoặc `spring.config.name` ảnh hưởng **giai đoạn nạp Config Data**. Chúng cần được cung cấp từ nguồn phù hợp và đủ sớm, chẳng hạn environment variable, Java system property hoặc command-line argument.

Không nên nghĩ rằng đặt `spring.config.additional-location` bên trong một bean `@PostConstruct` sẽ làm Boot quay lại giai đoạn nạp Config Data và nạp lại thư mục.

## 19. File application.yml trên classpath và file ngoài JAR

Khi dự án được build thành executable JAR, một tệp:

```text
src/main/resources/application.yml
```

thường được đóng gói dưới:

```text
BOOT-INF/classes/application.yml
```

trong cấu trúc executable JAR thông dụng.

Có thể kiểm tra:

```bash
jar tf build/libs/config-demo-1.0.0.jar
```

Trên Linux/macOS:

```bash
jar tf build/libs/config-demo-1.0.0.jar | grep 'application.yml'
```

Trên PowerShell:

```powershell
jar tf .\build\libs\config-demo-1.0.0.jar |
    Select-String 'application\.yml'
```

Nếu không có tệp cấu hình như mong đợi trong JAR, cần xem lại cấu hình source set/resource processing và artifact thực tế.

Ngược lại, dù JAR chứa `application.yml`, người vận hành vẫn có thể cấp **một nguồn ưu tiên cao hơn** từ bên ngoài, ví dụ environment variables hoặc Config Data ở một vị trí ưu tiên hơn.

**Đóng gói file vào JAR không đồng nghĩa giá trị trong file đó luôn thắng.**

## 20. Cùng source code nhưng artifact khác phiên bản

Một lỗi khác ít liên quan tới Spring Environment: IDE có thể chạy mã mới nhất trong project, trong khi `java -jar` đang chạy **JAR được build từ hôm qua**.

Ví dụ:

- IDE đang đọc record có trường `delivery.channel` mới.
- Executable JAR cũ vẫn chứa phiên bản `DeliveryProperties` chưa có trường này.
- Cả hai dùng cùng `application.yml`, nhưng hợp đồng thực tế của class không giống nhau.

Vì thế, khi so sánh ba cách chạy, cần xác nhận:

1. Đã lưu mã nguồn.
2. Đã rebuild artifact.
3. Đang chạy đúng JAR vừa build.
4. Đang dùng đúng version của module/dependency.
5. Không có tiến trình ứng dụng cũ vẫn chạy trên port hoặc service khác.

Một lệnh build tái lập:

```bash
./gradlew clean bootJar
```

có thể giúp loại bỏ những class/resource cũ trong output, nhưng không thay thế việc xác nhận đường dẫn JAR được dùng ở deployment.

## 21. Build JAR và chạy JAR không phải cùng một việc

Hai lệnh:

```bash
./gradlew bootJar
java -jar build/libs/config-demo-1.0.0.jar
```

thực hiện hai bước riêng biệt:

1. `bootJar` tạo artifact dựa trên mã và cấu hình build.
2. `java -jar` tạo tiến trình Java mới và đọc các nguồn cấu hình tại thời điểm chạy.

Biến môi trường dùng trong **quá trình build** không mặc định trở thành biến môi trường của **quá trình chạy JAR** trong một máy/container khác.

Tương tự, một giá trị được khai báo trong Gradle script để ảnh hưởng `bootRun` không nhất thiết trở thành mặc định của JAR được đóng gói.

Nếu dự án muốn cùng hợp đồng cấu hình ở production, hãy đảm bảo artifact có cùng model Java và cấu hình runtime được cấp bằng một nguồn được Boot hỗ trợ, không dựa vào side effect của shell đã dùng để build.

## 22. Tệp .env không tự được nạp chỉ vì nằm cạnh JAR

Một tình huống phổ biến:

```text
project/
  .env
  build/libs/app.jar
```

Nội dung:

```dotenv
DELIVERY_MAXATTEMPTS=4
SPRING_PROFILES_ACTIVE=dev
```

Một tệp có tên `.env` **không tự động được Spring Boot nạp như environment variables** chỉ vì nó nằm trong project hoặc cạnh JAR.

Có những công cụ phát triển, Docker Compose, shell script hoặc thư viện bên ngoài hỗ trợ đọc file `.env`. Nhưng phải có thành phần chủ động đọc và đưa dữ liệu vào **môi trường tiến trình Java** hoặc PropertySource thích hợp.

Ví dụ:

- IDE có thể hỗ trợ plugin đọc `.env` nhưng đây là khả năng của plugin, không phải cơ chế mặc định.
- Docker Compose có quy tắc riêng về variable substitution và `env_file` khi được cấu hình.
- Shell script có thể xuất biến môi trường trước khi gọi Java.
- Một thư viện cấu hình riêng có thể nạp dotenv theo thiết kế của dự án.

**Hợp đồng đúng không phải “luôn có file .env” mà là “ứng dụng cần các khóa chuẩn, và phải biết ai chịu trách nhiệm cấp chúng cho tiến trình”.**

Đối với secret production, không nên viết token hoặc mật khẩu vào file `.env` rồi commit lên repository.

## 23. Thử đồng nhất giá trị qua cùng một nhóm environment variables

Muốn kiểm tra ba cách chạy với cùng giá trị, có thể dùng environment variables:

```text
SPRING_PROFILES_ACTIVE=dev
DELIVERY_TIMEOUT=3s
DELIVERY_MAXATTEMPTS=4
DELIVERY_CHANNEL=smoke-test
```

Từ IDE, cấp bốn biến cho Run configuration.

Từ terminal Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=dev \
DELIVERY_TIMEOUT=3s \
DELIVERY_MAXATTEMPTS=4 \
DELIVERY_CHANNEL=smoke-test \
./gradlew bootRun
```

Với JAR:

```bash
SPRING_PROFILES_ACTIVE=dev \
DELIVERY_TIMEOUT=3s \
DELIVERY_MAXATTEMPTS=4 \
DELIVERY_CHANNEL=smoke-test \
java -jar build/libs/config-demo-1.0.0.jar
```

Khi không có nguồn ưu tiên cao hơn ghi đè, kết quả dự kiến:

```text
activeProfiles=dev
endpoint=https://delivery.example.invalid
timeout=PT3S
maxAttempts=4
enabled=true
channel=smoke-test
```

**Không nên dùng `--delivery.timeout=2s` trong một cách chạy nhưng không dùng trong hai cách còn lại** rồi kết luận Spring Boot không đồng nhất vì kết quả khác. Đó là hai bộ đầu vào khác nhau, không phải ba cách chạy tương đương.

## 24. Thử đồng nhất qua Program arguments

Một cách khác là dùng cùng danh sách program arguments:

```text
--spring.profiles.active=dev
--delivery.timeout=3s
--delivery.max-attempts=4
--delivery.channel=smoke-test
```

**IDE:** nhập các token trên trong Program arguments, một dòng hoặc đúng cú pháp IDE hỗ trợ.

**Gradle:**

```bash
./gradlew bootRun \
  --args='--spring.profiles.active=dev --delivery.timeout=3s --delivery.max-attempts=4 --delivery.channel=smoke-test'
```

**JAR:**

```bash
java -jar build/libs/config-demo-1.0.0.jar \
  --spring.profiles.active=dev \
  --delivery.timeout=3s \
  --delivery.max-attempts=4 \
  --delivery.channel=smoke-test
```

Nếu nguồn khác vẫn chứa cùng khóa, các program arguments thông thường có ưu tiên cao hơn Config Data và environment variables trong Spring Boot mặc định.

Tuy nhiên, trong các môi trường kiểm thử tích hợp, có thể còn những property sources dành riêng cho test với quy tắc ưu tiên khác. Không nên suy từ một test với `@SpringBootTest(properties=...)` sang mọi cách chạy production.

## 25. Viết một danh sách kiểm tra khi giá trị khác nhau

Khi có lỗi “IDE nhận timeout=2s nhưng JAR nhận timeout=5s”, không cần vội sửa code. Hãy điều tra:

| Câu hỏi | IDE | bootRun | java -jar |
| --- | --- | --- | --- |
| Main class/artifact có cùng version? | Kiểm tra module | Kiểm tra Gradle module | Kiểm tra tên và thời điểm build JAR |
| Active profiles có giống nhau? | Program args/env/VM | `--args`/env | CLI/env/-D |
| Working directory ở đâu? | Run configuration | Task workingDir | Thư mục shell/service |
| Có external Config Data không? | Tham số/vị trí | Tham số/vị trí | Tham số/vị trí |
| Biến môi trường thực sự tồn tại? | Environment của Run | Child process của Gradle | Shell/service/container |
| Có program arguments ghi đè không? | Program arguments | `--args` | Sau tên JAR |
| Có system property ghi đè không? | VM options | Task JVM | `-D` trước `-jar` |
| File YAML đã được build/package? | Resources của IDE | Resource output | `BOOT-INF/classes` |
| Có validation lỗi không? | Log startup | Log task | Log JVM |
| Có một tiến trình cũ đang chạy? | IDE Run sessions | Gradle task khác | Dịch vụ/JVM khác |

Bước đáng tin cậy là **xác nhận giá trị có hiệu lực trong cùng một tiến trình đang chạy**, thay vì so sánh tệp cấu hình trên đĩa rồi suy luận.

## 26. Quan sát PropertySource một cách an toàn

Khi nghi có nguồn cấu hình ghi đè, có thể liệt kê tên các nguồn từ `ConfigurableEnvironment`.

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class PropertySourceNamePrinter implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public PropertySourceNamePrinter(
            ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (var source : environment.getPropertySources()) {
            System.out.println("propertySource=" + source.getName());
        }
    }
}
```

Đây là **bước chẩn đoán cho môi trường phát triển/test**, không nhất thiết nên bật trong production. Tên nguồn đôi khi chứa đường dẫn hoặc thông tin hạ tầng, nên cũng cần cân nhắc mức độ thông tin được log.

Không in toàn bộ cặp key/value của các PropertySource, bởi chúng có thể chứa secret.

### 26.1. Chỉ tìm giá trị khóa không nhạy cảm

```java
String channel =
        environment.getProperty("delivery.channel");
```

Dùng để quan sát một khóa minh họa không chứa bí mật. Cần phân biệt kết quả đọc trực tiếp từ `Environment` với giá trị đã được binder đưa vào bean trước đó, đặc biệt nếu ứng dụng chủ động thay đổi nguồn cấu hình ở thời gian chạy.

### 26.2. Actuator env endpoint

Nếu ứng dụng có Spring Boot Actuator, endpoint môi trường có thể giúp điều tra nguồn thuộc tính. Tuy nhiên:

- endpoint này không nên mở công khai một cách tùy tiện;
- cần cấu hình quyền truy cập và cơ chế che dữ liệu nhạy cảm;
- cách hiển thị và mức độ thông tin phụ thuộc phiên bản/cấu hình Actuator;
- đừng coi việc có endpoint là lý do bỏ qua kiểm soát bảo mật.

Trong ví dụ học tập đơn giản, một runner in vài giá trị không nhạy cảm đã đủ để so sánh ba cách khởi chạy.

## 27. Validation giúp giữ hợp đồng ngay cả khi nguồn thay đổi

Một ưu điểm của `@ConfigurationProperties` có validation là **không cần viết quy tắc riêng cho từng cách chạy**.

Giả sử CLI ghi:

```bash
java -jar app.jar --delivery.max-attempts=0
```

hoặc IDE Run configuration ghi:

```text
--delivery.max-attempts=0
```

hoặc environment variable:

```text
DELIVERY_MAXATTEMPTS=0
```

Trong cả ba trường hợp, nếu giá trị cuối cùng được liên kết là `0` và provider validation được thiết lập, `@Min(1)` của record đều có thể từ chối.

Tương tự:

```bash
java -jar app.jar --delivery.timeout=not-a-duration
```

sẽ gây lỗi binding/conversion khi Spring không thể chuyển chuỗi thành `Duration` theo quy tắc thông thường.

Hợp đồng bảo vệ ứng dụng khỏi **đầu vào không hợp lệ**, không phụ thuộc nhà cung cấp đầu vào là IDE, Gradle hay tiến trình JAR.

### 27.1. Thiếu cấu hình bắt buộc

Nếu không có `delivery.endpoint` trong bất kỳ nguồn nào, record có `@NotNull URI endpoint` giúp phát hiện giá trị bị thiếu.

Nếu `delivery.channel=""`, `@NotBlank` giúp phát hiện chuỗi rỗng.

Cần hiểu giới hạn:

- `@NotNull` không kiểm tra scheme của URI có phải HTTPS hay không.
- `@Min(1)` trên `int` bảo đảm giá trị ít nhất là 1, nhưng không cho biết một khóa đã được khai báo rõ ràng hay chưa.
- Nếu muốn bắt buộc người dùng **phải cung cấp giá trị số ngay cả khi 0 hợp lệ**, cân nhắc `Integer` kết hợp `@NotNull` thay vì dùng primitive.

## 28. Kiểm thử hợp đồng mà không phụ thuộc IDE hoặc JAR

Nếu một hợp đồng cấu hình có thể được kiểm thử độc lập, bạn sẽ phát hiện lỗi trước khi chuyển cách chạy.

Spring Boot Test cung cấp `ApplicationContextRunner` để tạo context nhỏ với nguồn thuộc tính thử nghiệm.

Giả sử record:

```java
package com.example.configdemo;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotNull Duration timeout,
        @Min(1) int maxAttempts) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class DeliveryPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void acceptsTheContract() {
        runner.withPropertyValues(
                "delivery.timeout=3s",
                "delivery.max-attempts=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            DeliveryProperties properties =
                    context.getBean(DeliveryProperties.class);

            assertThat(properties.timeout())
                    .isEqualTo(Duration.ofSeconds(3));
            assertThat(properties.maxAttempts()).isEqualTo(4);
        });
    }

    @Test
    void rejectsInvalidAttempts() {
        runner.withPropertyValues(
                "delivery.timeout=3s",
                "delivery.max-attempts=0"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void rejectsInvalidDuration() {
        runner.withPropertyValues(
                "delivery.timeout=bad-duration",
                "delivery.max-attempts=4"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class TestConfiguration {
    }
}
```

**Lưu ý:** record này là một **phiên bản tối giản phục vụ riêng test** để minh họa. Trong dự án thật, không nên khai báo đồng thời hai lớp cùng tên và package `DeliveryProperties`. Hãy áp dụng cùng ý tưởng test cho record đầy đủ đã định nghĩa ở đầu bài.

Test `ApplicationContextRunner` kiểm tra **cơ chế binder và validation**, không nhất thiết kiểm tra executable JAR chứa tài nguyên YAML theo đúng cấu trúc hay IDE đã đặt working directory chính xác chưa. Những khía cạnh đó cần kiểm thử tích hợp/bài kiểm tra triển khai.

## 29. Kiểm thử tích hợp với profile cụ thể

Nếu muốn xác nhận cả logic nạp profile-specific Config Data, có thể dùng Spring Boot integration test.

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("dev")
class DeliveryDevProfileTest {

    @Autowired
    private DeliveryProperties properties;

    @Test
    void loadsDevChannel() {
        assertThat(properties.channel())
                .isEqualTo("development");
    }
}
```

Bài test này giả định dự án có `application-dev.yml` và record đầy đủ như phần đầu. Nếu có nguồn cấu hình test đặc biệt ghi đè `delivery.channel`, kỳ vọng cần điều chỉnh theo những nguồn có hiệu lực thực tế.

Đây là cách xác minh rằng “profile dev thực sự làm giá trị phù hợp được nạp” thay vì chỉ kiểm tra binder với một property truyền trực tiếp.

Tuy nhiên, **test profile không bảo đảm JAR production đã được build và triển khai đúng**. Nó kiểm chứng một phần quan trọng của hợp đồng cấu hình ở mức ứng dụng.

## 30. Một smoke test cho executable JAR

Sau khi build:

```bash
./gradlew clean bootJar
```

có thể chạy smoke test với các property không nhạy cảm:

```bash
java -jar build/libs/config-demo-1.0.0.jar \
  --spring.profiles.active=dev \
  --delivery.timeout=3s \
  --delivery.max-attempts=4 \
  --delivery.channel=smoke-test
```

Tùy ứng dụng, smoke test có thể xác nhận:

1. JVM khởi động đúng main class.
2. Executable JAR chứa class/resources cần thiết.
3. Spring Boot nạp được cấu hình.
4. Binder tạo được `DeliveryProperties`.
5. Validation không từ chối dữ liệu hợp lệ.
6. Ứng dụng in hoặc cung cấp thông tin trạng thái phù hợp.
7. Không có lỗi sớm do đường dẫn file hoặc dependency.

Nếu ứng dụng là web server, nên có cách kiểm tra readiness phù hợp và kết thúc tiến trình an toàn sau smoke test. Với ứng dụng chạy lâu dài, lệnh `java -jar` có thể tiếp tục cho đến khi bạn dừng tiến trình; điều này là bình thường.

Không nên dùng smoke test để gọi một endpoint bên ngoài không thuộc môi trường kiểm thử; `example.invalid` được dùng trong bài để tránh hiểu rằng kết nối thật phải thành công.

## 31. Spring Boot DevTools và khác biệt chế độ phát triển

Trong IDE hoặc `bootRun`, một dự án có thể sử dụng Spring Boot DevTools để hỗ trợ restart hoặc những tiện ích phát triển.

Điều này có thể khiến quá trình chạy từ source/classpath có hành vi phụ trợ khác với executable JAR. Ví dụ một lần thay đổi class có thể gây restart trong chế độ phát triển.

Tuy nhiên, khác biệt về DevTools **không thay đổi mục tiêu của hợp đồng cấu hình**:

```text
delivery.timeout -> Duration
delivery.max-attempts -> int >= 1
```

Nếu DevTools gây một lần restart, Spring có thể khởi tạo lại context và bind lại cấu hình trong một số trường hợp. Không nên suy từ đó rằng thay file YAML sẽ tự làm mới một singleton bean của mọi ứng dụng production.

DevTools, refresh scope và cơ chế cấu hình động là những chủ đề riêng; không phải một bộ quy tắc khác về tên khóa dành riêng cho IDE.

## 32. IDE Run không đồng nghĩa với bootRun

Một số IDE có thể cho phép bạn khởi chạy:

1. **Main class trực tiếp** bằng Java launcher của IDE;
2. **Gradle task bootRun** ngay bên trong IDE.

Dù cả hai được kích hoạt bằng nút Run của IDE, chúng có thể dùng **hai cơ chế khởi chạy khác nhau**.

Ví dụ:

- Chạy main class trực tiếp: IDE quyết định classpath, Program arguments, working directory.
- Chạy Gradle bootRun trong IDE: Gradle task quyết định classpath và cách cấp arguments; IDE chủ yếu mở một tiến trình Gradle.

Khi debug khác biệt, hãy kiểm tra bạn đã chọn loại Run configuration nào. Đừng coi mọi thứ được bấm trong giao diện IDE đều là “IDE Java Application run”.

Đối với bài học này, “chạy từ IDE” được hiểu chủ yếu là khởi chạy main class trực tiếp. Nếu IDE thực chất gọi `bootRun`, hãy xem nó như trường hợp Gradle bootRun và kiểm tra tham số ở task.

## 33. Cẩn trọng khi cấu hình JVM của bootRun

Gradle có **JVM chạy Gradle** và task `bootRun` có thể khởi chạy **JVM ứng dụng**. Hai tiến trình không phải lúc nào cũng dùng cùng tập Java system properties.

Một cấu hình:

```groovy
tasks.named('bootRun') {
    jvmArgs '-Ddelivery.timeout=4s'
}
```

hướng tới JVM của ứng dụng do task tạo ra.

Ngược lại, khi chạy:

```bash
./gradlew -Ddelivery.timeout=4s bootRun
```

không nên tự giả định giá trị ấy sẽ được sao chép sang JVM của ứng dụng. Nếu cần, cấu hình truyền system properties một cách tường minh hoặc dùng `--args`.

Khi tài liệu hóa quy trình nhóm, chọn **một cách truyền chính** cho mỗi loại đầu vào để giảm việc cùng khóa xuất hiện ở nhiều nơi. Ví dụ:

- Dùng environment variables cho thông số triển khai.
- Dùng Program arguments để chạy tạm một kịch bản thử.
- Dùng file Config Data cho cấu hình theo profile.
- Chỉ dùng VM/system properties khi có lý do kỹ thuật cụ thể.

Đây là một quy ước thực hành, không phải giới hạn của Spring Boot.

## 34. Đường dẫn tương đối trong IDE, bootRun và JAR

Giả sử ứng dụng có khóa:

```properties
delivery.template-file=./templates/email.txt
```

Nếu mã dùng:

```java
Path.of(properties.templateFile());
```

thì `./templates/email.txt` thường được giải quyết theo working directory của tiến trình.

Với IDE, working directory có thể là project root. Với Gradle bootRun, nó theo task configuration. Với JAR từ thư mục khác, nó theo shell/service.

**Thống nhất tên thuộc tính không bảo đảm đường dẫn tương đối chỉ tới cùng tệp.**

Để tránh lỗi:

1. Dùng đường dẫn tuyệt đối được truyền qua cấu hình nếu file là tài nguyên ngoài ứng dụng.
2. Hoặc xác định working directory giống nhau trong cả ba cách chạy.
3. Nếu file thực sự là resource đóng gói, cân nhắc dùng classpath resource thay vì đường dẫn file system tương đối.
4. Không xây đường dẫn bằng giả định rằng JAR luôn được khởi chạy ở thư mục chứa chính JAR.

Việc chạy:

```bash
java -jar /opt/apps/config-demo.jar
```

không tự đặt working directory thành `/opt/apps`. Nó vẫn là directory của tiến trình shell/service trừ khi trình khởi chạy chủ động thay đổi.

## 35. Cấu hình theo environment nhưng không trùng lặp logic

Giả sử dev muốn timeout 2 giây, production muốn timeout 10 giây.

Cách hợp lý:

```yaml
# application-dev.yml
delivery:
  timeout: 2s
```

```yaml
# application-prod.yml
delivery:
  timeout: 10s
```

và một record:

```java
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(Duration timeout) {
}
```

Không cần:

```java
if (isRunningFromIde()) {
    timeout = Duration.ofSeconds(2);
} else if (isRunningFromJar()) {
    timeout = Duration.ofSeconds(10);
}
```

Vì IDE cũng có thể chạy prod và JAR cũng có thể chạy dev. Môi trường triển khai được mô tả bằng profile và nguồn dữ liệu, không phải bằng công cụ khởi chạy.

**Bằng cách này, ứng dụng đạt một điều quan trọng: cùng artifact có thể dùng ở nhiều môi trường**, miễn là những đầu vào cấu hình thích hợp được cấp.

## 36. Không hardcode secret cho từng cách chạy

Nếu ứng dụng cần token:

```text
delivery.api-token
```

thì không nên:

- commit token production vào `application-prod.yml`;
- để token trong `build.gradle` rồi đóng gói hoặc in log;
- chép token vào Program arguments rồi chia sẻ ảnh màn hình/log chứa toàn bộ command;
- ghi token vào script dùng chung không được bảo vệ;
- log toàn bộ `Environment` hoặc record cấu hình có chứa token.

Thay vào đó, dùng biến môi trường, secret manager hoặc cơ chế quản lý secret đã được tổ chức phê duyệt.

Hợp đồng vẫn có thể là:

```text
delivery.api-token: String, bắt buộc, nhạy cảm
```

nhưng **giá trị thực tế** phải được cấp qua nguồn an toàn tại thời điểm chạy.

Việc dùng cùng hợp đồng cho IDE, bootRun và JAR **không có nghĩa dùng chung một secret** giữa dev và production.

## 37. Các lỗi phổ biến và nguyên nhân

### 37.1. IDE chạy đúng, JAR báo thiếu thuộc tính

Nguyên nhân có thể:

- IDE có environment variable riêng.
- IDE có Program arguments mà lệnh `java -jar` chưa truyền.
- JAR không có tệp `application.yml` hoặc đang dùng bản build cũ.
- Working directory khác khiến file ngoài JAR không được nạp.
- Profile khác nhau.

**Hướng xử lý:** đối chiếu đầu vào tiến trình, artifact, profile, Config Data và giá trị có hiệu lực trước khi sửa record.

### 37.2. bootRun đọc giá trị khác IDE

Nguyên nhân có thể:

- Gradle task được cấp `--args` khác.
- IDE Java Application có VM options hoặc environment variables riêng.
- Gradle JVM và app JVM không nhận cùng system properties.
- Working directory hoặc module khác.

**Hướng xử lý:** kiểm tra loại Run configuration và tập biến/tham số của chính tiến trình ứng dụng.

### 37.3. java -jar không đọc file ngoài cạnh JAR

Nguyên nhân thường là working directory hoặc vị trí Config Data không như dự đoán.

**Hướng xử lý:** dùng đường dẫn tuyệt đối, `spring.config.additional-location` phù hợp và kiểm tra directory location có dấu `/` cuối.

### 37.4. Đặt -D sau tên JAR

```bash
java -jar app.jar -Ddelivery.timeout=4s
```

không truyền `-D...` như JVM option. Sửa thành:

```bash
java -Ddelivery.timeout=4s -jar app.jar
```

hoặc dùng:

```bash
java -jar app.jar --delivery.timeout=4s
```

### 37.5. Truyền --delivery.timeout trực tiếp cho Gradle

```bash
./gradlew bootRun --delivery.timeout=4s
```

không phải cách thông dụng để truyền program arguments cho `bootRun`. Sửa thành:

```bash
./gradlew bootRun --args='--delivery.timeout=4s'
```

### 37.6. File .env có nhưng ứng dụng không nhận

Spring Boot không tự đọc một file `.env` theo mặc định. Cần công cụ/triển khai chủ động xuất các biến môi trường hoặc một nguồn PropertySource/Config Data được hỗ trợ.

### 37.7. Cấu hình dev ghi đè nhưng lại thấy giá trị YAML cơ sở

Profile dev có thể chưa được kích hoạt, tệp dev chưa được nạp, hoặc một nguồn khác có mức ưu tiên cao hơn.

### 37.8. Tên biến môi trường dùng dấu gạch dưới chưa đúng

Ví dụ `DELIVERY_MAX_ATTEMPTS` có thể không tương ứng với khóa chuẩn theo quy tắc environment variable đang dùng. Nên áp dụng dạng chuẩn `DELIVERY_MAXATTEMPTS` và xác nhận kết quả binding.

### 37.9. Không có Bean Validation provider

Record có `@NotNull` hoặc `@Min` nhưng dự án thiếu provider phù hợp. Hãy kiểm tra `spring-boot-starter-validation` và cấu hình build.

### 37.10. In toàn bộ cấu hình để debug

Việc in tất cả thuộc tính có thể làm lộ secret. Thay bằng log những khóa không nhạy cảm, tên nguồn và trạng thái cần thiết.

## 38. Quy trình chẩn đoán có thể lặp lại

Khi kết quả từ ba cách chạy khác nhau, dùng quy trình:

**Bước 1.** Xác nhận cùng source commit, dependency version và artifact.

**Bước 2.** Xác nhận main class và cách khởi chạy: IDE Java Application, Gradle bootRun hay JVM JAR.

**Bước 3.** Xác nhận profile đang hoạt động trong mỗi tiến trình.

**Bước 4.** Ghi lại program arguments, VM options và environment variables **không nhạy cảm**.

**Bước 5.** Xác nhận working directory và các vị trí Config Data bổ sung.

**Bước 6.** Đọc các khóa không nhạy cảm qua `Environment` và bean `@ConfigurationProperties`.

**Bước 7.** Nếu tên khóa đúng nhưng giá trị sai, kiểm tra PropertySource có ưu tiên cao hơn.

**Bước 8.** Nếu bean không tạo được, phân biệt thiếu giá trị, lỗi conversion và lỗi validation.

**Bước 9.** Viết test binding và test profile để tái hiện.

**Bước 10.** Chỉnh cấu hình ở **nguồn gây lỗi**, rồi chạy lại cùng bộ đầu vào để kiểm chứng.

Quy trình này khuyến khích chẩn đoán theo bằng chứng thay vì tạo ba bộ cấu hình riêng biệt cho từng cách khởi chạy.

## 39. Bài tập A — dự đoán giá trị trong ba cách chạy

Cho:

```yaml
# application.yml
delivery:
  timeout: 5s
  max-attempts: 3
```

```yaml
# application-dev.yml
delivery:
  timeout: 2s
  max-attempts: 2
```

Và ba cách:

**IDE Program arguments:**

```text
--spring.profiles.active=dev --delivery.max-attempts=4
```

**bootRun:**

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --delivery.max-attempts=4'
```

**JAR:**

```bash
java -jar app.jar --spring.profiles.active=dev --delivery.max-attempts=4
```

Giả sử không có nguồn nào khác ghi đè.

**Đáp án:** cả ba đều nhận `timeout=2s` và `maxAttempts=4` sau khi binding.

Giải thích: profile dev cung cấp timeout 2 giây; đối số ứng dụng ghi đè max attempts của file dev.

## 40. Bài tập B — phân biệt VM options và Program arguments

Một người đặt trong IDE:

```text
VM options: -Ddelivery.timeout=3s
Program arguments: --delivery.timeout=4s
```

**Câu hỏi:** Spring Boot thông thường sẽ dùng timeout nào nếu không có nguồn ưu tiên cao hơn?

**Đáp án:** `4s` từ command-line property, vì nó thường ưu tiên hơn Java system property khi cùng một khóa.

Điều này minh họa rằng hai ô trong IDE không phải chỉ khác giao diện; chúng tạo hai nguồn dữ liệu khác nhau.

## 41. Bài tập C — giải thích lỗi -D sau JAR

Một người chạy:

```bash
java -jar app.jar -Ddelivery.timeout=3s
```

và thắc mắc vì sao cấu hình không đổi.

**Đáp án:** `-D` sau JAR không còn được JVM xử lý như system property. Sửa thành:

```bash
java -Ddelivery.timeout=3s -jar app.jar
```

Hoặc dùng tham số ứng dụng:

```bash
java -jar app.jar --delivery.timeout=3s
```

## 42. Bài tập D — file ngoài JAR và working directory

Một ứng dụng có tệp `./config/application.yml` nằm ở `/opt/team/config/application.yml`.

- Người A chạy `java -jar /opt/team/app.jar` từ `/opt/team`.
- Người B chạy cùng lệnh từ `/home/user`.

**Câu hỏi:** có thể chắc chắn hai người nạp cùng file ngoài JAR không?

**Không.** `./config` phụ thuộc working directory của từng tiến trình. Nếu muốn dùng đúng file ở `/opt/team/config`, nên chuẩn hóa working directory hoặc truyền một location tuyệt đối phù hợp.

## 43. Bài tập E — không nhầm profile với cách chạy

**Câu hỏi:** phải chăng `bootRun` luôn dùng profile `dev`, còn `java -jar` luôn dùng profile `prod`?

**Không.** Đây là hai cách chạy. Profile được xác định bởi nguồn cấu hình có hiệu lực, chẳng hạn `--spring.profiles.active=...` hoặc `SPRING_PROFILES_ACTIVE`. Cả hai cách chạy đều có thể kích hoạt bất kỳ profile hợp lệ nào nếu được cấu hình.

## 44. Bài tập F — bắt lỗi sớm trong cả ba cách chạy

Record:

```java
@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @Min(1) int maxAttempts) {
}
```

Nếu IDE, bootRun và JAR đều nhận giá trị cuối cùng:

```text
delivery.max-attempts = 0
```

thì khi Spring Boot đăng ký, bind bean và thực thi Bean Validation đúng cách, cả ba đều có thể thất bại lúc khởi động. Đây là hành vi mong muốn của **một hợp đồng cấu hình chung**.

Nếu một cách chạy không thất bại, hãy kiểm tra xem nó có thực sự dùng cùng class, annotation, validation provider và giá trị cuối cùng không.

## 45. Ghi nhớ

- **IDE, bootRun và java -jar là ba cách khởi chạy khác nhau, không phải ba hệ thống cấu hình riêng.**
- Hãy định nghĩa một hợp đồng chung qua `@ConfigurationProperties`: cùng prefix, cùng tên khóa, cùng kiểu Java, cùng default và validation.
- `Spring Environment` hợp nhất các nguồn thuộc tính và binder tạo đối tượng Java; service không cần biết giá trị được cấp bằng công cụ nào.
- **IDE:** Program arguments, VM options, environment variables và working directory là những cấu hình khác nhau.
- **bootRun:** dùng `--args='--key=value'` để truyền program arguments; đừng nhầm JVM của Gradle với JVM ứng dụng.
- **java -jar:** dùng `--key=value` sau JAR hoặc `-Dkey=value` trước `-jar`; build JAR và chạy JAR là hai bước khác nhau.
- **Profile** được kích hoạt bằng thuộc tính như `spring.profiles.active`, không tự suy ra từ IDE/Gradle/JAR.
- **Thứ tự ưu tiên nguồn** giải thích vì sao một giá trị CLI/env có thể ghi đè YAML. Cùng đầu vào hiệu lực phải cho cùng kết quả binding.
- **Working directory** quyết định ý nghĩa của đường dẫn file tương đối; dùng vị trí ngoài JAR rõ ràng và `spring.config.additional-location` khi phù hợp.
- **File .env không tự được Spring Boot nạp** chỉ vì tồn tại; tiến trình phải thực sự nhận các biến hoặc nguồn cấu hình tương ứng.
- **Validation** giúp từ chối dữ liệu thiếu, sai kiểu hoặc vi phạm ràng buộc trong cả ba cách khởi chạy.
- Kiểm thử theo ba lớp: test binder/validation, test profile-specific Config Data, và smoke test executable JAR.
- Khi kết quả khác nhau, kiểm tra **artifact, profile, working directory, arguments, system properties, environment variables và nguồn có hiệu lực** trước khi sửa code.
