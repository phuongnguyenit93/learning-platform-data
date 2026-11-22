# Classpath, tài nguyên kiểm thử và khác biệt với môi trường ứng dụng trong Spring Boot

## 1. Mục tiêu

Một ứng dụng có thể vượt qua `mvn test` hoặc `gradle test` nhưng lỗi khi chạy `java -jar`: thiếu file JSON/SQL, cấu hình sai, bean chỉ tồn tại trong test, hoặc thư viện chỉ được khai báo với scope test. Ngược lại, một test có thể đọc được `application-test.properties`, H2, Mockito và fixture mà ứng dụng triển khai không hề có. Để tìm nguyên nhân, cần hiểu ba thứ riêng biệt:

1. **Classpath của JVM** quyết định những class và resource nào trình nạp lớp có thể tìm thấy.
2. **Source set và dependency scope** quyết định những gì được đưa vào classpath khi biên dịch, chạy test, chạy ứng dụng và đóng gói.
3. **Cơ chế cấu hình của Spring Boot** quyết định property cuối cùng có giá trị gì sau khi kết hợp file, profile, biến môi trường, command line và override của test.

Sau bài này, bạn phải phân biệt được `src/main/resources` với `src/test/resources`, lý giải test classpath khác runtime classpath, dùng đúng `@ActiveProfiles`/`@TestPropertySource`/`@SpringBootTest(properties = ...)`, truy cập fixture không phụ thuộc working directory, và kiểm tra được artifact production có chứa hoặc không chứa resource mong muốn.

Phần thực hành dùng **Java 17+, Maven, Spring Boot 3.5.16, JUnit Jupiter**; trình bày thêm đường đi tương ứng trong Gradle. Các tên package/plugin có thể khác ở Spring Boot 4.x, nên khi nâng major version phải đối chiếu tài liệu của phiên bản đang dùng.

## 2. Classpath thực sự là gì?

Classpath là danh sách các **thư mục chứa class/resource** và **file JAR** mà một class loader có thể tìm kiếm. JVM có thể nạp `com.example.App` từ file `com/example/App.class`, và `ClassLoader.getResource("fixtures/order.json")` tìm `fixtures/order.json` theo đường dẫn **tương đối với gốc classpath**.

Classpath không đồng nghĩa với:
- Thư mục mã nguồn `src/main/java`, vì Java phải được biên dịch thành `.class`.
- Working directory nơi bạn gõ lệnh: `new File("...")` tìm đường dẫn hệ thống tệp; `classpath:...` tìm resource qua class loader.
- Spring `Environment`: đây là tập property sources hợp nhất, trong đó file trên classpath chỉ là một nguồn.
- Toàn bộ dependency trong `pom.xml`/`build.gradle`: scope/configuration quyết định dependency có hiện diện ở từng pha.
- Module path của JPMS (`--module-path`): Java module system có quy tắc khác classpath truyền thống; nhiều dự án Spring Boot vẫn dùng classpath khi chạy executable JAR.

Sơ đồ Maven mặc định:

```text
PROJECT/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/.../*.java       -> compile -> target/classes/.../*.class
│   │   └── resources/
│   │       ├── application.properties         -> target/classes/application.properties
│   │       └── templates/email.html            -> target/classes/templates/email.html
│   └── test/
│       ├── java/com/example/.../*Test.java     -> target/test-classes/.../*Test.class
│       └── resources/
│           ├── application-test.properties     -> target/test-classes/application-test.properties
│           └── fixtures/sample.json            -> target/test-classes/fixtures/sample.json
└── target/
    ├── classes/                               # output main
    ├── test-classes/                          # output test
    └── app.jar                                 # artifact cho runtime (không có test-classes)
```

Maven Surefire mặc định xây test runtime classpath theo thứ tự: **`target/test-classes` → `target/classes` → dependencies → các phần bổ sung được cấu hình**. Đây là mô hình quan trọng để hiểu resource trùng tên trong môi trường test. Gradle cũng có main/test source sets và outputs riêng, nhưng **không được suy ra mọi launcher/IDE có thứ tự classpath giống Surefire**; hãy kiểm tra runtime classpath thực tế khi debug.

## 3. Phân biệt các pha thực thi và phạm vi tài nguyên

