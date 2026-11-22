# Chạy ma trận hệ điều hành, JDK hoặc phiên bản Gradle có chủ đích

**Nhóm:** Tích hợp CI/CD — Build Tool Gradle.

## 1. Vì sao cần một ma trận CI thay vì chỉ chạy `./gradlew build`?

Một project Java có thể chạy ổn trên Ubuntu với JDK 21, nhưng gặp lỗi khi chạy trên Windows, macOS, JDK 17 hoặc một phiên bản Gradle được công bố là còn hỗ trợ. Ví dụ:

- Lệnh `./gradlew` chạy trong Bash nhưng không phải cú pháp phù hợp nếu một Windows job dùng PowerShell thuần và cần `.\gradlew.bat`.
- Task đọc `README.md` nhưng repository chỉ có `Readme.md`, nên Windows có thể không lộ lỗi khi Linux báo thiếu file do filesystem case sensitivity.
- JAR được biên dịch bằng JDK 21 dù README nói artifact tương thích Java 17.
- Tests được pin chạy trên Java toolchain 17; thay `JAVA_HOME` trong CI sang Java 21 không có nghĩa tests đã chạy trên Java 21.
- Một Gradle convention plugin dùng API chỉ tồn tại ở Gradle 9 trong khi nhóm vẫn cam kết build được trên Gradle 8.
- Task tự tạo đường dẫn `/tmp`, gọi `grep`/`sed` hoặc nối classpath bằng dấu `:`, gây lỗi trên Windows native shell.
- Một Java version không được Gradle distribution đang thử hỗ trợ để **chạy Gradle**, làm CI fail trước khi project compilation bắt đầu.
- Ma trận có nhiều jobs nhưng toàn bộ chỉ gọi `help` hoặc một `test` task có `NO-SOURCE`; màu xanh không chứng minh compatibility.
- Bật `continue-on-error: true` tùy tiện che lỗi ở nền tảng mà sản phẩm thật sự cam kết hỗ trợ.
- Cho mọi job trong matrix gọi `publish` dẫn tới race condition, trùng artifact coordinates và rò rỉ secrets.

**Ma trận CI là tập các phép thử có mục tiêu**, không chỉ là phép nhân mọi lựa chọn OS × JDK × Gradle. Mỗi ô phải trả lời một câu hỏi tương thích cụ thể và phải có test thực tế để kiểm nó.

Bài này xây một **Java 17 library với Gradle Kotlin DSL**, JUnit tests xác nhận JVM thực tế của Test task, và workflow GitHub Actions chạy một số tổ hợp có chủ đích. Các phần nâng cao giải thích GitLab CI/Jenkins, Gradle TestKit, cache, report, bảo mật và CI gates.

### Kết quả học tập

Bạn sẽ biết:

1. Chọn các trục `os`, `jdk`, `gradle`, `vendor` và `architecture` theo compatibility contract.
2. Phân biệt **JVM chạy Gradle**, **JDK dùng để compile**, **JVM chạy tests**.
3. Chạy baseline bằng Gradle Wrapper và kiểm một Gradle version khác mà không sửa Wrapper.
4. Dựa vào Gradle Java compatibility matrix để tránh những cặp runtime không hợp lệ.
5. Tạo một matrix `include` gồm các tổ hợp có lý do rõ ràng.
6. Dùng GitHub Actions `setup-java`, `setup-gradle`, `checkout`, `upload-artifact`.
7. Chạy thật `check`/JUnit, không chỉ kiểm màu xanh hay `BUILD SUCCESSFUL`.
8. Dùng `fail-fast`, `max-parallel` và `cache-read-only` đúng ngữ nghĩa.
9. Đọc log để phân biệt lỗi OS, compiler, Test JVM, Gradle API và repository.
10. Thiết kế các vòng kiểm nhanh trên PR, đầy đủ trước release và canary định kỳ.

## 2. Ma trận có chủ đích: chọn tập trường hợp, không nhân bừa các trục

Ví dụ team tuyên bố:

- Thư viện biên dịch thành Java 17-compatible bytecode.
- Người dùng chạy code với JDK 17/21; Java 25 là case tương thích tương lai được chủ động kiểm thêm.
- CI chạy trên Ubuntu, Windows và macOS.
- Build dựa vào Gradle Wrapper 9.1.0; build logic vẫn cần có kiểm chứng trên Gradle 8.14.3.

Một ma trận tự động nhân:

```text
OS:       Ubuntu, Windows, macOS              = 3
JVM:      17, 21, 25                          = 3
Gradle:   8.14.3, 9.1.0                       = 2
Tổng:     3 × 3 × 2                           = 18 jobs
```

Nó tạo ra các cặp **Gradle 8.14.3 + JVM 25** không thuộc compatibility chính thức của Gradle; nó cũng lặp nhiều checks giữa OS/JDK khi code không có lý do phụ thuộc những combinations đó.

Một lựa chọn hợp lý hơn:

| Case | Runner OS | JVM chạy Gradle/test | Gradle CLI | Mục đích |
| --- | --- | --- | --- | --- |
| `linux-wrapper-jdk17` | Ubuntu 24.04 | JDK 17 | Wrapper 9.1.0 | Baseline Java 17 |
| `linux-wrapper-jdk21` | Ubuntu 24.04 | JDK 21 | Wrapper 9.1.0 | Runtime mới hơn |
| `windows-wrapper-jdk21` | Windows 2025 | JDK 21 | Wrapper 9.1.0 | Windows paths/shell/filesystem |
| `macos-wrapper-jdk21` | macOS 15 | JDK 21 | Wrapper 9.1.0 | macOS/ARM64 smoke |
| `linux-gradle814-jdk17` | Ubuntu 24.04 | JDK 17 | Gradle 8.14.3 | Older Gradle API compatibility |
| `linux-gradle814-jdk21` | Ubuntu 24.04 | JDK 21 | Gradle 8.14.3 | Old Gradle + supported newer JDK |
| `linux-gradle91-jdk25` | Ubuntu 24.04 | JDK 25 | Gradle 9.1.0 | Java 25 runtime canary |

Đây là **7 case cố định** chứ không phải 18 case. Phiên bản Gradle/JDK và runner labels là **lựa chọn của ví dụ**, không phải câu trả lời rằng đây luôn là release mới nhất. Bạn phải rà support matrix và dependency/plugin versions của repo trước khi dùng.

Tài liệu Gradle xác nhận Java 21 được hỗ trợ chạy Gradle từ **8.5**, Java 25 từ **9.1.0**. Vì thế 8.14.3 + 17/21 và 9.1.0 + 17/21/25 là những cặp có ý nghĩa để thử; không nên đưa Gradle 8.14.3 + JDK25 làm required job rồi coi failure là bug của project.

**Điểm quan trọng nhất của chủ đích:** mỗi ô phải có **một câu “tôi đang kiểm điều gì”**. Nếu không thể viết câu ấy, cân nhắc bỏ ô hoặc chuyển nó sang nightly experiment.

## 3. Phải phân biệt ba loại Java version trong Gradle

| Thành phần | Ai quyết định? | Nó kiểm cái gì? |
| --- | --- | --- |
| **JVM chạy Gradle Daemon** | `JAVA_HOME`/`PATH`, daemon criteria, Gradle runtime settings | Gradle/plugins/build scripts có chạy trên JVM này không |
| **Java compiler toolchain** | `java.toolchain.languageVersion` hoặc task compiler | Bytecode/source compilation target |
| **JVM chạy JUnit tests** | `Test.javaLauncher` hoặc task defaults | Ứng dụng/libraries thực sự hoạt động trên runtime đó không |

Một CI job in:

```bash
java -version
./gradlew --version
```

chỉ xác minh môi trường launcher/Gradle process. **Nó chưa chứng minh JUnit Test task chạy JVM mà matrix yêu cầu.**

Với một Java library hỗ trợ Java 17+, mô hình phù hợp là:

```text
JDK17 compiler
       |
       v
classes target Java 17
       |
       +-- Test JVM17
       +-- Test JVM21
       +-- Test JVM25
```

Để có kết quả này, Gradle build cần:

- Dùng `java.toolchain` Java 17 cho compilation.
- Chọn `Test.javaLauncher` dựa vào CI property `-PtestJdk=...`.
- Có thực sự các JDK installations tương ứng trong runner.
- Có test assertion kiểm `Runtime.version().feature()`, tránh “ma trận giả”.

Một build có thể compile Java 17 trên JDK17 và chạy tests trên JDK21. Không cần compile cùng Java source ba lần bằng JDK17/21/25 nếu mục tiêu chỉ là test một bytecode target trên ba JVM.

### 3.1. Khi nào nên matrix compiler JDK?

Nếu dự án phát triển annotation processor, Gradle plugin, Kotlin compiler integration, code generation hoặc phụ thuộc hành vi `javac`, việc test compiler version có thể quan trọng. Tạo trục `compileJdk` riêng, xác định target bytecode và test tools cụ thể. Đừng nhầm thêm một compiler axis với thêm một runtime axis.

### 3.2. Một vài lệnh xác minh

Linux/macOS:

```bash
java -version
./gradlew --version
./gradlew -q javaToolchains
```

Windows PowerShell:

```powershell
java -version
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
```

- `java -version`: phiên bản Java executable trên `PATH`.
- `gradlew --version`: Gradle distribution và thông tin launcher/Daemon JVM theo Gradle release.
- `javaToolchains`: JDKs Gradle tìm được.
- JUnit `Runtime.version().feature()`: JVM mà **test code thực sự chạy**.

Không suy rằng mọi câu trả lời giống nhau khi có toolchains.

## 4. Gradle Wrapper là baseline, phiên bản Gradle thử nghiệm là trường hợp riêng

Wrapper là cách Gradle khuyến nghị để kiểm soát version trong repository. Những file quan trọng:

```text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.jar
gradle/wrapper/gradle-wrapper.properties
```

Một `gradle-wrapper.properties` có `distributionUrl` kiểu:

```properties
distributionUrl=https\://services.gradle.org/distributions/gradle-9.1.0-bin.zip
```

Đây chỉ là **dòng minh họa**; file Wrapper còn có thể chứa những keys khác và cần được Gradle tạo/duy trì đúng. Đừng tự tạo `gradle-wrapper.jar` bằng text file.

Với project mới chưa có Wrapper, cài Gradle tạm và chạy:

```bash
gradle wrapper --gradle-version 9.1.0 --distribution-type bin
```

Commit Wrapper scripts/JAR/properties. Nếu project đã có Wrapper, dùng wrapper task để nâng version theo quy trình chính thức, kiểm Gradle release notes, Wrapper JAR integrity và source-control changes.

### 4.1. Một lỗi CI rất thường gặp

```yaml
- uses: gradle/actions/setup-gradle@v6
  with:
    gradle-version: '8.14.3'

- run: ./gradlew check
```

**Sai mục tiêu nếu Wrapper vẫn ghim 9.1.0**: dù action provision 8.14.3, gọi `./gradlew` vẫn chọn **Wrapper version**. Đó là lý do workflow mẫu sẽ:

- Với `matrix.gradle == 'wrapper'`: dùng `./gradlew`.
- Với explicit `'8.14.3'` hoặc `'9.1.0'`: dùng CLI `gradle` do setup-gradle đặt trên `PATH`.

Và luôn **in `--version` của chính executable dùng chạy tests**. Một job có label `gradle8` nhưng thực tế đang chạy Gradle9 là **false coverage**.

### 4.2. Không mutate Wrapper từ từng matrix leg

Đừng chạy `./gradlew wrapper --gradle-version=...` ở các matrix jobs chỉ để đổi distribution version. Nó có thể thay source files, làm log/test state khó tái lập và không đại diện commit gốc. Với compatibility matrix, provision explicit Gradle distribution rồi dùng CLI `gradle`.

### 4.3. Bảo mật Wrapper

`gradle/actions/setup-gradle` tự kiểm Wrapper JAR theo tài liệu chính thức. Khi không dùng action này, có thể sử dụng `gradle/actions/wrapper-validation`. Nếu dùng `distributionSha256Sum`, lấy **checksum thật** của exact Gradle distribution từ nguồn chính thức; không tự điền một chuỗi SHA tùy ý.

## 5. Demo project Java 17: mã nguồn và tests thật

Cấu trúc:

```text
gradle-matrix-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── src/main/java/example/math/Calculator.java
├── src/test/java/example/math/CalculatorTest.java
└── .github/workflows/gradle-matrix.yml
```

**Mục đích:** compile thành Java17-compatible library rồi chạy JUnit tests bằng JDK được chọn trong ma trận. Baseline cần Gradle Wrapper hợp lệ, JDK17, Maven Central hoặc corporate mirror để tải JUnit; đây không phải ví dụ offline hoàn toàn.

### 5.1. `settings.gradle.kts`

```kotlin
rootProject.name = "gradle-matrix-lab"
```

### 5.2. Toàn bộ `build.gradle.kts`

```kotlin
plugins {
    `java-library`
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

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

val testJdk = providers.gradleProperty("testJdk")
    .map(String::toInt)
    .orElse(17)

tasks.withType<Test>().configureEach {
    useJUnitPlatform()

    val selected = testJdk.get()

    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(selected))
    })

    systemProperty("expectedTestJdk", selected)

    testLogging {
        events("passed", "failed", "skipped")
    }
}
```

**Giải thích:**

1. `java-library` tạo Java source sets, compile/test tasks, `check` và other Java lifecycle tasks.
2. `mavenCentral` dùng cho test dependencies; với doanh nghiệp, thay bằng mirror được phép và không hardcode credentials.
3. JUnit BOM `5.11.4` ghim một version nhóm JUnit để Jupiter/launcher đồng bộ; đây là một phiên bản **ví dụ**, không phải claim “mới nhất”.
4. `java.toolchain.languageVersion=17` yêu cầu JDK17 compiler toolchain dù Gradle Daemon đang chạy bằng Java21/25.
5. `-PtestJdk=21` là Gradle project property được `providers.gradleProperty` đọc; không có property thì default 17.
6. `Test.javaLauncher` chọn runtime Test JVM theo `testJdk`, không chỉ dựa vào `JAVA_HOME`.
7. `systemProperty("expectedTestJdk", selected)` truyền giá trị dự kiến vào forked test JVM để assertion kiểm đúng runtime.
8. `configureEach` giữ cấu hình Test tasks lazy.
9. Dùng `testJdk.get()` trong Test task configuration lúc task được realized là có chủ đích; nếu project có tổ hợp build logic phức tạp, có thể mô hình hóa Provider sâu hơn.
10. Nếu JDK17 compiler hoặc requested JDK21/25 Test launcher không có sẵn, Gradle sẽ báo không tìm được toolchain; job chưa kiểm được application compatibility.
11. Nếu chỉ chạy `compileJava` mà không chạy `test`/`check`, phép thử JVM runtime chưa diễn ra.

### 5.3. Java source `Calculator.java`

File `src/main/java/example/math/Calculator.java`:

```java
package example.math;

public final class Calculator {
    private Calculator() {
    }

    public static int sum(int a, int b) {
        return Math.addExact(a, b);
    }
}
```

`Math.addExact` là Java API chuẩn, có overflow behavior rõ. Không dùng một Java feature chỉ có từ Java21 khi compile target17.

### 5.4. Java test `CalculatorTest.java`

File `src/test/java/example/math/CalculatorTest.java`:

```java
package example.math;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

final class CalculatorTest {

    @Test
    void addsTwoValues() {
        assertEquals(7, Calculator.sum(3, 4));
    }

    @Test
    void rejectsOverflow() {
        assertThrows(
            ArithmeticException.class,
            () -> Calculator.sum(Integer.MAX_VALUE, 1)
        );
    }

    @Test
    void usesSelectedRuntimeJdk() {
        int expected = Integer.parseInt(
            System.getProperty("expectedTestJdk")
        );
        int actual = Runtime.version().feature();

        assertEquals(
            expected,
            actual,
            "JUnit tests should run on requested Java version"
        );
    }
}
```

