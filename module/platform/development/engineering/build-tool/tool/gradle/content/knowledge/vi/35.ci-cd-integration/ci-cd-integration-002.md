# Thiết kế các bước kiểm tra, kiểm thử, đóng gói và phát hành với Gradle trong CI/CD

## 1. Kết quả mong đợi của một pipeline

Một pipeline Gradle cho Java phải biến **một commit đã được xác định** thành **artifact đã được kiểm tra**, sau đó chỉ phát hành khi đạt các điều kiện về chất lượng và quyền truy cập. Bốn bước chính không được đánh đồng:

1. **Kiểm tra (verification):** dự án cấu hình/biên dịch đúng, Java style/static analysis/dependency policy đạt yêu cầu.
2. **Kiểm thử (testing):** unit tests, integration/contract tests được chọn và chạy đúng môi trường; reports lưu lại.
3. **Đóng gói (packaging):** sinh JAR, application distribution ZIP/TAR hoặc artifact loại khác, kiểm tra nội dung và checksum.
4. **Phát hành (publishing/release):** xuất bản chính artifact và metadata sang Maven repository hoặc distribution server sau khi được phê duyệt.

~~~text
Git commit / pull request
       |
       v
checkout + Gradle Wrapper + JDK 17 + credentials policy
       |
       v
compile / static checks / dependency verification
       |
       v
unit tests :core:test :app:test
       |
       v
integration test :app:integrationTest
       |
       v
quality gate :core:check :app:check
       |
       v
package :core:jar :app:distZip
       |
       v
artifact inspection, hashes, Maven metadata
       |
       v
protected tag + approval + release secrets
       |
       v
publish :core:publishMavenJavaPublicationToReleaseRepository
       |
       v
verify published bytes/coordinates and record provenance
~~~

**Đừng coi `./gradlew build` là toàn bộ CD pipeline**: Java/Base plugin định nghĩa lifecycle `build` thường phụ thuộc `assemble` và `check`; `maven-publish` tạo các task xuất bản riêng. Bất cứ thao tác deploy server, promote release, kiểm tra environment, thu hồi release hoặc chạy health check nào cũng cần mô hình hóa qua CI/CD hoặc các plugin/tasks bổ sung.

Bài này cung cấp một lab **Gradle Kotlin DSL + Java 17** gồm Java library `:core`, Java Application `:app`, JUnit unit tests, JVM integration test suite, Maven publication staging, run/distribution commands và GitHub Actions workflow. Các code block ví dụ độc lập được ghi đầy đủ; những mảnh mở rộng dùng repository thật được chỉ rõ là tùy chọn.

## 2. Nhận diện đúng lifecycle tasks của Gradle

| Gradle task | Phạm vi và chức năng | Điều nó KHÔNG tự bảo đảm |
| --- | --- | --- |
| `compileJava` | Compile Java source và dependencies cần thiết. | Không chạy JUnit assertions. |
| `test` | Chạy unit tests trong default test source set. | Không tự chọn integration suites khác. |
| `check` | Lifecycle verification: thường gồm `test` và verification tasks được khai báo. | Không bao gồm plugin kiểm tra chưa được áp hoặc suite chưa được nối. |
| `jar` | Đóng JAR từ Java classes/resources của project. | Không tự thành executable/fat JAR đủ runtime libraries. |
| `assemble` | Tập hợp artifacts đã đăng ký của project. | Không nhất thiết chạy tests. |
| `build` | Lifecycle thường đòi `assemble` và `check`. | Không tự publish artifact. |
| `run` | Application plugin chạy main class từ runtime classpath. | Không thử distribution đã đóng gói. |
| `installDist` | Application plugin tạo installation directory với scripts/libs. | Không cài vào production server. |
| `distZip`/`distTar` | Application plugin tạo full distribution. | Không tự upload release. |
| `publishToMavenLocal` | Xuất publication vào local Maven repository. | Không publish tới server remote. |
| `publish` | Aggregate Maven Publish tasks cho các publishing repositories đã cấu hình. | Không biết CI approval/credentials policy. |
| `publish<Name>PublicationTo<Repo>Repository` | Publish đúng publication→repository. | Không mặc nhiên chạy mọi integration/security gate. |

Từ root multi-project build, `./gradlew build` là **task selector** chọn các `build` tasks phù hợp ở root/subprojects; `./gradlew :build` chọn **root-only** task rồi chạy prerequisites của nó. Nếu chỉ muốn app:

~~~bash
./gradlew :app:build
~~~

Lệnh này có thể kéo tasks compile/artifact của `:core` khi app phụ thuộc project, nhưng **không tự chạy `:core:test`** chỉ vì `implementation(project(":core"))`. Release CI nên chọn cả `:core:check` và `:app:check`.

## 3. Xác lập các gates trước khi viết YAML

