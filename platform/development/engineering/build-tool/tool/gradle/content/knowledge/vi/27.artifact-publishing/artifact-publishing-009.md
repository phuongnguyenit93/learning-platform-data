# Quy trình phiên bản, changelog, tag và phát hành artifact có thể truy vết trong Gradle

## 1. Mục tiêu: đi từ một JAR tới đúng source commit

Một thư viện Java đã phát hành không chỉ là file `library-1.0.0.jar`. Khi người dùng báo lỗi ở version `1.0.0`, team cần xác định được **chính xác** commit nào tạo ra artifact, version/changelog tương ứng, Gradle/JDK và dependency versions nào được sử dụng, kết quả kiểm thử nào đã đạt, ai phê duyệt và SHA-256 của file cuối cùng.

Một quy trình đầy đủ có chuỗi chứng cứ:

```text
PR + review
    |
    v
Source commit + CHANGELOG.md + version decision
    |
    v
Annotated/signed Git tag v1.0.0
    |
    v
CI checkout exact tag/commit
    |
    v
Gradle Wrapper + Java 17 toolchain + locked inputs
    |
    v
Compile + tests + metadata validation
    |
    v
Build JAR / sources / Javadoc / POM / .module
    |
    v
Stage + hashes/signatures/SBOM/consumer check
    |
    v
Approval -> promote exact verified bytes
    |
    v
Immutable Maven GAV + release notes + audit evidence
```

Bài học tập trung phạm vi **xuất bản artifact bằng Gradle**. Git và CI cung cấp truy vết, Maven repository phân phối artifact, còn Gradle chịu trách nhiệm build/publication. Không một thành phần nào tự thay thế được tất cả phần còn lại.

## 2. Các loại định danh phải phân biệt

| Thứ | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Project version** | `1.0.0` | Version dùng trong Gradle/POM. |
| **Maven GAV** | `com.example.training:traceable-greeting:1.0.0` | Group, artifact, version để consumer resolve. |
| **Git tag** | `v1.0.0` | Tên mốc release gắn với Git object/commit. |
| **Full commit SHA** | Giá trị từ `git rev-parse HEAD` | Danh tính chính xác của commit nguồn. |
| **Artifact SHA-256** | Hash của JAR đã publish | Danh tính bytes của file. |
| **Signature** | OpenPGP `.asc` | Bằng chứng chữ ký với public key/trust model phù hợp. |
| **CI run ID** | ID do pipeline cấp | Tra logs, checks, approvals, môi trường build. |

**Git tag không phải SHA-256 artifact.** Tag trỏ tới commit; JAR được tạo từ commit ấy có thể khác nhau nếu build inputs/toolchain không được chốt. Một filename `1.0.0.jar` cũng có thể bị đổi tên tùy ý. Vì vậy cần đối chiếu Git SHA, GAV, hashes, signatures và evidence record.

## 3. Version policy: SemVer, snapshot, prerelease

Với **Semantic Versioning** `MAJOR.MINOR.PATCH`:

- **MAJOR** khi thay đổi phá contract của public API.
- **MINOR** khi bổ sung tính năng/API vẫn tương thích với contract trước.
- **PATCH** khi sửa lỗi tương thích ngược.
- **Prerelease** có dạng `2.0.0-rc.1`, `2.0.0-beta.2`.
- `0.y.z` thường biểu diễn giai đoạn trước khi API ổn định hoàn toàn.

Ví dụ:

| Thay đổi | Version |
| --- | --- |
| Sửa lỗi không đổi public API | `1.0.0 -> 1.0.1` |
| Thêm API tương thích | `1.0.1 -> 1.1.0` |
| Xóa method public | `1.x -> 2.0.0` |
| Thử bản lớn sắp tới | `2.0.0-rc.1` |
| Phát triển theo quy ước Maven | `2.0.0-SNAPSHOT` |

Team phải xác định **public API** là gì. Với thư viện Java, nó gồm class/method signatures, hành vi, Java minimum runtime và có thể cả serialization format. Với Gradle plugin, plugin IDs, task names, DSL extension và minimum Gradle version cũng có thể là contract.

**Maven `-SNAPSHOT` không đồng nghĩa stable release**, và không nên đồng nhất hoàn toàn với SemVer prerelease. Snapshot thường được xử lý bằng repository/retention policy riêng; một `-rc.1` có identity phiên bản cụ thể. Không tái sử dụng một stable version từng được publish.

### 3.1. Một nguồn chân lý duy nhất

Có thể chọn một trong các cách:

1. Commit version trong `gradle.properties` và kiểm tra Git tag trùng nó.
2. Lấy version từ protected release tag, truyền vào Gradle qua `-PreleaseVersion=...`.
3. Với monorepo nhiều publications, dùng release manifest chứa từng module/version/tag/commit.

Trong bài lab, CI có thể dùng `-PreleaseVersion=1.0.0`. Khi không cung cấp, Gradle dùng `0.1.0-SNAPSHOT` cho local development. Chọn policy cố định và **không hard-code version trùng lặp** trong nhiều scripts mà không kiểm tra consistency.

## 4. Release lifecycle và quality gates

