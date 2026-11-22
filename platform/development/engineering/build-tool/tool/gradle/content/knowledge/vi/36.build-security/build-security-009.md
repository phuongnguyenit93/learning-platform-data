# Thiết kế môi trường CI tách biệt cho build kiểm tra và phát hành trong Gradle

## 1. Vì sao phải tách hai môi trường?

Trong Gradle, `build.gradle.kts`, `settings.gradle.kts`, `buildSrc`, included builds, Gradle plugins và các test đều có thể **thực thi mã**. Nếu workflow cho một pull request chưa được tin cậy truy cập credentials phát hành, người đóng góp có thể sửa build logic để đọc hoặc gửi secrets đi ngay **trong configuration phase**, thậm chí trước khi task `test` chạy.

Vì vậy, thiết kế CI/CD an toàn cần hai ranh giới:

**Môi trường kiểm tra (verify / CI):** chạy mã nguồn cần kiểm tra, compile, static checks, unit/integration tests, tạo candidate artifact; token đọc tối thiểu, không có publish secrets và không có quyền ghi release.

**Môi trường phát hành (release / promotion):** chỉ mở sau gates, commit/tag được duyệt và protection rules; cấp đúng quyền publish cho job/step cuối. Đối với mô hình bảo mật mạnh, publisher **chỉ nhận artifact đã xác minh như dữ liệu** và không chạy Gradle build scripts với credentials.

~~~text
Pull request / fork PR
       |
       v
VERIFICATION JOB (untrusted context)
- checkout PR source
- no production credentials
- read-only repository token
- isolated ephemeral runner
- Gradle Wrapper validation
- compile + tests + artifact candidate
- upload reports and data only
       |
       +--> Pull request: STOP, no release
       |
Trusted tag vX.Y.Z (protected source)
       |
       v
VERIFICATION JOB (trusted tag context)
- checkout exact tagged commit
- same tests and gates
- build ZIP once
- SHA-256 + commit/version manifest
- upload artifact to this workflow run
       |
       v
RELEASE JOB (privileged, separate runner)
- waits for verification PASS and environment approval
- does NOT checkout or execute Gradle source
- downloads candidate from SAME trusted run
- validates checksum/commit/version
- uploads exact candidate bytes
       |
       v
GitHub Release / approved artifact destination
       |
       v
post-release checksum / provenance / audit
~~~

**Phân biệt:** Tách `jobs` bằng `needs` là tốt nhưng **chưa đủ** nếu vẫn dùng chung self-hosted runner, Gradle User Home, secrets, network/SSH agents hoặc remote cache có thể bị ghi bởi PR. Phải tách **quyền, runner state và nguồn artifact**.

Sau bài, bạn có thể:
- Xác định trust boundary của source, build scripts, runners, secrets và cache.
- Chọn `pull_request`, `push` vào branch/tag được bảo vệ, environment approvals và quyền token riêng.
- Hiểu vì sao `pull_request_target` và `workflow_run` nguy hiểm nếu chạy mã hoặc artifact chưa tin cậy trong privileged context.
- Dùng Gradle Wrapper đã xác minh, Java 17 toolchains, dependency verification và task graphs làm verification gate.
- Tạo dự án Java 17 multi-project Gradle Kotlin DSL với unit tests, integration test suite và ZIP distribution.
- Viết GitHub Actions workflow gồm verify job và release job, có checksums và **không chạy lại Gradle ở release job**.
- Phân biệt GitHub Release asset promotion với Maven Publish trên repository thật.
- Xây chính sách remote cache, branch/tag protection, OIDC, artifact attestations, audit và rollback.

## 2. Threat model: attacker có thể kiểm soát những gì?

| Đối tượng/cửa vào | Có thể bị thay đổi thế nào? | Hậu quả nếu quyền quá rộng |
| --- | --- | --- |
| PR source | Java code, tests, Gradle scripts, dependencies. | Chạy mã trong runner có token/secret. |
| `buildSrc` hoặc `includeBuild(...)` | Convention/plugin code được đánh giá khi build cấu hình. | Đọc environment/credential trước bất kỳ security task nào. |
| Gradle Wrapper JAR/script | Thay code khởi động Gradle. | Tấn công ngay trước khi Gradle load build. |
| Remote plugin/dependency | Thay artifact hoặc nhầm private group với public. | Build chạy mã độc/compile artifact bị thay. |
| GitHub workflow file | Sửa trigger, permissions, lệnh publish. | Bỏ qua quality gate hoặc cấp quyền ghi cho PR. |
| Tag release | Trỏ `v2.3.0` vào commit chưa review. | Publish artifact không được phê duyệt. |
| Gradle User Home | `init.d`, cached plugin/dependency, credentials. | Lây mã/secret giữa jobs. |
| Shared remote Build Cache | Upload cache entry chứa bytes bị thay. | Trusted build nhận poisoned artifact `FROM-CACHE`. |
| Uploaded CI artifact | Đổi ZIP hoặc tải artifact sai run. | Release nhầm/độc hại. |
| Self-hosted runner | Job khác dùng lại workspace, daemon, Docker socket. | Vượt ranh giới job/secret. |
| Publishing token | Lộ từ environment/log/process. | Upload/overwrite release hoặc truy cập cloud resources. |

**Quan trọng:** GitHub-hosted ephemeral runner là điểm khởi đầu tiện lợi cho untrusted PR builds, nhưng vẫn cần least privilege và quản lý external network. Self-hosted runner xử lý PR chưa tin cậy phải cách ly ở cấp máy/VM/container, không chỉ thay tên job.

## 3. Mỗi GitHub event có mức tin cậy khác nhau

### `pull_request`

Dùng cho kiểm tra code chưa được merge. Khi PR đến từ fork, GitHub thông thường không cung cấp repository secrets và giới hạn `GITHUB_TOKEN` ở quyền đọc; vẫn cần thiết lập `permissions: contents: read` tường minh.

PR workflow được phép compile và test code; **không** publish/deploy, không access production Maven password, internal DB hoặc cloud role có quyền nhạy cảm. Ngay cả lệnh `./gradlew help` cũng có thể chạy mã của `settings.gradle.kts`/`build.gradle.kts`.

### `push` lên protected `main`

Là code đã qua review nếu branch protection thực sự bắt buộc check/review và quản trị bypass. Có thể build trusted snapshots/cache, nhưng không mặc nhiên publish release cho mọi push main.

### `push` lên protected `vX.Y.Z` tag