| Hoàn cảnh | Mã nguồn/output thường dùng | Resources nhìn thấy | Dependencies điển hình |
| --- | --- | --- | --- |
| Biên dịch main | `src/main/java` → `target/classes` | `src/main/resources` được copy vào main output | Maven `compile`; `provided` cho biên dịch; Gradle `implementation`/`compileOnly` |
| Biên dịch test | `src/test/java` → `target/test-classes`, tham chiếu main | Main và test outputs theo quy trình build | Main dependencies + `test` scope/`testImplementation` cần cho biên dịch |
| Chạy test | Test classes + main classes + test/main resources | **Cả fixture test lẫn resource ứng dụng** | `spring-boot-starter-test`, Mockito, JUnit, JDBC test driver... nếu khai báo tương ứng |
| Chạy từ IDE hoặc `spring-boot:run`/`bootRun` | Main output và runtime dependencies; có thể được IDE/plugin tùy chỉnh | Mặc định là **main resources**; cấu hình riêng có thể thay đổi | Runtime classpath, không mặc định bao gồm mọi test dependency |
| Chạy executable JAR `java -jar` | App classes và resources trong artifact | `BOOT-INF/classes` + JAR dependencies trong `BOOT-INF/lib` và cấu hình ngoài | Các dependency được packaging plugin đưa vào artifact; thư viện test scope không được đưa vào mặc định |
| Chạy trong container/deployment | Artifact đã build + env/file mount/hạ tầng | Những gì nằm trong artifact và external config/mount được cung cấp | Phụ thuộc vào image, Java runtime, cách khởi chạy |

Các kết luận thiết thực:
- File `src/test/resources/fixtures/data.sql` thấy được khi `mvn test`, nhưng **không tự xuất hiện trong production JAR**.
- Nếu test dùng H2 dependency scope `test` còn deployment dùng PostgreSQL, các test có thể “xanh” dù query/dialect ở production khác.
- Không thể lấy “test chạy được từ IDE” làm bằng chứng rằng `java -jar` sẽ chạy được: IDE có thể bổ sung folders, VM options, working directory hoặc system properties.
- `@SpringBootTest` khởi tạo Spring context nhưng vẫn chạy trên **test classpath**. Nó không mô phỏng nguyên trạng classpath của artifact đã đóng gói.

## 4. Tài nguyên main và test: đặt ở đâu, đọc thế nào?

### 4.1. Quy tắc đặt file

| Tài nguyên | Đường dẫn gợi ý | Lý do |
| --- | --- | --- |
| Cấu hình mặc định của ứng dụng | `src/main/resources/application.properties` hoặc `application.yml` | Được đóng gói để sử dụng khi chạy app |
| Template/email, schema, tệp tĩnh cần tại runtime | `src/main/resources/templates/...`, `static/...`, `db/migration/...` | Có mặt trong artifact; đúng chuẩn directory convention |
| Profile config dành riêng cho test | `src/test/resources/application-test.properties` | Chỉ test classpath có; kích hoạt bằng `@ActiveProfiles("test")` hoặc cách tương đương |
| JSON/XML/CSV fixture và expected output | `src/test/resources/fixtures/...` | Không lẫn với dữ liệu production |
| SQL setup/cleanup test | `src/test/resources/sql/...` | Dùng bằng `@Sql("classpath:/sql/setup.sql")` hoặc code test |
| Cấu hình logger cho test | `src/test/resources/logback-test.xml` (khi dùng Logback) | Điều chỉnh log test mà không đưa vào app JAR |
| Cấu hình thay thế chỉ cho test Spring | `src/test/java/.../*TestConfig.java` hoặc nested `@TestConfiguration` | Nằm trong test source set; import có kiểm soát |

Cần phân biệt:
- `src/main/resources/config/settings.json` được chép vào gốc classpath theo đường dẫn `config/settings.json`, **không** phải `src/main/resources/config/settings.json`.
- Java code dùng `getResourceAsStream("config/settings.json")` hoặc Spring `new ClassPathResource("config/settings.json")`; **không** dùng đường dẫn nguồn `src/...` để truy cập runtime.
- `getClass().getResource("/config/settings.json")` có dấu `/` đầu vì tra từ gốc classpath; `ClassLoader#getResource("config/settings.json")` **không** có dấu `/` đầu. Không trộn hai quy ước này.
- Resource bên trong JAR có thể không có đường dẫn file-system thông thường. `ClassPathResource#getInputStream()` dùng được; `getFile()` có thể thất bại khi resource nằm trong JAR. Chỉ dùng `Path`/`File` nếu thật sự là external file.

### 4.2. Khi trùng tên resource, điều gì xảy ra?

Giả sử có đồng thời:

```text
src/main/resources/application.properties    demo.mode=main
src/test/resources/application.properties    demo.mode=test
```

Trong nhiều cách chạy test (bao gồm thứ tự Surefire mặc định), file ở `test-classes` được tìm thấy trước khi tra file cùng đường dẫn ở `classes`. Với cơ chế nạp config, điều này dễ dẫn tới việc giá trị hoặc toàn bộ file ở main bị che khuất; kết quả còn phụ thuộc cách Spring Boot thu thập config locations/import. **Không thiết kế test dựa trên một giả định ngầm rằng hai file cùng tên được hợp nhất theo thứ tự mong muốn**.

Mẫu rõ ràng hơn:

```properties
# src/main/resources/application.properties
demo.mode=main
demo.timeout=3s
```

```properties
# src/test/resources/application-test.properties
demo.mode=test
```

Dùng `@ActiveProfiles("test")` để nạp cấu hình profile tương ứng; property không được override vẫn có thể lấy từ cấu hình cơ sở. Nếu môi trường test cần khác biệt rất lớn, dùng một profile/cấu hình test đầy đủ, có test kiểm tra giá trị quan trọng, thay vì dựa vào resource shadowing khó phát hiện.

