# Giới hạn tự làm mới cấu hình của Spring Boot thuần và ranh giới Spring Cloud

## 1. Câu hỏi cốt lõi: sửa cấu hình rồi, tại sao ứng dụng vẫn giữ giá trị cũ?

Spring Boot cung cấp một hệ thống **Externalized Configuration** linh hoạt: ứng dụng có thể đọc `application.yaml`, `application.properties`, file bên ngoài JAR, biến môi trường, system properties, command-line arguments và `configtree:`. Những nguồn này giúp thay đổi cấu hình **mà không phải sửa mã nguồn Java**.

Tuy nhiên, từ câu “cấu hình nằm ngoài ứng dụng” đến câu “đổi giá trị là ứng dụng tự cập nhật ngay” còn một khoảng cách lớn.

Giả sử có:

```yaml
demo:
  banner: "version-one"
  request-timeout: 2s
```

và một service:

```java
@Component
public class BannerService {

    private final String banner;

    public BannerService(@Value("${demo.banner}") String banner) {
        this.banner = banner;
    }

    public String banner() {
        return banner;
    }
}
```

Nếu bạn sửa file thành:

```yaml
demo:
  banner: "version-two"
  request-timeout: 500ms
```

khi process Spring Boot đang chạy, `banner()` **không tự đổi**. Spring Boot core không mặc định theo dõi file để nạp lại Config Data, không tự chạy lại constructor của bean, và cũng không tự làm mới mọi connection pool hoặc HTTP client.

Nhiều công nghệ được gọi là “refresh” thực chất giải quyết **những lớp khác nhau**:

1. Nguồn cấu hình thật được chỉnh sửa.
2. Tiến trình phát hiện và nạp lại giá trị mới.
3. `Environment`/`PropertySource` trong tiến trình phản ánh giá trị mới.
4. Bean phụ thuộc cấu hình được bind lại hoặc tạo lại.
5. Tài nguyên nghiệp vụ đang sống thực sự áp dụng thay đổi.
6. Nhiều instance cùng chuyển sang trạng thái mới một cách an toàn.

**Spring Boot thuần tập trung vào việc nạp và bind cấu hình trong vòng đời khởi động; Spring Cloud bổ sung các cơ chế remote config, refresh, scope và sự kiện để hỗ trợ một số lớp cập nhật runtime.** Nhưng có Spring Cloud cũng không có nghĩa toàn bộ sáu bước luôn tự động, tức thời và nhất quán.

Bài thuộc nhóm **Triển khai cấu hình** trong chủ đề **Spring Boot Externalized Configuration**.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **externalized** với **hot-reload** và **dynamic refresh**.
- Mô tả cách Config Data nạp vào `Environment` khi Spring Boot khởi động.
- So sánh kết quả đọc `Environment.getProperty()`, giá trị đã tiêm qua `@Value`, bean `@ConfigurationProperties` và tài nguyên đã được xây dựng từ cấu hình.
- Giải thích vì sao việc sửa mounted file, ConfigMap, Secret hoặc YAML ngoài JAR không làm ứng dụng tự cập nhật.
- Thực hiện một thử nghiệm Boot-only chứng minh file sửa khi đang chạy không tự được đọc lại.
- Thực hiện một thử nghiệm **thay `PropertySource` trong bộ nhớ** để chứng minh giá trị mới trong `Environment` không đồng nghĩa với bean đã đổi.
- Nắm vai trò của `EnvironmentChangeEvent`, `@RefreshScope`, `/actuator/refresh`, Spring Cloud Config, Consul Watch và Spring Cloud Bus.
- Biết khi nào rolling restart có thể an toàn và đơn giản hơn refresh tại chỗ.
- Hiểu giới hạn của records, constructor binding, static fields, connection pools và secret rotation.
- Thiết kế kiểm thử, rollout, rollback và bảo mật cho các thay đổi cấu hình runtime.

**Phạm vi minh họa:** Java 21, Spring Boot 3.3.x; ví dụ cố định Spring Boot `3.3.13`. Phần Spring Cloud mô tả release train `2023.0.x` tương thích với Boot 3.3 (trong ví dụ dùng `2023.0.6`). Đây là các phiên bản dùng để học, không phải khẳng định chúng luôn là phiên bản mới nhất. Với dự án đang chạy một release train khác, cần đọc tài liệu đúng phiên bản đó.

---

## 2. Hai khái niệm dễ bị đánh đồng: externalized configuration và live refresh

**Externalized configuration** có nghĩa nguồn cấu hình có thể nằm ngoài Java code hoặc ngoài artifact, cho phép từng môi trường cung cấp dữ liệu riêng. Nó giải quyết:

```text
Cùng một binary JAR
       |
       +--> development: application-dev.yaml
       |
       +--> staging:     environment variables / mounted file
       |
       +--> production:  configtree / remote config provider
```

Mục tiêu là **tách code khỏi giá trị triển khai**. Không có điều khoản mặc định rằng process đang chạy sẽ kiểm tra từng file liên tục.

**Live refresh** là một chuỗi hành động có chủ đích:

```text
Giá trị ở nguồn thay đổi
           |
           v
Có cơ chế phát hiện / gọi refresh?
           |
           v
Tải lại các property sources?
           |
           v
Environment biết giá trị mới?
           |
           v
Bean được cập nhật hoặc tạo lại?
           |
           v
Service và tài nguyên đang chạy áp dụng giá trị mới?
```

Thiếu bất kỳ mắt xích nào thì kết quả thực tế có thể là “nguồn đã thay nhưng nghiệp vụ vẫn dùng giá trị cũ”.

Ví dụ: một secret trong Vault được rotate thành công. Điều đó chỉ khẳng định **bản ghi trong Vault hoặc lease** đã thay đổi. Nếu một `DataSource` đã giữ connection dùng credential cũ, pool và connection có thể vẫn cần được tái tạo hoặc có chính sách xử lý riêng.

### 2.1. Bốn câu hỏi chẩn đoán nên hỏi theo thứ tự

1. **Nguồn đã đổi thật chưa?** Kiểm tra file, revision, KV path, secret version hoặc nguồn hiện tại.
2. **Process đã thấy nguồn mới chưa?** `Environment` hoặc nguồn provider có nạp lại không?
3. **Bean nào đang giữ snapshot cũ?** `@Value`, constructor-injected field, record, bean config hoặc một singleton tự copy dữ liệu.
4. **Hạ tầng/runtime nào cần tái tạo?** HTTP client, `DataSource`, thread pool, scheduler, cache, TLS context hoặc subscriber.

Đừng vội thêm `@RefreshScope` trước khi biết đang thiếu bước nào.

## 3. Spring Boot core làm gì với Config Data?

Trong Spring Boot, Config Data API xử lý dữ liệu như:

```text
application.yaml
application.properties
application-{profile}.yaml
spring.config.import
spring.config.location
spring.config.additional-location
file:
classpath:
configtree:
```

Các property được nạp vào hệ thống `Environment` dưới dạng các `PropertySource`. Khi cần, `@ConfigurationProperties` Binder thực hiện chuyển tên, chuyển kiểu, constructor/setter binding và validation để tạo bean.

Sơ đồ thời gian đơn giản:

```text
SpringApplication.run(...)
           |
           v
Tạo và chuẩn bị Environment
           |
           v
Tải Config Data, profile, import locations
           |
           v
ApplicationContext / bean definitions
           |
           v
Tạo và bind @ConfigurationProperties beans
           |
           v
Tiêm @Value, tạo các bean nghiệp vụ
           |
           v
Khởi tạo và mở tài nguyên cần thiết
           |
           v
Ứng dụng sẵn sàng phục vụ
```

Sơ đồ này mang tính khái niệm: không phải mọi bean đều có thứ tự tuyệt đối; lazy initialization và dependency graphs có thể thay đổi thời điểm cụ thể. Điều chắc chắn cần nhớ là **cấu hình thường được nạp và sử dụng trong khởi tạo application context**.

### 3.1. `spring.config.import` không phải file watcher

Ví dụ:

```yaml
spring:
  config:
    import: "optional:file:./runtime-overrides.yaml"
```

Khi khởi động, Config Data xử lý location này và thêm dữ liệu cần thiết. Nếu sau đó sửa file `runtime-overrides.yaml`, Spring Boot core **không mặc định theo dõi file rồi tự đọc và bind lại**.

Tương tự:

```yaml
spring:
  config:
    import: "optional:configtree:/run/config/"
```

chỉ định một nguồn config tree có thể được nạp trong vòng đời Config Data. Không nên hiểu rằng mọi file dưới `/run/config/` đều trở thành biến live được liên tục đồng bộ với các bean.

`optional:` chỉ xử lý trường hợp location có thể vắng mặt theo semantics của loại location. Nó **không** có nghĩa “khi location xuất hiện hoặc thay đổi, process sẽ tự refresh”.

### 3.2. `spring.config.location` và location precedence

`spring.config.location` có thể thay đổi tập location dùng để tìm Config Data, còn `spring.config.additional-location` bổ sung location vào tập mặc định. `spring.config.import` đưa tài liệu import vào quy trình Config Data, với các quy tắc precedence.

Các thuộc tính này ảnh hưởng **đến giá trị được chọn khi tải cấu hình**. Chúng không tự triển khai một cơ chế watch hoặc rebind runtime.

### 3.3. Nguồn động do bạn tự viết vẫn khác Boot core tự động refresh

Spring Framework cho phép `MutablePropertySources`, và thư viện có thể cung cấp `PropertySource` đọc dữ liệu động. Do vậy, một số lời gọi `Environment.getProperty()` **có thể thấy giá trị mới** nếu property source đang được dùng đã thay đổi hoặc được thay thế.

Điều này không mâu thuẫn với việc **Boot Config Data mặc định không tự giám sát file**. Đó là hai vấn đề khác nhau:

```text
Có thể truy vấn giá trị động từ một PropertySource?
    Có, nếu chính PropertySource/ứng dụng làm điều đó.

Boot tự kiểm tra mọi YAML/volume rồi rebind mọi bean?
    Không, không mặc định.
```

## 4. `Environment`, `@Value` và `@ConfigurationProperties` khác nhau về snapshot

Giả sử bean đã được tạo với:

```properties
demo.banner=alpha
```

Sau đó, một cơ chế đặc biệt đưa `demo.banner=beta` vào `Environment`.

### 4.1. Lời gọi `Environment.getProperty()` tại thời điểm truy vấn

```java
String current = environment.getProperty("demo.banner");
```

Nếu `Environment` đang chứa nguồn mới và source mới có precedence thích hợp, lời gọi **mới** có thể trả `beta`.

