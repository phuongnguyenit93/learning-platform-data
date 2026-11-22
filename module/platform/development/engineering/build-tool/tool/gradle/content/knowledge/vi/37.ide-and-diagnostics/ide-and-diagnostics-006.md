# Chẩn đoán khác biệt giữa IDE, terminal và CI trong dự án Gradle

## 1. Vấn đề thực tế và cách tư duy đúng

Một repository Java/Gradle có thể **chạy thành công từ nút Run trong IDE**, thất bại khi gọi `./gradlew test` ngoài terminal, rồi thất bại bằng một lỗi khác khi GitHub Actions hoặc GitLab CI chạy `clean check`. Điều này **không đồng nghĩa Gradle hoặc IDE bị lỗi**: ba môi trường có thể khác **Gradle version, Gradle JVM, Java toolchain, project SDK, task graph, environment variables, plugin/dependency repositories, local caches, filesystem và test runner**.

Ví dụ:
- IntelliJ IDEA dùng **compiler của IDE**, còn CI chạy `JavaCompile` task thực sự.
- Java trên shell PATH là 21, Gradle daemon chạy JDK 17, nhưng Gradle toolchain cho ứng dụng là 17.
- IDE bấm Run trực tiếp `demo.Main`, không dùng Gradle `application.run` và các Java system properties cấu hình trong build script.
- CI có checkout sạch, không có các cached JAR/plugins mà laptop đã tải từ trước.
- Developer có `~/.gradle/gradle.properties`, custom init scripts hoặc Maven credentials, CI runner thì không.
- Windows filesystem thường không phân biệt hoa/thường còn CI Linux có thể phân biệt; `gradlew` bị CRLF hoặc mất executable bit.
- Developer chỉ chạy một JUnit test method; CI chạy `check` với toàn bộ tests, codegen, static analysis hoặc integration suites.

**Quy tắc chẩn đoán:** trước khi thay code, hãy chuẩn hóa **cùng Git commit, cùng Gradle Wrapper, cùng task/arguments, cùng Java toolchain và cùng input contract**. Sau đó thay đổi **một biến mỗi lần** để xác định sự khác nhau ở đâu.

### 1.1. Mục tiêu bài học

Bạn sẽ:
1. Phân biệt IDE Sync/Build/Run/Test với Gradle tasks.
2. Xác định chính xác JDK nào chạy Gradle và JDK nào chạy Java app/test.
3. Tạo một Java 17 lab có output định trước để kiểm tra IDE/terminal/CI.
4. Thiết lập Gradle Wrapper, Kotlin DSL/Groovy DSL và GitHub/GitLab CI.
5. So sánh environment, Gradle User Home, repositories, caches, OS và task graph.
6. Dùng `--version`, `javaToolchains`, `--info`, `--stacktrace`, `--dry-run`, `--profile` đúng mục đích.
7. Dùng bảng triệu chứng và một quy trình tái hiện có thể giao cho đồng nghiệp.

## 2. Sơ đồ ba môi trường chạy cùng một project

```text
             Same Git revision and committed Gradle project
                                |
        +-----------------------+-----------------------+
        |                       |                       |
  IntelliJ / Eclipse        Terminal                 CI runner
        |                       |                       |
  IDE Gradle JVM            JAVA_HOME               Runner JDK
  IDE Project SDK           PATH                    Container OS
  IDE internal builder      ./gradlew or gradle     Wrapper invocation
  Gradle Tool Window        Shell profile           CI variables
  IDE test runner           User init scripts       Fresh caches
        |                       |                       |
        +-----------------------+-----------------------+
                                |
                    Gradle distribution (Wrapper)
                    Settings, plugins, project scripts
                    Java toolchain, repositories
                    Tasks, inputs, outputs, tests
                                |
                       Build result / artifacts
```

**Cùng code không đủ để bảo đảm cùng build**. Gradle build logic là code thực thi trong Settings/scripts/plugins; nếu một môi trường nạp init scripts hoặc plugin version khác, cả configuration và task behavior có thể khác trước khi Java source được compile.

### 2.1. Những gì cần ghi nhận

| Thuộc tính | IDE | Terminal | CI |
| --- | --- | --- | --- |
| Git SHA | IDE VCS/`git rev-parse HEAD` | `git rev-parse HEAD` | Checkout/ref của job |
| Gradle distribution | IDE Gradle Distribution | `./gradlew --version` | Wrapper trong CI |
| Gradle JVM/daemon | IDE Gradle JVM/daemon criteria | `./gradlew --version` | Cùng command trên runner |
| Java compiler/test JVM | Gradle toolchain hoặc IDE SDK | `javaToolchains`/task configuration | `javaToolchains` |
| Task chạy | IDE Sync, Build, Run, Gradle Tool Window | CLI task path | CI YAML task path |
| Environment | IDE process/Run config | Shell vars | Job/step vars |
| User Home | Local user caches/init scripts | `GRADLE_USER_HOME` | CI user home/cache |
| Dependency source | Cache/proxy/repo | Cache/proxy/repo | Mirrors/secrets/network |
| OS/fs | Developer host | Developer shell | Linux/macOS/Windows runner |
| Incremental state | Warm IDE builds | Warm/cold | Often fresh checkout |

Đừng kết luận “CI khác IDE” khi chưa có **exact commands**. IDE **Sync** tải model dự án nhưng không nhất thiết chạy `test`. IDE **Build Project** có thể dùng compiler nội bộ chứ không phải Gradle `classes`. CI thường chạy `./gradlew clean check`, task graph lớn hơn.

## 3. Bước nền tảng: dùng Gradle Wrapper ở cả ba nơi

### 3.1. System Gradle không phải Gradle Wrapper

```bash
# Chạy Gradle distribution đã được chốt trong repository:
./gradlew --version
./gradlew clean check

# Chạy Gradle được cài trên PATH; có thể là version khác:
gradle --version
gradle clean check
```

Dùng `./gradlew` trên Linux/macOS, `.\gradlew.bat` trên Windows PowerShell hoặc `gradlew.bat` trong Command Prompt. IntelliJ nên chọn distribution từ `gradle-wrapper.properties`; CI dùng chính Wrapper files được commit.

### 3.2. Những file cần có

```text
root/
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
```

`gradle-wrapper.properties` có `distributionUrl` và có thể có `distributionSha256Sum` nhằm kiểm tra ZIP. Không tự bịa checksum cho một distribution: lấy từ nguồn chính thức khi cấu hình. Với một root build có Wrapper, có thể nâng bằng root `wrapper` task với Gradle version đã kiểm tra, rồi commit thay đổi.

