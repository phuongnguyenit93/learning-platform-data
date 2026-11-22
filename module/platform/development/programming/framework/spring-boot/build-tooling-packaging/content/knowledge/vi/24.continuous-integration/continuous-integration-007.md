# Đặt điều kiện xuất bản sau khi các bước kiểm tra bắt buộc thành công

Một bản build Spring Boot có thể compile thành công và tạo được JAR/container image nhưng vẫn chưa đủ điều kiện phát hành. Artifact chỉ được publish khi tất cả **quality gates bắt buộc** đã chạy và trả về kết quả thành công: unit tests, integration tests, kiểm tra chất lượng mã, dependency/security scan, kiểm tra package và các quy tắc release đã được nhóm thống nhất.

Bài học tập trung vào ba nguyên tắc:

1. **Mỗi gate có hợp đồng rõ ràng:** xác định lệnh nào chạy, report nào được tạo, tiêu chí pass/fail và cách xử lý khi test/scanner infrastructure gặp lỗi.
2. **Publish phụ thuộc vào toàn bộ gate:** nếu một gate fail, bị cancel, bị skip ngoài dự kiến hoặc không có bằng chứng thì job xuất bản không được chạy.
3. **Đúng artifact đã được kiểm tra được phát hành:** khi tách build và publish thành nhiều job, truyền chính JAR/image đã qua QA, kiểm tra checksum/digest và không âm thầm tạo binary khác ở job publish.

Ví dụ dùng **Java 17, Spring Boot 3.3.13, Maven 3.9.x, Gradle 8.x** và GitHub Actions. Đây là bộ version minh họa cố định; project thực tế cần chọn toolchain tương thích và đã được tổ chức phê duyệt.

## 1. Mô hình gate từ source đến release

Một pipeline phát hành Spring Boot có thể được tổ chức như sau:

```text
Pull request / protected release tag
                 |
                 v
        Checkout source + toolchain
                 |
                 v
       Compile + unit tests (UT)
                 |
                 v
       Integration tests (IT)
                 |
                 v
       Static / code quality checks
                 |
                 v
       Dependency / security / license checks
                 |
                 v
       Package executable JAR / OCI image
                 |
                 v
       Artifact smoke test + checksum
                 |
                 v
        All required gates SUCCESS
                 |
                 v
         Publish exact artifact
                 |
                 v
       Registry / artifact repository
                 |
                 v
        Verify remote artifact identity
                 |
                 v
        Protected deployment approval
```

Không phải project nào cũng cần một job riêng cho từng gate. Một số bước có thể chạy trong cùng Maven/Gradle invocation hoặc chạy song song trong CI. Điều quan trọng là **đầu ra của từng gate phải nằm trên đường phụ thuộc trước publish**.

| Gate | Bằng chứng | Điều kiện đạt |
| --- | --- | --- |
| Compile | Compiler exit code, compiled classes | Không có compilation error |
| Unit test | Surefire/Gradle test reports | Test được phát hiện và tất cả pass |
| Integration test | Failsafe/Gradle IT reports | IT chạy, kết quả được verify |
| Code quality | Lint, formatting, static analysis | Tất cả rule bắt buộc đạt |
| Security | CVE, secret, malware, license scan | Không có finding chặn release theo policy |
| Package | JAR layout, manifest, startup/smoke test | Đúng executable artifact và chạy được |
| Integrity | Git commit, tool versions, SHA-256/digest | Artifact gắn với đúng source/build |
| Release policy | Version, tag, approval, branch rule | Nguồn và điều kiện phát hành hợp lệ |

Phân biệt **required** và **advisory** checks. Báo cáo coverage hoặc scanner finding ở mức cảnh báo có thể chỉ mang tính thông tin. Gate bắt buộc phải có tiêu chí pass/fail. Không gọi một job là required nếu pipeline vẫn publish khi job đó fail hoặc bị bỏ qua.

## 2. Trạng thái nào cho phép publish?

Trong CI, một gate có thể có các trạng thái:

- **Success:** hoàn tất và đạt điều kiện.
- **Failure:** kiểm tra phát hiện lỗi hoặc command trả exit code khác 0.
- **Cancelled:** bị hủy do timeout, người dùng hoặc workflow cancellation.
- **Skipped:** không chạy do điều kiện, dependency hoặc cấu hình.
- **Không có kết quả:** job không được tạo, runner gặp sự cố hoặc status không được gửi.

Với release gate, chỉ **Success rõ ràng** mới đủ điều kiện. Job bị skip không phải bằng chứng rằng kiểm tra đã đạt.

| Unit tests | Security scan | Integration tests | Publish |
| --- | --- | --- | --- |
| Success | Success | Success | Được xét điều kiện release tiếp theo |
| Failure | Success | Success | Không chạy |
| Success | Failure | Success | Không chạy |
| Success | Success | Skipped | Không chạy nếu IT là required |
| Success | Success | Cancelled | Không chạy |
| Success | Success | Success | Vẫn cần đúng tag/version, approval và artifact validation |

### 2.1. Nguyên tắc fail-closed

Release pipeline nên **mặc định từ chối phát hành khi thiếu bằng chứng**:

- Test command không chạy hoặc không tìm thấy test theo policy thì gate phải fail.
- Scanner không kết nối được database/dịch vụ cần thiết thì gate phải fail hoặc đi vào exception process được duyệt; không tự coi lỗi scanner là pass.
- Không tìm thấy artifact, checksum không khớp hoặc download lỗi thì publish dừng.
- Required job bị skip/cancel/fail thì publish dừng.
- Không dùng `continue-on-error: true`, `|| true`, `-x test`, `-DskipTests` hoặc cấu hình tương tự để biến required gate thành advisory.
- Không đặt `always()` lên publish job để “dù job trước fail vẫn publish”. `always()` phù hợp cho thu thập report/cleanup, không phải bỏ qua quality gates.

