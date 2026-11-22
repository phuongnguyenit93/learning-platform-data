# Kiểm thử thực tế thứ tự ưu tiên, import và vị trí tệp qua `SpringApplication` — Spring Boot 3.3

## 1. Vì sao cần kiểm thử cấu hình bằng một lần khởi động thật?

Trong Spring Boot, các giá trị cấu hình có thể xuất hiện ở nhiều nơi: `application.properties` hoặc YAML trong classpath, file ngoài JAR, file theo profile, biến môi trường, Java system properties, command-line arguments, tài liệu được `spring.config.import` và các nguồn được ứng dụng bổ sung.

Một ví dụ:

```properties
lab252.mode=base
```

trong `application.properties`, nhưng file được import ghi:

```properties
lab252.mode=imported
```

và lệnh khởi động truyền:

```bash
java -jar app.jar --lab252.mode=cli
```

Giá trị cuối cùng là gì? Nếu chỉ mở từng file, không thể có bằng chứng đầy đủ về **cơ chế nạp và thứ tự ưu tiên thực tế**. Phải xét: file có thật sự được nạp không, import có được giải quyết đúng vị trí không, profile nào hoạt động, location có bị thay thế không, và có nguồn ưu tiên cao hơn hay không.

Vì vậy bài học này xây dựng các bài kiểm thử **thực sự gọi `SpringApplication.run(...)`**, tạo các file cấu hình tạm rồi đọc giá trị cuối từ `ConfigurableApplicationContext#getEnvironment()`.

Bài thuộc nhóm **Kiểm thử cấu hình** của chủ đề **Spring Boot Externalized Configuration**. Các ví dụ sử dụng **Java 17+**, **Spring Boot 3.3.x**, **JUnit 5**, Maven hoặc Gradle và **AssertJ**.

### Kết quả cần đạt

Sau bài này, bạn có thể:

1. Giải thích tại sao test `Environment` tự ghép các `PropertySource` chưa chứng minh Config Data thực sự vận hành đúng.
2. Khởi động một ứng dụng tối thiểu bằng `SpringApplication` trong test rồi đóng context.
3. Sử dụng `@TempDir` tạo file `.properties` và directory độc lập cho từng test.
4. Kiểm tra file classpath mặc định có được đọc không.
5. Chứng minh `spring.config.location` **thay thế** default search locations.
6. Chứng minh `spring.config.additional-location` **bổ sung** vị trí và cho phép override giá trị.
7. Kiểm chứng `spring.config.import`, import tương đối, nhiều import, import tùy chọn.
8. Kiểm chứng CLI có ưu tiên cao hơn config data.
9. Kiểm chứng file profile-specific và location groups dùng `,` khác `;`.
10. Phân biệt “đọc đúng giá trị cuối” với “bind đúng kiểu” hoặc “đạt validation”.
11. Chẩn đoán lỗi khi file thiếu, location viết sai, profile không bật, working directory khác.
12. Tránh test không cô lập, làm bẩn system properties, hoặc nhầm `@TestPropertySource` với Config Data processing.

> Trọng tâm là **bằng chứng hành vi tại startup**. Một lời khẳng định “nguồn A đáng lẽ phải thắng B” chưa đủ khi chưa biết Spring Boot đã nạp những nguồn nào.

## 2. Bốn tầng cần kiểm thử riêng

Một bài kiểm thử cấu hình có thể chạm tới bốn tầng:

| Tầng | Câu hỏi | Bằng chứng phù hợp |
| --- | --- | --- |
| Vị trí tìm kiếm | Spring Boot có tìm và nạp file này không? | Khởi động với file tạm rồi assert khóa chỉ tồn tại ở file đó |
| Import | File được import có thực sự được tải và ưu tiên đúng không? | File gốc và imported file dùng cùng một key có giá trị khác nhau |
| Precedence | CLI, system property, environment, config data: nguồn nào thắng? | Assert `Environment#getProperty()` khi nhiều nguồn có cùng key |
| Binding và validation | Giá trị cuối có chuyển sang model Java và đạt constraint không? | Assert bean `@ConfigurationProperties` và trường hợp startup lỗi |

Trong bài, ta ưu tiên ba tầng đầu. Tầng thứ tư được minh họa để tránh suy luận sai từ một test chỉ kiểm tra chuỗi.

Một sơ đồ:

```text
@SpringBootConfiguration tối thiểu
                |
                v
        SpringApplication.run(...)
                |
                v
       Config Data được xử lý
        |         |          |
      search     import    profiles
        |         |          |
        +---------+----------+
                  |
                  v
         MutablePropertySources
                  |
                  v
       Spring Environment resolver
                  |
                  v
       getProperty("lab252.mode")
                  |
                  v
              Assertion
```

`SpringApplication.run(...)` đi qua bootstrap của Spring Boot, vì vậy có thể quan sát hoạt động thực của Config Data. Một `MockEnvironment` đơn giản không tự thực hiện toàn bộ các bước ấy.

## 3. Các quy tắc Spring Boot 3.3 mà test cần chứng minh

Theo Spring Boot 3.3 Reference, nguồn cấu hình có thứ tự ưu tiên định nghĩa rõ. Dưới đây là sơ đồ rút gọn cho những nguồn thông dụng, **theo mức ưu tiên từ cao xuống thấp**:

```text
Command-line properties của SpringApplication
                |
                v
Java system properties của JVM đang chạy app
                |
                v
OS environment variables
                |
                v
Config Data
                |
                v
Default properties của SpringApplication
```

Thực tế còn có `SPRING_APPLICATION_JSON`, test property sources, JNDI, servlet parameters, devtools settings và nguồn tùy chỉnh. Trong test nên kiểm soát đầu vào, không giả định sơ đồ rút gọn là toàn bộ các nguồn có thể tồn tại.

Bên trong **Config Data** còn nhiều quy tắc:

- `application.properties`/YAML ở classpath.
- File profile-specific như `application-prod.properties`.
- File ở vị trí bên ngoài JAR.
- File được `spring.config.import`.
- Vị trí bổ sung và vị trí thay thế.
- Thứ tự location và location groups.
- Tài liệu cấu hình nhiều phần, profile activation.
- File tùy chọn dùng prefix `optional:`.

Các quy tắc dưới đây đặc biệt quan trọng:

| Đầu vào | Ý nghĩa |
| --- | --- |
| `spring.config.name` | Đổi basename khi tìm file trong directory |
| `spring.config.location` | Thay thế các default search locations |
| `spring.config.additional-location` | Thêm location bên cạnh các location mặc định |
| `spring.config.import` | Đưa thêm config data vào từ file hoặc vị trí khác |
| `optional:` | Cho phép location không tồn tại trong các trường hợp được hỗ trợ |
| `spring.profiles.active` | Chọn profile, ảnh hưởng việc chọn file có hậu tố profile |
| `,` trong location list | Phân tách các location theo thứ tự |
| `;` trong location list | Nhóm các location ở cùng một mức ưu tiên cho xử lý profile |

Những thuộc tính như `spring.config.location`, `spring.config.name`, `spring.config.additional-location` được Spring Boot dùng **rất sớm**. Khi thử chúng, truyền trực tiếp dưới dạng đối số `SpringApplication.run(...)`, Java system property hoặc biến môi trường phù hợp; đừng dựa vào một nguồn chỉ xuất hiện sau khi Config Data đã chạy.

## 4. Vì sao chọn `SpringApplication` thay vì chỉ `@SpringBootTest`?

`@SpringBootTest` rất hữu ích khi muốn kiểm thử ngữ cảnh ứng dụng thật. Nhưng một bài kiểm thử được yêu cầu **chủ động đổi cả nơi tìm file cấu hình** ở mỗi test có thể cần kiểm soát trực tiếp các đối số startup.

Một ví dụ:

```java
SpringApplication app = new SpringApplication(TestApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);

try (ConfigurableApplicationContext context = app.run(
        "--spring.config.location=file:/somewhere/application.properties")) {

    assertThat(context.getEnvironment().getProperty("lab252.mode"))
            .isEqualTo("external");
}
```

Trong ví dụ, `run(...)` đi qua startup Spring Boot và cho phép test tự đặt một location thật sự có thể nạp.

So sánh các cách:

| Cách | Phù hợp khi | Giới hạn cần nhớ |
| --- | --- | --- |
| Unit test với `MockEnvironment` | Thử xử lý `PropertySource` do chính code tạo | Không tự chạy toàn bộ Config Data bootstrap |
| `ApplicationContextRunner` | Thử bean, auto-configuration, điều kiện | Không nên mặc định nó mô phỏng đầy đủ `SpringApplication` Config Data location/import |
| `@SpringBootTest` | Kiểm thử ứng dụng tích hợp theo một bộ cấu hình | Test context caching và property overrides có thể làm việc thử nhiều startup location kém trực tiếp |
| `SpringApplication.run` | Kiểm thử discovery/search/import/precedence lúc khởi động | Cần quản lý context, đầu vào toàn cục, file tạm |