| Stage | Task / kiểm tra | Điều kiện PASS | Artifact / chứng cứ |
| --- | --- | --- | --- |
| Setup | Wrapper validation, JDK/toolchain, checkout commit | Phiên bản và đường dẫn hợp lệ. | Git SHA, Gradle/JDK versions. |
| Fast checks | `compileJava`, static style nếu có plugin | Compiler/linter pass. | Compile/log/reports. |
| Unit tests | `:core:test :app:test` | JUnit assertions pass, không bị skip ngoài ý muốn. | JUnit XML/HTML. |
| Integration tests | `:app:integrationTest` | Cross-module hoặc service contract pass. | Separate reports/logs. |
| Quality gate | `:core:check :app:check` | Mọi task được nối vào check pass. | Job status, verification reports. |
| Package | `:core:jar :app:distZip` | JAR/ZIP thực sự tồn tại và nội dung hợp lệ. | JAR/ZIP, SHA-256. |
| Staging | Maven publication vào repository file/isolated server | GAV, POM/metadata/artifacts hợp lệ. | Staged Maven tree. |
| Release | protected tag + approval + credentials + publish | Remote repository nhận đúng artifact/version. | URL, GAV, signing/provenance. |
| Post-publish | External consumer resolves artifact, checksum verify | Bytes + contract thực tế đúng. | Downloaded hash/smoke results. |

Các plugin Checkstyle, SpotBugs, JaCoCo, SCA, CycloneDX/SBOM hoặc signing **không tự xuất hiện** chỉ vì Gradle được cài. Nếu pipeline đòi chúng, phải apply plugin, pin version, cấu hình rules/thresholds và nối task vào gate. Còn `--dry-run` chỉ in task graph dự kiến, **không** xác nhận pass.

Tối ưu thứ tự gate dựa trên chi phí: các checks nhanh nên fail sớm, các tests chậm cần cách cô lập resources, publish phải chạy với quyền riêng. Không dùng retry để che mã nguồn fail test một cách ổn định.

## 4. Lab đầy đủ: Java library và Java application

### 4.1. Cấu trúc

~~~text
pipeline-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── core/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/demo/core/Messages.java
│       └── test/java/demo/core/MessagesTest.java
├── app/
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/demo/app/Main.java
│       ├── test/java/demo/app/MainTest.java
│       └── integrationTest/java/demo/app/AppIntegrationTest.java
└── .github/workflows/ci.yml
~~~

Yêu cầu: Gradle Wrapper hoạt động, Gradle version tương thích với JVM Test Suite plugin, JDK 17 có thể resolve bằng local installation/toolchain, Maven Central truy cập được để tải JUnit. JVM Test Suite plugin còn được tài liệu Gradle đánh dấu **incubating**, nên kiểm thử compatibility khi nâng Gradle. Các lệnh `./gradlew` dành cho Unix; PowerShell dùng `.\gradlew.bat`.

### 4.2. Root `settings.gradle.kts`

~~~kotlin
rootProject.name = "pipeline-lab"
include("core", "app")
~~~

Hai subprojects `:core`/`:app` thuộc **cùng một multi-project build**. Không thay `include("core")` bằng `includeBuild("core")` trong lab, vì app sẽ dùng project dependency `project(":core")`.

### 4.3. Root `build.gradle.kts`

~~~kotlin
plugins {
    base
}

tasks.register("verifyAll") {
    group = "verification"
    description = "Run the defined verification gates"
    dependsOn(":core:check", ":app:check")
}
~~~

`verifyAll` là root aggregator tự tạo. Root `:build` của Base plugin không tự chọn hai child `:build` tasks nếu không có explicit dependency; từ root dùng selector `./gradlew build` hoặc task `:verifyAll` của bài.

### 4.4. Library `core/build.gradle.kts`

~~~kotlin
plugins {
    `java-library`
    `maven-publish`
}

group = "dev.example.pipeline"
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
    withSourcesJar()
    withJavadocJar()
}

testing {
    suites {
        named<JvmTestSuite>("test") {
            useJUnitJupiter("5.11.4")
        }
    }
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            artifactId = "pipeline-core"
            from(components["java"])

            pom {
                name.set("Pipeline Core")
                description.set("Java library used by the CI/CD lab")
            }
        }
    }

    repositories {
        maven {
            name = "staging"
            url = uri(layout.buildDirectory.dir("staging-repository"))
        }
    }
}
~~~

**Giải thích:**
- `java-library` tạo compilations, JAR, Java component và test lifecycle.
- `maven-publish` chỉ tạo publishing model/tasks; không tự publish khi chạy `build`.
- `group` và `version` kết hợp `artifactId = "pipeline-core"` xác định GAV `dev.example.pipeline:pipeline-core:1.0.0-SNAPSHOT` theo default.
- `from(components["java"])` xuất artifact cùng dependencies/variants metadata của Java component.
- `withSourcesJar`/`withJavadocJar` yêu cầu artifacts bổ sung cho publication.
- `testing.suites.named<JvmTestSuite>("test")` cấu hình built-in unit test suite chạy JUnit Jupiter. `useJUnitJupiter` cung cấp test framework dependencies cho suite, thay vì phải cấu hình thủ công các dependencies của Test task.
- Repo `staging` là Maven-compatible directory nằm dưới `core/build/`, không cần credentials và **không phải production**.
- `releaseVersion` đọc từ Gradle project property, default snapshot. CI phải đưa cùng value cho verification và publishing nếu chúng ở các jobs khác nhau.

### 4.5. App `app/build.gradle.kts`

~~~kotlin
plugins {
    application
}

group = "dev.example.pipeline"
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
    mainClass.set("demo.app.Main")
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

            // Additional suites do not implicitly depend on main outputs.
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

