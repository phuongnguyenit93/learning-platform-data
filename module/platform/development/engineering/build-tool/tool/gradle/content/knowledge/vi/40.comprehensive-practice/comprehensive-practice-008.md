# Thực hiện nâng cấp Gradle với bằng chứng hành vi trước và sau

**Nhóm kiến thức:** Thực hành tổng hợp — Build Tool Gradle.  
**Bối cảnh thực hành:** Nâng Gradle Wrapper **8.14.6 → 9.9.0** của một dự án Java 17, giữ nguyên mã Java, JUnit và compiler toolchain, rồi đối chiếu hành vi trước/sau bằng bằng chứng tái lập.

## 1. “Nâng Gradle thành công” nghĩa là gì?

Đổi một dòng `distributionUrl` từ Gradle 8 sang Gradle 9 chỉ là **thay công cụ thực thi build**. Nó chưa chứng minh ứng dụng vẫn đúng. Ngay cả console `BUILD SUCCESSFUL` cũng không đủ nếu test task bị `NO-SOURCE`, không khám phá test nào, custom task bỏ qua output hoặc publication mất artifact.

Một kết luận nâng cấp đáng tin phải trả lời:

1. **Phiên bản và môi trường:** Wrapper thật sự dùng Gradle mục tiêu? Daemon chạy JDK tương thích? Java compiler/test launcher được chọn đúng?
2. **Chức năng:** Các tests có thực thi đủ, không bị skip? Ứng dụng có in/return đúng kết quả như trước?
3. **Artifact:** JAR, distributions, resource files, POM/Gradle Module Metadata có đủ những thành phần đã cam kết?
4. **Dependencies:** Resolved versions/variants có thay ngoài kế hoạch? Lockfiles và checksum verification có còn phù hợp?
5. **Build semantics:** Task dependencies, `UP-TO-DATE`/`FROM-CACHE`, configuration cache và incremental behaviors có hoạt động đúng?
6. **Chẩn đoán:** Deprecated APIs và compatibility issues nào đã được sửa, cái nào được ghi vào follow-up có owner?
7. **CI và rollback:** Các required jobs đã chạy qua? Nếu regression, có cách quay về bản build cũ mà không xóa unrelated source changes?

**Bài thực hành thực hiện một phép so sánh có kiểm soát:** cùng source commit, cùng JDK 17, cùng JUnit versions, cùng task requests và cùng project semantics; **biến thay đổi chủ yếu là Gradle distribution**. Nếu phải sửa code build logic để phù hợp Gradle9, ghi những sửa đó thành commit/đầu mục riêng thay vì đánh đồng một thay đổi Wrapper-only.

Mục tiêu không phải bắt mọi file log/JAR/HTML report giống nhau từng byte. Mục tiêu là xác định **invariants** có ý nghĩa đối với người dùng và chất lượng phát hành.

## 2. Chọn đường nâng cấp có chủ đích

Ví dụ này dùng:

| Thành phần | Trước | Sau | Vì sao |
| --- | --- | --- | --- |
| Gradle Wrapper | 8.14.6 | 9.9.0 | Kiểm major upgrade 8 → 9 |
| Gradle Daemon JVM | 17 | 17 | Giữ môi trường chạy build ổn định |
| Java compiler toolchain | 17 | 17 | Không vô tình đổi target bytecode |
| Java source | Không đổi | Không đổi | Cô lập thay đổi Gradle |
| JUnit Jupiter | 5.11.4 | 5.11.4 | Không đồng thời nâng test framework |
| JUnit Platform Launcher | 1.11.4 | 1.11.4 | Giữ test discovery dependencies nhất quán |
| Target program output | `UPGRADE_OK;sum=7` | Cùng giá trị | So hành vi chạy thực tế |
| JUnit tests | 3 pass | 3 pass | Không bỏ sót kiểm thử |
| Artifact JAR | Có hai classes bắt buộc | Có hai classes bắt buộc | Contract packaging không mất |

