# Kiểm tra metadata sinh ra trong JAR và hỗ trợ hoàn thành cấu hình của IDE

**Chủ đề:** Spring Boot Auto Configuration  
**Nhóm kiến thức:** Metadata  
**Mục tiêu:** Tạo configuration metadata cho một thư viện/starter Spring Boot, xác minh metadata đã được sinh khi compile và đóng gói vào JAR, rồi kiểm tra IDE có thể gợi ý tên property, kiểu, mô tả và giá trị hợp lệ khi người dùng viết `application.yml` hoặc `application.properties`.

## 1. Configuration metadata giải quyết vấn đề gì?

Giả sử thư viện `acme-report-autoconfigure` cung cấp các cấu hình:

```yaml
acme:
  report:
    enabled: true
    timeout: 2s
    max-attempts: 3
    output-format: json
```

Spring Boot có thể bind những giá trị này vào một class `@ConfigurationProperties`. Tuy nhiên, khi người dùng viết YAML, IDE không tự biết chắc:

- Prefix `acme.report` có tồn tại hay không.
- Các key `enabled`, `timeout`, `max-attempts` là những lựa chọn được thư viện hỗ trợ.
- Kiểu dữ liệu và đơn vị của mỗi giá trị.
- Giá trị mặc định, ý nghĩa hoặc các giá trị được khuyến nghị.
- Một property đã deprecated và có key thay thế hay chưa.

**Configuration metadata** là dữ liệu mô tả các property để IDE và công cụ phát triển cung cấp trợ giúp theo ngữ cảnh, chẳng hạn autocomplete, documentation popup, kiểu giá trị, gợi ý giá trị và cảnh báo deprecated.

File metadata chuẩn nằm trong JAR tại:

```text
META-INF/spring-configuration-metadata.json
```

Phần lớn metadata được tạo tự động lúc compile bởi annotation processor `spring-boot-configuration-processor`, dựa trên các class/method có `@ConfigurationProperties`. Với những trường hợp processor không thể suy luận, thư viện có thể cung cấp metadata bổ sung.

Điểm quan trọng: metadata phục vụ **công cụ phát triển**. Nó không thay thế Binder, không tự đăng ký bean, không làm một property có tác dụng ở runtime và không tự kiểm tra mọi giá trị người dùng nhập. Runtime vẫn cần code bind/đọc và áp dụng property tương ứng.

## 2. Ba thành phần không được nhầm lẫn

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| `@ConfigurationProperties` | Khai báo nhóm cấu hình và cung cấp dữ liệu cho Spring Boot Binder | `ReportProperties` với prefix `acme.report` |
| `spring-boot-configuration-processor` | Đọc source lúc compile và sinh metadata | Tạo `META-INF/spring-configuration-metadata.json` |
| IDE hỗ trợ Spring Boot | Đọc metadata để gợi ý và hiển thị tài liệu | Gợi ý `acme.report.max-attempts` trong YAML |

Quy trình:

```text
Java/Kotlin source có @ConfigurationProperties
                 |
                 v
spring-boot-configuration-processor
                 |
                 v
META-INF/spring-configuration-metadata.json
                 |
                 v
Được đóng gói trong JAR của thư viện
                 |
                 v
Ứng dụng consumer thêm JAR vào dependency
                 |
                 v
IDE đọc metadata và cung cấp autocomplete
```

Nếu annotation processor không chạy, class Java vẫn có thể biên dịch và runtime Binder vẫn có thể bind property, nhưng JAR có thể thiếu metadata. Khi đó IDE có thể báo “Cannot resolve configuration property” hoặc không gợi ý key của thư viện.

Ngược lại, một key xuất hiện trong metadata không bảo đảm code runtime thật sự đọc hoặc bind nó. Metadata mô tả contract cho công cụ; implementation phải thực hiện contract đó.

## 3. Metadata gồm những nhóm thông tin nào?

Một file `spring-configuration-metadata.json` có thể có các phần sau:

| Phần | Ý nghĩa | Dùng để |
| --- | --- | --- |
| `groups` | Nhóm/prefix cấu hình, thường gắn với một type | Hiển thị namespace và ngữ cảnh |
| `properties` | Tên, kiểu, mô tả, nguồn và default của từng key | Autocomplete và documentation |
| `hints` | Giá trị gợi ý hoặc provider hỗ trợ nội dung | Gợi ý enum/string/class/bean/profile |
| `ignored` | Các property cố ý loại khỏi danh sách metadata | Ngăn công cụ quảng bá key không nên dùng |

Ví dụ rút gọn minh họa:

```json
{
  "groups": [
    {
      "name": "acme.report",
      "type": "com.acme.report.ReportProperties",
      "sourceType": "com.acme.report.ReportProperties"
    }
  ],
  "properties": [
    {
      "name": "acme.report.enabled",
      "type": "java.lang.Boolean",
      "description": "Bật hoặc tắt report integration.",
      "sourceType": "com.acme.report.ReportProperties",
      "defaultValue": false
    },
    {
      "name": "acme.report.timeout",
      "type": "java.time.Duration",
      "description": "Thời gian chờ cho một lần gọi report."
    }
  ],
  "hints": [
    {
      "name": "acme.report.output-format",
      "values": [
        { "value": "json" },
        { "value": "csv" }
      ]
    }
  ]
}
```

Đây là ví dụ rút gọn để giải thích cấu trúc, không phải file đầu ra nguyên văn. Metadata thật có thể có thêm property, source method, default, deprecation và thông tin khác.

Tên property dùng dạng canonical lower-case, phân tách bằng dấu chấm: `acme.report.max-attempts`. IDE có thể trình bày key theo cú pháp YAML hoặc `.properties`, nhưng metadata lưu tên canonical.

## 4. Tạo metadata tự động với `@ConfigurationProperties`

Annotation processor phát hiện class và method được đánh dấu `@ConfigurationProperties`. Với JavaBean thông thường, processor nhận diện property từ getter/setter; với constructor binding hoặc record, property được xác định từ constructor parameter/record component theo quy tắc của Spring Boot.

Ví dụ Java 17:

```java
package com.acme.report;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.report")
public class ReportProperties {

    /**
     * Bật hoặc tắt report integration.
     */
    private boolean enabled = false;

    /**
     * Thời gian chờ tối đa cho một lần gọi report.
     */
    private Duration timeout = Duration.ofSeconds(2);

    /**
     * Tổng số lần thử, bao gồm lần thử đầu tiên.
     */
    private int maxAttempts = 3;

    /**
     * Định dạng đầu ra được yêu cầu.
     */
    private String outputFormat = "json";

    /**
     * Danh sách vùng dữ liệu cần xử lý.
     */
    private List<String> regions = new ArrayList<>();

    /**
     * Mức xử lý report.
     */
    private Mode mode = Mode.STANDARD;

    public enum Mode {
        STANDARD,
        STRICT
    }

    public boolean isEnabled() {
        return this.enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public Duration getTimeout() {
        return this.timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxAttempts() {
        return this.maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public String getOutputFormat() {
        return this.outputFormat;
    }

    public void setOutputFormat(String outputFormat) {
        this.outputFormat = outputFormat;
    }

    public List<String> getRegions() {
        return this.regions;
    }

    public void setRegions(List<String> regions) {
        this.regions = regions;
    }

    public Mode getMode() {
        return this.mode;
    }

    public void setMode(Mode mode) {
        this.mode = mode;
    }
}
```

Processor có thể tạo metadata cho:

- Prefix/group `acme.report`.
- `acme.report.enabled` với kiểu Boolean.
- `acme.report.timeout` với kiểu Duration.
- `acme.report.max-attempts` với kiểu Integer.
- `acme.report.output-format` với kiểu String.
- `acme.report.regions` với kiểu Collection.
- `acme.report.mode` với kiểu enum.

Javadoc đặt trên field được dùng làm mô tả property. Hãy viết mô tả ngắn, rõ và hướng đến người cấu hình: nêu ý nghĩa, đơn vị, phạm vi tác động hoặc giới hạn quan trọng. Tránh đưa implementation detail như tên biến private, thuật toán nội bộ hay class helper vào tài liệu.

### 4.1. Default value được suy luận như thế nào?

Annotation processor dùng heuristic để đọc default từ source model. Các default tĩnh như:

```java
private boolean enabled = false;
private int maxAttempts = 3;
```

có thể được đưa vào metadata. Default chỉ được suy luận khi source của type đang được compile; nếu type chỉ tồn tại dưới dạng compiled dependency, processor không có đầy đủ source để đọc mô tả/default.

Có những trường hợp không tự suy luận được:

- Giá trị được tính động bằng method.
- Default lấy từ constant nằm trong class khác.
- Default của `Collection`/`Map`.
- Một số biểu thức khởi tạo phức tạp.
- Type được tái sử dụng từ module khác nhưng metadata của type đó chưa được xuất bản.

Với `regions`, dù code khởi tạo `new ArrayList<>()`, không nên mặc định processor sẽ suy ra `[]`. Nếu muốn IDE hiển thị chính xác default rỗng, bổ sung metadata thủ công.

### 4.2. Nested properties và record

Processor tự nhận diện nested properties cho inner class. Với một class bên ngoài được dùng làm property lồng nhau, có thể đánh dấu field/getter bằng `@NestedConfigurationProperty` để mô tả cấu trúc mong muốn. Annotation này không cần thiết cho `Collection` và `Map`, vì chúng được nhận diện theo cơ chế riêng.

Nếu dùng Java record:

```java
@ConfigurationProperties("acme.report")
public record ReportProperties(
        boolean enabled,
        Duration timeout,
        int maxAttempts
) {
}
```

Mô tả từng component nên được viết bằng Javadoc tag `@param` ở cấp class, vì record không có instance field thông thường để đặt field Javadoc:

```java
/**
 * Cấu hình report integration.
 *
 * @param enabled bật/tắt integration
 * @param timeout thời gian chờ của một lần gọi
 * @param maxAttempts tổng số lần thử, bao gồm lần đầu
 */
```

Không chỉ đổi class thành record rồi kỳ vọng field Javadoc cũ vẫn được xử lý giống JavaBean. Hãy kiểm tra file metadata sinh ra để xác nhận mô tả thực tế.

## 5. Cấu hình annotation processor trong Maven

Với Maven, dependency processor nên được khai báo `optional` để công cụ build của thư viện sử dụng nó nhưng không truyền processor sang mọi consumer.

Ví dụ POM hoàn chỉnh cho một module auto-configuration:

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

    <groupId>com.acme</groupId>
    <artifactId>acme-report-autoconfigure</artifactId>
    <version>1.0.0</version>

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
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
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
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-configuration-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-configuration-processor` là công cụ compile-time. Nó không phải dependency runtime mà ứng dụng cần để bind `ReportProperties`. Cấu hình `optional=true` giúp dependency processor không bị truyền tiếp cho consumer.

`annotationProcessorPaths` đăng ký processor rõ ràng với Maven Compiler Plugin. Đây là cách phù hợp với các build muốn kiểm soát processor path tường minh; cần giữ version processor đồng bộ với Spring Boot version của module.

Chạy:

```bash
mvn clean compile
```

Sau compile, kiểm tra file trong output directory:

```text
target/classes/META-INF/spring-configuration-metadata.json
```

Nếu file chưa xuất hiện, kiểm tra Maven Compiler Plugin, processor dependency/path, annotation trên class và việc source có thực sự được compile trong module đó không.

## 6. Cấu hình annotation processor trong Gradle

Với Gradle, khai báo processor bằng configuration `annotationProcessor`, không đưa nó vào `implementation` hoặc `runtimeOnly`:

```groovy
plugins {
    id 'java'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure:3.3.13'

    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor:3.3.13'

    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}