Với các file như `messages.properties`, `schema.sql`, `logback.xml`, `application.properties` và `META-INF/...`, hãy đặc biệt cẩn thận khi trùng tên vì framework có quy tắc khám phá và ưu tiên riêng. Một số API dùng `getResource` (lấy resource đầu tiên), một số dùng `getResources` (thu thập nhiều resource). Đừng suy rộng quy tắc của cái này sang cái kia.

## 5. Dependency scope: lý do classpath của test “rộng” hơn

### Maven

```xml
<dependencies>
  <!-- Có mặt trong code/application runtime -->
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
  </dependency>

  <!-- Chỉ dùng khi biên dịch/chạy test -->
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

| Maven scope | Ý nghĩa thực tế |
| --- | --- |
| `compile` (mặc định) | Cần cho compile và runtime, đồng thời test cũng thấy |
| `runtime` | Không bắt buộc cho main compile; hiện diện khi chạy ứng dụng và test |
| `test` | Dùng cho test compile và test runtime; **không** trở thành dependency runtime production theo mặc định |
| `provided` | Dự án mong đợi môi trường cung cấp thư viện; cách đóng gói trong executable JAR/WAR còn phụ thuộc Spring Boot packaging và plugin, không suy luận bằng tên scope |

Dùng Maven BOM/`spring-boot-starter-parent` để đồng bộ phiên bản. Khi thấy `NoSuchMethodError`, `ClassNotFoundException` hay `NoClassDefFoundError`, trước tiên đối chiếu **dependency graph thực tế** ở test và runtime; lỗi có thể do thiếu thư viện hoặc phiên bản xung đột, không phải file resource.

```bash
mvn dependency:tree -Dscope=test
mvn dependency:tree -Dscope=runtime
mvn help:effective-pom
```

### Gradle

Trong dự án đã cấu hình plugin Java và Spring Boot:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    // testRuntimeOnly("...") nếu thư viện chỉ cần lúc chạy test
}

tasks.test {
    useJUnitPlatform()
}
```

Đây là **đoạn cấu hình phụ thuộc** trong `build.gradle.kts`, không phải toàn bộ build script; Spring Boot version/BOM/plugin cần được khai báo ở phần còn lại của dự án. Gradle cung cấp `sourceSets.main` và `sourceSets.test`; task `test` chạy với `sourceSets.test.runtimeClasspath`. Có thể xem:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew test --info
```

Trên Windows, dùng `gradlew.bat` tương ứng. Nếu tự tạo `integrationTest` source set hoặc JVM Test Suite, phải chủ động định nghĩa dependencies, outputs, runtimeClasspath và task để tránh nhầm rằng integration tests mặc định thấy mọi test fixture.

**Bẫy:** thêm mock/test driver vào `implementation` chỉ để “hết lỗi class not found” có thể làm tăng dependency production hoặc thay đổi auto-configuration. Chỉ di chuyển dependency sang runtime chính nếu ứng dụng **thật sự cần** nó tại runtime.

## 6. Spring Boot đọc cấu hình trên test classpath như thế nào?

Resource xuất hiện trên classpath **không có nghĩa** Spring luôn tự đọc resource ấy thành property. Spring Boot nhận diện `application.properties`/`application.yml` và biến thể theo profile; một file tên `fixtures/sample.properties` không tự thành environment property nếu không được import hoặc khai báo.

### 6.1. Các công cụ quan trọng

| Cách cấu hình | Tác dụng | Dùng khi |
| --- | --- | --- |
| `@ActiveProfiles("test")` | Kích hoạt Spring profile, từ đó xem xét `application-test.properties` và bean theo `@Profile` | Phần lớn integration/slice tests cần cấu hình test nhất quán |
| `@SpringBootTest(properties = "demo.mode=inline")` | Override property khi tạo Spring Boot test context | Một test cần thay một vài giá trị rõ ràng |
| `@TestPropertySource(properties = "demo.mode=inline")` | Thêm property trực tiếp vào test `Environment` | Kiểm thử Spring context với override cụ thể |
| `@TestPropertySource(locations = "classpath:config/override.properties")` | Tải file properties tại vị trí được chỉ định | Một nhóm test dùng file cấu hình riêng |
| `@DynamicPropertySource` | Đăng ký giá trị động (ví dụ URL/port Testcontainers) | Giá trị chỉ biết sau khi hạ tầng test khởi chạy |
| `System.setProperty(...)` trong test | Chạm trạng thái global của JVM | **Không ưu tiên**; dễ rò sang test khác hoặc ảnh hưởng context cache |
| `spring.config.import` | Import config data theo cơ chế Spring Boot | Khi app/test cần chia nhỏ tập cấu hình có kiểm soát |

Điểm khác biệt: `@ActiveProfiles("test")` **không tự tạo** `application-test.properties` và không làm cho file dưới `src/test/resources` xuất hiện trong production JAR. Profile chỉ ảnh hưởng cách Spring xét và áp dụng nguồn cấu hình **đang hiện diện**.

Có thể dùng `@TestPropertySource("classpath:config/custom.properties")` để đọc `src/test/resources/config/custom.properties`. Với Spring Framework 6.x, `@TestPropertySource` mặc định hỗ trợ tệp `.properties` (và XML properties); đừng coi `@TestPropertySource("...yml")` là hợp lệ nếu chưa cấu hình factory phù hợp. Muốn dùng YAML theo cơ chế chuẩn Spring Boot, chọn `application-{profile}.yml` hoặc config data import phù hợp.

### 6.2. Không có “một thứ tự ưu tiên” cho mọi trường hợp

Spring Boot kết hợp nguồn cấu hình theo precedence của `Environment`. Ví dụ thường thấy:
- `application.properties` cung cấp mặc định.
- `application-test.properties` override các key tương ứng khi profile `test` hoạt động.
- Biến môi trường, Java system properties, command-line arguments có thể override file config (theo precedence và cách chạy).
- Property được khai báo ở test annotation và dynamic test property source thường override cấu hình file.
- File cấu hình ngoài JAR có thể override file trong JAR.

Precedence chi tiết phụ thuộc **phiên bản**, cơ chế `ConfigData`, test annotations và custom property sources. Không kết luận từ vị trí file đơn thuần. Nếu giá trị không như mong đợi, đọc `Environment#getProperty` trong test và xem provenance qua `ConfigurableEnvironment#getPropertySources()`; với hệ thống thật, Actuator `env`/`configprops` chỉ nên bật trong môi trường và chính sách bảo mật thích hợp.