| Trạng thái | Công việc | Bằng chứng |
| --- | --- | --- |
| Prepare | Review PR, API, changelog và version. | PR/approval links. |
| Freeze | Chọn một source commit, tag chưa bị dùng. | Full SHA và tag. |
| Build | Checkout tag, build bằng Wrapper và JDK đã chốt. | CI run, toolchain info. |
| Verify | Unit/integration tests, scan, metadata QA. | Test reports/quality status. |
| Stage | Upload release candidate vào staging. | Artifact listing/GAV/checksums. |
| Consume | Consumer mới resolve và chạy artifact đã stage. | Consumer smoke results. |
| Approve | Reviewer/phê duyệt theo chính sách. | Approval record. |
| Promote | Upload/promote **chính bytes đã được xác minh**. | Published repository audit. |
| Announce | Release notes và link tag/GAV/digest. | Changelog/release page. |
| Observe | Theo dõi lỗi và phát hành hotfix khi cần. | Incident/release history. |

Một Gradle `publish` task **không tự đồng nghĩa test pass**. Trong bài lab sẽ thêm `publish.dependsOn(check)` như một policy. Với CI thực tế còn cần security gates, approval và staging verification.

## 5. Maven publication identity trong Gradle

`maven-publish` có `MavenPublication`. Theo cấu hình Java component thông thường:

```text
groupId    <- project.group
artifactId <- project.name, trừ khi publication override
version    <- project.version
```

Ví dụ:

```kotlin
group = "com.example.training"
version = "1.0.0"
```

và `settings.gradle.kts`:

```kotlin
rootProject.name = "traceable-greeting"
```

tạo GAV:

```text
com.example.training:traceable-greeting:1.0.0
```

Maven layout:

```text
com/example/training/traceable-greeting/1.0.0/
  traceable-greeting-1.0.0.jar
  traceable-greeting-1.0.0.pom
  traceable-greeting-1.0.0-sources.jar
  traceable-greeting-1.0.0-javadoc.jar
  ...
```

Ngoài các file trên, Gradle có thể publish Gradle Module Metadata `.module` và checksum files tùy configuration/repository. Mỗi artifact có hash riêng; POM/GAV nhận diện module, không phải checksum của JAR.

## 6. Ví dụ Java 17 hoàn chỉnh: xây và xuất bản vào Maven repository local

Bài tập dùng core plugins `java-library` và `maven-publish`, Java 17 toolchain, JUnit Jupiter, sources/Javadoc JAR và một file-based Maven repository dưới `build/`. Nó **không upload public**, không cần Maven server hoặc credentials.

### 6.1. Cây thư mục

```text
traceable-greeting/
├── settings.gradle.kts
├── build.gradle.kts
├── CHANGELOG.md
├── LICENSE
├── README.md
└── src/
    ├── main/java/demo/release/Greeting.java
    └── test/java/demo/release/GreetingTest.java
```

`README.md` và `LICENSE` khi xuất bản thật phải chứa dữ liệu có ý nghĩa, đúng quyền sử dụng. Không coi file license rỗng là đã hoàn thành nghĩa vụ pháp lý.

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "traceable-greeting"
```

### 6.2. build.gradle.kts đầy đủ

```kotlin
import org.gradle.api.publish.maven.MavenPublication

plugins {
    `java-library`
    `maven-publish`
}

group = "com.example.training"
version = providers.gradleProperty("releaseVersion")
    .orElse("0.1.0-SNAPSHOT")
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

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.test {
    useJUnitPlatform()
}

publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])

            pom {
                name.set("Traceable Greeting")
                description.set("Java library demonstrating traceable releases")
                url.set("https://example.org/traceable-greeting")

                licenses {
                    license {
                        name.set("The Apache License, Version 2.0")
                        url.set("https://www.apache.org/licenses/LICENSE-2.0.txt")
                    }
                }
                developers {
                    developer {
                        id.set("example-maintainer")
                        name.set("Example Maintainer")
                    }
                }
                scm {
                    connection.set(
                        "scm:git:https://example.org/traceable-greeting.git"
                    )
                    developerConnection.set(
                        "scm:git:ssh://git@example.org/traceable-greeting.git"
                    )
                    url.set("https://example.org/traceable-greeting")
                }
            }
        }
    }

    repositories {
        maven {
            name = "LocalStaging"
            val lane = if (project.version.toString().endsWith("-SNAPSHOT")) {
                "snapshots"
            } else {
                "releases"
            }
            url = uri(layout.buildDirectory.dir("publication-repo/$lane"))
        }
    }
}

// Quality gate của riêng bài lab: publish phải qua check.
tasks.named("publish") {
    dependsOn(tasks.named("check"))
}
```

**Giải thích:**

1. `java-library` tạo `components["java"]` để `MavenPublication` xuất bản một Java library.
2. `version` lấy từ `-PreleaseVersion` khi có; thiếu property thì dùng snapshot version, tránh bất ngờ xuất stable từ local.
3. `withSourcesJar()` và `withJavadocJar()` tạo classifiers `sources`/`javadoc`.
4. `testImplementation`/`testRuntimeOnly` chỉ cấp JUnit cho test; production library không có dependency JUnit.
5. `pom` có metadata thông thường cho repository; `example.org` và tên maintainer là **thông tin minh họa**, phải thay khi release thật.
6. `publishing.repositories` là **đích upload**, không phải nơi Java `implementation(...)` tải dependency.
7. Lệnh `publish` đẩy vào thư mục dưới `build/`; `clean` có thể xóa thư mục này. Nó **không tương đương public release**.
8. `publish.dependsOn(check)` được cấu hình **có chủ đích**. Task `publishToMavenLocal` không tự kế thừa quan hệ này; CI phải kiểm soát mọi đường upload.

### 6.3. Greeting.java biên dịch và chạy bằng JDK 17

**`src/main/java/demo/release/Greeting.java`:**

```java
package demo.release;

