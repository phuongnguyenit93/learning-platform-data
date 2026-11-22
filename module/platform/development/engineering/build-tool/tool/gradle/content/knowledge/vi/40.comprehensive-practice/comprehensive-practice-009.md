# Kiểm chứng build tái lập, artifact độc lập và quản lý thông tin bí mật trong Gradle

Một dự án Java có thể báo **BUILD SUCCESSFUL** trên laptop và CI nhưng vẫn không đủ điều kiện để phát hành: hai lần build cùng source commit sinh JAR khác byte; bản ZIP chỉ chạy khi còn thư mục `build/` và Gradle cache trên máy tác giả; hoặc token dùng để publish vô tình bị chèn vào manifest, log, generated resources và artifacts được lưu công khai.

Bài **Thực hành tổng hợp** của chủ đề **Build Tool Gradle** tập trung ba mục tiêu:

1. **Build tái lập (reproducible build):** từ cùng source, cùng dependencies/toolchain và declared inputs, hai bản build sạch phải sinh artifact **byte-for-byte identical**.
2. **Artifact độc lập:** bản phân phối ứng dụng phải có launcher và runtime dependencies cần thiết để chạy **ngoài source tree, không gọi Gradle**. Với ví dụ này, máy đích vẫn phải có **Java 17 runtime**.
3. **Quản lý bí mật đúng ranh giới:** build, test và packaging không cần secrets; chỉ trusted publishing/deployment mới được nhận credentials qua secret store/Gradle typed APIs. Không đưa token vào JAR, ZIP, test reports hoặc caches.

Ta sẽ tạo repository **Gradle 9.9.0 + Kotlin DSL + Java 17 + JUnit Jupiter**, có module `:core` xuất thư viện và `:cli` tạo runnable distribution. Sau đó viết hai Bash scripts kiểm tra byte equality và ZIP isolation, thêm quy trình dependency locking/verification, CI GitHub Actions và publish security. Các file được ghi là **toàn bộ file** có thể dùng để tạo dự án. Các đoạn ghi **mảnh mở rộng** hoặc **chống mẫu** không được paste thêm nguyên xi vào file đã có.

**Phạm vi kiểm chứng:** một kết quả PASS với hai builds cùng máy là bằng chứng mạnh cho trường hợp đã thử, **không tự chứng minh** mọi JDK vendor/OS, mọi plugin, mọi artifact remote hoặc mọi tình huống bảo mật đều đúng. Những hạn chế này được ghi cụ thể ở từng bước.

## 1. Tiêu chí nghiệm thu và những thứ dễ nhầm

| Tiêu chí | Phép thử | Ý nghĩa khi PASS |
| --- | --- | --- |
| Java functionality | `:cli:test` với JUnit assertions | Business logic và generated resource hoạt động trên Gradle Test runtime |
| Artifact độc lập | Extract `cli-1.0.0.zip`, chạy `bin/cli` ở temp directory | Distribution không phụ thuộc source tree/Gradle |
| Reproducible bytes | Hai Git worktrees sạch + `--no-build-cache` + `cmp` | Các JAR/ZIP được chọn có bytes trùng |
| Output ownership | TaskProvider/`@OutputFile`/distinct directories | Gradle biết task nào sở hữu output, không ghi chồng |
| Locked versions | `gradle.lockfile` | Selected dependency versions được xác định |
| Verified dependency bytes | `verification-metadata.xml` | Artifact tải từ repositories khớp trusted hash/signature |
| Secret boundary | Read-only PR CI; protected publish job | Secrets không cấp cho code PR chưa tin cậy |
| Published artifact integrity | Hash file tải lại từ registry so với file đã duyệt | Registry không thay bytes của đối tượng đang xác minh |

Một số thuật ngữ **không đồng nghĩa**:

- `UP-TO-DATE`: Gradle bỏ qua action vì task inputs/outputs cục bộ chưa thay đổi.
- `FROM-CACHE`: Gradle khôi phục task outputs từ Build Cache.
- Configuration Cache: reuse configured task graph/configuration state, không phải artifact bytes.
- Reproducible: có thể **tự xây lại** từ source và cho artifact bytes bằng nhau.
- Artifact self-contained theo contract: có các runtime JARs/scripts cần thiết, nhưng có thể vẫn cần JRE/OS phù hợp.
- Supply-chain assurance: hash, provenance, signatures, trusted toolchain và source review; cần nhiều lớp chứ không chỉ một `sha256sum`.

Hai bản JAR **cùng hash nhưng cùng lỗi** vẫn không phải artifact chất lượng — cần cả tests và chạy thực tế. Hai lần `UP-TO-DATE` cũng chưa chứng minh task có thể tạo lại cùng bytes vì Gradle có thể không thực thi action lần hai.

## 2. Điều gì làm một build không tái lập?

Mô hình mong muốn:

```text
OutputBytes = F(
  committed source,
  reviewed Gradle scripts and plugin versions,
  pinned and verified dependency artifacts,
  compiler JDK/toolchain and options,
  explicitly declared task inputs,
  deterministic task implementations,
  stable archive metadata
)
```

Những hidden inputs phổ biến:

- `System.currentTimeMillis()`, `Instant.now()`, `UUID.randomUUID()`, random seed không cố định.
- Source file modified times, filesystem iteration order, ZIP/JAR entry timestamps.
- Absolute checkout path hoặc username/hostname/temp directory được ghi vào output.
- Build dùng JDK vendor/patch khác, nhưng chỉ đặt `sourceCompatibility = 17`.
- Dynamic versions như `1.+`, version ranges, mutable `-SNAPSHOT`.
- Compiler plugin/annotation processor không ổn định.
- Manifest chứa CI run ID, wall clock, token; generated code đọc environment variable không khai báo.
- Hai tasks ghi chung file/directory hoặc dùng raw path thiếu producer dependency.
- Task output từ cache che đi việc action tạo bytes khác nếu chạy từ đầu.

Điều cần đạt là **cùng declared inputs và toolchain trong phạm vi xác minh ⇒ cùng bytes**. Hai Git commits khác nhau có thể hợp lệ khi cho SHA-256 khác; đặc biệt nếu version/provenance thay đổi có chủ đích.

## 3. Gradle 9.x có reproducible archives mặc định

Theo tài liệu Gradle, từ **Gradle 9.0**, các `AbstractArchiveTask` như `Jar`, `Zip`, `Tar`, `War`, `Ear` mặc định:

- `isReproducibleFileOrder = true`: sắp thứ tự files trong archive ổn định.
- `isPreserveFileTimestamps = false`: không giữ filesystem mtime khác nhau theo lần build.
- Permissions trong archive mặc định cố định (directories `0755`, files `0644`).
- Có thể cấu hình `reproducibleFileTimestamp` cho một mốc được xác định sẵn nếu business cần, nhưng phải tôn trọng phạm vi timestamp của ZIP/TAR.

Ví dụ Gradle Kotlin DSL:

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

Đây vẫn là cấu hình hữu ích khi audit Gradle cũ hoặc muốn thể hiện cam kết trong code. **Không đủ để bảo đảm mọi artifact reproducible:** nếu nội dung `.class`, manifest, resource hoặc dependency JAR khác nhau thì output archive vẫn khác bytes.

Chống mẫu, **không ghép vào demo**:

```kotlin
tasks.jar {
    manifest {
        attributes["Built-At"] =
            System.currentTimeMillis().toString()
    }
}
```

Nếu cần build provenance, dùng commit SHA hoặc release version **được xác định, khai báo và review**, không embed volatile CI job time hay credential vào binary. Một commit SHA khác tạo artifact khác là đúng; cùng commit thì metadata phải ổn định.

Nguồn: [Gradle Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html) và [Gradle Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html).

## 4. Artifact độc lập là contract rõ ràng, không phải một danh từ chung

Có nhiều cấp:

| Artifact | Tính độc lập | Điều kiện |
| --- | --- | --- |
| Library JAR | Consumer có thể dùng trên JVM classpath | Cần runtime dependencies của library |
| Application JAR thường | Có app `.class`/resources | Chưa chắc `java -jar` được nếu thiếu Main-Class/dependencies |
| Application `distZip` | ZIP có launcher `bin/` và tất cả runtime JARs trong `lib/` | Cần Java runtime phù hợp trên máy đích |
| Fat/uber JAR | Gộp app và dependencies trong một JAR | Phải xử lý duplicate entries/services/signatures/metadata |
| Runtime image/installer | Có JVM modules/runtime hoặc native packaging | Cần build riêng theo OS/CPU, ví dụ `jlink`/`jpackage` |

Demo chọn **Gradle Application plugin `distZip`**. Người dùng unzip và chạy launcher, **không cần Gradle, source code hay dependency cache**. Nhưng ZIP **không tự đóng gói JDK**. Khi giao sản phẩm cần ghi rõ yêu cầu Java17 và các OS được hỗ trợ.

## 5. Cây thư mục mẫu

```text
repro-gradle-lab/
├── settings.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── core/
│   ├── build.gradle.kts
│   └── src/main/java/demo/core/Greeting.java
├── cli/
│   ├── build.gradle.kts
│   ├── src/main/java/demo/cli/Main.java
│   └── src/test/java/demo/cli/CliTest.java
├── scripts/
│   ├── verify-distribution.sh
│   └── verify-reproducible.sh
└── .github/workflows/reproducibility.yml
```

Yêu cầu: **Gradle Wrapper 9.9.0** từ nguồn tin cậy, JDK17 được Gradle phát hiện qua toolchain, Maven Central truy cập được cho JUnit dependencies. Bash/Git/`unzip`/`cmp`/`sha256sum`/`mktemp` cần cho scripts trên Linux/macOS/GitHub Ubuntu. Windows có thể build bằng PowerShell/`gradlew.bat`, chạy Bash scripts trong WSL/Git Bash hoặc CI Ubuntu.

### 5.1. `settings.gradle.kts` — toàn bộ file

```kotlin
rootProject.name = "repro-gradle-lab"
include(":core", ":cli")
```

Root project không áp dụng `base`/`java` plugin; không mặc định có task root `clean`. Lệnh thực hành sẽ gọi `:core:clean` và `:cli:clean` tường minh.

### 5.2. `core/build.gradle.kts` — toàn bộ file

```kotlin
import org.gradle.api.tasks.bundling.AbstractArchiveTask

plugins {
    `java-library`
}

group = "demo.repro"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

`java-library` là Gradle core plugin tạo JVM library variants và JAR. `group/version` cố định. `java.toolchain` pin Java **major 17** cho compilation, nhưng **chưa pin exact vendor và patch**. Nếu cần byte-identical cross-host nghiêm ngặt, phải cố định compiler image/toolchain distribution sâu hơn và đo trên các runners tương ứng.

### 5.3. `core/src/main/java/demo/core/Greeting.java` — toàn bộ file

```java
package demo.core;

public final class Greeting {
    private Greeting() {
    }

    public static String hello(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                "name must not be blank"
            );
        }
        return "Hello, " + name + "!";
    }
}
```

Business logic thuần Java17, không đọc clock, random, external file hoặc secret. Nó được compile thành `core-1.0.0.jar` để Java consumer dùng qua Gradle project dependency.

### 5.4. `cli/build.gradle.kts` — toàn bộ file

```kotlin
import org.gradle.api.DefaultTask
import org.gradle.api.file.RegularFileProperty
import org.gradle.api.provider.Property
import org.gradle.api.tasks.CacheableTask
import org.gradle.api.tasks.Input
import org.gradle.api.tasks.OutputFile
import org.gradle.api.tasks.TaskAction
import org.gradle.api.tasks.bundling.AbstractArchiveTask
import org.gradle.language.jvm.tasks.ProcessResources

plugins {
    application
}

group = "demo.repro"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.cli.Main")
}

dependencies {
    implementation(project(":core"))

    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

// Task tạo file độc lập với build clock/hostname/secrets.
@CacheableTask
abstract class GenerateBuildMetadata : DefaultTask() {

    @get:Input
    abstract val releaseVersion: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val file = outputFile.get().asFile
        file.parentFile.mkdirs()
        file.writeText(
            "releaseVersion=" + releaseVersion.get() + "\n",
            Charsets.UTF_8
        )
    }
}

// Version được đọc ở configuration phase, là input ổn định.
val fixedReleaseVersion = version.toString()

val generateBuildMetadata =
    tasks.register<GenerateBuildMetadata>("generateBuildMetadata") {
        releaseVersion.set(fixedReleaseVersion)
        outputFile.set(
            layout.buildDirectory.file(
                "generated/build-metadata/build-info.properties"
            )
        )
    }