Ví dụ một property “bị đổi” do CI:

```text
application.properties:             demo.mode=main
application-test.properties:        demo.mode=test
CI environment DEMO_MODE:           ci
@SpringBootTest(properties=...):    demo.mode=inline
```

Nhìn từng file riêng sẽ khó suy ra giá trị cuối. Hãy viết assertion nêu rõ hợp đồng của test và kiểm tra tác động của nguồn override. Đồng thời tránh tùy tiện đặt `spring.profiles.active` trong chính file profile-specific; profile nên được quyết định tại launch/test annotation hoặc cấu hình hợp lệ theo tài liệu.

## 7. Thực hành hoàn chỉnh: chứng minh khác biệt test và packaged app

Dự án dưới đây có thể biên dịch/chạy bằng Maven, Java 17+. Mục tiêu là quan sát rõ:
- Test đọc được **main resource + test-only fixture**.
- `@ActiveProfiles("test")` nạp `application-test.properties` từ test classpath.
- Test override có chủ đích có giá trị khác file profile.
- JAR được đóng gói **không** có fixture hay profile config đặt trong `src/test/resources`.
- Việc kích hoạt profile `test` khi chạy JAR **không thể tự mang test resource vào JAR**.

### 7.1. Cây file

```text
classpath-lab/
├── pom.xml
├── src/main/java/com/example/classpathlab/
│   └── ClasspathLabApplication.java
├── src/main/resources/
│   ├── application.properties
│   └── fixtures/public-message.txt
└── src/test/
    ├── java/com/example/classpathlab/
    │   ├── ClasspathResourceTest.java
    │   ├── ProfileConfigTest.java
    │   └── InlineConfigTest.java
    └── resources/
        ├── application-test.properties
        └── fixtures/test-message.txt
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>classpath-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
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
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

`spring-boot-starter-test` mang JUnit Jupiter và phần hỗ trợ Spring Test đến **test classpath**. Ví dụ không cần web server, datasource hay thư viện ngoài khác.

### 7.3. Main application

`src/main/java/com/example/classpathlab/ClasspathLabApplication.java`:

```java
package com.example.classpathlab;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ClasspathLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ClasspathLabApplication.class, args);
    }

    @Bean
    CommandLineRunner printMode(Environment environment) {
        return args -> System.out.println(
                "MODE=" + environment.getProperty("demo.mode", "missing"));
    }
}
```

Ứng dụng chỉ in một giá trị và kết thúc (không có web server), để việc kiểm tra khác biệt classpath dễ quan sát. Spring Boot vẫn có thể in thêm log khởi động, nhưng **dòng bắt đầu bằng `MODE=`** là output xác định của ví dụ khi không có override ngoài.

Nội dung đúng từng file:

```properties
# src/main/resources/application.properties
demo.mode=main
```

```text
# src/main/resources/fixtures/public-message.txt
MAIN_RESOURCE
```

```properties
# src/test/resources/application-test.properties
demo.mode=test
```

```text
# src/test/resources/fixtures/test-message.txt
TEST_FIXTURE
```

**Chú ý:** trong hai khối `text` chứa fixture, dòng `# src/...` chỉ là **chú thích minh họa vị trí file trong tài liệu**, không phải nội dung phải chép vào fixture. Mỗi fixture thực tế chứa duy nhất một dòng `MAIN_RESOURCE` hoặc `TEST_FIXTURE` (có thể có newline cuối file). Tương tự, với `.properties` các dòng bắt đầu `#` là comment hợp lệ.

