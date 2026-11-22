# Liên kết artifact với commit, nhánh và mã lần chạy CI

Khi một Spring Boot service gặp lỗi trên production, câu hỏi “ứng dụng đang chạy version nào?” thường chưa đủ. Hai JAR đều có Maven version `1.0.0` nhưng được build từ hai commit khác nhau; hai workflow run cùng commit có thể sử dụng dependency/toolchain khác nhau; một lần rerun trên CI có thể tạo artifact mới dù `run_id` không thay đổi. Vì vậy cần nối **artifact thực tế được triển khai** với **revision nguồn**, **ref/nhánh kích hoạt**, **mã lần chạy và lần thử CI**, đồng thời giữ một định danh mạnh để kiểm chứng chính xác những byte đã phát hành.

Bài học tập trung vào **metadata bản dựng** trong Spring Boot, Maven/Gradle và CI/CD:

- Gắn thông tin nhận diện nguồn và CI vào executable JAR qua `META-INF/build-info.properties` bằng Spring Boot build plugins.
- Phân biệt `commit SHA`, `branch/ref`, `run ID`, `run attempt`, `version` và `SHA-256 artifact`.
- Kiểm tra metadata được tạo **trong build**, được **đóng trong JAR**, được Spring Boot đọc khi chạy, và khớp với CI logs.
- Có lựa chọn **metadata nhúng trong artifact** hoặc **provenance/sidecar đi kèm theo digest**, để không vô tình phá tính tái lập của bản dựng.
- Xử lý đúng Git detached HEAD, pull request merge commit, tag, rerun, monorepo và chiến lược promotion qua môi trường.

Các ví dụ dùng **Java 17, Spring Boot 3.3.13**, Maven 3.9.x hoặc Gradle tương thích với Boot 3.3; GitHub Actions chỉ là một provider mẫu. Phiên bản được pin để người học tái hiện cơ chế, không phải đề xuất rằng đây là các phiên bản mới nhất.

## 1. Sáu loại danh tính khác nhau

Giả sử CI sinh một tệp `lineage-demo-1.0.0.jar`. Metadata tưởng tượng của lần build có thể là:

```text
application.version = 1.0.0
source.repository    = example-org/lineage-demo
source.commit        = 4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b
source.ref           = refs/heads/main
ci.provider          = github-actions
ci.run.id            = 8123456789
ci.run.attempt       = 2
artifact.sha256      = <64 hexadecimal characters computed AFTER packaging>
```

Dòng `<64 hexadecimal characters ...>` là **mô tả cấu trúc**, không phải một digest hợp lệ để sử dụng; digest phải được tính từ byte thật của JAR. Những giá trị khác cũng chỉ minh họa, không mô tả một commit hay workflow thực tế.

| Thuộc tính | Trả lời câu hỏi | Có bất biến không? | Dùng để làm gì? |
| --- | --- | --- | --- |
| **Artifact version** | Release logic mang version nào? | Không đủ để phân biệt mọi binary | Release notes, dependency coordinate, semantic version |
| **Full commit SHA** | Working tree/check-out dựa trên Git object nào? | Định danh object ổn định trong repository | Truy ngược source tại build; đối chiếu commit |
| **Branch/tag/ref** | Build được kích hoạt dưới tên ref nào? | **Không**: branch có thể dịch chuyển | Biết ngữ cảnh PR/main/release; policy deployment |
| **CI run ID** | Workflow/pipeline invocation nào tạo artifact? | Ổn định trong phạm vi provider/repository; chưa chắc globally unique | Tìm log, test reports, artifacts, approvals |
| **Run attempt** | Lần thử thứ mấy của cùng run? | Gắn với lần retry/rerun | Phân biệt hai lần chạy lại một run |
| **Artifact digest** | Chính xác byte nào đang được nói đến? | Mạnh với từng file; đổi byte thì digest đổi | Kiểm tra integrity, đối chiếu deploy và provenance |

**Không dùng tên branch làm định danh bất biến của source.** `main` có thể trỏ commit khác sau mỗi merge. **Không dùng Maven version làm bằng chứng duy nhất của artifact**: có thể rebuild cùng version. **Không dùng run ID mà bỏ attempt** khi provider giữ nguyên run ID qua rerun.

Với GitHub Actions, `GITHUB_RUN_ID` không thay đổi khi chạy lại một workflow run, còn `GITHUB_RUN_ATTEMPT` tăng lên. `GITHUB_RUN_NUMBER` là counter của workflow, không thay `GITHUB_RUN_ID`; sự kết hợp repository + workflow identity + run ID + attempt (+ job/matrix nếu cần) giúp truy vết đến đúng invocation.

## 2. Kiến trúc provenance: mã nguồn → build → artifact → deployment

```text
Git repository
   commit: immutable full SHA
   ref: branch/tag/PR ref at trigger time
         |
         v
CI event + checkout
   repository ID + workflow
   run ID + attempt + job ID
   working tree revision (HEAD)
         |
         v
Maven/Gradle build
   Java/Boot/plugin/dependency versions
   verification tests + packaging
         |
         +--> Embedded metadata:
         |    META-INF/build-info.properties
         |    [optional git.properties]
         |
         v
Executable Spring Boot JAR
   BOOT-INF/classes
   BOOT-INF/lib
         |
         +--> Compute SHA-256 AFTER packaging
         |
         +--> External provenance/attestation:
         |    artifact digest -> source revision + CI invocation
         |
         v
Artifact registry / OCI image
   name + version + digest
         |
         v
Deployment record
   environment + timestamp + deployed digest
         |
         v
Incident lookup: digest -> CI run -> commit/source
```

Chuỗi này có **hai liên kết độc lập**:

1. **Build link:** commit/ref/run information được CI thu thập và ghi kèm output.
2. **Release link:** artifact được publish/deploy có cùng **digest** với file đã được verify.

Nếu chỉ có liên kết thứ nhất, pipeline có thể vô tình deploy một JAR khác cùng tên/version. Nếu chỉ có digest mà không có build record, bạn xác định được bytes nhưng khó truy ngược commit, test logs và người phê duyệt. Chất lượng truy vết đến từ **cả hai**.

### Build metadata không tự chứng minh tính xác thực

Bất kỳ ai có quyền tạo/chỉnh file JAR đều có thể ghi một dòng `build.ci.commit=...` giả. Vì vậy, metadata nhúng là **dữ liệu tự khai báo của artifact**, hữu ích cho chẩn đoán nhưng **không phải chữ ký mật mã**. Khi cần supply-chain assurance, bổ sung checksums, signed provenance/attestations, CI identity và chính sách kiểm chứng nguồn tin cậy.

## 3. Spring Boot cung cấp metadata ở đâu?

Spring Boot 3.3 có cơ chế chuẩn:

- **`META-INF/build-info.properties`:** Maven goal `spring-boot:build-info` hoặc Gradle task `bootBuildInfo` tạo file. Spring Boot auto-configures `BuildProperties` khi resource này có trên classpath. `BuildInfoContributor` có thể đưa build data lên Actuator `/actuator/info`.
- **`git.properties`:** thường được tạo bằng một Git metadata plugin hoặc build task riêng, đặt **ở classpath root**. Spring Boot auto-configures `GitProperties` khi file có mặt; `GitInfoContributor` có thể hiển thị commit/ref trên info endpoint.
- **Manifest `META-INF/MANIFEST.MF`:** đối với executable Boot JAR, `Main-Class` trỏ `JarLauncher`, `Start-Class` trỏ app main class. Một số attributes thể hiện version/build metadata, nhưng **không phải** nơi duy nhất hoặc bắt buộc để gắn CI run identity.
- **CI artifact store/sidecar:** chứa kết quả test, SHA-256, provenance, SBOM, signed attestations... được nối với cùng artifact digest.

Một file `build-info.properties` điển hình có thể chứa:

```properties
build.artifact=lineage-demo
build.group=dev.example
build.name=lineage-demo
build.version=1.0.0
build.ci.commit=4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b
build.ci.ref=refs/heads/main
build.ci.run.id=8123456789
build.ci.run.attempt=2
```

Spring Boot Maven Plugin **thêm prefix `build.`** cho những properties tùy chỉnh khai báo qua `<additionalProperties>`. Do đó khi cấu hình tên `ci.commit`, file chứa `build.ci.commit`. Qua `BuildProperties`, người dùng đọc bằng `build.get("ci.commit")`, không phải tự đoán rằng `git.properties` và build-info là cùng một nguồn.