Một dashboard xanh chỉ có ý nghĩa khi pipeline thực sự chạy các gate cần thiết. Kiểm tra cả test count, scanner scope và danh sách job mà publish phụ thuộc.

## 3. Xác định release policy trước khi viết workflow

Ví dụ policy cho một Spring Boot service:

| Nhóm | Điều kiện release |
| --- | --- |
| Source | Commit từ protected branch hoặc release tag được bảo vệ |
| Java/toolchain | Java 17 đúng cấu hình, Maven/Gradle Wrapper đã pin |
| Unit tests | Tất cả test bắt buộc pass; có test được phát hiện |
| Integration tests | IT chạy trên cấu hình gần production và pass |
| Quality | Checkstyle/SpotBugs/JaCoCo hoặc rule tương ứng pass |
| Security | Dependency/image scan không có finding chặn theo ngưỡng đã duyệt |
| Dependency | Không có SNAPSHOT/dynamic version nếu release policy cấm |
| Packaging | Boot executable JAR hoặc OCI image đúng loại |
| Integrity | Checksum/digest được tính và lưu |
| Publish | Chỉ chạy sau mọi required gates |
| Approval | Protected release environment được duyệt khi cần |

Tránh điều kiện mơ hồ như “CI xanh” hoặc “đã kiểm tra đầy đủ”. Mỗi điều kiện cần chỉ ra **job/task nào thực hiện**, **bằng chứng ở đâu**, **trạng thái nào được chấp nhận**.

### 3.1. Phân biệt build, publish và deploy

- **Build/package:** tạo JAR hoặc container image.
- **Publish:** đưa artifact lên Maven repository, package registry hoặc OCI registry.
- **Deploy:** triển khai artifact đã publish vào staging/production.

Ba hành động có thể có gate và quyền khác nhau. Publisher chỉ cần quyền ghi artifact; deployer cần quyền triển khai vào môi trường. Không cấp production deployment secrets cho job chỉ chạy test.

## 4. Maven lifecycle: dùng verify để chốt unit và integration tests

Maven có lifecycle chuẩn. Với project JAR, các phase liên quan thường là:

```text
validate
   |
compile
   |
test-compile
   |
test                 Surefire: unit tests
   |
package              executable JAR
   |
pre-integration-test setup environment
   |
integration-test     Failsafe: integration tests
   |
post-integration-test teardown environment
   |
verify               Failsafe verifies IT results
   |
install
   |
deploy
```

### 4.1. Surefire và Failsafe có vai trò khác nhau

- **Maven Surefire Plugin** chạy unit tests ở phase `test`.
- **Maven Failsafe Plugin** chạy integration tests ở `integration-test` và kiểm tra kết quả ở `verify`.
- Failsafe cố ý không dừng build ngay tại `integration-test` khi test fail, để `post-integration-test` có thể dọn môi trường.
- Vì vậy, với integration tests, hãy gọi **`mvn verify`**, không chỉ gọi phase `integration-test` trực tiếp. Nếu dừng ở `integration-test`, các bước teardown/verify sau đó có thể không chạy.

`verify` chạy các phase trước nó, gồm compile, unit tests, package và integration test lifecycle đã cấu hình. Chỉ gọi `mvn package` không đảm bảo Failsafe đã chạy.

### 4.2. POM Spring Boot cho unit và integration tests

Ví dụ dùng Java 17, Spring Boot 3.3.13, JUnit 5. `*Test.java` dành cho Surefire; `*IT.java` dành cho Failsafe.