### 7.4. Test #1: tài nguyên main và test đều nằm trên test classpath

`src/test/java/com/example/classpathlab/ClasspathResourceTest.java`:

```java
package com.example.classpathlab;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class ClasspathResourceTest {

    @Test
    void testRuntimeSeesBothResourceSets() throws IOException {
        assertEquals("MAIN_RESOURCE",
                readRequired("fixtures/public-message.txt"));
        assertEquals("TEST_FIXTURE",
                readRequired("fixtures/test-message.txt"));
    }

    private static String readRequired(String path) throws IOException {
        ClassLoader loader = Thread.currentThread().getContextClassLoader();
        try (InputStream stream = loader.getResourceAsStream(path)) {
            assertNotNull(stream, "Không tìm thấy resource: " + path);
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }
    }
}
```

Đây là **JUnit unit test thuần Java**, không khởi tạo Spring context. Nó kiểm được rằng build đã đưa đúng cả hai tập resources vào test runtime. `InputStream` hoạt động được cho file trong thư mục lẫn file bên trong JAR. `strip()` chỉ loại khoảng trắng/xuống dòng đầu-cuối để fixture nhất quán trên Windows/Linux; nếu whitespace là một phần của hợp đồng, đừng `strip()` mà so sánh byte hoặc text chính xác.

Nếu đặt nhầm `test-message.txt` tại `src/test/java` trong một dự án có build config chỉ xử lý `src/test/resources`, test có thể không tìm thấy. Không suy đoán IDE sẽ luôn tự copy file ngoài resource directory.

### 7.5. Test #2: profile test làm thay đổi config

`src/test/java/com/example/classpathlab/ProfileConfigTest.java`:

```java
package com.example.classpathlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class ProfileConfigTest {
    @Autowired Environment environment;

    @Test
    void usesProfileSpecificTestProperties() {
        assertEquals("test", environment.getProperty("demo.mode"));
    }
}
```

`@SpringBootTest` tạo context bằng cơ chế Spring Boot trên test classpath, trong khi `@ActiveProfiles("test")` làm Spring xét `application-test.properties`. Việc test đọc được file **không** chứng minh file này có trong production artifact.

### 7.6. Test #3: override tường minh ở annotation

`src/test/java/com/example/classpathlab/InlineConfigTest.java`:

```java
package com.example.classpathlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = "demo.mode=inline")
@ActiveProfiles("test")
class InlineConfigTest {
    @Autowired Environment environment;

    @Test
    void inlineTestPropertyOverridesProfileFile() {
        assertEquals("inline", environment.getProperty("demo.mode"));
    }
}
```

Bài test này minh họa rằng cùng test classpath và cùng profile nhưng property có thể khác do annotation. Dùng cách này cho các thay đổi nhỏ, được kiểm chứng bằng assertion; đừng trộn nhiều override giống nhau đến mức không xác định được nguồn giá trị.

### 7.7. Chạy kiểm thử và đóng gói

Trong thư mục chứa `pom.xml`:

```bash
mvn -q clean test
mvn -q package
jar tf target/classpath-lab-0.0.1-SNAPSHOT.jar
java -jar target/classpath-lab-0.0.1-SNAPSHOT.jar
java -jar target/classpath-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=test
java -jar target/classpath-lab-0.0.1-SNAPSHOT.jar --demo.mode=cli
```

Diễn giải kết quả mong đợi:

| Lệnh / quan sát | Kỳ vọng |
| --- | --- |
| `mvn -q clean test` | Ba lớp test vượt qua assertion; Maven exit code 0 (log có thể khác từng môi trường) |
| `mvn -q package` | Tạo executable JAR; mặc định Maven chạy test trong lifecycle trước khi package |
| `jar tf ...` | Có `BOOT-INF/classes/application.properties` và `BOOT-INF/classes/fixtures/public-message.txt` |
| `jar tf ...` | **Không** có `BOOT-INF/classes/fixtures/test-message.txt` hoặc `BOOT-INF/classes/application-test.properties` từ `src/test/resources` |
| `java -jar ...` | Trong log có dòng `MODE=main` |
| `java -jar ... --spring.profiles.active=test` | Trong ví dụ này vẫn có `MODE=main` vì JAR không chứa file test profile |
| `java -jar ... --demo.mode=cli` | Trong log có dòng `MODE=cli` vì command-line override cấu hình file |

Điều kiện: chạy trong thư mục dự án sạch, không đặt thêm `application-test.properties`/`application.properties` ngoài JAR, không set `DEMO_MODE` hoặc system property cùng key. Những nguồn cấu hình ngoài có thể làm output thay đổi theo cơ chế override bình thường. Nếu chỉ muốn dòng `MODE=...`, lọc log tại terminal; không coi các dòng banner/log Spring là stdout cố định.