import java.util.Objects;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Hello, " + Objects.requireNonNull(name).strip() + "!";
    }

    public static void main(String[] args) {
        System.out.println(message(" Release "));
    }
}
```

Đây là Java 17-compatible code, không cần dependency ngoài. Biên dịch/chạy thủ công:

```bash
mkdir -p manual-out
javac --release 17 -d manual-out src/main/java/demo/release/Greeting.java
java -cp manual-out demo.release.Greeting
```

Stdout **chính xác**:

```text
Hello, Release!
```

`String.strip()` có từ Java 11. Dùng JDK17+ cho `javac --release 17`; runtime Java phải đọc được bytecode target Java17. Nếu shell chọn Java version khác, kiểm tra `java -version`.

### 6.4. GreetingTest.java với JUnit Jupiter

**`src/test/java/demo/release/GreetingTest.java`:**

```java
package demo.release;

import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;

public class GreetingTest {
    @Test
    void normalizesName() {
        assertEquals("Hello, Release!", Greeting.message(" Release "));
    }

    @Test
    void handlesBlankName() {
        assertEquals("Hello, !", Greeting.message(" "));
    }
}
```

`useJUnitPlatform()` và JUnit Jupiter dependencies đã được khai báo. Để chạy:

```bash
./gradlew test
./gradlew check
```

Cần Gradle Wrapper tương thích Java 17 và kết nối/cache Maven Central để tải JUnit. Test pass bảo đảm behavior đã kiểm tra trên source/classes, **chưa bảo đảm một remote artifact đã upload đúng bytes**. Vì vậy còn cần staging/consumer/hash checks.

### 6.5. Build release 1.0.0 thử nghiệm

```bash
./gradlew --version
./gradlew -PreleaseVersion=1.0.0 clean check publish
```

Đầu ra theo cấu hình lab:

```text
build/libs/
  traceable-greeting-1.0.0.jar
  traceable-greeting-1.0.0-sources.jar
  traceable-greeting-1.0.0-javadoc.jar

build/publication-repo/releases/com/example/training/
  traceable-greeting/1.0.0/
    traceable-greeting-1.0.0.jar
    traceable-greeting-1.0.0.pom
    traceable-greeting-1.0.0-sources.jar
    traceable-greeting-1.0.0-javadoc.jar
    traceable-greeting-1.0.0.module
    ...
```

Sự hiện diện của `.module` và checksums phụ thuộc publication/repository behavior của Gradle version. Không đoán rằng `publishToMavenLocal` tạo các checksum như remote/file-backed repo.

Kiểm tra:

```bash
jar tf build/libs/traceable-greeting-1.0.0.jar
java -cp build/libs/traceable-greeting-1.0.0.jar demo.release.Greeting
```

Stdout:

```text
Hello, Release!
```

**Không dùng `java -jar` với JAR này**: Java library plugin không tự sinh `Main-Class`, dù source có `main`. `java -cp <jar> demo.release.Greeting` mới là lệnh tương ứng.

## 7. Groovy DSL tương đương bài lab

Giữ nguyên Java source và test. Dùng `settings.gradle`:

```groovy
rootProject.name = 'traceable-greeting'
```

Dùng `build.gradle` thay Kotlin script:

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
}

group = 'com.example.training'
version = providers.gradleProperty('releaseVersion')
    .orElse('0.1.0-SNAPSHOT')
    .get()

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
    withSourcesJar()
    withJavadocJar()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

publishing {
    publications {
        mavenJava(MavenPublication) {
            from components.java

            pom {
                name = 'Traceable Greeting'
                description = 'Java library demonstrating traceable releases'
                url = 'https://example.org/traceable-greeting'
                licenses {
                    license {
                        name = 'The Apache License, Version 2.0'
                        url = 'https://www.apache.org/licenses/LICENSE-2.0.txt'
                    }
                }
                developers {
                    developer {
                        id = 'example-maintainer'
                        name = 'Example Maintainer'
                    }
                }
                scm {
                    connection = 'scm:git:https://example.org/traceable-greeting.git'
                    developerConnection =
                        'scm:git:ssh://git@example.org/traceable-greeting.git'
                    url = 'https://example.org/traceable-greeting'
                }
            }
        }
    }
    repositories {
        maven {
            name = 'LocalStaging'
            def lane = project.version.toString().endsWith('-SNAPSHOT')
                ? 'snapshots'
                : 'releases'
            url = layout.buildDirectory.dir("publication-repo/${lane}")
        }
    }
}

tasks.named('publish') {
    dependsOn tasks.named('check')
}
```

Groovy `"publication-repo/${lane}"` nội suy biến như GString. Chỉ chọn **một** DSL cho mỗi build, không trộn cú pháp hai DSL trong một script. Kết quả JAR/POM và stdout của Java giống phiên bản Kotlin.

## 8. Changelog: làm rõ thay đổi giữa các phiên bản

`CHANGELOG.md` không phải bản sao nguyên `git log`. Nó chọn những thay đổi có ý nghĩa với consumer, ghi migration/compatibility và tóm lược release.

Ví dụ `CHANGELOG.md` theo Keep a Changelog:

```markdown
# Changelog

Các thay đổi đáng chú ý được ghi theo từng release.

## [Unreleased]

### Added
- Bổ sung kiểm thử tên chứa ký tự Unicode.

## [1.0.0] - 2026-11-09

### Added
- API Greeting.message(String) hỗ trợ Java 17.
- Maven publication có binary, sources, Javadoc và POM.
- Kiểm thử bằng JUnit Jupiter.

[Unreleased]: https://example.org/traceable-greeting/compare/v1.0.0...HEAD
[1.0.0]: https://example.org/traceable-greeting/releases/tag/v1.0.0
```

Đây là **một mẫu release giả định**, không phải khẳng định repo ở `example.org` có release thật. Khi vận hành, dùng ngày, issue/PR links và source repository thực.

### 8.1. Các nhóm changelog hữu ích

- **Added**: chức năng, API, cấu hình mới.
- **Changed**: hành vi hoặc contract thay đổi.
- **Deprecated**: API sắp ngừng hỗ trợ, phương án thay thế.
- **Removed**: API bỏ đi và migration guide.
- **Fixed**: bug fix, regression test.
- **Security**: bản vá bảo mật theo chính sách disclosure.
- **Compatibility**: Java minimum, Gradle plugin compatibility, serialization/runtime requirements.

Không cần một heading trống ở mọi release. Nhưng nếu đổi public API không tương thích, nên ghi rõ breaking change, hướng dẫn nâng version và path migration.

### 8.2. Chốt changelog trước Git tag

1. PR đáng kể cập nhật `Unreleased` hoặc change fragments.
2. Reviewer xác định version MAJOR/MINOR/PATCH.
3. Release preparation chuyển các entries đã merge sang heading `[1.0.0]`, thêm migration notes.
4. Commit changelog/version changes sau review.
5. Tạo tag trên **commit chứa bản changelog đã chốt**.
6. Sau khi artifact publish thành công, phát hành release notes trỏ đúng tag/GAV.

Đừng tạo tag trên commit A, sửa changelog trong commit B, rồi để release artifact build từ A mà release notes tuyên bố nội dung từ B. Một số team dùng Conventional Commits để tự động đề xuất release notes; đó là công cụ hỗ trợ, **không thay thế review semantic compatibility**.

## 9. Git tags: annotated, signed, commit SHA

Git tag và Maven version là hai identity liên kết bởi policy:

```text
Git tag:        v1.0.0
Gradle version: 1.0.0
Maven GAV:      com.example.training:traceable-greeting:1.0.0
Changelog:      [1.0.0]
```

### 9.1. Lightweight và annotated tags

```bash
git tag v1.0.0
```

là lightweight tag. Annotated tag thích hợp cho release vì có tagger, message và timestamp:

```bash
git tag -a v1.0.0 -m "Release 1.0.0"
```

Signed tag khi có signing key/backend được cấu hình:

```bash
git tag -s v1.0.0 -m "Release 1.0.0"
git tag -v v1.0.0
```

Chọn **một** cách tạo tag theo policy. `git tag -v` chỉ verify cryptographic signature khi tag đã được ký và trust setup đúng; unsigned annotated tag không có signature để kiểm tra.

### 9.2. Kiểm tra trước và sau tạo tag

```bash
git status --short
git fetch --tags origin
git switch main
git pull --ff-only
git log -1 --format="%H %cI %s"
git diff --exit-code
git diff --cached --exit-code
```

Sau release approval, người có quyền thao tác:

```bash
git tag -a v1.0.0 -m "Release 1.0.0"
git show v1.0.0 --no-patch
git rev-parse v1.0.0^{commit}
git push origin v1.0.0
```

Các lệnh Git ở đây là **ví dụ vận hành**, không phải thao tác trên repository thật. Dùng branch/tag protection, tránh làm release từ working tree chưa commit. **Không force-move tag đã công bố** để thay code dưới cùng release name.

### 9.3. CI lấy version từ tag

Shell POSIX minh họa:

```bash
TAG=$(git describe --tags --exact-match)
VERSION=${TAG#v}

echo "tag=${TAG}"
echo "version=${VERSION}"
git rev-parse HEAD

./gradlew -PreleaseVersion="${VERSION}" clean check
```

Trong CI production cần validate tag theo parser/regex đủ chặt cho SemVer và repo policy, kiểm tra checkout chính xác full source SHA. Không chấp nhận bất kỳ chuỗi bắt đầu bằng `v` rồi bỏ ký tự đầu để tự publish stable. Git shallow clone có thể thiếu tag metadata; cấu hình fetch đúng source/tag.

### 9.4. Tag đã ký vẫn không ký JAR

Signed Git tag chứng minh một Git tag object được ký. Nó **không xác minh** SHA-256 của artifact hoặc ai đã chạy CI. Publication signing và release provenance cần được xác minh riêng. Nếu tag trỏ commit X nhưng publisher upload JAR từ commit Y, signed tag không thể tự phát hiện lỗi đó.

## 10. Invariant: chặn version drift trước publish

Một release phải đồng nhất:

```text
Git tag:         v1.0.0
Git SHA:         commit được tag trỏ tới
Gradle version:  1.0.0
POM version:     1.0.0
GAV:             com.example.training:traceable-greeting:1.0.0
Artifact path:   .../traceable-greeting/1.0.0/...
Changelog:       [1.0.0]
Release notes:   1.0.0
```

Nếu tag `v1.0.0` nhưng POM ghi `0.1.0-SNAPSHOT`, pipeline **phải fail**. Nếu một multi-project build dùng independent module versions, release manifest cần liệt kê từng module/tag/GAV rõ ràng. Đừng mặc định mọi subproject kế thừa root version nếu không cấu hình.