**Quan trọng:** chạy `./gradlew --version` từ cả terminal/CI xác nhận Gradle distribution thực tế; việc IDE hiển thị “Gradle” trong tool window chưa chứng minh nó dùng cùng distribution nếu tùy chọn “Specified location” đang bật.

### 3.3. Kiểm tra chênh lệch Gradle version

Khi IDE chạy Gradle khác version của Wrapper, có thể xuất hiện:
- `Could not find method ...` do Gradle API thay đổi.
- Kotlin DSL generated accessors/plugin DSL không tương thích.
- Warning/deprecation ở một version nhưng thành error ở version khác.
- Plugin version yêu cầu Gradle mới hơn.
- Cache format khác, làm lần đầu build chậm.

Sửa theo hướng **thống nhất distribution** trước khi nâng hoặc hạ random plugin versions. Đừng thay Gradle Wrapper chỉ để chạy trên một IDE có cấu hình sai.

## 4. Gradle JVM, Java toolchain, Project SDK và Java trên PATH

Có ít nhất bốn khái niệm cần phân biệt:

| JDK/JVM | Dùng để làm gì? | Cách tìm |
| --- | --- | --- |
| Shell Java | `java` và `javac` từ PATH/JAVA_HOME. | `java -version`, `javac -version` |
| Gradle JVM/daemon | Chạy Gradle, Settings, build scripts, plugins. | `./gradlew --version`, IDE Gradle JVM, daemon criteria. |
| Java toolchain | JavaCompiler/test launcher/application launcher do Gradle tasks dùng. | `./gradlew -q javaToolchains` và `java.toolchain`. |
| IDE Project SDK | IDE internal compiler/Run Main nếu không delegated. | Project Structure và Run Configuration. |

**Gradle JVM không nhất thiết bằng Java toolchain.** Một Gradle daemon chạy JDK 21 vẫn có thể dùng **Java 17 compiler/launcher** thông qua toolchain; ngược lại IDEA Project SDK 17 không tự bảo đảm Gradle daemon sẽ chạy 17 nếu IDE Gradle JVM đang khác.

### 4.1. Ba lệnh căn bản

```bash
java -version
./gradlew --version
./gradlew -q javaToolchains
```

- `java -version` hiển thị JVM được shell chọn.
- `./gradlew --version` hiển thị Gradle version và JVM/runtime metadata (cách hiển thị launcher/daemon thay theo phiên bản Gradle).
- `javaToolchains` liệt kê JDKs mà Gradle phát hiện/provision và thông tin của chúng; **không có nghĩa tất cả tasks đang chọn cùng một JDK**.

IDE có thể sử dụng Gradle JVM setting riêng, `org.gradle.java.home` hoặc **Daemon JVM criteria** nếu build cấu hình. Không mặc định chỉ cần sửa `JAVA_HOME` là đủ để đổi daemon JVM thực tế.

### 4.2. Toolchain Java 17

Kotlin DSL:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

Groovy DSL:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

Toolchain này được các Gradle Java-related tasks hỗ trợ để compile/test/run bằng Java 17. Cấu hình không tự biến Java `java` từ PATH thành version 17; không tự sửa IDE Project SDK; cũng không bắt mọi custom `Exec` task dùng toolchain.

## 5. IntelliJ IDEA: ba cài đặt cần đối chiếu

Vào **Settings/Preferences → Build, Execution, Deployment → Build Tools → Gradle** (tên/menu có thể thay theo IDE version):

1. **Distribution**: chọn `gradle-wrapper.properties` thay cho installed Gradle ở một thư mục lạ.
2. **Gradle JVM**: chọn JDK tương thích và so với daemon JVM trên terminal/CI.
3. **Build and run using / Run tests using**: chọn **Gradle** khi cần kết quả giống `./gradlew build` và `./gradlew test`.

Theo IntelliJ docs, “Build and run using IntelliJ IDEA” dùng compiler/incremental build của IDE, có thể nhanh hơn cho một số project Java/Kotlin nhưng không thực hiện mọi Gradle-specific build processing. “Run tests using IntelliJ IDEA” có thể khác cấu hình Gradle `Test` tasks.

### 5.1. IDE Sync khác Build

**Gradle Sync/Reload All Gradle Projects**: import Gradle project model, source sets, plugins, dependencies, run configurations. Sync pass **không chứng minh** `./gradlew clean check` hoặc `:app:compileJava` pass.

**IDE Build Project**: có thể đi qua IntelliJ compiler nếu được cấu hình; generated source tasks/annotation processors/Gradle plugin tasks có thể không được chạy như Gradle.

**Gradle Tool Window → :test/:check/:run**: thực thi Gradle tasks, gần CLI hơn, nhưng Gradle JVM/env vẫn cần được đối chiếu.

### 5.2. IDE Run Main khác Gradle application:run

IntelliJ Run Configuration có:
- Main class.
- Module/classpath.
- Project SDK/JRE.
- VM options và program arguments.
- Working directory/environment variables.

Gradle `run` là một `JavaExec` task có thể có `mainClass`, classpath, `jvmArgs`, `systemProperty`, toolchain và dependencies trên các Gradle tasks khác. Hai đường chạy có thể in kết quả khác vì **Java system property chỉ được truyền ở một đường chạy**, không có gì hỏng trong source code.

### 5.3. IDE test runner khác Gradle Test task

Các cấu hình trong `tasks.test { ... }` như `useJUnitPlatform()`, `systemProperty`, `jvmArgs`, `testLogging`, test filters, environment và task dependencies không nhất thiết được IntelliJ internal runner áp dụng. Nếu test chạy trong IDE nhưng CI không tìm thấy JUnit 5 tests, trước tiên đối chiếu **Run tests using Gradle** và khai báo JUnit/launcher dependencies.

## 6. Demo Java 17 hoàn chỉnh để kiểm chứng ba môi trường

Ví dụ một project Java application với JUnit 5. Program in ra greeting, Java runtime major và một property `app.mode`. **Không in paths/secrets** nên có expected stdout ổn định. Tạo thư mục riêng, không sửa Gradle project production chỉ để chạy lab.

### 6.1. Cây thư mục

```text
gradle-environment-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
└── src/
    ├── main/java/demo/
    │   ├── Message.java
    │   └── Main.java
    └── test/java/demo/
        └── MessageTest.java
```