Lưu ý: nội dung dạng `text` của fixture cần tạo **đúng như phần mô tả** (chỉ giá trị), không chép dòng mô tả đường dẫn làm dữ liệu test. Khi JAR đã đóng gói, Java đọc `fixtures/public-message.txt` theo tên classpath ở runtime; đường dẫn `src/main/resources` không phải một thành phần runtime.

## 8. Sự khác biệt còn đến từ Spring context, không chỉ từ resource

Một số nguồn gây chênh lệch giữa test và application rất thường gặp:

### 8.1. Auto-configuration phản ứng với classpath

Spring Boot quyết định nhiều auto-configuration dựa trên **class có sẵn** và **bean có sẵn**. Khi test có các starter hoặc driver mới, context có thể đổi:
- Có H2 test dependency: cấu hình database nhúng có thể xuất hiện trong test nếu điều kiện auto-config phù hợp; production không có H2 và dùng datasource khác.
- Có hoặc không có Spring MVC/WebFlux: loại web context được chọn có thể khác. Khi cả hai cùng có mặt, Spring Boot có quy tắc ưu tiên được ghi trong tài liệu.
- Có library kiểm thử hoặc các `@MockitoBean`: bean đang sử dụng trong test có thể được thay bằng mock.
- Test slice `@WebMvcTest`/`@DataJpaTest` chỉ bật một phần cấu hình; `@SpringBootTest` bật nhiều hơn nhưng vẫn chịu ảnh hưởng của test classpath.

Vì vậy, `@SpringBootTest` “load context thành công” chưa đủ chứng minh rằng executable JAR chạy với đúng profile/driver/config ở container. Nếu một behavior phụ thuộc PostgreSQL dialect, transaction, broker, TLS hoặc native library, cần integration test với hạ tầng và cấu hình phù hợp.

### 8.2. `@TestConfiguration`, bean quét nhầm và package layout

`@SpringBootTest` thường tự tìm class `@SpringBootApplication` bằng cách đi ngược lên các package cha từ package của test. Nếu đặt test ở package không liên quan hoặc nhiều cấu hình root, có thể cần `classes = YourApplication.class`.

Có thể thêm bean hỗ trợ test bằng nested `@TestConfiguration` hoặc import một top-level `@TestConfiguration` trong `src/test/java`:

```java
// Minh họa: đặt bên trong một lớp @SpringBootTest
@TestConfiguration(proxyBeanMethods = false)
static class StubConfiguration {
    @Bean
    ExternalClock externalClock() {
        return () -> java.time.Instant.parse("2026-01-01T00:00:00Z");
    }
}
```

Đoạn trên **chỉ minh họa cơ chế**, không phải file chạy độc lập: `ExternalClock` là interface do ứng dụng phải tự định nghĩa. Nested `@TestConfiguration` bổ sung cấu hình cho test; `@Configuration` lồng vào test có thể thay đổi cách chọn cấu hình gốc của Spring Boot. Test configuration đặt ngoài nên được import rõ ràng và tránh bị component scan nhặt nhầm; không đặt stub của test trong `src/main/java`.

### 8.3. Property phụ thuộc môi trường thật

Cấu hình có thể khác dù classpath không đổi:
- Test chạy local có `SPRING_PROFILES_ACTIVE=test` từ IDE, CI không có.
- CI có `DATABASE_URL`, `SPRING_DATASOURCE_URL`, `JAVA_TOOL_OPTIONS`, timezone/locale khác máy dev.
- Container mount `/config/application.properties` ngoài JAR; file ngoài có thể override giá trị trong artifact.
- Testcontainers tạo port động; hard-code `localhost:5432` có thể sai. Dùng `@DynamicPropertySource` hoặc service connection được Spring Boot hỗ trợ, tùy phiên bản.
- `@Transactional` test rollback không có nghĩa request qua web server thật cũng rollback: `RANDOM_PORT` hoạt động trên transaction phía server riêng với client/test.

Đánh giá environment cần test bằng **đúng loại context** và **đúng biên giới hạ tầng**. Với unit test thuần Java, `@ActiveProfiles` không có tác dụng nếu không có Spring TestContext khởi tạo.

## 9. Khi nào dùng `classpath:`, `file:` và đường dẫn tuyệt đối?

| Phương án | Ví dụ | Mục đích |
| --- | --- | --- |
| Class loader | `loader.getResourceAsStream("fixtures/order.json")` | Đọc fixture trong test classpath hoặc resource đóng gói |
| Spring resource | `new ClassPathResource("templates/mail.html").getInputStream()` | Cách đọc resource Spring có thể chạy cả trong JAR |
| Resource location trong annotation | `@Sql("classpath:/sql/seed.sql")` | Định vị file SQL trên classpath của test |
| External file | `Path.of("/etc/myapp/config.json")` | File nằm ngoài JAR và được triển khai/mount rõ ràng |
| Spring external config | `--spring.config.additional-location=file:./config/` | Nạp cấu hình ngoài artifact theo cơ chế config data |