// TaskProvider giữ file output và producer dependency.
tasks.named<ProcessResources>("processResources") {
    from(generateBuildMetadata)
}

tasks.withType<AbstractArchiveTask>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

Các điểm then chốt:

- `implementation(project(":core"))` cho Gradle tự chọn JVM library variant và producer task dependency. Không hardcode `core/build/libs/*.jar`.
- JUnit chỉ là `testImplementation`/`testRuntimeOnly`; không đóng gói test framework trong runtime ZIP.
- Custom `GenerateBuildMetadata` có `@Input` và `@OutputFile` rõ ràng. File được tạo từ `releaseVersion` ổn định, encoding UTF-8 và LF cố định; không có hidden time/env/file input.
- `@CacheableTask` chỉ là **cam kết về correctness**, không tự biến nondeterministic code thành deterministic.
- Generator **sở hữu** file `cli/build/generated/build-metadata/build-info.properties`.
- `processResources` **sở hữu** `cli/build/resources/main`; `from(generateBuildMetadata)` sao chép output của producer theo task dependency graph.
- Không cho generator ghi thẳng `build/resources/main`, vì trùng output ownership với `processResources` và có thể vô hiệu hóa caching.

### 5.5. `cli/src/main/java/demo/cli/Main.java` — toàn bộ file

```java
package demo.cli;

import demo.core.Greeting;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) throws IOException {
        Properties props = new Properties();

        try (InputStream input =
                Main.class.getResourceAsStream(
                    "/build-info.properties"
                )) {
            if (input == null) {
                throw new IOException(
                    "Missing build-info.properties"
                );
            }
            props.load(input);
        }

        String release = props.getProperty("releaseVersion");
        if (release == null) {
            throw new IllegalStateException(
                "Missing releaseVersion"
            );
        }

        System.out.println(
            Greeting.hello("Gradle")
                + " [version=" + release + "]"
        );
    }
}
```

Ứng dụng chỉ đọc generated metadata từ **runtime classpath**, không đọc project source files hay Gradle caches. Nếu ZIP thiếu `core.jar` hoặc `build-info.properties`, standalone smoke test ở phần sau sẽ thất bại.

### 5.6. `cli/src/test/java/demo/cli/CliTest.java` — toàn bộ file

```java
package demo.cli;

import demo.core.Greeting;
import org.junit.jupiter.api.Test;

import java.io.InputStream;
import java.util.Properties;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

public final class CliTest {

    @Test
    void greetingIsStable() {
        assertEquals(
            "Hello, Gradle!",
            Greeting.hello("Gradle")
        );
    }

    @Test
    void rejectsBlankName() {
        assertThrows(
            IllegalArgumentException.class,
            () -> Greeting.hello(" ")
        );
    }

    @Test
    void generatedResourceIsPresent() throws Exception {
        Properties props = new Properties();

        try (InputStream input =
                Main.class.getResourceAsStream(
                    "/build-info.properties"
                )) {
            assertNotNull(input);
            props.load(input);
        }

        assertEquals(
            "1.0.0",
            props.getProperty("releaseVersion")
        );
    }
}
```

Ba JUnit tests xác nhận function output, validation và resource trên Gradle test classpath. **Tests pass không đồng nghĩa ZIP runnable ngoài source tree**; ta phải kiểm thử thêm đường phát hành.

## 6. Tạo Gradle Wrapper và kiểm tra version

Nếu project chưa có Wrapper, dùng một trusted Gradle installation phù hợp để bootstrap:

```bash
gradle wrapper --gradle-version 9.9.0 --distribution-type bin
./gradlew --version
```

PowerShell:

```powershell
.\gradlew.bat --version
```

Gradle version phải là `9.9.0`; Java runtime/Gradle Daemon JVM cần đáp ứng compatibility matrix. Commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar`, `gradle/wrapper/gradle-wrapper.properties`.

Không tạo fake wrapper JAR hoặc đoán checksum. Nếu cấu hình `distributionSha256Sum`, lấy **SHA-256 chính thức** cho đúng Gradle distribution URL, xác minh và review. Wrapper/JAR/buildscripts là executable code; không chạy untrusted repository trên runner có production secrets.

## 7. Build sạch, test và quan sát outputs

Bash:

```bash
./gradlew :core:clean :cli:clean \
    :core:jar :cli:distZip :cli:test \
    --no-build-cache --no-configuration-cache \
    --console=plain

./gradlew :cli:run --quiet
```

PowerShell:

```powershell
.\gradlew.bat :core:clean :cli:clean :core:jar :cli:distZip :cli:test --no-build-cache --no-configuration-cache --console=plain
.\gradlew.bat :cli:run --quiet
```

**Stdout chính xác của `Main.main`:**

```text
Hello, Gradle! [version=1.0.0]
```

Gradle còn in task status, download progress, test/build summary tùy environment. Không coi toàn bộ terminal chỉ có một dòng trên.

Files dự kiến:

```text
core/build/libs/core-1.0.0.jar
cli/build/libs/cli-1.0.0.jar
cli/build/distributions/cli-1.0.0.zip
cli/build/generated/build-metadata/build-info.properties
cli/build/resources/main/build-info.properties
cli/build/reports/tests/test/index.html
cli/build/test-results/test/TEST-demo.cli.CliTest.xml
```

### Kiểm tra những entry quan trọng

```bash
jar tf core/build/libs/core-1.0.0.jar
jar tf cli/build/libs/cli-1.0.0.jar
unzip -l cli/build/distributions/cli-1.0.0.zip
```

Những entries cần có, **không phải toàn bộ output `jar tf`**:

```text
core jar:
    demo/core/Greeting.class

cli jar:
    demo/cli/Main.class
    build-info.properties

distribution ZIP:
    cli-1.0.0/bin/cli
    cli-1.0.0/bin/cli.bat
    cli-1.0.0/lib/cli-1.0.0.jar
    cli-1.0.0/lib/core-1.0.0.jar
```

Để xem file metadata:

```bash
unzip -p cli/build/libs/cli-1.0.0.jar \
    build-info.properties