Thường khởi tạo release verification. Phải bảo vệ **người có quyền tạo/sửa/xóa tags**, bảo đảm tag trỏ tới commit được duyệt. Pattern `tags: ["v*"]` chỉ là trigger filter, **không phải approval**.

### `workflow_dispatch`

Manual trigger chỉ phù hợp nếu kiểm tra actor/inputs/ref, có Environment approval và audit. Đừng cho input arbitrary repository/ref điều khiển privileged checkout rồi chạy scripts.

### `pull_request_target` là bẫy phổ biến

Event này chạy với trust của base repo, có thể truy cập repository secrets và token có quyền cao. **Phản ví dụ không được dùng trong production:**

~~~yaml
on: pull_request_target

jobs:
  unsafe-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: ${{ github.event.pull_request.head.sha }}
      - name: Run untrusted Gradle build with release credentials
        env:
          MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
        run: ./gradlew test
~~~

Vấn đề nằm ở việc **checkout và thực thi PR code dưới privileged context**, không chỉ ở tên trigger. Plugin/build scripts của PR có thể đọc `MAVEN_PASSWORD`. Theo tài liệu GitHub, không dùng `pull_request_target` nếu không thật sự cần; labeling/triage không chạy PR code có thể phù hợp, còn test Gradle nên dùng `pull_request`.

### `workflow_run` cần xử lý cẩn trọng

Một workflow có quyền ghi có thể được kích hoạt sau workflow khác. Thành công của upstream job **không tự chứng minh artifact đáng tin**: upstream có thể chạy trên fork PR hoặc tạo dữ liệu độc hại. Không download và execute PR scripts/binaries trong privileged `workflow_run`. Phải kiểm tra workflow ID, triggering event, repository, ref/SHA, conclusion và provenance; khi có thể, dùng **hai jobs `needs` trong cùng trusted tag workflow** như lab.

## 4. Thiết kế ranh giới quyền, runner và GitHub Environment

### 4.1. Least privilege ở job-level

~~~yaml
permissions:
  contents: read

jobs:
  verification:
    permissions:
      contents: read

  release:
    permissions:
      contents: write
~~~

Mảnh trên chỉ minh họa scopes. `contents: write` đủ cho GitHub CLI tạo GitHub Release, không tự cho quyền publish Maven Central. `id-token: write` chỉ cấp khi job thật sự dùng OIDC/attestations; đừng mở rộng `actions: write` hoặc `packages: write` chỉ vì “lỡ cần”.

### 4.2. Environment protection

Trong repository Settings, tạo environment `production-release` và khi plan/visibility hỗ trợ:
- required reviewers, tùy chọn prevent self-review;
- deployment branches/tags restrictions;
- environment-specific secrets/variables;
- restrict bypass/record approvals;
- branch/tag rulesets, CODEOWNERS và required status checks.

YAML:

~~~yaml
jobs:
  release:
    environment: production-release
~~~

**Chỉ gắn tên Environment chưa tự tạo approval.** Nếu Environment chưa được cấu hình protection rules, release job có thể chạy mà không dừng chờ. GitHub có giới hạn availability khác nhau giữa public/private repositories và plans; phải kiểm tra quyền thực tế.

### 4.3. Chọn runner

- **GitHub-hosted ephemeral runner:** lựa chọn phù hợp để bắt đầu.
- **Self-hosted shared runner:** không nên chạy untrusted PR cùng trust boundary với release; Docker socket, credentials và caches có thể tồn tại sau job.
- **Self-hosted ephemeral/reimaged:** có thể dùng khi cần build hardware hoặc internal network, nhưng phải chứng minh isolation/reimage, token expiry và network segmentation.
- **Release runner:** không cần JDK/Gradle trong mô hình upload prebuilt ZIP; giảm attack surface.
- **Gradle User Home:** chứa init scripts `init.d`, credential files, caches và daemons; không tái sử dụng giữa PR và release.

## 5. Chuẩn bị Gradle an toàn trước khi chạy tasks

Gradle documentation cảnh báo: build logic không sandbox, những thứ được chạy **trước** tasks như Wrapper, Settings và init scripts là điểm tấn công.

### 5.1. Wrapper

Theo dõi các file:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
~~~

- Pin đúng Gradle distribution HTTPS và exact version.
- Xác minh `gradle-wrapper.jar` với official Gradle checksums; dùng `gradle/actions/setup-gradle@v6` tích hợp Wrapper validation.
- Khai báo `distributionSha256Sum` sau khi lấy actual official checksum để kiểm tra distribution download.
- Không chạy một untrusted wrapper chỉ để “tạo lại wrapper an toàn”; xác minh trước.
- Review changes của Wrapper và `buildSrc` tương tự workflow file changes.

### 5.2. Dependencies, repositories và build logic

- Pin versions, tránh dynamic versions `1.+` trong releases.
- Content filtering/exclusive repositories cho private groups, tránh dependency confusion.
- Chỉ dùng HTTPS repositories và policy credentials thích hợp.
- Dùng dependency verification với `gradle/verification-metadata.xml` và signatures/hashes đã review.
- Cân nhắc dependency locking với nhiều environment/CI.
- Kiểm tra plugin dependencies, annotation processors và included builds.
- Không tải/execute remote scripts bằng `apply(from = "...")` không pin nội dung/version.

Bootstrap verification metadata:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

Lệnh này được dùng **khi thiết lập hoặc đổi dependencies**, sau đó review nguồn hashes trước khi commit. Không chạy lại lệnh bootstrap mặc định ở mọi CI vì nó có thể hợp thức hóa artifact đã bị thay. Kiểm tra checksum không thay thế vulnerability scanning/CVE analysis.

### 5.3. Build Cache và Configuration Cache

- `UP-TO-DATE` khác `FROM-CACHE` và khác `Reusing configuration cache.`.
- PR builds không được **push** remote Build Cache entries mà trusted release job sử dụng.
- Release job của bài không chạy Gradle nên không cần Gradle caches.
- Không chia sẻ `.gradle/configuration-cache`/Gradle User Home giữa runners khác trust.
- Configuration Cache có thể serialize sensitive configuration state; tránh đọc secrets lúc configuration.
- Tắt Build Cache không làm build script an toàn hơn nếu script vốn có thể chạy mã ở configuration phase.

## 6. Lab Java 17: source, Gradle Kotlin DSL, unit và integration tests

Lab tạo `:core` (Java library) và `:app` (Application). Candidate là ZIP distribution từ `:app:distZip`; đúng artifact này được upload lên GitHub Release **sau** quality gates.