**Không** làm như sau cho file được đóng gói:
```java
// Sai trong executable JAR hoặc CI chạy khác working directory:
var path = java.nio.file.Path.of("src/test/resources/fixtures/order.json");
var text = java.nio.file.Files.readString(path);
```

File trên có thể tồn tại trong source checkout nhưng không tồn tại trong container hoặc lúc chạy JAR. Thay bằng `getResourceAsStream` khi mục tiêu là classpath; nếu dữ liệu thật sự cần nằm bên ngoài, thiết kế external path và quy trình cung cấp file đó rõ ràng.

Một lỗi khác là thêm `/` vào đầu đường dẫn cho `ClassLoader#getResourceAsStream`. Với class loader, dùng `"fixtures/order.json"`; với `Class#getResourceAsStream`, dùng `"/fixtures/order.json"` để chỉ root classpath.

## 10. Chẩn đoán lỗi theo triệu chứng

| Triệu chứng | Giả thuyết cần kiểm | Kiểm tra/sửa đúng chỗ |
| --- | --- | --- |
| `getResourceAsStream(...) == null` trong test | File sai folder, sai chữ hoa/thường, không qua `process-test-resources`, path có `src/...` | Xem `target/test-classes`/`build/resources/test` và key đường dẫn root-classpath |
| Chạy IDE được, Maven/Gradle CI lỗi | IDE thêm resource folder, working directory hoặc env khác | Chạy `mvn clean test`/`gradle clean test` tại terminal, so sánh VM options và test task |
| Test đọc nhầm `application.properties` | File cùng tên ở test/main shadow nhau hoặc config import khác | Tách `application-test.properties`, bật profile, assert key và kiểm property sources |
| `@ActiveProfiles("test")` nhưng giá trị vẫn là main | File `application-test.properties` không có trên test classpath; key sai; nguồn ưu tiên cao override | Xem `target/test-classes/application-test.properties`, `Environment` và nguồn override |
| `java -jar` không thấy fixture | Fixture chỉ có trong `src/test/resources`, không được package | Đọc `jar tf`; nếu app runtime thực sự cần, chuyển resource sang main hoặc cung cấp external file |
| `ClassNotFoundException` chỉ ở production | Dependency cần tại runtime bị khai báo `test` hoặc `compileOnly` sai | So sánh dependency runtime với test; sửa scope/configuration |
| `NoSuchMethodError` trên CI | Xung đột phiên bản dependency/classpath order | Dùng dependency tree/runtimeClasspath để tìm JAR thắng cuối |
| Bean test hoạt động, production thiếu bean | Bean chỉ ở `src/test/java`/`@TestConfiguration` hoặc profile test | Xác định bean cần cho production và chuyển định nghĩa thật sang main |
| Test DB H2 qua, PostgreSQL lỗi | Driver/dialect/query/migration khác môi trường | Test bằng PostgreSQL Testcontainers và migration thật |
| `getFile()` lỗi trong executable JAR | Classpath resource nằm trong JAR, không phải file thường | Dùng `InputStream`, trích ra temp file nếu API bên ngoài bắt buộc nhận `File` |
| Fixture không cập nhật sau sửa | Resource output cũ, incremental build hoặc IDE copy chưa chạy | Chạy clean/process-test-resources, so nội dung output và nguồn |
| Test khi chạy riêng qua nhưng chạy suite fail | Global system properties, static state, context cache, file chung | Cô lập test data/clock/property, tránh `System.setProperty` toàn cục |

Quy trình debug tối thiểu:

1. **Xác định pha lỗi:** test compile, test runtime, dev run, `java -jar` hay container? Mỗi pha có classpath khác.
2. **Kiểm output thực:** Maven `target/classes` và `target/test-classes`; Gradle `build/resources/main` và `build/resources/test`. Đừng chỉ nhìn nguồn.
3. **Kiểm artifact:** `jar tf ...` để xem file thực được đóng gói; với Spring Boot executable JAR thường là `BOOT-INF/classes/...`.
4. **Kiểm dependency graph:** so test/runtime configurations; đừng thêm thư viện vô tội vạ.
5. **Kiểm config active:** profile, external config location, environment variables, test annotation overrides.
6. **Tạo phép kiểm nhỏ nhất:** assertion đọc resource cụ thể hoặc `Environment#getProperty`, thay vì bật DEBUG cho toàn bộ ứng dụng ngay lập tức.

Khi thực sự cần kiểm từ đâu một resource được load:

```java
// Đặt trong một phương thức Java có thể chạy, ví dụ phương thức @Test.
var loader = Thread.currentThread().getContextClassLoader();
var url = loader.getResource("fixtures/public-message.txt");
System.out.println(url == null ? "NOT_FOUND" : url.toExternalForm());
```

Đoạn trên là **minh họa**: URL sẽ phụ thuộc môi trường và class loader (`file:...` lúc test, `jar:...` hoặc định dạng khác lúc chạy từ JAR), vì vậy không khẳng định một output URL cố định. Chỉ in URL/path khi không làm lộ đường dẫn bí mật hay token.

