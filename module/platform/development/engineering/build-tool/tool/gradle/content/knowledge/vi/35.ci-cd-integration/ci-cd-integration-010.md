# Xác minh artifact từ môi trường sạch trước khi triển khai với Gradle CI/CD

## 1. Vì sao “build thành công trên máy tôi” chưa đủ để triển khai?

Một ứng dụng Java có thể chạy tốt trên máy phát triển nhưng thất bại sau triển khai vì máy đó vô tình có:

- Class files hoặc generated resources từ một lần build cũ.
- Dependency JAR trong cache không tương ứng với bản đã được chấp nhận.
- Biến môi trường, private repository hoặc credential mà CI/production không có.
- Gradle daemon, JDK hoặc plugin version khác với release environment.
- File chưa commit trong working tree nhưng đã được dùng khi compile.
- Task cache hit có output lỗi do thiếu input tracking.
- Artifact được build **lại lần thứ hai** trong deployment job với môi trường khác.
- JAR có đúng tên nhưng thiếu entrypoint, service provider, resource hoặc runtime dependency.
- Test task bị bỏ qua, báo `NO-SOURCE` hoặc bị cấu hình `ignoreFailures`.
- Một thay đổi Gradle build script làm output khác nhưng quality gate chỉ kiểm tra exit code.

**Xác minh artifact từ môi trường sạch** là quy trình tạo và kiểm tra artifact trong môi trường có thể tái lập, từ **source revision đã được xác định**, không dựa vào outputs có sẵn trong workspace developer; sau đó bảo đảm **chính bytes đã kiểm tra** là bytes được đưa qua bước triển khai.

Trong CI/CD, câu hỏi đúng không chỉ là:

> “`./gradlew build` có exit code 0 không?”

mà phải là:

> “Từ đúng commit, công cụ và dependencies được kiểm soát, chúng ta có tạo được artifact đầy đủ, qua đúng tests/quality gates, chạy smoke test trong môi trường thích hợp và xác nhận artifact được promote vẫn là cùng một đối tượng đã kiểm tra hay không?”

### 1.1. Hai nguyên tắc cốt lõi

1. **Build once, verify, promote:** tạo artifact một lần trong trusted verification job, chạy tests và kiểm tra đúng artifact đó, sau đó lưu vào immutable artifact store và **promote cùng digest**. Không build lại trong deploy job.
2. **Clean, controlled, traceable:** môi trường build mới hoặc được làm sạch có chủ đích; chốt commit SHA, Gradle Wrapper/JDK, dependency versions, flags/cache mode và lưu đủ bằng chứng để giải thích kết quả.

Tốc độ rất quan trọng, nhưng không được đánh đổi tính đúng/supply-chain integrity chỉ để CI xanh sớm hơn.

## 2. Vị trí của bước xác minh trong pipeline CI/CD

Một pipeline chuẩn có thể chia:

```text
Git commit / signed release tag
           |
           v
Checkout revision cụ thể trong clean runner/workspace
           |
           v
Verify Gradle Wrapper + toolchain + dependency policy
           |
           v
Build from clean source: compile + test + verify + package
           |
           v
Inspect artifact content, entrypoint, dependencies
           |
           v
Execute packaged artifact in smoke-test environment
           |
           v
Calculate SHA-256 + record build provenance
           |
           v
Upload immutable VERIFIED artifact to artifact store
           |
           v
Policy / approval / security checks
           |
           v
Download the SAME artifact in deployment job
           |
           v
Check expected SHA-256 / provenance / signature
           |
           v
Deploy the verified bytes (không build lại)
           |
           v
Runtime health / smoke tests + rollback strategy
```

Nếu quality gate hoặc artifact validation thất bại, phải dừng pipeline **trước** khi có side effect production.

### 2.1. Ai chịu trách nhiệm ở từng giai đoạn?

| Giai đoạn | Trách nhiệm | Bằng chứng |
| --- | --- | --- |
| Source checkout | CI / VCS | Commit SHA, clean tree, protected branch/tag |
| Toolchain | Gradle Wrapper / Java setup | Gradle/JDK version, Wrapper validation |
| Dependency resolution | Gradle + repository policy | Lockfiles, verification metadata, audit |
| Compile/test | Gradle tasks | Exit codes, JUnit XML, task graph, quality reports |
| Package | Gradle `jar`/`assemble`/`distZip` | Artifact name, entries, manifest, dependencies |
| Smoke test | Java/runtime environment | Real launch result, stdout/health response |
| Integrity | Hash/signature/provenance tooling | SHA-256, artifact ID, builder identity |
| Store/promote | CI/artifact repository | Immutable artifact reference/digest |
| Deploy | Release/deployment tooling | Digest equality, environment approval, deploy record |
| Postdeploy | Runtime checks | Readiness, behavior, rollback signal |

Không nên giao cho Gradle một trách nhiệm mà nó không tự cung cấp. Ví dụ, Gradle có thể tạo JAR và kiểm tra external dependencies; **Gradle không tự chứng nhận nguồn gốc của mọi artifact đã upload** trừ khi bạn bổ sung signing/attestation/pipeline policy phù hợp.

## 3. “Môi trường sạch” có nhiều mức độ

Từ **clean** không có nghĩa duy nhất. Hãy xác định mức độ sạch của phép thử.

| Mức độ | Làm gì? | Chưa bảo đảm điều gì? |
| --- | --- | --- |
| Workspace clean | `./gradlew clean` xóa outputs mà task `clean` quản lý | Vẫn có dependency/Build Cache, daemon và file untracked khác |
| Cache-disabled task build | `--no-build-cache` | Dependency cache, transforms hoặc toolchain vẫn có thể được tái sử dụng |
| Rerun task actions | `--rerun-tasks` | Không bảo đảm dependency bytes được lấy từ nguồn tin cậy |
| Fresh source checkout | Checkout commit vào thư mục mới | Gradle User Home/OS/runner có thể còn state |
| Isolated Gradle User Home | Dùng thư mục `GRADLE_USER_HOME` riêng | Không thay hệ điều hành/JDK/network hoặc attestations |
| Ephemeral CI runner | Máy/container mới được cấp phát | Base image, action versions, network/repository vẫn là inputs |
| Reproducible build | Same controlled inputs sinh same artifact bytes | Không tự xác minh source/dependency có an toàn hay không |

**Khuyến nghị cho release:** dùng fresh checkout ở đúng commit + runner tin cậy + Gradle Wrapper được xác minh + JDK/toolchain xác định + dependencies có policy/verification + không dựa trên stale task outputs. Trong lần kiểm tra nhạy cảm, có thể cô lập Gradle User Home và tắt Build Cache để giảm phụ thuộc vào cached task outputs.

### 3.1. `clean` không tự xóa tất cả caches

```bash
./gradlew clean check
```

có thể sử dụng Gradle Daemon cũ, dependencies đã tải, file user configuration, Build Cache và configuration state. Lệnh `clean` là task thuộc build, không phải reset toàn bộ máy.

### 3.2. `--no-build-cache` khác `--refresh-dependencies`

- `--no-build-cache`: tắt khả năng tái sử dụng task outputs qua Gradle Build Cache cho invocation.
- `--refresh-dependencies`: kiểm tra lại thông tin dependency metadata/artifacts theo cơ chế của Gradle; **không chứng minh chúng an toàn**.
- `--rerun-tasks`: yêu cầu thực thi task actions lại thay vì dựa vào up-to-date checks.
- `--no-configuration-cache`: không reuse configuration state.
- `--offline`: không truy cập repositories; với một Gradle User Home hoàn toàn mới có thể không resolve được dependencies.

Không đặt tất cả flags vào mọi pipeline chỉ để “sạch”; hãy giải thích rõ threat model và chi phí. Với CI release, tối thiểu phải chứng minh không dùng **stale workspace outputs**, còn dependency trust cần giải quyết bằng lockfiles và verification policy.

### 3.3. Fresh clone khác `git clean`

`git clean -fdx` có thể xóa untracked files rất mạnh và dễ gây mất dữ liệu trên máy developer. **Không khuyến nghị chạy trên working tree đang phát triển** chỉ để tạo release artifact.

Thay vào đó, CI nên checkout vào workspace mới hoặc tạo một disposable clone/worktree. Một clone từ commit cụ thể cũng giúp bảo đảm file mới chỉ nằm local nhưng chưa commit **không xuất hiện** trong bản release.

## 4. Một artifact được xác minh tốt cần những điều kiện nào?

Mỗi dự án có contract khác nhau, nhưng một Java application thường cần:

1. **Source revision:** chính xác commit được chọn.
2. **Toolchain:** Gradle Wrapper và JDK tương thích/được chốt.
3. **Dependencies:** versions/metadata được kiểm soát, không vô tình lấy artifact khác.
4. **Compilation:** main và test source compile thành công.
5. **Tests:** unit, integration/contract và quality tasks bắt buộc chạy và pass.
6. **Artifact structure:** main class, manifest, classes/resources/libs đúng.
7. **Runtime smoke test:** artifact thực sự khởi động ở runtime phù hợp.
8. **Artifact integrity:** SHA-256 và tham chiếu artifact được bảo toàn khi chuyển jobs/environments.
9. **Provenance:** ai build, từ commit nào, workflow/run ID nào, toolchain nào.
10. **Promotion gate:** release/deploy chỉ dùng artifact đã verify, không rebuild.
11. **No secrets in artifact:** không đóng gói credentials hoặc file môi trường riêng.
12. **Rollback:** có khả năng triển khai lại artifact phiên bản trước đã biết tốt.

### 4.1. Thế nào là “artifact giống nhau”?

Có nhiều mức kiểm tra:

- **Byte-identical:** toàn bộ file có cùng SHA-256.
- **Content/entry-equivalent:** cùng các class/resources cần thiết, nhưng timestamps/metadata có thể khác.
- **ABI-equivalent:** cùng public API/bytecode contract phù hợp.
- **Behavior-equivalent:** chạy tests/smoke cho kết quả đúng, có thể khác bytes.
- **Deployment identity:** đúng artifact ID/digest đã được verification job cho phép.

Trong bước **promote artifact giữa hai jobs**, nên yêu cầu **byte-identical**. Nếu deploy job download file khác SHA-256, phải dừng.

Trong bài toán **rebuild độc lập từ cùng source**, checksum giống nhau là tiêu chí reproducibility mạnh, nhưng có thể khác vì timestamps, toolchains, signature timestamp, generated metadata. Khi đó cần điều tra tính reproducible và contract; không kết luận mọi checksum khác là malware, cũng không bỏ qua checksum mismatch khi artifact đang được promote.

## 5. Bài thực hành Java 17 với Gradle Kotlin DSL

Bài lab tạo ứng dụng Java nhỏ, không cần third-party runtime dependencies để `java -jar` chạy trực tiếp. JUnit 5 chỉ dùng trong tests, làm rõ tính độc lập của main runtime và test classpath.

Mục tiêu:

- Build từ clean workspace.
- Chạy tests thực sự.
- Tạo JAR có entrypoint.
- Dùng Java runtime mở **chính file JAR**.
- Kiểm tra các entries quan trọng.
- Tạo và kiểm tra SHA-256 ở các bước khác nhau.
- Áp dụng quy tắc “build once, deploy same bytes”.

### 5.1. Cây thư mục

```text
clean-artifact-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
├── src/
│   ├── main/java/demo/
│   │   ├── Calculator.java
│   │   └── Main.java
│   └── test/java/demo/
│       └── CalculatorTest.java
├── tools/
│   └── VerifyJar.java
└── .github/
    └── workflows/
        └── verify-artifact.yml
```

Các file Wrapper chỉ hiện diện nếu project đã tạo/cài Wrapper, không được viết JAR Wrapper giả bằng tay. Những thư mục `build/`, `verified/`, `.gradle/` và các cache tạm chỉ xuất hiện khi thực thi và không nên commit.

**Yêu cầu:** JDK 17+, Gradle tương thích JDK 17; dùng Wrapper trong repository để mọi build gọi cùng Gradle distribution. JUnit dependencies ở Maven Central có thể cần network lúc đầu.

### 5.2. `settings.gradle.kts`

```kotlin
rootProject.name = "clean-artifact-lab"
```

Giữ tên project cố định giúp tên JAR dự kiến rõ ràng.

### 5.3. `build.gradle.kts`

```kotlin
import org.gradle.jvm.tasks.Jar

plugins {
    application
}

group = "dev.learning"
version = "1.0.0"

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

application {
    mainClass.set("demo.Main")
}

tasks.test {
    useJUnitPlatform()
}

tasks.named<Jar>("jar") {
    manifest {
        attributes["Main-Class"] = "demo.Main"
    }

    // Khai báo rõ ngay cả trên Gradle 9+ vốn đã có mặc định reproducible.
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

Giải thích:

- `application` tạo Java application model, cung cấp `run` và distribution tasks.
- `java.toolchain` yêu cầu compiler Java 17. Môi trường phải cài toolchain hoặc cấu hình resolver hợp lệ.
- `testImplementation` và `testRuntimeOnly` phục vụ JUnit tests, **không được đưa vào runtime JAR của ứng dụng**.
- `mainClass` dùng cho Application plugin. Ta cũng đặt manifest `Main-Class` vì `java -jar` đọc entrypoint từ JAR manifest.
- `isPreserveFileTimestamps=false` bỏ timestamps file input khi tạo archive.
- `isReproducibleFileOrder=true` áp đặt thứ tự entries ổn định khi đọc thư mục.

**Chú ý phiên bản:** Gradle 9.0+ đã đặt mặc định reproducible cho archive tasks, nhưng explicit settings giúp contract của bài dễ nhìn và có ích khi làm việc với Gradle versions cũ. Những yếu tố khác (JDK, generated files, archive customizations, ký thời gian thực) vẫn có thể làm builds không byte-identical.

### 5.4. Java source `Calculator.java`

**File `src/main/java/demo/Calculator.java`:**

```java
package demo;

public final class Calculator {
    private Calculator() {
    }

    public static int sumTo(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be non-negative");
        }

        int result = 0;
        for (int value = 1; value <= n; value++) {
            result += value;
        }
        return result;
    }
}
```

Với `n=10`, kết quả là 55. Đây là ví dụ nhỏ giúp kiểm tra behavior sau khi đóng gói.

**Giới hạn API:** `int` có thể overflow với `n` quá lớn; lab chỉ dùng inputs nhỏ. Production API phải có contract/kiểm tra overflow phù hợp.

### 5.5. Java entrypoint `Main.java`

**File `src/main/java/demo/Main.java`:**

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        int result = Calculator.sumTo(10);

        System.out.println(
                "artifact-verified=true; checksum=" + result
        );
    }
}
```

**Stdout chính xác** nếu lớp được compile đúng:

```text
artifact-verified=true; checksum=55
```

Dòng này là output của app, không phải SHA-256. Từ “checksum” trong source là nhãn giá trị kiểm tra phép tính; **không được nhầm với cryptographic digest của JAR**.

### 5.6. JUnit 5 tests `CalculatorTest.java`

**File `src/test/java/demo/CalculatorTest.java`:**

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

final class CalculatorTest {
    @Test
    void returnsZeroForEmptyRange() {
        assertEquals(0, Calculator.sumTo(0));
    }

    @Test
    void sumsTenNumbers() {
        assertEquals(55, Calculator.sumTo(10));
    }