Nhưng nếu bạn vừa sửa file YAML trên disk mà Boot chưa nạp lại `PropertySource`, lời gọi này vẫn có thể trả `alpha`.

### 4.2. `@Value` là giá trị được resolve tại điểm injection

```java
@Component
public class BannerSnapshot {

    private final String banner;

    public BannerSnapshot(@Value("${demo.banner}") String banner) {
        this.banner = banner;
    }

    public String banner() {
        return banner;
    }
}
```

Với singleton thông thường, constructor chạy khi bean được tạo và `banner` là một snapshot `alpha`. Việc `Environment` có `beta` về sau không tự gọi lại constructor.

Điều tương tự với `@Value` đặt trên field instance: việc tiêm thường xảy ra trong lifecycle của bean, không phải một subscription mặc định theo property.

### 4.3. `@ConfigurationProperties` là một object đã được bind

```java
@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String banner,
        Duration requestTimeout
) {}
```

Record được Binder tạo thành một object có component `final`. Sau khi bind `alpha`, instance đó không tự thay thành `beta` khi nguồn thay đổi.

Mutable JavaBean cũng không tự được setter-binder chạy lại chỉ vì file trên disk thay đổi. Tính mutable có thể làm rebind khả thi khi **một cơ chế riêng** kích hoạt, nhưng không tự tạo cơ chế refresh.

### 4.4. Service có thể giữ bản sao thứ hai

```java
@Service
public class TimeoutPolicy {

    private final Duration timeout;

    public TimeoutPolicy(DemoProperties props) {
        this.timeout = props.requestTimeout();
    }

    public Duration getTimeout() {
        return timeout;
    }
}
```

Ngay cả nếu một bean config nào đó được cập nhật bằng cơ chế custom, `TimeoutPolicy` vẫn giữ `timeout` được copy lúc khởi tạo. Đây là lý do “refresh property source” và “áp dụng vào toàn bộ nghiệp vụ” là hai cam kết khác nhau.

### 4.5. Bảng đối chiếu

| Điểm truy cập | Khi process mới khởi động | Khi `Environment` được cập nhật thủ công | Khi chỉ sửa file YAML ngoài JAR |
| --- | --- | --- | --- |
| `environment.getProperty()` mới | Giá trị được chọn | Có thể thấy giá trị mới | Không mặc định thấy mới |
| `@Value` đã tiêm vào singleton | Snapshot khởi tạo | Không tự tiêm lại | Không tự tiêm lại |
| `@ConfigurationProperties` record | Instance đã bind | Không tự tạo instance mới | Không tự tạo instance mới |
| Mutable `@ConfigurationProperties` POJO | Instance đã bind | Không tự rebind nếu thiếu trigger | Không tự rebind |
| HTTP client/pool được xây từ config | Tài nguyên hoạt động theo cấu hình ban đầu | Không tự tái tạo | Không tự tái tạo |

Những trường hợp có Spring Cloud scope/rebinder/custom lifecycle sẽ khác, nhưng phải mô tả **cơ chế bổ sung cụ thể** đang hoạt động.

## 5. Lab A: ứng dụng Spring Boot thuần có thể chạy được

Mục tiêu lab là chứng minh:

1. Boot đọc file ngoài JAR khi khởi động.
2. `Environment`, `@Value` và config record ban đầu đồng ý về cùng giá trị.
3. Sửa file khi process đang chạy **không** tự nạp lại file.
4. Restart process mới khiến cấu hình được xử lý lại.
5. Không thêm Spring Cloud để tránh lẫn bản chất của Boot core.

Dự án sử dụng Spring Boot web starter chỉ để giữ process sống và cho phép gọi một endpoint đọc các giá trị không nhạy cảm. **Web starter không mang lại refresh.**

### 5.1. Cấu trúc thư mục

```text
boot-refresh-boundary/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── runtime-overrides.yaml             # file local tạo khi thử
└── src/
    ├── main/
    │   ├── java/dev/example/refresh/
    │   │   ├── RefreshBoundaryApplication.java
    │   │   ├── DemoProperties.java
    │   │   ├── BannerSnapshot.java
    │   │   └── StateController.java
    │   └── resources/
    │       └── application.yaml
    └── test/
        └── java/dev/example/refresh/
            ├── BindingTest.java
            └── EnvironmentMutationTest.java
```

Tạo skeleton từ Spring Initializr, chọn Java 21, Gradle và Spring Boot 3.3.x, thêm Web, Actuator và Test. `gradlew`/`gradlew.bat` đến từ Gradle Wrapper do project tạo.

### 5.2. `settings.gradle`

```groovy
rootProject.name = 'boot-refresh-boundary'
```

### 5.3. `build.gradle`

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Không có bất kỳ Spring Cloud dependency nào. `spring-boot-starter-actuator` chỉ cung cấp những endpoint/observability được hỗ trợ và bật cấu hình phù hợp. **Nó không tự bổ sung `/actuator/refresh` của Spring Cloud Context.**

### 5.4. `DemoProperties.java`

```java
package dev.example.refresh;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoProperties(
        String banner,
        Duration requestTimeout
) {}
```

Record không có setter. Đây là một ví dụ rõ về config snapshot được tạo bằng constructor binding.

### 5.5. `BannerSnapshot.java`

```java
package dev.example.refresh;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

@Component
public class BannerSnapshot {

    private final String banner;

    public BannerSnapshot(@Value("${demo.banner}") String banner) {
        this.banner = banner;
    }

    public String banner() {
        return banner;
    }
}
```

Giá trị `banner` được resolve khi bean instance được khởi tạo. Không có listener hay scheduler ở đây.

### 5.6. `RefreshBoundaryApplication.java`

```java
package dev.example.refresh;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class RefreshBoundaryApplication {

    public static void main(String[] args) {
        SpringApplication.run(RefreshBoundaryApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` giúp Boot đăng ký và bind `DemoProperties` theo cơ chế configuration properties. Không cần gắn `@Component` lên record constructor-bound.

### 5.7. `StateController.java`

```java
package dev.example.refresh;

import java.util.Map;

import org.springframework.core.env.Environment;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StateController {

    private final Environment environment;
    private final DemoProperties properties;
    private final BannerSnapshot snapshot;

    public StateController(
            Environment environment,
            DemoProperties properties,
            BannerSnapshot snapshot) {
        this.environment = environment;
        this.properties = properties;
        this.snapshot = snapshot;
    }

    @GetMapping("/state")
    public Map<String, Object> state() {
        return Map.of(
                "environment", environment.getProperty(
                        "demo.banner", "<missing>"),
                "configRecord", properties.banner(),
                "valueInjected", snapshot.banner(),
                "timeout", properties.requestTimeout().toString());
    }
}
```

Endpoint trả bốn giá trị **không nhạy cảm**. Nó không cho phép ghi dữ liệu, không expose toàn bộ `Environment` và không sử dụng secret thật. Cả `DemoProperties` và `BannerSnapshot` đều đã được tạo trước khi endpoint trả về.

**Lưu ý:** đối tượng `Map` cần các value không `null` trong ví dụ. File cấu hình dưới đây luôn cung cấp `demo.banner` và `demo.request-timeout`; trong ứng dụng production, hãy bổ sung validation/fallback cho các trường bắt buộc.

### 5.8. `application.yaml`

```yaml
server:
  address: 127.0.0.1
  port: 8089

spring:
  config:
    import: "optional:file:./runtime-overrides.yaml"

demo:
  banner: "from-base-file"
  request-timeout: 2s

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Chúng ta bind web server vào loopback `127.0.0.1` để lab không mở cho toàn bộ mạng. `runtime-overrides.yaml` là một **Config Data file ngoài classpath**, được import lúc khởi động. Nếu nó chưa tồn tại, `optional:` cho phép chạy với base file trong trường hợp thiếu location được phép bỏ qua.

### 5.9. Chạy cấu hình nền

Từ gốc project, **chưa tạo** `runtime-overrides.yaml`:

macOS/Linux:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Trong terminal khác:

```bash
curl http://127.0.0.1:8089/state
```

PowerShell:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8089/state'
```

Kết quả JSON có nội dung tương đương:

```json
{
  "environment": "from-base-file",
  "configRecord": "from-base-file",
  "valueInjected": "from-base-file",
  "timeout": "PT2S"
}
```

Thứ tự các key của JSON không quan trọng. Điều cần xác nhận là **ba cách nhìn cấu hình** đang có cùng banner tại lúc khởi tạo.

## 6. Lab B: file được import nhưng sửa file không tự refresh

Dừng ứng dụng trước, rồi tạo file:

`runtime-overrides.yaml`:

```yaml
demo:
  banner: "external-v1"
  request-timeout: 500ms
```

Chạy lại ứng dụng. Kỳ vọng `/state` trả:

```json
{
  "environment": "external-v1",
  "configRecord": "external-v1",
  "valueInjected": "external-v1",
  "timeout": "PT0.5S"
}
```

Bây giờ **không dừng ứng dụng**, sửa chính file ngoài JAR thành:

```yaml
demo:
  banner: "external-v2"
  request-timeout: 100ms
```

Gọi lại:

```bash
curl http://127.0.0.1:8089/state
```

Trong mô hình Boot-only và không có công cụ reload riêng, kết quả thông thường vẫn là:

```json
{
  "environment": "external-v1",
  "configRecord": "external-v1",
  "valueInjected": "external-v1",
  "timeout": "PT0.5S"
}
```

Vì sao?

- `application.yaml` và `runtime-overrides.yaml` được đọc khi process khởi động.
- `PropertySource` tương ứng đang giữ dữ liệu đã nạp.
- Không có file watcher mặc định tự tải lại YAML.
- Không có rebind hay bean reconstruction được kích hoạt.
- `Duration` trong record là một object từ lần bind ban đầu.

Khi bạn dừng và **khởi động lại** process, Boot nạp file ngoài một lần nữa; lúc đó kỳ vọng:

```json
{
  "environment": "external-v2",
  "configRecord": "external-v2",
  "valueInjected": "external-v2",
  "timeout": "PT0.1S"
}
```

Đây là sự khác biệt rất quan trọng giữa **có thể thay đổi cấu hình giữa hai lần chạy** và **cập nhật tự động trong một lần chạy**.

### 6.1. Vì sao file import được ưu tiên hơn file nền?

Trong ví dụ, tài liệu import từ `runtime-overrides.yaml` có precedence phù hợp để cung cấp các key `demo.*` và thay giá trị đặt trong tài liệu khai báo import. Nhưng precedence chỉ trả lời **giá trị nào được chọn khi import**.

Dù có precedence cao, file import vẫn không tự trở thành một data stream được watch.