## 11. publishToMavenLocal, private Maven và Maven Central khác nhau

| Lệnh/hệ thống | Đích thực tế |
| --- | --- |
| `publishToMavenLocal` | Cache Maven local, thường `~/.m2/repository`. |
| `publish` trong lab | File-based Maven repo dưới `build/publication-repo`. |
| `publish` với private repository | Nexus/Artifactory hoặc Maven-compatible endpoint với credentials đúng. |
| Maven Central Portal | Public publishing flow có validation/signatures/namespace theo Sonatype. |

**Maven Central hiện hành không tương đương legacy OSSRH upload**. Tài liệu Gradle ghi nhận thay đổi protocol từ **30/06/2025**; dự án mới nên dùng Central Publisher Portal compatible plugin/flow, không copy endpoint OSSRH cũ. Khi release công khai, đối chiếu Sonatype docs hiện tại.

### 11.1. Metadata POM có ý nghĩa gì?

Maven Central có requirements cụ thể cho POM: name, description, URL, license, developers, SCM, namespace và chữ ký. Bài lab dùng `example.org` chỉ để minh họa, không publish công khai với những values giả định. `from(components["java"])` hỗ trợ tạo POM/module metadata của Java component; kiểm tra declared/resolved dependencies và scopes khi dự án có dependencies ngoài.

`versionMapping` trong Maven Publish cho phép chọn resolved versions trong metadata theo chiến lược; nếu dùng dynamic dependency versions, lock/verify và kiểm tra resolved graph trước release. Không giả định version catalog tự chốt mọi selected dependency version.

## 12. Tách snapshot, prerelease và stable repositories

`0.1.0-SNAPSHOT` có thể được publish theo chính sách snapshot (có thể dọn/ghi đè). `1.0.0-rc.1` là prerelease với version identity cụ thể. `1.0.0` là stable: **không được redeploy/overwrite**.

Trong lab, điều kiện `version.endsWith("-SNAPSHOT")` gửi snapshot vào thư mục `snapshots`, các version còn lại vào `releases`. **Đây không phải một bộ phân loại SemVer hoàn chỉnh**: `1.0.0-rc.1` cũng vào lane `releases` nếu chưa bổ sung quy tắc. Pipeline thật cần pre-release policy rõ nếu quản lý ba lanes riêng.

Repository manager nên chặn overwrite stable artifacts, giữ audit logs, tách release credentials với snapshot permissions, và bảo toàn retention. Nếu một stable version đã được consumer tải, việc đổi bytes tại cùng GAV gây mất truy vết và cache inconsistency.

## 13. Ký publication bằng Gradle Signing Plugin

Gradle có `signing` plugin tạo **OpenPGP signatures** cho publication. Ví dụ bổ sung trong build đã áp `maven-publish` và đã có publication `mavenJava`:

**Kotlin:**

```kotlin
plugins {
    `signing`
}

signing {
    val signingKey = providers.gradleProperty("signingKey").orNull
    val signingPassword = providers.gradleProperty("signingPassword").orNull
    useInMemoryPgpKeys(signingKey, signingPassword)
    sign(publishing.publications["mavenJava"])
}
```

**Groovy:**

```groovy
plugins {
    id 'signing'
}

signing {
    def signingKey = providers.gradleProperty('signingKey').orNull
    def signingPassword = providers.gradleProperty('signingPassword').orNull
    useInMemoryPgpKeys(signingKey, signingPassword)
    sign publishing.publications.mavenJava
}
```

Đây là **đoạn cấu hình mở rộng, không độc lập**: cần signing keys và publication thật. CI có thể dùng secret variables `ORG_GRADLE_PROJECT_signingKey` và `ORG_GRADLE_PROJECT_signingPassword`, không commit private key/password vào repository. Nếu policy yêu cầu signed artifact mà key không được cung cấp, release gate phải fail, không âm thầm publish unsigned.

**OpenPGP `.asc` khác signed Git tag**. Chữ ký JAR/POM giúp xác minh người ký bytes cụ thể, nhưng vẫn cần ghi test/CI/provenance evidence; một artifact được ký không tự chứng minh đã qua regression tests.

## 14. SHA-256 và release evidence

Một release evidence record nên gắn:

- Source repository URL, tag và **full Git commit SHA**.
- CI provider/run ID, builder identity, workflow revision.
- Gradle Wrapper version, JDK/toolchain vendor/version, OS/container digest.
- Dependency lock/verification records và SBOM nếu có.
- Test report IDs, security checks, approvals.
- Maven GAV, artifact file list, SHA-256 từng file, signatures.
- Repository publish URL, thời điểm release và changelog link.

Một JSON minh họa **cấu trúc cần điền bằng dữ liệu thật**:

```json
{
  "release": {
    "group": "com.example.training",
    "artifact": "traceable-greeting",
    "version": "1.0.0",
    "tag": "v1.0.0"
  },
  "source": {
    "commitShaSource": "git rev-parse HEAD"
  },
  "build": {
    "runIdSource": "CI_RUN_ID"
  },
  "artifact": {
    "file": "traceable-greeting-1.0.0.jar",
    "sha256Source": "hash of published bytes"
  }
}
```

Các field `...Source` trong mẫu chỉ nói **cách lấy dữ liệu**, không phải bằng chứng thật. Production CI phải ghi commit SHA, CI run ID và artifact hashes **thực tế**, lưu record ở nơi có retention và quyền sửa được kiểm soát.