### 6.1. Layout

~~~text
secure-gradle-ci/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── core/
│   ├── build.gradle.kts
│   ├── src/main/java/example/core/Message.java
│   └── src/test/java/example/core/MessageTest.java
├── app/
│   ├── build.gradle.kts
│   ├── src/main/java/example/app/Main.java
│   ├── src/test/java/example/app/MainTest.java
│   └── src/integrationTest/java/example/app/AppIntegrationTest.java
└── .github/workflows/secure-release.yml
~~~

Giả định Wrapper đã được tạo/xác minh, JDK 17 có thể resolve, Gradle version hỗ trợ JVM Test Suite plugin (API này còn có các phần `@Incubating`) và Maven Central tải được JUnit 5.11.4. Các lệnh `./gradlew` dành cho Unix/macOS; Windows dùng `.\gradlew.bat`.

### 6.2. `settings.gradle.kts`

~~~kotlin
rootProject.name = "secure-gradle-ci"
include("core", "app")
~~~

Hai modules thuộc **một multi-project build**, không dùng `includeBuild("core")` thay `include("core")`.

### 6.3. Root `build.gradle.kts`

~~~kotlin
plugins {
    base
}

tasks.register("verifyAll") {
    group = "verification"
    description = "Checks core and app before packaging"
    dependsOn(":core:check", ":app:check")
}
~~~

`verifyAll` là aggregator tự tạo; `:build` ở root khác task selector `build` từ root. Khi app phụ thuộc core code, `:app:build` có thể compile core nhưng **không mặc nhiên chạy `:core:test`**.

### 6.4. `core/build.gradle.kts`

~~~kotlin
plugins {
    `java-library`
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

`java-library` tạo Java compile/JAR/test lifecycles; JUnit platform được cấu hình rõ. Library ở lab **không** có remote publish credentials; chỉ tạo ZIP cho app.

### 6.5. `core/src/main/java/example/core/Message.java`

~~~java
package example.core;

public final class Message {
    private Message() {
    }

    public static String value() {
        return "trusted-core";
    }
}
~~~

### 6.6. `core/src/test/java/example/core/MessageTest.java`

~~~java
package example.core;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MessageTest {
    @Test
    void valueIsStable() {
        assertEquals("trusted-core", Message.value());
    }
}
~~~

### 6.7. `app/build.gradle.kts`

~~~kotlin
plugins {
    application
}

group = "dev.example"
version = providers.gradleProperty("releaseVersion")
    .orElse("1.0.0-SNAPSHOT")
    .get()

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("example.app.Main")
}

dependencies {
    implementation(project(":core"))
}

testing {
    suites {
        val test = named<JvmTestSuite>("test") {
            useJUnitJupiter("5.11.4")
        }

        register<JvmTestSuite>("integrationTest") {
            useJUnitJupiter("5.11.4")
            dependencies {
                implementation(project())
            }
            targets {
                all {
                    testTask.configure {
                        shouldRunAfter(test)
                    }
                }
            }
        }
    }
}

tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}
~~~

- Application plugin tạo `:app:run` và `:app:distZip`.
- `implementation(project(":core"))` đưa library vào runtime classpath; không chỉ là task ordering.
- JVM Test Suite plugin cấu hình JUnit Jupiter dependencies cho default `test` và additional `integrationTest`.
- Additional suite **không** tự phụ thuộc main application outputs, vì vậy khai báo `implementation(project())`.
- `shouldRunAfter(test)` chỉ là ordering; `check.dependsOn(integrationTest)` mới bảo đảm suite được chọn trong quality gate.
- `releaseVersion` mặc định snapshot; workflow tag sẽ đưa version số thống nhất, không dùng timestamp/random khi tạo archive.

### 6.8. `app/src/main/java/example/app/Main.java`

~~~java
package example.app;

import example.core.Message;

public final class Main {
    private Main() {
    }

    public static String result(String target) {
        return "SECURE_CI=" + Message.value() + ":" + target;
    }

    public static void main(String[] args) {
        String target = args.length == 0 ? "local" : args[0];
        System.out.println(result(target));
        System.out.println("ARG_COUNT=" + args.length);
    }
}
~~~

### 6.9. `app/src/test/java/example/app/MainTest.java`

~~~java
package example.app;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {
    @Test
    void verifiesResult() {
        assertEquals(
            "SECURE_CI=trusted-core:CI",
            Main.result("CI")
        );
    }
}
~~~

### 6.10. `app/src/integrationTest/java/example/app/AppIntegrationTest.java`

~~~java
package example.app;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class AppIntegrationTest {
    @Test
    void appAndLibraryWorkTogether() {
        assertEquals(
            "SECURE_CI=trusted-core:release",
            Main.result("release")
        );
    }
}
~~~

Đây là **module integration smoke test**, không phải thử nghiệm network/database production thật. Mục tiêu là chứng minh suite chạy riêng và kiểm tra app sử dụng core. Trong hệ thống thực có thể thêm Testcontainers/HTTP/DB test infrastructure nhưng không đưa production credentials vào PR runner.

### 6.11. Chạy kiểm tra Gradle

~~~bash
./gradlew --version
./gradlew projects

./gradlew :core:compileJava :app:compileJava
./gradlew :core:test :app:test
./gradlew :app:integrationTest
./gradlew :core:check :app:check
./gradlew :verifyAll

./gradlew :app:distZip
./gradlew :app:installDist
./gradlew :app:run --args="CI"
./app/build/install/app/bin/app CI
~~~

PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat :core:check :app:check
.\gradlew.bat :app:integrationTest
.\gradlew.bat :app:distZip
.\gradlew.bat :app:run --args="CI"
.\gradlew.bat :app:installDist
.\app\build\install\app\bin\app.bat CI
~~~

**Java stdout chính xác khi truyền `CI`:**

~~~text
SECURE_CI=trusted-core:CI
ARG_COUNT=1
~~~

Các dòng `> Task`, daemon/warnings của Gradle không thuộc stdout của Java main.

### 6.12. Biên dịch/chạy Java 17 độc lập với Gradle

Linux/macOS:

~~~bash
mkdir -p build/manual/core build/manual/app

javac -encoding UTF-8 -d build/manual/core \
    core/src/main/java/example/core/Message.java

javac -encoding UTF-8 -cp build/manual/core \
    -d build/manual/app \
    app/src/main/java/example/app/Main.java