**Lưu ý:** `spring-boot:build-info` và `bootBuildInfo` **không tự lấy full Git SHA/CI run ID** nếu bạn không cấu hình thêm. Các thông tin đó phải được cấp từ CI, Git metadata plugin hoặc build script.

## 4. Ví dụ đầy đủ Maven: nhúng commit, ref và run identity

Ví dụ này tạo Spring Boot web application có endpoint `GET /lineage` trả metadata đã nhúng vào JAR. Trong local build, giá trị fallback rõ ràng để ứng dụng vẫn chạy. Trên CI, các giá trị được truyền bằng Maven system/user properties.

Cấu trúc:

```text
lineage-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/dev/example/lineage/
    │   │   ├── LineageApplication.java
    │   │   └── LineageController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/dev/example/lineage/
            └── LineageControllerTest.java
```

### 4.1. `pom.xml` hoàn chỉnh

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
    <artifactId>lineage-demo</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
        <ci.commit>local</ci.commit>
        <ci.ref>local</ci.ref>
        <ci.run.id>local</ci.run.id>
        <ci.run.attempt>0</ci.run.attempt>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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
                <executions>
                    <execution>
                        <id>generate-build-lineage</id>
                        <goals>
                            <goal>build-info</goal>
                        </goals>
                        <configuration>
                            <time>off</time>
                            <additionalProperties>
                                <ci.commit>${ci.commit}</ci.commit>
                                <ci.ref>${ci.ref}</ci.ref>
                                <ci.run.id>${ci.run.id}</ci.run.id>
                                <ci.run.attempt>${ci.run.attempt}</ci.run.attempt>
                            </additionalProperties>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

Các điểm chính:

1. `spring-boot-starter-parent` quản lý dependency versions và cung cấp cấu hình Spring Boot Maven Plugin; plugin trong `build/plugins` thực hiện `repackage` theo starter parent và execution `build-info` được khai báo thêm. **Không phải import BOM đơn thuần** là tự chạy hai goals.
2. `<ci.commit>local</ci.commit>`, `<ci.ref>local</ci.ref>`, `<ci.run.id>local</ci.run.id>`, `<ci.run.attempt>0</ci.run.attempt>` là **giá trị dev fallback**, không được chấp nhận làm release provenance thật.
3. `<additionalProperties>` chuyển Maven properties sang `build.ci.*` trong generated `META-INF/build-info.properties`.
4. `<time>off</time>` chủ động bỏ `build.time` để thời gian build biến đổi không làm file metadata đổi ở mỗi lần chạy. **Nó chưa đủ bảo đảm artifact reproducible** nếu CI run ID/attempt luôn thay đổi: những field này vẫn làm JAR khác byte.
5. `spring-boot-starter-actuator` cho phép dùng `BuildInfoContributor` ở `/actuator/info` khi được expose; controller `/lineage` trong ví dụ chỉ phục vụ bài thực hành. Không mặc định mở cả hai endpoint công khai trên production.
6. Mã nguồn không dùng `GitProperties` nên **không cần Git plugin** ở ví dụ tối thiểu; Git commit được CI truyền vào build-info trực tiếp.

### 4.2. Application main class

`src/main/java/dev/example/lineage/LineageApplication.java`:

```java
package dev.example.lineage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LineageApplication {

    public static void main(String[] args) {
        SpringApplication.run(LineageApplication.class, args);
    }
}
```

### 4.3. HTTP controller đọc metadata được đóng trong JAR

`src/main/java/dev/example/lineage/LineageController.java`:

```java
package dev.example.lineage;

import org.springframework.boot.info.BuildProperties;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class LineageController {

    private final BuildProperties build;

    public LineageController(BuildProperties build) {
        this.build = build;
    }

    @GetMapping("/lineage")
    public LineageResponse lineage() {
        return new LineageResponse(
                build.getVersion(),
                build.get("ci.commit"),
                build.get("ci.ref"),
                build.get("ci.run.id"),
                build.get("ci.run.attempt")
        );
    }

    public record LineageResponse(
            String version,
            String commit,
            String ref,
            String runId,
            String attempt
    ) {
    }
}
```

**Giải thích:** `BuildProperties` là bean được Spring Boot tạo khi tìm thấy `META-INF/build-info.properties`. `build.getVersion()` là version Maven/Gradle đã ghi, còn `build.get("ci.commit")` đọc property bổ sung **sau khi bỏ prefix `build.`** ở tầng Spring Boot. Nếu file metadata không có hoặc build-info goal không chạy, ứng dụng sẽ thiếu `BuildProperties` bean để inject, giúp phát hiện lỗi ngay khi startup.

Endpoint minh họa không trả secret, token, đường dẫn workspace hoặc tên runner. Ở production, **không nên tự động public metadata build chi tiết**; tùy độ nhạy repository/ref và chính sách bảo mật, endpoint nên chỉ dành cho monitoring nội bộ hoặc có authentication/authorization.

### 4.4. Cấu hình HTTP tối thiểu

`src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: lineage-demo
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
```

Với Spring Boot Actuator 3.3, HTTP `info` **không được expose mặc định**; cấu hình trên chỉ expose `health` và `info`. Nó không bảo vệ authentication cho `/lineage` — vì vậy **đây là cấu hình dành cho thực hành trong môi trường tin cậy**. Dự án production phải áp dụng Spring Security, reverse proxy restrictions hoặc management port riêng theo quy tắc doanh nghiệp.

### 4.5. Test xác nhận bean và metadata có mặt

`src/test/java/dev/example/lineage/LineageControllerTest.java`:

```java
package dev.example.lineage;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LineageControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void exposesBuildMetadataGeneratedDuringBuild() throws Exception {
        mvc.perform(get("/lineage"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.version").value("1.0.0"))
                .andExpect(jsonPath("$.commit").isNotEmpty())
                .andExpect(jsonPath("$.ref").isNotEmpty())
                .andExpect(jsonPath("$.runId").isNotEmpty())
                .andExpect(jsonPath("$.attempt").isNotEmpty());
    }
}
```

Test này xác minh Spring context nhìn thấy `BuildProperties` và các trường được xuất ra. Nó **không chứng minh artifact cuối là chính file CI upload/deploy**; việc đó phải kiểm tra digest và package như ở phần sau.

### 4.6. Chạy local với giá trị fallback

Trong thư mục chứa `pom.xml`:

```bash
mvn -version
mvn clean verify
java -jar target/lineage-demo-1.0.0.jar
```

Terminal thứ hai:

```bash
curl -s http://localhost:8080/lineage
```

Body JSON theo cấu hình local mặc định:

```json
{
  "version": "1.0.0",
  "commit": "local",
  "ref": "local",
  "runId": "local",
  "attempt": "0"
}
```

Thứ tự các property JSON khi serialize không nhất thiết giống thứ tự ví dụ; giá trị và tên trường là nội dung quan trọng.

Spring Boot Actuator `/actuator/info` cũng có thể hiển thị nhóm `build`. Cách lồng nhóm JSON và chế độ contributor phụ thuộc cấu hình Boot; không dùng JSON của `/actuator/info` làm nguồn duy nhất thay cho file metadata và CI build record.

## 5. Maven: tạo build có commit/ref/run cụ thể từ CI

Git lưu commit object, còn CI cung cấp context của workflow. Với một terminal Linux/macOS có Git và JDK, bạn có thể thử thủ công:

```bash
COMMIT="$(git rev-parse --verify HEAD)"
REF="$(git symbolic-ref --quiet HEAD || printf 'detached-HEAD')"

mvn -B -ntp clean verify \
  "-Dci.commit=$COMMIT" \
  "-Dci.ref=$REF" \
  "-Dci.run.id=local-check-001" \
  "-Dci.run.attempt=1"
```

**Phân biệt:** `git rev-parse --verify HEAD` trả **commit thực đang checkout**. `git symbolic-ref --quiet HEAD` chỉ trả một symbolic ref khi HEAD gắn với local branch; trên detached HEAD (CI checkout commit trực tiếp) câu lệnh có thể không có output/exit code khác 0, nên ví dụ đặt nhãn `detached-HEAD`. Ref do CI event cung cấp có thể chính xác hơn để mô tả **ngữ cảnh trigger**, và **không nhất thiết là branch name**.