// Explicitly include integration tests in quality gate.
tasks.named("check") {
    dependsOn(testing.suites.named("integrationTest"))
}
~~~

Gradle JVM Test Suite plugin được `java`/`application` áp dụng gián tiếp. **Additional suite** cần `implementation(project())` để test classes compile against app production outputs và dependencies; nếu thiếu, integration test có thể không nhìn thấy `demo.app.Main`. `shouldRunAfter(test)` là **ordering**, không tự chọn task `test`. `dependsOn(testing.suites.named("integrationTest"))` thêm suite vào `:app:check`.

Một production integration suite có thể cần Docker/Testcontainers, database/HTTP service, isolated ports, credentials và data cleanup. Lab dùng kiểm thử phối hợp **app → core** đơn giản để có thể chạy mà không cần service bên ngoài.

### 4.6. `core/src/main/java/demo/core/Messages.java`

~~~java
package demo.core;

public final class Messages {
    private Messages() {
    }

    public static String greeting() {
        return "pipeline-core";
    }
}
~~~

### 4.7. `core/src/test/java/demo/core/MessagesTest.java`

~~~java
package demo.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MessagesTest {
    @Test
    void greetingIsStable() {
        assertEquals("pipeline-core", Messages.greeting());
    }
}
~~~

### 4.8. `app/src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.core.Messages;

public final class Main {
    private Main() {
    }

    public static String result(String name) {
        return "PIPELINE_OK=" + Messages.greeting() + ":" + name;
    }

    public static void main(String[] args) {
        String name = args.length > 0 ? args[0] : "guest";
        System.out.println(result(name));
        System.out.println("ARG_COUNT=" + args.length);
    }
}
~~~

### 4.9. `app/src/test/java/demo/app/MainTest.java`

~~~java
package demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {
    @Test
    void formatsMainMessage() {
        assertEquals(
            "PIPELINE_OK=pipeline-core:CI",
            Main.result("CI")
        );
    }
}
~~~

### 4.10. `app/src/integrationTest/java/demo/app/AppIntegrationTest.java`

~~~java
package demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class AppIntegrationTest {
    @Test
    void applicationAndLibraryWorkTogether() {
        assertEquals(
            "PIPELINE_OK=pipeline-core:IT",
            Main.result("IT")
        );
    }
}
~~~

Test này kiểm chứng app gọi API thư viện qua project dependency. Nó là **integration tối thiểu giữa modules**, chưa phải end-to-end test HTTP/database/production deployment. Source folder `src/integrationTest/java` được test suite tên `integrationTest` dùng theo convention.

## 5. Chạy lab tại local: kiểm tra stdout và các stage

### 5.1. Chạy Java Application

~~~bash
./gradlew :app:run --args="CI"
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:run --args="CI"
~~~

**Hai dòng do `Main.main` in:**

~~~text
PIPELINE_OK=pipeline-core:CI
ARG_COUNT=1
~~~

Gradle có thể in thêm `> Task :app:run`, daemon/logging/warning. Hai dòng trên là Java stdout, không phải toàn bộ terminal transcript bất biến.

### 5.2. `javac`/`java` độc lập

Unix:

~~~bash
mkdir -p build/manual/core build/manual/app

javac -encoding UTF-8 -d build/manual/core \
    core/src/main/java/demo/core/Messages.java

javac -encoding UTF-8 -cp build/manual/core \
    -d build/manual/app \
    app/src/main/java/demo/app/Main.java

java -cp build/manual/core:build/manual/app demo.app.Main CI
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual/core | Out-Null
New-Item -ItemType Directory -Force build/manual/app | Out-Null

javac -encoding UTF-8 -d build/manual/core core/src/main/java/demo/core/Messages.java
javac -encoding UTF-8 -cp build/manual/core -d build/manual/app app/src/main/java/demo/app/Main.java

java -cp "build/manual/core;build/manual/app" demo.app.Main CI
~~~

Expected Java stdout vẫn:

~~~text
PIPELINE_OK=pipeline-core:CI
ARG_COUNT=1
~~~

Đây chỉ là kiểm tra Java source và classpath; nó **không chứng minh** Gradle Test Suite/publishing đúng. Trên Unix, `:` là Java classpath separator; trên Windows dùng `;`. Cú pháp đó không cùng nghĩa Gradle task path.

### 5.3. Chạy từng gate

~~~bash
# Biết các project/task thật.
./gradlew --version
./gradlew projects
./gradlew :app:tasks --all

# Compile nhanh.
./gradlew :core:compileJava :app:compileJava

# Unit tests.
./gradlew :core:test :app:test

# Integration test suite riêng.
./gradlew :app:integrationTest

# Quality gate (bao gồm integrationTest ở app).
./gradlew :core:check :app:check
./gradlew :verifyAll
~~~

`:app:compileJava` có thể kéo producer tasks của `:core`, nhưng **không** mặc nhiên chạy `:core:test`. Đó là lý do CI chọn core và app tests riêng, rồi quality gate tổng thể.

Khi `:app:integrationTest` không có: kiểm tra `testing.suites.register<JvmTestSuite>("integrationTest")`, Gradle version, `src/integrationTest/java` và `:app:tasks --all`. `--dry-run` giúp xem graph, không chạy assertions.

### 5.4. Các báo cáo test