### 6.2. Nếu chỉ sửa file mà IDE tự restart thì sao?

Có thể môi trường phát triển đang sử dụng Spring Boot DevTools hoặc IDE automation. Nếu process thực sự **restart**, nó sẽ đọc file mới. Điều này khác một refresh nội bộ không restart.

Khi làm lab, có thể tắt DevTools hoặc không đưa DevTools vào dependency; file `build.gradle` ở mục trước vốn không có DevTools. Kiểm tra process logs để biết có restart không, tránh kết luận sai rằng Boot core đang hot-reload.

## 7. Lab C: thay `Environment` trong bộ nhớ mà bean vẫn giữ snapshot cũ

Một trường hợp tinh tế hơn: giả sử **bản thân `Environment` đã thay đổi**, nhưng không kích hoạt cơ chế rebinding.

Spring Framework cung cấp `ConfigurableEnvironment` và `MutablePropertySources`. Ta có thể viết một test tạo `MapPropertySource` ưu tiên cao hơn các nguồn cũ. Đây là **thao tác chủ động trong bộ nhớ**, không phải Boot tự theo dõi file.

Tạo `src/test/java/dev/example/refresh/EnvironmentMutationTest.java`:

```java
package dev.example.refresh;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.MutablePropertySources;

@SpringBootTest(properties = {
        "demo.banner=test-original",
        "demo.request-timeout=2s"
})
class EnvironmentMutationTest {

    @Autowired
    ConfigurableEnvironment environment;

    @Autowired
    DemoProperties properties;

    @Autowired
    BannerSnapshot snapshot;

    @Test
    void changingEnvironmentDoesNotRecreateExistingBeans() {
        assertEquals("test-original", properties.banner());
        assertEquals("test-original", snapshot.banner());

        MutablePropertySources sources =
                environment.getPropertySources();

        MapPropertySource manual = new MapPropertySource(
                "lab-manual-override",
                Map.of("demo.banner", "changed-in-memory"));

        sources.addFirst(manual);

        try {
            // Lời gọi Environment mới thấy property source mới.
            assertEquals(
                    "changed-in-memory",
                    environment.getProperty("demo.banner"));

            // Hai bean cũ không tự bị bind/inject lại.
            assertEquals("test-original", properties.banner());
            assertEquals("test-original", snapshot.banner());
        } finally {
            sources.remove("lab-manual-override");
        }
    }
}
```

Chạy:

macOS/Linux:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Kết quả test dự kiến pass, thể hiện:

```text
Environment.getProperty("demo.banner") = changed-in-memory

DemoProperties.banner()                = test-original
BannerSnapshot.banner()                = test-original
```

Đây là **bằng chứng trực tiếp** rằng thay giá trị đang nhìn thấy trong `Environment` không đồng nghĩa với việc mọi bean đang tồn tại tự thay dữ liệu.

### 7.1. Vì sao test cleanup trong `finally`?

`ApplicationContext` trong Spring Boot Test có thể được cache và sử dụng lại bởi các test tương thích. Nếu test để lại một `PropertySource` ưu tiên cao, các test sau có thể đọc nhầm giá trị.

Bởi vậy, sample dùng:

```java
sources.remove("lab-manual-override");
```

trong `finally`. Trong hệ thống nhiều thread, việc thay `MutablePropertySources` đang phục vụ request là một hành động cần kiểm soát concurrency và lifecycle. **Không đưa thao tác debug này thành endpoint ghi cấu hình production.**

### 7.2. Có cần phát một sự kiện sau khi thay `PropertySource`?

Trong Boot-only, việc `MapPropertySource` được thêm vào **không tự phát ra một sự kiện rebind tất cả bean**. Bạn có thể tự xây một hệ thống event/listener hoặc tạo lại bean có chủ đích, nhưng lúc đó đó là một cơ chế custom do ứng dụng quản lý, không phải bảo đảm mặc định của Boot.

Spring Cloud có những event/rebinder riêng. Không nên lấy ví dụ test này rồi thêm lệnh bắn một event bất kỳ mà mong mọi resource được cập nhật an toàn.

### 7.3. Kiểm thử giá trị nền qua test riêng

Tạo `src/test/java/dev/example/refresh/BindingTest.java`:

```java
package dev.example.refresh;

import static org.junit.jupiter.api.Assertions.assertEquals;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "demo.banner=from-test",
        "demo.request-timeout=750ms"
})
class BindingTest {

    @Autowired
    DemoProperties settings;

    @Autowired
    BannerSnapshot snapshot;

    @Test
    void bindsAtContextCreation() {
        assertEquals("from-test", settings.banner());
        assertEquals(Duration.ofMillis(750),
                settings.requestTimeout());
        assertEquals("from-test", snapshot.banner());
    }
}
```

Test này kiểm tra *startup binding*, còn `EnvironmentMutationTest` kiểm tra *không tự cập nhật snapshot sau thay đổi in-memory*. Hai loại test bổ sung cho nhau.

## 8. Docker và Kubernetes: nguồn được cập nhật chưa chắc bean cập nhật

Trong deployment hiện đại, ConfigMap, Secret và mounted files thường tạo cảm giác rằng cấu hình “động” vì chúng ở ngoài container image. Tuy nhiên, cần phân biệt **cách container nhận giá trị**.

### 8.1. Biến môi trường container

Ví dụ Docker Compose:

```yaml
services:
  demo:
    image: example/demo:1.0
    environment:
      DEMO_BANNER: "from-container-env"
```

Giá trị environment được truyền vào **khi process/container được tạo**. Sửa `compose.yaml` hay Kubernetes Deployment manifest không tự thay biến môi trường trong tiến trình JVM đang chạy. Thông thường cần tái tạo container/pod theo deployment workflow.

Spring Boot nhận `DEMO_BANNER` như một property source khi startup. Không có cơ chế để tự biết một file YAML ngoài Kubernetes đã được chỉnh sửa nếu pod/process chưa thay.

### 8.2. ConfigMap volume

Kubernetes có thể cập nhật một số nội dung ConfigMap được mount thành volume trong pod đang chạy, theo cơ chế propagation của kubelet. Tuy nhiên:

```text
ConfigMap object được cập nhật
     |
     v
File trong pod có thể được cập nhật sau độ trễ
     |
     v
Boot Config Data đã nạp file trước đó
     |
     v
Bean cũ vẫn giữ snapshot
```

Việc file mới đến đĩa là **một bước**, không phải kết quả cuối. Khi mount dùng `subPath`, một số hình thức cập nhật volume còn **không được phản ánh** tự động như mount cả directory.

### 8.3. Kubernetes Secret volume

Tương tự, secret được cập nhật/mount lại không bắt buộc làm `@Value`, `@ConfigurationProperties` hay connection pool trong JVM tự đổi.

Với secret:

- Nếu đổi password, cần chắc chắn clients nhận và áp dụng credential mới.
- Nếu secret được rotate, cần xử lý connection/session/tokens tồn tại.
- Nếu secret cấp qua env var thay vì file, process thường cần restart.
- Nếu có operator/CSI driver hoặc agent, cần hiểu **cơ chế và chu kỳ cập nhật của chính integration đó**.

### 8.4. Spring Boot config tree

Giả sử file:

```text
/run/config/demo.banner
```

có nội dung:

```text
hello
```

`application.yaml`:

```yaml
spring:
  config:
    import: "optional:configtree:/run/config/"
```

Boot có thể đọc file thành property `demo.banner` khi khởi động. Nếu kubelet/sidecar thay nội dung file thành `goodbye` khi process vẫn chạy, Boot core **không tự quét lại config tree và bind lại tất cả các bean**.

Thay `configtree:` bằng một import remote cũng không tự bảo đảm live refresh; lúc đó phải xem integration remote làm gì và trigger cập nhật ra sao.

## 9. Spring Boot DevTools không phải cơ chế refresh production

Spring Boot DevTools phục vụ **quá trình phát triển**. Trong những điều kiện được hỗ trợ, thay đổi file trên classpath có thể kích hoạt **automatic restart** của application. DevTools cũng có thể hỗ trợ LiveReload cho giao diện web.

Một số khác biệt:

| Tiêu chí | DevTools restart | Spring Cloud refresh | Rolling restart |
| --- | --- | --- | --- |
| Mục tiêu | Phát triển local | Làm mới một phần config/beans khi đang chạy | Triển khai phiên bản hoặc config mới |
| Process/ApplicationContext | Tạo lại theo cơ chế restart của DevTools | Thường giữ process và làm mới một phần | Tạo process/pod mới |
| Tự giám sát file mount production? | Không phải cam kết | Tùy provider/watch | Do CD/Kubernetes điều phối |
| Có áp dụng cho mọi bean/resource? | Tái khởi tạo app trong giới hạn DevTools | Không | Có thể tạo lại toàn bộ state process |
| Có nên là chiến lược production? | Không | Có thể, khi được thiết kế và bảo vệ | Thường phù hợp cho thay đổi quan trọng |

Nếu đang học về refresh, **đừng lấy quan sát DevTools tự restart khi sửa file để suy ra Boot core có hot rebind**.

## 10. Ranh giới Spring Cloud: nó bổ sung những thành phần nào?

Spring Cloud không phải một “flag” duy nhất bật cập nhật tự động. Tùy dependency, nó cung cấp:

- **Spring Cloud Config Client**: đọc cấu hình từ Config Server.
- **Spring Cloud Context**: các thành phần phục vụ refresh, chẳng hạn `@RefreshScope`, `ContextRefresher`, sự kiện thay đổi Environment và rebinding cho những bean phù hợp.
- **Spring Cloud Actuator refresh endpoint**: một trigger quản trị khi được cài và exposed phù hợp.
- **Spring Cloud Bus**: có thể phát tán thông điệp làm mới giữa nhiều instance qua message broker.
- **Spring Cloud Consul Config**: đọc KV từ Consul; có Config Watch để phát hiện thay đổi theo cấu hình.
- **Spring Cloud Vault**: đọc secrets từ Vault và có các cơ chế lease/lifecycle; secret renewal không đồng nghĩa mọi bean được làm mới an toàn.

Các module này **không phải cùng một sản phẩm** và cũng không nhất thiết được thêm cùng nhau.

Một sơ đồ:

```text
Config Server / Consul KV / Vault / Other
                     |
             provider integration
                     |
                  Config Data
                     |
                 Environment
                     |
              change detection?
                     |
             refresh trigger/event
                     |
         +-----------+------------+
         |                        |
   rebind một số         @RefreshScope targets
@ConfigurationProperties         |
         |                        |
         +-----------+------------+
                     |
               Application beans
                     |
         resource lifecycle vẫn cần xử lý
```