```

Nội dung xác định, có một LF cuối dòng:

```properties
releaseVersion=1.0.0
```

## 8. Kiểm chứng ZIP chạy mà không cần source/Gradle

Tạo `scripts/verify-distribution.sh` — **toàn bộ file**:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo="$(cd "$(dirname "$0")/.." && pwd)"
archive="$repo/cli/build/distributions/cli-1.0.0.zip"

if [ ! -f "$archive" ]; then
  echo "ERROR: distribution ZIP not found" >&2
  exit 1
fi

tmp="$(mktemp -d)"
trap 'rm -rf -- "$tmp"' EXIT

unzip -q "$archive" -d "$tmp"
cd "$tmp/cli-1.0.0"

# Không gọi Gradle; không đọc source tree.
actual="$(./bin/cli)"
expected='Hello, Gradle! [version=1.0.0]'

if [ "$actual" != "$expected" ]; then
  printf 'ERROR: unexpected output: %s\n' "$actual" >&2
  exit 1
fi

printf '%s\n' 'PASS: distribution runs outside source tree'
```

Chạy:

```bash
chmod +x scripts/verify-distribution.sh
./gradlew :cli:distZip
./scripts/verify-distribution.sh
```

**Stdout xác định của script khi PASS:**

```text
PASS: distribution runs outside source tree
```

Phép thử trích ZIP vào directory mới và thực thi generated launcher. Không dùng Gradle, `build.gradle.kts`, `src` hoặc Maven caches khi chạy. **JDK/JRE17 vẫn là prerequisite**, nếu cần không cài Java thì phải tạo runtime image/installer riêng.

Windows PowerShell thực hành (lệnh một dòng, không cần Bash syntax):

```powershell
.\gradlew.bat :cli:distZip
$folder = Join-Path $env:TEMP "repro-cli-lab"
New-Item -ItemType Directory -Force -Path $folder | Out-Null
Expand-Archive -Path "cli\build\distributions\cli-1.0.0.zip" -DestinationPath $folder -Force
& (Join-Path $folder "cli-1.0.0\bin\cli.bat")
```

Dòng Java stdout vẫn là `Hello, Gradle! [version=1.0.0]`. Automation thật nên dùng temp directory độc lập mỗi run, tránh file cũ trong một folder cố định gây false PASS.

## 9. Vì sao `UP-TO-DATE` hoặc `FROM-CACHE` chưa chứng minh reproducibility?

Chống mẫu:

```bash
./gradlew :cli:distZip
./gradlew :cli:distZip
```

Ở lần hai, Gradle có thể ghi `:cli:distZip UP-TO-DATE` và **không thực thi** task action. ZIP giữ nguyên là một điều kiện quá yếu. Khi Build Cache bật, `FROM-CACHE` cũng có thể chỉ copy old result.

Kiểm chứng nghiêm hơn:
- Cùng committed Git SHA.
- Hai **fresh Git worktrees** ở hai paths khác nhau.
- Hai Gradle User Home độc lập.
- `--no-build-cache` để buộc không khôi phục output từ task output cache.
- `--no-configuration-cache` để tránh reuse configuration state trong phép đo.
- So **exact bytes** của các JAR/ZIP chọn để release.
- Chạy thêm functional ZIP smoke test ở ngoài source tree.

Configuration Cache không trực tiếp chứa JAR output; tắt nó ở đây chỉ để loại bớt biến số trong quá trình kiểm chứng.

## 10. Script so hai fresh worktrees và SHA-256

Tạo `scripts/verify-reproducible.sh` — **toàn bộ file**, dùng Bash/Ubuntu:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo="$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"

cleanup() {
  # Chỉ dọn worktrees mà chính script đã tạo.
  git -C "$repo" worktree remove --force "$tmp/a" \
    >/dev/null 2>&1 || true
  git -C "$repo" worktree remove --force "$tmp/b" \
    >/dev/null 2>&1 || true
  rm -rf -- "$tmp"
}
trap cleanup EXIT

# Worktrees từ committed HEAD, không từ dirty working tree.
git -C "$repo" worktree add --detach "$tmp/a" HEAD >/dev/null
git -C "$repo" worktree add --detach "$tmp/b" HEAD >/dev/null

if ! (
  cd "$tmp/a"
  GRADLE_USER_HOME="$tmp/gradle-home-a" ./gradlew \
    :core:jar :cli:jar :cli:distZip \
    --no-build-cache --no-configuration-cache \
    --console=plain > "$tmp/a.log" 2>&1
); then
  cat "$tmp/a.log" >&2
  exit 1
fi

if ! (
  cd "$tmp/b"
  GRADLE_USER_HOME="$tmp/gradle-home-b" ./gradlew \
    :core:jar :cli:jar :cli:distZip \
    --no-build-cache --no-configuration-cache \
    --console=plain > "$tmp/b.log" 2>&1
); then
  cat "$tmp/b.log" >&2
  exit 1
fi

for rel in \
  core/build/libs/core-1.0.0.jar \
  cli/build/libs/cli-1.0.0.jar \
  cli/build/distributions/cli-1.0.0.zip
do
  a="$tmp/a/$rel"
  b="$tmp/b/$rel"

  if ! cmp -s "$a" "$b"; then
    printf 'MISMATCH: %s\n' "$rel" >&2
    sha256sum "$a" "$b" >&2
    exit 1
  fi

  printf 'MATCH: %s\n' "$rel"
done