### 14.1. Kiểm tra SHA-256 bằng công cụ có sẵn

Linux:

```bash
sha256sum build/libs/traceable-greeting-1.0.0.jar
```

macOS:

```bash
shasum -a 256 build/libs/traceable-greeting-1.0.0.jar
```

PowerShell:

```powershell
Get-FileHash -Algorithm SHA256 build/libs/traceable-greeting-1.0.0.jar
```

Không bịa một hash cố định cho JAR. Muốn so sánh artifact đã publish với binary được build/test, tính hash cả hai file thật và đối chiếu.

### 14.2. Chương trình Java 17 độc lập so sánh hai artifact

Tạo file `ReleaseHashCheck.java` tại root:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.util.Arrays;

public final class ReleaseHashCheck {
    private ReleaseHashCheck() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Provide two file paths");
        }

        byte[] first = Files.readAllBytes(Path.of(args[0]));
        byte[] second = Files.readAllBytes(Path.of(args[1]));

        byte[] a = MessageDigest.getInstance("SHA-256").digest(first);
        byte[] b = MessageDigest.getInstance("SHA-256").digest(second);

        System.out.println("identical=" + Arrays.equals(a, b));
    }
}
```

Biên dịch/chạy bằng JDK17:

```bash
mkdir -p hash-out
javac --release 17 -d hash-out ReleaseHashCheck.java
java -cp hash-out ReleaseHashCheck \
  build/libs/traceable-greeting-1.0.0.jar \
  build/publication-repo/releases/com/example/training/traceable-greeting/1.0.0/traceable-greeting-1.0.0.jar
```

Nếu artifact đã stage giống binary JAR của Java component:

```text
identical=true
```

Nếu khác, chương trình in `identical=false`; **dừng promote để điều tra**. Với JAR lớn, `Files.readAllBytes` dùng nhiều RAM, hệ thống thật nên streaming-hash. Kiểm tra hash equality không thay thế public key verification.

## 15. Consumer smoke test: resolve published GAV thay vì dùng source trực tiếp

Một build có thể publish POM/GAV sai dù project tests pass. Vì vậy hãy tạo **một Gradle build độc lập** chỉ khai báo Maven staging repository của bài lab:

```text
traceable-greeting/
└── consumer-check/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/java/demo/consumer/Main.java
```

**`consumer-check/settings.gradle.kts`:**

```kotlin
rootProject.name = "consumer-check"
```

**`consumer-check/build.gradle.kts`:**

```kotlin
plugins {
    id("application")
}

repositories {
    maven {
        url = uri("../build/publication-repo/releases")
    }
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.consumer.Main")
}

dependencies {
    implementation("com.example.training:traceable-greeting:1.0.0")
}
```

**`consumer-check/src/main/java/demo/consumer/Main.java`:**

```java
package demo.consumer;

