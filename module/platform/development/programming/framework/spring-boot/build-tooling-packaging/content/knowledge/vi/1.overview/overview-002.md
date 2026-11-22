# Từ mã nguồn đến sản phẩm triển khai: biên dịch, kiểm tra, đóng gói và xuất bản

Một ứng dụng Spring Boot không trở thành sản phẩm triển khai chỉ vì chạy được trong IDE. Muốn chuyển mã nguồn thành một phiên bản có thể phát hành, nhóm phát triển cần một chuỗi thao tác có thể lặp lại: **xác định phiên bản và phụ thuộc → biên dịch → kiểm tra → đóng gói → xác minh artifact → xuất bản → triển khai**. Mỗi bước tạo ra bằng chứng cụ thể; bước sau chỉ nên dùng kết quả đã đạt yêu cầu của bước trước.

Bài này tập trung vào quy trình build và phát hành ứng dụng Spring Boot chạy trên JVM. Ví dụ dùng **Java 17, Spring Boot 3.3.13** để giữ cấu hình nhất quán; với dự án khác, chọn phiên bản JDK, Spring Boot và Gradle/Maven tương thích với chính dự án đó.

## 1. Hiểu đúng đầu vào, công đoạn và đầu ra

| Công đoạn | Mục đích | Đầu ra/điều kiện hoàn thành |
| --- | --- | --- |
| Chuẩn bị build | Chốt mã nguồn, cấu hình build, JDK, plugin và phiên bản dependency | Một revision có thể truy vết; build tool phân giải được dependency |
| Biên dịch | Chuyển mã Java thành bytecode; xử lý resources | `.class` và tài nguyên ứng dụng, không có lỗi compiler |
| Kiểm tra | Chạy unit test, integration test và các kiểm tra chất lượng được cấu hình | Báo cáo test/check thành công; lỗi làm pipeline dừng |
| Đóng gói | Gom bytecode, resources và runtime dependencies theo định dạng đích | Executable JAR/WAR hoặc OCI image |
| Xác minh artifact | Kiểm tra đúng tệp, cấu trúc và hành vi khởi động | Tệp tồn tại, chạy được, smoke test đạt |
| Xuất bản | Đưa artifact bất biến vào nơi lưu trữ/phân phối được kiểm soát | Version + vị trí artifact + checksum/digest |
| Triển khai | Chọn artifact đã được duyệt và chạy ở môi trường đích | Dịch vụ khởi động, health/smoke check đạt |

**Phân biệt:** *build* tạo/kiểm tra artifact; *publish* công bố artifact lên kho; *deploy* đưa đúng artifact ấy vào môi trường chạy. Lệnh `mvn deploy` thuộc vòng đời **xuất bản lên Maven repository**, không đồng nghĩa triển khai ứng dụng lên server.

Một nhánh quy trình thường gặp:

```text
Git commit + build configuration
        |
        v
Resolve dependencies -> Compile -> Unit tests / Integration tests
        |                                  |
        |                           Fail: dừng pipeline
        v                                  |
Package (bootJar / repackage / OCI image) <+
        |
        v
Validate artifact -> Publish immutable version -> Deploy -> Smoke test
```

## 2. Vai trò của Java, công cụ build và Spring Boot plugin

**JDK** cung cấp `javac` để biên dịch, `java` để chạy, `jar` để kiểm tra nội dung JAR. **Gradle/Maven** tổ chức dependency, task/phase, cache, test và artifact. **Spring Boot plugin** bổ sung cách chạy và đóng gói đặc thù: ứng dụng Spring Boot thường cần JAR chứa thư viện runtime và bootstrap loader để `java -jar` khởi động trực tiếp.

Với Gradle sử dụng Java plugin và Spring Boot plugin:

- `compileJava` biên dịch mã chính; `processResources` xử lý `src/main/resources`; `classes` tập hợp đầu ra.
- `test` chạy các test thuộc source set kiểm tra mặc định; `check` có thể gom thêm static analysis/integration test do dự án gắn vào.
- `bootJar` tạo **executable JAR** trong `build/libs/`. `jar` tạo JAR thông thường; trong cấu hình Spring Boot 3.3, JAR thông thường thường có hậu tố `-plain.jar`.
- `assemble` gom task tạo artifact và được Spring Boot plugin nối với `bootJar`; `build` phụ thuộc cả `assemble` lẫn `check`. Vì vậy **`bootJar` một mình không phải bằng chứng rằng toàn bộ test đã chạy**.
- `bootRun` khởi động ứng dụng từ classpath phục vụ phát triển; `bootBuildImage` tạo OCI image bằng Cloud Native Buildpacks khi có Docker daemon phù hợp.

Với Maven:

- `compile` → `test` → `package` → `verify` → `install` → `deploy` là thứ tự phase chuẩn. Gọi một phase sẽ thực hiện các phase đứng trước nó trong cùng lifecycle.
- `spring-boot-maven-plugin` với goal `repackage` biến JAR/WAR do phase `package` tạo thành executable archive. Khi dùng `spring-boot-starter-parent` và khai báo plugin này, execution `repackage` được cấu hình sẵn.
- `mvn clean verify` kiểm tra đến phase `verify`; integration test dùng Maven Failsafe chỉ chạy nếu dự án **đã cấu hình** plugin/goals tương ứng. `mvn install` đưa artifact vào kho Maven cục bộ; `mvn deploy` đẩy tới kho Maven từ xa đã cấu hình.

Không trộn nhiệm vụ giữa hai công cụ: chọn Gradle **hoặc** Maven làm nguồn sự thật cho một bản build, dùng Wrapper (`gradlew`/`mvnw`) nếu dự án cung cấp.

## 3. Ví dụ Gradle đầy đủ: từ Java source đến executable JAR

Cấu trúc ví dụ:

```text
demo-build/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/dev/example/demo/
    │   ├── DemoApplication.java
    │   └── HelloController.java
    └── test/java/dev/example/demo/
        └── HelloControllerTest.java
```

Tệp `settings.gradle`:

```groovy
rootProject.name = 'demo-build'
```

Tệp `build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`org.springframework.boot` đăng ký task `bootJar`, còn `io.spring.dependency-management` nhập BOM Spring Boot để các starter dependency không phải khai báo version riêng. Java toolchain chọn compiler Java 17; máy build vẫn phải có JDK tương thích để chạy Gradle/plugin. `mavenCentral()` là kho tìm dependency, **không phải kho tự động nhận artifact xuất bản**.

Tệp `src/main/java/dev/example/demo/DemoApplication.java`:

```java
package dev.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

Tệp `src/main/java/dev/example/demo/HelloController.java`:

```java
package dev.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HelloController {
    @GetMapping("/hello")
    public String hello() {
        return "Hello from JAR";
    }
}
```

Tệp `src/test/java/dev/example/demo/HelloControllerTest.java`:

```java
package dev.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class HelloControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void helloEndpointReturnsExpectedText() throws Exception {
        mockMvc.perform(get("/hello"))
                .andExpect(status().isOk())
                .andExpect(content().string("Hello from JAR"));
    }
}
```

Test dùng Spring test context và `MockMvc` để gọi endpoint mà không cần mở một cổng HTTP thật. Nó xác nhận controller trả mã HTTP 200 và nội dung chính xác. Một ứng dụng thực tế nên có thêm unit test cho nghiệp vụ thuần Java và integration test cho database, message broker hoặc dịch vụ ngoài; không nên dựa vào một test endpoint duy nhất.

**Thực thi từ thư mục dự án có Gradle Wrapper** (trên Windows thay `./gradlew` bằng `gradlew.bat`):

```bash
./gradlew clean build
java -jar build/libs/demo-build-1.0.0.jar
```

`clean` xóa đầu ra build trước; `build` tạo artifact và chạy `check`. Trong terminal khác, khi ứng dụng đã khởi động:

```bash
curl -s http://localhost:8080/hello
```

Phần thân response chính xác:

```text
Hello from JAR
```

Nếu dự án chưa có Wrapper, tạo/kiểm tra Wrapper theo chính sách dự án rồi dùng nó trong cả máy cá nhân và CI. Không giả định mọi dự án có sẵn tệp `gradlew`.

Các lệnh riêng hữu ích:

| Lệnh Gradle | Khi dùng | Điều cần nhớ |
| --- | --- | --- |
| `./gradlew compileJava` | Chỉ kiểm tra mã chính có biên dịch được | Chưa chạy test hay tạo bản phát hành |
| `./gradlew test` | Chạy test mặc định | Không đồng nghĩa đã đóng gói |
| `./gradlew check` | Chạy toàn bộ verification task được gắn vào `check` | Phạm vi phụ thuộc cấu hình dự án |
| `./gradlew bootJar` | Tạo executable JAR nhanh | Không tự bảo đảm các bài test đã chạy |
| `./gradlew clean build` | Build và kiểm tra theo lifecycle Gradle | Phù hợp làm gate CI cơ bản |
| `./gradlew bootRun` | Chạy ứng dụng từ source/classpath khi phát triển | Không xác minh JAR sẽ phát hành |
| `./gradlew tasks --all` | Xem các task thực sự tồn tại | Hữu ích khi dự án có custom plugin |

## 4. Ví dụ Maven tương đương với cùng mã Java

Nếu dự án dùng Maven, giữ nguyên ba tệp Java ở trên và dùng `pom.xml` sau **thay cho cấu hình Gradle**:

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

    <groupId>dev.example</groupId>
    <artifactId>demo-build</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

Thực hiện khi đã cài Maven tương thích (hoặc thay `mvn` bằng `./mvnw` nếu có Wrapper):

```bash
mvn clean verify
java -jar target/demo-build-1.0.0.jar
```

Nhờ `spring-boot-starter-parent` và plugin khai báo trong POM, `repackage` được gắn vào vòng đời đóng gói. Nếu **không** dùng parent này, cần cấu hình execution `repackage` phù hợp; chỉ khai báo plugin chưa chắc khiến JAR thành executable. Lệnh `mvn package spring-boot:repackage` là lựa chọn tường minh khi cần gọi goal sau khi có JAR gốc.

**Không nhầm `mvn verify` với việc đã có integration test thực sự:** kiểm tra rằng plugin Failsafe và mục tiêu `integration-test`/`verify` đã được nối vào lifecycle, rồi mới coi integration test là gate phát hành. Đừng dựa vào tên phase để kết luận những kiểm tra chưa được cấu hình đã chạy.

## 5. Kiểm tra chính artifact sẽ được phát hành

Đầu ra quan trọng của ví dụ Gradle là `build/libs/demo-build-1.0.0.jar`. Có thể còn `demo-build-1.0.0-plain.jar`; JAR `-plain` thông thường không có bộ runtime dependencies/bootstrap Spring Boot cần cho lệnh `java -jar` của ứng dụng.

Kiểm tra cấu trúc bằng JDK:

```bash
jar tf build/libs/demo-build-1.0.0.jar
```

Executable JAR Spring Boot 3.x thường chứa:

- `BOOT-INF/classes/`: bytecode và resources của ứng dụng.
- `BOOT-INF/lib/`: các JAR dependency dùng lúc chạy.
- Spring Boot loader và manifest điều hướng tới main class của ứng dụng.

Một JAR xuất hiện trên đĩa **chưa đủ** để coi build đã phát hành thành công. Tối thiểu cần xác nhận: (1) build và test gate thành công; (2) đúng artifact, đúng version; (3) `java -jar` khởi động được trong JRE/JDK tương thích; (4) endpoint hoặc health check cần thiết đáp ứng; (5) cấu hình môi trường được cấp ngoài artifact và không chứa secret bị commit.

Để so sánh artifact trước và sau khi chuyển nơi lưu trữ, tính SHA-256. Trên Linux/macOS:

```bash
sha256sum build/libs/demo-build-1.0.0.jar
```

Trên PowerShell:

```powershell
Get-FileHash build/libs/demo-build-1.0.0.jar -Algorithm SHA256
```

Checksum phải khớp ở nơi nhận. Hai lần build từ cùng source **không mặc nhiên có cùng checksum** nếu cấu hình, dependency, metadata trong archive hoặc môi trường build không được cố định; xác minh khả năng tái lập trước khi tuyên bố build reproducible.