Cần Gradle Wrapper tương thích JDK 17 và Java toolchain 17 có sẵn hoặc provisioning configured. Demo không dựa vào Java 21 APIs hay environment-specific path. Khi chưa có Wrapper, tạo bằng root `wrapper` task trên Gradle installation đáng tin và commit files.

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "gradle-environment-lab"
```

### 6.2. build.gradle.kts

```kotlin
plugins {
    application
}

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

tasks.test {
    useJUnitPlatform()
}

tasks.named<JavaExec>("run") {
    systemProperty(
        "app.mode",
        providers.gradleProperty("appMode").orElse("dev").get()
    )
}
```

- `application` đăng ký `run`, áp dụng Java plugin và nối Java source classpath.
- Toolchain 17 giúp Java-related Gradle tasks chọn JDK 17.
- `tasks.test.useJUnitPlatform()` chạy JUnit Jupiter tests theo Gradle.
- `providers.gradleProperty("appMode")` lấy Gradle `-PappMode`, default `dev`.
- `JavaExec.systemProperty("app.mode", ...)` chuyển Gradle project property sang JVM của Java application. **`-PappMode` tự nó không tương đương `-Dapp.mode` của JVM**.

### 6.3. src/main/java/demo/Message.java

```java
package demo;

import java.util.Objects;

public final class Message {
    private Message() {
    }

    public static String greeting(String name) {
        return "Hello, " + Objects.requireNonNull(name).strip() + "!";
    }
}
```

### 6.4. src/main/java/demo/Main.java

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(
            "GREETING=" + Message.greeting(" Gradle ")
        );
        System.out.println(
            "JAVA_MAJOR=" + Runtime.version().feature()
        );
        System.out.println(
            "APP_MODE=" + System.getProperty("app.mode", "dev")
        );
    }
}
```

### 6.5. src/test/java/demo/MessageTest.java

```java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

public class MessageTest {
    @Test
    void stripsWhitespace() {
        assertEquals(
            "Hello, Gradle!",
            Message.greeting(" Gradle ")
        );
    }
}
```

### 6.6. Biên dịch/chạy chỉ bằng JDK 17

```bash
mkdir -p manual-out
javac --release 17 -d manual-out \
  src/main/java/demo/Message.java \
  src/main/java/demo/Main.java
java -cp manual-out demo.Main
```

Khi lệnh `java` là Java 17 và không truyền thêm JVM property, **stdout của chương trình chính xác**:

```text
GREETING=Hello, Gradle!
JAVA_MAJOR=17
APP_MODE=dev
```

`javac --release 17` tạo target Java 17, **không ép** Java launcher trong PATH phải chạy bản 17. Nếu dùng Java 21 chạy class, dòng `JAVA_MAJOR` là 21. Đây là kiểm tra rất hữu ích để phân biệt compiler target và runtime launcher.

Chạy Java độc lập với JVM property:

```bash
java -Dapp.mode=ci -cp manual-out demo.Main
```

Khi launcher Java 17, output:

```text
GREETING=Hello, Gradle!
JAVA_MAJOR=17
APP_MODE=ci
```

### 6.7. Chạy bằng Gradle Wrapper

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew clean check
./gradlew -q run
```

Output của `demo.Main` khi Gradle `run` dùng toolchain Java 17:

```text
GREETING=Hello, Gradle!
JAVA_MAJOR=17
APP_MODE=dev
```

Chạy có project property:

```bash
./gradlew -q run -PappMode=ci
```

Output program:

```text
GREETING=Hello, Gradle!
JAVA_MAJOR=17
APP_MODE=ci
```

Không hard-code toàn bộ Gradle task logs: trạng thái `UP-TO-DATE`, `FROM-CACHE` hoặc download JUnit dependencies có thể thay đổi. Các dòng trong các text fences trên là stdout do Java program in ra khi điều kiện Java 17 được đáp ứng.

### 6.8. Tái hiện sự khác nhau trong IntelliJ

1. Import dự án thành Gradle project và chọn Wrapper.
2. Đặt Gradle JVM tương thích.
3. Mở Gradle Tool Window, chạy `run`, thêm Gradle args `-PappMode=ci`: `APP_MODE=ci`.
4. Tạo **IntelliJ Application Run Configuration** chạy trực tiếp `demo.Main`, không có VM option: `APP_MODE=dev`, dù Gradle CLI vừa dùng `-PappMode=ci`.
5. Thêm VM option `-Dapp.mode=ci` trong internal Run Configuration: `APP_MODE=ci`.
6. Nếu internal Run dùng JDK 21 thay vì toolchain 17, `JAVA_MAJOR=21`; đổi Run Configuration JRE hoặc delegate sang Gradle để kiểm chứng.

**Kết luận từ lab:** cùng source và class name, nhưng khác **executor/JDK/JVM properties** đủ để tạo output khác. Đừng sửa `Main.java` khi điều khác nhau thực ra là Java Run Configuration.

## 7. Groovy DSL tương đương cho cùng Java 17 demo

Giữ nguyên ba Java files; thay `settings.gradle.kts` bằng **`settings.gradle`**:

```groovy
rootProject.name = 'gradle-environment-lab'
```

Thay `build.gradle.kts` bằng **`build.gradle`**:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.Main'
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('run', JavaExec) {
    systemProperty(
        'app.mode',
        providers.gradleProperty('appMode').orElse('dev').get()
    )
}
```

Lệnh `./gradlew -q run -PappMode=ci` vẫn cho ba dòng output `GREETING=Hello, Gradle!`, `JAVA_MAJOR=17`, `APP_MODE=ci` khi toolchain có sẵn. Kotlin/Groovy là hai **lựa chọn cú pháp build script**, không phải hai nội dung cùng dán vào một file.

## 8. CI đối chiếu: GitHub Actions

Để so với terminal, CI phải dùng cùng Gradle Wrapper và Java toolchain. Ví dụ **`.github/workflows/verify.yml`**:

```yaml
name: Gradle IDE terminal CI parity

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout source revision
        uses: actions/checkout@v4

      - name: Install JDK 17
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Configure Gradle
        uses: gradle/actions/setup-gradle@v4

      - name: Identify Java and Gradle environment
        run: |
          java -version
          ./gradlew --version
          ./gradlew -q javaToolchains

      - name: Compile and run tests
        run: ./gradlew --no-daemon --console=plain clean check

      - name: Run app with controlled property
        run: ./gradlew -q run -PappMode=ci
```