`pom.xml`:

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
    <artifactId>release-gate-demo</artifactId>
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

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.2.5</version>
                <configuration>
                    <includes>
                        <include>**/*IT.java</include>
                    </includes>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

`failIfNoTests` giúp ví dụ này không âm thầm pass nếu test class cần thiết không được phát hiện. Với multi-module có module không có IT, cấu hình theo module/profile thay vì bật cứng cho mọi module.

### 4.3. Spring Boot application

`src/main/java/dev/example/releasegate/ReleaseGateApplication.java`:

```java
package dev.example.releasegate;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReleaseGateApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReleaseGateApplication.class, args);
    }
}
```

`src/main/java/dev/example/releasegate/StatusController.java`:

```java
package dev.example.releasegate;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {

    @GetMapping("/status")
    public String status() {
        return "ready";
    }
}
```

### 4.4. Unit test chạy bằng Surefire

`src/test/java/dev/example/releasegate/StatusControllerTest.java`:

```java
package dev.example.releasegate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(StatusController.class)
class StatusControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void returnsReady() throws Exception {
        mvc.perform(get("/status"))
                .andExpect(status().isOk())
                .andExpect(content().string("ready"));
    }
}
```

Đây là MVC slice test: Spring tạo web layer cần thiết và `MockMvc` gọi controller mà không cần mở TCP server thật.

### 4.5. Integration test chạy bằng Failsafe

`src/test/java/dev/example/releasegate/StatusControllerIT.java`:

```java
package dev.example.releasegate;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class StatusControllerIT {

    @LocalServerPort
    private int port;

    @Autowired
    private TestRestTemplate http;

    @Test
    void applicationServesHttpRequest() {
        String body = http.getForObject(
                "http://localhost:" + port + "/status",
                String.class
        );

        assertThat(body).isEqualTo("ready");
    }
}
```

IT khởi động embedded server trên cổng ngẫu nhiên và gửi HTTP request thật qua loopback. Nó kiểm tra application context, web server và routing; chưa thay thế test database, broker hoặc dịch vụ ngoài nếu ứng dụng phụ thuộc chúng.

### 4.6. Chạy và đọc kết quả

Từ project root:

```bash
./mvnw -B -ntp clean verify
```

Report thường nằm ở:

- `target/surefire-reports/` cho unit tests.
- `target/failsafe-reports/` cho integration tests.

Khi thành công, Maven kết thúc bằng:

```text
BUILD SUCCESS
```

Đây là dòng kết thúc tổng quát; số test và log cụ thể tùy project. Không dùng một output mẫu với số test cố định làm tiêu chí duy nhất; hãy kiểm tra exit code và report thực.

### 4.7. Flag làm mất hiệu lực gate

Không dùng các flag sau trong release job nếu test là required:

| Flag/cấu hình | Tác động |
| --- | --- |
| `-DskipTests` | Có thể bỏ chạy test theo cấu hình Surefire/Failsafe |
| `-Dmaven.test.skip=true` | Bỏ cả biên dịch và chạy test |
| `-DskipITs` | Bỏ integration tests/verification của Failsafe |
| `-Dmaven.test.failure.ignore=true` | Có thể bỏ qua lỗi test |
| `testFailureIgnore=true` | Làm test failure không chặn build |

Nếu cần profile build nhanh cho developer, tách profile khỏi release pipeline và không cho publish job dùng nó.

## 5. Gradle: nối integration tests vào lifecycle check

Với Gradle Java Plugin:

- `test` chạy unit tests.
- `check` là lifecycle task tổng hợp verification tasks; mặc định phụ thuộc `test`.
- `build` phụ thuộc `check` và `assemble`.

Nếu dự án tạo custom task `integrationTest` nhưng **không gắn task đó vào `check`**, lệnh `./gradlew build` có thể hoàn thành mà IT không chạy. Phải nối custom test suite vào verification lifecycle hoặc liệt kê rõ trong CI.

### 5.1. Gradle Groovy DSL cho Spring Boot

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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

tasks.named('test') {
    useJUnitPlatform()
}

sourceSets {
    integrationTest {
        java.srcDir file('src/integrationTest/java')
        resources.srcDir file('src/integrationTest/resources')
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.register('integrationTest', Test) {
    description = 'Runs integration tests against the Spring Boot application.'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    include '**/*IT.class'
    shouldRunAfter tasks.named('test')
    useJUnitPlatform()
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

`integrationTestImplementation` kế thừa dependencies của `testImplementation`; `integrationTestRuntimeOnly` kế thừa runtime-only dependencies của test. Source set có thư mục riêng để IT không bị lẫn với unit test.

### 5.2. Đặt integration test đúng thư mục

Dùng cùng nội dung test ở mục Maven nhưng đặt tại:

`src/integrationTest/java/dev/example/releasegate/StatusControllerIT.java`

Tên class kết thúc bằng `IT` và custom task có include pattern `**/*IT.class`.

### 5.3. Chạy và kiểm tra task graph

```bash
./gradlew clean check
./gradlew clean build
./gradlew check --dry-run
```

- `check` phải chạy unit test và `integrationTest`.
- `build` gọi `check` rồi `assemble`, do đó bao gồm verification task đã được gắn.
- `--dry-run` hiển thị task graph dự kiến, hữu ích để xác nhận IT nằm trong chuỗi.

Nếu CI chỉ gọi `./gradlew bootJar`, task `check` không nhất thiết chạy. `bootJar` là packaging task; nó không tự chứng minh toàn bộ quality gates đã pass.

### 5.4. Gradle skip/ignore

Không bỏ qua required task trong release:

- `-x test` bỏ unit test.
- `-x integrationTest` bỏ custom integration task.
- `-x check` bỏ aggregate verification task.
- `ignoreFailures = true` có thể khiến test failure không fail build.
- `onlyIf { false }` có thể làm task không chạy.

Nếu task bị skip ngoài dự kiến, release pipeline phải phát hiện và fail. Kiểm tra task graph, report và test count.

## 6. Nối quality gates vào dependency graph

Có hai kiểu tổ chức phổ biến.

### 6.1. Một job, một build command

Ví dụ Maven:

```bash
set -euo pipefail
./mvnw -B -ntp clean verify
./ci/run-required-quality-checks.sh
./ci/validate-release-artifact.sh target/release-gate-demo-1.0.0.jar
./ci/publish-release-artifact.sh target/release-gate-demo-1.0.0.jar
```

Shell dừng khi lệnh bắt buộc trả exit code khác 0. Mỗi script trong ví dụ là script của project, cần thực hiện gate tương ứng và trả exit code non-zero nếu điều kiện không đạt.

Maven có lifecycle phase `deploy` sau `verify`. Nếu plugins được bind đúng, `mvn deploy` chạy các phase trước nó trước khi deploy. Nhưng scan/security/approval nằm ngoài Maven vẫn phải được nối vào điều kiện publish.

### 6.2. Nhiều job có quan hệ needs

Một CI hiện đại thường tách job để chạy song song:

```text
       +--------- verify ---------+
       |                          |
       |                          v
       |                    upload artifact
       |
       +--------- security -------+
                    |
                    v
             all required jobs
                    |
                    v
                  publish
                    |
                    v
                  deploy
```

Trong GitHub Actions, `jobs.<job_id>.needs` khai báo những job phải hoàn thành thành công trước job hiện tại. Nếu dependency fail hoặc bị skip, downstream job cũng bị skip theo mặc định, trừ khi condition của downstream job được viết để tiếp tục.