Không có công cụ nào “tốt nhất cho mọi loại test”. Chọn `SpringApplication` ở đây vì mục tiêu là **kiểm chứng quy trình khởi động Config Data thật**, không phải chỉ kiểm tra một giá trị Java sau khi tự gán.

### Điều gì phải được cô lập?

- Các file cấu hình của mỗi test.
- Đường dẫn file/directory.
- Các đối số startup.
- Những system properties hoặc environment variables được test chủ động sửa.
- ApplicationContext được mở và đóng.
- Cấu hình test resource ở classpath.
- Trạng thái profile và default properties.
- Những side effect bên ngoài như network, database, server port.

Mỗi test nên chạy nhanh, không cần kết nối dịch vụ ngoài và không dựa trên file thật trong máy developer.

## 5. Chuẩn bị project kiểm thử

Ví dụ Maven có dependency management Spring Boot 3.3.x:

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

`spring-boot-starter-test` thường cung cấp JUnit Jupiter, AssertJ và các thành phần kiểm thử phù hợp với phiên bản Boot.

Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Không nhất thiết thêm Spring Web hoặc database chỉ để test thứ tự cấu hình. Để tránh tạo embedded web server, ví dụ sẽ đặt:

```java
app.setWebApplicationType(WebApplicationType.NONE);
```

### Cấu trúc thư mục đề xuất

```text
config-precedence-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── example/
    │           └── configlab/
    │               └── ConfigLabApplication.java
    └── test/
        ├── java/
        │   └── example/
        │       └── configlab/
        │           └── ConfigDataStartupTest.java
        └── resources/
            └── application.properties
```

Ứng dụng `ConfigLabApplication` có thể là Spring Boot application thông thường. Bài test sử dụng một class cấu hình nhỏ riêng để tránh thành phần ngoài phạm vi.

## 6. Đặt một file mặc định có dấu hiệu nhận biết

Trong `src/test/resources/application.properties`:

```properties
lab252.packaged-only=present-in-classpath
lab252.shared=from-classpath
lab252.mode=classpath-mode
```

File test resource này làm **đường chuẩn** cho một số phép so sánh:

- Khi không thay location, ta trông đợi `lab252.packaged-only` hiện diện.
- Khi dùng `spring.config.location` trỏ thẳng tới file ngoài, ta trông đợi marker này **không được nạp từ default classpath location**.
- Khi dùng `spring.config.additional-location`, marker classpath vẫn còn, còn key trùng `lab252.shared` có thể bị file bổ sung override.

Dùng prefix `lab252` thay vì tên chung như `test.value` để giảm nguy cơ bị các tệp hoặc biến môi trường không liên quan tác động.

**Lưu ý:** file dưới `src/test/resources` thuộc **test classpath**, không phải file trong production JAR. Nó phù hợp để kiểm tra config data từ classpath khi chạy test. Không cần sao chép file này vào `src/main/resources`.

## 7. Lớp khởi động tối thiểu cho test

Trong file test `ConfigDataStartupTest.java`, ta có thể khai báo class nested:

```java
@SpringBootConfiguration(proxyBeanMethods = false)
static class MinimalApplication {
}
```

`@SpringBootConfiguration` là một biến thể cấu hình của Spring Boot, đủ làm một primary source cho test khởi động ngữ cảnh tối thiểu.

Một helper:

```java
private static ConfigurableApplicationContext start(String... arguments) {
    SpringApplication application =
            new SpringApplication(MinimalApplication.class);

    application.setWebApplicationType(WebApplicationType.NONE);
    application.setBannerMode(Banner.Mode.OFF);
    application.setLogStartupInfo(false);

    return application.run(arguments);
}
```

Import cần dùng:

```java
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
```

Điểm quan trọng:

- `new SpringApplication(...)` tạo đối tượng điều phối bootstrap.
- `run(arguments)` nhận đối số giống cách ứng dụng thực khởi động.
- `SpringApplication` vẫn đi qua việc chuẩn bị `Environment` và Config Data.
- `WebApplicationType.NONE` tránh mở HTTP server.
- Tắt banner và startup info giúp output test bớt nhiễu.
- `try-with-resources` đóng context sau assertion, tránh giữ tài nguyên qua các test.

Không nên thay helper này bằng `new StandardEnvironment()` rồi kỳ vọng các file import tự được nạp. `StandardEnvironment` đơn lẻ không chạy Config Data pipeline của Boot.

## 8. Dùng `@TempDir` để tạo file thật nhưng không phụ thuộc máy

JUnit Jupiter cung cấp:

```java
@TempDir
Path tempDir;
```

Trường này nhận một directory tạm do JUnit quản lý cho test instance.

Helper ghi UTF-8:

```java
private static Path write(Path file, String content)
        throws IOException {

    Files.createDirectories(file.getParent());
    Files.writeString(file, content, StandardCharsets.UTF_8);
    return file;
}
```

Các import:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.io.TempDir;
```

Ví dụ:

```java
Path config = write(
        tempDir.resolve("external/application.properties"),
        "lab252.shared=external\n");
```

Tệp được tạo thật trên filesystem. Từ `Path` có thể tạo URI:

```java
String location = config.toUri().toString();
```

Một URI thường có dạng:

```text
file:///tmp/junit-xyz/external/application.properties
```

hoặc với Windows:

```text
file:///C:/Users/.../Temp/.../external/application.properties
```

Dùng `Path.toUri()` tránh nối thủ công `file:` với đường dẫn Windows chứa dấu `\` hoặc ký tự cần escape.

**Không dùng tên file tạm cố định ở thư mục làm việc** rồi để các test cùng sửa một file `application.properties`. Điều đó làm test có thể ảnh hưởng lẫn nhau và phụ thuộc thứ tự chạy.

## 9. Test 1 — classpath `application.properties` được nạp

Khi chạy helper `start()` **không đưa location đặc biệt**, Spring Boot tìm file theo những default locations.

Ví dụ:

```java
@Test
void loadsClasspathApplicationProperties() {
    try (ConfigurableApplicationContext context = start()) {
        assertThat(context.getEnvironment()
                .getProperty("lab252.packaged-only"))
                .isEqualTo("present-in-classpath");

        assertThat(context.getEnvironment()
                .getProperty("lab252.shared"))
                .isEqualTo("from-classpath");
    }
}
```

Ở đây `src/test/resources/application.properties` nằm trên classpath của bài test.

Kết quả kỳ vọng:

```text
lab252.packaged-only = present-in-classpath
lab252.shared        = from-classpath
```

Điều được chứng minh: Spring Boot bootstrap đã tìm và đưa file classpath vào `Environment` cho một lần startup tiêu chuẩn trong môi trường test.

Điều **chưa** được chứng minh: file ngoài JAR sẽ ghi đè ra sao, import tương đối ra sao, hay profile-specific file có được đọc hay không. Mỗi tình huống cần một test riêng.

## 10. Test 2 — `spring.config.location` thay thế default locations

Tạo file ngoài:

```properties
lab252.shared=from-explicit-location
lab252.external-only=present
```

và chạy:

```java
@Test
void explicitLocationReplacesDefaultSearchLocations()
        throws IOException {

    Path external = write(
            tempDir.resolve("replacement/application.properties"),
            "lab252.shared=from-explicit-location\n"
            + "lab252.external-only=present\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + external.toUri())) {

        ConfigurableEnvironment environment =
                context.getEnvironment();

        assertThat(environment.getProperty("lab252.shared"))
                .isEqualTo("from-explicit-location");

        assertThat(environment.getProperty("lab252.external-only"))
                .isEqualTo("present");

        assertThat(environment.getProperty("lab252.packaged-only"))
                .isNull();
    }
}
```

Đây là một test “phân biệt có/không”:

- `lab252.external-only` chứng minh external file được nạp.
- `lab252.packaged-only` vắng mặt chứng minh classpath default file **không còn được nạp qua default search locations** khi explicit location thay thế.

Đừng chỉ assert `lab252.shared=from-explicit-location`: một giá trị trùng key có thể bị override ngay cả khi classpath vẫn được nạp. Marker độc lập giúp chứng minh cơ chế **replace**, không chỉ chứng minh kết quả precedence.

### `spring.config.location` nhận file hay directory?

Một file:

```text
file:/path/application.properties
```

được nạp trực tiếp (nếu tồn tại).

Một directory:

```text
file:/path/config/
```

được Boot xử lý như một thư mục tìm file theo `spring.config.name`; directory location cần kết thúc bằng `/`.

Ví dụ trên cố ý dùng **file location**, nên không cần dự đoán basename nào sẽ được ghép vào directory.

## 11. Test 3 — `spring.config.additional-location` giữ default và bổ sung external

Tạo file:

```properties
lab252.shared=from-additional
lab252.external-only=from-additional
```

Sau đó:

```java
@Test
void additionalLocationKeepsDefaultsAndOverridesSharedKey()
        throws IOException {

    Path external = write(
            tempDir.resolve("additional/application.properties"),
            "lab252.shared=from-additional\n"
            + "lab252.external-only=from-additional\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.additional-location="
            + external.toUri())) {

        ConfigurableEnvironment environment =
                context.getEnvironment();

        assertThat(environment.getProperty("lab252.packaged-only"))
                .isEqualTo("present-in-classpath");

        assertThat(environment.getProperty("lab252.external-only"))
                .isEqualTo("from-additional");

        assertThat(environment.getProperty("lab252.shared"))
                .isEqualTo("from-additional");
    }
}
```

Hai loại dữ liệu cùng hiện diện:

- Marker classpath chứng minh default file vẫn được nạp.
- Marker external chứng minh additional file cũng được nạp.
- Key `shared` có giá trị từ additional file, thể hiện file bổ sung có thể override cấu hình mặc định trong trường hợp này.

**Khác biệt quan trọng:**

```text
spring.config.location
    -> thay thế default locations