- `setup-java` cung cấp JDK 17 cho runner; Gradle toolchain vẫn được Gradle lựa chọn theo configuration.
- `setup-gradle` giúp Gradle setup/caching theo action behavior.
- `contents: read` đủ cho checkout/verify; **không cần publishing secrets**.
- `--no-daemon` dành cho automation không nhất thiết tránh **single-use daemon** mà Gradle có thể tạo do JVM requirements.
- Actions `@v4` minh họa major refs. Với supply-chain security, production nên pin **reviewed full action commit SHAs** và cập nhật theo policy.

Nếu CI đã cài JDK 17, Gradle Wrapper tải được distribution và JUnit dependencies tải/cache được, chương trình chạy `-PappMode=ci` phải in đúng ba dòng ở mục 6.7. Nếu mạng bị chặn hoặc Wrapper checksum sai, build sẽ fail **trước khi chạy Java code**.

### 8.1. GitLab CI tương đương

```yaml
stages:
  - verify

verify_java_gradle:
  stage: verify
  image: eclipse-temurin:17-jdk
  script:
    - java -version
    - ./gradlew --version
    - ./gradlew -q javaToolchains
    - ./gradlew --no-daemon --console=plain clean check
    - ./gradlew -q run -PappMode=ci
```

Image chỉ mô tả JDK runtime cơ bản; cần mạng/truststore/repos và executable Wrapper đúng trên Linux runner. Production có thể pin container image digest. Nếu runner sử dụng network restricted, pre-provision Gradle distributions/dependencies từ mirror đã phê duyệt thay vì vô hiệu TLS.

## 9. So sánh đúng task/arguments giữa IDE và CLI

| IDE operation | CLI gần tương đương | Khác biệt phải nhớ |
| --- | --- | --- |
| Gradle Tool Window `run` | `./gradlew run` | IDE Gradle JVM/env vẫn có thể khác. |
| Gradle Tool Window `test` | `./gradlew test` | Test filters/args phải khớp. |
| Gradle Tool Window `check` | `./gradlew check` | Kiểm tra đúng project/module. |
| IDE Reload/Sync | Không có task CLI hoàn toàn tương đương | Chỉ import model, không phải full test. |
| IDE Build Project nội bộ | Không đồng nhất với `./gradlew classes` | Compiler/codegen khác. |
| IntelliJ Run Main nội bộ | Gần `java -cp ... demo.Main` | VM args/JDK/classpath/working dir riêng. |
| IDE chạy một JUnit method | `./gradlew test --tests ...` | CI `check` thường nhiều tests hơn. |
| Gradle Tool Window `:app:test` | `./gradlew :app:test` | Root/subproject task paths cần đúng. |

Với multi-project, `:app:run` không phải `:run` ở root. Để hiểu task graph:

```bash
./gradlew projects
./gradlew tasks --all
./gradlew test --dry-run
```

`--dry-run` hiển thị các tasks sẽ được lên kế hoạch, **không thực thi tests**. Đừng coi nó là bằng chứng CI build pass. Trong project lab một module, không dùng `:app:*` trừ khi đã tạo subproject `app`.

### 9.1. Tại sao clean check khác một IDE Run?

`clean` xóa outputs dưới `build/`; nó không xóa toàn bộ Gradle User Home. `check` thực hiện các verification tasks được plugins đăng ký; còn IDE Run có thể chỉ khởi động class. Nếu `clean check` fail nhưng IDE Run pass, hãy chạy cùng `clean check` từ IDE Gradle Tool Window trước khi sửa Java source.

## 10. Gradle User Home và user-specific configuration

Mặc định Gradle User Home là `~/.gradle` (Windows có vị trí tương đương trong user profile), có thể đổi bằng `GRADLE_USER_HOME`. Nó chứa:
- User-level `gradle.properties`.
- Init scripts dưới `init.d`.
- Dependency/plugin caches và Build Cache.
- Wrapper distributions, daemon logs, một số JDK toolchains được provision.

Laptop có thể có một `~/.gradle/init.d/enterprise-repos.gradle` thêm Maven mirror nội bộ, còn CI không có; IDE có thể nạp init script khác terminal nếu user home khác. Nếu đó là required build configuration, chuyển non-secret phần cần thiết vào Settings hoặc managed enterprise policy, **không copy toàn bộ User Home** (có thể chứa credentials).

### 10.1. Property precedence

Các file `gradle.properties` thường được Gradle đọc theo thứ tự ưu tiên:
1. Gradle User Home.
2. Root project.
3. Gradle installation home.

Command-line Gradle options/system properties có precedence riêng. Với **project properties**, nguồn gồm `-Pname=value`, `-Dorg.gradle.project.name=value`, `ORG_GRADLE_PROJECT_name` và `gradle.properties` theo quy tắc ưu tiên được tài liệu mô tả.

Ví dụ:
```properties
# gradle.properties tại root:
appMode=dev
```

```bash
./gradlew -q run -PappMode=ci
```

Ở lab, command-line `-PappMode=ci` thắng default value từ file. **Không đánh đồng** `-PappMode=ci` của Gradle với `-Dapp.mode=ci` của Java launcher. Build script có nhiệm vụ chuyển nó thành JavaExec system property.

### 10.2. Init scripts có thể làm khác cả plugin resolution

`~/.gradle/init.d` có thể thêm repositories, apply plugins, đặt build scan policy hoặc internal credentials. IDE và terminal cùng account có thể dùng chúng, CI fresh runner không có. Vì vậy developer tưởng project khai báo đầy đủ repositories, nhưng source trong Git thực ra thiếu `pluginManagement.repositories` hoặc dependency repositories. CI fail là tín hiệu về reproducibility.

## 11. Environment variables và quyền truy cập secrets

Các biến đáng kiểm tra:
- `JAVA_HOME`, `PATH`, `GRADLE_USER_HOME`.
- `JAVA_OPTS`, `GRADLE_OPTS`, `JAVA_TOOL_OPTIONS`.
- `ORG_GRADLE_PROJECT_*` và application-specific variables.
- Proxy/CA settings, `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` tùy tool.
- CI variables/secret manager, `HOME` và workspace directory.

**Không in `env`/`printenv` đầy đủ vào CI logs.** Chỉ ghi việc một biến có tồn tại hay không, hoặc giá trị không bí mật sau khi đã rà soát. Gradle scripts/plugins có thể đọc environment; PR từ nguồn chưa tin cậy không được cấp publishing tokens chỉ để chạy `check`.