## 6. Các định dạng đóng gói và lựa chọn triển khai

| Artifact | Cách tạo phổ biến | Cách sử dụng phù hợp |
| --- | --- | --- |
| Executable JAR | Gradle `bootJar`; Maven `package` + `repackage` | `java -jar` trên JVM; dịch vụ đóng gói cùng dependency |
| Plain JAR | Gradle `jar`; Maven JAR thường nếu không repackage | Thư viện được module khác sử dụng, không phải bundle tự chạy |
| Executable WAR | Gradle `bootWar`; Maven WAR + repackage | Ứng dụng cần WAR hoặc môi trường servlet container phù hợp |
| OCI image | Gradle `bootBuildImage`; Maven `spring-boot:build-image` | Registry/container runtime; đóng gói filesystem/runtime cho triển khai |

**Không xuất bản executable Boot JAR làm dependency thư viện thông thường** nếu module khác cần import class trực tiếp: class của ứng dụng nằm trong `BOOT-INF/classes`, khác layout Java library JAR. Nếu cần thư viện tái sử dụng, tách module thư viện và xuất bản plain JAR của nó.

Tạo image bằng Cloud Native Buildpacks khi Docker daemon sẵn sàng:

```bash
./gradlew bootBuildImage --imageName=demo-build:1.0.0
docker image inspect demo-build:1.0.0
docker run --rm -p 8080:8080 demo-build:1.0.0
```

`bootBuildImage` tạo image cục bộ; **chưa tự đẩy image lên registry**. Muốn phát hành image cần đăng nhập registry, đặt tag hợp lệ, push và lưu lại **image digest**. Tag có thể bị thay đổi; digest xác định đúng bytes của image đã xây dựng. Với container, vẫn phải thực hiện smoke test sau khi chạy image.

## 7. Xuất bản artifact có kiểm soát

Có ba đích phổ biến, và chúng có ý nghĩa khác nhau:

1. **Build artifact của CI/release storage:** lưu executable JAR/WAR như một tệp phát hành kèm version, commit và SHA-256. Tác vụ `upload-artifact` trong CI chỉ lưu tệp build để tải lại; không tự cài/triển khai lên môi trường chạy.
2. **Maven artifact repository:** `mvn install` lưu vào local `~/.m2/repository`; `mvn deploy` đẩy lên repository từ xa khi POM có `distributionManagement` và credentials hợp lệ. Gradle cần plugin `maven-publish`, `publishing.publications` và `publishing.repositories` trước khi `./gradlew publish` có đối tượng để xuất bản. Đừng dùng repository chứa dependency tải xuống làm mặc định cho việc upload.
3. **OCI registry:** đẩy image đã tag và xác minh bằng digest; triển khai phải chọn image từ registry, tránh tự build lại tại server.

Ví dụ workflow CI kiểm tra và lưu JAR sau khi đạt gate (`.github/workflows/build.yml`), dùng với dự án Gradle ở mục 3 **đã có Gradle Wrapper**:

```yaml
name: Verify and package
on:
  pull_request:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle
      - name: Build and verify
        run: ./gradlew clean build
      - uses: actions/upload-artifact@v4
        with:
          name: executable-jar
          path: build/libs/demo-build-1.0.0.jar
          if-no-files-found: error
```

Workflow này dừng khi `build` thất bại hoặc tệp JAR không tồn tại. Nó **chưa là release production**: bước xuất bản tới registry/repository ngoài và deploy nên được gắn điều kiện riêng (ví dụ release tag đã duyệt), quyền truy cập tối thiểu và cách truy vết artifact. Tránh ghi token, mật khẩu, private key vào `build.gradle`, `pom.xml`, source hoặc log; cấp credentials từ secret manager của CI.

Một bản phát hành nên có **release record** gồm: `group/artifact/version` hoặc tên image + digest, Git commit, phiên bản Java/Spring Boot, thời điểm build, kết quả test, checksum, nơi lưu artifact và thông tin người/phần mềm đã phê duyệt. Giữ nguyên artifact từ kiểm thử đến triển khai để tránh tình trạng “mỗi môi trường tự build một bản khác”.

## 8. Cách thiết kế các cổng chất lượng (quality gates)