printf '%s\n' 'PASS: all selected artifacts are byte-identical'
```

Lệnh sử dụng:

```bash
chmod +x scripts/verify-reproducible.sh
git status --short
# Chỉ chạy sau khi source, Wrapper và scripts đã commit/review.
./scripts/verify-reproducible.sh
```

**Stdout của script khi PASS:**

```text
MATCH: core/build/libs/core-1.0.0.jar
MATCH: cli/build/libs/cli-1.0.0.jar
MATCH: cli/build/distributions/cli-1.0.0.zip
PASS: all selected artifacts are byte-identical
```

Script dùng `cmp` để xác minh bytes; nếu mismatch, nó in SHA-256 **thực** của hai files. Không có giá trị SHA-256 hex nào được suy ra trước khi chạy build với source/toolchain cụ thể.

Nếu cần hash dùng trong release metadata:

```bash
sha256sum core/build/libs/core-1.0.0.jar
sha256sum cli/build/libs/cli-1.0.0.jar
sha256sum cli/build/distributions/cli-1.0.0.zip
```

**Giới hạn quan trọng:** script dùng cùng OS/JDK environment, dù checkout paths và Gradle user homes riêng. PASS ở đây không chứng minh Java compiler từ vendor khác, Windows/macOS hay một build server độc lập tạo đúng bytes. Muốn assurance cao, chạy cùng source trên hai trusted independent runners với toolchains đã pin, so hash của artifact download thực.

`git worktree ... HEAD` kiểm tra **committed snapshot**, không bao gồm local edits chưa commit. Script chỉ xóa temporary directories/worktrees do `mktemp` và các lệnh trong chính nó tạo; không chạy `git clean -fdx` hoặc xóa global `~/.gradle` trên working tree của developer.

## 11. Task ownership và build graph đúng

| Producer | Output chính | Consumer |
| --- | --- | --- |
| `:core:jar` | `core/build/libs/core-1.0.0.jar` | `:cli` runtime project dependency |
| `:cli:generateBuildMetadata` | `cli/build/generated/build-metadata/build-info.properties` | `:cli:processResources` |
| `:cli:processResources` | `cli/build/resources/main` | `:cli:jar`, tests |
| `:cli:jar` | `cli/build/libs/cli-1.0.0.jar` | `:cli:distZip` |
| `:cli:distZip` | `cli/build/distributions/cli-1.0.0.zip` | CI consumer/release |

Chống mẫu:

```kotlin
// KHÔNG thêm vào project demo.
tasks.register("writeA") {
    doLast { file("build/shared/result.txt").writeText("A") }
}
tasks.register("writeB") {
    doLast { file("build/shared/result.txt").writeText("B") }
}
```

Hai tasks ghi cùng file nhưng không khai báo inputs/outputs; với parallel execution có thể có race, và Gradle không biết file thuộc producer nào. **Không “chữa” bằng cách tắt parallel builds** nếu design vẫn sai. Tách mỗi producer output và tạo một consumer/Copy/Sync task rõ ràng, nối bằng `TaskProvider.flatMap { it.outputFile }` hoặc `from(producerTaskProvider)`.

Provider chỉ cho Gradle suy ra task dependency khi chính nó mang **producer provenance**. Một generic provider chứa string path không tự tạo dependency edge.

## 12. Task Build Cache và non-deterministic action

Gradle Build Cache key của task dựa trên implementation, task action classpath, declared input property values/names và output property definitions. Một task cacheable phải có deterministic output cho cùng declared inputs.

Chống mẫu, không đưa vào production:

```kotlin
@TaskAction
fun generate() {
    outputFile.get().asFile.writeText(
        "builtAt=" + System.currentTimeMillis()
    )
}
```

Nếu vẫn đánh dấu `@CacheableTask` mà không khai báo time là input, task output có thể khác trên rebuild mới nhưng cache key không đổi; `FROM-CACHE` trả old bytes và che bug. **Cache không thể chữa missing input declaration hoặc nondeterministic behavior.**

Sau khi kiểm chứng reproducibility, mới đo hiệu năng:

```bash
./gradlew :cli:build --build-cache
./gradlew :cli:build --build-cache
```

Task có thể `UP-TO-DATE`, `FROM-CACHE` hoặc thực thi; không có outcome bất biến. Nếu custom task đọc file, dùng `@InputFile`/`@PathSensitive(PathSensitivity.RELATIVE)` khi thực sự đúng semantics để cache relocatable. **Không khai báo RELATIVE nếu output vẫn ghi absolute file path vào nội dung.**

## 13. Dependency version locking và checksum verification

Gradle pinning có nhiều lớp:

| Cơ chế | Cố định/xác minh cái gì? |
| --- | --- |
| Gradle Wrapper | Gradle distribution/version |
| Java toolchain | JDK major/compiler selection (cần pin vendor/patch thêm nếu strict) |
| Fixed dependency versions/BOM | Direct dependency selection và version constraints |
| `gradle.lockfile` | Resolved module versions của locked configurations |
| `verification-metadata.xml` | Trusted checksum/signature của external artifacts/metadata |
| `sha256sum` produced JAR/ZIP | Bytes **do project tạo ra** |

**Bước 1 — Dependency locking**, mảnh mở rộng thêm vào `cli/build.gradle.kts`:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Tạo/update lock state:

```bash
./gradlew :cli:test --write-locks
```

Gradle ghi `cli/gradle.lockfile` cho các configurations thực sự resolved. `:cli:test` **không đảm bảo resolve mọi configuration**. Commit reviewed lockfile và không để CI tự dùng `--write-locks` trong mỗi verification run. Locking giữ module **versions**, không đóng băng bytes của mutable `SNAPSHOT` hoặc một artifact bị republish cùng GAV.

**Bước 2 — Dependency Verification**, tạo baseline cần review:

```bash
./gradlew --write-verification-metadata sha256 :cli:test
```

Gradle tạo/cập nhật `gradle/verification-metadata.xml`. Phải review repositories, versions, hashes/signatures và trusted origin. Nếu bootstrap khi mirror đã bị xâm nhập, công cụ có thể ghi hash của artifact độc hại; đừng tự động chấp nhận mọi hash. Sau khi review, commit metadata.

**Bước 3 — Verify own artifact bytes:** Gradle dependency verification không tự xác minh `core.jar`/`cli.zip` do build tạo. Hai scripts reproducibility/distribution và release hash verification làm việc này.

Tài liệu: [Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html), [Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html).

## 14. Secrets không thuộc source/JAR/ZIP

Các secrets như registry password, GitHub PAT, signing private key, cloud credentials, API token và production database password có thể bị lộ qua nhiều đường:

- Hardcoded literal trong `build.gradle.kts`/`gradle.properties` được commit.
- Gradle task `println`/`logger.lifecycle`/debug/stacktrace.
- JAR manifest, `.properties` resource hoặc class file nhúng token.
- Test XML/HTML report/log thu thập environment details.
- Build Cache output nếu task tạo file chứa secret.
- Configuration Cache/task state nếu plugin giữ credential trong managed fields.
- Build Scan/Develocity publishing khi chưa kiểm soát redaction/privacy policy.
- CI `upload-artifact` glob quá rộng, bao gồm `.gradle`/`~/.gradle`/temp directories.

**Chống mẫu không được dùng:**

```kotlin
val password = "production-password"
val token = System.getenv("REPOSITORY_TOKEN")
println("Token: " + token)