java -cp build/manual/core:build/manual/app example.app.Main CI
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual/core | Out-Null
New-Item -ItemType Directory -Force build/manual/app | Out-Null
javac -encoding UTF-8 -d build/manual/core core/src/main/java/example/core/Message.java
javac -encoding UTF-8 -cp build/manual/core -d build/manual/app app/src/main/java/example/app/Main.java
java -cp "build/manual/core;build/manual/app" example.app.Main CI
~~~

Kết quả Java stdout vẫn:

~~~text
SECURE_CI=trusted-core:CI
ARG_COUNT=1
~~~

Lệnh `javac` không xác nhận Gradle plugin/testing/CI jobs; nó chỉ tách lỗi Java source khỏi lỗi build environment. Java classpath separator Unix là `:`, Windows là `;`.

### 6.13. Candidate distribution

Với `-PreleaseVersion=2.3.0`, `:app:distZip` tạo file theo convention:

~~~text
app/build/distributions/app-2.3.0.zip
~~~

ZIP Application plugin chứa app JAR, runtime library JARs và launcher scripts; **không tự bundle Java 17 JRE**. Plain `:app:jar` không mặc nhiên là fat JAR chạy độc lập bằng `java -jar`.

## 7. Workflow hoàn chỉnh: PR chỉ kiểm tra, tag phát hành đúng artifact đã kiểm thử

Thiết kế một workflow có hai jobs:
- `verify-and-package` chạy trên PR, protected main và tag; chỉ có quyền đọc, chạy Gradle tasks, upload candidate.
- `release` chỉ chạy khi push tag `vMAJOR.MINOR.PATCH`, phụ thuộc verification pass, được bảo vệ bởi GitHub Environment và có `contents: write`; **không checkout hoặc execute Gradle**.

### 7.1. `.github/workflows/secure-release.yml`

~~~yaml
name: Safe Gradle CI and Release

on:
  pull_request:
  push:
    branches: [main]
    tags: ["v*"]

permissions:
  contents: read