- **Trước package:** dependency resolve thành công, compile sạch, unit test và những static checks đã cấu hình đều đạt.
- **Trước publish:** integration test thực sự được cấu hình và chạy, executable JAR/OCI image được tạo, khởi động thử và smoke test đạt; kiểm tra dependency/security theo chính sách dự án.
- **Trước deploy:** artifact có version/digest bất biến, nguồn xuất bản được xác thực, cấu hình/secrets của môi trường đã chuẩn bị; cần có phương án rollback sang bản trước.
- **Sau deploy:** health/readiness check và một số luồng nghiệp vụ chính hoạt động; theo dõi log/metrics để phát hiện regression.

Không dùng `-x test` (Gradle), `-DskipTests` hoặc `-Dmaven.test.skip=true` (Maven) để âm thầm vượt quality gate. Nếu buộc phải bỏ test cho mục đích chẩn đoán, đánh dấu rõ artifact không được duyệt phát hành cho đến khi kiểm tra lại.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh/khắc phục |
| --- | --- | --- |
| Biên dịch lỗi `invalid source release` hoặc `Unsupported class file major version` | JDK/toolchain khác yêu cầu; runtime cũ hơn bytecode | Xem `java -version`, toolchain, Gradle/Maven và Java dùng chạy artifact |
| JAR tạo được nhưng `java -jar` không chạy | Chạy nhầm `-plain.jar`, thiếu Boot loader hoặc main class | Chạy đúng `bootJar`/`repackage`, kiểm tra manifest và tên tệp |
| `bootJar` thành công nhưng CI vẫn có lỗi test | `bootJar` không bảo đảm chạy `check` | Dùng `clean build` hoặc gọi rõ verification task trước khi publish |
| `mvn package` cho JAR không tự chạy | `repackage` chưa được gắn vào lifecycle | Kiểm tra starter parent/execution hoặc gọi `mvn package spring-boot:repackage` |
| `mvn deploy` không khởi động ứng dụng trên server | `deploy` là phase xuất bản artifact Maven | Tạo bước triển khai riêng chọn đúng artifact |
| `./gradlew publish` không có gì để tải lên | Thiếu/không hoàn chỉnh `maven-publish` và cấu hình publication/repository | Kiểm tra task publish và mô hình publication đúng loại artifact |
| Build image thất bại vì không kết nối Docker | `bootBuildImage` cần Docker daemon đang hoạt động và có quyền truy cập | Kiểm tra Docker context/daemon và network dùng tải builder |
| Máy chạy khác máy build phát sinh lỗi cấu hình | Port, env variables, profile, secrets, JDK/JRE hoặc network khác | Thử cùng artifact, cấp cấu hình ngoài, xem startup log và health |
| Build “cùng commit” ra kết quả khác | Dynamic dependency/SNAPSHOT, Wrapper/JDK không cố định, dữ liệu sinh có timestamp | Khóa version, dùng Wrapper và toolchain, kiểm soát input và so checksum |

## 10. Checklist thực hành

Trước khi nói “sẵn sàng phát hành”, tự trả lời được:

- Có thể dựng lại từ một Git commit và cấu hình build đã version hóa không?
- JDK, Spring Boot, plugin và dependency đã được chọn rõ chưa?
- `clean build`/`clean verify` đã **thực sự chạy** những kiểm tra dự án yêu cầu chưa?
- Đã xác định đúng executable JAR/WAR hoặc image, chạy thử chính artifact ấy chưa?
- Đã gắn version và lưu checksum/digest cùng nơi xuất bản chưa?
- Có thể triển khai lại hoặc rollback **cùng một artifact** mà không biên dịch lại không?

Khi sáu câu trả lời đều “có” với bằng chứng tương ứng, nhóm đã có một quy trình chuyển từ source đến sản phẩm triển khai có thể kiểm tra và lặp lại.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3 Gradle plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/
- Spring Boot 3.3 Maven plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/
- Gradle build lifecycle (`assemble`, `check`, `build`): https://docs.gradle.org/current/userguide/base_plugin.html
- Gradle Maven Publish Plugin: https://docs.gradle.org/current/userguide/publishing_maven.html