    @Test
    void rejectsNegativeInput() {
        assertThrows(
                IllegalArgumentException.class,
                () -> Calculator.sumTo(-1)
        );
    }
}
```

Có **ba tests** thực sự. CI cần xác nhận test task đã chạy/discover tests và exit thành công; nếu `test` báo `NO-SOURCE` hoặc report trống, đó không phải quality gate đạt yêu cầu.

### 5.7. Khởi tạo Wrapper nếu chưa có

Dùng Gradle tương thích được cài sẵn **một lần** khi tạo repository:

```bash
gradle wrapper
```

Sau đó commit `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.jar` và `gradle-wrapper.properties`. CI dùng chính Wrapper này.

**Không** download một wrapper JAR ngẫu nhiên từ nguồn không tin cậy. Có thể dùng checksum validation/Gradle official mechanisms trong CI; bản thân Gradle Wrapper JAR là code được chạy trước khi build.

### 5.8. Xây và xác minh từ workspace sạch

Tại root project:

```bash
./gradlew --no-build-cache --no-configuration-cache clean check jar --console=plain
java -jar build/libs/clean-artifact-lab-1.0.0.jar
```

Windows PowerShell:

```powershell
.\gradlew.bat --no-build-cache --no-configuration-cache clean check jar --console=plain
java -jar build\libs\clean-artifact-lab-1.0.0.jar
```

**Stdout của `java -jar`:**

```text
artifact-verified=true; checksum=55
```

Các điều kiện cần xác nhận:

- Gradle exit code 0.
- Task `test` thực thi ba JUnit tests hoặc phản ánh caching/up-to-date đúng theo scenario.
- Không dùng `-x test` hay `ignoreFailures=true`.
- JAR được tạo ở path đã định; không sử dụng file được build trên máy khác.
- `java -jar` chạy được bằng Java runtime phù hợp.

**Tại sao dùng `check`?** Với Java plugin, `check` là lifecycle verification task có dependency tới `test`. Dự án thực có thể có thêm integration tests, Checkstyle, SpotBugs hoặc quality tasks tùy plugin/config. Không giả định root `check` tự chạy tất cả integration tests trong mọi repository.

### 5.9. Kiểm tra archive entries

```bash
jar tf build/libs/clean-artifact-lab-1.0.0.jar
```

Trong danh sách phải có:

```text
META-INF/MANIFEST.MF
demo/Calculator.class
demo/Main.class
```

Thứ tự entry có thể khác; không nhất thiết ba dòng đứng cạnh nhau. `jar tf` chứng minh file nằm trong JAR, nhưng không chứng minh bytecode hợp lệ khi runtime; vì vậy cần cả `java -jar`.

### 5.10. Kiểm tra test reports

Sau `check`:

```text
build/test-results/test/
build/reports/tests/test/
```

JUnit XML cho phép CI kiểm số tests, failures, skipped tests. Với dự án thật, nên coi điều kiện "0 tests" là failure khi project có test suite bắt buộc.

**Phân biệt:** `BUILD SUCCESSFUL` có thể xảy ra khi không có tests vì source path sai; kiểm tra `NO-SOURCE` là một quality gate riêng.

## 6. Java 17 tool kiểm tra cấu trúc JAR trong CI

Ngoài `jar tf`, có thể tạo một verifier nhỏ để kiểm tra manifest và class entries bằng Java standard library.

**File `tools/VerifyJar.java`:**

```java
import java.nio.file.Path;
import java.util.jar.Attributes;
import java.util.jar.JarFile;
import java.util.jar.Manifest;

public final class VerifyJar {
    private VerifyJar() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: VerifyJar <path-to-jar>"
            );
        }

        Path path = Path.of(args[0]);

        try (JarFile jar = new JarFile(path.toFile(), true)) {
            Manifest manifest = jar.getManifest();
            if (manifest == null) {
                throw new IllegalStateException("JAR manifest is missing");
            }

            String mainClass = manifest.getMainAttributes()
                    .getValue(Attributes.Name.MAIN_CLASS);

            if (!"demo.Main".equals(mainClass)) {
                throw new IllegalStateException(
                        "Unexpected Main-Class: " + mainClass
                );
            }

            requireEntry(jar, "demo/Main.class");
            requireEntry(jar, "demo/Calculator.class");
        }

        System.out.println(
                "jar-structure=PASS; main=demo.Main; classes=2"
        );
    }

    private static void requireEntry(JarFile jar, String name) {
        if (jar.getJarEntry(name) == null) {
            throw new IllegalStateException("Missing JAR entry: " + name);
        }
    }
}
```

Chạy từ root project sau khi tạo JAR:

Linux/macOS:

```bash
mkdir -p build/verify-tools
javac -d build/verify-tools tools/VerifyJar.java
java -cp build/verify-tools VerifyJar build/libs/clean-artifact-lab-1.0.0.jar
```

PowerShell:

```powershell
New-Item -ItemType Directory -Force build\verify-tools | Out-Null
javac -d build\verify-tools tools\VerifyJar.java
java -cp build\verify-tools VerifyJar build\libs\clean-artifact-lab-1.0.0.jar
```

**Stdout chính xác:**

```text
jar-structure=PASS; main=demo.Main; classes=2
```

Verifier chỉ kiểm tra **cấu trúc cần thiết**; nó chưa đọc hết bytecode hoặc xác thực cryptographic signatures của JAR. Việc truyền `true` vào `JarFile` giúp kiểm tra signatures cho những entry được đọc thích hợp, nhưng code trên chỉ tra entry metadata, **không được dùng như một chữ ký số validator đầy đủ**. Để kiểm tra chữ ký, provenance và trust chain, dùng công cụ/chính sách được thiết kế riêng.

**Không thay `java -jar` bằng công cụ này**: một JAR có đúng Main-Class và classes vẫn có thể fail khi khởi động vì dependency/runtime mismatch.

## 7. Xác minh SHA-256 cho đúng file sắp triển khai

Một file artifact được kiểm thử trong job A cần có nhận dạng content digest. SHA-256 là lựa chọn phổ biến.

### 7.1. Linux/macOS với công cụ sẵn có

Linux có `sha256sum`; macOS mặc định thường có `shasum -a 256` (công cụ không hoàn toàn giống nhau). Trong ví dụ CI chạy Linux:

```bash
mkdir -p verified
cp build/libs/clean-artifact-lab-1.0.0.jar verified/app.jar

(
  cd verified
  sha256sum app.jar > SHA256SUMS
  sha256sum -c SHA256SUMS
)
```

`verified/app.jar` là **bản sao đúng artifact đã kiểm tra**, còn `SHA256SUMS` chứa digest và filename. Không ghi một hash 64 ký tự giả trong tài liệu vì hash thực phụ thuộc bytes của bản build.

Khi chạy `sha256sum -c SHA256SUMS` thành công trong đúng thư mục, output điển hình:

```text
app.jar: OK
```

Nếu checksum mismatch, command trả exit code khác 0; pipeline phải dừng.

### 7.2. Windows PowerShell

```powershell
$jar = "build\libs\clean-artifact-lab-1.0.0.jar"
Get-FileHash -Path $jar -Algorithm SHA256
```

PowerShell in digest thực tế tại thời điểm chạy. Để kiểm tra sau khi chuyển file, lưu digest như một **expected value được bảo vệ** trong manifest/artifact repository, rồi so giá trị hash của file tải về với giá trị dự kiến.

Ví dụ trong một PowerShell session có digest đã xác minh:

```powershell
$originalHash = (Get-FileHash -Path "build\libs\clean-artifact-lab-1.0.0.jar" -Algorithm SHA256).Hash
New-Item -ItemType Directory -Force "verified" | Out-Null
Copy-Item -LiteralPath "build\libs\clean-artifact-lab-1.0.0.jar" -Destination "verified\app.jar"
$copiedHash = (Get-FileHash -Path "verified\app.jar" -Algorithm SHA256).Hash

if ($originalHash -ne $copiedHash) {
    throw "Artifact digest mismatch"
}
Write-Output "SHA256 copy verification: PASS"
```

**Stdout nếu hai bản sao bằng nhau:**

```text
SHA256 copy verification: PASS
```

Đây chỉ là kiểm tra bản sao **trong cùng môi trường**. Để chứng thực khi artifact đi qua CI jobs, expected digest phải được mang qua một kênh đáng tin cậy hoặc lấy từ signed attestation/immutable artifact record, không lấy từ nguồn bất kỳ do attacker kiểm soát.

### 7.3. SHA-256 chứng minh điều gì và không chứng minh điều gì?

SHA-256 cho biết **hai byte streams có giống nhau** hay không khi dùng expected digest đáng tin cậy. Nó không tự chứng minh:

- Source code đã được review.
- Build runner/CI workflow không bị chiếm quyền.
- Dependencies hoặc Gradle Wrapper là bản hợp lệ.
- Artifact không có lỗ hổng bảo mật.
- Người tạo artifact có đúng quyền release hay không.

Nếu attacker thay cả JAR và file SHA256SUMS trong cùng một chỗ không được bảo vệ, phép đối chiếu có thể vẫn báo `OK`. Do đó digest phải gắn với **trusted producer identity, protected CI run hoặc signed provenance**, và artifact storage cần ACL/immutability.

## 8. Build một lần, promote nhiều môi trường

Một anti-pattern CI/CD:

```text
CI:        ./gradlew clean check     → PASS
Staging:   ./gradlew build           → tạo JAR A
Production:./gradlew build           → tạo JAR B
```

JAR A và B có thể khác vì thời gian, dependencies, toolchain, source revision, configuration hoặc cache. Những bytes được tests trong CI chưa chắc là bytes production chạy.

**Mô hình đúng:**

```text
Protected verification job:
    commit abc... → build + test + artifact checks
                 → app.jar, digest H
                 → upload immutable artifact H

Staging:
    download artifact H
    verify H
    deploy H
    smoke tests pass

Production after approval:
    download same artifact H
    verify H + provenance
    deploy H
    health checks + monitor