## 11. Thiết kế tài nguyên test để CI và production đáng tin

### Tổ chức và đặt tên

- Tập trung fixture dưới `src/test/resources/fixtures/<feature>/...`; tên thể hiện đầu vào, trường hợp biên và expected output, ví dụ `fixtures/orders/invalid-quantity.json`.
- Dùng UTF-8 nhất quán; tránh test phụ thuộc default charset, line ending CRLF/LF hoặc chữ hoa/thường của filesystem.
- Không chứa mật khẩu, API key hoặc dữ liệu khách hàng thật trong fixture/config commit lên repository. Dùng dữ liệu giả và cấp secret qua cơ chế CI/test environment đã được kiểm soát.
- Tách test configuration khỏi main configuration để đánh giá nội dung sẽ đóng gói; tránh “để tiện” mà đưa `application-test.properties`, mock, driver test vào `src/main/resources`.
- Khi cần resource production (template, migration, JSON schema), đặt ở main và có test truy cập resource đó; đừng giữ bản duy nhất trong test.
- Khi nhiều test cần dùng chung fixture, cân nhắc module test fixtures/test-jar có dependency riêng, kiểm soát scope và version, tránh copy file xuyên module không có hợp đồng rõ ràng.
- Nếu bật Maven resource filtering hoặc Gradle `processTestResources` expansion, bảo đảm chuỗi `${...}` trong JSON/YAML/test fixture không bị thay nhầm và kiểm byte output; với Spring Boot Maven parent, delimiter cấu hình có thể khác dự án Maven thuần.

### CI và vòng đời build

Một pipeline khả thi:
1. Chạy `mvn clean test` hoặc `./gradlew clean test` để xác nhận test runtime classpath từ checkout sạch.
2. Chạy `mvn package` hoặc `./gradlew bootJar` và kiểm artifact xuất ra.
3. Với smoke test quan trọng, chạy **artifact đã đóng gói** trên profile/config tương tự môi trường triển khai; đây là phép kiểm riêng với `@SpringBootTest`.
4. Dùng container/emulated infrastructure khi behavior phụ thuộc DB, broker, cache, filesystem, hostname hoặc quyền.
5. Ghi lại môi trường tái lập: JDK, plugin, active profiles, runtime args, env và source của property, nhưng không ghi secret vào log.

**Lưu ý quản trị test:** `@DirtiesContext`, vô số cấu hình `@SpringBootTest(properties=...)` khác nhau và `@DynamicPropertySource` với giá trị thay đổi có thể giảm tái sử dụng Spring test context cache. Tối ưu thời gian build bằng cách dùng cấu hình nhất quán, nhưng không hy sinh cô lập hay giả lập hạ tầng sai.

## 12. Checklist cuối bài

Trước khi kết luận một lỗi là “do Spring Boot” hoặc “do CI”, tự trả lời:

- [ ] Tôi đang nói đến **test classpath**, **main runtime classpath** hay **packaged artifact**?
- [ ] Resource đang ở `src/main/resources` hay `src/test/resources`? File output thật ở đâu?
- [ ] Đường dẫn dùng trong Java bắt đầu từ **gốc classpath**, không phải từ thư mục nguồn?
- [ ] Có file trùng tên trên main/test outputs hoặc nhiều JAR không?
- [ ] Dependency cần cho runtime có bị khai báo `test`/`testImplementation`/`compileOnly` sai không?
- [ ] Test có profile, override, bean, mock, H2, logger config hoặc test-only resource mà production không có không?
- [ ] Đã kiểm `Environment`/property sources thay vì chỉ nhìn một file properties?
- [ ] Đã kiểm nội dung artifact bằng `jar tf` và chạy thử đúng `java -jar`/container chưa?
- [ ] Fixture không mang secret thật, không lệ thuộc absolute path, encoding, thứ tự chạy hay working directory?
- [ ] Với lỗi DB/protocol, đã dùng hạ tầng đủ giống production chưa?

**Ý chính:** `src/test/resources` bổ sung tài nguyên cho **quá trình test**; `src/main/resources` là tài nguyên của **ứng dụng**; `@ActiveProfiles` chọn cấu hình từ những nguồn **đang có mặt**; còn `java -jar` chạy bằng classpath và config của **artifact/triển khai**, không mang theo mọi thứ mà IDE hay test runner từng thấy. Biết chính xác pha thực thi và nguồn tài nguyên sẽ giúp tìm được nguyên nhân thay vì sửa ngẫu nhiên annotation hoặc đường dẫn.

## 13. Nguồn tham khảo chính thức

- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Externalized Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Framework — Context Configuration with Test Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven Surefire — Configuring the Classpath: https://maven.apache.org/surefire-archives/surefire-3.5.5/maven-surefire-plugin/examples/configuring-classpath.html
- Maven Resources — resources:testResources: https://maven.apache.org/plugins/maven-resources-plugin/testResources-mojo.html
- Gradle — Testing in Java & JVM projects: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Building Java & JVM projects: https://docs.gradle.org/current/userguide/building_java_projects.html