Ví dụ:

```yaml
jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - run: ./mvnw -B -ntp clean verify

  security:
    runs-on: ubuntu-latest
    steps:
      - run: ./ci/run-security-gate.sh

  publish:
    needs: [verify, security]
    runs-on: ubuntu-latest
    steps:
      - run: ./ci/publish-release-artifact.sh
```

`publish` chỉ được chạy sau khi cả `verify` và `security` thành công. Danh sách `needs` phải chứa **tất cả required gates**; job không có trong danh sách không tự chặn publish.

### 6.3. Cẩn thận với if, success và always

Mẫu release condition:

```yaml
publish:
  needs: [verify, security]
  if: ${{ success() && github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v') }}
```

Điều kiện yêu cầu dependencies thành công và workflow được kích hoạt bởi tag release dạng `v...`.

Không dùng:

```yaml
publish:
  needs: [verify, security]
  if: ${{ always() }}
```

`always()` có thể khiến job được xét chạy ngay cả khi dependency fail/skip. Nó phù hợp cho report/cleanup, không phải điều kiện publish an toàn.

Nếu một gate optional theo policy, định nghĩa rõ event/nhánh nào được miễn và điều kiện miễn có thể audit. Không làm gate bắt buộc thành optional bằng expression quá rộng.

## 7. GitHub Actions: workflow verify → security → publish

Ví dụ dành cho Maven project ở mục 4. Workflow chạy kiểm tra trên Pull Request vào `main` và khi push tag release `v*`. Publish chỉ chạy trên tag, sau khi `verify` và `security` cùng thành công.

Tệp `.github/workflows/release-gates.yml`:

```yaml
name: Spring Boot release gates

on:
  pull_request:
    branches: [main]
  push:
    tags:
      - 'v*'

permissions:
  contents: read

jobs:
  verify:
    name: Required build and tests
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Run unit and integration tests
        run: ./mvnw -B -ntp clean verify

      - name: Prepare exact verified artifact
        shell: bash
        run: |
          set -euo pipefail
          mkdir -p dist
          cp target/release-gate-demo-1.0.0.jar dist/
          sha256sum dist/release-gate-demo-1.0.0.jar \
            > dist/release-gate-demo-1.0.0.jar.sha256

      - name: Upload verified artifact
        uses: actions/upload-artifact@v4
        with:
          name: spring-boot-jar-${{ github.sha }}
          path: dist/
          if-no-files-found: error
          retention-days: 7

  security:
    name: Required security scan
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Scan source and dependency manifests
        run: |
          trivy fs \
            --scanners vuln,misconfig,secret \
            --severity HIGH,CRITICAL \
            --exit-code 1 \
            .

  publish:
    name: Publish verified release
    needs: [verify, security]
    if: ${{ success() && github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v') }}
    runs-on: ubuntu-latest
    environment: release
    permissions:
      contents: read

    steps:
      - name: Checkout release metadata
        uses: actions/checkout@v4

      - name: Download artifact from verify job
        uses: actions/download-artifact@v4
        with:
          name: spring-boot-jar-${{ github.sha }}
          path: dist/

      - name: Verify artifact checksum
        run: |
          sha256sum --check dist/release-gate-demo-1.0.0.jar.sha256

      - name: Publish the verified JAR
        env:
          RELEASE_REPOSITORY_URL: ${{ vars.RELEASE_REPOSITORY_URL }}
          MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
          MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
        run: |
          set -euo pipefail
          test -n "${RELEASE_REPOSITORY_URL:-}"
          test -n "${MAVEN_USERNAME:-}"
          test -n "${MAVEN_PASSWORD:-}"

          ./mvnw -B -ntp -s .ci/settings-release.xml \
            org.apache.maven.plugins:maven-deploy-plugin:3.1.3:deploy-file \
            -Dfile=dist/release-gate-demo-1.0.0.jar \
            -DpomFile=pom.xml \
            -DrepositoryId=release-repo \
            -Durl="$RELEASE_REPOSITORY_URL"
```

### 7.1. Điều kiện để workflow chạy

- Repository có Maven Wrapper, POM, Java source/test ở mục 4 và `.ci/settings-release.xml`.
- Runner của `security` job có Trivy version đã pin/quản lý và tải được scanner database. Nếu scanner chưa được cài hoặc không hoạt động, job phải fail.
- `MAVEN_USERNAME`, `MAVEN_PASSWORD` và `RELEASE_REPOSITORY_URL` được thiết lập trong GitHub Environment/Variables/Secrets tên `release`.
- Maven server ID trong settings file là `release-repo`, trùng với `-DrepositoryId=release-repo`.
- Version `1.0.0` trong POM phải phù hợp tag release. Project thực tế cần rule kiểm tra tag/version và tránh publish lại cùng immutable release coordinate.
- Đường dẫn JAR phải đúng output thực tế. Với multi-module có thể là `api-service/target/...jar`.
- Action `@v4` là version tag minh họa. Production nên pin action tới full commit SHA đã review hoặc dùng workflow dependency lock theo policy.

### 7.2. Maven settings cho release repository

`.ci/settings-release.xml`:

```xml
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0 https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>release-repo</id>
            <username>${env.MAVEN_USERNAME}</username>
            <password>${env.MAVEN_PASSWORD}</password>
        </server>
    </servers>
</settings>
```

File này chỉ chứa tên biến, không chứa secret. Maven `deploy-file` chọn credentials theo server ID. Không in settings đã resolve hoặc bật Maven `-X` trong log công khai.

### 7.3. Vì sao publish job tải artifact từ verify job?