Chữ “một số” quan trọng: không nên kỳ vọng một refresh trigger sẽ thay thế bất kỳ resource nào bằng một instance an toàn, bất kể cấu trúc hay kiểu Java.

## 11. `EnvironmentChangeEvent` là gì?

Trong Spring Cloud Context, `EnvironmentChangeEvent` là một loại event báo rằng có những key của Environment đã thay đổi hoặc có thay đổi cần xử lý theo luồng tích hợp. Các cơ chế Spring Cloud có thể dùng event này để hỗ trợ rebinding và cập nhật một số phần cấu hình.

Nhưng có ba điểm dễ nhầm:

1. **Event không tự là nguồn dữ liệu.** Cần tải hoặc thay những property sources trước khi mong giá trị mới.
2. **Event không tự thay thế mọi bean.** Có những kiểu bean/config không hỗ trợ rebinding theo cách thông thường.
3. **Event không tự tái tạo resource nghiệp vụ.** Một JDBC pool, scheduler, kết nối WebSocket hoặc thư viện client có cache cần chính sách riêng.

Trong lab Boot-only, việc thay một `MapPropertySource` không tự phát Spring Cloud event (vì không thêm Spring Cloud). Khi một provider đưa sự kiện vào hệ thống, vẫn cần biết listener nào thực sự xử lý và bean nào được cập nhật.

### 11.1. Nhận diện được key đổi khác với rebind thành công

Một sự kiện có thể mang danh sách key thay đổi:

```text
demo.banner
demo.request-timeout
```

Nhưng một bean có thể không được tạo lại, một field có thể giữ giá trị cũ hoặc một resources holder đã copy timeout có thể tiếp tục dùng `2s`.

Khi debug, ghi nhận **giá trị ở nguồn**, **giá trị trong Environment**, **giá trị bean** và **giá trị thật của downstream resource** ở từng thời điểm. Chỉ nhìn logs “refresh completed” chưa đủ xác minh nghiệp vụ đã chuyển.

## 12. `@RefreshScope`: làm mới target bean, không mutate mọi field

Spring Cloud Context cung cấp:

```java
import org.springframework.cloud.context.config.annotation.RefreshScope;
```

Một bean được đánh dấu `@RefreshScope` thường được truy cập qua proxy. Khi refresh scope cache bị invalidated, target có thể được tạo lại ở lần truy cập tiếp theo.

Ví dụ trong ứng dụng có Spring Cloud Context:

```java
package dev.example.refresh;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.cloud.context.config.annotation.RefreshScope;
import org.springframework.stereotype.Component;

@Component
@RefreshScope
public class RefreshableBanner {

    private final String banner;

    public RefreshableBanner(
            @Value("${demo.banner}") String banner) {
        this.banner = banner;
    }

    public String currentBanner() {
        return banner;
    }
}
```

Nếu `Environment` đã nạp giá trị mới **và** refresh được kích hoạt theo cơ chế hỗ trợ, target mới của bean có thể được tạo, chạy lại constructor và nhận banner mới.

Cách hiểu đúng:

```text
Trước refresh:
  proxy -> target#1("alpha")

Sau thay Environment + invalidate scope:
  proxy -> target#2("beta") khi cần tạo mới
```

Đây không phải thao tác ghi vào trường `final` của target cũ. Nó là cơ chế **thay target phía sau scope/proxy**.

### 12.1. Vì sao không đặt `@RefreshScope` lên tất cả bean?

Một bean có thể:

- Giữ tài nguyên I/O cần đóng/tạo lại.
- Có nhiều dependency đang giữ reference trực tiếp.
- Có method đang xử lý request dài.
- Giữ lock, state mutable hoặc hàng đợi.
- Dùng external session, token hoặc connection pool.
- Có side effect trong constructor/`@PostConstruct`.
- Có lifecycle do framework khác quản lý.

Refresh một bean giữa request cần xem concurrency, lifecycle và rollback. Một bean đơn giản chứa banner có thể refresh dễ; một pool đang xử lý transaction thì phức tạp hơn nhiều.

### 12.2. `@RefreshScope` không tự tìm giá trị mới

Nếu source không thay hoặc property sources chưa được nạp lại, tạo target mới vẫn có thể lấy **giá trị cũ**. `@RefreshScope` giải quyết phần tạo lại target, không giải quyết mọi provider/watch/precedence.

### 12.3. Đừng xem record constructor-bound là JavaBean có setter

Một `@ConfigurationProperties` record là immutable snapshot. Spring Cloud Context có những giới hạn với record `@ConfigurationProperties` và một số loại object constructor-bound trong luồng refresh/rebinding. Không giả định có thể gắn `@RefreshScope` lên record rồi mọi dependency tự thay giá trị một cách an toàn.

Nếu cần dynamic value, bạn có thể:

- Dùng một `@RefreshScope` service bean hỗ trợ tạo lại target từ `@Value`.
- Tạo một holder/reference có cơ chế atomic swap và validation được thiết kế rõ.
- Dùng source động được đọc tại thời điểm request cho dữ liệu cho phép như vậy.
- Dùng rolling restart khi cần thay nhiều resource cùng lúc.

Chọn một cơ chế có thể kiểm chứng, không dựa trên kiểu Java bất biến như một phép màu.

## 13. `/actuator/refresh`: trigger quản trị, không thuộc Boot Actuator thuần

Một Boot-only application thêm:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

sẽ có Actuator endpoints của Boot theo dependencies/cấu hình. Điều đó **không tự tạo endpoint refresh của Spring Cloud**.

Khi có Spring Cloud Context/refresh endpoint phù hợp, một application có thể expose:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,refresh
```

Rồi một caller được phép kích hoạt:

```bash
curl -X POST http://127.0.0.1:8089/actuator/refresh
```

**Không bật công khai endpoint này trong production.** Nó có thể làm đổi hành vi runtime và cần kiểm soát như thao tác vận hành nhạy cảm: xác thực, phân quyền, mTLS hoặc mạng nội bộ, audit, rate limiting và quy trình phê duyệt.

### 13.1. Endpoint tồn tại không chứng minh đã refresh dữ liệu cần dùng

`POST /actuator/refresh` là **trigger**. Để có tác dụng thật:

- Có provider hoặc mechanism cập nhật `PropertySource`.
- Dữ liệu mới được đọc thành công.
- Những bean cần cập nhật nằm trong cơ chế refresh được hỗ trợ.
- Bean/resource nghiệp vụ không tiếp tục dùng snapshot cũ.
- Cần test giá trị cuối và hành vi của service.

Nếu một request refresh trả kết quả, không nên suy ra tất cả HTTP clients đã được tái cấu hình hay mọi replica đều đồng thời đổi giá trị.

### 13.2. Không nhầm với `/actuator/env`

Actuator `env` dùng để quan sát môi trường theo cấu hình cho phép và có thể có khả năng cập nhật property qua quản trị khi bật những cài đặt đặc biệt. Nó không đồng nghĩa với Config Data import được nạp lại hay các bean bất biến được tạo lại.

Vì `env`/`configprops` có thể liên quan tới secret và cấu trúc hệ thống, **không mở chúng ra Internet** chỉ để debug. Ưu tiên logging allowlist, health checks và tooling có quyền phù hợp.

## 14. Lab D: bổ sung Spring Cloud Config vào ứng dụng

Sau khi xác nhận giới hạn Boot-only, tạo **một nhánh thực hành riêng** từ lab ban đầu. Giữ Java record `DemoProperties`, `BannerSnapshot` và `StateController` để quan sát sự khác nhau khi có provider remote.

### 14.1. Dependency và version

Trong Gradle, dùng Spring Cloud BOM phù hợp với Boot 3.3.x. Ví dụ lab:

```groovy
dependencyManagement {
    imports {
        mavenBom "org.springframework.cloud:spring-cloud-dependencies:2023.0.6"
    }
}
```

Bổ sung vào `dependencies` hiện có:

```groovy
implementation 'org.springframework.cloud:spring-cloud-starter-config'
```

Không tự gán một version riêng cho starter nếu BOM đã quản lý. Nếu dự án sử dụng Boot/Cloud version khác, cần kiểm tra matrix tương thích chính thức trước khi copy BOM này.

### 14.2. Import từ Config Server

Sử dụng:

```yaml
spring:
  application:
    name: demo-client
  config:
    import: "configserver:http://localhost:8888"
```

Config Client tìm thông tin cho application/profile/label trên Config Server. Điều kiện cần:

- Có Spring Cloud Config Client dependency.
- Config Server ở endpoint được cấu hình.
- Có cấu hình phù hợp ở backend của server.
- Client có quyền truy cập và TLS/auth đúng với môi trường.
- App có chiến lược fail-fast/optional theo độ quan trọng của cấu hình.

Đối với thử nghiệm local khi server có thể không chạy, có thể dùng:

```yaml
spring:
  config:
    import: "optional:configserver:http://localhost:8888"
```

`optional:` cho phép ứng dụng xử lý trường hợp server vắng mặt theo cơ chế của Config Client; nó không phải lời hứa rằng mọi lỗi auth, cấu hình sai hoặc binding lỗi đều bị bỏ qua.

### 14.3. Config Server và Config Client là hai tiến trình

Một topology:

```text
Git/native config repository
           |
           v
    Config Server :8888
           |
      HTTP(S) Config
           |
      demo-client app
           |
    Environment + Beans
```

Config Server hỗ trợ phân phối cấu hình, còn Client đưa giá trị vào `Environment`. Khi một file Git thay đổi, thay đổi phải được Config Server nhìn thấy rồi client nhận lại theo cơ chế phù hợp.

Một Git commit mới **không tự tương đương** với việc mọi client instance đang chạy đã áp dụng được giá trị mới.

### 14.4. Một Config Server local dùng native backend

Một project riêng có:

```groovy
implementation 'org.springframework.cloud:spring-cloud-config-server'
```

và main class:

```java
@SpringBootApplication
@EnableConfigServer
public class ConfigServerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigServerApplication.class, args);
    }
}
```

`application.yaml` của server:

```yaml
server:
  port: 8888

spring:
  profiles:
    active: native
  cloud:
    config:
      server:
        native:
          search-locations: "file:./config-repo"
```

Tạo:

```text
config-repo/
  demo-client.yaml
```

với:

```yaml
demo:
  banner: "remote-alpha"
  request-timeout: 800ms