```

Trong pipeline thực tế, deployment có thể dùng JAR, ZIP distribution, Docker image hoặc Kubernetes container image. Khi là container, hãy promote **image digest** (`sha256:...`) đã test, không chỉ mutable tag `latest`.

### 8.1. Vì sao không nên rebuild trong deploy job?

Nếu deploy job tự chạy `./gradlew assemble` lần nữa, build có thể:

- Lấy dependency mới nếu version dynamic.
- Dùng khác JDK patch version hoặc plugin.
- Chạy với repository credentials/config khác.
- Tạo manifest/build timestamp khác.
- Đưa file source chưa commit vào output.
- Bỏ qua tests từng có ở verification job.
- Đóng gói class/resources khác.
- Tự động chèn secrets từ deployment environment.

Vì vậy deploy job chỉ nên **kiểm tra và dùng artifact đã xác minh**, không compile lại trừ khi pipeline có lý do đặc biệt và một quy trình verification độc lập mới.

### 8.2. Manifest, metadata và provenance

Một release record hữu ích nên có:

| Trường | Ví dụ cách lấy |
| --- | --- |
| Source commit SHA | `git rev-parse HEAD` |
| Source ref/tag | CI event metadata |
| Gradle Wrapper version | `./gradlew --version` |
| Gradle JVM/JDK | Setup Java logs, `java -version` |
| Build job identity | CI run ID, protected branch/tag |
| Artifact filename/size | Repository metadata, file info |
| Artifact SHA-256 | `sha256sum` hoặc digest API |
| Tests | JUnit XML/test reports |
| Security checks | Dependency verification, vulnerability scan, policy reports |
| Runtime smoke result | `java -jar` stdout/exit code |
| Signature/attestation | Sigstore/SLSA or organization tooling if used |
| Deployment target | Environment approval and release record |

Đây là một **record of evidence**, không phải một file metadata tự động Gradle tạo đủ mọi trường.

## 9. GitHub Actions mẫu: build/verify rồi tải đúng artifact ở predeploy

Đây là **một workflow minh họa có thể áp dụng cho project lab đã có Gradle Wrapper được commit**, chạy trên GitHub-hosted Ubuntu runner. Nó không chứa credential production và **không tự triển khai production**; bước `predeploy` là gate để chứng minh job sau nhận đúng JAR đã test.

**File `.github/workflows/verify-artifact.yml`:**

```yaml
name: Verify packaged Java artifact

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify-artifact:
    runs-on: ubuntu-24.04
    steps:
      - name: Checkout repository
        uses: actions/checkout@v6
        with:
          persist-credentials: false

      - name: Configure Java 17
        uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: "17"

      - name: Isolate Gradle User Home
        run: echo "GRADLE_USER_HOME=$RUNNER_TEMP/gradle-home-verify" >> "$GITHUB_ENV"

      - name: Setup Gradle and validate Wrapper
        uses: gradle/actions/setup-gradle@v6
        with:
          cache-disabled: true

      - name: Run complete verification from clean checkout
        run: ./gradlew --no-build-cache --no-configuration-cache clean check jar --console=plain

      - name: Smoke test packaged JAR
        shell: bash
        run: |
          java -jar build/libs/clean-artifact-lab-1.0.0.jar | tee smoke.txt
          grep -Fx 'artifact-verified=true; checksum=55' smoke.txt
          jar tf build/libs/clean-artifact-lab-1.0.0.jar | grep -Fx 'demo/Main.class'
          jar tf build/libs/clean-artifact-lab-1.0.0.jar | grep -Fx 'demo/Calculator.class'

      - name: Stage verified bytes and digest
        shell: bash
        run: |
          mkdir -p verified
          cp build/libs/clean-artifact-lab-1.0.0.jar verified/app.jar
          (cd verified && sha256sum app.jar > SHA256SUMS)
          (cd verified && sha256sum -c SHA256SUMS)

      - name: Upload tested JAR with digest
        uses: actions/upload-artifact@v6
        with:
          name: verified-release
          path: verified/
          if-no-files-found: error
          retention-days: 7

  predeploy:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: verify-artifact
    runs-on: ubuntu-24.04
    environment: staging
    steps:
      - name: Download exact artifact from verification job
        uses: actions/download-artifact@v6
        with:
          name: verified-release
          path: verified/

      - name: Configure Java 17
        uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: "17"

      - name: Verify digest before any deployment
        shell: bash
        run: |
          cd verified
          sha256sum -c SHA256SUMS
          java -jar app.jar | grep -Fx 'artifact-verified=true; checksum=55'

      # Production deployment is deliberately not included.
      # Only a separately approved release job should deploy verified/app.jar.
```

**Điểm chú ý:**

- `actions/checkout@v6`, `setup-java@v5`, `gradle/actions/setup-gradle@v6` và artifact actions `@v6` là major tags minh họa; **production supply-chain policy nên pin full commit SHAs đã review**, và kiểm tra runner support/chính sách update actions.
- `setup-gradle@v6` có tính năng validate Gradle Wrapper, nhưng không thay thế review Gradle distribution source/checksum/URL.
- `cache-disabled: true` tắt cơ chế caching của setup-gradle action; `--no-build-cache`/`--no-configuration-cache` tắt hai Gradle cache modes tương ứng cho invocation.
- `GRADLE_USER_HOME` dưới `RUNNER_TEMP` giúp tách Gradle user state khỏi checkout, không giữ secrets ở repository.
- `verify-artifact` chạy trên cả PR và main. Không cấp production deploy credentials cho PR.
- `predeploy` chỉ chạy sau push vào `main` và cần `verify-artifact` thành công.
- `environment: staging` có thể gắn approval/protection rules của repository, nhưng **phải cấu hình rules thật** thì mới có bước duyệt.
- `predeploy` không checkout source và không chạy Gradle, để đảm bảo nó **không rebuild**.
- `SHA256SUMS` được tạo sau smoke test từ chính bản JAR đã build. Nó giúp xác nhận bytes được tải lại, nhưng muốn chống attacker sửa cả artifact và hash cần artifact identity/provenance, token permissions và attestation.
- Workflow dùng Linux utilities `sha256sum`, `grep`, `jar`; trên Windows runner phải dùng lệnh tương ứng.

**Không coi workflow này là pipeline production đầy đủ:** application thật cần integration tests, quality/security gates, vulnerability scan, repo-specific configurations, secret policy và deploy approval phù hợp. Phần `predeploy` cố ý không có bước deploy thực để không tạo một thao tác phát hành ngoài ý muốn.

## 10. Build từ Git revision và Gradle User Home tách biệt

Trong dự án Git thật, một phép kiểm tra thêm có thể dùng disposable clone. Đây là **thí nghiệm độc lập** với GitHub Actions ở mục 9, dành cho người muốn kiểm tra không phụ thuộc file chưa commit ở máy mình.

### 10.1. Linux/macOS

Chạy từ thư mục root của repository đã có commit hợp lệ:

```bash
set -eu

SOURCE_COMMIT="$(git rev-parse HEAD)"
TEMP_ROOT="$(mktemp -d)"

git clone --no-local . "$TEMP_ROOT/source"
cd "$TEMP_ROOT/source"
git checkout --detach "$SOURCE_COMMIT"

export GRADLE_USER_HOME="$TEMP_ROOT/gradle-home"

./gradlew --version
./gradlew --no-build-cache --no-configuration-cache clean check jar --console=plain
java -jar build/libs/clean-artifact-lab-1.0.0.jar
```

Kết quả `java -jar` đúng với fixture:

```text
artifact-verified=true; checksum=55
```

Lệnh có thể tốn network để tải Wrapper distribution/JUnit vì Gradle User Home mới. Điều đó là **dependency acquisition**, không phải bằng chứng tính an toàn của dependencies. Để cleanup, chỉ xóa `TEMP_ROOT` sau khi kiểm tra đường dẫn đó nằm trong vùng tạm mình vừa tạo và không còn cần báo cáo.

**Không chạy các lệnh xóa đệ quy không được kiểm tra trên working directory thật.**

### 10.2. Windows PowerShell

Chạy từ root Git repository:

```powershell
$source = (Get-Location).Path
$commit = (git rev-parse HEAD).Trim()
$tempRoot = Join-Path $env:TEMP ("verify-" + [guid]::NewGuid().ToString("N"))
$clone = Join-Path $tempRoot "source"

git clone --no-local $source $clone
if ($LASTEXITCODE -ne 0) { throw "Git clone failed" }

