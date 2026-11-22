# Lộ trình học và ứng dụng mẫu để quan sát cấu hình trong Spring Boot

## 1. Bài học này giúp bạn làm được gì?

Trong Spring Boot, cùng một ứng dụng có thể chạy ở máy lập trình viên, môi trường kiểm thử và production mà không cần sửa mã Java cho từng nơi. Giá trị cấu hình được đưa từ bên ngoài vào ứng dụng thông qua file, biến môi trường, tham số khởi động và những nguồn khác. Phần khó không chỉ là khai báo một thuộc tính, mà là trả lời được: **giá trị cuối cùng đến từ đâu, vì sao nó thắng giá trị khác, và đối tượng Java đang nhận giá trị nào?**

Bài này kết hợp **lộ trình học có thứ tự** với **ứng dụng mẫu Config Observer**. Ứng dụng hiển thị một tập nhỏ thuộc tính thử nghiệm, profile đang hoạt động, giá trị sau khi Spring Boot xử lý và tên các nguồn có chứa thuộc tính. Nhờ thay từng nguồn cấu hình rồi chạy lại, bạn nhìn thấy hiệu ứng thực tế thay vì chỉ ghi nhớ lý thuyết.

Sau khi thực hành, bạn có thể:

- Phân biệt nguồn cấu hình, khóa cấu hình, giá trị hiệu lực và đối tượng được binding.
- Dùng `application.yml`, `application-dev.yml`, biến môi trường và đối số dòng lệnh.
- Giải thích được một trường hợp ghi đè cấu hình bằng bằng chứng từ chương trình.
- Dùng `@ConfigurationProperties`, `Environment` và Actuator để quan sát có kiểm soát.
- Viết kiểm thử cho binding và biết cách tìm nguyên nhân khi giá trị không như mong đợi.
- Nhận biết ranh giới bảo mật: không đưa bí mật hay toàn bộ môi trường runtime lên API công khai.

**Nền tảng cho ví dụ:** Java 21, Spring Boot 3.3.x, Gradle, Spring Web, Spring Boot Actuator và Validation. Mã dưới đây sử dụng các API thông dụng của Spring Boot 3.3; có thể thay phiên bản plugin phù hợp với dự án đang học.

## 2. Bản đồ khái niệm trước khi viết mã

Hãy hình dung một đường đi từ cấu hình tới hành vi ứng dụng:

```text
application.yml / application-dev.yml
                   + biến môi trường
                   + Java system properties
                   + đối số dòng lệnh
                         |
                         v
              Spring Environment
        (đọc các PropertySource theo thứ tự)
                         |
             +-----------+------------+
             |                        |
             v                        v
  Environment.getProperty()  @ConfigurationProperties
  (lấy từng khóa)            (binding nhóm khóa vào Java)
             |                        |
             +-----------+------------+
                         |
                         v
                  Hành vi ứng dụng
```

Ba câu hỏi cần tách riêng:

1. **Giá trị được khai báo ở đâu?** Ví dụ `demo.message` có thể tồn tại trong file YAML, biến môi trường và đối số dòng lệnh.
2. **Giá trị hiệu lực là gì?** Khi có nhiều nguồn cùng cung cấp một thuộc tính, nguồn có ưu tiên cao hơn sẽ quyết định kết quả.
3. **Ứng dụng sử dụng giá trị ấy như thế nào?** `Environment` cho phép đọc trực tiếp; `@ConfigurationProperties` binding cả nhóm khóa vào một đối tượng có kiểu rõ ràng.

Một vài quy tắc thực hành đủ để bắt đầu:

- Cấu hình trong `application.yml` là giá trị nền của demo.
- File `application-dev.yml` bổ sung hoặc ghi đè giá trị nền **khi profile `dev` được kích hoạt**.
- Trong các tình huống của bài này, biến môi trường có thể ghi đè giá trị trong file, và đối số dòng lệnh có thể ghi đè cả hai. Thứ tự đầy đủ của Spring Boot còn có nhiều nguồn khác; không nên suy rộng bảng thí nghiệm thành toàn bộ quy tắc ưu tiên.
- `DEMO_MESSAGE` là tên biến môi trường thường dùng cho khóa `demo.message` nhờ cơ chế ánh xạ tên thuộc tính của Spring Boot.
- Thay file cấu hình trên đĩa **không mặc nhiên** làm giá trị trong một tiến trình Spring Boot đang chạy thay đổi. Ở bài này, mỗi lần thay nguồn cấu hình ta khởi động lại ứng dụng để quan sát kết quả rõ ràng.
- Profile là cách chọn nhóm cấu hình theo ngữ cảnh. Profile không phải cơ chế lưu trữ bí mật.

## 3. Lộ trình học đề xuất

| Chặng | Trọng tâm | Thực hành chính | Dấu hiệu đã hiểu |
| --- | --- | --- | --- |
| 1. Giá trị nền | Khóa, giá trị, `application.yml` | Chạy app không chọn profile | Giải thích được ba giá trị mặc định |
| 2. Profile | `spring.profiles.active`, `application-dev.yml` | Chạy profile `dev` | Chỉ ra giá trị nào thay đổi và vì sao |
| 3. Ghi đè từ bên ngoài | Biến môi trường và đối số CLI | Đặt cùng một khóa ở ba nơi | Dự đoán và xác nhận nguồn thắng |
| 4. Binding có kiểu | `@ConfigurationProperties`, validation | Kiểm tra đối tượng `DemoProperties` | Hiểu lỗi khởi động do cấu hình không hợp lệ |
| 5. Quan sát và kiểm thử | `Environment`, `PropertySource`, Actuator, JUnit | Xem báo cáo và chạy test | Phân biệt giá trị hiệu lực với nguồn khai báo |
| 6. Ứng dụng thực tế | Cấu hình ngoài JAR, bảo mật, vận hành | Nạp file bên ngoài, loại bỏ secret khỏi log | Có quy trình chẩn đoán khi cấu hình sai |

Nên hoàn thành chặng 1–3 trước khi đào sâu các nguồn nâng cao như config tree, cấu hình từ nền tảng triển khai hoặc kho quản lý secret. Mỗi chặng chỉ thay **một yếu tố cấu hình** để kết quả dễ đối chiếu.

## 4. Ứng dụng mẫu: Config Observer

### 4.1. Kịch bản

Giả sử một dịch vụ có ba thuộc tính nghiệp vụ dùng để học:

| Khóa | Ý nghĩa | Giá trị nền |
| --- | --- | --- |
| `demo.message` | Thông điệp hiển thị | `hello-from-base` |
| `demo.region` | Nhãn vùng giả lập | `local` |
| `demo.feature-enabled` | Cờ chức năng giả lập | `false` |

Đây đều là **dữ liệu công khai, chỉ dùng cho bài lab**. Endpoint quan sát sẽ không nhận một khóa tùy ý do người dùng nhập, để tránh vô tình tiết lộ mật khẩu, token hay thuộc tính nhạy cảm.

Cây thư mục tối thiểu:

```text
config-observer/
├── settings.gradle
├── build.gradle
├── gradlew / gradlew.bat      # Gradle Wrapper
└── src/
    ├── main/
    │   ├── java/dev/example/configobserver/
    │   │   ├── ConfigObserverApplication.java
    │   │   ├── DemoProperties.java
    │   │   └── ConfigController.java
    │   └── resources/
    │       ├── application.yml
    │       └── application-dev.yml
    └── test/
        └── java/dev/example/configobserver/
            └── DemoPropertiesTest.java
```

Có thể tạo một dự án Spring Boot Gradle mới với các dependency **Spring Web**, **Spring Boot Actuator** và **Validation**, giữ Gradle Wrapper do công cụ tạo dự án sinh ra, rồi đặt nội dung sau vào các file tương ứng.