Lưu ý `$(...)` là shell command substitution; ví dụ trên dành cho Bash. Trong PowerShell, dùng `git rev-parse HEAD` để lấy SHA, rồi truyền quoted arguments Maven theo cú pháp PowerShell tương ứng; không dùng nguyên vẹn cú pháp shell Linux nếu không có Bash.

Khi CI cung cấp các metadata:

```bash
mvn -B -ntp clean verify \
  "-Dci.commit=$CI_COMMIT" \
  "-Dci.ref=$CI_REF" \
  "-Dci.run.id=$CI_RUN_ID" \
  "-Dci.run.attempt=$CI_RUN_ATTEMPT"
```

Mỗi biến phải được **kiểm tra có giá trị hợp lệ trước build**. Không cho một release job rơi về fallback `local`, vì như vậy artifact phát hành sẽ ghi provenance mơ hồ dù build thành công.

### Dữ liệu nào là nguồn sự thật?

- `CI_COMMIT`: lý tưởng là commit SHA **của checkout đang được build** (đối chiếu bằng `git rev-parse HEAD`). Với GitHub PR workflows, checkout mặc định có thể là **merge commit tạm** trong `refs/pull/N/merge`; nó khác commit đầu PR. Nếu bạn muốn ghi thêm PR head SHA, lưu nó trong một field riêng (ví dụ `source.pr.head.sha`), **không thay thế âm thầm commit thực đã build**.
- `CI_REF`: full ref của event như `refs/heads/main`, `refs/tags/v1.0.0`, `refs/pull/123/merge`. Không suy mọi ref đều là branch; một workflow chạy do tag cũng có ref.
- `CI_RUN_ID`: định danh CI invocation trong phạm vi provider/repository.
- `CI_RUN_ATTEMPT`: phân biệt lần rerun nếu provider có notion này.
- `CI_JOB_ID`/matrix: nếu cùng run có nhiều jobs/Java versions/architectures tạo file khác nhau, lưu job/variant trong external provenance; một run ID không đủ định danh mọi output trong matrix.

## 6. Kiểm tra metadata **sau** khi đóng gói Maven

Sau build, Spring Boot executable JAR của ví dụ chứa:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/example/lineage/LineageApplication.class
BOOT-INF/classes/dev/example/lineage/LineageController.class
BOOT-INF/classes/META-INF/build-info.properties
BOOT-INF/lib/...
```

File `build-info.properties` nằm ở `target/classes/META-INF` trước khi repackage và chuyển vào `BOOT-INF/classes/META-INF` trong executable JAR. **Đừng kiểm tra nhầm `META-INF/build-info.properties` ở root của executable outer JAR**; đường Boot JAR thường nằm dưới `BOOT-INF/classes`.

Xem trực tiếp:

```bash
jar tf target/lineage-demo-1.0.0.jar
unzip -p target/lineage-demo-1.0.0.jar \
  BOOT-INF/classes/META-INF/build-info.properties
```

Tìm các dòng tương ứng:

```properties
build.ci.commit=4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b
build.ci.ref=refs/heads/main
build.ci.run.id=8123456789
build.ci.run.attempt=2
```

Đây là minh họa cho các giá trị đã được CI truyền; thực tế phải đọc đúng SHA/ref/run của lần build. Do `<time>off</time>` trong POM, không kỳ vọng có `build.time` trong file.

### Gate tự động để tránh fallback giả

Ví dụ Bash, chạy **sau khi đã build ở CI**:

```bash
#!/usr/bin/env bash
set -euo pipefail

JAR="target/lineage-demo-1.0.0.jar"
COMMIT="$(git rev-parse --verify HEAD)"

test -f "$JAR"
test -n "$COMMIT"
test -n "$CI_REF"
test -n "$CI_RUN_ID"
test -n "$CI_RUN_ATTEMPT"

unzip -p "$JAR" BOOT-INF/classes/META-INF/build-info.properties > build-info-check.properties

grep -Fqx "build.ci.commit=$COMMIT" build-info-check.properties
grep -Fqx "build.ci.ref=$CI_REF" build-info-check.properties
grep -Fqx "build.ci.run.id=$CI_RUN_ID" build-info-check.properties
grep -Fqx "build.ci.run.attempt=$CI_RUN_ATTEMPT" build-info-check.properties

echo "PASS: embedded build metadata matches CI and working commit"
```

Khi các kiểm tra trên đạt, stdout của script:

```text
PASS: embedded build metadata matches CI and working commit
```

Trong shell `set -euo pipefail`, các biến CI chưa được định nghĩa gây lỗi rõ ràng. Nếu một giá trị chưa được truyền vào Maven và plugin ghi fallback `local`, `grep -Fqx` sẽ thất bại. Đây là **bằng chứng kiểm tra metadata ở byte artifact**, không phải một chữ ký bảo đảm người build đáng tin.

**Khi cần tránh tệp tạm trong workspace**, có thể dùng pipe `unzip -p ... | grep ...`, nhưng script minh họa giữ nội dung một lần để đối chiếu nhiều field. Trong CI nhiều jobs song song cùng workspace, tên file tạm phải cách ly theo job.

## 7. Gradle: tạo cùng metadata bằng `bootBuildInfo`

Spring Boot Gradle Plugin 3.3 cung cấp DSL `springBoot { buildInfo { ... } }` và task `bootBuildInfo`. Tệp metadata cuối có cùng định dạng mà Spring Boot Actuator/`BuildProperties` hiểu. Dưới đây là lựa chọn **thay POM** cho cùng source Java và test của mục 4.

`settings.gradle`:

```groovy
rootProject.name = 'lineage-demo'
```

`build.gradle` (Groovy DSL):

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
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

def ciCommit = providers.environmentVariable('CI_COMMIT').orElse('local')
def ciRef = providers.environmentVariable('CI_REF').orElse('local')
def ciRunId = providers.environmentVariable('CI_RUN_ID').orElse('local')
def ciAttempt = providers.environmentVariable('CI_RUN_ATTEMPT').orElse('0')

springBoot {
    mainClass = 'dev.example.lineage.LineageApplication'
    buildInfo {
        excludes = ['time']
        properties {
            additional = [
                'ci.commit'     : ciCommit.get(),
                'ci.ref'        : ciRef.get(),
                'ci.run.id'     : ciRunId.get(),
                'ci.run.attempt': ciAttempt.get()
            ]
        }
    }
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Ý nghĩa:

- `bootBuildInfo` tạo `META-INF/build-info.properties` như task output, được nối vào resource/classpath của application khi dùng Java plugin; `bootJar` đóng resource đó vào executable archive.
- `properties.additional` lưu các khóa `ci.commit`/`ci.ref`/`ci.run.id`/`ci.run.attempt`, được ghi thành `build.ci.*`. Gradle không có sẵn mặc định một khóa `CI_COMMIT` theo chuẩn Spring Boot; `providers.environmentVariable(...)` lấy từ environment của **build invocation**.
- `excludes = ['time']` tránh ghi `build.time` thay đổi ở mỗi build. Theo tài liệu Spring Boot Gradle Plugin, thời gian build mặc định làm task không up-to-date và làm outputs khác nhau. Bỏ time cải thiện tính ổn định; nhưng nhúng run ID/attempt vẫn khiến artifact của các lần chạy khác nhau khác byte.
- `test` dùng JUnit Platform để chạy `LineageControllerTest` của Spring Boot starter test.
- Việc gọi `.get()` trong cấu hình trên khiến Gradle lấy env ngay khi evaluating build script. Với dự án lớn cần tối ưu configuration cache hoặc lazy providers, nên chuyển sang cấu hình có `Provider` phù hợp và kiểm thử tính tương thích plugin/version; không dùng một script tùy tiện đọc secret vào output.

### Build Gradle với metadata local

Nếu repository đã có Gradle Wrapper phù hợp:

```bash
./gradlew clean build
java -jar build/libs/lineage-demo-1.0.0.jar
```

Ở terminal khác:

```bash
curl -s http://localhost:8080/lineage
```

Response sẽ có `version=1.0.0` và các giá trị `local`/`0` tương tự Maven.

Với Linux/macOS và biến CI cụ thể, có thể chạy:

```bash
CI_COMMIT="$(git rev-parse --verify HEAD)" \
CI_REF="refs/heads/main" \
CI_RUN_ID="local-check-001" \
CI_RUN_ATTEMPT="1" \
./gradlew clean build
```

Trong ví dụ này `refs/heads/main` là giá trị **tự nhập** để học, không bảo đảm đó là ref thật đang checkout. Khi chạy CI thực, lấy ref từ chính provider và kiểm tra checkout event.

### Đường output Gradle

Kiểm tra:

```bash
jar tf build/libs/lineage-demo-1.0.0.jar
unzip -p build/libs/lineage-demo-1.0.0.jar \
  BOOT-INF/classes/META-INF/build-info.properties