```

Chạy Config Server từ working directory chứa `config-repo`. Kiểm tra:

```bash
curl http://localhost:8888/demo-client/default
```

Cấu hình này dành cho local lab. Production cần auth, TLS, HA và backend được quản lý.

### 14.5. Quan sát Client từ lúc khởi động

Khi client start và đọc remote property, `/state` có thể phản ánh:

```json
{
  "environment": "remote-alpha",
  "configRecord": "remote-alpha",
  "valueInjected": "remote-alpha",
  "timeout": "PT0.8S"
}
```

Giá trị chính xác phụ thuộc các nguồn cạnh tranh như CLI, env và file local. Để test dễ hiểu, **tránh đặt cùng một key ở nhiều nguồn** cho đến khi đã xác minh import thành công.

### 14.6. Sửa remote config khi client đang chạy

Thay server config:

```yaml
demo:
  banner: "remote-beta"
  request-timeout: 100ms
```

Việc Config Server đọc được nội dung mới không tự chứng minh client đã nạp lại. Hãy kiểm tra:

1. GET Config Server endpoint thấy revision/value nào?
2. Client `Environment` đã nạp lại từ server chưa?
3. `@RefreshScope` target đã được invalidated/tạo mới chưa?
4. `DemoProperties` record còn giữ snapshot cũ không?
5. Resource nghiệp vụ có đang dùng timeout mới không?

Đây là cấu trúc đúng để phân biệt **remote distribution** và **runtime refresh**.

## 15. Lab E: dùng `@RefreshScope` để quan sát khác biệt

Trong nhánh có Spring Cloud, thêm `RefreshableBanner` ở mục 12.

Thêm endpoint riêng trong controller:

```java
@GetMapping("/refreshable-banner")
public Map<String, String> refreshableBanner(
        RefreshableBanner current) {
    return Map.of("banner", current.currentBanner());
}
```

Ở ví dụ trên, dependency `RefreshableBanner` được Spring cung cấp theo scope/proxy thích hợp. Cách thực hiện cũng có thể đơn giản là inject `RefreshableBanner` vào constructor của controller rồi gọi method trong handler.

Sau khi thay remote source, dùng trigger refresh được cấu hình và bảo vệ:

```bash
curl -X POST http://127.0.0.1:8089/actuator/refresh
```

Nếu provider đã đưa giá trị mới vào `Environment` và `@RefreshScope` invalidated target, request mới tới `/refreshable-banner` có thể trả `remote-beta`. Đồng thời:

- `BannerSnapshot` singleton không đặt trong refresh scope có thể vẫn trả `remote-alpha`.
- `DemoProperties` record constructor-bound cũ không mặc định tự được thay.
- `StateController` có thể vẫn giữ reference tới bean config record cũ.
- Một pool/client đã tạo từ timeout `800ms` có thể vẫn giữ cấu hình cũ.

Bài học là **refresh có phạm vi**, không phải “tất cả trường trong JVM đồng loạt thay đổi”.

### 15.1. `@RefreshScope` phải đi cùng dependency thực sự hỗ trợ

Không thêm import:

```java
import org.springframework.cloud.context.config.annotation.RefreshScope;
```

vào Boot-only build khi chưa có Spring Cloud Context. Đây không phải annotation của Spring Boot core.

Tương tự, không mong endpoint `/actuator/refresh` hoạt động nếu chỉ thêm `spring-boot-starter-actuator` mà thiếu phần Spring Cloud liên quan.

### 15.2. Bản dùng `@ConfigurationProperties` mutable và rebinder

Spring Cloud Context có cơ chế cho phép rebinding một số bean `@ConfigurationProperties` khi Environment thay đổi. Kết quả phụ thuộc kiểu bean, registration, property sources và version. Một class JavaBean có setters có thể được cập nhật theo cơ chế phù hợp, nhưng cần thử nghiệm thay vì áp dụng một kết luận cho mọi bean.

Với record, constructor binding hoặc một bean đã dùng giá trị config để tạo tài nguyên, **rebind không đồng nghĩa recreate resource**. Cần ranh giới lifecycle rõ.

## 16. Spring Cloud Bus: một trigger tới nhiều instances

Trong một hệ thống có nhiều replicas:

```text
Config Server
      |
   service-1 (3 instances)
   service-2 (5 instances)
```

Gọi `/actuator/refresh` trên **một** instance không tự bảo đảm cả tám instance còn lại cùng refresh.

Spring Cloud Bus có thể dùng message broker để truyền sự kiện đến nhiều instance theo cấu hình. Ví dụ cơ chế sử dụng RabbitMQ hoặc Kafka thông qua starter/transport tương ứng.

Sơ đồ:

```text
Config changed
      |
      v
Bus event / broker
      |
      +--> instance A -> refresh
      +--> instance B -> refresh
      +--> instance C -> refresh
      +--> instance D -> refresh
```

Đây là **fan-out**, không phải một distributed transaction:

- Một instance có thể đang offline.
- Một subscriber có thể xử lý trễ.
- Một refresh có thể fail vì dữ liệu mới không hợp lệ.
- Các request đồng thời có thể gặp instance dùng version khác nhau.
- Broker sẵn sàng không chứng minh bean/resource đã đổi xong.

Muốn trạng thái nhất quán mạnh, cần rollout policy, version gate, readiness và kiểm thử thêm; có những yêu cầu tốt hơn nên dùng rolling restart thay cho refresh hàng loạt.

## 17. Consul Config Watch: theo dõi thay đổi KV không đồng nghĩa đổi mọi bean

Spring Cloud Consul Config có thể đọc KV vào `Environment` qua import như:

```yaml
spring:
  application:
    name: demo-client
  config:
    import: "consul:localhost:8500"
```

Khi có dependency Spring Cloud Consul Config và hạ tầng Consul được cấu hình, một số triển khai có **Config Watch** theo dõi thay đổi KV prefix và phát event refresh cho application context.

Ví dụ quá trình:

```text
Consul KV thay key
      |
      v
Consul Watch phát hiện
      |
      v
Refresh event của Spring Cloud
      |
      v
Property sources / beans được xử lý theo cơ chế hỗ trợ
      |
      v
Ứng dụng dùng giá trị mới? -> phải kiểm chứng
```

Cần phân biệt Consul Config với Consul Discovery. Discovery giúp đăng ký và tìm service; nó không phải công cụ làm mới một cấu hình timeout lấy từ KV.

### 17.1. Khi watch phát event nhưng không thấy thay đổi

Kiểm tra:

- Key nằm đúng prefix/path/profile và format Consul Config đang đọc không?
- Watch có chạy và được phép truy cập Consul KV không?
- Có network/ACL issue không?
- `Environment` có giá trị mới không?
- Bean có được rebind hoặc recreate theo scope không?
- Service có giữ một field final hoặc copy giá trị cũ không?

Không vội bật một polling loop thứ hai trong application để “sửa” watch khi chưa biết mắt xích nào không hoạt động.

### 17.2. Watch có thể tạo áp lực vận hành

Nếu nhiều key bị thay liên tục, những sự kiện refresh không kiểm soát có thể dẫn đến resource recreation hoặc request spike. Hãy có debounce/backoff, điều phối rollout và giới hạn rate khi cần. Việc một config store hỗ trợ watch không có nghĩa mọi tham số đều nên được cập nhật live.

## 18. Vault và secret rotation: giá trị mới chưa đủ

HashiCorp Vault có secret engines, authentication, policies, token/lease lifecycle, audit và khả năng cấp credentials động. Spring Cloud Vault giúp ứng dụng đọc secrets thành các property sources.

Một import ví dụ:

```yaml
spring:
  application:
    name: demo-client
  config:
    import: "vault://"
```

Nhưng hãy tách bốn khái niệm:

1. **Secret source thay đổi:** Vault có version secret mới hoặc phát credential mới.
2. **Client lấy secret mới:** integration/agent/CSI mechanism thực sự đọc giá trị mới.
3. **Bean dùng secret cập nhật:** `Environment`, injected bean hoặc config holder thay đổi.
4. **Resource áp dụng secret mới:** database pool, TLS context, HTTP client, connection đã mở được xử lý theo đúng lifecycle.

Ví dụ một `DataSource` được tạo lúc startup với password cũ. Khi Vault cấp credential mới, pool không tự thay tất cả connection đã mở chỉ vì property source đổi.

### 18.1. Static KV secret và dynamic credentials

- Với KV secret tĩnh, đổi một key trong Vault không đồng nghĩa service tự nạp lại.
- Với dynamic secret có lease, việc renew/revoke có vòng đời riêng của Vault và integration.
- Với database credentials, cần giải quyết connection pool recreation, transaction đang chạy, credential expiry và readiness.

Một kế hoạch rotation tốt có thể yêu cầu tạo resource mới trước, chuyển traffic, đóng resource cũ sau, và chỉ revoke secret cũ khi việc chuyển đã hoàn tất theo chính sách.

### 18.2. Không dùng refresh để che lỗi security

Nếu Vault trả lỗi 403 hoặc thiếu secret bắt buộc, đừng âm thầm dùng password dummy trong production để ứng dụng tiếp tục nhận request. Việc có `optional:` hay một fallback local phải được quyết định theo mức độ quan trọng của dữ liệu.

Không log nguyên secret, không expose toàn bộ `Environment` để debug và không biến `/actuator/refresh` thành endpoint công khai.

## 19. Restart và rolling deployment: tại sao thường dễ kiểm soát hơn?

Nếu cấu hình điều khiển:

- database URL hoặc pool credentials,
- TLS certificate/key,
- thread pool sizing,
- connection timeout của một HTTP client,
- topic/queue subscription,
- feature flags có ảnh hưởng lớn tới schema,
- endpoint discovery hoặc route lớn,
- security policies,

thì việc **recreate ứng dụng hoặc pod** theo một rollout có kiểm soát có thể đơn giản và an toàn hơn cố cập nhật mọi resource tại chỗ.

Một rolling deployment thường có bước:

```text
Config revision N+1 được duyệt
        |
        v
CI/CD áp dụng image/config/pod template mới
        |
        v
Pod mới khởi động và bind config N+1
        |
        v
Readiness check + smoke tests
        |
        v
Chuyển traffic sang pod mới
        |
        v