tasks.jar {
    manifest {
        attributes("Repository-Token" to token)
    }
}
```

Chuyển một hardcoded token thành env var mà **vẫn embed nó trong manifest hoặc in log** không giải quyết rủi ro.

Bảo vệ theo thiết kế: **unprivileged build/test** tạo deterministic artifact trước; **privileged publish/deploy** nhận credential trong trusted job riêng để gọi external API/registry, không rewrite artifact bằng password.

## 15. Typed Gradle credentials API

Đây là **mảnh mở rộng**, không thuộc runnable demo. Nếu muốn publish `:core` lên private Maven repository, thay plugin block của `core/build.gradle.kts` thành:

```kotlin
plugins {
    `java-library`
    `maven-publish`
}
```

Thêm imports ở đầu file:

```kotlin
import org.gradle.api.credentials.PasswordCredentials
import org.gradle.api.publish.maven.MavenPublication
```

Và thêm publishing config:

```kotlin
publishing {
    publications {
        create<MavenPublication>("mavenJava") {
            from(components["java"])
        }
    }

    repositories {
        maven {
            name = "internalReleases"
            url = uri("https://repo.example.invalid/releases")
            credentials(PasswordCredentials::class)
        }
    }
}
```

`example.invalid` là **URL minh họa không hoạt động**, phải thay bằng trusted registry của tổ chức trước khi publish. Typed credentials được Gradle lookup từ properties có identity theo repository name:
- `internalReleasesUsername`
- `internalReleasesPassword`

Trên CI có thể cấp hai values qua environment variables:
- `ORG_GRADLE_PROJECT_internalReleasesUsername`
- `ORG_GRADLE_PROJECT_internalReleasesPassword`

Không commit credential values vào repository `gradle.properties`. Gradle hỗ trợ conditional credential requirement: repository credentials chỉ cần khi task thực sự truy cập repository đó. Typed API xử lý credential tốt hơn code tự đọc/in token, nhưng **không cho phép logging tùy tiện hoặc coi mọi cache là nơi lưu bí mật**.

Lệnh `./gradlew :core:publish` **chỉ hợp lệ sau khi** bổ sung Maven Publishing plugin, publication, URL và valid credentials thật. Nó không chạy thành công trên demo gốc hoặc fake URL.

## 16. Provider không có nghĩa secret đã được mã hóa

Ví dụ Gradle Provider:

```kotlin
val tokenProvider =
    providers.environmentVariable("PUBLISH_TOKEN")
```

Provider cho giá trị lazy; nó **không** tự:
- Cấm `println(tokenProvider.get())`.
- Ngăn bạn ghi token vào JAR/manifest/resource.
- Thay thế CI secrets store, identity/access control.
- Bảo đảm Configuration Cache/task state không capture token.
- Bảo đảm mọi plugin tự redacted values.

Với repository auth, ưu tiên `credentials(PasswordCredentials::class)`. Với cloud registry có OIDC, ưu tiên short-lived credentials. Với task publish/deploy, tránh đánh dấu side effects là cacheable output tasks chỉ để tiết kiệm thời gian.

### Configuration Cache

Gradle Configuration Cache có cơ chế encryption key và hướng dẫn bảo vệ `.gradle/configuration-cache` và `GRADLE_USER_HOME`. Một task configuration chứa secret có thể tạo sensitive state trong serialized data. Không upload cache directory hay key vào downloadable workflow artifacts; không chia sẻ privileged release cache cho PR untrusted. Khi cần explicit key cho CI, dùng `GRADLE_ENCRYPTION_KEY` từ secret store, **không commit key**.

## 17. Sentinel test với giá trị giả

Để xác minh artifact không phụ thuộc một environment variable **không được dùng**, thử:

```bash
DEMO_FAKE_TOKEN='FAKE_ONLY_NOT_A_SECRET' \
  ./gradlew :cli:distZip \
    --no-build-cache --rerun-tasks

sha256sum cli/build/distributions/cli-1.0.0.zip
```

Vì demo không đọc `DEMO_FAKE_TOKEN`, artifact bytes **không nên** đổi chỉ do biến này. So với một clean build không cấp biến và cùng compiler/dependencies; tốt nhất dùng fresh worktrees.

**Không dùng real secret làm chuỗi sentinel.** Shell history/process arguments/logs của chính phép quét có thể làm lộ nó. `grep` trực tiếp một compressed ZIP **không chứng minh** secret không nằm trong nested JARs: phải extract ZIP và các nested JARs rồi kiểm tra resources/manifest, đồng thời audit logs/caches/data flow.

## 18. GitHub Actions workflow CI không có publishing secret

File `.github/workflows/reproducibility.yml` — **toàn bộ YAML**, sau khi Wrapper và hai scripts đã commit:

```yaml
name: Gradle reproducibility and artifact isolation

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    timeout-minutes: 40

    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v6
        with:
          cache-provider: basic
          cache-read-only: ${{ github.event_name == 'pull_request' }}

      - name: Prepare Wrapper and scripts
        run: |
          chmod +x ./gradlew
          chmod +x ./scripts/verify-distribution.sh
          chmod +x ./scripts/verify-reproducible.sh

      - name: Fresh build and JUnit tests
        run: |
          ./gradlew :core:clean :cli:clean \
            :core:jar :cli:distZip :cli:test \
            --no-build-cache --no-configuration-cache \
            --console=plain --stacktrace

      - name: Run distribution outside source tree
        run: ./scripts/verify-distribution.sh

      - name: Compare independent artifact rebuilds
        run: ./scripts/verify-reproducible.sh

      - name: Upload JUnit reports
        if: ${{ always() }}
        uses: actions/upload-artifact@v7
        with:
          name: junit-reports-${{ github.run_id }}
          path: |
            cli/build/reports/tests/test/
            cli/build/test-results/test/
          if-no-files-found: ignore
          retention-days: 7

      - name: Upload verified distribution
        if: ${{ success() }}
        uses: actions/upload-artifact@v7
        with:
          name: cli-distribution-${{ github.run_id }}
          path: cli/build/distributions/cli-1.0.0.zip
          if-no-files-found: error
          retention-days: 14