```

Không giả định tệp cuối luôn nằm cố định ở `build/resources/main/META-INF` trong mọi version/configuration. Điều cần xác nhận là **resource tồn tại trong Boot executable JAR** và khớp với data CI đã sử dụng.

## 8. CI mẫu: GitHub Actions thu thập và gắn commit/ref/run/attempt

Đoạn workflow dưới đây dành cho repository **Maven** ở mục 4, dùng GitHub-hosted Ubuntu runner và các action versions minh họa. Với ứng dụng Gradle, thay Maven build step bằng Gradle Wrapper và truyền cùng nhóm biến `CI_*`. Workflow phải được tạo tại `.github/workflows/lineage.yml` trong dự án thật; ở đây nó là **tài liệu học**, không thực hiện thao tác nào lên repository.

```yaml
name: Build artifact with source lineage

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  jar:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Build and verify with immutable source identity
        shell: bash
        env:
          CI_REF: ${{ github.ref }}
          CI_RUN_ID: ${{ github.run_id }}
          CI_RUN_ATTEMPT: ${{ github.run_attempt }}
        run: |
          set -euo pipefail
          CI_COMMIT="$(git rev-parse --verify HEAD)"
          test -n "$CI_COMMIT"
          test -n "$CI_REF"
          test -n "$CI_RUN_ID"
          test -n "$CI_RUN_ATTEMPT"

          mvn -B -ntp clean verify \
            "-Dci.commit=$CI_COMMIT" \
            "-Dci.ref=$CI_REF" \
            "-Dci.run.id=$CI_RUN_ID" \
            "-Dci.run.attempt=$CI_RUN_ATTEMPT"

          unzip -p target/lineage-demo-1.0.0.jar \
            BOOT-INF/classes/META-INF/build-info.properties \
            > target/embedded-lineage.properties

          grep -Fqx "build.ci.commit=$CI_COMMIT" \
            target/embedded-lineage.properties
          grep -Fqx "build.ci.ref=$CI_REF" \
            target/embedded-lineage.properties
          grep -Fqx "build.ci.run.id=$CI_RUN_ID" \
            target/embedded-lineage.properties
          grep -Fqx "build.ci.run.attempt=$CI_RUN_ATTEMPT" \
            target/embedded-lineage.properties

          sha256sum target/lineage-demo-1.0.0.jar \
            > target/lineage-demo-1.0.0.jar.sha256

      - name: Upload exact verified JAR and digest
        uses: actions/upload-artifact@v4
        with:
          name: lineage-demo-${{ github.run_id }}-${{ github.run_attempt }}
          path: |
            target/lineage-demo-1.0.0.jar
            target/lineage-demo-1.0.0.jar.sha256
          if-no-files-found: error
```

**Đọc đúng ý nghĩa workflow:**

- `actions/checkout` tạo checkout mà build thực sự dùng. `git rev-parse --verify HEAD` đo commit ở **working tree đó**, thay vì đoán từ tên branch.
- `github.ref` là **full triggering ref**; trên Pull Request event có thể là `refs/pull/N/merge`. Trong workflow PR, HEAD được checkout thường là merge commit tạm. Nếu cần lưu PR head commit hoặc base commit, ghi **những field riêng**, không nhập nhằng với commit đã biên dịch.
- `github.run_id` là run identity trong repository; `github.run_attempt` là số lần chạy lại. Artifact name trong workflow gắn cả hai để tránh nhầm các lần thử.
- `mvn clean verify` chạy test/build theo POM; release policy có thể bổ sung integration/static/security gates khác.
- `grep -Fqx` kiểm tra **nội dung embedded build-info** khớp event/checkout. Một metadata fallback hoặc nhầm CI env sẽ làm job fail.
- `sha256sum` tính digest **sau khi packaging**, trên chính file JAR sẽ upload. Digest được lưu kèm file, không tự nhét chính digest ấy vào JAR tạo vòng lặp tự tham chiếu.
- `upload-artifact` upload đúng JAR/digest của lần build đó. Nó không tự ký provenance; nếu cần guarantee về nguồn build, thêm bước attestation/signing theo policy.

**Lưu ý quan trọng về bảo mật workflow:** ví dụ giới hạn `permissions: contents: read` và không đụng secrets. Ở production nên pin action bằng commit SHA đã được duyệt và bảo vệ branch/tag/build environment; các tên `@v4` là ví dụ về API major version, **không** có nghĩa nó mang cùng mức đảm bảo supply chain như pin immutable action commit.

### Có cần ghi thêm `GITHUB_SHA` không?

`GITHUB_SHA` là commit được GitHub event đánh dấu, nhưng ý nghĩa cụ thể phụ thuộc loại event. Đối với một số pull request workflows, nó là **merge commit** của PR; `github.event.pull_request.head.sha` là commit đầu PR. Cả hai đều có ích nhưng không nhất thiết giống nhau.

**Quy tắc:** metadata `source.commit` mô tả **commit thực sự build** (`git rev-parse HEAD`), đồng thời CI record có thể lưu thêm **trigger SHA**, **PR head SHA**, **base SHA** nếu cần giải thích vì sao build phản ánh source nào. Không đưa nhãn “head commit” cho một SHA của merge checkout.

## 9. Truy ngược từ run ID về log như thế nào?

Với GitHub Actions, một dạng link log là:

```text
https://github.com/<owner>/<repo>/actions/runs/<run_id>
```

Đây là **mẫu URL**, cần thay owner/repo/run_id thật; các URL của private repository đòi quyền phù hợp. Khi cùng run được rerun, dùng `attempt` để xác định tập logs và artifacts chính xác. Tên workflow, job và matrix variant cũng giúp phân biệt trường hợp một run build nhiều binary.

Bảng gợi ý một record truy vết trong artifact repository hoặc deployment database:

| Trường | Ví dụ | Giải thích |
| --- | --- | --- |
| `repository` | `example-org/lineage-demo` | Phải kèm host/namespace khi có nhiều nguồn |
| `artifact_coordinate` | `dev.example:lineage-demo:1.0.0` | Maven coordinate, có thể không unique theo bytes |
| `commit_sha` | Full SHA từ checkout | Revision thực build |
| `source_ref` | `refs/heads/main` | Context event, không bất biến |
| `ci_provider` | `github-actions` | Namespace của run |
| `ci_run_id` | `8123456789` | Chạy workflow nào |
| `ci_attempt` | `2` | Rerun nào |
| `ci_job` | `jar` | Job/variant tạo output |
| `sha256` | SHA-256 trên JAR thực | Định danh bytes |
| `build_status` | `passed` | Tập quality gates đã đạt |
| `published_uri` | Maven/registry URL | Artifact được lưu ở đâu |
| `deployed_environment` | `staging` hoặc `production` | Deploy ở đâu sau build |

Không ghi credential, access token, private key hoặc toàn bộ environment variables vào record này. Nếu Git branch hoặc tên repo mang nội dung nhạy cảm, cân nhắc dùng internal metadata store và giới hạn endpoint runtime.

## 10. Metadata nhúng và provenance ngoài: hai lựa chọn có đánh đổi

### 10.1. Cách A — Nhúng cả commit + branch/ref + run ID vào JAR

POM và Gradle build mẫu ở trên dùng cách A. Ưu điểm:

- Chỉ cần đúng JAR là có thể đọc revision/ref/run ID ngay cả khi mất mạng CI.
- `/lineage` hoặc Actuator `/info` có thể hỗ trợ debug và hỗ trợ vận hành.
- Artifact inspection trong CI xác nhận metadata được build chứ không phải lấy từ runtime environment.

Nhược điểm:

- **Cùng một commit build lại ở run mới sẽ có `build.ci.run.id` khác**, dẫn đến byte nội dung và SHA-256 khác nhau.
- Khi một CI run được rerun với attempt khác, artifact thường khác dù source giống hệt.
- Git branch/ref là thông tin event, không bất biến; nếu rebuild từ cùng commit ở nhánh/tag khác, metadata lại đổi.
- Có thể lộ thông tin vận hành hoặc tên ref ở endpoint nếu không kiểm soát HTTP exposure.

Nếu tổ chức ưu tiên **traceability trực tiếp trong binary** và chấp nhận run-specific JARs, đây là thiết kế hợp lý. Chỉ cần không tuyên bố “reproducible byte-for-byte” khi run-dependent fields thay đổi.

### 10.2. Cách B — Nhúng chỉ danh tính nguồn ổn định, lưu run bên ngoài

Một chiến lược khác là:

1. Chỉ nhúng **version + immutable Git commit SHA** và metadata tĩnh/được kiểm soát vào JAR.
2. Không nhúng run ID/attempt, branch name, wall-clock build time hoặc dữ liệu môi trường thay đổi.
3. Sau khi package, tính SHA-256 của JAR.
4. Ghi **CI run ID + attempt + branch/ref + build environment** trong sidecar/provenance record **được khóa bởi digest**.
5. Publish JAR và attestation cùng nhau; deploy chỉ dựa trên digest đã được phê duyệt.

```text
Executable JAR
  build.version=1.0.0
  build.ci.commit=<full stable revision>
        |
        v