Thoát pod N theo graceful shutdown
```

Những chi tiết như `maxSurge`, `maxUnavailable`, PodDisruptionBudget và readiness probes tùy hạ tầng; Spring Boot core không tự áp dụng một chiến lược Kubernetes rollout.

**Ưu điểm:** một process mới đi qua đầy đủ lifecycle của Config Data, Binder, validation và resource initialization. Bạn không phải bảo đảm tất cả object cũ có thể cập nhật an toàn tại chỗ.

**Đổi lại:** có chi phí startup, cần đủ capacity và quy trình xử lý rollout thất bại. Không phải mọi thay đổi nhỏ đều cần restart, nhưng restart thường là baseline dễ chứng minh cho cấu hình quan trọng.

### 19.1. ConfigMap thay đổi không chắc kích hoạt rollout

Kubernetes không tự triển khai một pod mới chỉ vì mọi trường hợp ConfigMap data đổi; hành vi phụ thuộc deployment controller/automation. Nhiều team dùng checksum annotation trong pod template hoặc một operator/reloader có chủ đích để trigger rollout khi cấu hình được duyệt.

Điều cần kiểm tra là **pod template có thay đổi hay không**, **pod mới có được tạo hay không** và **app mới có đọc đúng revision không**.

### 19.2. Rollback không chỉ là rollback cấu hình

Khi config N+1 thay đổi protocol hoặc schema ngoài ứng dụng, quay lại N có thể cần xét compatibility. Với secret đã revoke, rollback về credential cũ không nhất thiết hợp lệ. Hãy thiết kế rollback gồm cả dependencies và trạng thái bên ngoài, không chỉ restore YAML.

## 20. Nhất quán giữa nhiều replicas

Một service có ba instance:

```text
app-A -> timeout=1s
app-B -> timeout=2s
app-C -> timeout=2s
```

Trong giai đoạn refresh hoặc rollout, request có thể được xử lý bởi những instance có **khác version cấu hình**. Điều này có thể chấp nhận với banner hiển thị nhưng không chắc an toàn với một security policy hoặc write path.

Cần lựa chọn một mô hình consistency:

- **Eventual consistency:** chấp nhận độ trễ, theo dõi cho tới khi mọi instance hội tụ.
- **Version-gated rollout:** instance mới chỉ nhận traffic khi đúng config revision.
- **Coordinated restart:** triển khai theo nhóm/đợt để giảm mixed versions.
- **Feature flag có hợp đồng tương thích:** hai version được phép cùng tồn tại trong một cửa sổ.
- **Global disable/kill switch:** cần định nghĩa độ trễ và fallback khi nguồn unreachable.

Một hệ thống “đã có Bus” vẫn cần theo dõi **instance nào nhận revision nào và có thực sự áp dụng chưa**.

### 20.1. Gắn revision cho cấu hình

Trong cấu hình thường, có thể bổ sung một khóa không nhạy cảm:

```yaml
demo:
  config-revision: "r42"
```

Ứng dụng chỉ báo `config-revision` ở health/readiness hoặc diagnostics được kiểm soát. Khi thay đổi, bạn kiểm tra từng instance có revision mong đợi.

Không dùng trường revision này như bằng chứng duy nhất rằng mọi resource phụ đã được tái tạo. Nó chỉ là một chỉ báo giúp đối chiếu phiên bản nguồn/bean được bind.

### 20.2. Refresh có thể thất bại một phần

Một provider đã tải được config mới nhưng một bean tạo lại bị lỗi validation hoặc network. Trong giai đoạn đó, hệ thống có thể chứa trạng thái không đồng nhất. Cần trả lời:

- Request mới có tiếp tục nhận không?
- Instance có chuyển `readiness=false` không?
- Có rollback được bean/resource không?
- Có giữ secret cũ sau khi nó đã bị revoke không?
- Có log/metrics phân biệt từng giai đoạn?
- Có cảnh báo khi một instance không hội tụ?

Một chiến lược restart thường đưa được phần lớn lỗi vào **startup failure** trước khi nhận traffic, dù vẫn cần quản lý rollout.

## 21. Điều gì xảy ra với property source có khả năng đọc động?

Một custom `PropertySource` có thể override:

```java
public Object getProperty(String name) {
    return remoteStore.get(name);
}
```

Với cách này, một lời gọi `Environment.getProperty(name)` có thể truy vấn remote store và nhận giá trị mới mỗi lần. Tuy nhiên:

- I/O trên đường request có thể tạo latency và outage dependency.
- Caching và TTL làm dữ liệu không nhất thiết “ngay lập tức”.
- `@Value` đã inject vẫn giữ snapshot.
- `@ConfigurationProperties` đã bind vẫn giữ trạng thái cũ nếu không có rebind.
- Tài nguyên dùng property vẫn không được tạo lại.
- Một key có thể đổi giữa hai lần đọc, làm mất tính nhất quán trong một operation.

**Đọc động không thay thế một cơ chế refresh có điều phối.** Nếu có yêu cầu runtime update thật, cân nhắc snapshot versioned + atomic swap hoặc refresh scope, và quản lý consistency cho một nhóm property liên quan.

### 21.1. Đừng tự viết file watcher chỉ để gọi setter tùy ý

Một phương án dễ gây lỗi:

```text
WatchService thấy YAML đổi
      |
      v
Parse file mới
      |
      v
Gọi setters của từng singleton
```

Nó có thể dẫn đến:

- Một số bean dùng config mới, bean khác dùng cũ.
- Thay một phần trong khi thread khác đang đọc.
- Thứ tự cập nhật không xác định.
- Không có validation toàn bộ config snapshot.
- Resource bên dưới không được tạo lại.
- Race condition giữa watcher và shutdown/restart.
- Khó rollback khi chỉ một bước giữa chuỗi setter thất bại.

Nếu xây custom reconfiguration, hãy định nghĩa object snapshot bất biến, validation trước khi publish, atomic switch, thread safety và resource lifecycle. Không nên biến một tính năng watch đơn giản thành một nguồn bất ổn production.

## 22. Khi nào dùng trực tiếp `Environment.getProperty()` cho dữ liệu động?

Không phải lúc nào đọc config tại mỗi request cũng sai. Nhưng cần phân biệt loại dữ liệu.

Tương đối phù hợp:

- Một cờ hiển thị không nhạy cảm với độ trễ có thể chấp nhận.
- Một lựa chọn chỉ ảnh hưởng đến logic request hiện tại.
- Một config key nhỏ được truy vấn từ một holder có caching/versioning rõ.

Không phù hợp nếu không có thiết kế riêng:

- Credential đang dùng để mở kết nối.
- Endpoint base URL gắn với client đã được pool.
- TLS context/cert đang phục vụ kết nối.
- Thread pool size hoặc connection pool size đang sống.
- Ràng buộc bảo mật yêu cầu toàn bộ request nhìn cùng revision.
- Nhiều key phải thay đổi đồng thời như một transaction.

Một rule thực dụng: **nếu giá trị được dùng để xây resource, refresh phải nói rõ cách xây lại resource đó**. Nếu chỉ dùng để tính toán cho mỗi request, một nguồn đọc động có thể đủ, miễn khả năng consistency và lỗi đã được thiết kế.

## 23. So sánh các lựa chọn kỹ thuật

| Giải pháp | Phát hiện nguồn đổi | Cập nhật Environment | Recreate/rebind bean | Tài nguyên nghiệp vụ | Độ phức tạp |
| --- | --- | --- | --- | --- | --- |
| Boot-only file + restart thủ công | Người vận hành | Khi process mới chạy | Context/bean mới | Resource mới | Thấp |
| Boot-only `configtree:` + rolling restart | Deployment workflow | Khi pod mới chạy | Context/bean mới | Resource mới | Trung bình |
| Boot DevTools | Theo cơ chế dev file changes | Khi app restart | Theo restart | Theo restart | Dev-only |
| Custom dynamic PropertySource | Theo code tự viết | Có thể ngay tại lookup | Không mặc định | Không mặc định | Tùy thiết kế |
| Spring Cloud Config Client | Remote fetch khi startup/refresh | Theo provider/trigger | Một số bean qua Cloud Context | Cần kiểm tra | Trung bình |
| Cloud `@RefreshScope` | Cần refresh trigger | Cần nguồn được reload | Target bean có thể recreate | Không tự tổng quát | Trung bình-cao |
| Spring Cloud Bus | Fan-out sự kiện | Qua logic refresh của instance | Qua cơ chế Cloud | Cần kiểm tra | Cao hơn |
| Consul Config Watch | Theo dõi KV | Qua integration/refresh | Theo hỗ trợ refresh | Cần kiểm tra | Trung bình-cao |
| Vault secret rotation | Secret engine/lease | Tùy client/agent | Không đồng bộ mọi bean mặc định | Rất cần lifecycle riêng | Cao |
| Kubernetes rolling deployment | Controller/automation | Process mới | Bean mới | Resource mới | Rõ ràng nhưng có chi phí |

Không nên chọn công nghệ chỉ từ cột “phát hiện nguồn đổi”. Hãy xem cả **cơ chế áp dụng và trạng thái hậu cập nhật**.

## 24. Debug đúng tầng thay vì đoán

Giả sử người vận hành báo:

> “Tôi sửa ConfigMap rồi nhưng timeout của HTTP client chưa thay.”

Một quy trình chẩn đoán:

**Bước 1 — Xác nhận ConfigMap/Secret revision.** Có đúng namespace, key và deployment không?

**Bước 2 — Xác nhận pod nhận dữ liệu.** Nếu mount file, file trong pod có đổi không? Có dùng `subPath` không? Nếu env var, pod đã được recreate chưa?

**Bước 3 — Xác nhận process mới hay cũ.** Uptime, PID, pod UID, deployment revision và logs startup.

**Bước 4 — Xác nhận Boot có đọc lại file không.** Có restart, reloader hoặc provider integration không?

**Bước 5 — Xác nhận `Environment`.** Một công cụ nội bộ có quyền có thể quan sát key an toàn, không expose secrets.

**Bước 6 — Xác nhận bean.** `@Value`, config record/POJO có nhận giá trị mới không?

**Bước 7 — Xác nhận client resource.** HTTP client, connection pool hay retry policy có giữ object cũ không?

**Bước 8 — Xác nhận mọi replica.** Một pod mới không nói lên toàn bộ Deployment đã hội tụ.

**Bước 9 — Xem lại rollout/restart.** Nếu thuộc nhóm không refresh an toàn, cần tạo resource/process mới theo quy trình.

Mỗi bước có thể đúng riêng lẻ nhưng kết quả cuối vẫn sai nếu bỏ qua một bước.

### 24.1. Log gì khi debug cấu hình?

Nên log:

```text
configRevision=r42
configLoaded=true
activeProfiles=prod
refreshAttempted=true
refreshApplied=false
reason=validation_error
```

Không nên log:

```text
datasourcePassword=<secret>
vaultToken=<token>
allEnvironmentProperties=<all values>
```

Đối với property nhạy cảm, chỉ hiển thị có/không, phiên bản hoặc fingerprint được thiết kế an toàn, không in raw values.

## 25. Sự khác nhau giữa refresh cấu hình và refresh route/service discovery

Một tên service có thể được resolve động qua DNS hoặc service discovery. Cơ chế này không phải `@ConfigurationProperties` refresh.

Ví dụ:

- Kubernetes Service DNS cập nhật endpoints theo pod.
- Consul Discovery thay danh sách service instances theo health.
- Load balancer client có thể cập nhật danh sách target.
- Application settings như `http.connect-timeout` vẫn có thể là snapshot từ startup.

**Discovery** giải quyết “gọi instance nào?”. **Configuration refresh** giải quyết “đọc và áp dụng property mới ra sao?”. **Secret rotation** giải quyết “identity/credential nào còn hợp lệ?”. Ba đường có thể phối hợp nhưng không tương đương.

Không kéo một hệ thống discovery vào chỉ để đổi một timeout, và không mặc định Config Server giải quyết việc tìm endpoints đang sống.

## 26. Trường hợp đặc biệt: refresh và GraalVM native image/AOT

Spring Boot hỗ trợ AOT/native image, nhưng những kỹ thuật reconfiguration động phụ thuộc vào proxy, reflection và thay target runtime cần được xem xét theo tài liệu Spring Cloud của phiên bản cụ thể.

Spring Cloud Context ghi nhận giới hạn hỗ trợ `RefreshScope` trong AOT/native và hướng dẫn tắt refresh trong cấu hình native tương ứng, ví dụ:

```properties
spring.cloud.refresh.enabled=false
```

Không suy ra rằng một project Boot-only chạy native image sẽ có hot reload chỉ vì runtime hoặc Config Data có thể đọc file cấu hình.

Nếu dự án cần cả native executable và cấu hình runtime thay đổi, hãy đánh giá:

- Đọc nguồn động tại request qua API phù hợp.
- Một holder snapshot có cơ chế cập nhật tường minh.
- Restart/rolling deployment.
- Hỗ trợ AOT/native của provider cụ thể.

Đừng dựa vào một annotation Cloud refresh được dùng trong JVM mà chưa có native test.

## 27. Kiến trúc lựa chọn theo mục tiêu

### 27.1. Ứng dụng nhỏ, ít thay đổi cấu hình

```text
Boot Config Data + env/file + CI/CD restart
```

Đây là một lựa chọn mạnh vì đơn giản: mỗi process có một snapshot rõ, startup validation diễn ra đầy đủ.

### 27.2. Microservices cần cấu hình tập trung, có version Git

```text
Spring Cloud Config Server + Config Client
```

Thêm Config Server có quản trị tốt và client dùng `configserver:`. Quyết định refresh/restart **vẫn tách riêng**. Không mặc định Config Server phát thông báo cho mọi client khi Git thay đổi.

### 27.3. Tổ chức đã dùng Consul KV và cần watch

```text
Spring Cloud Consul Config + Watch + refresh policy
```

Phù hợp nếu team hiểu Consul KV contexts, ACL, format và event. Cần xác nhận bean/resource được cập nhật sau sự kiện.

### 27.4. Secret có lease, rotation hoặc quyền truy cập chặt

```text
Vault + Spring Cloud Vault hoặc Vault Agent/CSI
```

Đường đưa secret vào Boot là một phần của bài toán; auth, lease renewal, resource recreation và audit là các phần còn lại.

### 27.5. Kubernetes đã có deployment pipeline mạnh

```text
ConfigMap/Secret/CSI volume
          |
          v