Theo [Gradle Release Notes](https://docs.gradle.org/current/release-notes.html), **Gradle 9.9.0 phát hành ngày 7/11/2026**. Đây là **bản mục tiêu được ghim cho bài học**, không phải lời khuyên luôn dùng một số phiên bản cố định ở mọi dự án hoặc mọi thời điểm.

Gradle 9.0 đã đưa vào breaking changes quan trọng: Gradle Daemon cần **JVM 17+**, một số Gradle public APIs bị xóa, custom `Test` task không còn ngầm kế thừa `test` source set; khi có sources nhưng không tìm thấy tests, một task `test` có thể fail theo mặc định. Sau Gradle 9.0, các releases 9.x lại có thêm thay đổi: phải đọc cả migration guide **9.0** và **9.x** tới 9.9.0.

**Tài liệu bắt buộc để đánh giá kế hoạch:** [Gradle 9 major upgrade](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html), [Gradle 9.x upgrades](https://docs.gradle.org/current/userguide/upgrading_version_9.html), [Gradle 8.x upgrades](https://docs.gradle.org/current/userguide/upgrading_version_8.html), [Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html).

### 2.1. Không gộp quá nhiều lần nâng vào một phép đo

Không nên đồng thời nâng Java11 → Java25, Gradle8 → Gradle9, Spring Boot3 → Boot4, Kotlin plugin, AGP, JUnit và toàn bộ dependency BOM mà không có lịch phân tách tác nhân. Các versions này có compatibility contracts khác nhau.

Nếu product bắt buộc nhiều nâng cấp cùng lúc, dùng migration staging:

- Baseline cố định.
- JVM/Gradle compatibility preflight.
- Wrapper-only trial.
- Plugin compatibility fixes, mỗi nhóm kèm tests.
- Library/platform version migration được review riêng.
- Full CI matrix và release staging.
- Ghi rõ **không thể quy lỗi cho Gradle riêng** nếu có nhiều variables đổi trong cùng run.

## 3. Trước khi sửa một byte: khai báo acceptance contract

Với demo, định nghĩa:

| Kiểm chứng | Giá trị kỳ vọng | Dấu hiệu failure |
| --- | --- | --- |
| `./gradlew --version` | Before 8.14.6; after 9.9.0 | Chạy Gradle system/Wrapper sai |
| Java runtime của thí nghiệm | JDK17 | Environment drift |
| `:compileJava` | PASS trên Java17 toolchain | Compiler/plugin compatibility |
| `:test` | Đúng 3 tests, không lỗi/skip | Test engine/discovery regression |
| `demo.Main` | `UPGRADE_OK;sum=7` | Hành vi ứng dụng đổi |
| `:jar` | Có `demo/Main.class` và `demo/Calculator.class` | Packaging regression |
| `runtimeClasspath` | Các lựa chọn version được hiểu rõ | Dependency resolution drift |
| `testRuntimeClasspath` | JUnit Jupiter/Launcher tương thích | Test framework drift |
| Lượt chạy không đổi | Tasks có thể `UP-TO-DATE` | Hidden inputs, outputs mất |
| Deprecations | Được ghi trước và phân loại sau | API sẽ bị loại bỏ/đã bị loại bỏ |
| CI | Required OS/JDK jobs PASS | Pipeline không tương thích |
| Rollback | Có thể khôi phục Wrapper cũ + PASS | Phương án dự phòng thiếu |

**Không ép binary hashes, task durations hoặc toàn bộ text logs giống nhau** chỉ vì muốn diff sạch. Chúng có thể chứa timestamp, filename path, metadata, elapsed time, Gradle version hoặc ZIP implementation details.

Bằng chứng mạnh nhất là **các tiêu chí có thể kiểm tự động**: stdout/application contract, số test thực chạy, required JAR entries, selected modules và CI exit codes.

## 4. Bản đồ hồ sơ chứng cứ

Tạo một thư mục nằm **ngoài `build/`**:

```text
evidence/
├── before/
│   ├── gradle-version.txt
│   ├── java-version.txt
│   ├── help.log
│   ├── build.log
│   ├── repeat.log
│   ├── app-output.txt
│   ├── jar-entries.txt
│   ├── test-results.xml
│   ├── runtime-deps.txt
│   └── test-deps.txt
└── after/
    ├── gradle-version.txt
    ├── java-version.txt
    ├── help.log
    ├── build.log
    ├── repeat.log
    ├── app-output.txt
    ├── jar-entries.txt
    ├── test-results.xml
    ├── runtime-deps.txt
    └── test-deps.txt
```

**Mỗi file trả lời câu hỏi riêng:**

- `gradle-version.txt`: Gradle **thực tế** của process.
- `java-version.txt`: Java CLI environment; đối chiếu thêm JVM trong `gradle-version.txt` nếu Daemon có override.
- `help.log`: build scripts/plugins có load được, deprecation warnings nào xuất hiện trong configuration.
- `build.log`: task graph, task failures, `test` và `jar` có chạy không.
- `repeat.log`: lần hai cùng inputs có bị làm lại không.
- `app-output.txt`: output chạy chương trình, được dùng làm functional oracle.
- `jar-entries.txt`: required classes/resources có trong JAR không.
- `test-results.xml`: số tests, passed/failed/errors/skipped và tên methods.
- `runtime-deps.txt`/`test-deps.txt`: selected dependency graph.

**Lưu ý provenance:** mỗi evidence directory phải gắn commit SHA, OS/JDK, Gradle Wrapper version, command và kết quả exit code. Trong doanh nghiệp, đừng công khai logs có repository URL/credentials/hostnames nếu chưa được policy cho phép.

## 5. Dựng demo Java 17 + Gradle Kotlin DSL

### 5.1. Project layout

```text
upgrade-proof/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
└── src/
    ├── main/java/demo/
    │   ├── Calculator.java
    │   └── Main.java
    └── test/java/demo/
        └── CalculatorTest.java
```

Cần JDK17, Gradle Wrapper thật do Gradle tạo, kết nối Maven Central hoặc approved mirror cho JUnit. Nếu chưa có Wrapper, có thể dùng một Gradle cài tạm để bootstrap:

```bash
gradle :wrapper --gradle-version 8.14.6 --distribution-type bin
```

Sau đó dùng **Wrapper** ở mọi bước. Commit `gradlew`, `gradlew.bat`, `gradle-wrapper.jar` và `gradle-wrapper.properties` từ nguồn chính thức, không tự dựng JAR giả.

### 5.2. `settings.gradle.kts`

```kotlin
rootProject.name = "upgrade-proof"
```

Giữ nguyên root project name ở cả before và after để JAR output path không bị đổi ngoài ý muốn.

### 5.3. `build.gradle.kts` đầy đủ

```kotlin
import org.gradle.jvm.tasks.Jar

plugins {
    application
}

group = "example"
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
    mainClass.set("demo.Main")
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    testLogging {
        events("passed", "failed", "skipped")
    }
}

tasks.withType<Jar>().configureEach {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

**Giải thích:**

1. `application` là Gradle core plugin, tránh thêm một third-party plugin chỉ để phục vụ bài nâng Gradle.
2. `java.toolchain` chọn JDK17 cho compilation; Gradle Daemon JVM có thể khác nếu được cấu hình nhưng ở bài này cũng dùng Java17.
3. `mainClass` là contract của application, không để Gradle tự đoán.
4. JUnit Jupiter `5.11.4` và Platform Launcher `1.11.4` cùng release family và được ghim; không dùng `latest.release` hoặc dynamic versions.
5. `useJUnitPlatform()` chỉ rõ Gradle test engine; không để task âm thầm không tìm thấy JUnit5 tests.
6. `withType<Test>().configureEach` cấu hình lazily các Test tasks.
7. `Jar` archive tasks được cài reproducible file order/timestamps để giảm noise khi so archive bytes; nó không bảo đảm mọi Gradle release tạo JAR byte-identical.
8. `mavenCentral()` chỉ dành cho dependencies, không thay buildscript/plugin repositories nếu project có plugin ngoài.
9. Không thay dependency coordinates, Java source hoặc build script trong lượt Wrapper-only trial.
10. Gradle `jar` là library/plain archive task; đừng tự mặc định nó có executable manifest giống Spring Boot `bootJar`.

### 5.4. `src/main/java/demo/Calculator.java`

```java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int sum(int a, int b) {
        return Math.addExact(a, b);
    }
}
```

`Math.addExact` trong Java17 ném `ArithmeticException` khi integer overflow, tạo edge case có thể test.

### 5.5. `src/main/java/demo/Main.java`

```java
package demo;

public final class Main {
    private Main() {
    }

    public static String message() {
        return "UPGRADE_OK;sum=" + Calculator.sum(3, 4);
    }

    public static void main(String[] args) {
        System.out.println(message());
    }
}
```

Stdout **chính xác từ chương trình** (một dòng với platform newline cuối):

```text
UPGRADE_OK;sum=7
```

Không cho timestamp, hostname hoặc số ngẫu nhiên vào demo contract, vì chúng làm baseline và after khác ngay cả khi code đúng.

### 5.6. `src/test/java/demo/CalculatorTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

final class CalculatorTest {

    @Test
    void addsPositiveValues() {
        assertEquals(7, Calculator.sum(3, 4));
    }

    @Test
    void addsNegativeValues() {
        assertEquals(1, Calculator.sum(-2, 3));
    }

    @Test
    void preservesOutputAndOverflowBehavior() {
        assertEquals("UPGRADE_OK;sum=7", Main.message());
        assertThrows(
            ArithmeticException.class,
            () -> Calculator.sum(Integer.MAX_VALUE, 1)
        );
    }
}
```

**Kỳ vọng:** JUnit Jupiter phát hiện **3 tests** và mỗi test PASS. Nếu Gradle báo `NO-SOURCE`, `SKIPPED` hoặc tạo XML có 0 tests, **không** xem đó là compatibility PASS.

### 5.7. Kiểm Java độc lập với Gradle

Để tách lỗi Java code khỏi Gradle build logic, có thể compile bằng `javac`:

Linux/macOS:

```bash
mkdir -p manual-classes
javac --release 17 -d manual-classes \
  src/main/java/demo/Calculator.java \
  src/main/java/demo/Main.java
java -cp manual-classes demo.Main
```

Windows PowerShell:

```powershell
New-Item -ItemType Directory -Force manual-classes | Out-Null
javac --release 17 -d manual-classes src/main/java/demo/Calculator.java src/main/java/demo/Main.java
java -cp manual-classes demo.Main
```

Kỳ vọng:

```text
UPGRADE_OK;sum=7
```

Đây chỉ là oracle Java runtime khi **không cần third-party dependency**; nó **không thay thế** việc chạy Gradle tests, package và dependency resolution.

## 6. Giai đoạn BEFORE: thu dữ liệu với Gradle 8.14.6

**Điều kiện:** chưa chỉnh Wrapper, mã nguồn và test dependencies ở trạng thái đã chọn, JDK17 được cài. Tạo branch/commit baseline để biết chính xác source revision.

### 6.1. Thu baseline bằng Bash

```bash
mkdir -p evidence/before evidence/after

./gradlew --version > evidence/before/gradle-version.txt 2>&1
java -version > evidence/before/java-version.txt 2>&1

./gradlew help --warning-mode=all --stacktrace \
  --no-configuration-cache --console=plain \
  > evidence/before/help.log 2>&1

./gradlew clean check jar --no-build-cache \
  --no-configuration-cache --warning-mode=all --console=plain \
  > evidence/before/build.log 2>&1

./gradlew check jar --no-build-cache \
  --no-configuration-cache --console=plain \
  > evidence/before/repeat.log 2>&1

java -cp build/classes/java/main demo.Main \
  > evidence/before/app-output.txt

jar tf build/libs/upgrade-proof-1.0.0.jar \
  > evidence/before/jar-entries.txt

cp build/test-results/test/TEST-demo.CalculatorTest.xml \
  evidence/before/test-results.xml

./gradlew dependencies --configuration runtimeClasspath \
  > evidence/before/runtime-deps.txt

./gradlew dependencies --configuration testRuntimeClasspath \
  > evidence/before/test-deps.txt
```

**Đây là các command cần chạy có kiểm exit code; không phải script đã thực thi.** Trong script automation thật dùng `set -euo pipefail` hoặc kiểm status sau từng lệnh. Nếu `clean check jar` fail, dừng ngay: không copy một XML/JAR cũ rồi báo baseline PASS. `grep ... || true` có thể dùng khi **chỉ lọc logs**, nhưng không bao giờ bọc lệnh build quan trọng bằng `|| true` để che failure.

### 6.2. Thu baseline bằng PowerShell

```powershell
New-Item -ItemType Directory -Force evidence/before | Out-Null
New-Item -ItemType Directory -Force evidence/after | Out-Null

.\gradlew.bat --version *> evidence/before/gradle-version.txt
java -version *> evidence/before/java-version.txt

.\gradlew.bat help --warning-mode=all --stacktrace --no-configuration-cache --console=plain *> evidence/before/help.log
if ($LASTEXITCODE -ne 0) { throw "Baseline help failed" }

.\gradlew.bat clean check jar --no-build-cache --no-configuration-cache --warning-mode=all --console=plain *> evidence/before/build.log
if ($LASTEXITCODE -ne 0) { throw "Baseline build failed" }

.\gradlew.bat check jar --no-build-cache --no-configuration-cache --console=plain *> evidence/before/repeat.log
if ($LASTEXITCODE -ne 0) { throw "Baseline repeat failed" }

java -cp build/classes/java/main demo.Main *> evidence/before/app-output.txt
if ($LASTEXITCODE -ne 0) { throw "Baseline Main failed" }

jar tf build/libs/upgrade-proof-1.0.0.jar *> evidence/before/jar-entries.txt
if ($LASTEXITCODE -ne 0) { throw "Baseline JAR inspection failed" }

Copy-Item build/test-results/test/TEST-demo.CalculatorTest.xml evidence/before/test-results.xml

.\gradlew.bat dependencies --configuration runtimeClasspath *> evidence/before/runtime-deps.txt
if ($LASTEXITCODE -ne 0) { throw "Baseline runtime dependencies failed" }

.\gradlew.bat dependencies --configuration testRuntimeClasspath *> evidence/before/test-deps.txt
if ($LASTEXITCODE -ne 0) { throw "Baseline test dependencies failed" }
```

PowerShell `*>` là redirection của tất cả streams; commands phù hợp PowerShell5+. Nếu shell/team standard khác, thay phần redirection cho đúng. Không đổ lỗi nâng Gradle chỉ vì Windows PowerShell gọi sai `./gradlew` thay vì `.\gradlew.bat`.

### 6.3. Phải xác nhận gì trước khi tiếp tục?

- `gradle-version.txt` có Gradle **8.14.6**, không phải một Gradle system version tình cờ.
- Java môi trường là **17**, Gradle Daemon JVM/toolchain phù hợp.
- `help.log` được tạo và deprecation warnings đã được đọc.
- `build.log` thể hiện `:test` thực thi và `:jar` được tạo.
- `test-results.xml` ghi **3 tests, 0 failures, 0 errors, 0 skips**.
- `app-output.txt` chứa `UPGRADE_OK;sum=7`.
- `jar-entries.txt` chứa `demo/Main.class` và `demo/Calculator.class`.
- `repeat.log` cho thấy những tasks không đổi có thể `UP-TO-DATE` (và đã kiểm output còn hợp lệ).
- Dependency graphs được chụp, không có artifact mới không giải thích được.
- Exit codes của **mọi command quan trọng** là 0.

**Nếu baseline chưa PASS, không nên nâng để “thử xem Gradle mới chữa được không”** khi mục tiêu bài là chứng minh upgrade không tạo regression. Sửa baseline trước hoặc ghi rõ failure đang có để phân biệt với lỗi newly introduced.

## 7. Đọc deprecations trước khi chuyển major

Gradle khuyến nghị chạy:

```bash
./gradlew help --warning-mode=all --console=plain
```

Khi được organization policy cho phép, `--scan` có deprecations view chi tiết. Nhưng Build Scan có thể chứa build metadata/environment, nên không mặc định publish từ repository nội bộ.

Phân loại:

| Nguồn cảnh báo | Cách xử lý |
| --- | --- |
| Build script dùng deprecated DSL | Sửa source đúng API mới |
| Plugin nội bộ dùng Gradle API cũ | Sửa custom plugin và thêm regression tests |
| Third-party plugin deprecated Gradle API | Nâng plugin theo compatibility matrix hoặc liên hệ upstream |
| Deprecation trong task config | Chuyển sang `tasks.register`/`named`/`configureEach` nếu liên quan |
| Legacy Java toolchain configuration | Dùng Gradle `javaToolchains`/managed properties phù hợp |
| Configuration cache problem | Sửa task model/Provider use, không chỉ tắt cache |
| Test framework classpath warning | Đối chiếu JUnit engine/Launcher/Gradle Test configuration |
| Resolution/variant warnings | Kiểm `dependencies`/`dependencyInsight` và metadata |

**Không tự động dùng `--warning-mode=none`** vì nó chỉ giấu warning, không đưa API đã bị xóa trở lại. Sau khi triage xong, có thể dùng `--warning-mode=fail` làm quality gate nếu team có chính sách zero deprecations; chưa nên bật khi baseline còn warnings không xử lý.

## 8. Nâng Gradle Wrapper hai lần

### 8.1. Bốn Wrapper files cần quản lý

```text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

`gradle-wrapper.jar` là executable code; cần kiểm integrity trước khi commit. `distributionUrl` là URL của Gradle distribution, còn `distributionSha256Sum` (nếu có) là checksum distribution. **Không nhầm SHA của Wrapper JAR với SHA của distribution ZIP.**

Nếu project đã có `distributionSha256Sum` tương ứng Gradle8, khi nâng sang9 phải thay bằng **checksum thật của Gradle9.9.0**, không giữ lại hash cũ. Có thể lấy official value từ:

```text
https://services.gradle.org/distributions/gradle-9.9.0-bin.zip.sha256
```

Không bịa SHA-256 chỉ để điền tài liệu; truy xuất và xác minh từ nhà phát hành. Nếu Wrapper task yêu cầu `--gradle-distribution-sha256-sum` do project đã có checksum, cung cấp **giá trị đã xác minh** theo tài liệu chính thức.

### 8.2. Lần thứ nhất: đổi distribution

Linux/macOS:

```bash
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin
```

Windows PowerShell:

```powershell
.\gradlew.bat :wrapper --gradle-version 9.9.0 --distribution-type bin
```

Lệnh ban đầu chạy bởi Gradle8.14.6 và cập nhật Wrapper configuration. Nó **có thể chưa cập nhật các scripts/JAR theo target**. Nếu lệnh bị checksum guard từ chối, dừng để bổ sung official target SHA thay vì xóa security control.

Xem `gradle/wrapper/gradle-wrapper.properties`, version trong URL phải ghim đúng **9.9.0**. Với Gradle9, Wrapper properties sử dụng format version **X.Y.Z**; tránh dùng `9.9` alias trong distribution URL.

### 8.3. Kiểm Gradle mới khởi động

```bash
./gradlew --version
```

Kỳ vọng banner là **Gradle 9.9.0**. Nếu lỗi download Gradle, proxy, certificate, checksum hoặc JDK Daemon, đó là lỗi setup/compatibility **trước khi** chạy application tests; xử lý riêng.

Không dùng một cold-run đang download distribution hàng trăm MB để làm performance benchmark đối chiếu warm-run của phiên bản cũ.

### 8.4. Lần thứ hai: đồng bộ Wrapper files

```bash
./gradlew :wrapper --gradle-version 9.9.0 --distribution-type bin
```

Lần thứ hai dùng Gradle9.9.0 để có scripts/JAR mới theo version này. Kiểm:

```bash
git status --short
git diff -- gradlew gradlew.bat gradle/wrapper/gradle-wrapper.properties
./gradlew --version
```

Binary `gradle-wrapper.jar` cần checksum integrity check; không cố dùng `git diff` như một text file. Có thể xác minh chính thức qua Gradle release checksums/Wrapper validation action.

**Lưu ý thực tế:** Gradle9.9.0 có hành vi giữ nhiều customized Wrapper properties khi regenerate. Nếu build cũ dùng `-all.zip` hoặc custom `networkTimeout`/`validateDistributionUrl`, kiểm file để không âm thầm đổi policy. Khi cần giá trị cụ thể, dùng Wrapper task options tương ứng.

### 8.5. Vì sao không dùng `latest`?

```bash
./gradlew :wrapper --gradle-version latest
```

Alias có thể thay version theo thời gian. Đối với bài cần evidence trước/sau **tái lập**, chỉ dùng exact target như 9.9.0; nếu muốn tự theo dõi releases, chạy một canary job riêng và ghi version được chọn.

## 9. AFTER: chạy lại chính workload trước nâng

Đừng chỉ chạy `help`. Phải chạy lại các tasks và ghi từng chứng cứ như trước.

### 9.1. Bash commands

```bash
./gradlew --version > evidence/after/gradle-version.txt 2>&1
java -version > evidence/after/java-version.txt 2>&1

./gradlew help --warning-mode=all --stacktrace \
  --no-configuration-cache --console=plain \
  > evidence/after/help.log 2>&1

./gradlew clean check jar --no-build-cache \
  --no-configuration-cache --warning-mode=all --console=plain \
  > evidence/after/build.log 2>&1

./gradlew check jar --no-build-cache \
  --no-configuration-cache --console=plain \
  > evidence/after/repeat.log 2>&1

java -cp build/classes/java/main demo.Main \
  > evidence/after/app-output.txt

jar tf build/libs/upgrade-proof-1.0.0.jar \
  > evidence/after/jar-entries.txt

cp build/test-results/test/TEST-demo.CalculatorTest.xml \
  evidence/after/test-results.xml

./gradlew dependencies --configuration runtimeClasspath \
  > evidence/after/runtime-deps.txt

./gradlew dependencies --configuration testRuntimeClasspath \
  > evidence/after/test-deps.txt
```

**Cần exit-code checks giống BEFORE.** Dùng `set -euo pipefail` cho script Bash thật hoặc CI steps tách nhau. Không tiếp tục copy artifact sau failed `check`/`jar`; một file cũ còn trên disk không có nghĩa target đã tạo thành công.

### 9.2. PowerShell commands

```powershell
.\gradlew.bat --version *> evidence/after/gradle-version.txt
java -version *> evidence/after/java-version.txt

.\gradlew.bat help --warning-mode=all --stacktrace --no-configuration-cache --console=plain *> evidence/after/help.log
if ($LASTEXITCODE -ne 0) { throw "Target help failed" }

.\gradlew.bat clean check jar --no-build-cache --no-configuration-cache --warning-mode=all --console=plain *> evidence/after/build.log
if ($LASTEXITCODE -ne 0) { throw "Target build failed" }

.\gradlew.bat check jar --no-build-cache --no-configuration-cache --console=plain *> evidence/after/repeat.log
if ($LASTEXITCODE -ne 0) { throw "Target repeat failed" }

java -cp build/classes/java/main demo.Main *> evidence/after/app-output.txt
if ($LASTEXITCODE -ne 0) { throw "Target Main failed" }

jar tf build/libs/upgrade-proof-1.0.0.jar *> evidence/after/jar-entries.txt
if ($LASTEXITCODE -ne 0) { throw "Target JAR inspection failed" }

Copy-Item build/test-results/test/TEST-demo.CalculatorTest.xml evidence/after/test-results.xml

.\gradlew.bat dependencies --configuration runtimeClasspath *> evidence/after/runtime-deps.txt
if ($LASTEXITCODE -ne 0) { throw "Target runtime dependencies failed" }

.\gradlew.bat dependencies --configuration testRuntimeClasspath *> evidence/after/test-deps.txt
if ($LASTEXITCODE -ne 0) { throw "Target test dependencies failed" }
```

Tất cả các bước này giả định bạn vẫn đang dùng **cùng Windows host/JDK17/source** với BEFORE. Nếu chuyển sang OS khác, không dùng thay đổi newline/classpath/timezone làm bằng chứng Gradle regression.

## 10. Đối chiếu bằng invariants thay vì text diff thuần túy

### 10.1. Program stdout

Bash:

```bash
diff -u evidence/before/app-output.txt \
  evidence/after/app-output.txt
```

Kỳ vọng exit code 0 và không có lines khác nhau. Kiểm thêm actual value:

```bash
cat evidence/after/app-output.txt
```

Expected output:

```text
UPGRADE_OK;sum=7
```

PowerShell:

```powershell
$before = (Get-Content evidence/before/app-output.txt -Raw).TrimEnd()
$after  = (Get-Content evidence/after/app-output.txt -Raw).TrimEnd()
if ($before -ne $after) { throw "Behavior changed" }
if ($after -ne "UPGRADE_OK;sum=7") { throw "Unexpected output" }
```

`TrimEnd()` chỉ hợp lý vì demo contract là **một dòng** và platform newline không mang nội dung. Với protocol binary hoặc output có meaningful trailing spaces, phải dùng comparator phù hợp để không che regression.

### 10.2. Test XML

`test-results.xml` có thể chứa timestamps, elapsed time và environment differences. Không so bytes toàn XML. Kiểm **logic counters và method names**:

```text
Test class: demo.CalculatorTest
Expected tests: 3
Expected failures: 0
Expected errors: 0
Expected skipped: 0
```

Đây là **oracle dự kiến**, không phải output XML đã được thực thi. Một JUnit publisher hoặc XML parser trong CI nên fail khi report missing/zero tests, không chỉ xét Gradle status.

### 10.3. JAR entries

Bash:

```bash
grep -Fx "demo/Main.class" evidence/before/jar-entries.txt
grep -Fx "demo/Calculator.class" evidence/before/jar-entries.txt

grep -Fx "demo/Main.class" evidence/after/jar-entries.txt
grep -Fx "demo/Calculator.class" evidence/after/jar-entries.txt
```

Khi cần diff:

```bash
sort evidence/before/jar-entries.txt > evidence/before/jar-sorted.txt
sort evidence/after/jar-entries.txt > evidence/after/jar-sorted.txt
diff -u evidence/before/jar-sorted.txt evidence/after/jar-sorted.txt
```

**Không buộc Gradle9 tạo cùng ZIP hash** nếu contract của bạn chỉ cần classes/manifest semantics; hash có thể đổi do archive implementation/metadata. Nếu project hứa reproducible artifact bytes, khi ấy bitwise comparison là một gate riêng với toolchain/build environment được cố định rất chặt.

### 10.4. Dependency graph

```bash
diff -u evidence/before/runtime-deps.txt \
  evidence/after/runtime-deps.txt

diff -u evidence/before/test-deps.txt \
  evidence/after/test-deps.txt
```

Báo cáo văn bản có thể đổi format. Đọc **resolved modules/versions** thực sự. Nếu JUnit modules bị chọn version khác, chạy:

```bash
./gradlew dependencyInsight --dependency junit-jupiter \
  --configuration testRuntimeClasspath

./gradlew dependencyInsight --dependency junit-platform-launcher \
  --configuration testRuntimeClasspath
```

Kiểm version được request và selected, BOM/constraints/lockfile effects. Đừng nâng JUnit version trong cùng lượt Wrapper-only rồi không còn phân biệt nguyên nhân thay đổi.

### 10.5. Archive checksum

```bash
sha256sum build/libs/upgrade-proof-1.0.0.jar
```

PowerShell:

```powershell
Get-FileHash build/libs/upgrade-proof-1.0.0.jar -Algorithm SHA256
```

Hash bằng nhau là evidence mạnh về bytes dưới điều kiện đó. Hash khác **không đủ** để kết luận functional regression. Xem JAR entries, manifest, classes, timestamps/ZIP metadata và required public API.

## 11. Task outcomes và hành vi Gradle incremental

| Outcome | Ý nghĩa | Liên quan nâng cấp |
| --- | --- | --- |
| `UP-TO-DATE` | Inputs/outputs không đổi nên Gradle skip action | Cần verify outputs vẫn hợp lệ |
| `FROM-CACHE` | Task outputs được restore từ build cache | Không có nghĩa action đã chạy |
| `NO-SOURCE` | Task không có sources phù hợp | Đối với test required cần xem lại |
| `SKIPPED` | Bỏ action do predicate/disabled/flags | Không coi required tests đã chạy |
| `FAILED` | Task lỗi | Không chấp nhận PASS |
| Không có suffix | Task action thường chạy | Kiểm behavior/output chứ không chỉ số tasks |

**Mẫu kiểm tốt:**

1. `clean check jar --no-build-cache --no-configuration-cache` để có evidence execution mới.
2. `check jar --no-build-cache --no-configuration-cache` không clean để quan sát `UP-TO-DATE`.
3. Thay **một** input và quan sát invalidation.
4. Khôi phục input, kiểm artifact behavior.
5. Kiểm build cache/configuration cache **ở luồng riêng**, sau khi chức năng đã PASS.

Không dùng `--rerun-tasks` khi bạn định đo up-to-date behavior vì flag ép chạy và phá phép thử. Ngược lại, có thể dùng flag khi muốn debug code path của `@TaskAction` bị skip.

### 11.1. Controlled input change

Trong một sandbox branch:

- Đổi literal ở `Main.message()` từ `UPGRADE_OK;sum=` sang `UPGRADE_CHANGED;sum=`.
- Chạy `./gradlew check jar --no-build-cache --no-configuration-cache`.
- Test `preservesOutputAndOverflowBehavior()` phải **FAIL**, vì kỳ vọng vẫn là output cũ.
- Đây là **negative control** để chứng minh JUnit có thể phát hiện regression.
- Sau đó có thể đổi test expectation theo contract mới để minh họa migration có chủ đích, nhưng **khôi phục lại source/test về baseline trước khi chốt PR chỉ nâng Gradle**.

Nếu test không fail sau controlled source change, kiểm test discovery, stale outputs, task graph và source set wiring; đừng chấp nhận “build nhanh hơn” khi tests đã mất khả năng phát hiện regression.

## 12. Breaking changes Gradle9 cần kiểm trong project thực

### 12.1. Gradle Daemon cần Java17+

Một CI runner vẫn dùng JVM11 làm Gradle Daemon có thể không chạy được Gradle9, dù build đã cấu hình Java toolchain17 để compile application. Nâng **Daemon JVM** hoặc cấu hình JVM criteria/`org.gradle.java.home` hợp lệ; không nhất thiết đổi compile target.

Kiểm:

```bash
java -version
./gradlew --version
./gradlew -q javaToolchains
```

CLI Java17 không tự bảo đảm Gradle Daemon Java17 nếu có explicit override.

### 12.2. Custom `Test` task không còn tự nhận test source set

Trước Gradle9, một `Test` task custom có thể nhờ deprecated default convention mà tự dùng `test` source set. Gradle9 đã bỏ convention này.

**Anti-pattern:**

```kotlin
tasks.register<Test>("otherTest") {
    useJUnitPlatform()
}
```

Task có thể không chạy tests mà bạn tưởng. **Ví dụ cấu hình tường minh**:

```kotlin
val testSourceSet = the<SourceSetContainer>().named("test")

tasks.register<Test>("otherTest") {
    testClassesDirs = testSourceSet.get().output.classesDirs
    classpath = testSourceSet.get().runtimeClasspath
    useJUnitPlatform()
}
```

Đoạn này là **snippet minh họa riêng**, không nằm trong build.gradle.kts của demo. Nó cố tình chạy **cùng test source set** để minh họa migration; trong production, dùng Gradle JVM Test Suites hoặc dedicated integration-test source set để không lặp tests không cần.

### 12.3. Test sources tồn tại nhưng no tests discovered

Gradle9 có check mới: khi test sources hiện hữu nhưng chạy `test` không discover tests, task có thể fail theo mặc định. Điều này thường phát hiện thiếu JUnit engine, sai test framework, hoặc source set config lỗi.

Không “chữa” bằng:

```kotlin
tasks.withType<Test>().configureEach {
    failOnNoDiscoveredTests = false
}
```

trừ khi task được policy cho phép zero tests và có review. Với required unit tests, để fail là đúng và cần sửa JUnit `useJUnitPlatform()`, launcher/engine, source set hoặc filters.

### 12.4. `Project.exec` và `Project.javaexec` bị xóa

Các build scripts/plugins cũ có thể gọi `project.exec`/`project.javaexec`/script-level equivalents. Gradle9 đã loại bỏ những helpers này.

**Hướng thay thế:**

- Nếu process invocation là một task riêng, dùng typed `Exec` hoặc `JavaExec`.
- Trong custom task type, dùng injected `ExecOperations`.

Snippet Kotlin DSL minh họa:

```kotlin
import javax.inject.Inject
import org.gradle.api.DefaultTask
import org.gradle.api.tasks.TaskAction
import org.gradle.process.ExecOperations

abstract class PrintGitVersion @Inject constructor(
    private val execOperations: ExecOperations
) : DefaultTask() {

    @TaskAction
    fun run() {
        execOperations.exec {
            commandLine("git", "--version")
        }
    }
}

tasks.register<PrintGitVersion>("gitVersion")
```

Đây là **snippet phụ thuộc `git` trên PATH**, chỉ in version và không có declared output; không phải production cacheable task. Đừng thực hiện I/O/process commands trong configuration phase chỉ để tránh nâng plugin API.

### 12.5. Gradle9.x còn có thay đổi riêng

Không chỉ đọc bản migration 9.0.0: các Gradle9.x releases có thể thay behavior của Kotlin DSL compilation, diagnostics/Problems API, Wrapper properties, Test/JUnit filtering, configuration cache và publishing.

Trong một plugin/monorepo, rà:

- Embedded Kotlin/Groovy versions và Kotlin Gradle Plugin compatibility.
- Java/Scala/Groovy compiler & annotation processors.
- Gradle `ValidatePlugins` và injected Gradle APIs.
- Changes to `assemble`/`archives`/publication variants.
- JSpecify nullability và methods mới final trong Gradle public API.
- Project directories, build output location và stale outputs.
- TestNG/JUnit engine selection và test discovery.
- Configuration cache unsupported listeners/state capture.
- Deprecated APIs trong third-party plugins.
- CI tooling/IDE versions khi import Gradle9 projects.

Không giả định mọi dự án gặp mọi thay đổi; chọn checks liên quan đúng plugins/tasks của bạn và đọc actual stacktrace/deprecation evidence.

## 13. Triaging một build đỏ sau nâng

| Giai đoạn fail | Dấu hiệu | Chỗ cần điều tra |
| --- | --- | --- |
| Wrapper/download | ZIP, network, TLS, SHA mismatch | Distribution URL, official checksum, mirror/proxy |
| JVM startup | Unsupported class file/JVM requirement | Gradle Java compatibility matrix |
| Settings/plugin resolution | Plugin not found, missing project directory | `settings.gradle.kts`, `pluginManagement` |
| Script evaluation | Unresolved reference/NoSuchMethodError | Gradle removed APIs, DSL/plugin version |
| Dependency resolution | No matching variant/version conflict | Attributes/constraints/lockfiles/repositories |
| Java compile | Compiler/toolchain error | JDK17, compiler options, source/ABI |
| `Test` | 0 tests, engine error, failOnNoDiscoveredTests | Source sets, JUnit engine/launcher, `useJUnitPlatform` |
| Custom task | Output missing, implicit dependency error | Declared inputs/outputs, TaskProvider wiring |
| `jar`/`assemble` | Artifact missing/changed | Archive tasks, Gradle9 artifact semantics |
| `publish` | POM/metadata/variant mismatch | Consumer contract, Gradle Module Metadata |
| Configuration cache | Incompatible task/plugin state | Gradle problems report and task model |
| CI | Old JDK/Gradle wrapper path/image issue | CI runner versions/shell/caching |

Khi fail:

1. Ghi exact command, environment, stacktrace và Gradle version.
2. Dùng `./gradlew help --warning-mode=all --stacktrace` để xem lỗi có xuất hiện trước task execution không.
3. Chỉ chạy một task bị lỗi, ví dụ `./gradlew test --stacktrace --info`.
4. Kiểm build script/plugin code frame đầu tiên ngoài Gradle internals.
5. Đối chiếu migration docs với API/thay đổi tương ứng.
6. Sửa **một nguyên nhân** rồi test lại command hẹp và full gate.
7. Lưu before/after logs và regression test.
8. Không dùng `-x test`, `ignoreFailures=true` hay `--warning-mode=none` để che incompatibility.

### 13.1. Configuration cache khác build cache

- **Configuration cache** tái sử dụng task graph/configuration state qua các invocations; code configuration có thể không chạy lại.
- **Build cache** tái sử dụng task outputs khi inputs/implementation fingerprint khớp và task cacheable.
- **Up-to-date checking** dùng state/output hiện tại để bỏ task action.
- **Incremental compilation** có thể compile ít classes hơn dù `compileJava` thực thi.

Các cơ chế tác động ở các lớp khác nhau. Một report `FROM-CACHE` không chứng minh `@TaskAction` đã chạy trong target Gradle version. Khi cần compare actual execution, tắt build cache ở lượt clean run.

## 14. CI job để kiểm đúng Wrapper trong pull request

Workflow GitHub Actions cho chính demo:

```yaml
name: Gradle upgrade verification

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-24.04
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v6

      - name: Show versions
        run: |
          ./gradlew --version
          java -version

      - name: Check and package
        run: |
          ./gradlew clean check jar \
            --no-build-cache --no-configuration-cache \
            --warning-mode=all --console=plain

      - name: Check program output
        run: |
          actual="$(java -cp build/classes/java/main demo.Main)"
          test "$actual" = "UPGRADE_OK;sum=7"

      - name: Upload JUnit XML
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: gradle-upgrade-tests
          path: |
            build/test-results/test/*.xml
            build/reports/tests/test/**
          if-no-files-found: error
```

Đây là **workflow mẫu**, chưa phải bằng chứng một CI run đã diễn ra. Các actions major versions cần được kiểm tương thích runner/organization và có thể được pin commit SHA theo security policy.

**Tại sao chạy `./gradlew`?** Mục tiêu PR là kiểm chính **Wrapper mới**. Nếu CI setup một Gradle system version rồi gọi `gradle`, job có thể pass mà Wrapper JAR/scripts/properties của PR vẫn sai.

### 14.1. Test count cần có gate riêng

`build.log` và JUnit XML phải chứng minh đủ 3 tests; khi dùng XML report publisher, cấu hình fail khi XML thiếu hoặc zero tests. `if-no-files-found: error` giúp tránh im lặng khi report chưa được tạo, nhưng không thay thế assertion rằng XML có ba methods executed.

### 14.2. CI matrix nào nên có?

Với Java library và Gradle9:

- Linux JDK17: bắt buộc để giữ baseline target.
- JDK21/25: nếu runtime product công bố hỗ trợ hoặc plugin build logic cần thử.
- Windows/macOS: nếu có native tool/path/shell behavior.
- Gradle8.14.6 compatibility: chỉ khi cần giữ support cho build logic/Gradle plugin consumers.
- Gradle9.9.0 Wrapper job: cần vì đó là version đang nâng.

**Không tạo tích Descartes mọi OS × JDK × Gradle** nếu không có hợp đồng/rủi ro tương ứng. Gradle9.9 hỗ trợ các Java runtimes cụ thể theo compatibility matrix; không đưa JVM11 vào job để chạy Daemon và gọi nó là Gradle bug.

### 14.3. Không phát hành từ PR matrix

Matrix dùng để verify. Publishing, signing, pushing Docker images hoặc upload Maven artifact có credentials phải là job riêng sau required checks và approvals. Đừng để nhiều matrix jobs cùng publish một tọa độ/version.

## 15. Đo performance khi đã qua functional gate

Một nâng cấp có thể làm compile nhanh hơn hoặc chậm hơn, nhưng trước tiên phải PASS về hành vi.

Để benchmark hợp lệ:

1. Cùng machine/runner class, OS, CPU/memory/disk.
2. Cùng JDK/Gradle Daemon mode và Gradle JVM args.
3. Có warm-up cho từng Gradle version.
4. Ghi thời gian nhiều lượt, so median/p95 khi phù hợp.
5. Phân biệt first-build/cold distribution vs warm incremental build.
6. Không trộn một bên `--build-cache`, bên kia `--no-build-cache`.
7. Không dùng `clean` giữa hai lượt nếu muốn đo `UP-TO-DATE`.
8. Dùng Gradle profiling/Build Scan nếu organization cho phép.
9. Cùng source revision/test selectors/compiler/toolchain.
10. Không tối ưu bằng cách tắt tests, annotation processors hoặc checks bắt buộc.

**Không tự tuyên bố “Gradle9 nhanh hơn X%” chỉ vì một dòng banner có elapsed time thấp hơn.** Download dependencies, Daemon warm-up và test runtime jitter có thể lớn hơn lợi ích của một plugin/script change.

### 15.1. Configuration cache sau khi basic upgrade PASS

```bash
./gradlew check jar --configuration-cache \
  --no-build-cache --console=plain

./gradlew check jar --configuration-cache \
  --no-build-cache --console=plain
```

Lần thứ hai có thể reuse configuration cache entry nếu build logic tương thích và configuration inputs không đổi. Nếu problems report xuất hiện, sửa task state/unsupported listeners hoặc Project access từ task action theo Gradle docs; **không đánh dấu cache compatibility PASS chỉ vì chuyển problems sang warning mode**.

### 15.2. Build cache test riêng

```bash
./gradlew clean check jar --build-cache \
  --no-configuration-cache --console=plain
```

Task caching phụ thuộc cacheable tasks/inputs/implementation/cache state. Không yêu cầu mọi task phải `FROM-CACHE`. Điều quan trọng là restore outputs đúng và tránh hidden inputs làm sai artifact.

## 16. Rollback mà không phá công việc khác

Nếu Wrapper changes đang là **uncommitted edits của chính lượt nâng này**, có thể restore **chỉ các file Wrapper**:

```bash
git restore -- \
  gradlew gradlew.bat \
  gradle/wrapper/gradle-wrapper.jar \
  gradle/wrapper/gradle-wrapper.properties

./gradlew --version
./gradlew clean check jar --no-build-cache --no-configuration-cache
```

Windows PowerShell:

```powershell
git restore -- gradlew gradlew.bat gradle/wrapper/gradle-wrapper.jar gradle/wrapper/gradle-wrapper.properties
.\gradlew.bat --version
.\gradlew.bat clean check jar --no-build-cache --no-configuration-cache
```

**Cảnh báo:** `git restore` sẽ bỏ uncommitted changes của đúng bốn Wrapper files. Chỉ dùng nếu đó là các thay đổi bạn đã xác nhận cần bỏ, không làm mất modification hợp lệ của đồng đội. Nếu migration đã commit/merge, làm **reviewed revert commit** thay vì reset toàn repository.

**Không dùng `git reset --hard` làm phương án mặc định.** Nó có thể xóa unrelated uncommitted work và làm mất evidence/bug fixes.

Rollback được công nhận khi:

1. Wrapper version quay lại đúng **8.14.6**.
2. Java/JUnit/other environment vẫn khớp baseline.
3. `clean check jar` PASS.
4. JUnit XML có 3 tests PASS.
5. Program stdout lại `UPGRADE_OK;sum=7`.
6. Required artifacts/classes có đủ.
7. CI checkout/branch policy không bị phá.
8. Những build-logic fixes độc lập có được giữ/rollback theo quyết định riêng.

**Thấy Gradle8 banner không đủ để tuyên bố rollback thành công.**

## 17. Plugin, Android và Spring Boot: các khác biệt trong dự án thật

### 17.1. Gradle plugin hoặc convention plugin

Nếu thứ bạn phát hành là **Gradle plugin**, người dùng có thể apply plugin trên nhiều Gradle distributions. Khi nâng build của plugin lên Gradle9, phải kiểm cả **consumer compatibility**.

Gradle TestKit có `GradleRunner.withGradleVersion(...)`:

```java
BuildResult result = GradleRunner.create()
    .withProjectDir(testProjectDir)
    .withPluginClasspath()
    .withGradleVersion("9.9.0")
    .withArguments("help", "--stacktrace")
    .build();
```

Đây là snippet trong một TestKit test method, **không phải full runnable Java test class**: cần imports, consumer fixture, plugin-under-test classpath và assertions. `withGradleVersion` điều khiển Gradle version của nested build, không tự thay OS/JDK.

Các checks quan trọng: plugin apply, tasks register/execute, publication metadata, configuration cache, variant API và backward compatibility nếu bạn vẫn hứa hỗ trợ Gradle8.

### 17.2. Spring Boot

Spring Boot Gradle plugin có support matrix theo **Boot release**. Không nên nâng Gradle9 trong một Boot version không hỗ trợ. Kiểm plugin release notes và Gradle minimum/maximum, tách Boot major migration khỏi Gradle major khi có thể, rồi chạy integration/startup/`bootJar` tests.

### 17.3. Android Gradle Plugin

Android builds còn có **AGP, Gradle, JDK, Android SDK** và variant APIs. Gradle9.9 không tự có nghĩa AGP hiện tại của project đã tương thích. Đọc Android Developers AGP/Gradle compatibility, run compile/tests/assemble từng variant phù hợp.

### 17.4. Kotlin/Scala/Groovy

Gradle9 nâng embedded Kotlin/Groovy nhưng điều đó không đồng nghĩa Kotlin Gradle Plugin/KSP/Scala compiler của dự án tự tương thích. Kiểm plugin minimum versions, compiler options, binary/API compatibility và test source set behavior.

## 18. Bảng những lỗi hay gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| Wrapper vẫn báo Gradle8 | Sai URL/chạy wrong executable | `./gradlew --version` và properties |
| Scripts/JAR không đổi | Chỉ chạy `:wrapper` một lần | Chạy lần hai bằng target Gradle |
| Gradle9 không start | Daemon JVM cũ hơn17 | Cấu hình Gradle JVM17+ |
| `Checksum mismatch` | Old hash / wrong ZIP / tamper | Dừng, kiểm official checksum |
| Plugin apply fail | Third-party plugin không hỗ trợ Gradle9 | Plugin release notes và migration |
| `Project.exec` unresolved | Removed Gradle9 API | Inject ExecOperations/typed Exec |
| Custom Test không chạy | Removed implicit Test sourceSet default | Set classpath/testClassesDirs |
| `No tests discovered` | JUnit platform/engine/source set sai | Sửa test config, không disable gate |
| `test NO-SOURCE` | Test files/source set không có | Kiểm tests thực sự được compile |
| `test SKIPPED` | onlyIf/enabled/task exclusion | Kiểm quality gate không bị bỏ |
| Build log thay format | Gradle logging/problem reports mới | So semantics, không diff text tuyệt đối |
| JAR SHA khác | ZIP metadata/implementation đổi | Kiểm entries/classes/manifest |
| JAR thiếu classes | Archive configuration/variant issue | `jar tf`, task graph, packaging |
| Test JUnit XML khác timestamp | Runtime duration khác | So counters/methods |
| Runtime deps đổi | Constraints/lock/variant resolution | `dependencyInsight` theo configuration |
| `UP-TO-DATE` sau repeat | Inputs/outputs không đổi | Expected nếu outputs hợp lệ |
| `FROM-CACHE` sau clean | Task cacheable/cache hit | Phân biệt execution vs restore |
| Configuration cache không reuse | Plugin/task state incompatible | Problems report/Provider API |
| Warning mới không rõ nguồn | Gradle9.x new deprecation | Migration guide, triage owner |
| CI Java11 fails | Gradle9 Daemon requires17+ | Cập nhật Gradle JVM |
| CI Windows script fails | Sai shell/Wrapper invocation | `.\gradlew.bat` trên PowerShell |
| CI xanh nhưng 0 tests | Missing report/skip/zero source | Assert report counters |
| Performance chậm sau nâng | Cold dist/cache, daemon warm-up | Profile cùng conditions |
| Gradle TestKit consumer fail | Plugin API compatibility | `withGradleVersion` fixtures |
| IDE sync đỏ | Tooling/IDE version lỗi | Kiểm IDE Gradle support |
| Rollback về Gradle8 rồi vẫn fail | Environment/source drift | Chạy baseline full gates |
| `--warning-mode=none` làm đẹp log | Chỉ che cảnh báo | Dùng `--warning-mode=all` |
| `-x test` làm build xanh | Đã bỏ quality checks | Khôi phục required tests |

## 19. Mẫu báo cáo kiểm định PR

Điền kết quả từ các files **được chạy thật**:

```text
Thay đổi:
  Gradle Wrapper 8.14.6 -> 9.9.0
  JDK 17 unchanged
  JUnit Jupiter 5.11.4 / Launcher 1.11.4 unchanged

Before:
  - Gradle: 8.14.6
  - JUnit: 3 tests passed / 0 failed
  - Program: UPGRADE_OK;sum=7
  - JAR: demo/Main.class, demo/Calculator.class
  - Deprecations: documented

After:
  - Gradle: 9.9.0
  - JUnit: 3 tests passed / 0 failed
  - Program: UPGRADE_OK;sum=7
  - JAR: required classes retained
  - Dependency graph: changes reviewed
  - New warnings/problems: triaged

Gates:
  - Wrapper JAR and distribution validated
  - Required CI jobs passed
  - No hidden skip/zero-test result
  - Rollback path tested or documented
```

**Đây là khung báo cáo, không phải chứng nhận một run đã xảy ra.** Không điền “3 passed” khi JUnit XML không tồn tại, hoặc “Gradle9.9.0” khi `--version` vẫn là 8.14.6.

## 20. Bài tập tự luyện

### Bài 1 — baseline evidence

Dựng demo `upgrade-proof`, chạy `clean check jar` ở Gradle8.14.6 và ghi mười files `evidence/before`. Xác nhận 3 test methods và stdout đúng.

### Bài 2 — warnings audit

Chạy `help --warning-mode=all`; xác định mỗi warning là build script, plugin hay Gradle toolchain. Nếu không thấy warning, ghi “none observed for this invocation”, không claim tất cả build paths hoàn toàn sạch.

### Bài 3 — Wrapper two-pass

Thực hiện đúng hai lượt `:wrapper --gradle-version 9.9.0`. Đọc Wrapper properties, JAR checksum và `./gradlew --version` sau mỗi bước.

### Bài 4 — verify full behavior

Chạy lại `clean check jar`, copy JUnit XML, program stdout và JAR entries sang `evidence/after`. So từng acceptance invariant.

### Bài 5 — canary regression

Đổi `Main.message()` có chủ đích, giữ test expectation cũ. Chứng minh JUnit fail. Khôi phục source và chạy lại full quality gate.

### Bài 6 — Test task migration

Trong bản sandbox, tạo một `Test` task không khai báo `testClassesDirs`/`classpath`. So Gradle8/9 behavior rồi sửa explicit source set; không tắt no-tests failure của toàn project.

### Bài 7 — removed API

Tìm `project.exec`/`project.javaexec` trong một plugin cũ, thay bằng `ExecOperations`/typed task và viết regression test cho action/output.

### Bài 8 — dependency graphs

So `runtime-deps.txt` và `test-deps.txt`, giải thích từng resolved version changed hoặc text formatting changed, không chỉ chạy raw diff.

### Bài 9 — cache/performance

So warm `help`/`check` trên cùng machine/JDK, tách configuration cache/build cache/incremental cases. Ghi nhiều samples, không tuyên bố performance win từ một run.

### Bài 10 — rollback rehearsal

Trên branch riêng, khôi phục **chỉ Wrapper files**, verify Gradle8.14.6 và chạy tests/app/JAR. Không dùng `git reset --hard` làm giải pháp phổ quát.

## 21. Câu hỏi tự kiểm tra

1. **Đổi `distributionUrl` có đủ chứng minh upgrade?** Không; phải kiểm behavior/tests/artifact/CI.
2. **Vì sao không nâng JDK và Gradle cùng lúc?** Khó quy nguyên nhân regression.
3. **Gradle9 Daemon cần tối thiểu JVM nào?** Java17.
4. **Compiler Java17 có bắt buộc Daemon dùng cùng JVM?** Không, toolchain độc lập.
5. **Lệnh nào report Wrapper version thực?** `./gradlew --version`.
6. **Vì sao chạy Wrapper task hai lần?** Đồng bộ Wrapper properties/scripts/JAR.
7. **`distributionSha256Sum` kiểm cái gì?** Distribution ZIP, khác Wrapper JAR checksum.
8. **Vì sao cần warning-mode=all ở baseline?** Tìm APIs sắp bị xóa.
9. **Vì sao `BUILD SUCCESSFUL` chưa đủ?** Có thể test không được thực thi.
10. **Khi `test NO-SOURCE` là PASS?** Không nếu tests là yêu cầu bắt buộc.
11. **Junit XML cần kiểm gì?** Tests count, failures/errors/skips, methods.
12. **Một archive hash khác đã là regression?** Không, còn phải xem contents/behavior.
13. **`UP-TO-DATE` nghĩa gì?** Action không chạy vì state hợp lệ.
14. **`FROM-CACHE` nghĩa gì?** Outputs được restore từ cache, không chạy action.
15. **Có dùng `--rerun-tasks` để đo up-to-date không?** Không, nó ép execution.
16. **`--no-configuration-cache` có phải `--no-build-cache`?** Không; hai lớp khác nhau.
17. **Custom Test task thay gì ở Gradle9?** Không còn implicit test source set defaults.
18. **Gradle9 có thể fail khi sources có nhưng không discover tests?** Có.
19. **`Project.exec` còn trên Gradle9?** Đã bị xóa, dùng API khác.
20. **TestKit `withGradleVersion` kiểm OS mới không?** Không, chọn Gradle distribution nested build.
21. **Performance comparison cần điều kiện gì?** Cùng host/JDK/cache states và nhiều mẫu.
22. **Rollback có được dùng `git reset --hard` mặc định?** Không.
23. **Rollback chỉ cần version banner đúng?** Không, phải PASS baseline behavior.
24. **Tại sao phải giữ evidence ngoài `build`?** `clean` sẽ xóa `build`.
25. **Bằng chứng đáng tin là gì?** Commands/exit codes thật, test results, stdout, artifact và dependency report.
26. **Cần publish Build Scan mọi lúc?** Không nếu policy không cho phép.
27. **Một required check được phép `-x test` không?** Không nếu nó được định nghĩa là verification gate.
28. **Khi nào được nâng dependency đồng thời?** Khi tương thích bắt buộc và có evidence/changelog riêng.
29. **Có bắt buộc JAR bitwise identical?** Chỉ khi release contract yêu cầu reproducible bytes trong môi trường kiểm soát.
30. **Khi nào được ghi QA PASS cho upgrade thực tế?** Khi tất cả acceptance invariants đã được kiểm chứng qua chạy thật.

## 22. Checklist nghiệm thu

- [ ] Có một baseline commit và source/Gradle script/JUnit versions cố định.
- [ ] Trước nâng, Gradle Wrapper report đúng 8.14.6.
- [ ] JVM chạy Daemon và compiler toolchain được ghi rõ.
- [ ] Baseline JUnit XML có 3 tests PASS, không skip/zero-source.
- [ ] Baseline app stdout chính xác `UPGRADE_OK;sum=7`.
- [ ] Baseline JAR có required classes.
- [ ] Đã thu before logs/version/dependency graphs.
- [ ] Đã chạy `--warning-mode=all` và phân loại deprecations.
- [ ] Đã đọc Gradle9 major guide và 9.x upgrading guide.
- [ ] Gradle9 Daemon dùng Java17+.
- [ ] Target Wrapper version ghim 9.9.0, không dùng `latest`.
- [ ] Wrapper task chạy hai lần theo docs.
- [ ] Wrapper properties/scripts/JAR đã được kiểm.
- [ ] Official distribution/JAR checksums được xác minh.
- [ ] Gradle9.9.0 `./gradlew --version` khởi động thành công.
- [ ] Full after `clean check jar` chạy trên cùng source/JDK.
- [ ] After JUnit XML có 3 tests thực thi và PASS.
- [ ] After stdout giữ đúng behavior contract.
- [ ] After JAR required entries còn đủ.
- [ ] Runtime/test resolved dependencies được kiểm.
- [ ] Task outcomes được hiểu, không lẫn `UP-TO-DATE`/`FROM-CACHE`.
- [ ] Có negative control chứng minh tests bắt regression nếu cần.
- [ ] Custom Test task/removed APIs được rà khi project dùng.
- [ ] Third-party plugins support Gradle9 được xác minh.
- [ ] Configuration/build cache kiểm riêng nếu là requirement.
- [ ] CI required OS/JDK/jobs đều thật sự PASS.
- [ ] Không bỏ checks bằng `-x test`/`ignoreFailures`/`--warning-mode=none`.
- [ ] Có rollback chỉ Wrapper files mà không phá unrelated work.
- [ ] Nếu đã merge, rollback dùng reviewed revert commit.
- [ ] PR evidence ledger chỉ ghi actual results, không tự giả định.
- [ ] Performance chỉ được tuyên bố khi đo đúng điều kiện.

## 23. Ghi nhớ

- **Nâng Gradle là một migration build platform, không đơn thuần là thay số version**.
- **Chứng minh behavior trước nâng** bằng test XML, stdout, artifacts và dependency reports.
- **Giữ JDK/source/dependencies ổn định** để cô lập biến Gradle distribution.
- **Chạy Wrapper task hai lượt** và kiểm checksum/integrity.
- **Gradle9 yêu cầu Daemon JVM17+, bỏ một số APIs cũ và thay Test task discovery/default conventions**.
- **Không đánh đồng log/JAR hash differences với regression** nếu contract chỉ cần behavior/entries.
- **Không xem zero tests, skipped tests hoặc cached outputs là một full execution test**.
- **So performance riêng** sau khi functional gates đạt.
- **Có CI gate, changelog warnings và rollback được kiểm** trước khi phát hành.
- **Không ghi PASS cho phép thử chưa được chạy**.

## Tài liệu chính thức

- [Gradle 9.9.0 Release Notes](https://docs.gradle.org/current/release-notes.html): bản target và phát hành 7/11/2026.
- [Gradle — Upgrade to Gradle 9](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html): Java17, removed APIs, Test task changes và packaging/metadata.
- [Gradle — Upgrade within Gradle 9.x](https://docs.gradle.org/current/userguide/upgrading_version_9.html): breaking changes và deprecations sau 9.0.
- [Gradle — Upgrade within Gradle 8.x](https://docs.gradle.org/current/userguide/upgrading_version_8.html): chuẩn bị baseline và deprecated APIs.
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): version pinning, two-pass upgrade, checksum và integrity.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): Gradle runtime JVM/toolchain requirements.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): compiler/test launcher vs Gradle Daemon JVM.
- [Gradle — Java Testing](https://docs.gradle.org/current/userguide/java_testing.html): `Test`, test discovery, reports.
- [Gradle — Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html): `dependencies`, `dependencyInsight`.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): config state reuse/compatibility.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cached task outputs and correctness.
- [Gradle — Incremental Build and Task Outcomes](https://docs.gradle.org/current/userguide/gradle_optimizations.html): outcomes/UP-TO-DATE/FROM-CACHE.
- [Gradle — TestKit](https://docs.gradle.org/current/userguide/test_kit.html): consumer plugin tests with `withGradleVersion`.
- [Gradle — Build Scans](https://docs.gradle.org/current/userguide/inspect.html): deprecation/performance diagnostics khi policy cho phép.
- [Gradle — Security Best Practices](https://docs.gradle.org/current/userguide/best_practices_security.html): Wrapper JAR integrity và supply-chain controls.