```

Cơ chế bảo mật: PR build chỉ có `contents: read`, không có production secrets hay `packages: write`. `setup-gradle` quản lý Wrapper validation và Gradle User Home caching của CI, nhưng script two-worktree **tự tạo isolated user homes** và dùng `--no-build-cache`. GitHub cache hit không được coi là proof of reproducibility.

GitHub Actions artifact storage có thể tạo outer ZIP khi download; nếu xác minh phát hành, so hash của **file Gradle-generated `cli-1.0.0.zip` bên trong artifact**, không nhầm outer container với inner distribution.

Các action major tags dựa trên tài liệu hiện hành tháng 11/2026; production nên pin verified full commit SHA hoặc Actions dependency lockfile theo policy.

## 19. Trusted publish job tách khỏi PR build

**Mảnh YAML minh họa**, chưa runnable trên demo base vì chưa thêm `maven-publish`/registry thật:

```yaml
jobs:
  publish:
    if: startsWith(github.ref, 'refs/tags/v')
    runs-on: ubuntu-24.04
    environment: production
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'
      - uses: gradle/actions/setup-gradle@v6
        with:
          cache-provider: basic
          cache-read-only: true
      - run: chmod +x ./gradlew
      - name: Build and verify release
        run: |
          ./gradlew :core:jar :cli:distZip :cli:test \
            --no-build-cache --no-configuration-cache
      - name: Publish with scoped credentials
        env:
          ORG_GRADLE_PROJECT_internalReleasesUsername: ${{ secrets.RELEASE_USER }}
          ORG_GRADLE_PROJECT_internalReleasesPassword: ${{ secrets.RELEASE_PASSWORD }}
        run: ./gradlew :core:publish --no-build-cache
```

Một workflow thật cần `on.push.tags` hoặc release event, protected tag/approval rules, registry URL/permissions và MavenPublication hợp lệ. `packages: write` chỉ khi đích publish yêu cầu (ví dụ GitHub Packages); với external registry có thể không cần. Nếu cloud/registry hỗ trợ, ưu tiên OIDC/short-lived credentials hơn static secrets.

**Không dùng `pull_request_target` để checkout fork PR code rồi chạy Gradle với elevated credentials.** Build scripts và Wrapper đều là executable code. Theo Gradle Security Best Practices, released artifacts nên được dựng trong **trusted pristine ephemeral CI environment**, không phụ thuộc stale incremental/cached outputs; Build Cache vẫn có ích trong developer/non-publishing CI.

## 20. Artifact provenance, signing và hash sau publish

Một chuỗi phát hành đáng tin:

```text
Reviewed source commit / protected tag
    -> pinned and verified inputs / Gradle toolchain
    -> isolated clean build
    -> JUnit + reproducibility + standalone ZIP smoke test
    -> SHA-256 of the actual JAR/ZIP
    -> signing / attestation (nếu policy yêu cầu)
    -> authenticated registry publish
    -> download and compare published bytes