`verify` job tạo JAR, tính SHA-256 và upload artifact. `publish` job tải đúng artifact cùng workflow run, kiểm tra checksum rồi publish file đó bằng `deploy-file`.

Cách này bảo đảm:

- Publish job không tự compile/package lại JAR với toolchain/cache khác.
- Checksum xác nhận file download khớp file đã upload.
- POM và settings được lấy từ cùng commit/tag.
- Nếu artifact thiếu hoặc checksum sai, publish dừng trước khi gọi repository.

Trong release pipeline nghiêm ngặt, sau publish cần tải lại artifact từ remote repository bằng read identity và so sánh checksum/digest. Log “upload success” chưa phải bằng chứng remote bytes khớp file đã kiểm tra.

### 7.4. Security scan là gate thực sự

Lệnh `trivy fs` minh họa scan source/dependency manifests, misconfiguration và secret. `--exit-code 1` làm command trả lỗi khi có finding thuộc severity đã chọn. Runner cần cài đúng Trivy version và có database cập nhật.

Ngưỡng `HIGH,CRITICAL` chỉ là ví dụ. Tổ chức cần xác định policy theo loại ứng dụng/môi trường và exception process. Nếu scanner khác được dùng, vẫn giữ hợp đồng: **scan không chạy hoặc gặp lỗi hạ tầng thì không được coi là pass**.

## 8. Branch protection và release environment là hai lớp riêng

Workflow `needs` điều khiển job dependency trong **một workflow run**. Nó không tự bảo đảm mọi pull request phải qua các job đó trước khi merge.

Cần cấu hình repository:

1. **Branch protection/ruleset:** yêu cầu status checks `Required build and tests` và `Required security scan` thành công trước khi merge vào `main`.
2. **Release tag policy:** giới hạn ai được tạo/push tag `v*` và bảo vệ tag đã phát hành.
3. **Environment protection:** job `publish` tham chiếu environment `release`; environment có thể yêu cầu reviewer, giới hạn branch/tag hoặc chờ approval.
4. **Secret scoping:** chỉ release job có publisher credentials; test job không cần write token.
5. **Action policy:** pin actions, giới hạn `GITHUB_TOKEN` permissions và review workflow changes.

`needs` ngăn publish trong workflow khi dependency fail; branch protection ngăn merge code chưa đạt required status; environment protection ngăn job có quyền publish chạy trước khi approval/policy đạt. Các cơ chế này bổ sung cho nhau.

### 8.1. Required status checks phải có tên ổn định

Đặt job names rõ ràng và duy nhất giữa các workflow. Khi bật branch protection, chọn đúng check contexts đã xuất hiện từ workflow thực. Nếu workflow bị skip do path filters/conditions, hãy bảo đảm required check không biến mất hoặc pending vô hạn; thiết kế trigger để required jobs chạy trên thay đổi cần kiểm tra.

### 8.2. Không cấp publish secrets cho Pull Request từ fork

PR từ fork có thể chứa build script do contributor sửa. Job chạy code đó không nên có quyền publish hoặc truy cập release secrets. Chạy test/scan với quyền read-only; chỉ cấp writer credentials cho protected release job sau khi source đã được review/merge và qua gates.

## 9. Gradle: nối check và publish task với required gates

Với Gradle, `./gradlew clean build` chỉ bao gồm các verification tasks thực sự nối vào `check`. Nếu đã cấu hình `integrationTest` như mục 5 và gắn vào `check`, `build` sẽ chạy unit tests, integration tests và assemble.

Với Gradle Maven Publish Plugin, không mặc định rằng mọi `publish` task tự phụ thuộc `check`. Có thể nối task publish tới check:

```groovy
import org.gradle.api.publish.maven.tasks.PublishToMavenRepository

tasks.withType(PublishToMavenRepository).configureEach {
    dependsOn tasks.named('check')
}
```

Đây là fragment cho project đã áp dụng `maven-publish` và khai báo Maven publications/repositories. `check` phải bao gồm đầy đủ required verification tasks. Trong CI tách job, vẫn nên có `needs: [verify, security]` ở publish job để bảo đảm gate ngoài Gradle cũng thành công.

### 9.1. Gradle CI command

```bash
./gradlew --no-daemon clean build
```

Nếu pipeline có static analysis, dependency verification, SBOM hoặc image scan riêng, chúng phải là task trong `check` hoặc job CI riêng được publish job phụ thuộc. Không chỉ nhìn `BUILD SUCCESSFUL` nếu task graph không gồm các gate policy yêu cầu.

### 9.2. Publish exact artifact giữa các job

Trong workflow nhiều job:

1. `verify` chạy `./gradlew clean build`, lưu đúng JAR/Boot JAR và SHA-256.
2. `security` scan source, dependency graph hoặc image theo policy.
3. `publish` khai báo `needs: [verify, security]`, tải JAR/checksum từ verify job.
4. Kiểm tra checksum trước khi publish.
5. Dùng publisher được cấu hình để nhận **file đã tải**; không gọi lại build task làm ra artifact mới rồi thay file cũ.

Nếu Gradle `publish` task tự build lại component từ source, hãy kiểm tra task graph/outputs. Với release yêu cầu exact artifact promotion, publish chính file đã xác minh hoặc giữ build + publish trong một task graph có dependency rõ ràng.

## 10. Một job hay nhiều job?