Test tasks thường lưu:
- `core/build/test-results/test/` và `core/build/reports/tests/test/`.
- `app/build/test-results/test/` và `app/build/reports/tests/test/`.
- `app/build/test-results/integrationTest/` và `app/build/reports/tests/integrationTest/`.

XML reports để CI parse, HTML để debug. Không nên upload logs chứa passwords/tokens hoặc test fixtures có dữ liệu nhạy cảm. Nếu một project báo `NO-SOURCE`, kiểm tra test discovery và source folders; đừng đánh đồng với “tất cả assertions đã chạy pass”.

### 5.5. Package

~~~bash
./gradlew :core:jar
./gradlew :app:distZip
./gradlew :app:distTar
./gradlew :app:installDist
~~~

- Plain `:app:jar` thường **không bundle toàn bộ runtime libraries** và không mặc nhiên là executable `java -jar`.
- Application plugin `distZip`/`distTar` đóng app JAR, runtime classpath dependencies và launch scripts.
- `installDist` tạo install directory để smoke test scripts.

Với version default, ZIP thường ở `app/build/distributions/app-1.0.0-SNAPSHOT.zip`. Nếu project customize `archiveFileName`/`destinationDirectory`, dùng task output Provider thay vì giả định path.

Smoke test Unix:

~~~bash
./gradlew :app:installDist
./app/build/install/app/bin/app CI
~~~

PowerShell:

~~~powershell
.\gradlew.bat :app:installDist
.\app\build\install\app\bin\app.bat CI
~~~

Khi launcher và JDK đúng, Java stdout là hai dòng `PIPELINE_OK=pipeline-core:CI` và `ARG_COUNT=1`. Đây là kiểm tra **distribution packaging** khác với chỉ dùng `:app:run`.

## 6. Tạo staging Maven publication

Maven Publish plugin của `:core` có publication `mavenJava` và repository `staging`. Gọi:

~~~bash
./gradlew :core:publishMavenJavaPublicationToStagingRepository
~~~

Dự kiến repo file được tạo trong:

~~~text
core/build/staging-repository/
└── dev/example/pipeline/pipeline-core/
    └── 1.0.0-SNAPSHOT/
        ├── pipeline-core-1.0.0-SNAPSHOT.jar
        ├── pipeline-core-1.0.0-SNAPSHOT.pom
        ├── pipeline-core-1.0.0-SNAPSHOT.module
        └── source/javadoc artifacts, checksums, metadata khác
~~~

Tên đích chính xác tùy snapshot policy/repository plugin, và một số repository manager dùng timestamped snapshots. Staging file repo trong lab không sử dụng Maven Central và không cần network credentials.

### Đường đi của publication

~~~text
core Java component
  ├── compiled classes + resources -> jar
  ├── sourcesJar (configured)
  ├── javadocJar (configured)
  ├── Maven POM
  └── Gradle Module Metadata
             |
             v
MavenPublication("mavenJava")
             |
             v
Maven repository "staging"
~~~

Các task diagnostic:

~~~bash
./gradlew :core:generatePomFileForMavenJavaPublication
./gradlew :core:generateMetadataFileForMavenJavaPublication
./gradlew :core:publishMavenJavaPublicationToStagingRepository
~~~

**Lưu ý tên file:** JAR output thường của `:core:jar` là `core-1.0.0-SNAPSHOT.jar` theo project name `core`; Maven artifact sau publishing là `pipeline-core-1.0.0-SNAPSHOT.jar` do `artifactId="pipeline-core"`. Maven artifactId không tự đổi `jar.archiveBaseName`.

Đừng dùng `./gradlew publish` ở PR khi build đã cấu hình remote repository; task aggregate có thể publish vào **tất cả** repositories đã đăng ký. Dùng task publication→repository cụ thể để tránh xuất bản ngoài ý muốn.

### Kiểm tra POM và variants

Maven POM `groupId/artifactId/version` phải khớp release policy. Gradle Module Metadata có variants/dependency information phong phú hơn POM trong một số trường hợp. Build cùng project dependency có thể pass nhưng **published artifact** vẫn có POM sai; cần một external consumer test giải quyết GAV từ staging/remote repository để kiểm tra contract thật.

## 7. Remote Maven publish an toàn: chỉ bật khi release

Để cấu hình remote repository, thêm **mảnh tùy chọn** sau block `publishing` trong `core/build.gradle.kts`:

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

Đặt `import` ở đầu file Kotlin DSL trước `plugins` nếu áp dụng. `if (releaseRepoUrl.isPresent)` giúp PR không cần remote URL; build chỉ có release repository khi biến đó được cấp. Khi có repository tên `release`, task publication-to-repository tương ứng:

~~~bash
./gradlew :core:publishMavenJavaPublicationToReleaseRepository \
  -PreleaseVersion=2.3.0
~~~

**Chỉ chạy lệnh thật khi** đã có Maven server, URL hợp lệ, credentials/approvals và policy. Lab thuần local sử dụng `staging`.

Với `credentials(PasswordCredentials::class)`, Gradle có thể tự inject project properties theo repository name:

~~~text
releaseUsername
releasePassword
~~~

Trên GitHub Actions, dùng environment variables:

~~~text
ORG_GRADLE_PROJECT_releaseRepoUrl
ORG_GRADLE_PROJECT_releaseUsername
ORG_GRADLE_PROJECT_releasePassword
~~~

Giá trị được lấy từ **CI Secrets/Variables**, không commit vào repo `gradle.properties` và không in log. Repository có thể là Nexus, Artifactory, GitHub Packages hoặc server Maven-compatible khác với policy auth/version riêng.

### Maven Central không giống mọi Maven server

Maven Central hiện hành sử dụng Central Portal workflow và không còn legacy OSSRH deployment path như trước; theo Gradle docs, publish lên Maven Central cần plugin/workflow phù hợp. Không chỉ đổi `releaseRepoUrl` sang một Maven Central URL rồi khẳng định publishing hoàn chỉnh.

### Khi publish fail một phần

Server có thể đã nhận JAR nhưng POM/metadata/signature bị lỗi sau đó, hoặc response timeout dù artifact đã tồn tại. Đừng retry mù, nhất là khi release GAV là immutable. Kiểm tra server state, checksum và release policy, sau đó chọn retry/resume/rollback thích hợp. Không overwrite cùng version bằng bytes mới chỉ để “sửa nhanh”.

## 8. Phiên bản và tính tái lập giữa jobs

Lab sử dụng:

~~~kotlin
version = providers.gradleProperty("releaseVersion")
    .orElse("1.0.0-SNAPSHOT")
    .get()
~~~

Từ CLI:

~~~bash
./gradlew :core:jar :app:distZip -PreleaseVersion=2.3.0
~~~

Mọi project phải nhận **cùng version value** nếu release muốn gắn artifacts vào cùng bản phát hành. Lệnh `-PreleaseVersion` không tự chứng minh đã kiểm thử version đó; CI cần commit SHA, tag, build run ID, Java/Gradle/compiler versions và hashes.

### Reproducible bytes

Hai builds từ cùng source **có thể tạo JAR/ZIP khác SHA-256** do timestamp, file order, Gradle/plugin/JDK version, locale, random seed, generated build time hoặc absolute paths. Gradle 9.x có defaults giúp archive reproducibility, nhưng code generator/plugin khác vẫn có thể gây khác biệt.

Khi hỗ trợ Gradle cũ hoặc muốn policy tường minh:

~~~kotlin
tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
~~~

Đây là cấu hình **tùy chọn** trong Gradle Kotlin DSL project script. SHA-256 xác nhận bytes giống nhau, không thay chữ ký/provenance và không chứng minh artifact an toàn trước mã độc.

Một release nên lưu:
- `group:artifactId:version`.
- Git commit SHA và protected tag.
- Gradle Wrapper/JDK version.
- Artifact SHA-256, POM/Module Metadata.
- SBOM/signatures khi policy yêu cầu.
- CI run ID và actor/approval.
- Remote repository URL/immutable release status.

## 9. GitHub Actions: workflow có 4 bước gate và release job riêng

Tài liệu Gradle chính thức mô tả `gradle/actions/setup-gradle@v6`: quản lý Gradle User Home caching, phân tích build và kiểm tra Wrapper. Kết hợp `actions/checkout@v4`, `actions/setup-java@v4`, `actions/upload-artifact@v4`; trong hệ thống bảo mật cao, nên pin action SHAs đã review thay vì chỉ major tags.

### 9.1. `.github/workflows/ci.yml`