Push-Location $clone
try {
    git checkout --detach $commit
    if ($LASTEXITCODE -ne 0) { throw "Git checkout failed" }

    $env:GRADLE_USER_HOME = Join-Path $tempRoot "gradle-home"
    .\gradlew.bat --no-build-cache --no-configuration-cache clean check jar --console=plain
    if ($LASTEXITCODE -ne 0) { throw "Gradle verification failed" }

    java -jar build\libs\clean-artifact-lab-1.0.0.jar
    if ($LASTEXITCODE -ne 0) { throw "Artifact smoke test failed" }
}
finally {
    Pop-Location
}
```

PowerShell không tự coi mọi native command non-zero exit là exception; đoạn này chủ động kiểm tra `$LASTEXITCODE`. Với repository thực, có thể cần thiết lập credential để clone/submodules mà không in secrets.

### 10.3. Vì sao clone vẫn cần chốt revision?

Một fresh clone có thể lấy HEAD khác nếu branch được cập nhật trong lúc chuẩn bị. Ghi `git rev-parse HEAD` rồi checkout `--detach` commit đã chọn giúp tách *đối tượng nguồn* khỏi tên nhánh biến động.

CI production thường dùng commit SHA của pipeline event, không phải `git pull` mới nhất vào lúc deploy.

### 10.4. Submodules và generated source

Nếu project dùng Git submodules hoặc Git LFS, cần checkout đúng commit/submodule revisions và verify LFS objects có đầy đủ. Fresh checkout thiếu submodule hoặc LFS file sẽ không đại diện cho source hợp lệ; đừng chữa bằng cách copy thủ công từ máy developer nếu điều đó phá khả năng tái lập.

Generated source nên có task/contract rõ ràng. Nếu build phụ thuộc file generated chưa commit nhưng không có task tái tạo, clean build sẽ fail — **đó là lỗi thiết kế đáng phát hiện trước deployment**.

## 11. Dependency locking và verification: “fresh” không đồng nghĩa “trusted”

Một isolated Gradle User Home làm dependencies được tải từ repositories thay vì dùng bản đang nằm trong cache của developer. Nhưng điều đó không tự bảo đảm artifacts được tải là đúng và an toàn.

### 11.1. Lock versions

Gradle Dependency Locking giúp cố định **versions của resolved dependencies**, kể cả transitive modules, cho các configurations được bật.

Trong `build.gradle.kts` của project (phần **tùy chọn bổ sung**):

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

Sau khi tổ chức chọn và review dependency versions, developer có thể tạo lock state:

```bash
./gradlew dependencies --write-locks
./gradlew check --write-locks
```

Sau đó review/commit `gradle.lockfile` cùng source. Trong CI/release **không** chạy `--write-locks` để tự cập nhật dependency graph; CI phải dùng lockfiles đã được review. Locking là per project/configuration, nên multi-project builds cần bảo đảm các configurations quan trọng đã được resolve và lock theo đúng phạm vi.

**Lockfiles không bảo đảm integrity của bytes**: một module cùng version có thể bị thay trên repository nếu không có verification. Locking cũng không phải giải pháp phù hợp cho dependencies thay đổi như SNAPSHOT nếu muốn reproducible releases.

### 11.2. Verify downloaded artifacts

Gradle Dependency Verification dùng metadata:

```text
gradle/verification-metadata.xml
```

để kiểm tra checksums/chữ ký của dependencies/plugins được resolve.

Bước bootstrap trong **môi trường nguồn đáng tin cậy**:

```bash
./gradlew --write-verification-metadata sha256
```

hoặc ghi cả SHA-256 và PGP signatures nếu phù hợp:

```bash
./gradlew --write-verification-metadata sha256,pgp
```

**Không chạy bootstrap trong release job rồi tự chấp nhận tất cả giá trị mới.** Lệnh tạo metadata từ những artifacts đang được tải, nên nếu repository đã bị compromise, nó có thể ghi nhận chính checksum của artifact độc hại. Cần review các thay đổi và đối chiếu với nguồn độc lập đáng tin.

Sau khi `verification-metadata.xml` được commit, CI nên dùng chế độ nghiêm ngặt:

```bash
./gradlew --dependency-verification strict check
```

Nếu verification metadata thiếu artifact mới, Gradle có thể fail resolution; đó là dấu hiệu cần review/update metadata theo quy trình, không phải lý do chuyển `--dependency-verification off` cho release.

### 11.3. Dependency verification không xác minh local JAR do build tạo

Gradle dependency verification bảo vệ **artifacts được tải qua dependency management**, không trực tiếp xác thực output JAR mà `jar` task vừa tạo từ source local.

Do đó pipeline cần hai lớp riêng:

1. Dependency integrity: verification metadata, locks, repository/owner policy.
2. Release artifact integrity: checksum/signature/attestation của **JAR do CI tạo**, kiểm tra trước deploy.

Đừng nói “có `verification-metadata.xml` nên mọi release JAR đã được ký và xác minh”.

### 11.4. Plugins và Wrapper cũng là thành phần supply chain

Một build có thể bị ảnh hưởng bởi Gradle plugins, init scripts, Wrapper distribution và CI actions trước cả khi source code ứng dụng được compile. Nên:

- Chốt Gradle Wrapper version/distribution URL.
- Kiểm tra Wrapper JAR theo official checksums.
- Cấu hình checksum cho Wrapper distribution khi policy yêu cầu.
- Pin plugin IDs/versions và plugin repositories.
- Kiểm soát init scripts/`GRADLE_USER_HOME`.
- Dùng trusted CI actions/images và review permissions.
- Hạn chế environment secrets cho untrusted PR.
- Không chạy untrusted build scripts với production credentials.

## 12. Reproducible JAR và lý do hai clean builds đôi khi khác SHA

Gradle 9.0+ đặt mặc định cho archive tasks để giảm nondeterminism từ timestamps và file entry order. Trong bài lab, ta khai báo rõ:

```kotlin
tasks.named<Jar>("jar") {
    isPreserveFileTimestamps = false
    isReproducibleFileOrder = true
}
```

Tuy nhiên một JAR có thể vẫn khác bytes giữa hai máy vì:

- JDK vendor/patch version hoặc compiler flags khác.
- Generated source/resource chèn current timestamp, random UUID hoặc hostname.
- Bytecode enhancement/compiler plugins khác.
- File path tuyệt đối được nhúng vào class/resource.
- Git commit metadata được xử lý khác.
- ZIP/JAR custom task không tôn trọng reproducible archive settings.
- Signature hoặc package metadata chứa thời điểm ký.
- Dependencies/version resolution thay đổi.
- Locale/timezone/line endings ảnh hưởng generators.

### 12.1. Thử rebuild ở hai môi trường

Một bài kiểm tra reproducibility thực tế:

1. Chốt một commit và các versions/verification metadata.
2. Build JAR ở clean runner A, ghi digest A.
3. Build lại ở clean runner B với cùng controlled toolchain/inputs, ghi digest B.
4. So A/B: nếu giống thì có evidence byte-for-byte reproducibility cho hai lần thử đó.
5. Nếu khác, inspect archive entries/timestamps, binary diff và environment trước khi kết luận.
6. Dù SHA giống, vẫn chạy correctness/security gates vì reproducibility ≠ correctness.

### 12.2. Byte-identical và semantic equivalence

Có trường hợp JAR không byte-identical vì metadata hợp lệ nhưng public APIs và runtime behavior giữ nguyên. Khi đó cần biết tổ chức yêu cầu **reproducible bytes** hay chỉ **functional equivalence**.

Đối với bước **promotion** của cùng một release, không hạ chuẩn: deploy phải dùng **đúng bytes đã test**. Chỉ trong bài toán **rebuild independent** mới phân tích nguyên nhân checksum khác và có chính sách cụ thể.

### 12.3. Kiểm tra archive content

Lệnh:

```bash
jar tf build/libs/clean-artifact-lab-1.0.0.jar
```

phải thấy các entry quan trọng. Với service có resources, kiểm tra:

- `META-INF/services` cho ServiceLoader.
- `application.yml` hoặc runtime config đã được thiết kế.
- Native libraries/OS-specific files nếu có.
- JARs trong `distZip`/`installDist` hoặc container image.
- `Main-Class` / launcher script.
- Java class file version phù hợp runtime.

Không coi việc nhìn thấy một JAR file tồn tại là đủ.

## 13. JAR thường khác “fat JAR” hoặc distribution

Lab không có external runtime dependency, nên `java -jar` hoạt động. Nhưng khi project dùng Commons Lang, Jackson, Guava hoặc Spring:

- Gradle `jar` mặc định thường **không** gom mọi external dependencies vào JAR.
- `application` tạo distribution có scripts và runtime libs qua `installDist`/`distZip`.
- Một plugin như Shadow có thể tạo fat/uber JAR nếu được cấu hình.
- Spring Boot có task/package model riêng.
- Docker image có thể chứa runtime JRE, libs, launcher và OS packages.

Vì vậy một project thật phải xác minh **đúng đối tượng sẽ deploy**.

| Loại sản phẩm | Artifact cần kiểm |
| --- | --- |
| Plain library | JAR API/resources + POM/GMM + consumer integration test |
| CLI app đơn giản | Runnable JAR/launcher với `Main-Class` |
| Application distribution | ZIP/TAR/installed directory, scripts + libs |
| Spring Boot app | Boot JAR hoặc image, embedded dependencies |
| Dockerized service | Image digest, ENTRYPOINT, health endpoint |
| Android | APK/AAB signatures, variant, instrumentation tests |
| Native binary | ELF/PE/Mach-O hoặc installation package, target OS/arch |

**Đừng smoke-test plain `jar` rồi deploy `bootJar` hoặc Docker image chưa được test**. Nếu pipeline phát hành image, việc promotion nên dựa vào image digest đã scan/test trong đúng container runtime.

## 14. Groovy DSL tương đương cho lab

Với `build.gradle` Groovy thay vì Kotlin DSL:

```groovy
plugins {
    id 'application'
}