| Tiêu chí | Một job / một invocation | Nhiều job với needs |
| --- | --- | --- |
| Thiết lập | Đơn giản, ít cấu hình truyền artifact | Cần artifact handoff và checksum |
| Parallelism | Hạn chế | Test, scan, policy có thể chạy song song |
| Quyền | Có thể một job chứa nhiều credentials | Tách read/test và write/publish dễ hơn |
| Debug | Log liền mạch | Mỗi gate có report riêng |
| Exact artifact | Cùng workspace, dễ giữ file | Cần upload/download và verify checksum |
| Approval | Có thể đặt environment cho job cuối | Dễ tách publish/deploy protected job |
| Phù hợp | Project nhỏ, lifecycle rõ | Monorepo, nhiều scanner/policy, release enterprise |

Một Maven invocation `mvn clean deploy` đi qua các phase trước `deploy`, gồm `verify`, nếu plugins được bind đúng. Nhưng scanner/approval nằm ngoài Maven vẫn phải được nối vào điều kiện publish.

## 11. Các gate khác nên cân nhắc cho Spring Boot

### 11.1. Code quality và coverage

- Checkstyle/SpotBugs/PMD hoặc quy tắc tương đương.
- JaCoCo coverage thresholds nếu nhóm đã định nghĩa baseline.
- Formatting/lint checks.
- API compatibility hoặc architecture tests.
- Không dùng coverage percentage đơn lẻ thay thế chất lượng test; test không có assertion hữu ích vẫn có thể làm coverage tăng.

Nếu coverage gate là required, command phải fail khi threshold không đạt. Report-only không chặn build thì chỉ là advisory.

### 11.2. Dependency và supply-chain checks

- Kiểm tra CVE trong direct/transitive dependencies.
- Kiểm tra license policy.
- Kiểm tra checksum/signature/dependency verification.
- SBOM cho JAR/container image.
- Pin build plugins, Wrapper và CI actions.
- Kiểm tra secrets trong source/config.
- Kiểm tra builder/base image nếu build OCI.

Không publish khi scanner không tải được vulnerability database hoặc verification metadata sai, trừ khi có exception được duyệt và audit rõ.

### 11.3. Package/image validation

- JAR có đúng Spring Boot executable layout (`BOOT-INF/classes`, `BOOT-INF/lib`) không?
- `java -jar` có khởi động được không?
- Health/readiness endpoint trả kết quả mong đợi không?
- OCI image có đúng repository/tag/platform/user/port/config không?
- Checksum/digest được tính từ artifact thực sau package?
- Smoke test có dùng chính image/JAR được chọn để publish không?

### 11.4. Release policy

- Version không phải SNAPSHOT nếu là release.
- Tag release khớp version trong POM/Gradle.
- Commit/tag thuộc protected source.
- Không tái sử dụng immutable release version.
- Changelog/release notes và approval đã đủ.
- Artifact đã ký/attested nếu policy yêu cầu.

## 12. Tránh các đường bypass vô tình

| Cấu hình/lệnh | Rủi ro | Cách xử lý |
| --- | --- | --- |
| `-DskipTests` | Unit tests không chạy | Cấm trong release workflow |
| `-Dmaven.test.skip=true` | Bỏ compile và run tests | Cấm trong release workflow |
| `-DskipITs` | Integration tests bị bỏ | Gate IT riêng hoặc cấm flag |
| `-Dmaven.test.failure.ignore=true` | Test fail nhưng build có thể tiếp tục | Không bật trong release |
| `-x test` / `-x check` | Gradle bỏ verification tasks | Không dùng ở release |
| `ignoreFailures = true` | Test failure không chặn task | Giữ fail-on-error |
| `continue-on-error: true` | Step fail nhưng job vẫn có thể xanh | Chỉ dùng cho advisory step |
| `if: always()` trên publish | Có thể chạy dù dependency fail/skip | Dùng `needs` + `success()` |
| `needs` thiếu required job | Publish không chờ gate đó | Liệt kê đầy đủ dependencies |
| Security job chỉ chạy PR nhưng publish ở tag không có gate tương ứng | Release thiếu scan | Chạy gate trên tag hoặc xác minh cùng commit |
| Publish job rebuild package | Artifact publish khác artifact đã test | Chuyển artifact và verify checksum |
| Tag `latest` mutable | Rollback không xác định đúng bytes | Lưu digest, dùng immutable reference |
| Upload artifact không fail khi thiếu file | Publish không có input hợp lệ | `if-no-files-found: error` và checksum check |
| Scanner lỗi hạ tầng được coi là pass | Không có bằng chứng scan | Fail closed hoặc exception có approval/expiry |

### 12.1. Dùng always để thu report, không dùng để publish

Có thể dùng `if: always()` cho bước upload logs/test reports để người review xem kết quả kể cả khi test fail. Đó là bước báo cáo. Publish job vẫn phải yêu cầu success của tất cả required jobs.

### 12.2. Gate bị skip do path filters

Nếu workflow không chạy khi thay đổi một số file, required status check có thể bị thiếu hoặc pending tùy cấu hình. Chỉ bỏ qua build khi có policy path-based được review và kiểm tra rằng thay đổi đó không ảnh hưởng sản phẩm. Với release tag, bảo đảm gate chạy trên chính commit được phát hành.

## 13. Multi-module và matrix builds

### 13.1. Maven/Gradle multi-module

Giả sử monorepo:

```text
platform/
├── pom.xml
├── common-library/
│   └── pom.xml
├── api-service/
│   └── pom.xml
└── admin-service/
    └── pom.xml
```

Nếu release `api-service`, phải bảo đảm upstream modules mà nó phụ thuộc được compile/test theo policy. Không giả định `mvn -pl :api-service` tự kiểm tra mọi module cần thiết; `-am` có thể build upstream projects trong reactor, nhưng test policy vẫn phải cấu hình. Với Gradle, task graph của `:api-service:build` chạy dependencies cần thiết, không tự kiểm tra mọi sibling module không liên quan.