Boot Config Data
          |
          v
Automated rolling restart theo config revision
```

Có thể là lựa chọn đáng tin cậy hơn việc mang thêm một hạ tầng remote chỉ để thay những cấu hình rất hiếm khi đổi. Nếu cần thay đổi liên tục, cân nhắc bổ sung cơ chế dynamic phù hợp với loại config.

## 28. Kiểm thử khi triển khai refresh hoặc rolling restart

Một bộ test nên bao phủ nhiều cấp.

### 28.1. Unit test

Tạo config record trực tiếp, kiểm tra logic service ở một giá trị cụ thể:

```java
DemoProperties props = new DemoProperties(
        "unit", Duration.ofMillis(750));
```

Không cần Spring Cloud hay external provider để xác nhận business logic.

### 28.2. Spring Boot binding test

Dùng `@SpringBootTest(properties = ...)` xác nhận source overrides và conversion tạo ra type đích đúng. Bài lab `BindingTest` đã minh họa.

### 28.3. Không refresh khi chỉ sửa file

Chạy process Boot-only với một file import, thay file và gọi `/state`. Test phải xác nhận process không tự đổi. Sau restart, test xác nhận giá trị mới. Đây là một phép thử **giới hạn hành vi**, không phải dấu hiệu lỗi.

### 28.4. Mô phỏng Environment thay đổi nhưng bean giữ snapshot

`EnvironmentMutationTest` xác minh một thay đổi in-memory không tự gọi lại constructor đã chạy. Đây là một test rất có ích khi ai đó cho rằng `Environment` động sẽ kéo theo mọi field động.

### 28.5. Cloud refresh test

Trong nhánh Cloud riêng:

1. Khởi động Config Server và Client.
2. Xác minh client nhận revision N.
3. Thay remote value lên revision N+1.
4. Kích hoạt refresh qua đường quản trị an toàn.
5. Xác minh `Environment` nhìn thấy N+1.
6. Xác minh `@RefreshScope` bean đủ điều kiện đọc N+1.
7. Xác minh một bean snapshot không được scope vẫn giữ giá trị cũ nếu không có cơ chế rebind riêng.
8. Xác minh một resource runtime được tạo lại nếu yêu cầu.
9. Thử lỗi validation khi remote config mới không hợp lệ.
10. Thử rollback và nhiều instances.

### 28.6. Chaos/failure test

Thử:

- Config Server unavailable lúc client startup.
- Config Server unavailable lúc refresh.
- Consul watch bị mất kết nối.
- Vault trả 401/403 hoặc secret path không tồn tại.
- File volume đang được cập nhật nhưng app chưa restart.
- Một replica nhận revision mới, các replica còn lại vẫn cũ.
- Config mới không convert/validate được.
- HTTP client có connection lâu sống qua lần đổi timeout.
- Secret mới đã có nhưng credential cũ chưa được revoke.
- `/actuator/refresh` bị truy cập trái phép.

Test thành công phải xác nhận **chính sách ứng dụng** (fail-start, retry, fallback, readiness, rollout), không chỉ xác nhận endpoint có phản hồi.

## 29. Những nhầm lẫn phổ biến

### “Externalized Configuration nghĩa là cấu hình động”

Không. Externalized nói về **vị trí và cách cấp giá trị**, không tự nói về watch hay refresh.

### “Sửa `application.yaml` là `Environment.getProperty()` luôn thấy giá trị mới”

Không. Nếu Config Data source giữ snapshot đã đọc, sửa file không làm source tự thay đổi. `Environment` chỉ thấy mới nếu có một cơ chế thực sự cập nhật nguồn đó.

### “Nếu `Environment` mới thì `@Value` cũng mới”

Không với một bean singleton đã được inject. Cần bean recreation hoặc cơ chế refresh phù hợp.

### “Record bất biến nên lỗi là do record”

Record biểu diễn snapshot rõ ràng, không phải nguyên nhân Boot thiếu watcher. POJO mutable cũng không tự rebind khi thiếu trigger. Với record, việc thay object phải được thiết kế thay vì mutation.

### “DevTools đã hỗ trợ refresh production”

Không. DevTools chủ yếu hỗ trợ restart và trải nghiệm local, không phải rollout policy production.

### “Boot Actuator có `/actuator/refresh` sẵn”

Không. Đây là phần Spring Cloud Context/Actuator khi dependency và exposure phù hợp; Boot Actuator thuần không tự có endpoint đó.

### “`@RefreshScope` tự lấy giá trị mới từ Git”

Không. Scope giúp target bean được tạo lại sau trigger; property source phải được tải/cập nhật theo cơ chế provider.

### “Cloud Config Server tự broadcast mỗi commit cho mọi client”

Không mặc định. Cần webhook/Bus/refresh/restart hoặc cơ chế điều phối thích hợp.

### “Consul Watch phát event nên mọi service đang chạy đổi ngay”

Không. Event chỉ là một đoạn trong đường cập nhật; bean và resource cần hỗ trợ.

### “Vault rotate password là connection pool tự đổi password”

Không mặc định. Pool, connection, lease và identity cần lifecycle phù hợp.

### “Đổi ConfigMap sẽ làm mọi pod restart”

Không mặc định cho mọi workflow. Cần controller/automation/pod-template change phù hợp.

### “Một `/actuator/refresh` thành công chứng minh mọi replica đã áp dụng”

Không. Endpoint thường tác động tới một instance; fan-out và consistency là bài toán riêng.

### “Tạo custom file watcher là đủ”

Không. Còn validation, atomicity, bean scope, resource recreation, concurrency, rollback và security.

### “Để bảo mật hơn, chỉ cần dùng `optional:`”

Không. `optional:` chủ yếu là một quyết định về khả năng thiếu location. Secret bắt buộc hoặc security config sai có thể cần fail-fast.

## 30. Bài tập thực hành

### Bài A — Dự đoán snapshot

Ứng dụng Boot-only có:

```properties
demo.banner=one
```

Sau khi khởi động, một singleton đã được tiêm `@Value("${demo.banner}")`. Bạn thay file thành `two` nhưng không restart.

Hãy dự đoán:

1. File trên disk chứa gì?
2. `Environment` có chắc thấy `two` không?
3. Field `@Value` có đổi không?
4. Sau restart thì điều gì xảy ra?

Giải thích từng tầng thay vì trả lời duy nhất “không”.

### Bài B — Thay `MapPropertySource`

Trong một test, bạn chủ động thêm:

```java
new MapPropertySource(
        "override",
        Map.of("demo.banner", "beta"))