group = 'dev.learning'
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
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

application {
    mainClass = 'demo.Main'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('jar', Jar) {
    manifest {
        attributes 'Main-Class': 'demo.Main'
    }
    preserveFileTimestamps = false
    reproducibleFileOrder = true
}
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'clean-artifact-lab'
```

Java sources/test/verifier giữ nguyên. Chỉ chọn **một DSL** phù hợp cho từng file/project; không để cả `build.gradle` và `build.gradle.kts` với hai cấu hình mâu thuẫn và mong Gradle ghép chúng.

## 15. Môi trường sạch nhưng vẫn phải bảo vệ build caches

### 15.1. Build Cache

Remote Build Cache giúp Gradle reuse task outputs, có thể tiết kiệm thời gian CI. Tuy nhiên một release verification có thể quyết định tắt Build Cache hoặc chỉ đọc trusted cache theo policy.

- `--no-build-cache` đảm bảo không restore task outputs từ Build Cache trong invocation.
- `--rerun-tasks` yêu cầu task actions chạy lại khi cần audit.
- Remote write permission phải được server-side enforce, tránh cache poisoning.
- Tasks có secret output không nên cache.
- Build Cache và dependency cache khác nhau, không dùng `--no-build-cache` để khẳng định dependency bytes đã được verify.

### 15.2. Configuration Cache

Configuration Cache tái sử dụng configuration state. Với plugin/build logic tương thích, có thể tăng tốc CI, nhưng một artifact verification nghiêm ngặt có thể dùng `--no-configuration-cache` để tránh phụ thuộc state trước đó.

Không mặc định configuration cache sai hoặc không an toàn; vấn đề là **phân loại trust/reproducibility và biết mình đang kiểm tra điều gì**. Nếu team bật nó trong production CI, phải kiểm tra compatibility và invalidation correctness.

### 15.3. Dependency Cache

Dùng fresh `GRADLE_USER_HOME` là cách đơn giản để không vô tình mượn dependencies từ máy developer. Nhưng mỗi lần tải lại toàn bộ dependencies làm CI chậm và phụ thuộc network; một hệ thống mature có thể dùng **trusted read-only dependency cache**, vẫn enforce checksums/locks và test một clean-room path định kỳ.

Một pipeline đạt chất lượng không nhất thiết phải download lại Internet cho mọi release; cần chính sách chứng minh dependencies được xác minh và inputs được kiểm soát.

## 16. CI không được thay “verification” bằng “skip work”

Những anti-pattern:

### 16.1. Bỏ tests

```bash
./gradlew assemble -x test
```

Lệnh có thể tạo JAR, nhưng không xác nhận tests. Nếu release policy yêu cầu `check`, đây không phải replacement tương đương.

### 16.2. Che test failures

```kotlin
tasks.test {
    ignoreFailures = true
}
```

Test failure có thể không làm build fail theo cách gate cần. Khi release, chỉ pass nếu test suite required thực sự thành công.

### 16.3. Không có tests vẫn cho qua

Nếu Gradle báo:

```text
> Task :test NO-SOURCE
```

đối với project được yêu cầu có tests, đây là sự cố cần điều tra. Có thể source set bị đặt sai hoặc test engine không được cấu hình. Build success không có nghĩa test coverage pass.

### 16.4. “Artifact tồn tại” là điều kiện duy nhất

```bash
test -f build/libs/clean-artifact-lab-1.0.0.jar
```

chỉ chứng minh path tồn tại. Một JAR có thể thiếu Main-Class, class files hoặc dependencies. Phải thêm structure/manifest/run tests.

### 16.5. Deploy từ một directory mới tạo lại source

Nếu deployment job chạy `git checkout main` rồi `./gradlew jar`, nó có thể lấy commit khác so với verification job, dù task cùng tên. Deploy phải download **artifact đã được xác minh từ job/run được chấp nhận**, sau đó kiểm digest.

### 16.6. Tạo digest sau khi artifact đã bị thay

Nếu deploy job nhận JAR từ nguồn chưa tin cậy rồi tự tính SHA-256 và coi hash đó là “đúng” thì phép tính không xác thực nguồn gốc. Cần **expected digest gắn với trusted verification job hoặc signed attestation** trước khi so.

### 16.7. Tự sinh lockfile/verification metadata trong release

```bash
./gradlew --write-locks --write-verification-metadata sha256 check
```

Đây là thao tác **tạo/cập nhật trạng thái tin cậy**, không phải cách validate release theo lock/metadata đã được review. Hãy sinh và review trong development workflow, commit state, rồi CI tiêu thụ state đó.

## 17. Kiểm tra security và supply chain trước promotion

Ngoài Java unit tests, dự án thực có thể cần:

- Dependency vulnerability scanning (SCA).
- License policy check.
- SBOM theo định dạng SPDX/CycloneDX.
- Static analysis hoặc secret scanning.
- Artifact signing bằng key hoặc keyless workflows.
- Provenance/attestation theo chính sách SLSA.
- Container image scanning nếu sản phẩm là container.
- Chứng thực toolchain/build runner identity.
- Check release tag/signature và permission chain.
- Integration tests trong môi trường staging giống production.
- Approval/quorum đối với thay đổi nhạy cảm.

Các công cụ này **không tự có đầy đủ chỉ vì áp dụng Gradle Java plugin**. Cần plugin/tooling/CI policy cụ thể, credentials và reports được quản lý an toàn.

### 17.1. Artifact SHA-256 và chữ ký khác nhau thế nào?

SHA-256 xác nhận content **khi expected value được tin cậy**. Chữ ký số cho phép xác minh một chủ thể sở hữu key đã ký artifact hoặc manifest. Attestation/provenance bổ sung thông tin người tạo, source revision và build invocation.

Không có cơ chế nào thay thế toàn bộ cơ chế còn lại:

- Checksums giúp phát hiện thay bytes.
- Signatures/attestations giúp xác thực nguồn gốc theo trust policy.
- Tests giúp phát hiện lỗi behavior.
- Dependency verification giúp bảo vệ inputs được tải.
- Approvals giúp kiểm soát quyền đưa bản build vào production.

### 17.2. Không nhúng production secrets vào artifact

Nếu app cần connection strings/tokens, nên được cung cấp qua runtime secret management trong deployment environment. Đừng generate `application.properties` chứa production password ở verification job rồi đóng gói vào JAR.

Ngoài rủi ro lộ secret, việc nhúng environment-specific config làm mất khả năng **build once, deploy many**: cùng artifact không thể promote sang staging/prod với runtime secrets riêng. Hãy giữ binary immutable, còn environment config được inject có kiểm soát tại runtime.

### 17.3. CI build logic và credentials cũng phải tin cậy

Gradle build scripts/plugins là code có thể thực thi trong CI. PR từ nguồn không tin cậy có thể sửa build logic. Không cấp publish/deploy secrets cho job kiểm thử PR; dùng protected environment và server-side ACL.

**Tạo artifact trên một runner chứa secret production mà chưa review source** có thể đã gây rủi ro trước cả bước deploy.

## 18. Tích hợp multi-project Gradle

Một root Gradle build có thể gồm `:api`, `:domain`, `:service` và `:cli`. Không nên mặc định:

```bash
./gradlew :service:jar
```

là equivalent với:

```bash
./gradlew clean check
```

Lệnh đầu có thể chỉ đóng gói một project, lệnh sau kiểm tra nhiều nơi tùy lifecycle/plugin model.

### 18.1. Mô hình gate cho multi-project

Ví dụ pipeline:

```text
:api:check
:domain:check
:service:check
:cli:check
           |
           v
:service:distZip hoặc :service:bootJar
           |
           v
Extract/start exact distribution
           |
           v
Integration/API contract checks
           |
           v
Digest + upload verified distribution
```

Dùng task targets thực sự tồn tại trong build. Nếu một project chỉ có `java-library` và không áp dụng `application`, nó không tự có task `run`.

### 18.2. Chọn đúng artifact thay vì quét mọi file `build/libs`

Có thể có:

- Main JAR.
- Sources JAR.
- Javadoc JAR.
- Tests fixtures JAR.
- Shadow JAR.
- Boot JAR.
- Artifact classifier riêng.

Đừng dùng wildcard `build/libs/*.jar` rồi chọn file đầu tiên làm production artifact. Khi có nhiều JAR, CI nên dùng **task output path được xác định rõ**, hoặc cơ chế publication/distribution artifacts của plugin, và verify đúng file.

### 18.3. Kiểm tra transitive runtime dependencies

Với Java library/application phụ thuộc external modules:

```bash
./gradlew :service:dependencies --configuration runtimeClasspath
./gradlew :service:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Đây là mảnh **minh họa cho một multi-project build có subproject `:service`**, không phải lệnh chạy trong single-project lab. Những reports giúp kiểm tra dependency versions và runtime graph.

Nhưng chỉ nhìn `runtimeClasspath` chưa chứng minh distribution thực sự bao gồm đủ JARs. Cần inspect `distZip` hoặc startup script/runtime container.

## 19. Verify release candidate trước deploy production

Một quy trình doanh nghiệp có thể dùng ba giai đoạn:

### 19.1. Candidate build

- Build từ protected source revision.
- Verify all required tests/static/security checks.
- Tạo artifact immutable, digest và provenance.
- Publish vào staging artifact repository (khác production releases), gắn run ID.
- Không cho developer tùy ý overwrite canonical candidate.

### 19.2. Staging deployment

- Download candidate by immutable digest/ID.
- Verify checksum/signature.
- Deploy đúng bytes sang staging.
- Chạy integration, smoke, readiness và security assertions.
- Lưu deployment evidence, không ghi lại artifact.

### 19.3. Production promotion

- Chỉ sau approval/quality gates/staging pass.
- Dùng **cùng digest**, không rebuild.
- Kiểm image/JAR provenance, secret policy và configuration.
- Deploy theo chiến lược canary/blue-green/rolling phù hợp.
- Theo dõi SLO/health và có rollback tới digest trước.

Release promotion không nên phụ thuộc “latest successful artifact” mà không khóa đúng run/source commit. Cần tham chiếu bất biến, ngăn race giữa nhiều builds của cùng branch.

## 20. Giảm thời gian CI mà không mất clean verification

Verification từ môi trường sạch thường chậm hơn developer incremental build. Có thể tối ưu hợp lệ:

1. Tách PR fast checks khỏi release full verification, nhưng release gate vẫn đầy đủ.
2. Dùng JDK/Gradle Wrapper từ runner image tin cậy để giảm setup.
3. Dùng artifact repository proxy/mirror được xác minh.
4. Cache downloaded dependencies theo policy, vẫn bật verification.
5. Tối ưu task inputs/outputs để tasks incremental đúng.
6. Dùng parallel test execution với resource limits và tránh flaky tests.
7. Chia test suites rõ và chạy integration tests theo pipeline phase.
8. Dùng trusted Build Cache cho các jobs được phép, nhưng vẫn chạy clean-room verification theo lịch hoặc trước release quan trọng.
9. Tránh build lại từ source trong deploy job: dùng artifact đã test.
10. Đo median/p95 build times và xem trade-off với supply-chain integrity.

**Không** tối ưu release CI bằng bỏ required tests, tắt dependency verification hoặc cho mọi PR push shared remote cache.

## 21. Troubleshooting: tại sao môi trường sạch phát hiện lỗi?

| Triệu chứng | Nguyên nhân thường gặp | Hướng kiểm tra |
| --- | --- | --- |
| Local build pass, fresh CI fail `file not found` | File/generated source chưa commit | Xem checkout và task generation |
| `gradlew: Permission denied` trên Linux | Wrapper script chưa executable | Commit mode executable đúng trong Git |
| Wrapper jar không hợp lệ | Wrapper file bị sửa hoặc từ nguồn không tin | Validate Wrapper JAR trước Gradle invocation |
| Gradle không tìm Java 17 toolchain | Runner chưa cài JDK/không có resolver | Setup JDK 17 và kiểm tra `javaToolchains` |
| JUnit dependencies không tải được | Repository/network/auth sai | Kiểm `repositories` và Gradle user home |
| `Dependency verification failed` | Artifact checksum/signature không khớp hoặc metadata thiếu | Review artifact source và verification-metadata.xml |
| `Locked version mismatch` | Lockfile khác resolved graph | Review phiên bản, cập nhật lockfile có kiểm soát |
| CI chỉ chạy `jar` không chạy `test` | Task target quá hẹp | Thêm `check`/quality gates phù hợp |
| `test NO-SOURCE` | Source layout hoặc test engine sai | Kiểm `src/test` và reports |
| `BUILD SUCCESSFUL` nhưng `java -jar` fail | Manifest thiếu Main-Class hoặc runtime libs | Kiểm JAR manifest/distribution |
| `NoClassDefFoundError` sau deploy | JAR không chứa runtime dependency | Dùng `distZip`/fat jar/image đúng |
| JAR thiếu resource | Resource source set/Copy task sai | Kiểm `jar tf` và build process |
| Artifact filename sai | Version, archiveBaseName hoặc task output changed | Không hardcode wildcard mơ hồ |
| SHA-256 khác sau upload/download | Artifact bytes bị thay/corrupt/mismatch | Dừng promotion, kiểm artifact store |
| Hai clean builds khác checksum | Timestamp, file order, compiler, generated metadata | Chuẩn hóa reproducible inputs và diff |
| Deploy job tạo JAR mới | Workflow chạy Gradle lại | Chuyển sang download verified artifact |
| Scan security báo lỗi nhưng pipeline vẫn xanh | Job failure không được propagate | Sửa required status checks |
| PR từ fork nhận deploy token | CI secret/permission model sai | Thu hồi/rotate, protected environments |
| Artifact registry trả file sai version | Dùng mutable tag/filename hoặc URL | Pin immutable digest/version |
| CI chậm bất thường ở clean build | Download/daemon/JIT/setup overhead | Tách setup và Gradle execution metrics |
| Build Cache hit nhưng artifact sai | Custom task thiếu inputs hoặc poisoning | Tắt cache, rebuild tin cậy, điều tra |
| App chạy trên CI Java 17 nhưng prod fail | Runtime JDK/OS mismatch | Test deployment runtime target |
| Artifact đúng nhưng runtime config sai | Secret/env/certs ở staging/prod | Giữ binary, kiểm riêng runtime config |
| Git LFS/submodules thiếu | Checkout không đầy đủ | Fetch đúng revision/submodule/LFS objects |
| CI chạy commit khác dự kiến | Branch được cập nhật giữa các jobs | Pin commit SHA và artifact run ID |
| Release bị chặn dù artifact có sẵn | Digest/approval/signature policy fail | Giữ gate, điều tra thay vì bypass |

### 21.1. Debug theo thứ tự

1. Xác định source commit và CI run.
2. Kiểm tra Wrapper/JDK/plugin versions.
3. Kiểm tra checkout đã lấy đầy đủ tracked source/submodules.
4. Xem task graph, tests và reports.
5. Xem dependency locking/verification failures.
6. Kiểm tra JAR/distribution content và manifest.
7. Chạy smoke test với **packaged artifact**, không chỉ `gradle run`.
8. So SHA-256 giữa verified artifact và downloaded artifact.
9. Kiểm signing/attestation/provenance nếu policy có.
10. Chỉ khi tất cả pass mới cho phép deployment.

Không chữa lỗi bằng cách copy `build/libs` từ máy developer hoặc tắt quality gates.

## 22. Các câu hỏi thiết kế trước khi đưa một pipeline vào production

1. Source revision được chọn bằng commit SHA hay mutable branch name?
2. Có thể kiểm chứng runner image/JDK/Wrapper không?
3. Repository có file generated/untracked bắt buộc không?
4. Gradle build scripts/plugins có được review và pin version?
5. Dependency versions và hashes có được quản lý?
6. Build Cache/Configuration Cache được dùng theo policy gì?
7. Required unit/integration tests có chạy thật không?
8. Quality/security scans có fail pipeline khi vi phạm không?
9. Artifact deploy là JAR, distribution hay container image?
10. Pipeline có smoke test **đúng artifact đó** không?
11. Main-Class/launcher, resources và runtime dependencies đủ không?
12. Có xác minh size/digest/manifest của artifact không?
13. Artifact được upload vào store có immutable ID không?
14. Release job có thể download đúng artifact theo CI run/digest không?
15. Digest có gắn với trusted producer/provenance không?
16. Deploy job có vô tình build lại không?
17. Production environment có compatible JDK/OS và secrets riêng không?
18. CI secrets có bị cấp cho untrusted PR không?
19. Deploy có approvals/audit logs theo policy không?
20. Có biết rollback về digest nào khi sự cố không?

## 23. Bài tập thực hành

**Bài tập A — tạo project lab.** Tạo các files Kotlin DSL và Java 17 ở mục 5, chạy `clean check jar`, xác nhận ba JUnit tests chạy và stdout `artifact-verified=true; checksum=55`.

**Bài tập B — kiểm JAR structure.** Chạy `jar tf` và `VerifyJar`, tìm Main-Class và hai class entries. Vì sao cấu trúc đúng vẫn chưa chứng minh runtime startup?

**Bài tập C — thiếu Main-Class.** Trong bản sao build script, bỏ manifest `Main-Class`. `java -jar` báo lỗi gì? Khôi phục trước khi tiếp tục.

**Bài tập D — test fail.** Đổi `Calculator.sumTo` để trả sai cho `n=10`. Vì sao `check` và JUnit phải chặn artifact release?

**Bài tập E — clean vs stale.** Tạo một file output không tracked rồi thử từ fresh checkout. Vì sao clean runner phát hiện được dependency ngầm vào file chưa commit?

**Bài tập F — lockfile.** Bật dependency locking trong một bản sao, tạo lock state có review, sau đó chạy build không có `--write-locks`. Giải thích khi nào lock mismatch làm build fail.

**Bài tập G — dependency verification.** Tạo verification metadata trong môi trường trusted, review hashes và thử build ở chế độ strict. Vì sao không bootstrap checksum trong release job?

**Bài tập H — digest.** Stage JAR vào `verified/app.jar`, tạo `SHA256SUMS` và verify. Sửa một byte trong bản sao rồi thử verify; mô tả failure signal.

**Bài tập I — source SHA.** Tạo disposable clone theo một commit SHA. So kết quả với build từ working tree có file chưa commit và giải thích khác biệt.

**Bài tập J — reproducibility.** Build cùng source ở hai clean environments, so SHA-256 và điều tra timestamps/toolchain nếu khác. Phân biệt reproducibility với behavior correctness.

**Bài tập K — artifact naming.** Thêm một `sourcesJar`, vì sao `build/libs/*.jar` không đủ làm lựa chọn production artifact?

**Bài tập L — promote không rebuild.** Tách CI verify và deploy, để deploy chỉ download artifact. Chỉ ra vì sao `git checkout && ./gradlew jar` trong deploy là anti-pattern.

**Bài tập M — CI YAML.** Cài workflow `verify-artifact.yml` trong một repo thử nghiệm có Wrapper; xác định vai trò của `verify-artifact` và `predeploy`, và vì sao PR job không có deploy secrets.

**Bài tập N — JDK mismatch.** Compile với toolchain Java 17 nhưng chạy `java -jar` trên Java 11. Dự đoán bytecode compatibility failure và cách xác minh target runtime.

**Bài tập O — runtime dependency.** Thêm Commons Lang vào `implementation` của app. Vì sao plain JAR có thể fail `java -jar` nếu không chuyển sang distribution/uber JAR?

**Bài tập P — signing.** Giải thích SHA-256 và digital signature/attestation bảo đảm những yếu tố nào khác nhau.

**Bài tập Q — container.** Chuyển app sang container image: bằng cách nào test/promote đúng **image digest**, không chỉ tag `latest`?

**Bài tập R — incident response.** Sau triển khai phát hiện digest prod khác digest verify; hãy lập hành động containment, xác minh logs, rollback và sửa policy.

**Bài tập S — quality gate zero tests.** Tạm chuyển test source sang thư mục sai. Vì sao `test NO-SOURCE` không phải trạng thái chấp nhận được cho release này?

**Bài tập T — bảo mật CI.** Giả sử một pull request chưa review có thể sửa `build.gradle.kts`. Vì sao không nên inject deploy credentials trong job chạy PR đó?

### Câu hỏi tự kiểm tra

1. Build từ môi trường sạch khác gì `./gradlew clean` trên máy developer?
2. `--no-build-cache` có xóa dependency cache không?
3. `--rerun-tasks` giúp kiểm tra điều gì?
4. Vì sao fresh checkout cần được pin commit SHA?
5. Gradle Wrapper cần được xác minh ở điểm nào của pipeline?
6. Java toolchain 17 khác JVM chạy Gradle ra sao?
7. Tại sao `test NO-SOURCE` có thể là lỗi release gate?
8. `check` có tự chạy mọi integration test trong mọi project không?
9. Vì sao `jar tf` chưa đủ để chứng minh application chạy được?
10. Vì sao `java -jar` nên chạy trên đúng JAR được deploy?
11. Main-Class nằm ở file metadata nào?
12. Plain JAR có tự đóng gói mọi external dependencies không?
13. `application` distribution khác plain JAR thế nào?
14. SHA-256 xác minh điều gì khi expected digest được tin cậy?
15. Có thể tin một JAR cùng hash file do attacker tạo không?
16. Vì sao deploy job không nên rebuild cùng source?
17. Artifact identity khác filename mutable ở đâu?
18. Dependency locking giữ version hay integrity của bytes?
19. `verification-metadata.xml` dùng cho artifact loại nào?
20. Vì sao không chạy `--write-verification-metadata` ở release CI?
21. Reproducible archive settings kiểm soát timestamp/order như thế nào?
22. Hai clean builds có thể khác bytes vì những nguyên nhân nào?
23. Byte-identical khác behavior-equivalent ra sao?
24. Khi promote artifact, checksum khác có chấp nhận được không?
25. CI build artifact có cần chạy security scanner/approval không?
26. Vì sao secrets không nên nhúng vào JAR?
27. Khi dùng container image, nên promote bằng tag hay digest?
28. Tại sao clean CI từ fork không được nhận deploy secrets?
29. Build Scan/Gradle caches có ảnh hưởng độ sạch thế nào?
30. Khi artifact verify fail, hành động đúng trước deployment là gì?

## 24. Tài liệu chính thức

- [Gradle — Testing Java Applications](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Building Java Applications](https://docs.gradle.org/current/userguide/building_java_projects.html)
- [Gradle — Application Plugin](https://docs.gradle.org/current/userguide/application_plugin.html)
- [Gradle — Best Practices for Security and Reproducible Archives](https://docs.gradle.org/current/userguide/best_practices_security.html)
- [Gradle — Securing Dependencies / Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html)
- [Gradle — Locking Dependency Versions](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html)
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html)
- [Gradle — Build Environments](https://docs.gradle.org/current/userguide/build_environment.html)
- [Gradle Actions — Setup Gradle](https://github.com/gradle/actions)
- [GitHub Actions — Upload Artifact](https://github.com/actions/upload-artifact)

**Ghi nhớ:** **Xác minh artifact từ môi trường sạch trước triển khai** nghĩa là lấy đúng source commit trong môi trường được kiểm soát, chạy compile/tests/quality gates, xác minh đúng JAR/distribution/image sẽ deploy, ghi content digest và provenance, rồi **promote chính artifact đã verify** qua staging/production. `clean` và `--no-build-cache` giúp giảm nguy cơ dùng output cũ, nhưng không tự chứng minh dependencies hoặc artifacts an toàn; phải kết hợp dependency locking/verification, smoke tests, hash/signature policy và approvals. Nếu không chứng minh được “artifact được triển khai chính là artifact đã được kiểm tra”, chưa nên phát hành.