### 13.2. Matrix Java/OS

Nếu sản phẩm hỗ trợ nhiều Java versions hoặc OS/architecture, publish phải chờ **mọi matrix leg bắt buộc** thành công. Không dùng `continue-on-error` cho matrix leg bắt buộc. Nếu một matrix entry là advisory, tách rõ khỏi release acceptance criteria.

Khi nhiều leg upload artifact, đặt tên riêng theo Java/OS để tránh ghi đè. Chỉ chọn artifact phát hành theo matrix/release policy đã định.

## 14. Bằng chứng và tính toàn vẹn artifact

Khi tách verify và publish:

1. Verify job tạo artifact.
2. Tính SHA-256 sau khi package hoàn tất.
3. Upload file và checksum như một cặp.
4. Publish job download đúng artifact cùng workflow run.
5. Chạy `sha256sum --check`.
6. Publish đúng file đã xác minh.
7. Đọc lại artifact từ repository/registry nếu có thể và so sánh digest.
8. Ghi release record: Git SHA, tag, CI run ID, artifact coordinate, SHA-256/OCI digest, test/security result và approval.

Ví dụ Bash:

```bash
sha256sum target/release-gate-demo-1.0.0.jar \
  > target/release-gate-demo-1.0.0.jar.sha256

sha256sum --check target/release-gate-demo-1.0.0.jar.sha256
```

Output khi file khớp:

```text
target/release-gate-demo-1.0.0.jar: OK
```

Checksum xác nhận file nhận được khớp checksum đã lưu; nó không tự chứng minh builder identity hoặc publisher authenticity. Nếu yêu cầu provenance mạnh, ký artifact/attestation và verify chữ ký, builder identity và subject digest ở deploy gate.

## 15. Phân biệt publish và production deployment

Sau khi publish artifact, production deployment vẫn có thể cần gate riêng:

```text
Required CI checks
       |
       v
Publish immutable artifact
       |
       v
Verify registry digest
       |
       v
Staging deployment
       |
       v
Smoke / health / integration checks
       |
       v
Production approval
       |
       v
Deploy same digest to production
```

Production environment có thể yêu cầu reviewer approval, wait timer, giới hạn branch/tag hoặc custom policy check. Quy tắc đó áp dụng cho job tham chiếu environment; nó không thay thế test/scan trước publish.

**Không build lại khi promote staging sang production.** Promote cùng artifact digest đã qua kiểm tra để tránh staging và production chạy binary khác dù cùng tag/version.

## 16. Chẩn đoán lỗi release gate

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Publish chạy dù unit test fail | `needs` thiếu job test hoặc `if` override dependency status | Liệt kê gate trong `needs`, dùng `success()` |
| Publish bị skip dù test xanh | Dependency khác bị skip/cancel hoặc branch/tag condition sai | Kiểm tra toàn bộ `needs` và `github.ref` |
| Maven verify pass nhưng không có IT report | Failsafe chưa bind hoặc test name không match | Kiểm tra plugin execution, `*IT.java`, report directory |
| Maven dừng trước cleanup IT | Chạy riêng `integration-test` hoặc test runner bị kill | Gọi `verify`, kiểm tra teardown/report |
| Gradle build pass nhưng IT không chạy | Custom task chưa gắn vào `check` | Thêm `dependsOn`, kiểm tra task graph |
| CI pass với 0 tests | Discovery pattern sai hoặc `failIfNoTests` chưa bật | Kiểm tra reports/count và cấu hình fail-if-none |
| Security job xanh dù scanner không chạy | `continue-on-error`, `|| true` hoặc step chỉ log | Bắt exit code scanner, fail khi scanner lỗi |
| Publish không tìm thấy artifact | Upload thiếu file hoặc artifact name/path lệch | `if-no-files-found: error`, đối chiếu tên/path |
| Checksum fail ở publish | File đổi, download nhầm artifact hoặc sidecar không cùng file | Dừng publish, điều tra; không tự tính lại rồi pass |
| Tag release khác version POM | Tag/version không được kiểm tra | Thêm consistency gate |
| PR checks pass nhưng tag thiếu scan | Security workflow chỉ trigger PR | Chạy gate trên tag hoặc verify cùng commit |
| GitHub environment chờ approval | Required reviewer/branch restrictions đang áp dụng | Kiểm tra environment protection |
| Build local pass nhưng CI fail | Khác toolchain, env, cache, secrets hoặc services | Dùng Wrapper, pin JDK, reproduce trên runner |
| Matrix publish dù một platform fail | Matrix leg được continue-on-error hoặc thiếu dependency | Đưa mọi leg bắt buộc vào required job |
| Release job rebuild khác artifact | Publish job gọi package/build lại | Truyền artifact đã verify và so digest |
| Publish thành công nhưng remote pull fail | Registry path, ACL, token hoặc replication issue | Dùng read identity kiểm tra remote repository |

### Quy trình điều tra khi publish bị chặn

1. Xem trạng thái từng required job: success, failure, cancelled hay skipped.
2. Kiểm tra `needs` của publish có gồm mọi required gate không.
3. Đọc exit code và report Surefire/Failsafe hoặc Gradle test tasks.
4. Xác nhận scanner thật sự chạy và dùng threshold đúng.
5. Kiểm tra branch/tag condition, environment protection và approval.
6. Kiểm tra artifact upload/download đúng tên/path.
7. So checksum trước publish; nếu sai, giữ evidence và dừng.
8. Chỉ rerun sau khi hiểu nguyên nhân; không bỏ gate hoặc sửa condition để ép release xanh.

## 17. Bài tập tự kiểm tra