```

Phân biệt ba hashes:
1. **Dependency hash**: kiểm tra input artifacts do Maven/Gradle tải về.
2. **Build artifact hash**: đo `core.jar`, `cli.jar`, `cli.zip` từ build.
3. **Published artifact hash**: tải lại từ registry và so với file trusted CI đã tạo.

Signatures/provenance đưa identity/trust vào quá trình phân phối nhưng không thay thế reproducibility. Signatures có thể có nonce/timestamp khiến signed envelope hash khác dù **unsigned artifact** reproducible. Không so nhầm Maven POM/GitHub upload container với JAR/ZIP thật đang phát hành.

## 21. Debug nếu hashes khác nhau

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `core.jar` khác | JDK compiler patch/vendor, mtime, manifest | `javaToolchains`, `jar tf`, compare `.class`/manifest bytes |
| `core.jar` giống, `cli.jar` khác | Generated resource, JavaCompile, manifest | `unzip -p cli.jar build-info.properties` |
| Hai JAR giống, ZIP khác | Launcher scripts, ZIP metadata, permissions | Extract ZIP and compare entries/modes |
| Chỉ khác khi checkout path khác | Absolute path leakage | Search paths trong generated resources/classes |
| Khác mỗi khi build | Clock/random/hostname in outputs | Audit custom tasks, stable inputs |
| Build Cache hit nhưng rebuild khác | Cache che nondeterministic task | Fresh worktrees, `--no-build-cache` |
| `java -jar cli.jar` fail | Chưa tạo executable/fat JAR | Dùng Application `distZip` |
| Extracted ZIP fail | Thiếu lib/resource/JDK | `unzip -l`, `bin/cli`, JRE 17 |
| JUnit fail | Compiler/test/runtime source | `:cli:test --stacktrace`, reports |
| `gradle.lockfile` thiếu | Chưa `--write-locks` | Resolve configurations và commit lock |
| Verification metadata mismatch | Downloaded artifact không khớp hash | Điều tra nguồn, không tắt verification |
| Token hiện trong manifest | Secret embedded by buildscript | Remove, rotate secret, purge leaked artifact |
| Token xuất hiện trong log | Logging/debug/plugin code | Stop logging, revoke/rotate, restrict access |
| PR job cần token | Build/test bị lẫn publishing | Tách trust-level jobs |
| Publish 403 | Credentials/permission/URL sai | Typed API, privileged release job |
| Worktree script PASS code cũ | Source chưa commit | `git status --short`, review HEAD |
| Gradle root `clean` task missing | Root không apply base plugin | Dùng `:core:clean :cli:clean` |

Lệnh điều tra:

```bash
./gradlew --version
./gradlew javaToolchains
./gradlew :cli:dependencies --configuration runtimeClasspath
jar tf core/build/libs/core-1.0.0.jar
unzip -p core/build/libs/core-1.0.0.jar META-INF/MANIFEST.MF
unzip -p cli/build/libs/cli-1.0.0.jar build-info.properties
unzip -l cli/build/distributions/cli-1.0.0.zip
```

Khi hai archive hashes khác, extract từng file trong archive và so names/bytes. Nếu file entries giống nhưng archive bytes khác, xem ZIP metadata/order/timestamps/permissions/compression. **Sửa producer build logic**, không vá tay ZIP rồi coi đó là reproducible build.

## 22. Bài tập thực hành

**A — Run standalone ZIP.** Chạy `./scripts/verify-distribution.sh`, giải thích vì sao không cần source tree nhưng vẫn cần Java17.

**B — Rebuild độc lập.** Commit source/Wrapper/scripts, chạy `./scripts/verify-reproducible.sh`, giải thích ý nghĩa ba dòng `MATCH`.

**C — Cố tình gây non-reproducibility.** Tạm sửa `GenerateBuildMetadata.generate()` trong branch thực hành:

```kotlin
// CHỐNG MẪU, không giữ ở production:
file.writeText(
    "releaseVersion=" + releaseVersion.get()
        + "\nbuiltAt=" + System.currentTimeMillis() + "\n",
    Charsets.UTF_8
)
```

Commit branch test, chạy lại two-worktree script. Thông thường JAR/ZIP mismatch; nếu hai timestamps tình cờ trùng, thêm random UUID để làm ví dụ rõ hơn. Khôi phục code deterministic.

**D — Overlapping outputs.** Thử cho generator ghi thẳng `build/resources/main`, quan sát vấn đề output ownership; sửa lại `build/generated/...` và `processResources.from(taskProvider)`.

**E — Dependency locking và verification.** Thêm `dependencyLocking { lockAllConfigurations() }`, chạy `--write-locks`, sinh verification metadata SHA256 và review. Phân biệt pin module version với verify artifact bytes.

**F — Fake sentinel.** Thử `DEMO_FAKE_TOKEN=FAKE_ONLY_NOT_A_SECRET`, so artifacts với build không có sentinel; không dùng token production thật.

**G — CI fail propagation.** Tạo assertion JUnit fail có chủ đích trên branch test, xác minh job đỏ, report vẫn được upload và ZIP không được quảng bá là passed; khôi phục assertion.

## 23. Câu hỏi tự kiểm tra

**1. Byte-for-byte reproducibility là gì?** Các artifact có exact bytes giống nhau với cùng reviewed inputs/toolchain trong phạm vi đã thử.

**2. Vì sao `UP-TO-DATE` chưa đủ?** Task action có thể không chạy lại.

**3. Vì sao `--no-build-cache` quan trọng trong phép thử?** Ngăn restore output cũ thay vì sinh mới.

**4. Gradle 9.x mặc định ổn định gì cho archives?** File ordering, timestamps và permissions.

**5. `java.toolchain=17` có pin JDK vendor/patch không?** Chưa, cần pin sâu hơn nếu nghiêm ngặt.

**6. Vì sao `cli.jar` không tự là fat JAR?** Application plugin dùng distribution `lib/` cho dependencies.

**7. `distZip` có bundle JRE không?** Không.

**8. Vì sao generator có output riêng?** Để không chồng ownership với `processResources`.

**9. `@CacheableTask` có ép code deterministic không?** Không, trách nhiệm thuộc developer và kiểm chứng.

**10. Lockfile chứa gì?** Exact resolved versions của locked configurations.

**11. Dependency verification chứa gì?** Trusted checksum/signature của external artifacts và metadata.

**12. Hai cơ chế đó có verify project own JAR không?** Không, cần rebuild/hash.

**13. Provider có tự redact secret nếu gọi `println` không?** Không.

**14. Typed credentials tìm values theo đâu?** Repo identity, ví dụ `internalReleasesUsername`/`internalReleasesPassword`.

**15. Vì sao không cấp publish secret cho PR?** Untrusted Gradle code có thể đọc/exfiltrate secrets.

**16. Configuration Cache có thể chứa secret state không?** Có, cần protect cache/key và tránh capture.

**17. Hash trùng bảo đảm ZIP chạy không?** Không, cần standalone functional test.

**18. Signature có thay thế reproducibility không?** Không; hai lớp assurance khác nhau.

**19. Vì sao cần so inner ZIP sau GitHub artifact download?** Storage service có thể tạo outer archive với bytes khác.

**20. Release nên build ở môi trường nào?** Trusted, pristine, isolated runner từ reviewed source.

## 24. Checklist trước khi bàn giao artifact

- [ ] Wrapper scripts/JAR/properties trusted, checksum/version được review.
- [ ] Compiler/toolchain JDK17 được kiểm soát; pin vendor/patch nếu strict.
- [ ] Committed source và build scripts đúng revision định kiểm chứng.
- [ ] Fixed dependency versions và lock/verification metadata được review.
- [ ] Archive order/timestamps/permissions ổn định.
- [ ] Generated resources không chứa clock/random/absolute machine path/secret.
- [ ] Task inputs/outputs khai báo rõ, không overlapping outputs.
- [ ] Project dependency và TaskProvider giữ producer provenance.
- [ ] JUnit tests có assertions thật và được chạy.
- [ ] Core JAR, CLI JAR, distribution ZIP đúng paths/contents.
- [ ] ZIP chạy ngoài source tree qua launcher.
- [ ] Two fresh worktrees không dùng output cache cho bytes identical.
- [ ] Hashes đo từ file thực, không copy hash dự đoán.
- [ ] Nếu cần cross-platform assurance, có independent runners/JDKs.
- [ ] PR CI read-only, không có production secrets.
- [ ] Typed credentials chỉ được dùng khi publish thật.
- [ ] Không log/hardcode/embed secrets trong class/resource/manifest.
- [ ] Không upload Gradle User Home/Configuration Cache như artifact công khai.
- [ ] Sentinel scanning không dùng secret thật, xét cả nested archives.
- [ ] Released files được download/verify theo hash/provenance.
- [ ] Signing/approval/rollback policy rõ trước khi phát hành.

## 25. Tài liệu chính thức

- [Gradle — Working with Files / Reproducible Archives](https://docs.gradle.org/current/userguide/working_with_files.html).
- [Gradle — Best Practices for Security](https://docs.gradle.org/current/userguide/best_practices_security.html).
- [Gradle — Securing the Build Tool](https://docs.gradle.org/current/userguide/securing_build_tool.html).
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html).
- [Gradle — Build Cache Concepts](https://docs.gradle.org/current/userguide/build_cache_concepts.html).
- [Gradle — Debugging Build Cache Misses](https://docs.gradle.org/current/userguide/build_cache_debugging.html).
- [Gradle — Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html).
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html).
- [Gradle — Supported Repository Protocols: Credentials](https://docs.gradle.org/current/userguide/supported_repository_protocols.html).
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html).
- [Gradle — Build Environment](https://docs.gradle.org/current/userguide/build_environment.html).
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html).
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html).
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html).
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html).
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html).
- [GitHub Docs — Secrets](https://docs.github.com/en/actions/concepts/security/secrets).
- [GitHub Docs — Using Secrets in Actions](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).
- [GitHub Docs — Workflow Syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).
- [Gradle Actions — setup-gradle](https://github.com/gradle/actions/blob/main/docs/setup-gradle.md).
- [GitHub — checkout](https://github.com/actions/checkout), [setup-java](https://github.com/actions/setup-java), [upload-artifact](https://github.com/actions/upload-artifact).