### 11.1. IDE process environment không nhất thiết bằng terminal

IDE mở bằng desktop launcher có thể kế thừa environment khác shell login; terminal panel trong IDE còn có shell profile riêng. Chạy các lệnh an toàn ở:
- Terminal bên ngoài.
- Terminal bên trong IDE.
- CI job log.

```bash
java -version
./gradlew --version
./gradlew -q javaToolchains
pwd
git rev-parse HEAD
```

Trên Windows PowerShell:
```powershell
java -version
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
Get-Location
git rev-parse HEAD
```

Nếu hai terminals khác `JAVA_HOME`, PATH hoặc Gradle version, điều tra shell/IDE startup configuration trước. Khi cần so secrets, chỉ kiểm tra presence và dùng dummy values trong reproduction.

## 12. Dependencies, proxy, TLS và offline caches

Một tình huống thường gặp: máy developer đã có JUnit JAR trong Gradle cache, IDE Sync pass, nhưng CI fresh runner fail `Could not resolve ...` hoặc `PKIX path building failed`. Các nghi vấn:
- Maven Central/internal mirror không truy cập từ CI.
- Proxy/DNS hoặc certificate truststore khác.
- Cần read-only dependency token nhưng CI chưa được cấp.
- Repositories/plugin repositories khai báo ngoài Git qua init script.
- CI đang chạy `--offline` mà cache trống.
- Đổi dependency dynamic version làm metadata khác.

### 12.1. Phân biệt các repository roles

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

Đây là đoạn đặt trong **`settings.gradle.kts`** của project cần những plugin repositories này. Trong `build.gradle.kts`, `repositories { mavenCentral() }` của lab là **dependency repositories** để tải JUnit. Với builds dùng `dependencyResolutionManagement.repositories`, organization có thể yêu cầu centralized repos; không tự thêm private URL chưa được duyệt.