### 4.2. Thiết lập Gradle

`settings.gradle`:

```groovy
rootProject.name = 'config-observer'
```

`build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Sử dụng Gradle Wrapper đi kèm dự án để tránh lệch phiên bản Gradle giữa các máy. Với repository đã quản lý phiên bản plugin tập trung, giữ thiết lập của repository và chỉ thêm các dependency còn thiếu.

### 4.3. Khởi động Spring Boot và quét cấu hình

`src/main/java/dev/example/configobserver/ConfigObserverApplication.java`:

```java
package dev.example.configobserver;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigObserverApplication {
    public static void main(String[] args) {
        SpringApplication.run(ConfigObserverApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` giúp Spring Boot tìm lớp binding cấu hình trong package hiện tại và các package con. Đây là lý do lớp `DemoProperties` bên dưới được đăng ký thành bean để controller có thể sử dụng.

### 4.4. Khai báo giá trị nền và profile

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: config-observer

server:
  address: 127.0.0.1
  port: 8080

demo:
  message: hello-from-base
  region: local
  feature-enabled: false

management:
  endpoints:
    web:
      exposure:
        include: health,info,env,configprops
  endpoint:
    env:
      show-values: never
    configprops:
      show-values: never
```

`src/main/resources/application-dev.yml`:

```yaml
demo:
  message: hello-from-dev
  region: dev-lab
  feature-enabled: true
```

Điểm cần quan sát:

- Không bật profile nào: ba khóa `demo.*` lấy từ `application.yml`.
- Bật `dev`: ba khóa tương ứng lấy từ `application-dev.yml` nếu không có nguồn ưu tiên cao hơn.
- Không cần lặp lại `server.port`, cấu hình Actuator hoặc các khóa nền khác trong file `application-dev.yml`.
- `server.address: 127.0.0.1` giới hạn máy truy cập vào endpoint lab. Các endpoint quản trị `env` và `configprops` chỉ nên dùng trong môi trường thử nghiệm có kiểm soát; ở production cần giảm exposure và cấu hình bảo vệ thích hợp.

**Lưu ý:** Cấu hình Actuator ở đây cố ý cho phép truy cập tên thuộc tính để học cách chẩn đoán. `show-values: never` yêu cầu Actuator che giá trị trong các endpoint nhạy cảm; không phụ thuộc vào cơ chế che giá trị đó để bảo vệ secret ở các API ứng dụng tự viết.

### 4.5. Binding nhóm thuộc tính thành đối tượng có kiểu

`src/main/java/dev/example/configobserver/DemoProperties.java`:

```java
package dev.example.configobserver;

import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        @NotBlank String message,
        @NotBlank String region,
        boolean featureEnabled
) {}
```

Ở đây:

- Prefix `demo` nối các khóa `demo.message`, `demo.region` và `demo.feature-enabled` vào một đối tượng.
- `feature-enabled` trong YAML được binding vào trường Java `featureEnabled` theo cơ chế relaxed binding.
- `@NotBlank` yêu cầu `message` và `region` có nội dung; nếu một nguồn ưu tiên cao ghi đè bằng giá trị trắng, ứng dụng sẽ báo lỗi validation khi khởi động.
- Kiểu `boolean` giúp ràng buộc ý nghĩa của feature flag. Với hệ thống lớn, có thể dùng các kiểu mạnh hơn, enum, duration, data size và các annotation validation phù hợp.

`@ConfigurationProperties` thích hợp khi nhiều thuộc tính cùng thuộc một nhóm nghiệp vụ. Với một khóa đơn lẻ, bạn cũng có thể thấy `@Value("${demo.message}")` trong code; tuy nhiên ở demo này ta dùng một đối tượng binding để các giá trị liên quan ở cùng một chỗ.

### 4.6. Endpoint quan sát có giới hạn

`src/main/java/dev/example/configobserver/ConfigController.java`:

```java
package dev.example.configobserver;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.PropertySource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/config")
public class ConfigController {

    private static final List<String> OBSERVED_KEYS = List.of(
            "demo.message",
            "demo.region",
            "demo.feature-enabled"
    );

    private final ConfigurableEnvironment environment;
    private final DemoProperties properties;

    public ConfigController(ConfigurableEnvironment environment,
                            DemoProperties properties) {
        this.environment = environment;
        this.properties = properties;
    }

    @GetMapping
    public Snapshot snapshot() {
        Map<String, Trace> traces = new LinkedHashMap<>();
        for (String key : OBSERVED_KEYS) {
            traces.put(key, trace(key));
        }
        return new Snapshot(
                Arrays.asList(environment.getActiveProfiles()),
                properties,
                traces
        );
    }

    private Trace trace(String key) {
        List<String> matchingSources = new ArrayList<>();

        for (PropertySource<?> source : environment.getPropertySources()) {
            // Spring Boot có thể đặt một adapter tổng hợp lên đầu danh sách.
            // Bỏ adapter để dễ nhìn các nguồn cấu hình thực bên dưới.
            if ("configurationProperties".equals(source.getName())) {
                continue;
            }
            if (source.getProperty(key) != null) {
                matchingSources.add(source.getName());
            }
        }

        String firstMatch = matchingSources.isEmpty()
                ? "(không tìm thấy qua tra cứu khóa trực tiếp)"
                : matchingSources.get(0);

        return new Trace(
                environment.getProperty(key),
                firstMatch,
                matchingSources
        );
    }

    public record Snapshot(
            List<String> activeProfiles,
            DemoProperties bound,
            Map<String, Trace> observed
    ) {}

    public record Trace(
            String effectiveValue,
            String firstMatchingSource,
            List<String> matchingSourcesInOrder
    ) {}
}
```

API này cố ý phân biệt **hai loại bằng chứng**:

- `effectiveValue`: kết quả `Environment.getProperty(key)` mà ứng dụng đọc được.
- `firstMatchingSource` và `matchingSourcesInOrder`: tên những `PropertySource` trả về giá trị với khóa đang khảo sát, theo thứ tự duyệt. Đây là công cụ quan sát đơn giản cho các nguồn trong bài lab, **không phải bộ phân tích provenance hoàn chỉnh** cho mọi kiểu alias, import, placeholder, relaxed binding hay nguồn cấu hình tùy biến.

Trường `bound` cho biết đối tượng `@ConfigurationProperties` thực sự nhận được gì. Với ba khóa trong bài lab, kết quả binding nên tương ứng với `effectiveValue` của từng khóa. Nếu sau này mở rộng API, hãy tiếp tục dùng danh sách khóa cho phép và không trả về giá trị nhạy cảm.

Một phản hồi minh họa khi chạy mặc định (tên nguồn có thể thay đổi theo đường dẫn và cách đóng gói):

```json
{
  "activeProfiles": [],
  "bound": {
    "message": "hello-from-base",
    "region": "local",
    "featureEnabled": false
  },
  "observed": {
    "demo.message": {
      "effectiveValue": "hello-from-base",
      "firstMatchingSource": "Config resource 'class path resource [application.yml]' ...",
      "matchingSourcesInOrder": [
        "Config resource 'class path resource [application.yml]' ..."
      ]
    }
  }
}
```

Ví dụ JSON đã rút gọn ở riêng nhánh `observed` để dễ đọc; endpoint thực tế trả về báo cáo cho cả ba khóa. **Tên nguồn trong ví dụ mang tính minh họa**; kiểm tra đầu ra trên chính máy của bạn để biết tên chính xác.

## 5. Chạy các thí nghiệm theo thứ tự

### Thí nghiệm A — chỉ có cấu hình nền

Trên macOS/Linux:

```bash
./gradlew bootRun
curl -s http://127.0.0.1:8080/api/config
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
Invoke-RestMethod http://127.0.0.1:8080/api/config
```

Dùng terminal thứ hai để gọi HTTP khi ứng dụng còn chạy. Kết quả cần quan sát:

```text
activeProfiles       = []
demo.message         = hello-from-base
demo.region          = local
demo.feature-enabled = false
```

`activeProfiles=[]` nghĩa là không có profile kích hoạt rõ ràng; không có nghĩa ứng dụng không có cấu hình. `application.yml` vẫn được nạp.

### Thí nghiệm B — kích hoạt profile `dev`

Dừng tiến trình trước, rồi chạy:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
curl -s http://127.0.0.1:8080/api/config
```

Hoặc PowerShell:

```powershell
.\gradlew.bat bootRun --args='--spring.profiles.active=dev'
Invoke-RestMethod http://127.0.0.1:8080/api/config
```

Kỳ vọng:

```text
activeProfiles       = [dev]
demo.message         = hello-from-dev
demo.region          = dev-lab
demo.feature-enabled = true
```

Hãy nhìn `matchingSourcesInOrder` của `demo.message`: thường bạn sẽ thấy cả cấu hình thuộc profile và cấu hình nền; trong trường hợp không có nguồn ưu tiên cao hơn, file profile quyết định giá trị hiệu lực.

### Thí nghiệm C — biến môi trường ghi đè file

Dừng app. Trên macOS/Linux:

```bash
DEMO_MESSAGE=hello-from-env ./gradlew bootRun --args='--spring.profiles.active=dev'
```

Trên PowerShell:

```powershell
$env:DEMO_MESSAGE = 'hello-from-env'
.\gradlew.bat bootRun --args='--spring.profiles.active=dev'
```

Gọi lại `/api/config`, sau đó đối chiếu:

```text
demo.message = hello-from-env   # đến từ môi trường
demo.region  = dev-lab          # vẫn đến từ file profile
```

Chỉ thay một khóa nên kết quả chứng minh được nguồn bên ngoài đã ghi đè đúng khóa đó mà không làm mất các giá trị còn lại. Sau khi thử nghiệm trên PowerShell, xóa biến khỏi session để tránh ảnh hưởng các lần chạy sau:

```powershell
Remove-Item Env:DEMO_MESSAGE
```

### Thí nghiệm D — đối số dòng lệnh ghi đè biến môi trường

Trên macOS/Linux:

```bash
DEMO_MESSAGE=hello-from-env ./gradlew bootRun \
  --args='--spring.profiles.active=dev --demo.message=hello-from-cli'
```

Trên PowerShell:

```powershell
$env:DEMO_MESSAGE = 'hello-from-env'
.\gradlew.bat bootRun --args='--spring.profiles.active=dev --demo.message=hello-from-cli'
Remove-Item Env:DEMO_MESSAGE
```

Kỳ vọng giá trị hiệu lực là `hello-from-cli`. Dù YAML, profile và biến môi trường đều khai báo `demo.message`, đối số CLI được ưu tiên trong thí nghiệm này. Phân biệt `--demo.message=...` (đối số ứng dụng Spring Boot) với tùy chọn của chính Gradle; `bootRun --args='...'` chuyển phần bên trong `--args` cho ứng dụng.

### Thí nghiệm E — cấu hình từ file nằm ngoài JAR

Tạo file `external/application.yml` bên cạnh `build.gradle`:

```yaml
demo:
  message: hello-from-external-file
  region: external-lab
```

Chạy:

```bash
./gradlew bootRun --args='--spring.config.additional-location=optional:file:./external/'
```

PowerShell dùng lệnh tương tự với `.\gradlew.bat`. Kiểm tra `/api/config` sẽ thấy các giá trị trong file bổ sung được nạp, trong khi `feature-enabled` vẫn giữ giá trị nền nếu file ngoài không khai báo.

`spring.config.additional-location` là thuộc tính được xử lý sớm trong quá trình tải config data. Cú pháp `optional:` cho phép app tiếp tục khởi động nếu đường dẫn không tồn tại; bỏ `optional:` khi muốn một file bắt buộc phải có. Với môi trường triển khai thực tế, đường dẫn tương đối phụ thuộc working directory của tiến trình, nên ưu tiên đường dẫn rõ ràng hoặc kiểm soát thư mục khởi động.

**Thận trọng về thứ tự:** Trong demo này chỉ có một thư mục bổ sung, không có import hoặc nhóm location phức tạp. Nếu dùng nhiều location và nhiều profile, cần xem quy tắc config data cụ thể trước khi dự đoán nguồn thắng.

### Thí nghiệm F — cấu hình không hợp lệ

Dừng app và cố tình truyền giá trị rỗng:

```bash
./gradlew bootRun --args='--demo.message='
```

`@NotBlank` trên `DemoProperties.message` khiến binding/validation không chấp nhận giá trị rỗng, nên ứng dụng không khởi động bình thường. Đây là hành vi mong muốn: phát hiện cấu hình thiếu hoặc sai ngay lúc khởi động dễ xử lý hơn một lỗi nghiệp vụ xuất hiện muộn.

Để khôi phục, bỏ đối số rỗng rồi chạy lại. Không để lại biến môi trường hoặc đối số thử nghiệm trong cấu hình chạy hằng ngày.

## 6. Quan sát bằng Spring Boot Actuator

Nếu đã bật Actuator theo `application.yml`, có thể gọi:

```bash
curl -s http://127.0.0.1:8080/actuator/health
curl -s http://127.0.0.1:8080/actuator/env/demo.message
curl -s http://127.0.0.1:8080/actuator/configprops
```

Ý nghĩa từng endpoint:

- `/actuator/health`: cho biết ứng dụng đang chạy, không chứng minh một giá trị cấu hình cụ thể.
- `/actuator/env/demo.message`: hỗ trợ tra cứu thuộc tính và nguồn của thuộc tính trong `Environment`. Giá trị có thể bị che theo cấu hình endpoint.
- `/actuator/configprops`: giúp quan sát các bean dùng `@ConfigurationProperties`, giá trị binding thường được che để tránh lộ dữ liệu.

Khi so sánh, endpoint `/api/config` của bài lab cho bạn **giá trị hiển thị** vì chỉ chứa ba thuộc tính giả lập đã cho phép; Actuator có thể cho **thông tin cấu trúc** nhiều hơn nhưng giới hạn phần giá trị. Việc hai endpoint hiển thị khác nhau không tự động có nghĩa binding sai.

Không bật truy cập công khai cho `env` hay `configprops` trên hệ thống thực chỉ để debug. Khi cần chẩn đoán production, sử dụng cơ chế xác thực, phân quyền, mạng quản trị và chính sách che giá trị phù hợp. Không ghi nguyên `Environment`, tất cả environment variables, hoặc dữ liệu cấu hình chứa mật khẩu vào log.

## 7. Kiểm thử binding có thể lặp lại

`src/test/java/dev/example/configobserver/DemoPropertiesTest.java`:

```java
package dev.example.configobserver;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.message=hello-from-test",
        "demo.region=test-lab",
        "demo.feature-enabled=true"
})
class DemoPropertiesTest {

    @Autowired
    private DemoProperties properties;

    @Test
    void bindsTestProperties() {
        assertEquals("hello-from-test", properties.message());
        assertEquals("test-lab", properties.region());
        assertTrue(properties.featureEnabled());
    }
}
```

Chạy:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

Ở đây test tự khai báo input cấu hình, nên kết quả không phụ thuộc người chạy có đang bật profile `dev` trong một terminal khác hay không. Với các test phức tạp hơn, có thể dùng `@ActiveProfiles("dev")`, `@TestPropertySource` hoặc property động cho hệ thống phụ trợ; hãy chọn cách phản ánh đúng điều kiện mình muốn kiểm tra.

Nếu muốn kiểm tra *ưu tiên* giữa hai nguồn trong một bài test, hãy viết kỳ vọng rõ ràng về cả hai nguồn và chỉ thay một biến mỗi lần. Đừng lấy việc test pass làm bằng chứng rằng mọi kiểu cấu hình của Spring Boot đều dùng một thứ tự đơn giản giống nhau.

## 8. Bảng ghi chép thí nghiệm

Điền kết quả thực tế từ endpoint thay vì chỉ sao chép cột kỳ vọng:

| Lần chạy | Nguồn được thêm hoặc thay | `demo.message` dự đoán | Giá trị thực tế | Nguồn khớp đầu tiên |
| --- | --- | --- | --- | --- |
| A | Chỉ `application.yml` | `hello-from-base` | Tự điền | Tự điền |
| B | Profile `dev` | `hello-from-dev` | Tự điền | Tự điền |
| C | `DEMO_MESSAGE=hello-from-env` và `dev` | `hello-from-env` | Tự điền | Tự điền |
| D | Thêm `--demo.message=hello-from-cli` | `hello-from-cli` | Tự điền | Tự điền |
| E | File `external/application.yml` | `hello-from-external-file` | Tự điền | Tự điền |
| F | `--demo.message=` | Khởi động thất bại do validation | Tự điền | Không áp dụng |

Sau mỗi lần chạy, hãy tự trả lời: “Ứng dụng đã đọc nguồn nào?”, “Có nguồn nào cùng khai báo khóa này?”, “Giá trị trong `bound` có khớp với giá trị hiệu lực không?”, “Lần chạy này đã khởi động tiến trình mới hay chưa?”.

## 9. Sự cố thường gặp và cách xác định nguyên nhân

**Đã sửa `application-dev.yml` nhưng vẫn thấy `hello-from-base`.** Kiểm tra `activeProfiles` có `dev` hay không, tên file đúng `application-dev.yml`, file nằm trong `src/main/resources`, và app đã được khởi động lại. Nếu `activeProfiles` đúng mà giá trị không đúng, xem có biến môi trường hoặc đối số CLI đang ghi đè.

**Biến môi trường có giá trị nhưng không tác động tới ứng dụng.** Kiểm tra biến được đặt trong đúng môi trường của *tiến trình chạy Java*, không chỉ một terminal khác. Dùng tên phù hợp (`DEMO_MESSAGE`, `DEMO_FEATURE_ENABLED`) và nhớ rằng các shell/session có phạm vi biến môi trường riêng. Với Gradle `bootRun`, biến môi trường của tiến trình Gradle thường được truyền cho ứng dụng con.

**`DemoProperties` không được inject hoặc có giá trị bất ngờ.** Kiểm tra package, `@ConfigurationPropertiesScan`, prefix `demo`, tên khóa, kiểu dữ liệu và annotation validation. `Environment.getProperty()` và relaxed binding vào `@ConfigurationProperties` không phải luôn tương đương tuyệt đối với những khóa tùy biến; kiểm tra key, dạng tên và nguồn thực tế khi mở rộng demo.

**Endpoint quan sát hiển thị tên nguồn lạ.** Spring Boot có thể thêm nguồn tổng hợp, cấu hình từ test, file đã import hoặc nguồn do thư viện cung cấp. Tên của `PropertySource` là chi tiết chẩn đoán, có thể khác theo cách chạy. Hãy dựa trước hết vào giá trị hiệu lực, active profile và các nguồn được xác nhận có khai báo khóa.

**Giá trị trong Actuator bị che.** Đây có thể là chính sách bảo vệ đúng chủ đích của endpoint, đặc biệt khi `show-values: never`. Đừng bỏ bảo vệ chỉ để lấy giá trị từ thuộc tính nhạy cảm. Với bài lab, ba khóa giả lập đã đủ để quan sát thứ tự ưu tiên.

**Một file ngoài không được nạp.** Kiểm tra đường dẫn, working directory, định dạng YAML, dấu `file:` và dấu `/` cuối thư mục trong `spring.config.additional-location`. Nếu muốn thiếu file là lỗi khởi động, không dùng `optional:`.

**Đã thay file mà app đang chạy không đổi.** Kiểm tra bạn có thực sự restart không. Externalized configuration mặc định được xử lý khi ứng dụng khởi động. Cơ chế refresh động, Spring Cloud Config hay tính năng hot reload có vòng đời và điều kiện riêng, không được giả định trong ứng dụng này.

## 10. Mở rộng sau khi hoàn thành bài cơ bản

Khi cả sáu chặng đã chạy được, có thể nâng bài lab theo thứ tự:

1. **Placeholder và mặc định:** thêm `demo.banner: "${demo.message:hello}"`, rồi quan sát giá trị khi khóa được cung cấp hoặc bị thiếu. Lưu ý placeholder có thể khiến việc giải thích “nguồn gốc giá trị cuối” tinh tế hơn việc duyệt property source trực tiếp.
2. **Nhóm cấu hình mới:** thêm `demo.timeout` dạng `Duration` và `demo.max-payload` dạng `DataSize`, binding có kiểu và validation để làm rõ lợi ích của `@ConfigurationProperties`.
3. **Cấu hình theo môi trường:** thêm profile `test` với giá trị giả lập và kiểm thử chọn profile. Không đưa thông tin đăng nhập thực vào file commit.
4. **Kiểm tra nguồn nâng cao:** so sánh `spring.config.import`, config tree hoặc một hệ thống cung cấp cấu hình từ bên ngoài. Mỗi loại nguồn cần đánh giá cách nạp, độ ưu tiên, lỗi khi vắng mặt và chính sách bảo mật.
5. **Quan sát ở production:** thay API demo bằng logging có chọn lọc những cờ không nhạy cảm và trang chẩn đoán đã xác thực; không xuất mọi khóa cấu hình ra ngoài.

Những câu hỏi tự kiểm tra:

- Nếu `demo.message` được khai báo ở file nền, file `dev`, biến môi trường và CLI, trường hợp nào đang có ưu tiên cao nhất trong thí nghiệm D?
- Vì sao `activeProfiles=[]` vẫn có giá trị trong `demo.message`?
- Vì sao `DemoProperties` tốt hơn một nhóm lớn biến `@Value` rời rạc khi cấu hình ngày càng nhiều?
- Vì sao một báo cáo `PropertySource` đơn giản cần ghi rõ giới hạn khi có relaxed binding hoặc placeholder?
- Khi thay file YAML trong khi ứng dụng vẫn chạy, cần kiểm tra điều gì trước khi kết luận hệ thống đã nhận cấu hình mới?
- Một endpoint hiển thị tất cả environment variables có thể gây hậu quả gì?

## 11. Điều cần giữ khi áp dụng vào dự án thật

Ứng dụng mẫu đã chỉ ra đường đi: **nguồn cấu hình → Spring Environment → binding hoặc truy xuất → hành vi ứng dụng**. Khi chuyển từ lab sang hệ thống thật, hãy ưu tiên cấu hình có kiểu và được validation, khai báo giá trị nền hợp lý, tổ chức profile rõ ràng, quản lý secret bằng cơ chế được thiết kế cho secret, kiểm soát endpoint quản trị và viết test cho các cấu hình quyết định hành vi quan trọng.

Mỗi khi gặp một giá trị “không hiểu lấy từ đâu”, quy trình chẩn đoán hữu ích là: xác định khóa chuẩn, xác định profile, liệt kê những nguồn có thể cấp khóa đó, kiểm tra giá trị hiệu lực, đối chiếu kết quả binding và khởi động lại trong điều kiện có thể tái lập. Đó là năng lực cốt lõi mà lộ trình và Config Observer muốn rèn luyện.