import demo.release.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message(" Consumer "));
    }
}
```

Sau khi publisher đã chạy `publish` version 1.0.0:

```bash
./gradlew -p consumer-check -q run
```

Stdout:

```text
Hello, Consumer!
```

Consumer này phải có Settings riêng và không được thêm `mavenLocal()` trước staging repository, vì bản Maven Local cũ có thể làm test xanh giả. Nó thực sự import published GAV chứ không dùng `project(":...")` trong cùng source tree.

**Groovy consumer:**

```groovy
// consumer-check/settings.gradle
rootProject.name = 'consumer-check'
```

```groovy
// consumer-check/build.gradle
plugins {
    id 'application'
}
repositories {
    maven {
        url = uri('../build/publication-repo/releases')
    }
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
application {
    mainClass = 'demo.consumer.Main'
}
dependencies {
    implementation 'com.example.training:traceable-greeting:1.0.0'
}
```

Giữ nguyên `Main.java`. Ngoài stdout, nên kiểm tra resolved artifact digest trùng release manifest.

## 16. CI phát hành từ tag: ví dụ quy trình

Một luồng CI provider-agnostic:

```text
Protected tag v1.0.0
   -> checkout đúng commit/tag
   -> validate version/changelog/GAV uniqueness
   -> Gradle Wrapper/JDK/dependencies pinned
   -> clean check
   -> generate publication artifacts
   -> stage
   -> checksum/sign/SBOM/consumer smoke
   -> approval
   -> publish/promote exact verified bytes
   -> verify remote GAV/hash + announce release notes
```

Ví dụ shell chạy từ tag checkout:

```bash
set -eu

TAG=$(git describe --tags --exact-match)
VERSION=${TAG#v}

echo "release tag=${TAG}"
echo "artifact version=${VERSION}"
git rev-parse HEAD
git diff --exit-code

./gradlew --version
./gradlew -PreleaseVersion="${VERSION}" clean check publish
```

Đây là **script minh họa**, không phải CI production hoàn chỉnh. Cần validate toàn bộ SemVer/tag pattern, reject snapshot khi stable, kiểm tra release commit, approval, repository target, signing credentials và published SHA. Lệnh `publish` trong bài lab chỉ upload tới `build/publication-repo`.

### 16.1. Bảo vệ secrets

PR/fork có thể chạy build logic tùy ý nên không cấp stable publishing secrets cho jobs chưa được review. Giới hạn publish token ở protected tag/branch, approval và quyền repository tối thiểu. Không echo token, không ghi secrets vào `CHANGELOG.md`, POM, JSON provenance hay stdout.

### 16.2. Build một lần, promote đúng bytes

Nếu CI test JAR A rồi rebuild JAR B mới upload, chúng có thể khác vì dynamic dependencies, JDK, timestamps hay tasks phát sinh. Nên kiểm tra/stage chính output sẽ promote; giữa các jobs truyền artifacts qua storage có checksum, tránh rebuild lại bằng branch có thể thay đổi.

## 17. Reproducibility không tự sinh ra từ Git tag

Cùng source commit không bảo đảm output bytes như nhau nếu có:

- Dynamic dependencies/ranges hoặc repository metadata thay đổi.
- Gradle Wrapper/plugin/JDK versions khác.
- Archive file order, timestamps, generated build info.
- Environment variables, OS/path/timezone.
- Code generation/annotation processing inputs ngoài Git.
- Build cache hoặc artifact đã bị overwrite.

Gradle Jar task có hỗ trợ:

**Kotlin:**

```kotlin
tasks.withType<Jar>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

**Groovy:**

```groovy
tasks.withType(Jar).configureEach {
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

Những flag này cải thiện reproducible archives, **không chứng minh mọi build byte-identical**. Để release đáng tin, pin Gradle Wrapper, Java Toolchain, dependencies và plugins, dùng dependency locking/verification khi phù hợp, ghi SBOM và kiểm tra hashes thực nghiệm.

`Version catalog` quản lý requested versions nhưng không tự bảo đảm final resolved graph. `Dependency locking` giúp giữ resolved versions; `dependency verification` kiểm tra artifact integrity; `SBOM` liệt kê thành phần; `provenance` liên kết source/builder/output. Mỗi thứ phục vụ một mục đích khác.

## 18. Xử lý lỗi sau tag hoặc sau publish

| Khi nào | Chính sách đúng |
| --- | --- |
| Test fail trước tag | Sửa và commit mới, test lại. |
| Tag đã đẩy, upload lỗi mạng nhưng source/artifact không đổi | Có thể retry từ cùng tag/commit nếu policy/repo cho phép. |
| Tag đã đẩy nhưng code cần sửa | Tạo version/tag mới, không force-move tag public. |
| Staging sai metadata trước promote | Hủy/sửa staging theo policy và kiểm tra lại artifacts. |
| Stable `1.0.0` đã public nhưng có bug | Hotfix `1.0.1` và changelog/tag mới. |
| Cùng GAV nhưng artifacts có SHA khác | Dừng release và điều tra, không overwrite. |
| Signing verification fail | Dừng promote, xác minh keys/bytes và trust chain. |
| Consumer import GAV fail | Kiểm tra POM/.module/URL/permissions/cache/dependency graph. |

**Không force-push một release tag đang được người dùng tham chiếu**, cũng không thay JAR dưới stable GAV. Nếu fix cần code thay đổi, một version mới giữ nguyên sự thật lịch sử và giúp consumer rollback/upgrade có kiểm soát.

## 19. Bảng lỗi Gradle publishing thường gặp

| Triệu chứng | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Tag `v1.0.0` nhưng POM `0.1.0-SNAPSHOT` | Không truyền property/override version sai. | Kiểm tra Gradle `project.version`, tag và generated POM. |
| `publish` pass nhưng không thấy trên Maven Central | Chỉ upload file/private repository. | Kiểm tra publishing.repositories và Central Portal flow. |
| Maven Local có nhưng CI không tải được | `publishToMavenLocal` chỉ ghi cache dev. | Upload đúng staging/remote repo, test consumer sạch. |
| Source JAR hoặc Javadoc JAR thiếu | Chưa gọi `withSourcesJar`/`withJavadocJar`. | Cấu hình Java publication và verify files. |
| POM thiếu developer/license/SCM | Metadata chưa đủ. | Dùng metadata thật, validate theo repository requirements. |
| Build xanh mà tests chưa chạy | `publish` không được nối quality gates. | CI check/approval và `publish.dependsOn(check)` nếu phù hợp. |
| Central reject upload | Legacy protocol, thiếu signature/namespace/metadata. | Dùng Central Portal flow theo docs hiện hành. |
| Git tag không tìm thấy trong CI | Checkout shallow hoặc thiếu tags. | Fetch đúng release refs và commit. |
| Release notes khác source | Changelog sửa sau tag mà không có bản ghi hậu release. | Chốt changes trong tagged commit. |
| JAR same GAV khác checksum | Repo cho overwrite, rebuild drift, cache sai. | Chặn redeploy và xác minh provenance/hash. |
| Consumer test pass trên dev nhưng fail CI | Consumer đọc `mavenLocal()` hoặc dependency cache. | Dùng staging repo duy nhất, so digest. |
| `java -jar` lỗi no main manifest attribute | Đây là library JAR thiếu Main-Class. | Chạy bằng `java -cp <jar> demo.release.Greeting`. |
| Artifact signed tag verify được nhưng JAR signature fail | Git tag signing khác publication signing. | Verify riêng Maven signatures và public key. |
| Khác artifact bytes giữa hai runners | Compiler/plugin/inputs/timestamps không chốt. | Pin toolchain, locking, archive reproducibility, hashes. |
| Stable GAV đã tồn tại khi retry | Repository có immutability policy. | Kiểm tra release đã công bố hoặc tạo version mới. |

### 19.1. Gradle tasks để điều tra

```bash
./gradlew --version
./gradlew tasks --all
./gradlew -PreleaseVersion=1.0.0 test
./gradlew -PreleaseVersion=1.0.0 check
./gradlew -PreleaseVersion=1.0.0 generatePomFileForMavenJavaPublication
./gradlew -PreleaseVersion=1.0.0 generateMetadataFileForMavenJavaPublication
./gradlew -PreleaseVersion=1.0.0 publish
./gradlew -PreleaseVersion=1.0.0 publishToMavenLocal
```

Tên `generatePomFileForMavenJavaPublication` dựa trên publication name `mavenJava`. Với publication name khác, Gradle tạo task tương ứng.

### 19.2. Git tasks để điều tra

```bash
git tag --list "v*"
git show v1.0.0 --no-patch
git rev-parse v1.0.0^{commit}
git log -1 --format="%H %cI %s" v1.0.0
git status --short
```

`git tag -v v1.0.0` chỉ kiểm chứng cryptographic signature nếu tag thực sự đã ký và có trust setup tương ứng.

## 20. Checklist release

### Trước tag

- [ ] Version bump phù hợp public API contract; stable GAV chưa tồn tại.
- [ ] Changelog, migration/compatibility notes đã được review.
- [ ] Code đã merge, working tree sạch, commit SHA được ghi nhận.
- [ ] Gradle Wrapper/JDK/plugin/dependency versions được chốt.
- [ ] Test/quality/security gates theo policy pass.
- [ ] Credentials publish chỉ dành cho release job được phê duyệt.

### Trong build/staging

- [ ] Git tag, Gradle version, GAV/POM và changelog khớp nhau.
- [ ] CI checkout đúng tagged source commit.
- [ ] MavenPublication xuất bản binary, sources, Javadoc và metadata.
- [ ] SHA-256 được tính từ đúng artifact sẽ upload.
- [ ] Signing/SBOM/provenance được tạo và kiểm tra nếu policy yêu cầu.
- [ ] Consumer độc lập resolve GAV từ staging repository.
- [ ] CI run ID, source SHA, test reports và approvals được lưu.

### Sau publish

- [ ] Stable repository giữ GAV bất biến, không redeploy.
- [ ] Consumer tải lại artifact, đối chiếu SHA-256 và signature.
- [ ] Release notes link đúng tag, changelog, Maven GAV và commit.
- [ ] Evidence record có retention và quyền sửa được quản lý.
- [ ] Có hướng dẫn rollback/upgrade; hotfix phát hành version mới.

## 21. Bảng tra nhanh

| Muốn làm | Công cụ/cấu hình |
| --- | --- |
| Version từ CI vào Gradle | `-PreleaseVersion=1.0.0`, `providers.gradleProperty("releaseVersion")`. |
| Maven GAV | `group:artifact:version`. |
| Publish Java library | `java-library`, `maven-publish`, `MavenPublication.from(components["java"])`. |
| Thêm sources/Javadoc | `withSourcesJar()` và `withJavadocJar()`. |
| Tạo release tag | `git tag -a v1.0.0 -m "Release 1.0.0"`. |
| Ký Git tag | `git tag -s v1.0.0 ...` theo policy. |
| Ký publication | Gradle `signing`/OpenPGP và CI secrets. |
| Ghi thay đổi | `CHANGELOG.md` với `Unreleased`/release headings. |
| Thử Maven publication an toàn | File-based Maven repository dưới `build/`. |
| Publish vào local Maven cache | `publishToMavenLocal` — không phải public release. |
| Quality gate trước upload | `check` trong CI hoặc `publish.dependsOn(check)`. |
| Audit JAR bytes | SHA-256 và so staged/published copy. |
| Truy ngược GAV tới source | Tag, full commit SHA, CI run, artifact hashes trong evidence. |
| Test consumer thật | Build độc lập resolve đúng GAV từ staging repo. |
| Public Maven Central | Central Publisher Portal compatible flow, metadata/signature requirements. |
| Release bị lỗi sau public | Hotfix version mới, không overwrite artifact cũ. |

**Kết luận:** Quy trình phát hành có thể truy vết phải liên kết **version policy, changelog, Git tag, source commit, Maven GAV, Gradle publication, quality gates, artifact SHA-256/signature, CI evidence và repository immutability**. Bất kỳ liên kết nào bị thiếu sẽ giảm khả năng tái hiện hoặc điều tra lỗi. Hãy build từ source đã duyệt, test và stage đúng artifacts sẽ promote, rồi công bố một stable version bất biến; mọi sửa lỗi hậu phát hành đi qua version/tag mới.

### Tài liệu tham khảo

- [Gradle — Maven Publish Plugin](https://docs.gradle.org/current/userguide/publishing_maven.html): publications, POM, repositories, snapshots, Maven Local.
- [Gradle — Publishing Overview](https://docs.gradle.org/current/userguide/publishing_overview.html): publication model.
- [Gradle — Signing Plugin](https://docs.gradle.org/current/userguide/signing_plugin.html): OpenPGP signing, publications, in-memory keys.
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html): Java component.
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html): chốt resolved versions.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): kiểm tra dependency artifacts.
- [Git — git-tag](https://git-scm.com/docs/git-tag): annotated/signed tags.
- [Semantic Versioning](https://semver.org/): SemVer 2.0.0.
- [Keep a Changelog](https://keepachangelog.com/en/1.1.0/): changelog format.
- [Sonatype Central Portal](https://central.sonatype.org/): publishing flow hiện hành.
- [Sonatype — Publishing Requirements](https://central.sonatype.org/publish/requirements/): POM, signing, license, SCM.