spring.config.additional-location
    -> giữ default locations và nạp thêm
```

Nếu chỉ nhìn `lab252.shared` mà không có marker riêng cho từng nguồn, ta khó phân biệt hai hành vi đó.

## 12. Test 4 — command-line argument thắng config data

Tạo external file:

```properties
lab252.mode=from-file
```

Truyền đồng thời một CLI option:

```java
@Test
void commandLineOverridesConfigFile() throws IOException {
    Path config = write(
            tempDir.resolve("cli/application.properties"),
            "lab252.mode=from-file\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + config.toUri(),
            "--lab252.mode=from-cli")) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.mode"))
                .isEqualTo("from-cli");
    }
}
```

`SpringApplication` theo mặc định chuyển option kiểu `--name=value` thành command-line property source, thường có ưu tiên cao hơn file config data.

Điều này khác với gọi:

```java
System.getProperty("lab252.mode")
```

Java system property có thể vắng mặt hoặc chứa giá trị khác; `Environment` là nơi quan sát **giá trị sau khi Spring tổng hợp nguồn**.

### Nếu vô hiệu hóa command-line properties thì sao?

SpringApplication có API:

```java
application.setAddCommandLineProperties(false);
```

Khi dùng API này, những `--lab252.mode=...` vẫn là đối số truyền cho ứng dụng, nhưng **không tự được thêm vào Spring Environment** như command-line property source.

Vì vậy test phải nêu giả định rõ: ở các bài thử trên, ta dùng **cấu hình mặc định** của `SpringApplication`, không gọi `setAddCommandLineProperties(false)`.

## 13. Test 5 — `spring.config.import` nạp file khác và thắng file khai báo import

Giả sử directory chứa:

```text
import-case/
├── application.properties
└── shared.properties
```

`application.properties`:

```properties
spring.config.import=shared.properties
lab252.value=from-root
lab252.root-only=present
```

`shared.properties`:

```properties
lab252.value=from-import
lab252.import-only=present
```

Theo Spring Boot Config Data, tài liệu được import được đưa vào theo quy tắc import và có thể **ghi đè** giá trị của tài liệu khai báo import.

Test:

```java
@Test
void importedFileOverridesDeclaringFile() throws IOException {
    Path dir = tempDir.resolve("import-case");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=shared.properties\n"
            + "lab252.value=from-root\n"
            + "lab252.root-only=present\n");

    write(
            dir.resolve("shared.properties"),
            "lab252.value=from-import\n"
            + "lab252.import-only=present\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri())) {

        ConfigurableEnvironment environment =
                context.getEnvironment();

        assertThat(environment.getProperty("lab252.value"))
                .isEqualTo("from-import");

        assertThat(environment.getProperty("lab252.root-only"))
                .isEqualTo("present");

        assertThat(environment.getProperty("lab252.import-only"))
                .isEqualTo("present");
    }
}
```

Test này xác nhận **cả hai file có tham gia**, nhưng key trùng được quyết định bởi import.

### Vì sao `shared.properties` có thể không cần `file:`?

Giá trị:

```properties
spring.config.import=shared.properties
```

là một **import-relative location**, được giải quyết tương đối với file đã khai báo import.

Trong ví dụ, root nằm trong directory `import-case`, nên `shared.properties` được tìm ngay cạnh root.

Nếu dùng:

```properties
spring.config.import=file:/absolute/path/shared.properties
```

thì đó là **fixed location**, không dựa vào vị trí của file khai báo.

## 14. Test 6 — import nhiều tầng là tương đối với từng file khai báo

Một cấu trúc:

```text
nested/
├── application.properties
└── child/
    ├── child.properties
    └── next/
        └── deep.properties