**Tình huống A.** Maven unit tests pass nhưng Failsafe IT fail. Có nên publish vì package đã thành công?

*Đáp án:* Không. Failsafe verify phải xác nhận IT results; `mvn verify` trả failure nếu integration test không đạt.

**Tình huống B.** `mvn integration-test` chạy IT nhưng môi trường test không được dọn. Vì sao?

*Đáp án:* Lệnh dừng ở phase `integration-test`, không đi tới `post-integration-test` và `verify`. Hãy gọi `mvn verify`.

**Tình huống C.** Gradle build xanh nhưng không có report integrationTest. Lý do khả dĩ?

*Đáp án:* Custom task chưa nối vào lifecycle `check`; `build` chỉ phụ thuộc `check` và `assemble`.

**Tình huống D.** GitHub Actions publish có `needs: [verify]` nhưng security scan fail. Vì sao vẫn publish?

*Đáp án:* Security job không nằm trong `needs`. Thêm mọi required jobs vào dependency list.

**Tình huống E.** Publish job dùng `if: always()`. Test fail nhưng artifact vẫn push. Sửa ra sao?

*Đáp án:* Bỏ `always()` khỏi publish, dùng `needs` đầy đủ và condition `success()` kết hợp branch/tag policy.

**Tình huống F.** Security scan timeout nhưng `continue-on-error: true` làm job xanh. Gate đã đạt chưa?

*Đáp án:* Chưa. Không có bằng chứng scan hoàn tất. Bỏ continue-on-error cho required scan hoặc dùng exception được duyệt, có thời hạn và audit.

**Tình huống G.** Verify upload JAR và checksum; publish job build lại JAR rồi push. Có chắc đúng artifact đã test?

*Đáp án:* Không. Publish phải download chính file đã verify, check checksum và publish file đó.

**Tình huống H.** Tất cả jobs pass nhưng tag `v1.0.0` trong khi POM version `1.0.1`. Có thể release không?

*Đáp án:* Không nếu policy yêu cầu tag/version match. Thêm version consistency gate.

**Tình huống I.** PR checks pass nhưng tag workflow không chạy security scan. Có thể lấy kết quả PR để publish?

*Đáp án:* Chỉ khi policy xác minh cùng commit SHA, cùng artifact/input và kết quả còn hiệu lực. An toàn hơn là chạy gates trên chính tag/commit phát hành.

**Tình huống J.** Publish job cần reviewer approval nhưng chưa được duyệt. Job có được coi là pass?

*Đáp án:* Không. Environment protection chưa cho job chạy; approval là một điều kiện release độc lập.

## 18. Checklist nghiệm thu release gate

**Test và build:**

- Maven release dùng `clean verify` hoặc lifecycle tương đương.
- Surefire chạy unit tests; Failsafe chạy IT và verify report.
- Không gọi riêng `integration-test` rồi kết luận gate hoàn tất.
- Gradle custom `integrationTest` được gắn vào `check`.
- Test discovery được kiểm tra; không pass với 0 tests ngoài chủ đích.
- Skip flags/ignore-failure không được phép trong release job.

**CI dependency graph:**

- Mọi required gate có job/task rõ ràng và kết quả success/failure.
- Publish job `needs` tất cả required jobs.
- Publish condition yêu cầu `success()` và đúng branch/tag/release policy.
- Không dùng `always()`/`continue-on-error` để bypass publish gates.
- Matrix jobs bắt buộc đều phải pass.
- Branch protection/ruleset yêu cầu đúng status checks.

**Artifact integrity:**

- JAR/image được tạo từ đúng commit/tag.
- Verify job lưu artifact và SHA-256/digest sau packaging.
- Publish job download đúng artifact cùng run và xác minh checksum.
- Không rebuild binary ở publish/deploy stage khi cần promote exact artifact.
- Remote repository/registry được kiểm tra lại sau upload.
- Release record lưu commit, CI run, artifact coordinate và digest.

**Bảo mật và approval:**

- Security/dependency/license scans thực sự chạy và fail khi có finding chặn.
- Scanner outage không tự trở thành pass.
- Publisher credentials chỉ có trong protected release job.
- Untrusted PR không truy cập write secrets.
- Production environment có reviewer/branch/tag rules nếu policy yêu cầu.
- Production deploy dùng đúng digest đã publish và được duyệt.

**Kết luận:** Điều kiện xuất bản phải được biểu diễn thành một **dependency graph có fail-closed semantics**. Maven dùng `verify` để hoàn tất Surefire/Failsafe lifecycle; Gradle gắn mọi verification task vào `check`; CI dùng `needs`/`success()` để publish chỉ chạy sau required gates; branch protection và environment approval kiểm soát merge/release; checksum/digest bảo đảm đúng artifact được phát hành. Khi gate fail, bị skip, cancel hoặc thiếu bằng chứng, release phải dừng cho đến khi nguyên nhân được xử lý.

### Tài liệu chính thức

- Maven Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Maven Surefire Plugin: https://maven.apache.org/surefire/maven-surefire-plugin/
- Maven Failsafe Plugin — Integration Test Lifecycle: https://maven.apache.org/surefire/maven-failsafe-plugin/
- Gradle Java Plugin — test, check, build: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle Task Basics and Dependencies: https://docs.gradle.org/current/userguide/task_basics.html
- GitHub Actions Workflow Syntax — needs, if, environment: https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- GitHub Actions Deployments and Environments: https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments
- GitHub Actions Secure Use: https://docs.github.com/en/actions/reference/security/secure-use
- Spring Boot 3.3 Maven Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/
- Spring Boot 3.3 Gradle Plugin: https://docs.spring.io/spring-boot/3.3/gradle-plugin/