**Ba tests có ý nghĩa khác nhau:**

- `addsTwoValues` kiểm business behavior đơn giản.
- `rejectsOverflow` kiểm edge case của library.
- `usesSelectedRuntimeJdk` kiểm chính **môi trường test**, bảo vệ ma trận khỏi việc “chỉ đổi JAVA_HOME nhưng Test.javaLauncher vẫn dùng Java17”.

Nếu `expectedTestJdk=21` mà test thật chạy Java17, phép assert phải fail thay vì job xanh giả.

**Không dùng `JAVA_HOME` trong test làm bằng chứng duy nhất**: Gradle Test task có thể dùng Java launcher khác Gradle process.

### 5.5. Chạy thủ công trước khi thêm CI

Linux/macOS:

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew --no-daemon clean check -PtestJdk=17
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat --no-daemon clean check -PtestJdk=17
```

Khi JUnit dependencies và JDK17 có sẵn, ba tests sẽ PASS. Gradle tạo XML ở `build/test-results/test/` và HTML `build/reports/tests/test/index.html`. Đây là **kỳ vọng của ví dụ**, không phải kết quả được tuyên bố là đã chạy trên CI.

Nếu có JDK21 được Gradle phát hiện:

```bash
./gradlew --no-daemon clean check -PtestJdk=21
```

Java compiler vẫn là17, tests chạy21. Khi yêu cầu `-PtestJdk=25` và chỉ cài JDK17, Gradle sẽ fail vì thiếu requested test launcher trừ khi toolchain auto-provisioning được cấu hình đúng.

## 6. GitHub Actions workflow đầy đủ cho ma trận 7 case

Tạo `.github/workflows/gradle-matrix.yml`:

```yaml
name: Gradle compatibility matrix

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  compatibility:
    name: ${{ matrix.case }}
    runs-on: ${{ matrix.os }}
    timeout-minutes: 30

    strategy:
      fail-fast: false
      max-parallel: 4
      matrix:
        include:
          - case: linux-wrapper-jdk17
            os: ubuntu-24.04
            jdk: '17'
            gradle: 'wrapper'
            cacheWriter: true

          - case: linux-wrapper-jdk21
            os: ubuntu-24.04
            jdk: '21'
            gradle: 'wrapper'
            cacheWriter: false

          - case: windows-wrapper-jdk21
            os: windows-2025
            jdk: '21'
            gradle: 'wrapper'
            cacheWriter: false

          - case: macos-wrapper-jdk21
            os: macos-15
            jdk: '21'
            gradle: 'wrapper'
            cacheWriter: false

          - case: linux-gradle814-jdk17
            os: ubuntu-24.04
            jdk: '17'
            gradle: '8.14.3'
            cacheWriter: false

          - case: linux-gradle814-jdk21
            os: ubuntu-24.04
            jdk: '21'
            gradle: '8.14.3'
            cacheWriter: false

          - case: linux-gradle91-jdk25
            os: ubuntu-24.04
            jdk: '25'
            gradle: '9.1.0'
            cacheWriter: false

    steps:
      - name: Checkout source
        uses: actions/checkout@v7

      - name: Install compiler and test JDKs
        uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: |
            17
            ${{ matrix.jdk }}

      - name: Setup Gradle, validate Wrapper
        uses: gradle/actions/setup-gradle@v6
        with:
          gradle-version: ${{ matrix.gradle }}
          cache-read-only: ${{ github.ref != 'refs/heads/main' || !matrix.cacheWriter }}

      - name: Verify actual versions
        shell: bash
        env:
          GRADLE_SELECTION: ${{ matrix.gradle }}
        run: |
          java -version
          if [ "$GRADLE_SELECTION" = "wrapper" ]; then
            ./gradlew --version
            ./gradlew -q javaToolchains
          else
            gradle --version
            gradle -q javaToolchains
          fi

      - name: Compile Java 17 and execute JUnit tests
        shell: bash
        env:
          GRADLE_SELECTION: ${{ matrix.gradle }}
          TEST_JDK: ${{ matrix.jdk }}
        run: |
          if [ "$GRADLE_SELECTION" = "wrapper" ]; then
            ./gradlew --no-daemon --stacktrace --console=plain \
              clean check -PtestJdk="$TEST_JDK"
          else
            gradle --no-daemon --stacktrace --console=plain \
              clean check -PtestJdk="$TEST_JDK"
          fi

      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: junit-${{ matrix.case }}
          path: |
            build/test-results/test/*.xml
            build/reports/tests/test/**
          if-no-files-found: warn
          retention-days: 7
```

**Điều kiện để workflow chạy được:** source/Wrapper phải có như phần 5, JUnit dependencies truy cập được, GitHub-hosted runner labels còn có sẵn, Git Bash trên Windows runner hoạt động. Nếu dùng runner Windows self-hosted không có Bash, cần tách PowerShell step như phần 9.2.

Phiên bản actions major ở đây phản ánh ví dụ GitHub/Gradle hiện hành khi biên soạn; trong production cần đối chiếu changelog và tổ chức có thể pin action commit SHA. `actions/upload-artifact@v4` là một version major được chọn rõ, không nên gắn hai upload steps từ nhiều jobs vào cùng một artifact name.

### 6.1. `matrix.include` tạo đúng bảy jobs

Mỗi record có `case`, `os`, `jdk`, `gradle` và `cacheWriter`. Không có `os: [...]`/`jdk: [...]` ở ngoài khiến CI vô tình tạo thêm Cartesian product. Xem GitHub Actions run page để đếm đúng **7 matrix legs**.

### 6.2. `fail-fast:false` không biến lỗi thành PASS

Khi một leg fail, GitHub vẫn cho các legs khác chạy để thu đủ kết quả. Không có `continue-on-error:true` trong workflow baseline; vì vậy failing leg là failure thật và phải được xét trong required checks.

Nếu cần job experimental trên JDK Early Access, tạo case/cột `experimental` được định nghĩa cho mọi entry rồi thiết kế `continue-on-error: ${{ matrix.experimental }}` **ở cấp job**, không đặt tùy tiện trong `strategy`. Không đặt toàn bộ matrix thành non-blocking chỉ vì một canary.

### 6.3. `max-parallel:4` giới hạn concurrency

Có bảy jobs, nhiều nhất bốn jobs chạy đồng thời trong scope matrix. Nó kiểm soát runner quota/chi phí/network, **không** giảm số phép thử. Hãy chọn con số theo organization capacity, không mặc định “4 nhanh nhất”.

### 6.4. Vì sao cài `17` và `matrix.jdk` cùng lúc?

`setup-java@v6` hỗ trợ nhiều JDK versions qua multiline input; bản được cài cuối thường trở thành default trên `PATH`. Do đó:

- JDK17 luôn có mặt để compiler toolchain Java17 không thiếu.
- JDK21 hoặc25 có mặt khi Test launcher yêu cầu.
- Default CLI Java trong mỗi matrix leg khớp JDK variable, nếu không có Gradle JVM override.
- Dòng `-PtestJdk="$TEST_JDK"` chọn chính runtime Test JVM.
- Trùng JDK17 trong case JDK17 có thể được setup-java xử lý. Khi cần tối ưu/cấu hình phức tạp, tách setup-java JDK17 và setup-java matrix JVM có điều kiện.

**Không dựa vào `java -version` để xác nhận JUnit đã dùng requested Java:** test `usesSelectedRuntimeJdk` là bước kiểm chứng thứ hai.

### 6.5. Vì sao có hai Gradle executables?

`gradle/actions/setup-gradle` hỗ trợ `gradle-version: 'wrapper'` hoặc explicit versions. Nếu sử dụng explicit version, action cấp CLI `gradle` trên `PATH`. Wrapper luôn đi theo `distributionUrl` trong repo.

```bash
# Wrapper baseline:
./gradlew --version
./gradlew check

# Explicit Gradle 8.14.3 sau setup-gradle provision:
gradle --version
gradle check
```

Đừng gọi `./gradlew` cho tất cả jobs rồi tưởng trục Gradle đã được kiểm. Script mẫu kiểm `GRADLE_SELECTION` và gọi executable thích hợp.

### 6.6. Tại sao dùng `clean check`?

`check` yêu cầu verification tasks, trong demo có ba JUnit tests. `clean` giúp tạo baseline không dựa vào local outputs từ invocation trước. Các GitHub-hosted runners thường có workspace mới nên `clean` có thể dư, nhưng nó rõ ràng cho compatibility test.

Đừng dùng `-x test` để “tăng tốc” ma trận: lúc đó JDK runtime trục có thể không còn được thử. Nếu muốn test packaged JAR, có thể dùng `build` hoặc `jar` bên cạnh `check`; trong demo mục tiêu là compatibility tests.

### 6.7. Test artifacts theo đúng case

`if: always()` cố gắng upload reports kể cả khi `check` fail. Artifact name `junit-${{ matrix.case }}` tránh trùng trên nhiều legs. Nếu lỗi ở giai đoạn setup Java/Gradle và chưa tạo reports, `if-no-files-found: warn` phát cảnh báo; job logs vẫn chứa thông tin chính.

Với nhiều Gradle subprojects, đổi pattern thành `**/build/test-results/**/TEST-*.xml` và `**/build/reports/tests/**` nếu phù hợp. Tránh upload entire build directory trong các PR workflows vì có thể có temporary files hoặc secrets.

### 6.8. Cache trong matrix

`cache-read-only` từ `setup-gradle` được bật cho tất cả cases ngoài một primary writer trên `main`. Điều đó giảm khả năng nhiều jobs cùng ghi cache và giữ PR/fork jobs read-only.

Không bật đồng thời `actions/setup-java cache: gradle` trong workflow nếu `gradle/actions/setup-gradle` đã quản lý Gradle User Home caching; hai cache controllers có thể gây hành vi khó đo. Build cache của Gradle và CI cache của GitHub Actions cũng là những cơ chế khác nhau.

## 7. Vì sao `include` tốt hơn một ma trận tự nhân mọi trục?

Phản ví dụ:

```yaml
strategy:
  matrix:
    os: [ubuntu-24.04, windows-2025, macos-15]
    jdk: ['17', '21', '25']
    gradle: ['8.14.3', '9.1.0']
```

Tạo 18 jobs, gồm cả Gradle8.14.3/JDK25 unsupported. Có thể dùng `exclude`:

```yaml
strategy:
  matrix:
    os: [ubuntu-24.04, windows-2025, macos-15]
    jdk: ['17', '21', '25']
    gradle: ['8.14.3', '9.1.0']
    exclude:
      - jdk: '25'
        gradle: '8.14.3'
```

Nhưng nó vẫn tạo nhiều jobs hơn cần nếu bạn chỉ muốn cặp Gradle8 trên Linux. Với **curated cases** và tập mục tiêu nhỏ, dùng `include` liệt kê từng case đầy đủ sẽ dễ review hơn.

### 7.1. `exclude` khác `continue-on-error`

- `exclude`: bỏ một combination, **không chạy job đó**.
- `continue-on-error`: **có chạy job**, nhưng job failure có thể không làm workflow tổng fail.
- `fail-fast:false`: một job fail không tự cancel các matrix jobs còn lại.
- `max-parallel`: giới hạn jobs chạy đồng thời.
- `timeout-minutes`: ngăn jobs treo chiếm tài nguyên quá lâu.

Không dùng `exclude` để giấu một supported combination hiện đang đỏ mà vẫn quảng cáo hỗ trợ nó.

### 7.2. Dùng version pins thay `latest` tùy tiện

`setup-java` có thể nhận `java-version: latest`; `setup-gradle` có alias `current`, `release-candidate` hoặc `nightly`. Các aliases hữu ích cho canary nhưng biến đổi theo thời gian. Với required checks, pin các major/versions rõ ràng để lỗi phản ánh source thay đổi chứ không phải một tool version tự cập nhật không kiểm soát.

Nếu muốn biết Gradle release candidate sắp gây breaking change, tạo **nightly experimental job riêng** có owner, báo cáo và threshold nâng baseline.

## 8. Chạy tests trên Windows/macOS đúng ngữ nghĩa

### 8.1. Windows shell

Workflow mẫu dùng `shell: bash` cho mọi runner, kể cả Windows. GitHub-hosted Windows runners có Git Bash nên `./gradlew` thường hoạt động. Với Windows self-hosted runner không cài Bash, thay bằng PowerShell-native:

```yaml
- name: Test with Wrapper on Windows
  if: runner.os == 'Windows'
  shell: pwsh
  run: |
    .\gradlew.bat --version
    .\gradlew.bat --no-daemon --console=plain check -PtestJdk=21

- name: Test with Wrapper on Unix
  if: runner.os != 'Windows'
  shell: bash
  run: |
    ./gradlew --version
    ./gradlew --no-daemon --console=plain check -PtestJdk=21
```

**Đây là một phương án minh họa cho workflow chỉ dùng Wrapper**, chưa giải quyết explicit Gradle version branch. Khi dùng trong full matrix, thay Java21 hardcoded bằng giá trị matrix, và với explicit Gradle version dùng CLI `gradle` thay vì Wrapper ở cả hai OS.

Lệnh CLI khác nhau:

- Bash/Linux/macOS: `./gradlew check`.
- Windows PowerShell: `.\gradlew.bat check`.
- Windows cmd.exe: `gradlew.bat check`.
- Windows Git Bash: `./gradlew check` khi Wrapper script khả dụng.

### 8.2. Đường file, case và line endings

Gradle Kotlin DSL và Java APIs giúp giảm OS-specific path bugs:

```kotlin
val inputFile = layout.projectDirectory.file("src/main/resources/config.txt")
val outputFile = layout.buildDirectory.file("generated/report.txt")
```

Thay vì hardcode:

```kotlin
val outputFile = "/tmp/report.txt" // sai giả định trên Windows
```

Dùng `java.nio.file.Path`/`Files` khi viết Java code và Gradle `RegularFileProperty`/`DirectoryProperty` trong tasks. Tránh nối các path segments bằng string `"/"` hoặc `"\\"` tùy tiện; filesystem rules/case sensitivity khác nhau.

Tình huống cần test:

- `README.md` khác `readme.md` về case trên Linux.
- CRLF vs LF trong text assertions.
- Java source/test dùng `StandardCharsets.UTF_8` thay default charset.
- Timestamp và timezone-dependent tests nên inject `Clock` thay dùng current time tùy hệ thống.
- Locale: dùng `Locale.ROOT` cho transformations phải tái lập.
- Shell commands: `grep`/`sed`/`rm` không có sẵn trong PowerShell native.
- Java `-cp` dùng dấu `:` trên Unix, dấu `;` trên Windows; Gradle `JavaExec`/`Test` nên tự xây classpath.

### 8.3. macOS ARM64 không phải macOS Intel

Runner label `macos-15` hiện thường chỉ macOS ARM64; `macos-15-intel` dành cho Intel nếu cần. Với pure Java, một macOS smoke có thể đủ. Với JNI/native components hoặc native image, OS **và architecture** là hai trục cần thử; không thể tuyên bố hỗ trợ cả arm64/x64 khi chưa test.

Vì runners có thể thay đổi trong tương lai, luôn xem [GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners) khi review workflow.

## 9. Bộ kiểm chứng thực tế: tránh ma trận “xanh giả”

Một job PASS phải đáp ứng tối thiểu:

1. Runner OS đúng case đã định.
2. `java -version` in JVM dự kiến.
3. Gradle distribution thực sự đúng Wrapper/explicit case.
4. JDK17 compile toolchain đã được Gradle tìm thấy.
5. Test JVM đúng `-PtestJdk`, chứng minh bằng assertion.
6. `test` thực sự chạy ba methods, không `NO-SOURCE`/`SKIPPED`.
7. Report XML/HTML được tạo khi Test task hoàn tất.
8. Không dùng `-x test` hay `continue-on-error` che failure.
9. Artifacts mang tên chứa case cụ thể.
10. Không publish/deploy khi chưa có release gate.

Bảng oracle dự kiến:

| Case | Compiler | Gradle runtime/Test JVM | Gradle distribution | Kỳ vọng |
| --- | --- | --- | --- | --- |
| Linux Wrapper 17 | 17 | 17 | Wrapper 9.1.0 | JUnit 3/3 |
| Linux Wrapper 21 | 17 | 21 | Wrapper 9.1.0 | JUnit 3/3 |
| Windows Wrapper 21 | 17 | 21 | Wrapper 9.1.0 | JUnit 3/3 |
| macOS Wrapper 21 | 17 | 21 | Wrapper 9.1.0 | JUnit 3/3 |
| Linux Gradle8 17 | 17 | 17 | 8.14.3 | JUnit 3/3 |
| Linux Gradle8 21 | 17 | 21 | 8.14.3 | JUnit 3/3 |
| Linux Gradle9 25 | 17 | 25 | 9.1.0 | JUnit 3/3 |

**Đây là kết quả mong đợi, chưa phải log một workflow đã được chạy.** Nếu setup Java, Gradle distribution, repository hoặc third-party plugins fail, cần điều tra. Không tuyên bố “all platform support verified” chỉ từ code review YAML.

### 9.1. Một job có `BUILD SUCCESSFUL` nhưng vẫn không đủ

Trường hợp Java project chưa có test files:

```text
> Task :test NO-SOURCE
BUILD SUCCESSFUL
```

Nếu bạn muốn kiểm JDK runtime compatibility, job như vậy chưa test gì. Vì thế demo có ba JUnit tests và assertion Test JVM.

Tương tự, task `compileJava` PASS chứng minh compile, không chứng minh application runtime Java21. Task `help` PASS chứng minh Gradle có thể load basic settings, không chứng minh plugin code/tasks/test behavior.

### 9.2. Nếu packaging là contract

`check` không nhất thiết tạo `jar`. Khi cần xác minh binary distribution, có thể chạy:

```bash
./gradlew --no-daemon build -PtestJdk=17
jar tf build/libs/gradle-matrix-lab-1.0.0.jar
```

Đây là test package riêng nếu build script Java library mặc định tạo JAR theo project name/version. Nếu project đã chỉnh artifact ID/archive naming, phải dùng exact artifact path tương ứng. Đừng suy một JAR có mặt chỉ vì test succeeded.

### 9.3. Java class file compatibility

Java17 class file major version thông thường là **61**. Có thể kiểm bằng `javap -verbose` trên compiled class:

```bash
javap -verbose build/classes/java/main/example/math/Calculator.class
```

Tìm dòng `major version: 61` trong output. Điều này hỗ trợ chứng minh bytecode target, **không thay cho test runtime** và cũng không đảm bảo public API không vô tình dùng runtime-specific dependencies.

## 10. Thực hành matrix Gradle version đúng cách

### 10.1. Tại sao Gradle8 và Gradle9 có giá trị?

Với shared Gradle build logic hoặc plugin, Gradle version là một phần hợp đồng. Một plugin có thể:

- Dùng API chỉ có từ Gradle9.
- Bị xóa deprecated API ở Gradle9.
- Có Kotlin DSL/embedded Kotlin behavior khác.
- Có task validation nghiêm ngặt hơn ở version mới.
- Có configuration cache restrictions thay đổi.
- Có dependency resolution/module metadata semantics liên quan version.
- Sử dụng JVM bytecode quá mới so với JVM Gradle8 có thể chạy.

Vì vậy chạy actual Gradle8.14.3 và9.1.0 có thể phát hiện lỗi build tooling dù Java source của application không đổi.

### 10.2. Gradle plugin nên test qua consumer build

Đơn thuần chạy `./gradlew test` trong plugin source không chắc test plugin apply thành công trên Gradle8/9. Dùng Gradle TestKit với consumer fixture:

```java
GradleRunner runner = GradleRunner.create()
    .withProjectDir(testProjectDir)
    .withPluginClasspath()
    .withGradleVersion("8.14.3")
    .withArguments("help", "--stacktrace");

BuildResult result = runner.build();
```

Đây là **một snippet**, cần imports, fixture directory, plugin-under-test classpath và assertions. `withGradleVersion(...)` chọn Gradle distribution cho nested build; nó **không thay OS** và không tự chọn Java runtime khác. TestKit bổ trợ cho CI matrix, không thay thế các OS-specific cases.

### 10.3. Không phải Java app nào cũng cần Gradle8 compatibility

Nếu người dùng chỉ tải JAR của bạn và không tự build source, việc kiểm Gradle8 có thể chỉ phục vụ build engineers. Nếu bạn công bố plugin hoặc Gradle starter template được consumer build trực tiếp, Gradle version là contract rõ hơn. Chọn các trường hợp theo người dùng thực tế, không theo số lượng jobs.

## 11. Dùng `fail-fast`, `continue-on-error` và required checks đúng chính sách

### 11.1. `fail-fast:false`

Giúp các matrix jobs còn lại được chạy khi một job thất bại, mang lại đủ evidence để biết lỗi độc lập theo OS hay xảy ra khắp nơi. Không có nghĩa failures được chấp nhận.

### 11.2. `continue-on-error` chỉ cho thử nghiệm

Có thể có canary:

```yaml
strategy:
  fail-fast: false
  matrix:
    include:
      - case: stable
        jdk: '21'
        experimental: false
      - case: future-jdk
        jdk: '27'
        experimental: true

continue-on-error: ${{ matrix.experimental }}
```

Đây là **mẫu minh họa policy**, chưa có `runs-on`, `setup-java` hoặc version Gradle tương thích với JDK27; không copy làm workflow standalone. Điểm chính: `continue-on-error` nằm **ở cấp job**, và `experimental` là boolean cho mọi record.

Với JDK27, cần Gradle release có hỗ trợ Java27 (theo compatibility matrix), runner/JDK distribution tương ứng. Không thêm một canary unsupported rồi gọi đó là future compatibility test.

### 11.3. Required check names và branch protection

Nếu branch protection yêu cầu một matrix job name cũ, đổi tên `matrix.case` hoặc thay số legs có thể khiến GitHub check status không còn khớp. Sau khi thay matrix, review required checks. Có thể thiết kế **aggregate gate job** với tên ổn định, phụ thuộc matrix jobs và fail nếu required matrix result fail; nhưng phải dùng proper `needs`/`if: always()` và assertions, không in một dòng “green” cố định.

### 11.4. Không cho mọi matrix leg publish

```text
PR
 |
 +----> selected compatibility jobs
 |           |
 |           +----> reports and required checks
 |
 +----> protected release gate
             |
             +----> one controlled publish/signing job
```

Đừng gọi `publish`/`deploy` trên từng OS/JDK matrix job. Nhiều jobs có thể ghi trùng Maven coordinate hoặc expose publishing credentials tới PR untrusted source. Nếu native artifacts phải build theo OS/architecture, mỗi leg tạo artifact độc nhất, promotion/publish tập trung ở job riêng.

## 12. Caching, secrets và supply-chain security

### 12.1. Gradle caching

`gradle/actions/setup-gradle@v6` hỗ trợ `cache-read-only`, và workflow chọn một primary writer ở `main`. Các non-primary legs và PRs chỉ đọc caches. Cấu hình như vậy giảm cạnh tranh cache updates.

**Phân biệt:**

- GitHub Actions cache: lưu Gradle User Home/downloads theo action.
- Gradle build cache: tái sử dụng task outputs khi task cacheable và input fingerprints khớp.
- Gradle configuration cache: tái sử dụng configured task graph, có thể chứa sensitive configuration data.
- Gradle Wrapper distribution: Gradle executable version ghim trong repo.
- JDK toolcache: các JDK installations trên runners.

Không trộn tất cả thành “một cache”. Nếu custom task bỏ sót input, cached output có thể sai trên một OS/JDK khác; lỗi nằm ở task input modeling, không nên “chữa” bằng việc bỏ compatibility checks.

### 12.2. Không dùng hai controllers cache Gradle song song

`actions/setup-java` cũng có `cache: gradle`, nhưng workflow đã dùng `setup-gradle`; vì vậy không bật Gradle caching thêm ở setup-java. Hai controllers cùng restore/save Gradle User Home có thể gây xung đột hoặc làm khó debug.

### 12.3. Security cho PRs

- Dùng `permissions: contents: read` khi chỉ checkout và test.
- Không đưa Maven publishing token, GPG/signing key, cloud secret vào PR jobs.
- Tránh `pull_request_target` + checkout fork code rồi chạy Gradle dưới quyền có secrets.
- Không in Gradle debug logs chứa credentials trong artifact public.
- Không tắt Wrapper validation để “cho qua” một checksum mismatch.
- Pin actions theo commit SHA nếu security policy yêu cầu; major tags trong tài liệu dễ đọc nhưng có thể di chuyển.
- Nếu dùng remote build cache/configuration cache có encryption key, tuân thủ Gradle documentation/security policy.
- Chỉ upload test reports cần thiết, không upload toàn bộ `~/.gradle` hoặc các files cấu hình nhạy cảm.
- Với proxy/private Maven repository, dùng scoped credentials từ secrets ở trusted workflow chứ không commit trong `build.gradle.kts`.

### 12.4. Tái lập build

Pin:

1. Gradle Wrapper `distributionUrl` và optional official SHA256.
2. Gradle explicit matrix versions.
3. Java vendor + major/patch policy.
4. Runner image labels và architecture.
5. Test dependencies/JUnit BOM/plugins.
6. Repo revision/commit; không dùng arbitrary branch HEAD của included builds.
7. Maven repositories/mirrors và dependency verification khi tổ chức yêu cầu.
8. Actions versions/SHA.
9. Test properties/timezone/locale khi ảnh hưởng correctness.

Không có nghĩa khóa mọi thứ mãi mãi; cập nhật theo PR review và chạy compatibility tests trước khi đổi baseline.

## 13. Chẩn đoán lỗi theo một quy trình nhất quán

### 13.1. Lỗi khởi động Gradle

Ví dụ:

```text
Unsupported class file major version
Gradle requires a JVM version ...
```

Cần kiểm:

- `java -version` và `gradle --version`.
- Gradle Java runtime compatibility, **không** chỉ Java toolchain compatibility.
- Một plugin có bytecode version vượt JVM Daemon hay không.
- Các build scripts/plugins có yêu cầu Gradle mới hơn không.
- Bạn đã gọi đúng `gradle` hay vô tình chạy Wrapper?
- Logs có chỉ đúng executable path/version?

Nếu combination unsupported, sửa matrix: dùng Gradle version hỗ trợ JVM đó hoặc chọn JVM supported. Không dùng `continue-on-error` để giả vờ product hỗ trợ.

### 13.2. Lỗi toolchain missing

```text
No matching toolchains found
No locally installed toolchains match requested specification
```

Kiểm `./gradlew -q javaToolchains`, `setup-java` multiline installation, `java.toolchain=17` và `-PtestJdk`. Nếu project compile17/test25, runner phải có cả JDK17 và JDK25 hoặc provisioning được cấu hình hợp lệ.

### 13.3. Lỗi Test JDK không đúng

Nếu `usesSelectedRuntimeJdk` fail:

- Kiểm `expectedTestJdk` được truyền qua `Test.systemProperty`.
- Kiểm `Test.javaLauncher` có bị plugin khác override không.
- Kiểm `-PtestJdk` có truyền thật từ CI matrix không.
- Kiểm test process/Gradle Daemon có dùng cùng JVM hay khác.
- Kiểm JDK installation Gradle chọn.

Không sửa assertion thành `>=17` để cho test pass; làm vậy đánh mất ý nghĩa runtime matrix.

### 13.4. Lỗi Windows/macOS

- PowerShell không nhận lệnh `./gradlew`: chuyển đúng shell hoặc `.\gradlew.bat`.
- `Permission denied` trên Linux/macOS: kiểm Git executable bit của `gradlew` và line endings.
- File name khác case: kiểm source và Gradle path đúng.
- Dấu phân tách classpath không đúng: dùng Gradle/JavaExec.
- CRLF/LF gây failed assertion: so spec/normalized data có chủ đích.
- JNI/native dependency không có artifact tương ứng ARM64: kiểm architecture axis và vendor releases.
- Default timezone/locale khác: pin hoặc inject clock/locale trong tests.
- Path length/file locks trên Windows: kiểm thư mục temp và process handles.

### 13.5. Lỗi chỉ Gradle8

- Gradle plugin/build logic đã dùng API Gradle9-only?
- Gradle8 có hỗ trợ JDK đang chạy không?
- Kotlin DSL DSL syntax tương thích không?
- Plugin third-party đang yêu cầu min Gradle9?
- Task validation/caching API khác?
- Dependencies yêu cầu Java runtime mới hơn?
- Hãy dùng TestKit consumer fixture với Gradle8.14.3 để có regression test cụ thể.

### 13.6. Không có JUnit reports

Nếu Gradle fail khi download JDK/distribution, không có reports là bình thường. Nếu Gradle chạy `test NO-SOURCE`, kiểm file `src/test/java/example/math/CalculatorTest.java` và JUnit engine. Nếu `test SKIPPED`, kiểm `onlyIf`/`enabled`/`-x test`. Nếu test có chạy nhưng `upload-artifact` không thấy file, kiểm path glob và working directory.

## 14. Tổng hợp lỗi theo bảng

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Java25 + Gradle8 fail trước compilation | Unsupported Gradle/JVM runtime combination | Bỏ combo, dùng Gradle9.1+ cho Java25 |
| Gradle8 job vẫn report 9.1 | Gọi `./gradlew` dù setup explicit Gradle8 | Dùng `gradle` CLI và log version |
| CI reports Test JVM17 trong case JDK21 | Toolchain/test launcher cố định17 | Cấu hình `Test.javaLauncher` từ matrix |
| Test task `NO-SOURCE` | Không có JUnit files/source set | Tạo tests và verify execution |
| Windows wrapper fail | Shell/Wrapper file syntax | Git Bash hoặc `.\gradlew.bat` |
| Linux file missing, Windows pass | Case-sensitive path mismatch | Sửa tên file chính xác |
| macOS Apple Silicon fail | Thiếu native arm64 binary | Thêm architecture coverage/native artifact |
| Compiler Java target21 | Compiler toolchain không pin17 | `java.toolchain=17`, kiểm class major61 |
| Gradle plugin chỉ fail trên Gradle8 | Dùng newer API/third-party plugin | TestKit regression, điều chỉnh min version |
| Gradle jar build pass, test fail Java25 | Runtime behavior/third-party incompatibility | Minimal reproduction và dependency audits |
| CI xanh nhưng release JAR sai | Check chỉ tests, packaging khác | Test `build`/`jar` và bytecode target |
| Matrix jobs cancel lẫn nhau | `fail-fast`/workflow concurrency | Kiểm strategy policy |
| Artifacts upload collision | Cùng tên cho nhiều matrix legs | Unique `junit-${{ matrix.case }}` |
| Không tìm thấy report | Job fail trước Test hoặc path sai | Đọc stage logs, glob và working dir |
| PR không có required check | Job name/filter thay đổi | Review branch protection |
| Tất cả PR jobs cache writes | Không phân biệt writer/read-only | `cache-read-only` theo trust/branch |
| CI fail khi Maven repo 403 | Credentials/proxy/mirror | Sửa repository access, không tắt tests |
| Performance rất khác giữa OS | Runner hardware/caches/FS | Không dùng matrix times làm benchmark tuyệt đối |
| Mac/Windows chưa được test mà README tuyên bố có | Coverage contract sai | Bổ sung OS case hoặc sửa claim |
| All jobs pass nhưng app chưa test | Chỉ chạy `help`/`compileJava` | Chạy `check`/tests có assertions |
| Published artifact fail ở consumer | Chỉ test local project, không test publication metadata | Consumer integration test độc lập |

## 15. Kiểm coverage thật trước khi báo “hỗ trợ”

Sau một GitHub Actions run:

1. Đếm đủ các case mà bạn định chạy.
2. Kiểm mỗi job có correct runner label/architecture.
3. Xem `java -version` và Gradle executable `--version`.
4. Xác minh compiler17 availability và test launcher target.
5. Xem task `test` không `NO-SOURCE`/`SKIPPED`.
6. Xem JUnit XML tests/failures, không chỉ status xanh.
7. Kiểm `expectedTestJdk` assertion PASS ở từng case.
8. Với Gradle8, kiểm thật `gradle --version` báo8.14.3.
9. Với Windows, xem shell/path behavior và tests.
10. Với macOS ARM, đừng ghi claim Intel coverage.
11. Với build logic/plugin, thêm TestKit consumer verification.
12. Với release, chạy packaged artifact consumer test nếu contract yêu cầu.
13. Không gọi canary pass khi nó `continue-on-error` và test thực sự failed.
14. Ghi rõ OS/JDK/Gradle combinations chưa được thử.

Một báo cáo đúng:

> “Java17 bytecode build và ba JUnit tests đã pass trên Ubuntu/JDK17, Ubuntu/JDK21, Windows/JDK21 và macOS/JDK21 cùng Wrapper version đã ghim; Gradle8.14.3 compatibility pass trên Ubuntu/JDK17 và21; Java25 runtime test pass trên Gradle9.1.0/Ubuntu. Các tổ hợp khác chưa nằm trong required matrix.”

Đây là **ví dụ mẫu văn bản báo cáo khi jobs thực sự thành công**, không phải kết quả mà bài viết tuyên bố đã chạy.

## 16. Dùng GitLab CI hoặc Jenkins như thế nào?

Ý tưởng chung không đổi: **mỗi case phải provision đúng toolchains và thực thi đúng Gradle/test command**.

### 16.1. GitLab CI

GitLab hỗ trợ `parallel:matrix`. Một snippet:

```yaml
stages: [test]

compatibility:
  stage: test
  parallel:
    matrix:
      - JAVA_RUNTIME: ["17", "21"]
  image: eclipse-temurin:17-jdk
  script:
    - java -version
    - chmod +x ./gradlew
    - ./gradlew --no-daemon check -PtestJdk=17
```

**Đây là phản ví dụ một matrix chỉ có nhãn**, chưa kiểm Java21: Docker image JDK17 và lệnh vẫn chọn `testJdk=17`. Để làm đúng, GitLab runner/container cần cài **JDK17 compiler và JDK tương ứng `JAVA_RUNTIME`**, rồi truyền `-PtestJdk=$JAVA_RUNTIME`. Có thể build một CI image tin cậy chứa nhiều JDKs hoặc dùng executor/job images phù hợp với toolchain provisioning. Windows/macOS cần runners phù hợp, không thể tự có chỉ nhờ sửa `JAVA_RUNTIME` trên Linux container.

### 16.2. Jenkins

Jenkins Declarative Pipeline có matrix axes; định nghĩa `OS`, `JDK` và agents tương ứng. Nhưng `echo` hai axis values chưa phải test. Mỗi node phải có đúng JDK installations, checkout, Gradle Wrapper/explicit distribution, shell chọn `sh` hoặc `bat` và `check` thực sự chạy.

Ví dụ orchestration về mặt ý tưởng:

```text
Jenkins matrix:
  linux × JDK17  -> ./gradlew check -PtestJdk=17
  linux × JDK21  -> ./gradlew check -PtestJdk=21
  windows × JDK21 -> gradlew.bat check -PtestJdk=21

Nếu cần Gradle8:
  provision Gradle8.14.3 -> gradle check
```

Đây là **task plan**, không phải một Jenkinsfile executable. Các plugins/agent labels/environment tool installations của Jenkins phụ thuộc server công ty, nên không thể giả định mỗi node đều giống GitHub-hosted runner.

### 16.3. Kỹ thuật nào thuộc Gradle, kỹ thuật nào thuộc CI?

- CI quyết định **OS/JDK/Gradle version combination** và runner.
- Gradle Wrapper/installation quyết định distribution thực thi.
- Gradle build script quyết định **compiler/test toolchain**.
- Gradle `check`/`test` quyết định verification work.
- CI quyết định job gating, caching, artifacts retention và release workflow.

Giữ các ranh giới này rõ làm pipeline có thể chuyển nhà cung cấp CI mà không cần viết lại toàn bộ build logic.

## 17. Khi nào nên thêm trục architecture hoặc JDK vendor?

### 17.1. Architecture

Pure Java libraries thường không cần nhân tất cả `x64`/`arm64` combinations. Nhưng nếu dùng JNI, GraalVM native image, protobuf native tools, compression/native crypto libraries hoặc database client có native binaries, `amd64` và `arm64` có thể thật sự khác.

Cần xác minh runners có đúng architecture; GitHub có các labels như `ubuntu-24.04-arm` hoặc `macos-15-intel` tùy plan/availability. Đừng gắn tên `linux-arm` lên runner x64.

### 17.2. JDK vendor

Eclipse Temurin, Microsoft Build of OpenJDK, Zulu, Corretto, Oracle/OpenJDK distributions có thể khác patches/certificates/provider behavior. Thường chọn một vendor chính; chỉ thêm vendor matrix nếu product support contract hoặc bug history đòi hỏi.

**Không nhân vendor × OS × version mặc định**; chọn một JDK21 vendor comparison trên Linux trước, rồi mở rộng khi có bằng chứng.

### 17.3. Android/Gradle Plugin Compatibility

Android builds còn có AGP version, Gradle version, JDK runtime và Android SDK matrix. Không dùng compatibility table cho Gradle JVM **một mình** để khẳng định mọi AGP/Android combination hỗ trợ. Cần kiểm cả Android Gradle Plugin compatibility và supported SDK/runner.

## 18. Chọn PR matrix, nightly canary và release matrix

Một chiến lược hợp lý theo rủi ro:

| Giai đoạn | Ma trận | Mục tiêu |
| --- | --- | --- |
| PR nhanh | Linux baseline + min/next supported Java | Feedback nhanh |
| PR bắt buộc OS | Windows/macOS cases theo support contract | Không merge lỗi cross-platform |
| Build-logic PR | Gradle min/current versions | Phát hiện Gradle API breakage |
| Nightly | JDK Early Access, Gradle RC/current thử nghiệm | Cảnh báo sớm |
| Release | Toàn bộ supported matrix + packaged artifact test | Bảo vệ public compatibility claim |
| Benchmark | Một máy/JDK/Gradle ổn định, warm/cold states | Đo performance có thể so sánh |

Nếu sản phẩm của bạn là Windows CLI, Windows không thể chỉ là optional nightly case. Nếu bạn bán Gradle plugin cho người dùng Gradle8, Gradle8 compatibility không được hạ thành non-blocking.

### 18.1. Path filters và required checks

Dùng filters để bỏ OS matrix khi chỉ sửa markdown có thể tiết kiệm, nhưng cũng có thể làm branch protection **đợi status check không được tạo**. Nếu packaging/docs generation liên quan changed markdown, việc skip còn có thể bỏ mất test hợp lệ.

Thiết kế một status job ổn định nếu policy cần và ghi rõ khi nào một phép thử được skip, thay vì giả định “không chạy = pass”.

### 18.2. Performance không giống compatibility

Một Windows job mất 7 phút và Linux job 2 phút có thể do runner CPU/SSD/network khác nhau. Không dùng ma trận compatibility làm chuẩn performance benchmark mà không pin hardware/cache conditions. Khi đo build performance, chọn stable runner, warm-up, đo nhiều lần và phân tích task outcomes/build scans.

## 19. Security: tách verify khỏi publish/deploy

CI ma trận kiểm PR source không tin cậy nên phải tối thiểu quyền:

- `permissions: contents: read`.
- Không đưa signing token, Maven credentials hay cloud deployment secrets vào matrix jobs.
- Không chạy `publish` trên mọi matrix leg.
- Dùng GitHub branch protection/release approvals cho publication job riêng.
- Validate Wrapper JAR và distribution SHA khi có policy.
- Không upload entire `~/.gradle`/`gradle.properties` hay debug logs có thể chứa secrets.
- Kiểm dependency verification/lockfiles nếu supply-chain risk cao.
- Với fork PRs, tránh `pull_request_target` + checkout untrusted code bằng high-trust token.
- Với action caching, dùng read-only cho non-primary/untrusted branches.
- Với remote build cache, bảo đảm cache write permissions và model task inputs đúng.
- Với provenance artifacts, gắn commit SHA, builder/version và release stage được kiểm soát.

Ma trận giúp đảm bảo compatibility, nhưng **không tự bảo đảm provenance hoặc supply-chain safety**; đó là một lớp chính sách khác.

## 20. Những câu hỏi tự kiểm tra

1. **Vì sao 3 OS × 3 JDK × 2 Gradle không phải mặc nhiên tốt?** Có unsupported combinations và chi phí thừa.
2. **Gradle8.14.3 chạy JVM25 không?** Không trong official Gradle runtime support matrix; cần Gradle9.1+.
3. **JDK compiler khác JVM Test task được không?** Có, khi cấu hình toolchains phù hợp.
4. **`java -version` có đủ chứng minh runtime JUnit không?** Không.
5. **Test nào kiểm JVM thật?** Assert `Runtime.version().feature()` trong forked Test process.
6. **`gradle-version: 8.14.3` rồi `./gradlew check` có kiểm8.14 không?** Không khi Wrapper ghim version khác.
7. **Version của Wrapper nằm ở đâu?** `gradle/wrapper/gradle-wrapper.properties`.
8. **Vì sao không sửa distributionUrl từ mỗi job?** Làm source/build state thay đổi và giảm reproducibility.
9. **`matrix.include` dùng để làm gì?** Chọn các explicit cases có mục tiêu.
10. **`exclude` khác continue-on-error?** Một cái không chạy, một cái chạy nhưng có policy chấp nhận failure.
11. **`fail-fast:false` có biến test fail thành success không?** Không.
12. **`max-parallel` có giảm số jobs không?** Không, chỉ concurrency.
13. **Vì sao setup-java cài JDK17 và JDK matrix?** Compile17 và test runtime theo JVM case.
14. **Case Java25 có cần Gradle9.1+ không?** Có theo runtime compatibility.
15. **Khi Windows runner là PowerShell native, dùng lệnh Wrapper nào?** `.\gradlew.bat`.
16. **Macos-15 ARM có test macOS Intel không?** Không.
17. **Một project `test NO-SOURCE` có xác nhận runtime compatibility không?** Không.
18. **Reports không tồn tại khi Java setup fail có bình thường không?** Có; xem stage logs.
19. **Vì sao artifact name chứa matrix case?** Tránh upload conflicts và dễ triage.
20. **Có nên dùng setup-java cache Gradle và setup-gradle cache cùng lúc không?** Tránh chồng controllers không cần.
21. **Dùng TestKit withGradleVersion có thay OS matrix không?** Không; nó chạy trên OS hiện tại.
22. **Khi nào cần Gradle version axis?** Khi build logic/Gradle plugin là compatibility contract.
23. **Có nên publish từ mọi job không?** Không; publish tập trung sau gated checks.
24. **JDK latest alias có an toàn làm required check mãi không?** Version có thể đổi, nên cần policy pin/canary.
25. **Ma trận có chủ đích thể hiện điều gì?** Mỗi case có lý do, đúng toolchain, tests thật, reports và kết luận giới hạn.

## 21. Checklist triển khai

- [ ] Đã định nghĩa OS/JDK/Gradle support contract trước khi viết YAML.
- [ ] Mọi case có mục tiêu rõ ràng và không tạo cặp Gradle/JVM unsupported.
- [ ] Wrapper được commit và validate, baseline dùng Wrapper đúng.
- [ ] Explicit Gradle version cases thật sự gọi CLI `gradle` được provision.
- [ ] Log `java -version` và exact `Gradle --version` trong mỗi case.
- [ ] Java compile toolchain là17 khi muốn target17.
- [ ] Test launcher lấy đúng matrix JDK, có assertion xác nhận JVM.
- [ ] Mọi job chạy JUnit tests thực, không `NO-SOURCE`/`SKIPPED`.
- [ ] Windows shell/Wrapper command phù hợp; paths portable.
- [ ] macOS/architecture coverage được ghi đúng giới hạn.
- [ ] `fail-fast`, `max-parallel`, `continue-on-error` theo policy.
- [ ] `include/exclude` được dùng để tránh combos thừa/unsupported.
- [ ] Không có vô tình two Gradle caching controllers cùng điều khiển User Home.
- [ ] Cache writes giới hạn ở primary trusted context.
- [ ] Reports upload ở `if: always()`, names unique.
- [ ] Required checks/branch protection được cập nhật khi đổi matrix.
- [ ] No secrets/publish credentials trong PR matrix.
- [ ] Gradle wrapper validation và action pinning phù hợp security.
- [ ] Dependency versions/JUnit BOM được ghim.
- [ ] CI release có publication job được approve riêng.
- [ ] Có TestKit consumer tests nếu sản phẩm là Gradle plugin.
- [ ] Có CI routine nâng JDK/Gradle baseline theo PR, không dùng “latest” ngẫu nhiên.
- [ ] Có runbook rõ để triage OS/JDK/Gradle failures.
- [ ] Không lấy elapsed time khác platform làm bằng chứng performance.
- [ ] Chỉ công bố hỗ trợ những tổ hợp thật sự được test.

## 22. Ghi nhớ

- **CI matrix là một tập các phép thử tương thích có mục đích**, không phải số lượng jobs.
- **Ba khái niệm JDK**: Daemon JVM, compiler toolchain và Test launcher cần được kiểm riêng.
- **Gradle Wrapper** là baseline version; explicit Gradle compatibility phải chạy đúng executable khác.
- **Gradle Java compatibility matrix** quyết định combinations có thể chạy Gradle trên một JVM.
- **`include`, `fail-fast:false`, `max-parallel`** giúp có đủ tín hiệu mà không nhân work vô ích.
- **GitHub Actions setup-java cài JDKs; setup-gradle quản lý Gradle, caching và wrapper validation**.
- **Một JUnit test kiểm Runtime.version()** giúp tránh matrix chỉ đổi label/JAVA_HOME.
- **Windows/macOS có filesystem/shell/architecture risks**; test đúng platform mới có ý nghĩa.
- **Build xanh với NO-SOURCE không chứng minh compatibility**.
- **Tránh đưa secrets và publishing vào PR matrix**; phát hành qua một job riêng có gate.
- **Mọi compatibility claim phải đi kèm actual test results** và giới hạn chưa kiểm.

## Tài liệu chính thức

- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): Java runtime vs Gradle versions, toolchain support.
- [Gradle — GitHub Actions](https://docs.gradle.org/current/userguide/github-actions.html): `setup-gradle`, Wrapper validation, matrix caching.
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): ghim distribution, scripts, checksum validation.
- [Gradle — Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): compile toolchain, `Test.javaLauncher`, JDK discovery.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): `test`, `check`, lifecycle.
- [Gradle — Java Gradle Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): plugin development, TestKit integration.
- [Gradle — TestKit](https://docs.gradle.org/current/userguide/test_kit.html): `GradleRunner.withGradleVersion`.
- [Gradle — Dependency Verification](https://docs.gradle.org/current/userguide/dependency_verification.html): supply-chain integrity.
- [GitHub — setup-java](https://github.com/actions/setup-java): Temurin JDKs, multiple versions, JAVA_HOME, caching.
- [Gradle Actions — setup-gradle](https://github.com/gradle/actions/blob/main/docs/setup-gradle.md): `gradle-version: wrapper`, explicit versions, cache rules.
- [GitHub Actions — Matrix Jobs](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs): `include`/`exclude`/`fail-fast`/`max-parallel`.
- [GitHub — Hosted Runners](https://docs.github.com/en/actions/reference/runners/github-hosted-runners): OS labels and architectures.
- [GitHub — Upload Artifact](https://github.com/actions/upload-artifact): report retention and naming.
- [GitHub Actions — Security Hardening](https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions): secrets and untrusted PR workflows.