sha256(JAR bytes) = D
        |
        +--> provenance record:
             subject.digest.sha256 = D
             source.revision       = commit SHA
             invocationId          = CI run + attempt
             source.ref            = branch/tag/PR
             builder identity      = trusted CI
             test results          = passed
```

Cách B giúp những lần build cùng input **có khả năng** tạo bytes giống nhau, nhưng điều đó còn phụ thuộc plugin, archive timestamp, dependency locks, toolchains, locale, input order và reproducible-build settings. **Không thể kết luận tính tái lập chỉ bằng việc bỏ run ID**; cần build lại ở môi trường độc lập và so sánh digest.

### 10.3. Vì sao không đưa chính SHA-256 cuối vào tệp build-info bên trong JAR?

Nếu bạn:

1. Tạo JAR A.
2. Tính SHA-256(A) = D.
3. Sửa `build-info.properties` **bên trong A** để thêm D.

thì JAR sau khi sửa là **A'**, và `SHA-256(A')` **khác** D. Việc lưu digest của toàn bộ artifact vào ngay trong những byte tạo nên digest đó gây **vòng lặp tự tham chiếu**. Giải pháp là lưu digest **bên ngoài** trong sidecar/registry/attestation; hoặc lưu digest của một tập con được xác định rõ, nhưng đừng gọi nó là SHA-256 của toàn bộ final JAR.

## 11. `git.properties` là một lựa chọn khác, không phải Maven build-info

Trong Spring Boot 3.3, nếu classpath root chứa `git.properties` có các khóa `git.branch`, `git.commit.id`, `git.commit.time`..., `GitProperties` và `GitInfoContributor` có thể đọc/hiển thị chúng.

Ví dụ resource:

```properties
git.branch=main
git.commit.id=4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b
git.commit.time=2026-11-09T00:00:00Z
```

Đây chỉ là **minh họa định dạng**, không phải output thật. Đừng tự viết timestamp tùy ý rồi trình bày nó là timestamp commit. Các plugin Git metadata (ví dụ plugin phổ biến cho Maven/Gradle) thường đọc từ `.git`, tạo `git.properties` và có thể tùy chọn các field.

**Ưu nhược điểm:**

- Thuận tiện cho `GitProperties.getCommitId()` và Actuator git contributor.
- CI checkout có thể chạy ở **detached HEAD**; field `git.branch` có thể không có hoặc không mang ý nghĩa event trigger mong đợi. Có thể cần ghi `CI_REF` riêng.
- Một số CI tạo shallow clone; plugin phụ thuộc Git history/tag có thể thiếu dữ liệu. Full commit SHA từ `HEAD` vẫn có thể lấy nếu commit đã checkout; không bắt buộc fetch toàn bộ history chỉ để lấy SHA.
- Không nên dùng Git plugin từ một checkout đã bị thay đổi sau khi CI thu metadata; kiểm tra working tree và source revision nhất quán.

**Không nhầm hai resource:**

| Resource | Được tạo bởi | Chứa gì? |
| --- | --- | --- |
| `META-INF/build-info.properties` | Spring Boot Maven/Gradle plugin | Maven/Gradle coordinates, version, time (tùy cấu hình), custom CI fields |
| `git.properties` | Git metadata plugin/build task | Git commit, branch, commit time và Git fields |
| `META-INF/MANIFEST.MF` | JAR/Boot packaging plugin | Entry point, Start-Class, archive/implementation metadata |
| Sidecar provenance | CI/attestation builder | Subject digest, revision, CI invocation, builder, test/publish evidence |

Trong bài Maven/Gradle đầy đủ, dùng **build-info** làm đường duy nhất để giảm nguy cơ hai nguồn Git metadata ghi không nhất quán. Trong hệ thống thật, nếu chọn cả hai, có thể thêm CI test so sánh `build.ci.commit` với `git.commit.id`.

## 12. Actuator `/actuator/info` và vấn đề lộ dữ liệu

Spring Boot Actuator cung cấp `info` endpoint để biểu diễn build và Git metadata. Với Boot 3.3:

- `BuildInfoContributor` được bật khi có `META-INF/build-info.properties`.
- `GitInfoContributor` được bật khi có `git.properties`.
- Mặc định HTTP Actuator thường **chỉ expose `health`**, nên cần explicitly include `info` nếu muốn truy cập qua HTTP.
- `management.info.git.mode=full` có thể làm lộ thêm nhiều Git fields. Không bật mode đầy đủ chỉ vì tiện debug nếu chưa đánh giá nội dung thực tế.
- Mọi endpoint build identity và source path phải được bảo vệ theo chính sách, nhất là khi có thông tin private repo, branch names hoặc CI URLs.

Cấu hình tối thiểu **cho môi trường phát triển**:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "health,info"
  info:
    git:
      mode: simple
```

Nếu chỉ cần một số trường an toàn, có thể tạo endpoint nội bộ chỉ trả version/full commit/run ID và quản lý access riêng. **Chỉ thêm dependency `spring-boot-starter-actuator` không có nghĩa endpoint `info` tự public.**

### Có nên cho mọi client thấy full commit?

Tùy chính sách và threat model. Full commit SHA thường không phải secret cryptographic, nhưng có thể tiết lộ repository history/branch context hoặc giúp fingerprint deployment. Trong môi trường public, ưu tiên `version` hoặc một deployment ID ít nhạy cảm; giữ full CI trace trong internal telemetry/registry. Không bao giờ đưa access token/password, runner hostname có dữ liệu nhạy cảm hoặc ký tự secret vào build-info.

## 13. GitHub Actions: nhận dạng commit đúng trong các loại event

**Một quan sát quan trọng:** `git rev-parse HEAD` và `GITHUB_SHA` không phải mọi lúc đều biểu diễn điều người dùng thường gọi là “commit của nhánh tính năng”.

| Event | Ref tiêu biểu | SHA cần lưu |
| --- | --- | --- |
| Push vào main | `refs/heads/main` | Working commit checkout, thường là push commit |
| Push tag release | `refs/tags/v1.0.0` | Commit được checkout theo tag/event; ref là tag, không phải branch |
| Pull request (workflow default checkout) | `refs/pull/123/merge` | Có thể là merge commit thử nghiệm do GitHub tạo, khác PR head |
| Pull request target | Ref ngữ cảnh base branch | Cần lưu rõ event checkout và trust boundary; không mặc định đó là PR head |
| Workflow dispatch | Ref được chọn lúc kích hoạt | Dùng checkout HEAD và full ref; lưu actor/event nếu policy cần |
| Rerun attempt | Ref/SHA thường liên quan cùng run | Run ID có thể giữ nguyên, attempt thay đổi; phải phân biệt artifact mới |

Với PR, nếu muốn đánh giá mã của PR **kết hợp vào base**, build synthetic merge commit là điều hợp lý. Nếu muốn chứng minh code đúng chính PR head, workflow checkout head SHA riêng theo policy. **Không tự động checkout/run code từ fork không tin cậy trong môi trường có production secrets.**

### Không lấy branch name qua `git branch --show-current` trên CI rồi coi là bất biến

Nhiều CI chạy detached HEAD, nên `git branch --show-current` có thể trả chuỗi trống. Hãy tách:

- **Built commit:** `git rev-parse HEAD`.
- **Trigger ref:** biến event của CI như `GITHUB_REF`.
- **Human-friendly name:** `GITHUB_REF_NAME` nếu muốn hiển thị; cần biết loại ref và định dạng `123/merge` đối với PR.
- **Source repository identity:** `GITHUB_REPOSITORY` hoặc URI chuẩn của repo.
- **Optional PR head SHA:** event payload riêng, khi thực sự cần.

## 14. Các CI provider khác: chuẩn hóa tên không đồng nghĩa ngữ nghĩa

Một application có thể được build bởi GitHub Actions, GitLab CI, Jenkins hoặc nhà cung cấp khác. Mục tiêu là chuẩn hóa vào nhóm internal fields `ci.commit`, `ci.ref`, `ci.run.id`, `ci.run.attempt` sau khi xác minh ý nghĩa từng biến.

| Provider | Nguồn commit thường gặp | Ref/branch | Run/build identifier |
| --- | --- | --- | --- |
| GitHub Actions | `GITHUB_SHA` và `git rev-parse HEAD` | `GITHUB_REF`/`GITHUB_REF_NAME` | `GITHUB_RUN_ID` + `GITHUB_RUN_ATTEMPT` |
| GitLab CI | `CI_COMMIT_SHA` | `CI_COMMIT_REF_NAME` hoặc `CI_COMMIT_REF_SLUG` | `CI_PIPELINE_ID`; `CI_JOB_ID` phân biệt job |
| Jenkins | `GIT_COMMIT` từ SCM plugin hoặc `git rev-parse HEAD` | `GIT_BRANCH` nếu plugin/SCM cấp | `BUILD_NUMBER` cần namespace theo `JOB_NAME`/server |

Tên/ý nghĩa biến GitLab/Jenkins phụ thuộc CI configuration, loại pipeline và plugin tương ứng. Ví dụ Jenkins `BUILD_NUMBER=42` chỉ unique **trong job**, không phải globally unique; nên lưu thêm Jenkins controller/job identity. Đừng coi một số “42” là có ý nghĩa nếu không có namespace.

Đối với monorepo/matrix, thêm `module`, `artifact name`, `Java version`, `OS/architecture` và `job identifier` để phân biệt nhiều sản phẩm do cùng pipeline tạo.

## 15. Bảo toàn artifact identity khi publish và deploy

Sau khi build/QA, cần quản lý **artifact identity** như một đối tượng bất biến:

### 15.1. Tính digest

Linux/macOS:

```bash
sha256sum target/lineage-demo-1.0.0.jar
```

Nếu muốn lưu sidecar:

```bash
sha256sum target/lineage-demo-1.0.0.jar > target/lineage-demo-1.0.0.jar.sha256
```

Cú pháp output có dạng:

```text
<sha256-hex>  target/lineage-demo-1.0.0.jar
```

`<sha256-hex>` là chú giải, không phải checksum thật. Khi di chuyển file sang thư mục khác, tên đường dẫn trong sidecar có thể không còn phù hợp; có thể xác minh trực tiếp bằng cách tính hash lại và so sánh giá trị 64 ký tự, hoặc sửa sidecar **theo cơ chế có kiểm soát** mà không thay JAR.

PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 target/lineage-demo-1.0.0.jar
```

### 15.2. Sau publish: verify digest

CI/CD nên:

1. Upload JAR có checksum được tính từ file đã test.
2. Tại registry hoặc staging, tải lại đúng file coordinate/digest.
3. Tính SHA-256 file tải về và so sánh với value đã được lưu trong build record.
4. Chỉ promotion/deploy **cùng bytes**, không chạy lại Maven/Gradle để tạo file mới trong deploy stage rồi dùng lại tên version.
5. Ghi deployment record: environment, cluster, time, deployed digest, CI run/attempt, commit.
6. Khi incident/rollback, tìm lại đúng digest và provenance, không chỉ “latest version”.

**Maven `SNAPSHOT`, mutable Docker tags (`latest`) và reused artifact version** là những nguồn nhầm lẫn phổ biến. Nếu registry cho phép ghi đè file theo cùng path/tag, cần enforce immutability hoặc pin digest trong deployment config.

### 15.3. OCI container images cũng có digest riêng

Nếu Spring Boot JAR được đặt trong container image, có **hai đối tượng**:

- **JAR SHA-256:** hash của đúng JAR bytes.
- **OCI image digest:** hash của image manifest/dữ liệu content-addressed theo registry.

Chúng **không phải cùng giá trị**. Container có thêm base image, filesystem layers, image config và metadata. Nên giữ bản ghi `image digest → JAR digest → Git commit → CI run`.

Có thể dùng OCI annotation/labels như:

```text
org.opencontainers.image.source   = https://github.com/example-org/lineage-demo
org.opencontainers.image.revision = 4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b
org.opencontainers.image.version  = 1.0.0
```

Các dòng trên chỉ biểu diễn **metadata concept**; cách gắn label thật phụ thuộc Dockerfile, buildpacks hoặc registry tooling. Label `revision` cũng là dữ liệu khai báo; để chứng minh nguồn gốc cần provenance/signature đáng tin và kiểm tra subject digest.

## 16. Provenance và SBOM: chứng minh được gì?

**Software Bill of Materials (SBOM)** liệt kê components/dependencies của artifact, hữu ích cho vulnerability/license tracking. **Provenance/attestation** mô tả subject artifact, builder, invocation và nguồn build. Hai thứ **bổ sung** nhau nhưng không đồng nhất.

Một record provenance theo tinh thần **SLSA provenance v1.x** có thể mô tả:

```json
{
  "subject": [
    {
      "name": "lineage-demo-1.0.0.jar",
      "digest": {
        "sha256": "HEX_DIGEST_COMPUTED_FROM_THE_REAL_JAR"
      }
    }
  ],
  "buildDefinition": {
    "buildType": "example-ci-build",
    "externalParameters": {
      "sourceRef": "refs/heads/main"
    },
    "resolvedDependencies": [
      {
        "uri": "git+https://github.com/example-org/lineage-demo",
        "digest": {
          "gitCommit": "4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b"
        }
      }
    ]
  },
  "runDetails": {
    "builder": {
      "id": "example-trusted-builder"
    },
    "metadata": {
      "invocationId": "github-actions/run/8123456789/attempt/2"
    }
  }
}
```

**Đây là sơ đồ JSON giải thích các nhóm field, không phải attestation đầy đủ hoặc payload được ký hợp lệ theo tất cả schema/requirements của SLSA.** Các giá trị như `HEX_DIGEST_COMPUTED_FROM_THE_REAL_JAR` phải được thay bằng hash thật, và `buildType`/`builder.id` phải theo định danh đã được nhà vận hành xác định. Không dùng đoạn này như một chứng thư đã được chứng thực.

Trong một quy trình an toàn:

- CI builder đáng tin tạo attestation có **subject digest khớp final artifact**.
- Attestation được ký theo cơ chế đã được doanh nghiệp phê duyệt, chẳng hạn Sigstore/certificate-based signing.
- Deployment gate xác minh chữ ký, builder identity, source revision và policy, **không chỉ parse JSON tự khai báo**.
- SBOM có thể được nối cùng artifact digest để biết những dependency nào thực sự tồn tại.

Run ID/attempt là trường truy tìm logs; nó không có quyền thay thế **builder identity, signature và subject digest**.

## 17. Tính tái lập: timestamp và run ID có thể phá byte-for-byte equality

Một artifact “reproducible build” nghĩa là cùng **effective inputs và toolchain** có thể tạo byte output giống nhau theo quy trình đã xác định. Điều này quan trọng khi kiểm chứng supply chain. Các giá trị **không ổn định** thường làm thay đổi binary:

- Wall-clock build timestamp trong `build.time` hoặc ZIP entry metadata.
- `ci.run.id` hoặc `ci.run.attempt` nhúng vào `build-info.properties`.
- Branch/ref name nếu cùng commit được build từ nhiều ref.
- Non-deterministic ordering của generated resources.
- Dependency dạng `SNAPSHOT`/version động hoặc artifact registry cho phép thay thế.
- Plugin/toolchain/environment khác nhau; locale/time zone/absolute paths bị nhúng.
- Source tree không sạch: generated files hoặc file uncommitted tham gia build.

**Với Maven** trong ví dụ, `<time>off</time>` bỏ property `build.time`, nhưng không tự làm mọi ZIP/JAR reproducible. Có thể còn cần `project.build.outputTimestamp` cố định, plugin version có hỗ trợ reproducible archives, dependency locks và kiểm tra thực tế.

**Với Gradle**, `excludes = ['time']` là lựa chọn phù hợp khi ưu tiên up-to-date và repeatability; tài liệu Boot Gradle Plugin giải thích rằng build-time current instant mặc định khiến `bootBuildInfo` khó up-to-date và output biến đổi.

### Thực nghiệm đúng cách

1. Chọn một Git commit và freeze toolchain/dependencies.
2. Build tại hai workspace sạch, đảm bảo **mọi giá trị nhúng đều giống nhau**.
3. Tính SHA-256 của mỗi artifact và so sánh.
4. Nếu khác, kiểm tra `build-info.properties`, archive entry timestamps, file order, generated metadata và toolchain.
5. Nếu cần giữ run identity mà binary phải giống nhau, chuyển run ID/attempt sang **sidecar provenance** (cách B ở mục 10).

Tại thời điểm nhúng run ID khác nhau, hai build **không có cùng effective input**; hash khác chưa đủ kết luận compiler không deterministic.

## 18. Multi-module: module nào có metadata và artifact nào dùng để deploy?

Trong Maven/Gradle multi-module, đừng chỉ ghi metadata ở root aggregator rồi tưởng mọi JAR của các module tự có cùng file:

```text
multi-module/
├── pom.xml                    (aggregator)
├── common/                    (plain library JAR)
└── api-service/               (Spring Boot executable JAR)
```

Nếu `api-service` là module phát hành:

- Bind `build-info`/**`bootBuildInfo` tại chính module app** (hoặc cấu hình inherited đúng, nhưng tránh sinh sai/thiếu metadata ở child).
- Dùng cùng full commit SHA/ref/run context từ CI cho các modules trong một build, nhưng thêm module/artifact coordinate vào external record.
- Kiểm tra `api-service/target/api-service-...jar` hoặc `api-service/build/libs/api-service-...jar`, không kiểm tra một artifact ở root.
- Nếu một lần CI build nhiều module, `run ID` là **chung**, nên cần `module` và `artifact SHA-256` để nhận dạng từng sản phẩm.
- Khi build chỉ một module bằng `mvn -pl :api-service -am` hoặc `./gradlew :api-service:build`, build tool vẫn có thể build upstream libraries; metadata build của app phải đại diện cho **revision của source đang compile** và artifact đã được package.
- Nếu module library được publish riêng cho consumers, thường dùng plain JAR với POM/Gradle module metadata; không áp dụng Boot repackage cho tất cả modules chỉ để nhúng build-info.

Ví dụ Maven module selector tại root:

```bash
mvn -B -ntp -pl :api-service -am clean verify \
  "-Dci.commit=$CI_COMMIT" \
  "-Dci.ref=$CI_REF" \
  "-Dci.run.id=$CI_RUN_ID" \
  "-Dci.run.attempt=$CI_RUN_ATTEMPT"
```

Đây là **fragment cho repository thực sự có `api-service`**; không chạy trực tiếp trong project `lineage-demo` một module của ví dụ. Trước khi publish, gate phải inspect đúng output module app và tạo digest riêng.

## 19. Truy vết lỗi deployment theo chiều ngược

Một tình huống thực tế: `/lineage` trên staging cho:

```json
{
  "version": "1.0.0",
  "commit": "4f6c9f2e9df68d65fc8d88c4bcdad5c41295e30b",
  "ref": "refs/heads/main",
  "runId": "8123456789",
  "attempt": "2"
}
```

Quy trình điều tra:

1. Lấy **digest của artifact đang được triển khai**, từ deployment/registry/infrastructure record (JAR checksum hoặc OCI image digest).
2. Đối chiếu digest với artifact CI đã publish từ `runId=8123456789` và `attempt=2`.
3. Xác định repository/workflow/job tạo artifact. Nếu có matrix, tìm đúng variant/OS/JDK.
4. Xác minh full SHA trong embedded metadata khớp checkout SHA trong CI logs/provenance.
5. Xem test reports, dependency scan/SBOM, build logs và approvals của lần build tương ứng.
6. Xem diff Git của commit so với bản đang chạy trước đó; **branch hiện tại có thể đã tiến lên**, nên không dùng HEAD mới nhất của branch để suy code đang deploy.
7. Nếu cần rollback, chọn **artifact digest đã qua QA**, không build lại một JAR cũ chỉ bằng tên version rồi đoán nó giống cũ.
8. Sau rollback, xác nhận runtime deployment record/endpoint/digest phản ánh chính artifact đã chọn.

**Nếu metadata endpoint và registry digest không khớp:** coi là dấu hiệu release process cần điều tra (deploy nhầm artifact, registry overwrite, CI stale output, image chứa JAR khác hoặc metadata bị can thiệp). Không tự sửa endpoint để che sự bất nhất.

## 20. Những lỗi dễ gặp và cách sửa

| Hiện tượng | Nguyên nhân khả dĩ | Hành động đúng |
| --- | --- | --- |
| `/actuator/info` trả rỗng dù có Actuator | Chưa sinh build-info/git.properties hoặc contributor/config chưa bật | Bật `build-info`/`bootBuildInfo`; inspect resource và HTTP exposure |
| `GET /actuator/info` trả 404 | HTTP info endpoint chưa expose | `management.endpoints.web.exposure.include=health,info`; cấu hình access an toàn |
| Spring không tạo `BuildProperties` bean | `META-INF/build-info.properties` không có trên classpath hoặc goal/task không chạy | Kiểm tra Maven execution/Gradle `bootBuildInfo` và jar entries |
| File chỉ có `build.version`, không có commit/run | Chưa truyền CI parameters hoặc chưa thêm additionalProperties | Cấu hình fields và verify metadata sau package |
| Release artifact ghi `ci.commit=local` | CI properties thiếu; fallback dev bị dùng trong release | Fail pipeline khi metadata fallback; đối chiếu SHA với `git rev-parse HEAD` |
| Commit trong JAR khác commit PR head | PR build synthetic merge commit | Lưu riêng built SHA và PR head SHA; không gọi cả hai là cùng identity |
| `git.branch=HEAD` hoặc rỗng | CI checkout detached HEAD | Ghi trigger ref từ CI event; giữ SHA từ checked-out commit |
| Cùng run ID có hai JAR khác nhau | Workflow rerun với attempt khác hoặc matrix jobs | Lưu attempt, job/matrix và **artifact digest** |
| Tên file/version giống nhau nhưng SHA-256 khác | Artifact rebuilt hoặc metadata timestamp/run ID khác | So sánh bytes, build inputs và provenance; đừng coi version là identity |
| SHA-256 lưu trong JAR không khớp file sau cùng | Self-reference khi nhúng digest vào chính artifact | Tính hash **sau** packaging và lưu bên ngoài |
| Maven import BOM nhưng không tạo build-info | BOM chỉ quản lý dependency versions | Bind `spring-boot:build-info` và `repackage` trong Boot Maven Plugin |
| Gradle `bootBuildInfo` luôn chạy lại | `build.time` mặc định thay đổi | Cân nhắc `excludes = ['time']`; kiểm tra toàn bộ các dynamic fields |
| CI build từ repo khác nhưng ghi same SHA | Thiếu repository namespace | Lưu repository URI/ID cùng full SHA; không dùng SHA đơn lẻ làm complete provenance record |
| Public endpoint lộ tên branch/private repo | Info hoặc custom lineage endpoint expose quá rộng | Giới hạn HTTP exposure, Spring Security, hoặc chỉ giữ metadata nội bộ |
| Artifact upload đúng nhưng deploy lại build | Deploy stage chạy Maven/Gradle thêm lần nữa | Promote **exact tested file/digest**; không rebuild ở deploy |
| OCI tag `latest` trỏ version khác | Mutable image tag | Pin image digest và lưu mapping JAR digest → image digest |
| Tệp `git.properties` và build-info có hai SHA khác nhau | Plugins dùng checkout/ref/thời điểm khác nhau | Kiểm tra pipeline, chỉ dùng một authoritative built SHA, thêm consistency gate |
| CI output có hash nhưng không chứng minh builder đáng tin | Chỉ checksum, không có signed provenance | Dùng attestation/signature/identity checks theo supply-chain policy |

### Quy trình debug nhanh

1. **Xác định file JAR thực** đã được build và sẽ phát hành.
2. Dùng `jar tf` tìm `BOOT-INF/classes/META-INF/build-info.properties`.
3. Dùng `unzip -p` đọc commit/ref/run/attempt trực tiếp từ binary.
4. Kiểm tra `git rev-parse HEAD` của CI checkout và full triggering ref.
5. Xem CI run ID, attempt, job/matrix, test logs, validation status.
6. Tính lại SHA-256 của file và so sánh với artifact store/deployment record.
7. Nếu cần provenance đáng tin, xác minh signature/attestation subject digest và builder identity.
8. Nếu mismatch, fail gate và sửa build/deploy script; **không sửa JAR sau khi đã ký/ghi digest**.

## 21. Bài tập củng cố

**Tình huống A.** Có artifact version `1.0.0` và ref `main`. Có đủ để xác định commit đã build?

*Đáp án:* Không. Branch là con trỏ có thể di chuyển; version có thể được tái sử dụng. Cần full commit SHA cùng repository identity.

**Tình huống B.** GitHub Actions rerun cùng workflow `run_id=8123456789`. Vì sao cần lưu attempt?

*Đáp án:* `run_id` giữ nguyên trong GitHub Actions rerun, còn `run_attempt` tăng. Hai lần có thể chạy trên môi trường khác hoặc tạo artifact khác; cần attempt và digest để phân biệt.

**Tình huống C.** Cùng commit được build hai lần, nhúng hai run IDs khác nhau vào `build-info.properties`. Kết quả SHA-256 JAR giống nhau chứ?

*Đáp án:* Thông thường **khác**, vì file metadata nằm trong archive đã đổi. Nếu cần byte-for-byte equality giữa các invocation, đẩy run ID/attempt sang provenance ngoài, đồng thời kiểm soát các input phi xác định khác.

**Tình huống D.** CI đã tính digest D của JAR, sau đó chèn D vào manifest rồi upload. Có thể dùng D để xác minh file đã upload?

*Đáp án:* Không, vì chèn manifest đã đổi byte của JAR. Phải tính hash **sau mọi thay đổi trên artifact**, rồi lưu hash bên ngoài.

**Tình huống E.** Một Pull Request trên GitHub có PR head SHA khác `git rev-parse HEAD` trong job. Metadata nên ghi gì?

*Đáp án:* Lưu built commit SHA từ checkout (có thể là synthetic merge commit), cùng optional PR head SHA trong field riêng. Đừng nói PR head SHA là source thực đã build nếu công việc build thực sự chạy trên merge commit.

**Tình huống F.** Có `spring-boot-starter-actuator` nhưng `/actuator/info` không hiển thị commit và run ID. Chỉ thêm `management.endpoints.web.exposure.include=health,info` có đủ?

*Đáp án:* Chưa. Phải tạo `META-INF/build-info.properties` hoặc `git.properties` đúng, bật contributor, đưa file vào classpath và bảo vệ endpoint theo policy.

**Tình huống G.** Maven file `pom.xml` đã khai báo build-info custom fields nhưng CI quên truyền `-Dci.commit`. Build và test vẫn pass. Có nên publish?

*Đáp án:* Không. Bài mẫu dùng fallback `local` cho developer, release gate phải fail nếu commit/run identity không khớp checkout và CI event.

**Tình huống H.** Một run tạo ba module JAR khác nhau. Cùng run ID có thể đại diện cho cả ba file không?

*Đáp án:* Run ID chỉ liên kết cùng workflow; mỗi artifact phải có module/coordinate và **digest riêng**, có thể thêm job/matrix variant.

**Tình huống I.** Docker image có label `org.opencontainers.image.revision` trỏ SHA X, nhưng deployment registry ghi digest tương ứng JAR từ SHA Y. Nên tin cái nào?

*Đáp án:* Chưa tin bên nào như bằng chứng tuyệt đối. Đối chiếu signed provenance/subject digest, build logs, JAR bytes trong image và deployment record; các labels là dữ liệu tự khai báo.

**Tình huống J.** Team muốn rollback bằng lệnh “build lại tag v1.0.0 rồi deploy”. Có đảm bảo đúng binary đã qua QA trước kia?

*Đáp án:* Không. Tag/version chỉ là một input; output có thể khác do dependencies, toolchain, timestamps hoặc run metadata. Nên rollback bằng **artifact digest đã qua QA**.

## 22. Checklist nghiệm thu truy vết artifact → CI → source

**Nguồn và build:**

- Ghi repository identity, **full SHA của checkout thực được build**, trigger ref và loại event.
- CI run ID có namespace provider/repository; lưu attempt và job/variant khi cần.
- Local fallback được phép cho dev nhưng bị release gate **từ chối**.
- Source tree và dependency/toolchain inputs được xác định; build chạy test/check bắt buộc.

**Metadata nhúng:**

- Maven `build-info` hoặc Gradle `bootBuildInfo` thực sự chạy.
- `META-INF/build-info.properties` tồn tại trong compiled classes và `BOOT-INF/classes/META-INF` của executable JAR.
- Custom fields `ci.commit`, `ci.ref`, `ci.run.id`, `ci.run.attempt` khớp CI context.
- Nếu có `git.properties`, không mâu thuẫn với full SHA đã ghi.
- Endpoint Actuator/custom lineage không lộ secrets hoặc không bị public ngoài chính sách.

**Artifact và phát hành:**

- Tính SHA-256 **sau** khi hoàn tất packaging; không sửa JAR sau hash/sign.
- CI artifact store, registry, image và deployment đều tham chiếu **đúng digest đã kiểm chứng**.
- Rerun/matrix/module khác nhau được phân biệt bằng attempt/job/artifact identity.
- Trước production có test, archive inspection, smoke test và approvals theo policy.
- Nếu yêu cầu provenance đáng tin, CI ký attestation với subject digest và builder/source identity, deploy gate xác minh.
- Nếu yêu cầu reproducibility, không nhúng run-specific metadata vào JAR; so sánh builds độc lập thực tế.

**Kết luận:** **Commit SHA cho biết code revision, ref cho biết ngữ cảnh, run ID + attempt cho biết lượt CI, còn artifact digest xác định chính xác bytes đã phát hành.** Spring Boot `build-info`/`bootBuildInfo` và `BuildProperties` cung cấp đường chuẩn để đưa metadata vào executable JAR; Git plugin/`git.properties` là nguồn bổ sung. Chuỗi truy vết chỉ hoàn chỉnh khi **metadata trong JAR khớp CI checkout, digest của file được kiểm tra, và deployment dùng chính artifact đã qua QA**.

### Tài liệu chính thức

- Spring Boot 3.3.13 — Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/
- Spring Boot — Maven build-info goal: https://docs.spring.io/spring-boot/3.4/maven-plugin/build-info.html
- Spring Boot 3.3 — Gradle Plugin: Generating Build Information: https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html
- Spring Boot 3.3.13 — Actuator info: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3.13 — BuildProperties API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/info/BuildProperties.html
- GitHub Actions — Contexts Reference: https://docs.github.com/en/actions/reference/workflows-and-actions/contexts
- GitHub Actions — Default Variables: https://docs.github.com/en/actions/reference/workflows-and-actions/variables
- Git — `rev-parse`: https://git-scm.com/docs/git-rev-parse
- SLSA — Provenance v1.1: https://slsa.dev/spec/v1.1/provenance
- OCI Image Specification — Annotations: https://github.com/opencontainers/image-spec/blob/main/annotations.md