```

Nếu module có `additional-spring-configuration-metadata.json`, task `compileJava` phải biết rằng nó phụ thuộc vào resources đã được xử lý:

```groovy
tasks.named('compileJava') {
    inputs.files(tasks.named('processResources'))
}
```

Điều này bảo đảm file metadata bổ sung đã có mặt khi annotation processor chạy. Nếu thiếu dependency giữa hai task, kết quả có thể không chứa phần metadata thủ công hoặc build incremental có thể không tái tạo file như mong muốn.

Sau khi chạy:

```bash
./gradlew clean compileJava
```

kiểm tra:

```text
build/classes/java/main/META-INF/spring-configuration-metadata.json
```

### 6.1. Maven và Gradle khác nhau ở đâu?

| Build tool | Cách khai báo processor | Output thường gặp |
| --- | --- | --- |
| Maven | Dependency optional và/hoặc `annotationProcessorPaths` của compiler plugin | `target/classes/META-INF/...` |
| Gradle | `annotationProcessor` configuration | `build/classes/java/main/META-INF/...` |

Không đưa processor vào runtime của ứng dụng chỉ để IDE có autocomplete. IDE đọc file metadata đã được sinh và đóng gói; processor không cần chạy trong ứng dụng production.

## 7. Thêm metadata thủ công khi processor không đủ thông tin

Không phải mọi property đều được khai báo bằng `@ConfigurationProperties`. Một số khóa được dùng trực tiếp trong `@ConditionalOnProperty`, hoặc default/hint của chúng không thể suy luận tự động.

Spring Boot cho phép tạo file:

```text
src/main/resources/META-INF/additional-spring-configuration-metadata.json
```

Ví dụ:

```json
{
  "properties": [
    {
      "name": "acme.report.regions",
      "defaultValue": [],
      "description": "Danh sách vùng dữ liệu cần xử lý. Để trống nghĩa là dùng vùng mặc định."
    }
  ],
  "hints": [
    {
      "name": "acme.report.output-format",
      "values": [
        {
          "value": "json",
          "description": "Đầu ra JSON có cấu trúc."
        },
        {
          "value": "csv",
          "description": "Đầu ra CSV phù hợp cho bảng tính."
        }
      ]
    }
  ]
}
```

Annotation processor tự hợp nhất nội dung file này vào `spring-configuration-metadata.json` chính:

- Nếu property đã được phát hiện tự động, các trường `description`, `defaultValue` và `deprecation` được khai báo thủ công có thể ghi đè thông tin tương ứng.
- Nếu property chưa được processor nhận diện trong module hiện tại, entry thủ công có thể bổ sung nó.
- Phần `hints` thêm các giá trị gợi ý cho IDE.
- File bổ sung là tùy chọn; không cần tạo nếu không có metadata đặc biệt.

**Metadata thủ công không tự triển khai runtime binding.** Nếu khai báo `acme.report.output-format` trong JSON nhưng code không bind hoặc đọc property, IDE vẫn có thể gợi ý nó, nhưng ứng dụng không tự thay đổi định dạng đầu ra.

### 7.1. Value hints và provider

`hints` có thể khai báo danh sách giá trị hợp lệ hoặc provider để IDE tìm lựa chọn theo ngữ cảnh.

Ví dụ value hint:

```json
{
  "hints": [
    {
      "name": "acme.report.output-format",
      "values": [
        { "value": "json" },
        { "value": "csv" },
        { "value": "xml" }
      ]
    }
  ]
}
```

Một số provider chuẩn có thể được IDE hỗ trợ:

| Provider | Mục đích |
| --- | --- |
| `class-reference` | Gợi ý class có trên project classpath, có thể giới hạn theo base type |
| `handle-as` | Yêu cầu IDE xử lý một property như một kiểu cao cấp hơn, ví dụ `Resource` |
| `logger-name` | Gợi ý tên logger và logger group |
| `spring-bean-reference` | Gợi ý bean name phù hợp với một kiểu |
| `spring-profile-name` | Gợi ý Spring profile hiện có |
| `any` | Cho phép thêm giá trị ngoài danh sách hint |

Không phải IDE nào cũng hỗ trợ mọi provider. Danh sách `values` là trợ giúp cho công cụ; nó không tự thay thế enum, validation hoặc kiểm tra nghiệp vụ tại runtime. Nếu giá trị thực sự chỉ có một tập cố định, nên dùng Java `enum` trong `@ConfigurationProperties` khi phù hợp. Nếu dùng `String` vì cần linh hoạt, value hint giúp người cấu hình khám phá các giá trị được khuyến nghị.

### 7.2. Deprecation metadata

Khi đổi tên property, metadata có thể thông báo key cũ đã deprecated:

```json
{
  "properties": [
    {
      "name": "acme.report.format",
      "type": "java.lang.String",
      "deprecation": {
        "level": "warning",
        "reason": "Đã đổi tên để thống nhất với output-format.",
        "replacement": "acme.report.output-format",
        "since": "2.1.0"
      }
    }
  ]
}
```

`warning` biểu thị property vẫn được hỗ trợ trong giai đoạn chuyển tiếp. `error` biểu thị property không còn được quản lý/bind theo contract metadata. Metadata không tự tạo alias trong code: nếu muốn key cũ tiếp tục hoạt động, implementation phải thực sự nhận và chuyển giá trị cũ sang key mới trong giai đoạn tương thích.

Với JavaBean `@ConfigurationProperties`, `@DeprecatedConfigurationProperty` có thể được đặt trên getter của property deprecated để sinh thông tin deprecation. Cách này cần getter/setter vẫn hỗ trợ việc đọc/bind key cũ. Metadata deprecation và migration runtime là hai phần cần được kiểm tra cùng nhau.

## 8. Đóng gói metadata vào JAR

Sinh metadata trong `target/classes` hoặc `build/classes` chưa đủ. Khi publish library, file phải nằm bên trong JAR tại đúng đường dẫn:

```text
META-INF/spring-configuration-metadata.json
```

Với Maven:

```bash
mvn clean verify
```

JAR ví dụ:

```text
target/acme-report-autoconfigure-1.0.0.jar
```

Liệt kê nội dung JAR:

```bash
jar tf target/acme-report-autoconfigure-1.0.0.jar
```

Lọc tên file trên Windows PowerShell:

```powershell
jar tf target/acme-report-autoconfigure-1.0.0.jar |
    Select-String 'META-INF/spring-configuration-metadata.json'