~~~yaml
name: Gradle Java CI and Maven release

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
    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v6

      - name: Set release version consistently
        shell: bash
        run: |
          if [[ "$GITHUB_REF_TYPE" == "tag" && "$GITHUB_REF_NAME" == v* ]]; then
            echo "ORG_GRADLE_PROJECT_releaseVersion=${GITHUB_REF_NAME#v}" >> "$GITHUB_ENV"
          else
            echo "ORG_GRADLE_PROJECT_releaseVersion=1.0.0-SNAPSHOT" >> "$GITHUB_ENV"
          fi

      - name: Compile and validate basic configuration
        run: ./gradlew :core:compileJava :app:compileJava --stacktrace --console=plain

      - name: Unit tests
        run: ./gradlew :core:test :app:test --stacktrace --console=plain

      - name: Integration tests
        run: ./gradlew :app:integrationTest --stacktrace --console=plain

      - name: Quality gate
        run: ./gradlew :core:check :app:check --stacktrace --console=plain

      - name: Package and stage Maven publication
        run: ./gradlew :core:jar :app:distZip :core:publishMavenJavaPublicationToStagingRepository --stacktrace --console=plain

      - name: Upload verified artifacts
        uses: actions/upload-artifact@v4
        with:
          name: verified-artifacts
          path: |
            core/build/libs/*.jar
            app/build/distributions/*.zip
            core/build/staging-repository/**
          if-no-files-found: error

      - name: Upload failing test reports
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: failed-test-reports
          path: |
            core/build/reports/tests/**
            app/build/reports/tests/**
            core/build/test-results/**
            app/build/test-results/**
          if-no-files-found: ignore

  release:
    if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')
    needs: verify-and-package
    runs-on: ubuntu-latest
    environment: production-release
    permissions:
      contents: read
    steps:
      - name: Checkout approved commit
        uses: actions/checkout@v4

      - name: Set up JDK
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Set up Gradle
        uses: gradle/actions/setup-gradle@v6

      - name: Publish Maven library
        shell: bash
        env:
          ORG_GRADLE_PROJECT_releaseRepoUrl: ${{ vars.RELEASE_REPO_URL }}
          ORG_GRADLE_PROJECT_releaseUsername: ${{ secrets.RELEASE_REPO_USERNAME }}
          ORG_GRADLE_PROJECT_releasePassword: ${{ secrets.RELEASE_REPO_PASSWORD }}
        run: |
          VERSION="${GITHUB_REF_NAME#v}"
          ./gradlew :core:publishMavenJavaPublicationToReleaseRepository -PreleaseVersion="$VERSION" --stacktrace --console=plain
~~~

**Điều kiện ngoài file YAML:**
- Tạo GitHub Environment tên `production-release` và approvals/tag protection thích hợp.
- Cấp `RELEASE_REPO_URL`, `RELEASE_REPO_USERNAME`, `RELEASE_REPO_PASSWORD` cho release environment.
- Đã thêm remote Maven repo snippet mục 7 trong `core/build.gradle.kts`.
- Tag `v2.3.0` phải trỏ tới commit đã được review; bảo vệ quyền tạo tags.
- Maven server tồn tại, credentials đúng scope; pipeline không tự tạo server.
- Pin action SHAs nếu policy supply-chain yêu cầu; bảo vệ default branch/Workflow changes.

### 9.2. Vì sao tách release job?

`pull_request` không được trao publishing secrets. Chỉ push tag hợp lệ và có `needs: verify-and-package` mới được chạy release; GitHub protected environment có thể yêu cầu approval. Tuy nhiên, **một tag tên v... không tự chứng minh tag an toàn** nếu repo không bảo vệ quyền tạo tag.

### 9.3. Cảnh báo: hai runners có hai filesystem riêng

Verify job tạo staging JAR/POM, upload `verified-artifacts`. Release job checkout lại commit và chạy Gradle publish mới; nó **có thể rebuild artifacts**. Dùng cùng commit/version không bảo đảm **bytes identical** nếu output phụ thuộc timestamp/host/JDK/plugin state.

Nếu yêu cầu **publish exact tested artifact**, thiết kế production nên:
1. Build canonical release artifacts một lần.
2. Tính SHA-256/provenance và archive chúng vào protected artifact storage.
3. Release job tải đúng bytes đó, kiểm tra hashes/signatures.
4. Promote/upload **those bytes** bằng repository-specific promotion workflow, không build lại.
5. Sau publish, tải từ repository và so SHA-256.

Workflow trong bài là mẫu rõ stages và đủ để luyện tập khi có server, **không** tự cài artifact promotion logic hoặc bảo đảm bit-for-bit release provenance. Một hệ thống production cần làm thêm bước này nếu chính sách yêu cầu.

### 9.4. Không dùng cache trùng

`gradle/actions/setup-gradle` quản lý cache Gradle User Home; tránh thêm một `actions/cache` khác cache nguyên `~/.gradle` chồng lên nó gây conflict. Cache cải thiện performance, không bỏ quality gates. Một job `BUILD SUCCESSFUL` chỉ xác nhận các tasks **được chọn** thành công.

## 10. Thử package và checksum trước publish

Unix:

~~~bash
./gradlew :core:jar :app:distZip :core:publishMavenJavaPublicationToStagingRepository

jar tf core/build/libs/core-1.0.0-SNAPSHOT.jar
unzip -l app/build/distributions/app-1.0.0-SNAPSHOT.zip
sha256sum app/build/distributions/app-1.0.0-SNAPSHOT.zip
~~~

PowerShell:

~~~powershell
.\gradlew.bat :core:jar :app:distZip :core:publishMavenJavaPublicationToStagingRepository
jar tf core/build/libs/core-1.0.0-SNAPSHOT.jar
Get-FileHash -Algorithm SHA256 app/build/distributions/app-1.0.0-SNAPSHOT.zip
~~~

Dùng version mặc định từ lab; nếu cung cấp `-PreleaseVersion=...`, file names thay tương ứng. Không hard-code version artifact path trong reusable CI nếu project customize archives.

Cần inspect:
- JAR chứa expected `demo/core/Messages.class` và không chứa secrets.
- ZIP chứa app launcher scripts và runtime library JARs.
- POM có đúng GAV và required dependencies.
- Gradle Module Metadata không mất variants cần cho Gradle consumers.
- SHA-256/provenance được lưu và có thể đối chiếu với published binary.
- Smoke test launcher `installDist` thành công với expected Java stdout.

**Tại sao plain app JAR không đủ?** Gradle Application plugin tạo `distZip`/`distTar` để đóng runtime dependencies và scripts. Nếu muốn executable fat JAR, cần plugin/packaging strategy riêng, không đổi ý nghĩa `jar` mặc định bằng cách đặt tên file “app-all.jar”.

## 11. Supply-chain security cho pipeline Gradle

### Wrapper validation

Commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties` và `gradle-wrapper.jar` hợp lệ; pin Gradle distribution/version. GitHub `setup-gradle` hỗ trợ Wrapper validation; nếu không dùng action đó, có thể chạy `gradle/actions/wrapper-validation@v6` riêng.

### Dependency locking và verification

Để kiểm soát resolution:
- Pin versions/version catalog và dùng dependency locking theo chính sách khi cần.
- Cấu hình `gradle/verification-metadata.xml` với checksums/signatures đã review.
- Tách **dependency integrity verification** khỏi **vulnerability scanning**. Một JAR đúng SHA-256 vẫn có thể chứa CVE.

Lệnh bootstrap metadata, dùng một lần khi thiết lập/đổi dependencies:

~~~bash
./gradlew --write-verification-metadata sha256
~~~

**Không chạy câu lệnh bootstrap này mặc định trong mỗi CI job**. Nó tự tin vào artifact bytes hiện có từ repository và tạo metadata; phải review hashes độc lập trước khi commit. Khi metadata được giữ trong VCS, strict verification giúp phát hiện artifact checksum khác expected.

### Signatures, SBOM và provenance

Maven Publish plugin không tự tạo ký số release nếu chưa cấu hình Signing plugin hoặc server-specific process. Nếu yêu cầu:
- Signing key/credential qua secret management, không commit private key.
- SBOM theo CycloneDX/SPDX plugin/tool riêng, không tự có với Java plugin.
- Release provenance theo CI attestations/build run/commit, và checksum trước-sau.
- Chọn registry/token privileges thấp nhất, định danh các approved publishing principals.
- Xem xét OIDC/short-lived tokens nếu Maven repository hỗ trợ.

### Trust boundary

- PR code không được chạy với production secrets.
- Protected tag/release environment cần approvers có quyền.
- CI actions nên pin SHA để hạn chế tags bị đổi.
- Logs/artifacts/test reports có thể chứa dữ liệu nhạy cảm; kiểm tra policy retention và access.
- Remote Build Cache chỉ nên cho trusted CI push khi có governance; không xem cache outputs như artifact signed/released.

## 12. Lỗi CI thường gặp

| Triệu chứng | Lý do | Hành động sửa |
| --- | --- | --- |
| `./gradlew :build` từ root không chạy app tests | Root-only path. | Dùng task selector `build` hoặc `:core:check :app:check`. |
| `:app:build` pass nhưng core tests không chạy | App chỉ cần core artifact producers. | Chọn `:core:test`/`:core:check` rõ. |
| `integrationTest` không tồn tại | Chưa khai báo JVM Test Suite. | `register<JvmTestSuite>("integrationTest")`, xem `:app:tasks --all`. |
| Integration code không thấy Main | Additional suite thiếu project dependency. | `implementation(project())` trong suite. |
| Integration test chạy nhưng không thuộc `check` | Không nối lifecycle. | `tasks.named("check") { dependsOn(testing.suites.named("integrationTest")) }`. |
| `shouldRunAfter` mà unit tests không chạy | Ordering rule không select task. | Cần gọi tasks/suite hoặc nối check. |
| Java 17 toolchain không resolve | Runner thiếu JDK/toolchain config. | `setup-java@v4` hoặc toolchain resolver hợp lệ. |
| Plain app JAR không chạy | Không có runtime libs/start script. | Dùng `distZip`/`installDist`. |
| `publishToMavenLocal` pass nhưng remote trống | Local Maven là filesystem của runner. | Gọi exact remote publication task. |
| GHA tag job thiếu publish task | `releaseRepoUrl` không được cung cấp, repo không được đăng ký. | Cấp property và verify Settings/build.gradle.kts. |
| 401/403 lúc publish | Token/permissions/URL sai. | Least privilege, secrets mapping, validate endpoint. |
| Maven version đã tồn tại | Server enforce immutable artifact. | Kiểm tra hashes/state, không overwrite mù. |
| Publish pass nhưng consumer không resolve được | POM/module metadata/GAV/repo cấu hình sai. | Test từ clean external consumer. |
| Test reports upload step fail ở compile | Chưa có report. | `if: failure()` và `if-no-files-found: ignore`. |
| Artifact upload không thấy ZIP | distZip chưa chạy/path sai. | Inspect tasks/output directories, giữ `if-no-files-found: error`. |
| CI build pass rất nhanh với `NO-SOURCE` | Tests không được tìm. | Kiểm tra source folder/test discovery. |
| `FROM-CACHE` nhưng artifact sai | Task input/output contract thiếu hoặc nondeterminism. | So no-cache execution và SHA, sửa task model. |
| Integration test flaky trong parallel CI | DB/port/files shared, dữ liệu không isolated. | Tách test fixtures/namespaces, hạn chế concurrency hợp lý. |
| Tag release version khác tested version | Jobs derive version khác nhau. | Áp cùng `releaseVersion`, lưu commit SHA. |
| Có secret trong log/test report | Config vô tình print raw credential. | Redact, revoke/rotate token, sửa logging. |

### Troubleshooting commands

~~~bash
./gradlew --version
./gradlew :app:tasks --all
./gradlew :core:check :app:check --stacktrace --info --console=plain
./gradlew :app:integrationTest --dry-run
./gradlew :app:distZip --info
./gradlew :core:publishMavenJavaPublicationToStagingRepository --info
~~~

`--dry-run` chỉ cho thấy graph. `--stacktrace`/`--info` giúp debug nhưng có thể chứa paths/environment, cần kiểm tra trước khi chia sẻ. Không dùng `--refresh-dependencies` hay xóa `~/.gradle/caches` như cách chữa chung cho mọi CI failure.

## 13. Checklist review trước khi merge workflow

- [ ] Root project paths đúng, không nhầm `build` và `:build`.
- [ ] Commit Gradle Wrapper và pin Gradle/JDK versions.
- [ ] Tất cả modules quan trọng có unit tests được chọn.
- [ ] Integration suite có dependencies, ordering, `check` wiring và isolation.
- [ ] Static analyzers thực sự được apply/cấu hình, không gọi task tưởng tượng.
- [ ] `check` gate chạy và reports upload/retention hợp lý.
- [ ] Package stage tạo đúng JAR/distribution và smoke test runtime.
- [ ] Maven publication đặt group/artifact/version + metadata chính xác.
- [ ] Stage staging không có production credentials.
- [ ] Release job chỉ có trên trusted tags/approval và được guard bằng `needs`.
- [ ] Gradle project properties cho repo URL/credentials được inject an toàn.
- [ ] Không gọi aggregate `publish` vô tình đến nhiều repos.
- [ ] Version và git SHA nhất quán giữa jobs.
- [ ] Có chính sách canonical artifact/exact bytes promotion khi cần.
- [ ] SHA-256, provenance, signing/SBOM theo release policy.
- [ ] External consumer verify published artifact, không chỉ project dependency.
- [ ] Registry version immutability/partial failure/retry được xử lý.
- [ ] Không cung cấp secrets cho untrusted PR code.
- [ ] Hạn chế cache/xóa cache vô cớ, phân biệt Build Cache với pass gates.
- [ ] Có runbook lỗi compile/test/packaging/publishing.
- [ ] Releases không bị nhầm với deployment đã thành công.

## 14. Câu hỏi tự kiểm tra

1. `assemble` có chạy unit tests mặc định không? Không, nó phục vụ packaging; `check` mới là verification lifecycle.
2. `build` có tự gọi Maven publish không? Không.
3. `:app:build` có mặc nhiên chạy `:core:test` khi app phụ thuộc core không? Không.
4. Tại sao cần `implementation(project())` cho additional JVM test suite? Để thấy production code/dependencies.
5. `shouldRunAfter(test)` có làm test tự chạy không? Không, chỉ áp ordering khi tasks được chọn.
6. Làm sao nối integration suite vào check gate? `dependsOn(testing.suites.named("integrationTest"))`.
7. Plain JAR khác application distribution ở điểm nào? Distribution có runtime dependencies và launch scripts.
8. `publishToMavenLocal` có upload remote Maven repository không? Không.
9. Tại sao nên gọi `publishMavenJavaPublicationToReleaseRepository` thay vì `publish`? Giới hạn đúng publication và repository.
10. Tại sao PR không nên có production publishing credentials? Mã PR có thể không tin cậy, nguy cơ secret exfiltration.
11. Hai jobs cùng commit/version có bảo đảm cùng SHA-256 artifact không? Không, có thể build nondeterministic.
12. Cần gì để publish exact tested bytes? Canonical artifacts được lưu, download/promote đúng bytes và checksum verification.
13. Dependency verification khác vulnerability scanning ra sao? Checksum/signatures xác minh identity/integrity; CVE scan tìm known vulnerabilities.
14. `--dry-run` có làm Maven server nhận JAR không? Không.
15. Vì sao tag cần được bảo vệ? Để release event chỉ do actor được phép tạo với commit approved.
16. Khi publish HTTP timeout, nên retry ngay không? Kiểm tra remote state và immutable version policy trước.
17. `NO-SOURCE` có nghĩa tests pass không? Không, nó báo không có sources cho task.
18. CI artifact ZIP có chứng minh đã deploy production không? Không.
19. Maven `artifactId` đổi có tự đổi `jar.archiveFileName` không? Không nhất thiết.
20. Mục tiêu cốt lõi của pipeline là gì? Artifact đúng, được kiểm thử, có nguồn gốc và chỉ phát hành với quyền/điều kiện được kiểm soát.

## 15. Tài liệu chính thức

- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): compile, test, assemble.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): Test tasks, reports, integration testing.
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html): `integrationTest`, `implementation(project())` và check wiring.
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html): `run`, `installDist`, `distZip`, `distTar`.
- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): MavenPublication, publish repositories, metadata.
- [Gradle — Publishing Setup](https://docs.gradle.org/current/userguide/publishing_setup.html): cấu hình publication.
- [Gradle — Repository Credentials](https://docs.gradle.org/current/userguide/supported_repository_protocols.html): PasswordCredentials, Gradle property auto-lookup.
- [Gradle — Gradle on GitHub Actions](https://docs.gradle.org/current/userguide/github-actions.html): `gradle/actions/setup-gradle`, wrapper validation/caching.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): checksums/signatures, verification metadata.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): output cache reuse và correctness.
- [Gradle — Security Best Practices](https://docs.gradle.org/current/userguide/best_practices_security.html): reproducible archives, dependency policies.
- [Gradle — Base Plugin](https://docs.gradle.org/current/userguide/base_plugin.html): lifecycle build/check/assemble.
- [GitHub Actions — Workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax): jobs, needs, if, permissions, environments.
- [GitHub Actions — Security hardening](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions): secret handling, least privilege, pinned actions.