### 12.2. Các lệnh kiểm tra

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew help --info
./gradlew --offline check
./gradlew --refresh-dependencies check
```

- `dependencies`: xem dependency graph theo configuration có trong Java project.
- `--offline`: chỉ dùng artifacts/metadata phù hợp đã cache; nếu thiếu thì fail, không tạo ra dependency.
- `--refresh-dependencies`: yêu cầu revalidate resolution; không sửa 401/403, proxy/TLS CA hoặc artifact không tồn tại.
- `--info`: cung cấp nhiều log để tìm root cause, nhưng tránh chia sẻ private repo tokens/URLs không được phép.

Không disable certificate verification để chữa lỗi TLS. Sửa corporate CA/truststore, repository URL hoặc auth server-side đúng cách.

## 13. Caches khiến task outcomes khác nhau mà output vẫn đúng

Một lần `compileJava` có thể báo:
- `SUCCESS`: task action đã thực thi.
- `UP-TO-DATE`: local outputs còn phù hợp inputs.
- `FROM-CACHE`: khôi phục outputs từ Build Cache.
- `NO-SOURCE`: source set trống.
- `SKIPPED`: task skip theo condition.

Khi CI có fresh checkout, `compileJava SUCCESS` trong khi IDE lần hai `UP-TO-DATE` là bình thường. Quan trọng là **Java bytecode/results** có đúng hay không.

| Cơ chế | Cache gì? | Tình huống chênh lệch |
| --- | --- | --- |
| Dependency cache | JAR/POM/module metadata | CI phải tải, laptop đã có. |
| Script compilation cache | Compiled Kotlin/Groovy scripts | CI cold compile lâu. |
| Task Build Cache | Task outputs | CI remote hit, local up-to-date. |
| Configuration Cache | Configuration/task graph | IDE warm reuse, CI ephemeral miss. |
| Incremental Java compilation | Chỉ sources bị ảnh hưởng | Clean CI compile lại nhiều hơn. |
| Daemon | JVM process reuse | IDE daemon warm, CI startup mới. |

### 13.1. Thí nghiệm loại trừ một số cache layers

```bash
./gradlew --no-build-cache --no-configuration-cache clean check
```

Cờ này tắt Build Cache và Configuration Cache cho invocation; **không tắt dependency cache hay mọi loại script cache**. Nếu muốn force task execution:
```bash
./gradlew --rerun-tasks check
```

Đây là phép thử chẩn đoán, không phải cấu hình CI bắt buộc. Muốn đo Build Cache, dùng `--build-cache` với task cacheable trong điều kiện phù hợp thay vì dùng `--rerun-tasks` và mong hit cache.

### 13.2. Không xóa toàn bộ ~/.gradle

Xóa Gradle User Home sẽ xóa nhiều caches, Wrapper distributions, init scripts/config liên quan và đôi khi secrets của user. Để điều tra clean environment, dùng **thư mục tạm riêng**, không chỉnh global home:
```bash
mkdir -p .tmp-gradle-home
GRADLE_USER_HOME="$PWD/.tmp-gradle-home" ./gradlew help --info
```

Ví dụ Bash trên Linux/macOS; PowerShell dùng `$env:GRADLE_USER_HOME` tương ứng. Home mới không có downloads, nên có thể cần mạng. Đây không phải cách để “sửa” build lâu dài; chỉ để xác nhận môi trường user-level có ảnh hưởng.

## 14. OS, đường dẫn, line endings, locale, timezone và charset

| Khác biệt | Lỗi có thể thấy | Cách khắc phục |
| --- | --- | --- |
| `gradlew` thiếu execute bit Linux | `Permission denied` | Commit đúng executable file mode. |
| CRLF trong shell script | `/bin/sh^M: bad interpreter` | `.gitattributes` với LF. |
| Windows path hard-code | File không tồn tại trên Linux | Gradle `layout.projectDirectory`, Java `Path`. |
| File/path case | `Main.java` và `main.java` khác trên Linux | Đồng nhất case trong Git/source imports. |
| Path separator | Windows `;`, Unix `:` | Gradle file collections hoặc `File.pathSeparator`. |
| Default charset | Unicode hoặc file output khác | `StandardCharsets.UTF_8`/compiler encoding. |
| Locale | Test number/date format khác | `Locale.ROOT` cho machine-readable values. |
| Timezone | Test midnight/UTC khác | Explicit `Clock`/`ZoneId` hoặc test JVM property. |
| File permissions/symlinks | Copy/package task fail | Test OS mục tiêu, ghi đúng permission contract. |

Ví dụ `.gitattributes` cho project có Wrapper:

```gitattributes
/gradlew text eol=lf
*.sh text eol=lf
*.bat text eol=crlf
```

Không chuyển binary files thành text tùy tiện. Nếu CI Linux báo `Permission denied`, xử lý executable bit trong Git thay vì chỉ thêm `chmod` trên runner; CI `chmod` tạm có thể là workaround nhưng không thay thế source fix.

### 14.1. Encoding và timezone của test JVM

Kotlin DSL, áp dụng khi đã có Java `test` task:
```kotlin
tasks.test {
    useJUnitPlatform()
    systemProperty("user.timezone", "UTC")
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
```

Nếu IntelliJ chạy JUnit **internal runner**, `systemProperty("user.timezone", "UTC")` của Gradle `Test` task có thể không truyền vào IDE JVM. Hoặc delegate tests to Gradle, hoặc đặt `-Duser.timezone=UTC` trong IDE test configuration để có tương đương. Production code tốt hơn nên explicit `Clock`/`ZoneId` thay vì phụ thuộc defaults.

## 15. buildSrc, convention plugins và IDE model differences

`buildSrc` là Gradle build đặc biệt ở root, có code/plugin logic được compile để cung cấp classpath cho project scripts. Nếu local IDE Sync pass nhờ caches nhưng CI cold fail ở `buildSrc:compileKotlin` hoặc plugin resolution:
- Xác minh `buildSrc` dependencies và repositories của **build riêng** này.
- Kiểm tra JDK/Gradle/Kotlin DSL compatibility.
- Kiểm tra file trong `buildSrc/src/main` có được commit (không bị ignore).
- Xem plugin-under-test và convention plugin classpaths.
- Tránh phụ thuộc vào user-specific init script hoặc IDE plugin setup.

Nếu repo thật có `buildSrc/`:
```bash
./gradlew -p buildSrc tasks --all
./gradlew -p buildSrc build --info
```

Đây là chẩn đoán build logic riêng, **không thay thế** full `./gradlew check` của main build. Nếu không có `buildSrc/`, không dùng lệnh này.

### 15.1. Included build build-logic

```kotlin
pluginManagement {
    includeBuild("build-logic")
}
```

Khi included build phát triển convention plugins, nó có Settings/repos/dependencies riêng. Nếu CI không resolve plugin ID, kiểm tra `pluginManagement.includeBuild`, plugin ID/source set và repository availability. Sau khi đổi build logic, Reload Gradle project trong IDE để tránh stale model, rồi dùng Wrapper CLI để kiểm chứng.

### 15.2. Script compilation vs application compilation

- `compileKotlin` hoặc precompiled plugin processing trong buildSrc: **build logic**.
- Kotlin/Groovy `build.gradle.kts`/`build.gradle` script compilation: **configuration infrastructure**.
- `:app:compileJava`: **application production source**.
- `:app:test`: **test execution**.

Đừng đổi `javac` compiler flags khi lỗi gốc là Kotlin script compilation, và đừng xóa application output để sửa plugin repository authentication.

## 16. Generated sources và annotation processing

IDE internal compiler có thể sử dụng generated sources từ lần chạy trước; CI clean checkout lại thiếu. Những trường hợp:
- Gradle task codegen chưa được khai báo dependency trước `compileJava`.
- Annotation processor được cài trong IDE nhưng thiếu `annotationProcessor` dependency trong Gradle.
- IDE caches cũ khiến IDE nhìn thấy classes không còn tồn tại trong build source sets.
- Test source sets hoặc resource processing khác.
- Codegen task dùng absolute file paths hoặc untracked files.

Sửa ở Gradle build model:
1. Khai báo đúng processor/generator dependency.
2. Dùng task providers để biểu diễn generated output là input của Java compilation.
3. Đặt generated sources under `build/` và tái tạo được.
4. Chạy `./gradlew clean check` trên fresh checkout để bảo đảm reproducibility.
5. Reload Gradle model ở IDE sau khi sửa.

Không copy `build/generated` từ developer vào Git chỉ để CI tạm xanh, trừ khi source-generation policy có lý do rõ và review.

## 17. JUnit 5: vì sao chạy test trong IDE và CI khác nhau?

### 17.1. Khác Gradle Test config

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}
tasks.test {
    useJUnitPlatform()
}
```

IDE internal runner có thể tự nhận JUnit framework nhưng CI Gradle cần dependencies/task configuration. Nếu test không được phát hiện trong Gradle, xác minh `useJUnitPlatform`, source set, `Test` task và JUnit launcher thay vì tắt test.

### 17.2. Một method khác cả suite

```bash
./gradlew test --tests demo.MessageTest
./gradlew check
```

Trong lab, `demo.MessageTest` là class tồn tại thật. `--tests` lọc test classes/methods theo Gradle; chạy một class pass không chứng minh toàn bộ `check` pass. CI có thể còn các verification tasks do plugins thêm vào.

### 17.3. Flaky tests và môi trường

Nếu test chỉ fail CI:
- So Java runtime/toolchain và `user.timezone`, locale, encoding.
- Kiểm tra temporary directory/permissions, clock, random seed và parallel execution.
- Chờ service readiness đúng thay vì giả định network/DB startup tức thì.
- Đừng dựa vào test method order.
- Với network integration test, dùng isolated test fixtures và mock server khi phù hợp.

Không thêm `ignoreFailures=true` hoặc skip test từ CI chỉ để pipeline xanh; cần hiểu nguyên nhân và thêm regression test.

## 18. Debug theo cấp độ: từ nhận diện tới truy nguyên

### 18.1. Bắt đầu bằng version và source identity

```bash
git status --short
git rev-parse HEAD
java -version
./gradlew --version
./gradlew -q javaToolchains
```

Một IDE có uncommitted file thay đổi còn CI checkout commit cũ cũng có thể giải thích toàn bộ chênh lệch. Đừng gửi thông tin nhạy cảm cùng logs.

### 18.2. Chạy task có thể so sánh

```bash
./gradlew clean check --console=plain
./gradlew clean check --stacktrace --console=plain
./gradlew check --info --console=plain
```

- `--stacktrace`: tìm root failure trong Gradle.
- `--info`: task/configuration/dependency resolution details.
- `--console=plain`: log dễ so.
- `--debug`: log rất lớn; chỉ dùng sau khi lọc root issue và tránh tiết lộ secrets.
- `--profile`: HTML profile khi cần đo chậm.
- `--scan`: Build Scan sâu hơn khi policy cho phép **upload metadata ra ngoài**; không dùng tự động cho private project nếu chưa được phê duyệt.

### 18.3. Tìm first meaningful error

Phân loại:
1. Wrapper download/checksum fail **trước configuration**.
2. Settings/plugin resolution/`buildSrc` fail **trong setup/configuration**.
3. `compileJava` fail **khi compilation**.
4. `test` fail **do tests/JVM/environment**.
5. `run` fail **do launcher/mainClass/props**.
6. CI pipeline stage fail **do runner permissions/paths/repositories**.

Đừng sửa file `build.gradle.kts` khi lỗi thật là `gradlew` không executable. Đừng thay JDK khi lỗi là Maven 401/403.

## 19. Quy trình điều tra tuần tự với ba môi trường

### Bước 1: cùng source, Wrapper, task

Xác minh Git SHA, Gradle Wrapper và nguyên văn command CI. Chạy `./gradlew clean check --console=plain` từ **external terminal**.

### Bước 2: chạy Wrapper trong IDE Terminal

Nếu IDE Terminal cũng fail nhưng IDE **Run Main** pass, kiểm tra internal compiler/runner. Nếu IDE Terminal pass còn external Terminal fail, so shell env, working directory, GRADLE_USER_HOME và JDK PATH.

### Bước 3: chạy từ Gradle Tool Window

Chạy đúng task `check` hoặc `:app:check`. Nếu Gradle Tool Window fail còn terminal CLI pass, đối chiếu Gradle JVM setting, Wrapper distribution và init scripts/User Home. Không dựa vào Sync status để kết luận.

### Bước 4: đối chiếu CI JDK/OS/network

CI dùng cùng Git revision nhưng khác OS/runner/caches. So `./gradlew --version`, `javaToolchains`, `java -version` và task arguments. Nếu error `Could not resolve`, tập trung network/proxy/cache/auth; nếu compiler/test fail, tập trung codegen/JDK/test environment.

### Bước 5: cô lập một biến mỗi lần

Lần lượt thử:
- Switch IDE “Build and run using Gradle”.
- Align Gradle JVM với CLI JVM hoặc Daemon JVM criteria.
- Chạy `-PappMode=ci` trong mọi nơi.
- Dùng fresh isolated Gradle User Home cho lab, có thể phải tải distributions/dependencies.
- Tắt task Build Cache/Configuration Cache trong test được kiểm soát.
- So Windows/Linux case sensitivity hoặc file mode.

**Không nâng cùng lúc Gradle Wrapper, plugin versions, JDK và dependencies**; nếu build xanh, bạn sẽ không biết nguyên nhân gốc.

### Bước 6: ghi regression và loại nguyên nhân phụ

Khi đã xác định bug, tạo test/assertion hoặc CI matrix target. Ghi:
- Source commit SHA.
- Gradle/JDK/plugin versions.
- Exact task + flags + Gradle User Home policy.
- OS/runner.
- Root failure và hành vi mong muốn.
- Nếu liên quan cache, task outcomes và cache hit/miss.

Không chia sẻ secrets, toàn bộ `GRADLE_USER_HOME` hay full environment dump.

## 20. Triệu chứng phổ biến và hướng xử lý

| Triệu chứng | Nghi vấn ưu tiên | Bước kiểm chứng |
| --- | --- | --- |
| IDE Run pass, Gradle `run` fail | Internal runner/JVM props/mainClass khác. | Delegate Gradle, so Run configuration và `-P`. |
| IDE Build pass, CI `compileJava` fail | IDE compiler/codegen bypass Gradle. | Gradle Tool Window `clean classes`. |
| IDE Sync pass, CI `check` fail | Sync không chạy tests/full task graph. | Chạy cùng `check` từ IDE. |
| Terminal `gradle` pass, Wrapper fail | Gradle distribution khác. | So cả hai `--version`. |
| Gradle Tool Window fail, terminal pass | IDE Gradle JVM/User Home/distribution khác. | Kiểm tra IDE Gradle settings. |
| `UnsupportedClassVersionError` | Class bytecode target mới hơn daemon/application JVM. | So toolchain và daemon JVM. |
| `No matching toolchains found` | JDK version chưa cài/phát hiện/provision. | `javaToolchains`, CI setup-java. |
| `JAVA_HOME is set to an invalid directory` | Environment path sai. | Sửa JDK installation. |
| `Could not find plugin` chỉ CI | Plugin repository/credentials/init scripts khác. | `pluginManagement.repositories`. |
| `Could not resolve artifact` | Network, proxy, missing cache/creds. | `--info`, repo access, scoped read token. |
| `PKIX path building failed` | Java truststore/certificate chain sai. | Sửa CA/truststore, không bypass TLS. |
| JUnit chạy IDEA nhưng không được Gradle tìm | IDE runner khác Test task, thiếu launcher. | `useJUnitPlatform` + dependencies. |
| Unit test pass đơn lẻ, `check` fail | Chạy ít test hoặc task graph khác. | Chạy full suite và scan task graph. |
| Test chỉ fail Linux CI | Case-sensitive paths/permissions/CRLF. | Git file modes, `.gitattributes`. |
| CI báo `Permission denied` với gradlew | Missing executable bit. | Commit executable mode. |
| CI có `/bin/sh^M` | CRLF shell script. | `eol=lf`. |
| APP_MODE khác IDE/CI | `-PappMode` chưa truyền vào internal Java process. | Gradle Run hoặc `-Dapp.mode`. |
| Gradle daemon JDK khác app JVM | Toolchain và daemon là hai JDK contexts. | Kiểm tra Gradle JVM và `javaToolchains`. |
| CI chậm hơn IDE | Cold caches/daemon/network/CPU quotas. | Phân loại cold/warm và profile phases. |
| buildSrc fail cold CI | Build logic dependencies/compiler/plugins chưa chuẩn hóa. | `-p buildSrc build --info`. |
| Configuration Cache always misses | Changing inputs/ephemeral runner. | Đọc cache invalidation report. |
| `--offline` local pass CI fail | Laptop có artifacts cache, CI không có. | Mirror/repository/credentials đúng. |
| `UP-TO-DATE` ở IDE, `SUCCESS` ở CI | Output reuse state khác. | So nội dung output thay vì task label. |

## 21. Checklist chuẩn hóa IDE, terminal và CI

### Source/build identity

- [ ] Cùng Git commit và không có file cần thiết chưa commit?
- [ ] Dùng Wrapper, không dùng system Gradle ngoài ý định?
- [ ] Gradle Wrapper version và checksum được chốt?
- [ ] Đúng root project và full task path?
- [ ] Flags/properties như `-P`, `-D`, `--offline` có giống nhau?

### Java và IDE

- [ ] Biết Java version trên PATH?
- [ ] Biết Gradle JVM/daemon JVM đang chạy?
- [ ] Đã xem `javaToolchains` ở cả ba environments?
- [ ] Đã phân biệt IDE Project SDK với Gradle JVM?
- [ ] IDE Build and run using/Run tests using chọn Gradle nếu cần parity?
- [ ] Đã Reload Gradle model sau plugin/build script changes?

### Dependencies, OS và environment

- [ ] Repositories/pluginManagement/mirrors và credentials có thể dùng ở CI?
- [ ] User Home/init scripts có tạo phụ thuộc ngầm trên laptop?
- [ ] Không in secret values vào logs hoặc gửi full env dump?
- [ ] CI OS filesystem path/case/file permissions phù hợp?
- [ ] Timezone/locale/encoding được khai báo khi test yêu cầu?
- [ ] Gradle distributions/JDK toolchains/dependencies có thể download hoặc pre-provision?

### QA và tái hiện

- [ ] Có exact command reproducer?
- [ ] Có first meaningful failure từ `--stacktrace`?
- [ ] Đã so Gradle Tool Window với IDE Terminal và external Terminal?
- [ ] Đã thử cache/state như một biến riêng?
- [ ] Có regression test/CI job verify kết quả sau fix?

## 22. Quick reference các lệnh

| Mục đích | Lệnh |
| --- | --- |
| Gradle distribution/JVM | `./gradlew --version` |
| Java trên shell | `java -version` |
| Java toolchains | `./gradlew -q javaToolchains` |
| Git SHA | `git rev-parse HEAD` |
| Git working tree | `git status --short` |
| Build/test Gradle | `./gradlew clean check` |
| Run app có mode ci | `./gradlew -q run -PappMode=ci` |
| Kiểm tra tasks | `./gradlew tasks --all` |
| Dự kiến task graph | `./gradlew test --dry-run` |
| Xem stacktrace | `./gradlew check --stacktrace --console=plain` |
| Chi tiết resolution | `./gradlew check --info` |
| Profile build | `./gradlew check --profile` |
| Thử offline | `./gradlew --offline check` |
| Revalidate dependencies | `./gradlew --refresh-dependencies check` |
| Test không Build/Configuration Cache | `./gradlew --no-build-cache --no-configuration-cache clean check` |
| Force task actions | `./gradlew --rerun-tasks check` |
| Đo Build Cache có điều kiện | `./gradlew --build-cache check` |
| BuildSrc riêng nếu tồn tại | `./gradlew -p buildSrc build --info` |

## 23. Tự kiểm tra

1. **IDE Sync pass có chứng minh `check` pass?** — Không; Sync chủ yếu import model, tests có thể chưa chạy.
2. **`gradle` và `./gradlew` có chắc cùng version?** — Không; Wrapper chốt distribution.
3. **Gradle JVM = Java toolchain = Project SDK?** — Không; đó là các context riêng.
4. **Vì sao IDEA Run ra APP_MODE=dev nhưng Gradle ra ci?** — Java property được truyền vào Gradle `run` bởi `-PappMode=ci`, không tự có trong IDE internal Run.
5. **`--release 17` có ép `java` launcher dùng JDK 17?** — Không.
6. **Tại sao fresh CI fail resolve dependencies?** — Có thể thiếu cache, mirror, credentials hoặc CA/proxy.
7. **Có nên xóa toàn bộ ~/.gradle?** — Không; dùng thí nghiệm cô lập để biết state nào khác.
8. **Khi local UP-TO-DATE còn CI SUCCESS, Java outputs chắc chắn khác?** — Không; có thể chỉ khác cache state.
9. **Mất executable bit ảnh hưởng IDE/CI ra sao?** — Linux CI có thể không chạy được `./gradlew`.
10. **Một JUnit test được IDE chạy có bảo đảm được Gradle nhận diện?** — Không; phải cấu hình Gradle Test/JUnit Platform.
11. **Đâu là cách bắt đầu điều tra có bằng chứng?** — Exact task, Git SHA, Wrapper/JDK versions và first meaningful error.
12. **Khi nào nên dùng Build Scan?** — Khi cần phân tích sâu và được phê duyệt chia sẻ build metadata.

**Kết luận:** Sự khác nhau giữa IDE, terminal và CI phần lớn là sự khác nhau ở **cách khởi chạy Gradle hoặc Java**, Gradle build model, môi trường và caches chứ không phải “ba bản Java source khác nhau”. Hãy dùng Gradle Wrapper, Java toolchain có version rõ, chạy đúng tasks, delegate IDE builds/tests sang Gradle khi cần parity, kiểm tra Gradle User Home/repos/OS và tái hiện từng biến. Sau khi sửa, giữ một test/CI job chứng minh kết quả thay vì chỉ kiểm tra trên máy của một developer.

### Tài liệu chính thức

- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): cố định Gradle distribution giữa developer/IDE/CI.
- [Gradle — Build Environment Configuration](https://docs.gradle.org/current/userguide/build_environment.html): environment, Gradle properties, priority, JAVA_HOME/GRADLE_USER_HOME.
- [Gradle — Toolchains for JVM projects](https://docs.gradle.org/current/userguide/toolchains.html): daemon JVM, IDE Gradle JVM và Java toolchain.
- [Gradle — Troubleshooting Builds](https://docs.gradle.org/current/userguide/troubleshooting.html): version, build errors và debug steps.
- [Gradle — Gradle-managed Directories and Caches](https://docs.gradle.org/current/userguide/directory_layout.html): User Home, init scripts, caches.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task caching, UP-TO-DATE/FROM-CACHE.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration reuse và inputs.
- [Gradle — Inspecting Gradle Builds](https://docs.gradle.org/current/userguide/inspect.html): logging/profile/scan.
- [IntelliJ IDEA — Gradle settings](https://www.jetbrains.com/help/idea/gradle-settings.html): Distribution, Gradle JVM, Build and run using, Run tests using.
- [IntelliJ IDEA — Work with Gradle projects](https://www.jetbrains.com/help/idea/work-with-gradle-projects.html): Gradle vs IntelliJ internal build.