```

Kết quả cần có:

```text
META-INF/spring-configuration-metadata.json
```

Trên Linux/macOS có thể dùng:

```bash
jar tf target/acme-report-autoconfigure-1.0.0.jar |
    grep 'META-INF/spring-configuration-metadata.json'
```

Để xem nội dung metadata, dùng `unzip` nếu có:

```bash
unzip -p target/acme-report-autoconfigure-1.0.0.jar \
    META-INF/spring-configuration-metadata.json
```

Hoặc dùng JDK `jar` để giải nén đúng file:

```bash
jar xf target/acme-report-autoconfigure-1.0.0.jar \
    META-INF/spring-configuration-metadata.json
```

Sau đó mở `META-INF/spring-configuration-metadata.json` bằng editor hoặc lệnh đọc file phù hợp.

Đối chiếu tối thiểu:

- Có group `acme.report`.
- Có đủ property được công bố: `enabled`, `timeout`, `max-attempts`, `output-format`, `regions`, `mode`.
- Type của property đúng.
- Description không rỗng và diễn tả đúng hành vi.
- Default được ghi đúng, nhất là collection hoặc giá trị không thể tự suy luận.
- Hint có các giá trị `json` và `csv`.
- Deprecation/replacement đúng nếu module có key cũ.
- File nằm trong JAR của **module mà consumer thực sự phụ thuộc**, không chỉ nằm trong module nguồn khác.

Nếu source metadata có nhưng JAR không có, kiểm tra cấu hình packaging, resource filtering, shade/relocation hoặc plugin build đã loại file `META-INF` hay chưa. Đừng giải quyết bằng cách chép một file metadata cũ vào JAR; cần sửa pipeline để processor tạo ra file đúng mỗi lần build.

## 9. Smoke test xác nhận metadata được sinh

Có thể viết một test nhỏ để phát hiện processor ngừng chạy hoặc metadata bổ sung không được hợp nhất.

Tạo `src/test/java/com/acme/report/MetadataPackagingTest.java`:

```java
package com.acme.report;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class MetadataPackagingTest {

    @Test
    void generatedMetadataContainsPublicPropertiesAndHints()
            throws IOException {

        try (InputStream input = getClass().getClassLoader()
                .getResourceAsStream(
                        "META-INF/spring-configuration-metadata.json")) {

            assertThat(input).isNotNull();

            String json = new String(
                    input.readAllBytes(),
                    StandardCharsets.UTF_8);

            String compact = json.replaceAll("\\s+", "");

            assertThat(compact)
                    .contains("\"name\":\"acme.report\"");
            assertThat(compact)
                    .contains("\"name\":\"acme.report.enabled\"");
            assertThat(compact)
                    .contains("\"name\":\"acme.report.timeout\"");
            assertThat(compact)
                    .contains("\"name\":\"acme.report.max-attempts\"");
            assertThat(compact)
                    .contains("\"name\":\"acme.report.output-format\"");
            assertThat(compact)
                    .contains("\"name\":\"acme.report.regions\"");
            assertThat(compact)
                    .contains("\"value\":\"json\"");
            assertThat(compact)
                    .contains("\"value\":\"csv\"");
        }
    }
}
```

Chạy:

```bash
mvn test
```

Kết quả mong đợi:

```text
Tests run: 1, Failures: 0, Errors: 0, Skipped: 0
```

Đây là smoke test đọc metadata trên test classpath sau compile. Nó kiểm tra processor đã tạo file và các hint thủ công đã được merge. Nó chưa thay thế bước `jar tf`: phải kiểm tra JAR cuối cùng để xác nhận file được đóng gói.

Có thể tăng độ chặt bằng cách parse JSON và kiểm tra từng object/field thay vì tìm chuỗi. Với một thư viện có contract lớn, nên kiểm tra danh sách property công khai, type, default, description và deprecation bằng test có cấu trúc để phát hiện thay đổi không chủ ý.

## 10. Kiểm tra autocomplete trong IDE của ứng dụng consumer

Sau khi metadata đã nằm trong JAR:

1. Publish/install artifact vào Maven local repository hoặc repository nội bộ.
2. Trong ứng dụng consumer, khai báo dependency đến đúng artifact/version của starter hoặc autoconfigure module.
3. Reload Maven project hoặc Refresh Gradle project để IDE cập nhật dependency graph.
4. Rebuild module thư viện và consumer để IDE nhìn thấy artifact mới.
5. Mở `application.yml` và gõ prefix:

```yaml
acme:
  report:
```

IDE được hỗ trợ có thể gợi ý:

```yaml
acme:
  report:
    enabled:
    timeout:
    max-attempts:
    output-format:
    regions:
    mode:
```

Khi gõ `output-format`, IDE có thể gợi ý `json` và `csv` nếu nó đọc được manual hints và hỗ trợ value completion. Khi chọn property, documentation popup có thể hiển thị mô tả và default.

Ví dụ cấu hình consumer:

```yaml
acme:
  report:
    enabled: true
    timeout: 750ms
    max-attempts: 5
    output-format: csv
    regions:
      - ap-southeast-1
      - eu-west-1
    mode: STRICT
```

Metadata của library được IDE dùng khi làm việc với source của consumer. Người dùng không cần chép `spring-configuration-metadata.json` vào project consumer nếu file đã có trong dependency JAR và IDE có thể index dependency đó.

Mức độ hỗ trợ autocomplete, hint provider và documentation popup phụ thuộc IDE, plugin Spring và trạng thái indexing. Metadata hợp lệ là điều kiện cần; nó không bảo đảm mọi IDE trình bày mọi provider giống nhau.

## 11. Chẩn đoán khi IDE không gợi ý property

### 11.1. File không được sinh

Kiểm tra:

- Class có `@ConfigurationProperties` đúng package/import không?
- Class/method có nằm trong source set được compile không?
- `spring-boot-configuration-processor` đã được khai báo chưa?
- Maven compiler có chạy annotation processor không?
- Gradle có khai báo `annotationProcessor` thay vì chỉ `implementation` không?
- IDE đang nhìn đúng module chứa `ReportProperties` hay không?

Chạy `mvn clean compile` hoặc `./gradlew clean compileJava`, sau đó tìm file ở output directory.

### 11.2. File có trong classes nhưng không có trong JAR

Đây là lỗi packaging. Kiểm tra:

- JAR có include resources từ output directory không?
- Plugin shade hoặc custom packaging có exclude `META-INF/**` không?
- Có build step nào xóa hoặc ghi đè `META-INF` không?
- Bạn đang kiểm tra đúng artifact và đúng version được consumer dùng không?

Luôn kiểm tra JAR cuối cùng, không chỉ `target/classes`.

### 11.3. JAR có metadata nhưng consumer IDE vẫn không gợi ý

Kiểm tra:

- Consumer có đúng dependency và version mới không?
- Dependency có nằm trên compile/development classpath mà IDE index không?
- Maven/Gradle đã được reload sau khi publish version mới chưa?
- IDE có plugin Spring Boot/YAML support phù hợp không?
- IDE cache/index có cần refresh không?
- Metadata JSON có hợp lệ và key dùng đúng canonical prefix không?

Thử tạo một consumer project nhỏ chỉ có dependency đó để tách vấn đề IDE khỏi cấu hình lớn của ứng dụng.

### 11.4. IDE gợi ý nhưng runtime không áp dụng property

Metadata không thực thi binding. Hãy kiểm tra riêng:

- Property có được bind bởi `@ConfigurationProperties`, `@Value` hoặc condition phù hợp không?
- Properties class có được đăng ký qua `@EnableConfigurationProperties` hoặc configuration properties scanning không?
- Auto-configuration có match không?
- Nguồn cấu hình/profile nào đang thắng?
- Có lỗi conversion hoặc validation không?

Ví dụ `acme.report.output-format` có trong JSON nhưng không có code nào đọc nó, IDE vẫn có thể gợi ý; ứng dụng sẽ không tự thay đổi output format.

## 12. Lỗi thường gặp khi xây dựng metadata

**Lỗi 1 — Chỉ thêm `spring-boot-configuration-processor` vào test scope.**  
Processor phải chạy trong compile của module production. Test scope không tạo metadata cho main artifact.

**Lỗi 2 — Đưa processor vào runtime dependency của starter.**  
Đây là công cụ build, không phải runtime API. Maven nên đánh dấu optional; Gradle dùng `annotationProcessor`.

**Lỗi 3 — Chỉ kiểm tra file trong source tree.**  
File generated có thể có ở `target/classes` nhưng bị loại khi đóng gói. Luôn kiểm tra nội dung JAR.

**Lỗi 4 — Viết Javadoc trên getter rồi không kiểm tra output.**  
Với JavaBean, processor dùng Javadoc trên field để tạo mô tả; với record, dùng class-level `@param`. Đặt sai vị trí có thể làm description rỗng.

**Lỗi 5 — Mong collection default tự xuất hiện.**  
Processor không tự phát hiện default cho Collections. Bổ sung `defaultValue` bằng manual metadata nếu cần hiển thị.

**Lỗi 6 — Dùng manual metadata như runtime implementation.**  
File JSON chỉ mô tả property cho tooling. Muốn property có tác dụng, code phải bind/đọc và áp dụng nó.

**Lỗi 7 — Khai báo value hint rồi xem nó như validation.**  
IDE có thể gợi ý `json` và `csv`, nhưng Binder không dùng metadata hint như một bộ validator runtime. Dùng enum hoặc validation nếu muốn giới hạn giá trị thực sự.

**Lỗi 8 — Quên Gradle task ordering.**  
Nếu dùng `additional-spring-configuration-metadata.json`, bảo đảm `compileJava` phụ thuộc `processResources` để processor đọc được file bổ sung.

**Lỗi 9 — Consumer dùng nhầm artifact.**  
Metadata trong `autoconfigure` module không giúp IDE nếu ứng dụng chỉ có một core module khác mà không chứa file đó. Xác định module nào thực sự được publish và thêm vào consumer.

**Lỗi 10 — Thay property mà không cập nhật metadata.**  
Rename/remove/default/deprecation phải cập nhật source, manual metadata, test, migration guide và artifact. Metadata cũ trong dependency cache có thể khiến IDE tiếp tục gợi ý key đã bỏ.

## 13. Quy trình review trước khi phát hành starter

| Kiểm tra | Kết quả cần có |
| --- | --- |
| Processor dependency | Maven optional hoặc Gradle annotationProcessor |
| Source properties | `@ConfigurationProperties` đúng prefix |
| Mô tả | Javadoc rõ ràng, đúng vị trí |
| Default | Được processor phát hiện hoặc bổ sung thủ công |
| Hints | Enum hoặc manual values/providers khi cần |
| Additional metadata | JSON hợp lệ và được merge lúc compile |
| Generated output | Có `META-INF/spring-configuration-metadata.json` |
| Packaged artifact | JAR thực sự chứa đúng đường dẫn metadata |
| Consumer | Dependency đúng artifact/version |
| IDE | Autocomplete và documentation xuất hiện sau reload/index |
| Runtime | Binder/auto-configuration thực sự áp dụng property |
| Compatibility | Deprecation/replacement/default được kiểm tra |

Với module nhiều properties, nên đưa kiểm tra metadata vào CI. Một build thành công nhưng metadata bị thiếu vẫn có thể làm trải nghiệm người dùng xấu đi; một JSON hợp lệ nhưng runtime không bind đúng cũng là lỗi contract.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** File metadata chuẩn phải nằm ở đâu bên trong JAR?  
**Đáp án:** `META-INF/spring-configuration-metadata.json`.

**Câu 2.** Annotation processor nào sinh metadata từ `@ConfigurationProperties`?  
**Đáp án:** `spring-boot-configuration-processor`, chạy trong quá trình compile.

**Câu 3.** Maven nên khai báo processor thế nào để không truyền nó tới consumer?  
**Đáp án:** Khai báo dependency `spring-boot-configuration-processor` với `<optional>true</optional>`; có thể cấu hình thêm annotation processor path tường minh trong Maven Compiler Plugin.

**Câu 4.** Gradle nên đặt processor ở configuration nào?  
**Đáp án:** `annotationProcessor`, không phải `implementation` hoặc `runtimeOnly`.

**Câu 5.** Vì sao một collection có default rỗng có thể thiếu `defaultValue` trong metadata?  
**Đáp án:** Processor không tự phát hiện default cho Collections; bổ sung `defaultValue` bằng `additional-spring-configuration-metadata.json`.

**Câu 6.** `hints.values` có buộc runtime chỉ chấp nhận những giá trị đó không?  
**Đáp án:** Không. Hints hỗ trợ IDE; dùng enum hoặc validation để ràng buộc runtime.

**Câu 7.** Metadata có trong `target/classes` nhưng IDE consumer vẫn không gợi ý. Bước tiếp theo là gì?  
**Đáp án:** Kiểm tra metadata trong JAR đã publish, dependency/version của consumer và việc IDE đã reload/index dependency mới chưa.

**Câu 8.** Metadata mô tả `acme.report.output-format`, nhưng code không bind hoặc đọc key. IDE có thể gợi ý không và runtime có thay đổi không?  
**Đáp án:** IDE có thể gợi ý; runtime không tự thay đổi vì metadata không thực thi property.

## 15. Nguyên tắc cần nhớ

- `spring-configuration-metadata.json` giúp IDE và tooling hiểu các property mà thư viện hỗ trợ.
- `spring-boot-configuration-processor` chạy lúc compile; Maven dùng dependency optional và Gradle dùng `annotationProcessor`.
- Javadoc, type và default có thể được suy luận từ source; record dùng Javadoc `@param`, còn Collections có thể cần metadata bổ sung.
- `additional-spring-configuration-metadata.json` bổ sung descriptions, defaults, deprecation và hints.
- Muốn autocomplete trong consumer, metadata phải nằm trong JAR mà consumer thực sự phụ thuộc.
- Dùng `jar tf` và trích xuất JSON để xác minh artifact cuối cùng.
- IDE support có thể khác nhau; refresh dependency/index khi thay đổi metadata.
- Metadata không thay Binder, auto-configuration, validation hoặc runtime behavior.

### Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Configuration Metadata](https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html)
- [Spring Boot — Generating Metadata with the Annotation Processor](https://docs.spring.io/spring-boot/specification/configuration-metadata/annotation-processor.html)
- [Spring Boot — Metadata Format](https://docs.spring.io/spring-boot/specification/configuration-metadata/format.html)
- [Spring Boot — Providing Manual Hints](https://docs.spring.io/spring-boot/specification/configuration-metadata/manual-hints.html)
- [Spring Boot 3.3 — `@ConfigurationProperties`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