```

`application.properties`:

```properties
spring.config.import=child/child.properties
lab252.depth=root
```

`child/child.properties`:

```properties
spring.config.import=next/deep.properties
lab252.depth=child
```

`child/next/deep.properties`:

```properties
lab252.depth=deep
```

Test:

```java
@Test
void nestedImportsResolveRelativeToDeclaringDocument()
        throws IOException {

    Path dir = tempDir.resolve("nested");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=child/child.properties\n"
            + "lab252.depth=root\n");

    write(
            dir.resolve("child/child.properties"),
            "spring.config.import=next/deep.properties\n"
            + "lab252.depth=child\n");

    write(
            dir.resolve("child/next/deep.properties"),
            "lab252.depth=deep\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri())) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.depth"))
                .isEqualTo("deep");
    }
}
```

Nếu hệ thống cố giải quyết **mọi** import tương đối từ working directory của shell, nó sẽ tìm sai file ở tầng hai. Spring Boot Config Data xử lý các import-relative locations theo **tài liệu chứa khai báo import**.

Đây là một lý do nên dùng temp directory với đường dẫn rõ ràng: test không cần dựa vào thư mục hiện tại của IDE hay CI.

## 15. Test 7 — import nhiều file: file được liệt kê sau có thể thắng

`application.properties`:

```properties
spring.config.import=first.properties,second.properties
lab252.level=root
```

`first.properties`:

```properties
lab252.level=first
```

`second.properties`:

```properties
lab252.level=second
```

Trong Spring Boot 3.3, các import được xét theo thứ tự khai báo, với import về sau có thể override import trước.

Test:

```java
@Test
void laterImportHasHigherPrecedence()
        throws IOException {

    Path dir = tempDir.resolve("several-imports");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=first.properties,second.properties\n"
            + "lab252.level=root\n");

    write(
            dir.resolve("first.properties"),
            "lab252.level=first\n");

    write(
            dir.resolve("second.properties"),
            "lab252.level=second\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri())) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.level"))
                .isEqualTo("second");
    }
}
```

**Không nhầm thứ tự import với thứ tự dòng trong cùng file.** Trong một document, đặt `spring.config.import` ở đầu hay cuối file không làm key của file đó ưu tiên hơn imported data. Quy tắc Config Data xử lý import, không lấy “dòng nào xuất hiện sau” làm precedence cho hai file.

### Còn import cùng một file nhiều lần?

Spring Boot áp dụng quy tắc nạp mỗi import một lần đối với cùng nguồn tương ứng. Không cần lạm dụng nhiều dòng import trùng để cố ghi đè một value. Nếu một test quan trọng cần kiểm chứng duplicate import, hãy thiết kế hai đường khai báo cùng chỉ đến một tài nguyên, rồi kiểm tra số source và giá trị có hiệu lực thay vì suy luận rằng file được áp hai lần.

## 16. Test 8 — import tùy chọn và file không tồn tại

Thực tế triển khai thường có file bổ sung chỉ hiện diện ở một số môi trường. Ví dụ máy developer không có `local-overrides.properties`, nhưng production có.

Có thể viết:

```properties
spring.config.import=optional:local-overrides.properties
lab252.value=base
```

Nếu file import không tồn tại, ứng dụng vẫn có thể khởi động.

Test:

```java
@Test
void optionalMissingImportDoesNotFailStartup()
        throws IOException {

    Path dir = tempDir.resolve("optional-import");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=optional:missing.properties\n"
            + "lab252.value=base\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri())) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.value"))
                .isEqualTo("base");
    }
}
```

Điểm quan trọng: `optional:` chỉ thay đổi cách xử lý **thiếu location/file**, không cho phép file tồn tại nhưng có cú pháp `.properties` hoặc YAML sai được bỏ qua một cách vô điều kiện.

### Khi bỏ `optional:`

```properties
spring.config.import=missing.properties
```

Spring Boot thường fail startup với exception thuộc nhóm Config Data location/resource not found.

Bài kiểm thử có thể:

```java
@Test
void requiredMissingImportFailsStartup()
        throws IOException {

    Path dir = tempDir.resolve("required-import");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=missing.properties\n"
            + "lab252.value=base\n");

    assertThatThrownBy(() -> start(
            "--spring.config.location=" + root.toUri()))
            .isInstanceOf(RuntimeException.class);
}
```

Đây là assertion ở mức **startup thất bại**. Để kiểm tra chặt hơn nguyên nhân, bạn có thể truy dấu exception chain đến loại Config Data cụ thể, nhưng không nên gắn một format thông báo lỗi cố định vốn có thể thay đổi giữa các bản vá.

### `spring.config.on-not-found=ignore`

Spring Boot còn có tùy chọn xử lý các lỗi thiếu Config Data location rộng hơn. Không nên dùng một chính sách “bỏ qua tất cả file thiếu” để che một file production **bắt buộc**. Nếu chỉ một file tùy chọn, dùng `optional:` ngay trên location cụ thể thường rõ hơn.

## 17. Test 9 — profile-specific file thắng file cơ sở

Tạo:

```text
profiles/
├── application.properties
└── application-prod.properties
```

File cơ sở:

```properties
lab252.color=base
```

File profile:

```properties
lab252.color=prod
```

Test:

```java
@Test
void profileSpecificPropertiesOverrideBase()
        throws IOException {

    Path dir = tempDir.resolve("profiles");

    Path root = write(
            dir.resolve("application.properties"),
            "lab252.color=base\n");

    write(
            dir.resolve("application-prod.properties"),
            "lab252.color=prod\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri(),
            "--spring.profiles.active=prod")) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.color"))
                .isEqualTo("prod");
    }
}
```

Khi `spring.profiles.active=prod`, Boot xét file có hậu tố profile tương ứng và profile-specific file có thể override file cơ sở.

**Không cần tự gọi `Files.readString` của file profile rồi gán property vào Environment.** Mục đích test là để Config Data tự tìm biến thể profile và kiểm tra kết quả.

### Nếu bật nhiều profiles?

Với `spring.profiles.active=prod,live`, quy tắc thường là **profile sau có khả năng override profile trước**, trong phạm vi location group tương ứng.

Không nên biến quy tắc này thành suy luận rằng **mọi file `live` luôn thắng mọi file `prod` tại tất cả các location**, vì location groups còn ảnh hưởng precedence.

## 18. Test 10 — vị trí directory và `spring.config.name`

`spring.config.location` có thể nhận một directory. Khi nhận directory, Spring Boot ghép các basename từ `spring.config.name` để tìm file cấu hình.

Ví dụ directory chứa:

```text
custom-name/
└── settings.properties
```

Nếu bạn đặt:

```text
spring.config.name=settings
spring.config.location=file:/.../custom-name/
```

Boot có thể nạp `settings.properties`.

Test:

```java
@Test
void directoryLocationUsesSpringConfigName()
        throws IOException {

    Path dir = tempDir.resolve("custom-name");
    Files.createDirectories(dir);

    write(
            dir.resolve("settings.properties"),
            "lab252.named=settings-file\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.name=settings",
            "--spring.config.location=" + dir.toUri())) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.named"))
                .isEqualTo("settings-file");
    }
}
```

`Path.toUri()` của một directory tồn tại thường biểu diễn URI có slash cuối. Cần phân biệt:

```text
file:/some/config/
```

là directory location, còn:

```text
file:/some/config/application.properties
```

là file location.

### Sai lầm: đưa directory không có dấu slash cuối

Spring Boot yêu cầu directory trong `spring.config.location` kết thúc bằng `/` để biết đó là thư mục. Nếu tự nối chuỗi `file:` hoặc sửa URI thủ công, hãy kiểm tra dấu slash cuối và cách escape đường dẫn.

Với test lập trình, sử dụng `Files.createDirectories(dir)` trước khi gọi `dir.toUri()`, rồi không tự sửa URI.

## 19. Test 11 — nhiều location: location liệt kê sau có thể override

Tạo:

```text
locations/
├── base/
│   └── application.properties
└── override/
    └── application.properties
```

`base/application.properties`:

```properties
lab252.region=base
```

`override/application.properties`:

```properties
lab252.region=override
```

Test:

```java
@Test
void laterLocationCanOverrideEarlierLocation()
        throws IOException {

    Path base = tempDir.resolve("locations/base");
    Path override = tempDir.resolve("locations/override");

    Files.createDirectories(base);
    Files.createDirectories(override);

    write(base.resolve("application.properties"),
            "lab252.region=base\n");

    write(override.resolve("application.properties"),
            "lab252.region=override\n");

    String locations = base.toUri() + "," + override.toUri();

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + locations)) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.region"))
                .isEqualTo("override");
    }
}
```

Dấu phẩy phân tách các location theo thứ tự. Trong trường hợp này location về sau có thể override key trùng từ location trước.

**Thứ tự location không phải thứ tự tên thư mục theo alphabet** khi bạn đã chỉ định rõ. Khác với một số trường hợp wildcard, vị trí trong danh sách có ý nghĩa.

### Test mạnh hơn khi cần

Ngoài key trùng, có thể cấp mỗi file một marker riêng để chứng minh cả hai được nạp:

```properties
lab252.base-only=yes
```

và:

```properties
lab252.override-only=yes
```

Khi assert cả marker lẫn giá trị trùng, kết quả mô tả được **presence** và **precedence** thay vì chỉ một giá trị cuối.

## 20. Test 12 — location groups: dấu phẩy khác dấu chấm phẩy

Đây là trường hợp nâng cao rất dễ hiểu sai.

Theo tài liệu Spring Boot 3.3:

- Dấu phẩy `,` phân tách các location theo **mức ưu tiên khác nhau**.
- Dấu chấm phẩy `;` kết hợp các location thành **cùng một nhóm** để xét profile theo cùng mức ưu tiên.

Giả sử có hai directory:

```text
groups/
├── cfg/
│   └── application-live.properties
└── ext/
    └── application-prod.properties
```

`cfg/application-live.properties`:

```properties
lab252.variant=cfg-live
```

`ext/application-prod.properties`:

```properties
lab252.variant=ext-prod
```

Bật:

```properties
spring.profiles.active=prod,live
```

### Trường hợp A: dấu phẩy

```text
spring.config.location=file:/.../cfg/,file:/.../ext/
```

Boot xử lý các location theo thứ tự, trong đó các file thuộc `ext` có thể override file thuộc `cfg`.

Với cấu trúc file trên, kỳ vọng:

```text
lab252.variant=ext-prod
```

### Trường hợp B: dấu chấm phẩy

```text
spring.config.location=file:/.../cfg/;file:/.../ext/
```

Hai location được nhóm ở cùng mức. Trong nhóm, profile được xử lý theo thứ tự `prod,live`; giá trị thuộc profile `live` được áp sau `prod` và có thể thắng.

Kỳ vọng:

```text
lab252.variant=cfg-live
```

### Test hai trường hợp

```java
@Test
void commaAndSemicolonCanChangeProfilePrecedence()
        throws IOException {

    Path cfg = tempDir.resolve("groups/cfg");
    Path ext = tempDir.resolve("groups/ext");
    Files.createDirectories(cfg);
    Files.createDirectories(ext);

    write(cfg.resolve("application-live.properties"),
            "lab252.variant=cfg-live\n");

    write(ext.resolve("application-prod.properties"),
            "lab252.variant=ext-prod\n");

    String commaLocations = cfg.toUri() + "," + ext.toUri();
    String groupedLocations = cfg.toUri() + ";" + ext.toUri();

    try (ConfigurableApplicationContext comma = start(
            "--spring.config.location=" + commaLocations,
            "--spring.profiles.active=prod,live")) {

        assertThat(comma.getEnvironment()
                .getProperty("lab252.variant"))
                .isEqualTo("ext-prod");
    }

    try (ConfigurableApplicationContext grouped = start(
            "--spring.config.location=" + groupedLocations,
            "--spring.profiles.active=prod,live")) {

        assertThat(grouped.getEnvironment()
                .getProperty("lab252.variant"))
                .isEqualTo("cfg-live");
    }
}
```

Test này có giá trị vì cho thấy **không thể rút gọn toàn bộ Config Data precedence thành câu “profile sau luôn thắng”** khi có nhiều location groups.

Đừng chuyển nguyên chuỗi có `;` lên một shell rồi quên nháy: ở nhiều shell, `;` là ký tự phân tách lệnh. Trong Java test, mỗi `--spring.config.location=...` được truyền trực tiếp dưới dạng một `String`, không qua parser của shell.

## 21. Test 13 — imported profile-specific file

Khi một tài liệu có:

```properties
spring.config.import=feature.properties
```

Config Data còn có thể xét file biến thể theo profile, ví dụ `feature-dev.properties`.

Directory:

```text
import-profile/
├── application.properties
├── feature.properties
└── feature-dev.properties
```

Nội dung:

`application.properties`:

```properties
spring.config.import=feature.properties
lab252.flag=root
```

`feature.properties`:

```properties
lab252.flag=feature-base
```

`feature-dev.properties`:

```properties
lab252.flag=feature-dev
```

Test:

```java
@Test
void profileSpecificVariantOfImportCanWin()
        throws IOException {

    Path dir = tempDir.resolve("import-profile");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=feature.properties\n"
            + "lab252.flag=root\n");

    write(
            dir.resolve("feature.properties"),
            "lab252.flag=feature-base\n");

    write(
            dir.resolve("feature-dev.properties"),
            "lab252.flag=feature-dev\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri(),
            "--spring.profiles.active=dev")) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.flag"))
                .isEqualTo("feature-dev");
    }
}
```

Điểm cần hiểu là import không chỉ là “đọc một file bằng `Files.readString`”. Spring Boot tích hợp các imported resources vào cơ chế Config Data, trong đó có hỗ trợ profile-specific variants khi phù hợp.

## 22. Tập hợp mã test vào một class hoàn chỉnh

Các đoạn trước có thể đặt trong **một test class** như sau. Đây là khung cần giữ khi ghép các phương thức test đã trình bày.

`src/test/java/example/configlab/ConfigDataStartupTest.java`:

```java
package example.configlab;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;