jobs:
  verify-and-package:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - name: Checkout triggering commit
        uses: actions/checkout@v4

      - name: Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Validate Gradle Wrapper and set up Gradle
        uses: gradle/actions/setup-gradle@v6

      - name: Select one version for all Gradle tasks
        shell: bash
        run: |
          set -euo pipefail
          if [[ "$GITHUB_REF_TYPE" == "tag" ]]; then
            version="${GITHUB_REF_NAME#v}"
            if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
              echo "Expected tag vMAJOR.MINOR.PATCH" >&2
              exit 1
            fi
          else
            version="1.0.0-SNAPSHOT"
          fi
          echo "ORG_GRADLE_PROJECT_releaseVersion=$version" >> "$GITHUB_ENV"

      - name: Compile
        run: ./gradlew :core:compileJava :app:compileJava --stacktrace --console=plain

      - name: Unit tests
        run: ./gradlew :core:test :app:test --stacktrace --console=plain

      - name: Integration tests
        run: ./gradlew :app:integrationTest --stacktrace --console=plain

      - name: Full verification gate
        run: ./gradlew :core:check :app:check --stacktrace --console=plain

      - name: Package application distribution
        run: ./gradlew :app:distZip --stacktrace --console=plain

      - name: Record immutable candidate checksum and identity
        shell: bash
        run: |
          set -euo pipefail
          cd app/build/distributions
          shopt -s nullglob
          zips=(app-*.zip)
          if [[ "${#zips[@]}" -ne 1 ]]; then
            echo "Expected exactly one app ZIP" >&2
            exit 1
          fi
          printf 'COMMIT=%s\nVERSION=%s\n' \
            "$GITHUB_SHA" "$ORG_GRADLE_PROJECT_releaseVersion" > BUILD-INFO.txt
          sha256sum "${zips[0]}" > SHA256SUMS
          sha256sum --check SHA256SUMS

      - name: Archive verified candidate data
        uses: actions/upload-artifact@v4
        with:
          name: candidate-${{ github.run_id }}
          path: app/build/distributions/
          if-no-files-found: error
          retention-days: 14

      - name: Save test evidence on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: failed-test-reports-${{ github.run_id }}
          path: |
            core/build/reports/tests/**
            core/build/test-results/**
            app/build/reports/tests/**
            app/build/test-results/**
          if-no-files-found: ignore
          retention-days: 7

  release:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
    needs: verify-and-package
    runs-on: ubuntu-latest
    environment: production-release
    permissions:
      contents: write

    steps:
      - name: Download candidate from this exact workflow run
        uses: actions/download-artifact@v4
        with:
          name: candidate-${{ github.run_id }}
          path: release-assets

      - name: Validate checksum and source identity
        shell: bash
        run: |
          set -euo pipefail
          cd release-assets
          sha256sum --check SHA256SUMS
          grep -Fx "COMMIT=$GITHUB_SHA" BUILD-INFO.txt

          version="${GITHUB_REF_NAME#v}"
          if ! [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
            echo "Invalid tag version" >&2
            exit 1
          fi
          grep -Fx "VERSION=$version" BUILD-INFO.txt

          shopt -s nullglob
          zips=(app-*.zip)
          if [[ "${#zips[@]}" -ne 1 ||
                "${zips[0]}" != "app-$version.zip" ]]; then
            echo "Candidate ZIP does not match release version" >&2
            exit 1
          fi

      - name: Create GitHub Release with exact checked ZIP
        shell: bash
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          set -euo pipefail
          shopt -s nullglob
          assets=(release-assets/app-*.zip)
          if [[ "${#assets[@]}" -ne 1 ]]; then
            echo "Missing unique validated asset" >&2
            exit 1
          fi
          gh release create "$GITHUB_REF_NAME" "${assets[0]}" \
            --verify-tag --generate-notes
~~~

**Lưu ý về tính runnable:**
- Dùng GitHub-hosted `ubuntu-latest` có `bash`, `sha256sum` và GitHub CLI `gh`. Trên self-hosted runner phải cài/verify tương đương.
- Gradle Wrapper cần tồn tại và `gradlew` có executable mode đã commit.
- Source tree phải đúng lab, dependencies có thể resolve từ Maven Central.
- Tag push phải trỏ commit của build và đáp ứng regex `vX.Y.Z`. Release assets từ same-run GitHub Actions artifact storage.
- `environment: production-release` **chỉ có approval thật nếu admin đã cấu hình required reviewers/protection rules**.
- Quyền `contents: write` trong release job được yêu cầu để GitHub CLI tạo release; repo/org policy phải cho phép.
- `gh release create` **không idempotent** nếu release đã có; cần runbook kiểm tra state khi rerun.

### 7.2. Ý nghĩa từng cơ chế bảo vệ

1. `on: pull_request`: PR có thể chạy tests mà không nhận release secrets.
2. `permissions: contents: read`: giảm quyền mặc định của `GITHUB_TOKEN`.
3. `setup-gradle@v6`: wrapper validation và cache management theo Gradle docs.
4. Tests chạy tách bước để dễ phân biệt compile/unit/integration failures.
5. `:core:check :app:check` là quality gate, integration suite đã nối vào `:app:check`.
6. Candidate ZIP chỉ được tạo khi verification pass (trong cùng job).
7. SHA-256 và `BUILD-INFO.txt` gắn artifact với run commit/version.
8. `actions/upload-artifact@v4` lưu data, không “phát hành”; job release tải đúng tên artifact cùng `github.run_id`.
9. `needs: verify-and-package` ngăn release khi verify fail.
10. `if: ... refs/tags/v` giới hạn trigger nhưng **phải** kèm protected tag rules.
11. `production-release` có thể chặn job đến khi approver đồng ý; approve rules là server-side config.
12. Release job **không có `checkout`, không có JDK, không chạy `./gradlew`**, nên build scripts không đọc được write token trong privileged job.
13. `sha256sum --check` fail nếu candidate ZIP bytes khác manifest.
14. `grep -Fx COMMIT/VERSION` đối chiếu identity trước khi tạo release.
15. `gh release create --verify-tag` không tự tạo Git tag mới; chỉ publish trên tag tồn tại.
16. Job có quyền ghi chỉ upload ZIP, không giải nén rồi execute file từ candidate.

### 7.3. CI artifact digest không đồng nghĩa build provenance

GitHub `upload-artifact`/`download-artifact` v4 có SHA-256 digest check tự động. Theo GitHub docs, mismatch có thể chỉ tạo **warning**, không luôn làm workflow fail. Vì vậy custom `sha256sum --check` trong release job là một gate có exit code.

Nhưng manifest và ZIP đều do **cùng verification producer** tạo. Nếu producer bị kiểm soát bởi attacker, nó có thể làm giả cả hai. Đừng coi kiểm tra checksum là đủ để biến PR artifact thành trusted artifact. Trust còn đến từ **protected tags, trusted source, workflow review, approvals, signing/attestations**.

### 7.4. Vì sao không dùng chung artifact của PR để phát hành?

Một PR job có thể tải lên ZIP do chính code của PR tạo. Workflow trên chỉ release **khi verify job chạy lại ở trusted tag event**, không tải một “candidate mới nhất” từ PR. Job release dùng artifact **same run** (tên theo run id), không chọn run khác chỉ vì tên trùng.

Nếu dùng `workflow_run` để kéo artifact từ run khác, phải kiểm tra run origin/ref/SHA/conclusion và không execute untrusted payload trong privileged context. Với use case đơn giản, same-run `needs` rành mạch hơn.

## 8. Cấu hình GitHub ngoài workflow: không thể bỏ qua

Một YAML đúng syntax chưa đủ bảo mật. Cần xác nhận:

1. **Branch ruleset** cho `main`: required checks, minimum reviews, CODEOWNERS cho workflow/build files, hạn chế force push và bypass.
2. **Tag ruleset** cho `v*`: chỉ release bot/người được duyệt có quyền tạo/sửa/xóa; tag không trỏ commit chưa review.
3. **Environment** `production-release` có required reviewers/approval khi repo plan cho phép; có thể chọn prevent self-review, deployment branch/tag policy và restrict bypass.
4. **Secret policy**: workflow chính không cần release password; `GITHUB_TOKEN` release job chỉ có contents write. Nếu chuyển sang Maven/cloud, chỉ cấp secret/OIDC ở release scope.
5. **Workflow settings** cho allowed actions và GITHUB_TOKEN permissions theo org/repo.
6. **Artifact retention** đủ lâu để approver phê duyệt; quá hạn download sẽ fail, không “fix” bằng cách build lại Gradle trong privileged job.
7. **Trusted actions**: production có thể pin `uses: owner/action@commitSHA` theo SHA đã review, thay vì tags dễ bị cập nhật.
8. **Audit**: actor/tag/commit/workflow run/approver và release asset SHA được lưu.

Tính năng GitHub Environments và required reviewers có giới hạn theo plan/visibility. Nếu private repo không có required reviewers ở plan hiện tại, dùng release approval bên ngoài và tách role/identity phù hợp; **không khẳng định job đã được duyệt chỉ vì có environment name**.

## 9. So sánh các trạng thái job

| Event | Verification | Release | Quyền publish |
| --- | --- | --- | --- |
| PR từ fork | Chạy compile/test/ZIP trên runner read-only. | Skip. | Không. |
| PR nội bộ | Chạy tương tự. | Skip. | Không. |
| Push `main` đã review | Chạy; tạo candidate snapshot. | Skip. | Không. |
| Protected tag `v2.3.0` | Chạy, build `app-2.3.0.zip`, ghi checksum. | Sau PASS/approval tải ZIP và upload. | Chỉ release job. |
| Tag `v2.3.0-rc1` theo YAML mẫu | Version regex fail. | Skip do needs fail. | Không. |
| Tag chưa được GitHub cho phép tạo | Trigger không xảy ra. | Không. | Không. |
| Candidate SHA sai | Verification hoặc release checksum fail. | Không publish. | Không sử dụng. |

**Đừng nhầm** `BUILD SUCCESSFUL` với bảo đảm mọi test đã chạy: `NO-SOURCE`, `SKIPPED`, `UP-TO-DATE` và `FROM-CACHE` có nghĩa khác nhau. CI chỉ biết những Gradle tasks thực sự được chọn; unit/integration suites chưa được wire sẽ không thành gate dù build xanh.

## 10. Tính toàn vẹn và nguồn gốc của artifact

### 10.1. Các lớp bằng chứng

| Cơ chế | Kiểm tra được | Không kiểm tra được |
| --- | --- | --- |
| SHA-256 và manifest | ZIP bytes khớp với manifest. | Ai đã tạo manifest. |
| GitHub Actions artifact digest | Bytes upload/download giống nhau. | Upstream commit có trusted không. |
| Git tag protection | Ai được phép chọn commit/version. | Dependencies có CVE hay không. |
| Environment approval | Release gate được reviewer phê duyệt. | Artifact bytes an toàn nếu reviewer sai. |
| Signed attestation | Artifact digest và build workflow identity được gắn bằng xác nhận cryptographic. | Chương trình không chứa lỗi logic/malware. |
| SBOM | Liệt kê thành phần phần mềm đã khai báo/phân tích. | Không tự sửa vulnerabilities. |
| Reproducible build | Cùng inputs sinh cùng bytes. | Không tự xác minh publisher identity. |

### 10.2. GitHub attestations

Khi repository/plan hỗ trợ, GitHub `actions/attest@v4` có thể tạo provenance attestation cho ZIP. Mảnh job permissions/step ví dụ:

~~~yaml
permissions:
  contents: read
  id-token: write
  attestations: write

steps:
  - uses: actions/attest@v4
    with:
      subject-path: app/build/distributions/app-*.zip
~~~

Đây là **mảnh minh họa** cần đặt trong **trusted artifact-producing job**, không copy nguyên `steps` vào YAML sẵn có. `id-token: write`/`attestations: write` là quyền tương ứng; vì permissions áp **per job**, bạn nên thiết kế trusted tag job riêng nếu không muốn trao các quyền này cho PR verification jobs. Dùng GitHub docs để kiểm tra support cho public/private repos và khả năng verify với `gh attestation verify`.

### 10.3. Reproducibility

Hai runners có thể tạo JAR/ZIP khác SHA nếu cùng source nhưng khác timestamps, toolchains, generated file order, locale hoặc plugin logic. Gradle 9.x có archive reproducibility defaults tốt, nhưng không tự sửa custom generators. Có thể cấu hình:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Mảnh Gradle Kotlin DSL optional, đặt trong project phù hợp và test theo Gradle version thực tế. Nếu thật sự cần bit-for-bit reproducibility, build ở hai workspaces sạch rồi so digest. **Hardened lab tránh rủi ro rebuild** bằng cách không tạo lại ZIP trong release job.

### 10.4. Hậu kiểm GitHub Release

Sau một release thực sự:

~~~bash
gh release view v2.3.0
gh release download v2.3.0 \
  --pattern "app-2.3.0.zip" \
  --dir downloaded-release

sha256sum downloaded-release/app-2.3.0.zip
~~~

So digest với `SHA256SUMS` của trusted candidate artifact. Đây là lệnh dành cho repo đã có release v2.3.0, không phải stdout mô phỏng chắc chắn xuất hiện.

## 11. Maven repository: hai lựa chọn, khác nhau về an toàn

Dự án phát hành Java library lên Maven repository thường dùng Gradle `maven-publish`. Nhưng chạy `./gradlew publish` ở privileged job có một rủi ro: **nó thực thi Gradle build logic trong quá trình đang có credentials**.

### 11.1. Mẫu Maven publication để staging an toàn

Nếu muốn phát hành `:core`, bổ sung `maven-publish` vào `core/build.gradle.kts` và cấu hình publication:

~~~kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "dev.example"
version = providers.gradleProperty("releaseVersion")
    .orElse("1.0.0-SNAPSHOT").get()

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            artifactId = "safe-core"
            from(components["java"])
        }
    }
    repositories {
        maven {
            name = "localStaging"
            url = uri(layout.buildDirectory.dir("local-staging"))
        }
    }
}
~~~

Đây là **phiên bản cấu hình thay thế/bổ sung**, cần giữ repositories/toolchain/test dependencies của core từ lab và không lặp `plugins` hai lần trong cùng file. Nó tạo file-based staging Maven repository:

~~~bash
./gradlew :core:publishMavenJavaPublicationToLocalStagingRepository
~~~

Công việc này không cần release credentials và có thể nằm trong trusted verification job. Staging artifacts gồm Java component JAR/POM/Gradle Module Metadata và checksums/metadata tùy publication.

### 11.2. Mô hình đơn giản: trusted release rebuild + publish

Cấu hình remote repo có `maven-publish`, release job checkout approved tag, chạy `:core:publishMavenJavaPublicationToReleaseRepository` với typed credentials. Ưu điểm là dễ dùng Gradle; nhược điểm là Gradle scripts/plugins đang chạy cùng secrets và artifacts có thể được rebuild khác bytes đã test. Chỉ dùng nếu tag/workflow đã review, runner hoàn toàn tin cậy, dependencies được xác minh, version immutability và secret policy rõ.

Mảnh remote repository Kotlin DSL:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials

val releaseRepoUrl = providers.gradleProperty("releaseRepoUrl")

if (releaseRepoUrl.isPresent) {
    publishing {
        repositories {
            maven {
                name = "release"
                url = uri(releaseRepoUrl.get())
                credentials(PasswordCredentials::class)
            }
        }
    }
}
~~~

Khai báo `import` ở đầu file; snippet này không được copy nguyên vào `core/build.gradle.kts` nếu đã có `plugins` block khác mà không hợp nhất.

Gradle tự lấy username/password theo repository name `release`:

~~~text
releaseUsername
releasePassword
ORG_GRADLE_PROJECT_releaseUsername
ORG_GRADLE_PROJECT_releasePassword
ORG_GRADLE_PROJECT_releaseRepoUrl
~~~

Đừng đặt passwords trong tracked `gradle.properties` hoặc in ra console. Khi dùng CI secret env injection, Gradle publication task:

~~~bash
./gradlew :core:publishMavenJavaPublicationToReleaseRepository \
  -PreleaseVersion=2.3.0
~~~

chỉ chạy ở trusted environment với URL/server/secret thực tế. Lab GitHub Release chính **không** chạy task remote này.

### 11.3. Mô hình chặt hơn: staging → promote exact tested Maven bytes

Nếu yêu cầu “phát hành đúng JAR/POM đã kiểm thử”:
1. Trusted no-secret builder tạo Maven publication vào immutable staging namespace.
2. Kiểm tra GAV, POM, Gradle Module Metadata, checksums/signatures và external consumer resolution.
3. Lưu provenance theo commit/tag/build run.
4. Privileged publisher chỉ gọi **repo-manager-specific promotion API** để promote đúng bytes.
5. Không chạy Gradle build scripts/`maven-publish` cùng secret trong privileged job.
6. Consumer tải từ release repository và verify checksum/signature.

Nexus, Artifactory, GitHub Packages và Maven Central Portal có APIs/policies khác nhau; **không có một cú pháp Maven promotion chung**. Với Maven Central, không tự dùng legacy OSSRH endpoint: Central Portal hiện hành có workflow riêng. Phần GitHub Release lab dùng GH CLI vì nó hỗ trợ promotion ZIP rõ ràng.

## 12. Secret handling, OIDC và bảo vệ supply chain

### 12.1. Không lộ secrets

- Secrets phải được inject đúng release job/step, sau Environment approval nếu có.
- Không ghi token trong code/script/Gradle User Home được shared.
- Không in raw token vào Gradle logging, `--debug`, test reports, Gradle Build Scan hoặc artifacts.
- Dùng credentials typed APIs, masked CI variables hoặc token ngắn hạn.
- Nếu cần cloud auth, ưu tiên OIDC federation/short-lived credentials khi provider hỗ trợ, thay vì long-lived keys.
- `GITHUB_TOKEN` có scope do workflow/job permissions xác định, không là secret có quyền vô hạn.
- Không expose secret trong shell args mà process list/logs có thể ghi lại.

### 12.2. OIDC không tự biến code không tin cậy thành trusted

`id-token: write` cho phép xin identity token theo policy; nếu cấp cho untrusted PR job và cloud role tin mọi subject, attacker vẫn có thể lấy cloud credentials. Cloud trust policy phải giới hạn **repository, branch/tag, environment, workflow identity, audience**. Chỉ bật OIDC trong job có thật sự cần external credentials.

### 12.3. Actions/version pinning

Các ví dụ dùng `actions/checkout@v4`, `actions/setup-java@v4`, `gradle/actions/setup-gradle@v6`, `actions/upload-artifact@v4` và `actions/download-artifact@v4` vì dễ đọc. Trong môi trường production, kiểm tra major versions hiện hành, pin **full commit SHA** của actions được review và cập nhật qua quy trình PR. Action tag có thể đổi; pin SHA giúp giảm supply-chain drift.

### 12.4. Immutable release, retry và rollback

`gh release create` có thể tạo draft, upload assets rồi publish qua nhiều API calls. Nếu gặp timeout/hết quota giữa chừng, không retry mù mà kiểm tra:
- Release đã tồn tại chưa?
- Có draft/asset upload dở không?
- Asset digest có khớp canonical bytes không?
- Tag còn đúng protected SHA không?
- Repository có release immutability policy không?

Nếu artifact sai, chặn promotion; release version mới có thể cần phát hành theo incident process thay vì overwrite bản cũ. Nếu đã deploy, rollback dịch vụ sang release đã xác nhận tốt; **publish khác deployment**.

## 13. Cache poisoning, isolated builds và Gradle User Home

### 13.1. Build Cache không phải artifact signing

`FROM-CACHE` nói task outputs được restore theo cache key, không chứng minh producer đáng tin. Attacker có quyền remote cache write có thể đặt output độc hại trong namespace mà trusted build reuse.

Kiểm soát:
- PR: no shared remote write, namespace tách hoặc read-only trusted cache.
- Trusted main/tag CI: push theo ACL và kiểm thử cache correctness.
- Remote cache HTTPS/auth/retention đúng.
- Khi nghi sai: chạy control `--no-build-cache --rerun-tasks`, so SHA/declared inputs.
- Không tự coi `--no-build-cache` là defense chống mã Gradle độc hại.

### 13.2. Configuration Cache và secrets

Configuration Cache lưu task graph/configuration state trên disk, có thể chứa sensitive config values nếu plugin đọc credentials lúc configuration. Không copy `.gradle/configuration-cache` từ release vào PR hoặc qua shared artifact cache. Dùng Providers/secrets ở execution time và tránh `get()` quá sớm khi có thể.

### 13.3. Gradle Daemon và init scripts

`GRADLE_USER_HOME` chứa init scripts/daemon/cache có thể tác động mọi build của user đó. Không dùng chung trên self-hosted runner giữa PR và release; khi buộc dùng shared hardware phải isolate users/VMs/containers và wipe/reimage. `./gradlew --stop` dừng daemon, **không** thay isolation boundary hoặc xóa caches có thể bị nhiễm.

## 14. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| PR job có Maven password | Secret được đặt workflow-level hoặc dùng privileged event. | Chuyển secrets chỉ vào release job/env; dùng `pull_request` không privileged. |
| `pull_request_target` checkout PR head rồi chạy Gradle | PR code thừa hưởng base repository secrets. | Không execute PR code trong context này. |
| Environment không đợi approval | Required reviewers chưa cấu hình hoặc plan không hỗ trợ. | Kiểm tra repo Settings/protection rules. |
| Tag v2.3.0 kích release chưa review | Tag trigger không phải tag authorization. | Protected tag/branch rules và approvals. |
| `GITHUB_TOKEN` báo 403 khi tạo GitHub Release | Release job không có `contents: write` hoặc repo policy chặn. | Kiểm tra scopes/policy; không mở quyền PR. |
| ZIP không tồn tại | `:app:distZip` fail, path version sai. | Xem task outcomes và `app/build/distributions`. |
| Release tải nhầm ZIP | Download artifact khác run hoặc không validate version. | Same-run named candidate + COMMIT/VERSION/digest check. |
| SHA mismatch | File candidate thay/transfer lỗi hoặc manifest sai. | Hard fail, không publish; truy vết producer. |
| SHA pass nhưng code độc hại | Producer và manifest cùng bị kiểm soát. | Source trust, signatures/attestations, review. |
| Tag `v2.3.0-rc1` fail | Regex sample chỉ cho X.Y.Z. | Thay policy hoặc dùng stable tag. |
| Release step nói tag không tồn tại | `--verify-tag` ngăn tạo tag tự động. | Tạo protected tag trước. |
| `gh release create` báo release đã tồn tại | Rerun/partial previous publish. | Kiểm tra assets/checksums trước retry. |
| App JAR không tự chạy | Plain `jar` không bundle runtime deps/scripts. | `distZip`/`installDist` và Java17 runtime. |
| `integrationTest` không tìm thấy | Chưa register JVM Test Suite hoặc Gradle version không phù hợp. | Kiểm tra `testing.suites` và Gradle docs. |
| App integration test thiếu production classes | Additional suite thiếu `implementation(project())`. | Khai báo dependency đúng suite. |
| `:app:build` pass nhưng core tests không chạy | Project dependency không tương đương core verification. | Chọn `:core:check` và `:app:check`. |
| Fork PR chạy trên persistent self-hosted runner | Runner có shared sockets/credentials/cache. | Ephemeral isolated runner và no prod network. |
| Build Cache entry bị poisoned | Untrusted push vào shared cache. | Trusted writers, namespace isolation, cache audit. |
| Repo publish Maven fail khi staging file pass | Remote URL/credentials/protocol/policy khác. | Test release repo qua safe staging, đúng task+auth. |
| Test reports upload fail khi compile fail | Chưa tạo report nhưng upload yêu cầu file. | Dùng `if: failure()` và `if-no-files-found: ignore`. |
| Download artifact báo digest warning nhưng job vẫn pass | Action digest validation có thể cảnh báo. | Bắt buộc explicit SHA256SUMS check. |
| Build script lộ secret qua `--debug` | Log không được redact. | Revocation/rotation, sửa secret handling, review logs. |

## 15. Checklist kiểm tra trước khi bật release thật

- [ ] PR jobs chạy read-only; không truy cập secrets/production network.
- [ ] Runners ephemeral, không dùng chung Docker socket/Gradle User Home với release.
- [ ] Workflow không dùng `pull_request_target` để execute PR build scripts.
- [ ] Không có privileged `workflow_run` tin artifact PR như executable code.
- [ ] Protected branch/tag rules và CODEOWNERS bảo vệ source/workflow changes.
- [ ] GitHub Environment required reviewers/conditions được bật thực sự.
- [ ] Token default `contents: read`, release `contents: write` duy nhất.
- [ ] Gradle Wrapper/JAR/distribution được pin và validate.
- [ ] Java 17 toolchain và Gradle version đủ chạy toàn bộ tests.
- [ ] Dependency verification và repository source trust policy đã review.
- [ ] Unit/integration tests nằm trong actual task graph, không bị skip im lặng.
- [ ] `:app:distZip` được kiểm tra và smoke test distribution.
- [ ] Candidate được tạo một lần trên exact trusted tag commit.
- [ ] Manifest có commit SHA, release version và ZIP SHA256.
- [ ] Release job download same-run artifact, validate bytes/version.
- [ ] Privileged release job không chạy Gradle hoặc source của PR.
- [ ] GitHub Actions action versions được kiểm soát; pin SHA khi production.
- [ ] Artifact retention đủ dài để approvals không hết hạn.
- [ ] Sau release có checksums/provenance để audit và verify từ ngoài.
- [ ] Nếu dùng Maven: stage→promotion/typed credentials và immutable GAV rõ.
- [ ] Khi failure, không retry publish mù hoặc overwrite đã phát hành.
- [ ] Có incident runbook cho token leak, wrong asset, cache poisoning, unauthorized tags.

## 16. Câu hỏi tự kiểm tra

1. Vì sao Gradle build scripts là executable code?
2. CI verification job khác release job ở quyền nào?
3. Hai jobs chạy trên cùng self-hosted runner có luôn cách ly secrets không?
4. `pull_request` và `pull_request_target` khác nhau thế nào?
5. Vì sao `workflow_run` không tự làm artifact PR trở nên trusted?
6. GitHub Environment có tự bật required reviewers khi chỉ gõ tên không?
7. Vì sao phải bảo vệ quyền tạo/sửa tag `v*`?
8. `contents: read` có đủ cho job tạo GitHub Release không?
9. Khi nào cần `contents: write`?
10. Vì sao release job của lab không checkout và chạy lại Gradle?
11. `sha256sum --check` bảo vệ khỏi loại lỗi nào?
12. Nếu attacker kiểm soát producer và SHA256SUMS thì hash có đủ không?
13. Mối liên hệ giữa GitHub artifact digest và attestation là gì?
14. Vì sao upload ZIP không đồng nghĩa deployment?
15. Additional JVM integration suite cần `implementation(project())` vì sao?
16. `:app:check` có chạy integrationTest nếu không nối `dependsOn` không?
17. `:app:build` có tự chạy `:core:test` vì project dependency không?
18. ZIP Application plugin có tự bundle JDK 17 không?
19. Remote Build Cache có thể là nguồn poisoning thế nào?
20. Configuration Cache có thể gây leak secret ở đâu?
21. `distributionSha256Sum` khác checksum Wrapper JAR ở điểm nào?
22. Tại sao release cần branch/tag rules dù workflow `if` đúng?
23. Maven Publish chạy trong privileged runner có nguy cơ gì?
24. Khi nào chọn repository-side promotion thay vì Gradle republish?
25. Vì sao không retry `gh release create` mù?
26. `--no-build-cache` có ngăn build script đọc environment không?
27. Biện pháp tối thiểu khi Maven token lộ là gì?
28. Tại sao action versions nên pin theo SHA?
29. Nếu tag `v2.3.0-rc1` không pass regex, có nên tắt toàn release gate không?
30. Mục tiêu cuối của mô hình là gì? **Artifact đúng, đã qua gates, gắn commit/version và phát hành bằng quyền có kiểm soát mà không trao secrets cho mã chưa tin cậy.**

## 17. Tài liệu chính thức

- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html): Wrapper, init scripts, `buildSrc`, Gradle User Home, caches, daemon và untrusted source.
- [Gradle — Securing Gradle Builds](https://docs.gradle.org/current/userguide/security.html): ranh giới repositories, dependencies, build tool.
- [Gradle — Securing Repositories](https://docs.gradle.org/current/userguide/securing_repositories.html): HTTPS, content filters, dependency confusion.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksum/signature metadata.
- [Gradle — GitHub Actions](https://docs.gradle.org/current/userguide/github-actions.html): `gradle/actions/setup-gradle@v6`, Wrapper validation/caching.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): `integrationTest`, `implementation(project())`, `check`.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): JUnit/tasks/reports.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, `installDist`, `distZip`.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): `MavenPublication`, remote publishing and task names.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cache correctness và remote cache.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): persisted state và secrets.
- [GitHub — Securely using pull_request_target](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target): privileged event risks.
- [GitHub — Secure use reference](https://docs.github.com/en/actions/reference/security/secure-use): token permissions, workflows, untrusted data.
- [GitHub — Managing Environments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments): required reviewers, protection rules, secrets.
- [GitHub — Workflow Syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): triggers, conditions, permissions, needs.
- [GitHub — Storing and sharing workflow data](https://docs.github.com/en/actions/tutorials/store-and-share-data): artifact upload/download, digest.
- [GitHub — Artifact attestations](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations): signed provenance via `actions/attest`.
- [GitHub CLI — gh release create](https://cli.github.com/manual/gh_release_create): `--verify-tag` và release asset upload.