```

với precedence cao. Hãy giải thích vì sao lời gọi `Environment.getProperty()` có thể trả `beta` nhưng bean record được bind trước vẫn trả `alpha`.

### Bài C — Nhận diện cơ chế refresh

Phân loại những hành động:

- DevTools tự restart khi classpath đổi.
- Config Server trả cấu hình từ Git.
- Consul Watch phát `RefreshEvent`.
- Cloud `@RefreshScope` tạo target bean mới.
- Spring Cloud Bus truyền event qua broker.
- Kubernetes rolling restart pod.
- Vault cấp credential mới.

Cái nào là *source*, *detection*, *trigger*, *bean recreation* hay *deployment*? Một công nghệ có thể tham gia hơn một bước nhưng không tự bao phủ tất cả.

### Bài D — HTTP client timeout

Một service tạo HTTP client với timeout `2s` trong constructor. Config Server sau đó thay thành `500ms`. Bạn cần những điều kiện nào để các request mới thật sự dùng timeout mới?

Đề xuất hai giải pháp: một dùng refresh/recreate resource có kiểm soát, một dùng rolling deployment.

### Bài E — Secret rotation

Vault cấp password mới, nhưng connection pool vẫn dùng password cũ. Hãy mô tả quá trình phát hiện, tạo pool mới, chuyển traffic và đóng pool cũ. Khi nào có thể revoke credential cũ?

### Bài F — Consul Watch

KV có `demo.banner=beta`, watch đã ghi log sự kiện refresh, nhưng endpoint vẫn trả `alpha`. Hãy liệt kê ít nhất bốn nơi cần kiểm tra để xác định nguyên nhân.

### Bài G — Kubernetes ConfigMap

Một ConfigMap được update và file mount đã đổi. Pod UID không thay đổi và ứng dụng dùng Boot-only Config Data. Vì sao `/state` vẫn trả giá trị cũ? Bạn sẽ thiết kế một rollout trigger thế nào?

### Bài H — Multi-instance consistency

Có 5 replicas, trong đó 2 instance nhận config N+1, 3 instance vẫn dùng N. Với banner hiển thị và security policy, rủi ro khác nhau thế nào? Bạn cần version observation, readiness hay rollout gì?

### Bài I — `/actuator/refresh`

Giả sử một team muốn công khai endpoint refresh để pipeline bên ngoài gọi dễ dàng. Hãy nêu rủi ro, chính sách auth/network phù hợp và những điều cần xác nhận sau request.

### Bài J — Native image

Ứng dụng Spring Boot dùng native image và team muốn thêm `@RefreshScope` theo một hướng dẫn JVM cũ. Bạn sẽ xác minh giới hạn AOT/native của Spring Cloud và lựa chọn gì nếu không hỗ trợ?

### Bài K — Thiết kế bảng phân loại cấu hình

Phân loại:

```text
ui.banner
api.connect-timeout
security.allowed-origins
database.password
scheduling.pool-size
feature.discount-enabled
tls.private-key
```

Với mỗi key, quyết định:

1. Có thể chấp nhận eventual consistency không?
2. Cần validation nào?
3. Bean/resource nào giữ snapshot?
4. Chọn refresh hay restart?
5. Có cần audit và secret handling không?

### Bài L — Viết test về “không tự refresh”

Từ `EnvironmentMutationTest`, thêm một check cho `DemoProperties.requestTimeout()`. Đưa property mới `demo.request-timeout=100ms` vào `MapPropertySource` rồi chứng minh `Environment` đọc raw value mới trong khi `DemoProperties` vẫn giữ `Duration` trước đó.

## 31. Câu hỏi tự kiểm tra

**1.** Externalized Configuration có tự đồng nghĩa với hot-reload không?

**2.** Spring Boot core có tự watch mọi file `application.yaml` và `configtree:` khi process đang chạy không?

**3.** Khi thêm `MapPropertySource` ưu tiên cao, `Environment.getProperty()` có thể trả giá trị mới mà `@Value` đã tiêm vẫn cũ không?

**4.** Vì sao record `@ConfigurationProperties` không tự đổi một component đã bind?

**5.** Một class mutable có setter có tự rebind chỉ vì file ngoài JAR thay đổi không?

**6.** Spring Boot DevTools restart có phải cùng cơ chế với Cloud `@RefreshScope` không?

**7.** Boot Actuator thuần có sẵn `/actuator/refresh` không?

**8.** `@RefreshScope` thay trường `final` trong một target bean cũ hay thường tạo target mới sau invalidation?

**9.** Spring Cloud Config Server có tự đẩy mọi commit Git vào mọi client đang chạy không?

**10.** Consul Config Watch có giải quyết tất cả lifecycle tài nguyên không?

**11.** Vault cấp credential mới có buộc các JDBC connections đang mở tự thay credential không?

**12.** Kubernetes ConfigMap update có tự restart toàn bộ pod không?

**13.** ConfigMap file mount đổi nhưng Boot app vẫn giữ config cũ có thể là hành vi đúng không?

**14.** Vì sao một `/actuator/refresh` trả kết quả không chứng minh cluster nhất quán?

**15.** Trường hợp nào rolling restart thường dễ kiểm chứng hơn dynamic refresh?

**16.** Vì sao custom file watcher không tự đủ để cập nhật mọi singleton?

**17.** Khi có secret mới nhưng một resource đang dùng secret cũ, tầng nào còn thiếu?

**18.** Có nên expose `/actuator/env` và `/actuator/refresh` không xác thực để debug không?

**19.** Với native image, có cần kiểm tra giới hạn Spring Cloud refresh riêng không?

**20.** Một test nào có thể chứng minh thay `Environment` không tự inject lại bean?

### Gợi ý đối chiếu

1. Không, externalized là tách nguồn khỏi code.
2. Không mặc định.
3. Có, vì thời điểm lookup khác thời điểm injection.
4. Record là snapshot instance với component final, và không có trigger tự tái tạo.
5. Không; cần cơ chế refresh/rebind.
6. Không; restart và refresh scope khác nhau.
7. Không; cần phần Spring Cloud tương ứng.
8. Thường tạo target mới qua scope/proxy.
9. Không mặc định; cần trigger/distribution riêng.
10. Không; watch/event chưa chắc recreate resources.
11. Không.
12. Không mặc định trong mọi workflow.
13. Có, vì Boot không tự nạp lại Config Data từ mount.
14. Các replicas và bean/resource có thể ở revision khác nhau.
15. Khi đổi credentials, client/pool, TLS, thread pool hoặc schema quan trọng.
16. Thiếu validation, atomicity, lifecycle, consistency và concurrency handling.
17. Resource/application-layer reconfiguration.
18. Không; endpoint quản trị và dữ liệu cấu hình nhạy cảm.
19. Có, theo version Cloud đang dùng.
20. Test tạo `MapPropertySource` và đối chiếu Environment với bean cũ.

## 32. Checklist triển khai production

Trước khi công bố một tính năng “runtime config refresh”:

- [ ] Xác định rõ nhóm property nào được phép thay động.
- [ ] Biết nguồn nào là owner của từng key, và precedence nào áp dụng.
- [ ] Phân biệt Config Data startup snapshot với provider dynamic source.
- [ ] Có trigger rõ: manual API, watch, bus, operator, deployment controller.
- [ ] Có cơ chế nạp lại property sources và xử lý lỗi mạng.
- [ ] Biết bean nào nằm trong refresh scope hoặc hỗ trợ rebinding.
- [ ] Không giả định mọi record/constructor-bound config tự refresh.
- [ ] Biết tài nguyên nào phải recreate, đóng hoặc di chuyển traffic.
- [ ] Có validation toàn bộ snapshot mới trước khi áp dụng.
- [ ] Có rollback khi chỉ một phần của thay đổi thất bại.
- [ ] Có quy tắc consistency cho các replicas.
- [ ] Theo dõi config revision trên mỗi instance bằng dữ liệu không nhạy cảm.
- [ ] Có rate limiting/debounce để tránh refresh storm.
- [ ] Có retry/backoff và fail-fast theo loại config.
- [ ] Có readiness policy khi secret hoặc resource mới chưa hợp lệ.
- [ ] Actuator refresh/env/configprops có auth, network isolation và audit.
- [ ] Không ghi password/token/raw secret vào log, metrics hoặc response.
- [ ] Có test chứng minh Boot-only không tự refresh file.
- [ ] Có test cho Environment mới nhưng bean cũ.
- [ ] Có integration test remote provider và bean/resource thực.
- [ ] Có chaos test khi source config down hoặc trả dữ liệu sai.
- [ ] Có test rollout/restart với ConfigMap/Secret và trường hợp subPath.
- [ ] Có xác minh AOT/native nếu dùng native image.
- [ ] Có runbook nêu rõ refresh, restart, rollback và quy tắc owner.

## 33. Tổng kết

Một câu cần nhớ:

> **Spring Boot thuần đọc và bind cấu hình rất tốt, nhưng không mặc định tự phát hiện thay đổi của file nguồn rồi làm mới mọi bean và tài nguyên đang chạy. Spring Cloud có thể bổ sung cơ chế tải lại, sự kiện và refresh scope, song mỗi ứng dụng vẫn phải thiết kế phạm vi cập nhật, lifecycle và tính nhất quán.**

Đường đi đầy đủ:

```text
Nguồn cấu hình
(file/YAML/Consul/Config Server/Vault/Secret volume)
                    |
                    v
           Change detected?
                    |
                    v
         PropertySource reloaded?
                    |
                    v
         Environment sees new value?
                    |
                    v
    Bean rebound or recreated correctly?
                    |
                    v
    Resource/client/pool uses new value?
                    |
                    v
    All replicas converged safely?
```

Nếu không cần cập nhật động thực sự, **rolling restart với cấu hình được version, kiểm tra startup và readiness** thường là lựa chọn đơn giản, kiểm soát được và dễ audit. Nếu cần live refresh, hãy coi nó là một tính năng vận hành có hợp đồng rõ, không phải hiệu ứng phụ của việc đặt YAML ngoài JAR.

### Tài liệu tham khảo chính thức

1. [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): `Environment`, `PropertySource`, profile, Config Data, config tree và binding.
2. [Spring Boot 3.3 — Developer Tools](https://docs.spring.io/spring-boot/3.3/reference/using/devtools.html): auto restart trong môi trường phát triển.
3. [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html): Bootstrap, `@RefreshScope`, `EnvironmentChangeEvent`, refresh endpoint và giới hạn.
4. [Spring Cloud Config — Client](https://docs.spring.io/spring-cloud-config/reference/client.html): Config Data import `configserver:`, fail-fast và Config Client.
5. [Spring Cloud Config — Server](https://docs.spring.io/spring-cloud-config/reference/server.html): mô hình Config Server và remote repository.
6. [Spring Cloud Bus](https://docs.spring.io/spring-cloud-bus/reference/): truyền sự kiện tới các service instances.
7. [Spring Cloud Consul — Distributed Configuration](https://docs.spring.io/spring-cloud-consul/reference/config.html): Consul KV, watch và RefreshEvent.
8. [Spring Cloud Vault — Reference](https://docs.spring.io/spring-cloud-vault/reference/): secret backends, property sources và lease lifecycle.
9. [Kubernetes — ConfigMaps](https://kubernetes.io/docs/concepts/configuration/configmap/): env/volume và cập nhật ConfigMap.
10. [Kubernetes — Secrets](https://kubernetes.io/docs/concepts/configuration/secret/): các hình thức sử dụng Secret và ranh giới bảo mật.
11. [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): exposure và bảo mật endpoint quản trị.