class ConfigDataStartupTest {

    @TempDir
    Path tempDir;

    @SpringBootConfiguration(proxyBeanMethods = false)
    static class MinimalApplication {
    }

    private static ConfigurableApplicationContext start(
            String... arguments) {

        SpringApplication application =
                new SpringApplication(MinimalApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        return application.run(arguments);
    }

    private static Path write(Path file, String content)
            throws IOException {

        Files.createDirectories(file.getParent());
        Files.writeString(file, content, StandardCharsets.UTF_8);
        return file;
    }

    // Đặt tại đây các phương thức @Test ở mục 9–21.
}
```

Với khung trên, bạn chỉ cần **một lần khai báo** `@TempDir`, helper `start`, helper `write`, và nested `MinimalApplication`.

Không tạo một file Java chứa nhiều class public có cùng tên `ConfigDataStartupTest`. Các ví dụ ở từng mục là các phương thức để ghép vào class này.

### Lệnh chạy test

Maven wrapper:

```bash
./mvnw test
```

Chỉ chạy class cụ thể với Maven Surefire khi project phù hợp:

```bash
./mvnw -Dtest=ConfigDataStartupTest test
```

Gradle wrapper:

```bash
./gradlew test
```

Chạy class cụ thể:

```bash
./gradlew test --tests example.configlab.ConfigDataStartupTest
```

Nếu test chạy trong một module con, cần thêm thông tin module tương ứng khi gọi Gradle/Maven từ repository root.

## 23. Đừng dùng `System.setProperty` một cách bất cẩn

Để kiểm tra Java system properties có ưu tiên cao hơn Config Data, rất dễ viết:

```java
System.setProperty("lab252.mode", "from-jvm");
```

Vấn đề: Java system properties là **trạng thái toàn cục của JVM test**. Nếu không khôi phục, các test khác cùng process có thể bị ảnh hưởng. Test chạy song song càng dễ gây kết quả lúc đúng lúc sai.

Nếu buộc phải kiểm tra, hãy:

1. Lưu giá trị trước khi sửa.
2. Thiết lập một key test có prefix riêng.
3. Đảm bảo test không chạy song song với test khác cũng sửa key đó (JUnit ResourceLock hoặc cấu hình chạy nối tiếp phù hợp).
4. Khôi phục đúng trạng thái trước đó trong `finally`.
5. Không dùng key như `spring.config.location` toàn cục nếu nhiều context test khác có thể khởi động đồng thời.

Một cấu trúc bảo vệ:

```java
String key = "lab252.mode";
String previous = System.getProperty(key);

try {
    System.setProperty(key, "from-jvm");
    // Khởi động SpringApplication, assert, đóng context.
} finally {
    if (previous == null) {
        System.clearProperty(key);
    } else {
        System.setProperty(key, previous);
    }
}
```

Nếu chạy test suite song song, chỉ khôi phục trong `finally` **chưa đủ** để tránh race condition; cần cơ chế đồng bộ hoặc cô lập process.

Trong bài, chúng ta ưu tiên kiểm tra CLI-vs-file vì có thể làm hoàn toàn qua tham số `run(...)` mà không đổi trạng thái toàn cục.

## 24. Test dựa trên `SpringApplication.setDefaultProperties` có chứng minh precedence không?

`SpringApplication` hỗ trợ:

```java
application.setDefaultProperties(Map.of(
        "lab252.mode", "from-default"));
```

Đây là nguồn giá trị mặc định, thường có ưu tiên thấp hơn Config Data và CLI.

Một ví dụ minh họa:

```java
SpringApplication application =
        new SpringApplication(MinimalApplication.class);

application.setWebApplicationType(WebApplicationType.NONE);
application.setDefaultProperties(Map.of(
        "lab252.mode", "from-default"));

try (ConfigurableApplicationContext context = application.run(
        "--lab252.mode=from-cli")) {

    assertThat(context.getEnvironment()
            .getProperty("lab252.mode"))
            .isEqualTo("from-cli");
}
```

Nhớ import `java.util.Map`.

Nếu bỏ CLI nhưng có file config data chứa `lab252.mode=from-file`, giá trị file có thể thắng default.

**Không dùng `setDefaultProperties` để giả lập Java system properties.** Nó là một mức ưu tiên khác trong Spring `Environment`.

## 25. Vị trí file trên filesystem và working directory

Một file được tham chiếu bằng URI tuyệt đối:

```text
file:/opt/service/config/application.properties
```

không phụ thuộc vào working directory của Java process theo cùng cách với:

```text
file:./config/application.properties
```

Đường dẫn tương đối phụ thuộc nơi ứng dụng thực sự chạy. Khi dùng:

```bash
java -jar app.jar
```

working directory thường là thư mục terminal hiện tại. Khi dùng `bootRun`, IDE hoặc CI, working directory có thể khác.

Trong test, nên dùng:

```java
file.toUri()
```

từ `@TempDir` để tránh độ không ổn định.

Nếu muốn kiểm tra **chính cơ chế relative path**, hãy đặt điều kiện của working directory rõ ràng, tốt nhất trong một process riêng. Đừng sửa tùy tiện `System.setProperty("user.dir", ...)` trong một JVM có nhiều test; thay đổi thuộc tính đó không bảo đảm mọi thư viện và API file system sẽ coi như process thật đã đổi current directory.

### `classpath:` không phải `file:`

Hai location:

```text
classpath:/application.properties
file:/absolute/path/application.properties
```

có nguồn tài nguyên khác nhau:

- `classpath:` tìm trong classpath (thư mục class/resource hoặc JAR).
- `file:` tìm trên filesystem.

Một file có cùng tên trong hai nơi có thể được nạp tùy location, profile và precedence.

Với test về file ngoài, dùng `file:` và temp directory là cách nhìn trực tiếp vào cơ chế đó. Với test classpath, dùng `src/test/resources`.

## 26. `spring.config.location` là một property dùng quá sớm để đặt muộn

Giả sử một bean:

```java
@Component
public class LaterBean {
    @PostConstruct
    void init() {
        System.setProperty(
                "spring.config.location",
                "file:/later/application.properties");
    }
}
```

Cách làm này quá muộn cho kỳ vọng Boot **tự chạy lại toàn bộ Config Data search**.

Để test vị trí tìm file, đặt:

```java
start("--spring.config.location=" + file.toUri())
```

ngay trong startup arguments.

Hoặc ở runtime thực:

```bash
java -jar app.jar \
  --spring.config.location=file:/config/application.properties
```

hay:

```bash
java \
  -Dspring.config.location=file:/config/application.properties \
  -jar app.jar
```

Tài liệu Spring Boot nhấn mạnh `spring.config.name`, `spring.config.location`, `spring.config.additional-location` được đọc rất sớm; test cần đặt chúng ở nguồn có sẵn từ lúc đó.

## 27. Vấn đề giữa `@TestPropertySource` và `spring.config.import`

Một số test dùng:

```java
@TestPropertySource(properties = {
        "spring.config.import=extra.properties"
})
```

và kỳ vọng nó sẽ giống như `spring.config.import` xuất hiện trong `application.properties` ở giai đoạn Config Data discovery.

Không nên giả định như vậy. Test annotations tham gia vào Spring TestContext lifecycle và precedence riêng. **Thời điểm cấu hình** của chúng không nhất thiết tương đương một value được Config Data engine đọc tại thời điểm tìm/import tài liệu.

Nếu mục tiêu là kiểm chứng **import thật trong file**, hãy:

1. Viết file `application.properties` tạm có `spring.config.import=...`.
2. Đặt `spring.config.location` từ đối số startup.
3. Gọi `SpringApplication.run(...)`.
4. Assert các khóa trong imported file.

Tương tự, `@PropertySource` trên class Spring không tự hỗ trợ đầy đủ multi-document YAML hoặc profile activation theo cơ chế Config Data. Nó không thay thế một test startup.

## 28. Tại sao `ApplicationContextRunner` không phải bằng chứng đầy đủ cho mọi import?

Một test đơn giản:

```java
new ApplicationContextRunner()
        .withPropertyValues("lab252.mode=from-test")
        .run(context -> {
            assertThat(context.getEnvironment()
                    .getProperty("lab252.mode"))
                    .isEqualTo("from-test");
        });
```

chứng minh giá trị được thêm vào context runner. Nó **không tự chứng minh** engine đã đi tìm `application.properties`, xử lý profile-specific file, import tương đối, `optional:` và `spring.config.location` giống một `SpringApplication` khởi động thật.

`ApplicationContextRunner` rất hữu ích khi test auto-configuration và điều kiện bean. Bài này chọn `SpringApplication.run` để tránh dùng công cụ không đi qua đúng lifecycle mong muốn.

Một test “pass” không nên được diễn giải rộng hơn chức năng mà nó đã kích hoạt.

## 29. Kiểm thử `.properties` và YAML có giống nhau hoàn toàn không?

Cả hai đều có thể dùng Config Data, nhưng cú pháp file khác nhau.

File `.properties`:

```properties
lab252.mode=base
spring.config.import=extra.properties
```

YAML:

```yaml
lab252:
  mode: base

spring:
  config:
    import: extra.properties
```

Nếu cần test YAML, tạo file `.yaml` bằng `Files.writeString`, dùng `spring.config.location` trỏ tới URI file hoặc directory có basename phù hợp, rồi assert `Environment`.

Ví dụ:

```java
Path yaml = write(
        tempDir.resolve("yaml/application.yaml"),
        "lab252:\n"
        + "  mode: yaml\n");

try (ConfigurableApplicationContext context = start(
        "--spring.config.location=" + yaml.toUri())) {

    assertThat(context.getEnvironment()
            .getProperty("lab252.mode"))
            .isEqualTo("yaml");
}
```

Không nên cho rằng cú pháp `#---` của multi-document properties là cú pháp multi-document YAML. YAML sử dụng `---` trên dòng phân tách riêng. Test nào cần nhiều document phải tạo file đúng format và assert hành vi activation.

### Cùng vị trí có cả `.properties` và YAML

Spring Boot tài liệu hóa rằng nếu có cả `application.properties` và YAML ở cùng location với cùng basename, `.properties` có ưu tiên cao hơn. Tốt nhất nên **dùng một format nhất quán** cho một ứng dụng để giảm khó hiểu.

Nếu dự án có cả hai, có thể tạo hai file trong cùng temp directory, bật cùng location, và assert property trùng đến từ `.properties`. Đây là một test khác với precedence giữa file classpath và external.

## 30. Phân biệt file import tương đối với location tương đối

Có hai kiểu tương đối:

**A. Relative filesystem location**

```text
file:./config/application.properties
```

được giải quyết theo môi trường filesystem/working directory của process.

**B. Import-relative location**

Trong file `application.properties`:

```properties
spring.config.import=child/extra.properties
```

Import này được giải quyết theo vị trí của tài liệu chứa nó, không phải mặc nhiên theo `user.dir`.

Hai cơ chế này rất dễ bị gọi chung là “relative path”, nhưng test cần biết mình đang kiểm tra loại nào.

Nếu muốn file import luôn trỏ một đường dẫn cố định, dùng scheme rõ ràng (`file:`, `classpath:`) hoặc đường dẫn cố định được Spring Boot hỗ trợ.

## 31. `optional:` không phải “bỏ qua mọi lỗi cấu hình”

Ví dụ:

```properties
spring.config.import=optional:missing.properties
```

cho phép thiếu resource tương ứng.

Nhưng nếu file **tồn tại** và có:

```properties
lab252.number=not-a-number
```

rồi Binder cố chuyển thành `int`, ứng dụng vẫn có thể fail binding/validation. Prefix `optional:` không chữa lỗi nội dung giá trị.

Tương tự, nếu YAML hiện diện nhưng sai cấu trúc, lỗi đọc có thể làm startup thất bại. Một cấu hình production quan trọng cũng không nên dùng `optional:` tùy tiện chỉ để ứng dụng lên được với giá trị thiếu.

### Phân biệt ba loại test thất bại

| Loại | Ví dụ | Test nên kiểm tra |
| --- | --- | --- |
| Không tìm thấy location | `spring.config.import=missing.properties` | Startup thất bại do resource/location không có |
| Parse dữ liệu thất bại | YAML sai cú pháp | Startup thất bại do không đọc được file |
| Bind/validation thất bại | `demo.port=abc` hoặc `@Min(1)` với `0` | Startup không tạo được bean cấu hình |

Tất cả đều có thể khiến test fail, nhưng root cause và hướng sửa khác nhau.

## 32. Tách “file được nạp” và “giá trị thắng”

Một test chỉ làm:

```java
assertThat(environment.getProperty("lab252.mode"))
        .isEqualTo("from-cli");
```

không chứng minh file nào đã được nạp, vì CLI có thể thắng ngay cả khi file không tồn tại.

Thiết kế test tốt nên có **marker riêng** ở từng nguồn:

File classpath:

```properties
lab252.classpath-only=yes
lab252.shared=classpath
```

File external:

```properties
lab252.external-only=yes
lab252.shared=external
```

CLI:

```text
--lab252.shared=cli
```

Các assert:

```text
lab252.classpath-only = yes      -> classpath tham gia
lab252.external-only  = yes      -> external tham gia
lab252.shared         = cli      -> CLI thắng
```

Từ đó ta kiểm chứng được **presence** và **precedence**. Đây là điểm đặc biệt quan trọng khi phân tích `spring.config.additional-location`, import và location groups.

## 33. Không phụ thuộc vào tên `PropertySource` cố định

Spring Boot có thể tạo tên nguồn như:

```text
Config resource 'file [...]' via location '...'
```

Tên này hữu ích khi debug, nhưng có thể thay đổi theo phiên bản Spring Boot, đường dẫn thực tế, profile, URI, loader hoặc định dạng file.

Một test dễ vỡ:

```java
assertThat(environment.getPropertySources()
        .contains("Config resource '...' via location '...'"))
        .isTrue();
```

Nếu mục tiêu chỉ là chứng minh file được nạp, marker property thường ổn định hơn.

Khi cần xem nguồn chi tiết để chẩn đoán, có thể duyệt các nguồn và kiểm tra:

```java
for (PropertySource<?> source :
        environment.getPropertySources()) {
    System.out.println(source.getName());
}
```

Nhưng hãy dùng cách đó như **diagnostics**, không mặc định là public API có format tên bất biến.

Không in toàn bộ nội dung mỗi PropertySource, vì có thể chứa mật khẩu, token, connection string hoặc giá trị nhạy cảm.

## 34. Thử qua Java system property: cần khóa trạng thái toàn cục

Nếu test muốn chứng minh:

```text
CLI > Java system property > Config Data
```

có thể viết một test có `@ResourceLock` để phối hợp khi chạy song song.

Ví dụ về cấu trúc:

```java
@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
@Test
void cliWinsOverJvmProperty() throws IOException {

    String key = "lab252.mode";
    String before = System.getProperty(key);

    Path config = write(
            tempDir.resolve("sys-property/application.properties"),
            "lab252.mode=from-file\n");

    try {
        System.setProperty(key, "from-jvm");

        try (ConfigurableApplicationContext context = start(
                "--spring.config.location=" + config.toUri(),
                "--lab252.mode=from-cli")) {

            assertThat(System.getProperty(key))
                    .isEqualTo("from-jvm");

            assertThat(context.getEnvironment().getProperty(key))
                    .isEqualTo("from-cli");
        }
    } finally {
        if (before == null) {
            System.clearProperty(key);
        } else {
            System.setProperty(key, before);
        }
    }
}
```

Các import bổ sung:

```java
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;
```

Cơ chế lock có hiệu quả khi **các test khác cũng tuân thủ hợp đồng resource locking**; nó không thể ngăn mọi code bên ngoài JUnit tự sửa system properties. Không để test suite song song cùng sửa các khóa startup như `spring.config.location` mà không có biện pháp cô lập.

Đối với hầu hết bài học cấu hình, test bằng CLI và temp files dễ bảo trì hơn vì không cần đụng tới trạng thái toàn cục.

## 35. Test `SpringApplication` hay test `SpringApplicationBuilder`?

Cả hai đều có thể chạy ứng dụng theo Spring Boot lifecycle.

Ví dụ `SpringApplicationBuilder`:

```java
try (ConfigurableApplicationContext context =
        new SpringApplicationBuilder(MinimalApplication.class)
                .web(WebApplicationType.NONE)
                .run("--spring.config.location=" + config.toUri())) {

    assertThat(context.getEnvironment()
            .getProperty("lab252.mode"))
            .isEqualTo("expected");
}
```

`SpringApplicationBuilder` thuận tiện cho những tình huống có cấu hình phân tầng hoặc muốn fluent API. Nhưng trong bài này:

```java
new SpringApplication(MinimalApplication.class).run(args);
```

đã đủ rõ về các giai đoạn bootstrap được test.

Đừng cố thêm parent/child contexts hay nhiều builder levels chỉ để thử một property source. Làm thế khiến test khó hiểu và có thể thay đổi cơ chế kế thừa environment so với ứng dụng thật.

## 36. Thực nghiệm trực tiếp với `java -jar`

Sau khi các test programmatic thành công, bạn có thể đối chiếu bằng chạy JAR thật.

Giả sử:

```text
config/
├── application.properties
└── extras/
    └── feature.properties
```

`config/application.properties`:

```properties
spring.config.import=extras/feature.properties
lab252.mode=from-root
```

`config/extras/feature.properties`:

```properties
lab252.mode=from-import
```

Nếu có executable JAR, chạy:

```bash
java -jar app.jar \
  --spring.config.location=file:./config/application.properties
```

Khi app ghi nhận `Environment#getProperty("lab252.mode")`, giá trị có thể là `from-import`.

Thử tiếp:

```bash
java -jar app.jar \
  --spring.config.location=file:./config/application.properties \
  --lab252.mode=from-cli
```

Giá trị cuối có thể là `from-cli` vì command-line property có ưu tiên cao hơn config data.

**Đây là thực nghiệm bổ sung**, không thay thế tự động hóa. Lệnh phụ thuộc thư mục hiện tại, shell và artifact JAR đã được build.

### PowerShell tương đương

```powershell
java -jar .\app.jar `
  '--spring.config.location=file:./config/application.properties'
```

Hoặc một dòng:

```powershell
java -jar .\app.jar '--spring.config.location=file:./config/application.properties'
```

Khi location chứa `;` hoặc khoảng trắng, dấu nháy càng quan trọng để shell không phân tách sai argument.

## 37. Các quyết định thiết kế để test đáng tin cậy

Một bộ test Config Data nên có các đặc điểm:

1. **Minimal application:** tránh scan nhiều bean không liên quan.
2. **Không mở web server:** dùng `WebApplicationType.NONE`.
3. **Đóng context:** `try-with-resources`.
4. **File tạm theo từng test:** dùng `@TempDir`.
5. **URI tuyệt đối:** dùng `Path.toUri()`.
6. **Marker riêng:** phân biệt file được nạp với file thắng.
7. **Một ý chính mỗi test:** dễ tìm nguyên nhân khi fail.
8. **Không dựa vào nguồn toàn cục:** tránh system property/environment contamination.
9. **Không dựa vào working directory:** trừ khi đó là mục tiêu test.
10. **Không kiểm tra nguyên văn exception message dễ thay đổi** khi chỉ cần biết startup fail.
11. **Phân biệt absence của key với key có empty string hoặc null**.
12. **Không dùng temp file có chứa secret thật.**
13. **Cân nhắc test process riêng** nếu cần kiểm tra JVM options và current working directory thực.
14. **Không chạy nội dung nguy hiểm từ file cấu hình** như một script tự động trong test.
15. **Dùng đúng phiên bản Spring Boot** của dự án để kết quả phù hợp runtime thực tế.

Một bài test có nhiều nguồn nhưng chỉ assert một key rất dễ đưa ra kết luận quá rộng. Tài liệu hóa nguồn nào thắng và vì sao ngay trong tên test giúp nhóm bảo trì dễ hiểu.

## 38. Lỗi thường gặp khi viết các test này

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Test không tìm thấy external file | URI không đúng, thiếu prefix `file:` | Dùng `Path.toUri()` |
| Test tùy máy developer | Relative path phụ thuộc `user.dir` | Dùng `@TempDir` và URI tuyệt đối |
| `spring.config.location` khiến file classpath biến mất | Cơ chế replace default locations | Dùng `spring.config.additional-location` nếu muốn giữ defaults |
| `additional-location` không ghi đè như kỳ vọng | Có CLI/system property ưu tiên cao hơn | Kiểm tra tất cả PropertySources |
| Import tương đối tìm nhầm file | Tưởng relative import luôn tính từ shell | Xác định file chứa khai báo import |
| File không tồn tại làm startup fail | Không dùng `optional:` cho file tùy chọn | Thêm `optional:` ở đúng location |
| Bật profile mà kết quả không đổi | File profile sai basename hoặc location | Kiểm tra `application-<profile>` và thư mục |
| `spring.config.name` không hiệu lực | Đặt muộn hoặc không dùng directory đúng | Cấp khi startup, kiểm tra slash cuối |
| Test với dấu `;` lỗi trên shell | Shell coi `;` là phân tách lệnh | Quote toàn bộ value của option |
| Tên PropertySource đổi giữa các bản Boot | Test phụ thuộc tên nội bộ | Assert marker property và kết quả |
| `ApplicationContextRunner` pass nhưng import thật fail | Runner không chạy cùng Config Data lifecycle | Dùng `SpringApplication.run` |
| `@TestPropertySource` không tái tạo import | Giai đoạn test property source khác | Đặt import trong file nguồn Config Data |
| Test runtime chậm/hỏng do DB | Test app quét bean không liên quan | Dùng minimal `@SpringBootConfiguration` |
| Nhiều test ảnh hưởng nhau | Global `System.setProperty` hoặc file chung | Cô lập temp dir, khôi phục trạng thái |
| Test xanh dù file chưa được nạp | Chỉ assert giá trị trùng với default/CLI | Thêm marker unique mỗi nguồn |
| Test thất bại vì shell quote | String argument bị tách ngoài ý định | Khi test Java, truyền `String... args` trực tiếp |
| Test không nhận YAML | Lỗi đuôi file/cú pháp | Tạo `.yaml` đúng và dùng URI đầy đủ |
| Spring app chọn giá trị ngoài kỳ vọng | Có nguồn ưu tiên hơn file | Đọc `Environment`, profile và nguồn thực tế |
| `optional:` vẫn lỗi | File có nhưng nội dung lỗi hoặc lỗi khác | Phân biệt missing với parse/bind failure |
| Nhiều profiles cho kết quả khác dự đoán | Location group thay đổi thứ tự | Kiểm tra `,` và `;` |
| Dùng system property để đặt location sau khi context đã start | Config Data đã được xử lý | Đặt location ngay từ startup |

## 39. Khi nào nên kiểm tra cả `@ConfigurationProperties`?

Nếu mục tiêu chỉ là thứ tự nguồn, `Environment#getProperty()` đủ để xác định key có hiệu lực.

Nhưng khi cần chứng minh giá trị được liên kết vào model có kiểu:

```java
@ConfigurationProperties(prefix = "lab252")
public record LabProperties(
        String mode,
        int retryCount,
        Duration timeout
) {
}
```

cần đăng ký class cấu hình qua:

```java
@EnableConfigurationProperties(LabProperties.class)
```

trên minimal test application, hoặc dùng `@ConfigurationPropertiesScan` trong phạm vi phù hợp.

Sau khi khởi động:

```java
LabProperties properties = context.getBean(LabProperties.class);
```

rồi assert:

```java
assertThat(properties.mode()).isEqualTo("from-cli");
assertThat(properties.retryCount()).isEqualTo(3);
assertThat(properties.timeout()).isEqualTo(Duration.ofSeconds(5));
```

Lúc đó test bao phủ cả:

```text
Config Data -> Environment -> Binder -> typed object
```

**Nhưng không cần mở rộng mọi test trong bài thành binding test.** Nên giữ các test precedence riêng, rồi thêm một test binding đại diện. Tách biệt nguyên nhân giúp khi lỗi xảy ra biết nó đến từ tìm file hay converter/validation.

## 40. Các bài tập mở rộng

### Bài 1 — thay thế và bổ sung

Classpath có:

```properties
lab252.classpath-only=yes
```

External file có:

```properties
lab252.external-only=yes
```

Hỏi: lệnh dùng `spring.config.location` và lệnh dùng `spring.config.additional-location` khác nhau thế nào?

**Đáp án:** `location` thay thế default search locations; `additional-location` giữ default và nạp thêm external. Hãy assert marker riêng để chứng minh.

### Bài 2 — import thắng file khai báo

Root file:

```properties
spring.config.import=extra.properties
lab252.value=root
```

Imported file:

```properties
lab252.value=extra
```

Hỏi: giá trị có hiệu lực trong test startup là gì, nếu không có nguồn cao hơn?

**Đáp án:** `extra`, theo quy tắc imported config data có precedence hơn file khai báo import.

### Bài 3 — CLI override

External file:

```properties
lab252.mode=external
```

Args:

```text
--lab252.mode=cli
```

Hỏi: `Environment#getProperty("lab252.mode")` trả gì?

**Đáp án:** `cli` trong SpringApplication mặc định.

### Bài 4 — thiếu file bắt buộc

Root file:

```properties
spring.config.import=missing.properties
```

Hỏi: kết quả mong đợi?

**Đáp án:** Startup fail do không tìm thấy Config Data, trừ khi có chính sách xử lý thiếu location tương ứng.

### Bài 5 — thiếu file tùy chọn

Root file:

```properties
spring.config.import=optional:missing.properties
lab252.value=base
```

Hỏi: kết quả mong đợi?

**Đáp án:** App có thể khởi động và nhận `base`, miễn là không có lỗi khác.

### Bài 6 — import nhiều tầng

Root imports `sub/first.properties`, file đó imports `next/second.properties`.

Hỏi: import thứ hai được giải quyết từ đâu?

**Đáp án:** Tương đối với vị trí file `first.properties` chứa khai báo import thứ hai.

### Bài 7 — nhiều import

Root:

```properties
spring.config.import=a.properties,b.properties
```

Cả hai khai `lab252.x`.

Hỏi: file nào thường thắng?

**Đáp án:** Import về sau, `b.properties`, khi không có nguồn ưu tiên cao hơn.

### Bài 8 — profile

`application.properties` có `x=base`, `application-prod.properties` có `x=prod`, active profile `prod`.

**Đáp án:** File profile-specific có thể override base thành `prod`.

### Bài 9 — location group

Hai directory, một có `application-live.properties` giá trị `cfg-live`, một có `application-prod.properties` giá trị `ext-prod`. Active profiles `prod,live`.

Hỏi: `,` và `;` có thể làm kết quả khác nhau không?

**Đáp án:** Có. Dấu phẩy xử lý các location theo mức thứ tự; dấu chấm phẩy gộp cùng mức để quy tắc profile-specific quyết định theo group.

### Bài 10 — unit test mock

Một test chỉ gọi `new StandardEnvironment()` rồi tự thêm `MapPropertySource` và thấy `x=value`.

Hỏi: đã chứng minh `spring.config.import` hoạt động đúng chưa?

**Đáp án:** Chưa. Test chỉ chứng minh cách tự thêm source; cần SpringApplication startup thật để kiểm chứng Config Data.

### Bài 11 — working directory

Tại sao `file:./config/application.properties` đôi khi chạy được ở terminal nhưng lỗi trong IDE?

**Đáp án:** Working directory của process khác nhau. Dùng đường dẫn rõ ràng, hoặc kiểm tra `workingDir` và `user.dir`.

### Bài 12 — có marker nhưng key không thắng

Classpath có `lab252.marker=classpath`, external có `lab252.value=external`, CLI có `--lab252.value=cli`.

Hỏi: marker classpath vẫn có nhưng `value=cli` có mâu thuẫn không?

**Đáp án:** Không. Marker thể hiện file được nạp; `value=cli` thể hiện precedence. Hai kiểm tra phục vụ mục tiêu khác nhau.

### Bài 13 — app thật so với test tối thiểu

Nếu test tối thiểu pass nhưng app production vẫn không chạy, có thể kết luận Config Data lỗi không?

**Đáp án:** Chưa. App thật có thể có thêm `@ConfigurationProperties` validation, beans, connection dependencies, profile khác, system/env properties khác hoặc đường dẫn runtime khác.

### Bài 14 — test thiếu timeout

Nếu một key `lab252.timeout=invalid` được nạp thành `String`, test `Environment#getProperty` có thể vẫn thành công. Nhưng bean có `Duration timeout` sẽ ra sao?

**Đáp án:** Binding có thể thất bại vì chuyển kiểu. Hai tầng cần các test riêng.

## 41. Bảng kiểm cho một bộ test Config Data đáng tin cậy

- [ ] Test sử dụng cùng dòng Spring Boot với ứng dụng, ở đây là 3.3.x.
- [ ] Có bài test startup thật bằng `SpringApplication.run`.
- [ ] App test tối thiểu, không cần web server hoặc DB.
- [ ] Context được đóng sau mỗi test.
- [ ] Tệp cấu hình được tạo trong `@TempDir`.
- [ ] Đường dẫn test dùng `Path.toUri()` để tránh lệ thuộc Windows/Unix.
- [ ] File classpath marker đã được khai báo ở `src/test/resources`.
- [ ] Có test `spring.config.location` thay thế default locations.
- [ ] Có test `spring.config.additional-location` giữ default và nạp thêm.
- [ ] Có test `spring.config.import` và imported value thắng parent.
- [ ] Có test import-relative lồng nhau.
- [ ] Có test nhiều import và thứ tự.
- [ ] Có test `optional:` và file thiếu bắt buộc.
- [ ] Có test profile-specific variant.
- [ ] Có test CLI override config data.
- [ ] Có test file location và directory location.
- [ ] Có test `spring.config.name` khi cần.
- [ ] Có test location groups nếu hệ thống dùng nhiều profiles.
- [ ] Không sửa system properties toàn cục nếu không có cơ chế cô lập.
- [ ] Không dựa trên format tên `PropertySource` hoặc exception message thiếu ổn định.
- [ ] Có marker độc lập để chứng minh file được nạp.
- [ ] Các dữ liệu nhạy cảm không bị viết ra log.
- [ ] Test của Binder và validation được tách khỏi test precedence khi cần.
- [ ] Build/test chạy được trên Windows và Unix với những đường dẫn hợp lệ.
- [ ] Có thể chạy test nhiều lần mà không cần dọn file thủ công.

## 42. Tóm tắt

Một quy trình thực nghiệm tốt cho **Spring Boot Externalized Configuration** không dừng ở việc đọc tài liệu ưu tiên nguồn. Nó **tạo những tình huống xung đột có kiểm soát**, khởi động Spring Boot thực rồi assert kết quả.

```text
Tạo file tạm bằng @TempDir
          |
          v
Ghi application.properties và file được import
          |
          v
Truyền spring.config.location / additional-location
          |
          v
SpringApplication.run(...)
          |
          v
Config Data tìm file, xử lý profile/import/precedence
          |
          v
ConfigurableApplicationContext#getEnvironment()
          |
          v
Assert marker + key xung đột
          |
          v
Đóng ApplicationContext
```

Các quy tắc quan trọng nhất:

1. **Dùng `SpringApplication.run`** khi cần chứng minh quá trình tìm file và `spring.config.import` trong startup.
2. **`spring.config.location` thay thế**, còn **`spring.config.additional-location` bổ sung** default locations.
3. **Imported data có thể thắng tài liệu khai báo import**; import-relative được giải quyết theo file khai báo.
4. **CLI `--key=value` có mức ưu tiên cao** trong SpringApplication mặc định.
5. **Profile-specific files và location groups** có thể thay đổi kết quả precedence; `,` và `;` không đồng nghĩa.
6. **`@TempDir` và URI tuyệt đối** giúp bài test tái lập, không phụ thuộc máy/working directory.
7. **Dùng marker riêng cho mỗi nguồn** để chứng minh nguồn có được nạp, rồi dùng key trùng để chứng minh nguồn nào thắng.
8. **Tách kiểm thử cấu hình đầu vào khỏi kiểm thử binding/validation và phụ thuộc vận hành**, vì một test startup configuration pass chưa chứng minh toàn bộ ứng dụng production sẵn sàng.

Thực hành những test này biến kiến thức về thứ tự ưu tiên, import và location thành **bằng chứng tái lập được**, giúp nhóm phát triển và vận hành tránh những lỗi khó chẩn đoán khi cùng một JAR chạy ở nhiều môi trường.

## Tài liệu tham khảo

- Spring Boot 3.3 Reference — Externalized Configuration (PropertySource Order, Config Data, Import, Optional Locations, Profile Specific Files): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 API — SpringApplication: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 Reference — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Framework API — ConfigurableEnvironment: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html
- JUnit 5 User Guide — @TempDir: https://junit.org/junit5/docs/current/user-guide/
