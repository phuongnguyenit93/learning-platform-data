# Phân biệt JVM chạy Gradle, Java compiler và JVM chạy kiểm thử

## 1. Vì sao cùng một dự án lại xuất hiện nhiều phiên bản Java?

Khi một Gradle project dùng Java 17, người mới thường nghĩ chạy `java -version` ra 17 là mọi bước đều dùng JDK 17. Thực tế, một build có thể đồng thời sử dụng:

1. **JVM khởi động Gradle client** — JVM của tiến trình gọi Wrapper/CLI.
2. **JVM thực thi Gradle build/Daemon** — nơi Gradle cấu hình project, chạy build logic và nhiều task actions.
3. **JDK chứa Java compiler (`javac`)** — JDK do `JavaCompile` chọn để biên dịch source.
4. **JVM chạy kiểm thử** — một hoặc nhiều **test worker processes** do task `Test` fork riêng.
5. Trong trường hợp có `JavaExec`/`application.run`, còn có **application JVM** độc lập.

Đề bài tập trung vào ba vai trò chính: **build JVM, compiler JDK và test JVM**. Tuy nhiên cần nhận ra Gradle client và Gradle Daemon **cũng có thể khác JVM**; nếu bỏ qua điều này, việc debug `JAVA_HOME`/IDE rất dễ sai.

Sau bài học, bạn sẽ:

- Xác định chính xác JVM nào chịu trách nhiệm chạy Gradle, Java compiler và test worker.
- Phân biệt `JAVA_HOME`, `org.gradle.java.home`, **Daemon JVM criteria**, Java toolchains, `sourceCompatibility`, `targetCompatibility` và `options.release`.
- Cấu hình **Java 17 compiler**, **test JVM 17 hoặc 21**, và Gradle Daemon có thể chạy trên một JDK khác khi phiên bản Gradle hỗ trợ.
- Chạy demo Java 17 + JUnit Jupiter và đọc được dấu hiệu chứng minh mỗi môi trường đang dùng phiên bản nào.
- Chẩn đoán các lỗi `UnsupportedClassVersionError`, `invalid source release`, `No matching toolchains found`, test worker launch failure và IDE/CI khác local.
- Thiết lập CI tái lập mà không phụ thuộc vào `java`/`javac` ngẫu nhiên trên `PATH`.

**Thông điệp cốt lõi:** số phiên bản được dùng để **chạy Gradle**, **biên dịch mã** và **thực thi kiểm thử** là ba quyết định khác nhau. Một cấu hình không tự thay thế hai cấu hình còn lại.

## 2. Sơ đồ các JVM trong một lần build

```text
Terminal / CI / IDE
       |
       |  ./gradlew test
       v
Gradle Client JVM  (do JAVA_HOME, PATH hoặc IDE khởi động)
       |
       |  yêu cầu build; kết nối daemon tương thích
       v
Gradle Build / Daemon JVM  (chạy settings, build scripts, plugins)
       |
       +---- JavaCompile task ------> JDK Compiler (javac)
       |                               Java toolchain / javaCompiler
       |                               tạo .class, .jar ...
       |
       +---- Test task ------------> Forked Test JVM #1
       |                               JavaLauncher / javaLauncher
       |                               chạy JUnit + code cần kiểm thử
       |                            -> Test JVM #2 (nếu parallel forks)
       |
       +---- JavaExec / run -------> Forked Application JVM
                                       javaLauncher riêng nếu cấu hình
```

**Lưu ý về quy trình:** Gradle có thể sử dụng **Java Compiler API** hoặc compiler worker bên trong một process được quản lý, chứ không nhất thiết chạy một tiến trình `javac` ngoài riêng cho mỗi lần compile. Từ “compiler JDK” nói đến **bộ công cụ/phiên bản compiler được chọn**, không hứa rằng luôn có một `javac.exe` process độc lập.

Test workers thì khác: theo Gradle, task `Test` chạy test trong **JVM forked riêng với build process**, có thể dùng memory, system properties, module args và Java version khác Gradle Daemon.

### 2.1. Bảng đối chiếu nhanh

| Vai trò | Mục đích | Cách chọn điển hình | Kiểm tra |
| --- | --- | --- | --- |
| Gradle Client JVM | Chạy CLI/Wrapper client | `JAVA_HOME`, `java` trên `PATH`, IDE launcher | `./gradlew --version` với thông tin launcher nếu phiên bản hỗ trợ |
| Gradle Build/Daemon JVM | Chạy Gradle, settings, plugins, task build logic | Daemon JVM criteria; `org.gradle.java.home`; mặc định kế thừa môi trường/Tooling API | `./gradlew --version`; in `System.getProperty("java.home")` từ task build |
| Java compiler JDK | Biên dịch `.java` thành `.class` | `java.toolchain` hoặc `JavaCompile.javaCompiler` | `javaCompiler.get().metadata`, `--info`, `javaToolchains` |
| Test worker JVM | Chạy JUnit/TestNG/tests | `Test.javaLauncher`, mặc định theo project toolchain | In `Runtime.version().feature()` bên trong test; logs task `Test` |
| `JavaExec`/`run` JVM | Chạy chương trình Java | `JavaExec.javaLauncher`, toolchain/application plugin | In Java version ngay trong `main` |

**Không đánh đồng:** `java -version` trong terminal chỉ là JVM của lệnh `java` được shell tìm thấy. Nó **không phải bằng chứng** Gradle Daemon, `JavaCompile` hoặc `Test` cũng dùng cùng JDK.

## 3. JVM chạy Gradle: Client và Daemon có thể khác nhau

### 3.1. Client JVM

Khi bạn chạy:

```bash
./gradlew --version
```

script Wrapper cần một Java runtime để khởi động Gradle client. Trong shell thông thường, `JAVA_HOME` có thể hướng Wrapper tới một JDK; nếu không có, executable `java` trên `PATH` có thể được dùng. IDE thường gọi Gradle thông qua Tooling API và có cài đặt **Gradle JVM** riêng.

Một số phiên bản Gradle mới hiển thị tách biệt **Launcher JVM** và **Daemon JVM** trong `--version`. Những bản Gradle cũ có thể chỉ in một dòng JVM; khi đó cần xem thêm daemon logs hoặc một task in system properties **trong build process**.

### 3.2. Build/Daemon JVM

Gradle Daemon là process JVM thường sống lâu giữa các lần build. Nó:

- Đọc settings và build scripts, thực thi plugin logic.
- Cấu hình tasks/graph và nhiều task actions.
- Dùng JVM runtime/library APIs mà phiên bản **Gradle Wrapper hiện tại** hỗ trợ.
- Có thể phục vụ nhiều lần build nếu Gradle version/JVM settings tương thích.

Vì vậy **JVM chạy Gradle phải nằm trong compatibility matrix của phiên bản Gradle**, không phải phiên bản bất kỳ mà code ứng dụng đang nhắm tới.

Ví dụ theo tài liệu Gradle 9.9, runtime chạy Gradle cần Java **17–27**; nhưng bản Gradle khác có phạm vi khác. Gradle 8.x/7.x không có cùng compatibility matrix. **Luôn tra tài liệu theo phiên bản Wrapper thực tế** và không lấy khoảng này làm quy tắc vĩnh viễn.

### 3.3. Ai ưu tiên khi chọn Daemon JVM?

Với Gradle hiện đại, có ba hướng phổ biến:

1. **Daemon JVM criteria** trong `gradle/gradle-daemon-jvm.properties`, cấu hình qua task `updateDaemonJvm`. Nếu đã có, **ưu tiên cao hơn** `JAVA_HOME` và `org.gradle.java.home`.
2. `org.gradle.java.home` trong `gradle.properties` hoặc cấu hình environment/IDE tương ứng, yêu cầu một Java home cụ thể cho daemon.
3. Nếu không có lựa chọn khác, Gradle thường dùng JVM khởi động Client hoặc Daemon tương thích từ môi trường hiện hành.

Ví dụ **chỉ để hiểu cú pháp**, không copy path tùy tiện vào một repository đa hệ điều hành:

```properties
org.gradle.java.home=/opt/jdks/jdk-17
```

Property này **chọn Daemon JVM**, không bắt buộc `JavaCompile` dùng JDK ấy nếu build đã khai báo toolchain khác. Và đường dẫn `/opt/jdks/jdk-17` chỉ hợp lệ khi máy đó thực sự có JDK tại vị trí tương ứng.

### 3.4. Daemon JVM criteria

Gradle hỗ trợ yêu cầu version cho Daemon thông qua:

```bash
./gradlew updateDaemonJvm --jvm-version=17
```

Lệnh này tạo/cập nhật file `gradle/gradle-daemon-jvm.properties`. Nhóm phát triển có thể commit file đó để Daemon JVM được xác định theo criteria thay vì phụ thuộc từng laptop. Tùy phiên bản Gradle, khi task tạo download URLs cho nhiều nền tảng có thể cần **toolchain download repositories/resolver** đã cấu hình; JDK phù hợp cũng có thể cần được cài sẵn.

**Khác với `java.toolchain`:** Daemon JVM criteria kiểm soát **JVM chạy Gradle**, không đồng nghĩa project Java source được compile bằng JDK đó. Một build có thể pin **Gradle Daemon Java 17**, biên dịch bằng **Java compiler 21** và chạy test JVM 17/21 nếu Wrapper/plugins hỗ trợ. Tương tự Daemon Java 21 vẫn có thể compile bằng toolchain 17.

**Lưu ý về bảo mật:** Daemon chạy build plugins/scripts; chỉ chạy các plugin/build scripts có nguồn đáng tin. Giữ Gradle Wrapper, daemon criteria và các toolchains trong phạm vi compatibility được hỗ trợ.

## 4. Java compiler: `java.toolchain` không phải `JAVA_HOME`

Java plugin cung cấp Java toolchains để chọn **JDK dùng cho compile, test, javadoc**. Trong `build.gradle.kts`:

```kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

Sau đó task `compileJava` thường sử dụng **compiler của toolchain Java 17**; `compileTestJava` cũng nhận default toolchain này. Các task `Test` và `Javadoc` mặc định được Java plugin gắn với toolchain nếu không cấu hình override.

**Điều không xảy ra:**

- Block `java.toolchain` **không chuyển JVM đang chạy Gradle Daemon sang Java 17**.
- Nó không sửa `JAVA_HOME` hay `PATH` của shell.
- Nó không bắt buộc Gradle cài toolchain từ network nếu chưa có **toolchain download repository/resolver**.
- Nó không biến code Java 21 thành code Java 17 tương thích nếu dùng những API/language features không hỗ trợ.

### 4.1. Toolchain được Gradle tìm ở đâu?

Gradle có cơ chế **tự phát hiện** JDK/JRE từ những vị trí phổ biến: `JAVA_HOME`, nơi cài OS, SDKMAN!, IDE và các công cụ quản lý JDK được hỗ trợ. Bạn cũng có thể khai báo thêm:

```properties
org.gradle.java.installations.fromEnv=JDK17,JDK21
```

Đây là một cấu hình trong `gradle.properties`. Các biến môi trường `JDK17` và `JDK21` **phải trỏ đến installation directories có thật** trên máy/CI; nếu không Gradle có thể cảnh báo và bỏ qua. Cũng có `org.gradle.java.installations.paths` để nêu paths cụ thể, nhưng không nên hardcode paths máy cá nhân trong repository dùng nhiều OS.

Liệt kê những toolchains Gradle phát hiện:

```bash
./gradlew -q javaToolchains
```

Report này cho biết **những installations có sẵn**, Java version/vendor/location và khả năng đáp ứng compiler/launcher. **Nó không tự chứng minh** một task cụ thể đã chọn toolchain nào; phải kiểm tra `JavaCompile.javaCompiler` hoặc `Test.javaLauncher` của chính task đó.

Nếu cần một JDK chưa có, Gradle có thể tự provision **chỉ khi toolchain download repositories đã được thiết lập** (thường thông qua resolver plugin). Từ Gradle 8 trở lên, không nên giả định có “download mọi JDK tự động” chỉ từ `languageVersion`. Nếu không có resolver hoặc JDK phù hợp, Gradle thường báo **No matching toolchains found**.

### 4.2. Toolchain specification có nhiều tiêu chí

Ngoài version:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
        vendor.set(JvmVendorSpec.ADOPTIUM)
    }
}
```

Đây là **lựa chọn có chủ đích**, chỉ dùng nếu dự án cần vendor cụ thể và JDK đó sẵn có/có thể provision. Chỉ định vendor có thể giảm sự khác nhau giữa developer và CI nhưng cũng khiến build fail ở máy không có vendor ấy. Không thể chỉ yêu cầu vendor mà bỏ `languageVersion` trong một toolchain specification có ràng buộc (Gradle hiện đại sẽ coi spec thiếu version là không hợp lệ).

Java toolchain còn có thể phân biệt JVM implementation, ví dụ HotSpot/OpenJ9; tuy nhiên đa số Java application không cần khóa chi tiết như vậy.

## 5. `--release` khác compiler version và source/target compatibility

Ba câu hỏi khác nhau:

1. **JDK compiler nào được dùng?** → `java.toolchain`/`javaCompiler`.
2. **Source code được phép dùng cú pháp Java nào?** → `--release` hoặc `sourceCompatibility`.
3. **Bytecode có thể chạy trên JVM phiên bản nào và được phép gọi Java API nào?** → `--release` là lựa chọn chặt nhất khi cross-compiling.

Ví dụ sử dụng JDK 21 để build code vẫn phải chạy Java 17:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
```

**Kết quả mong muốn:** Gradle chọn compiler của JDK 21; `javac --release 17` giới hạn cú pháp, bytecode và **public JDK APIs** về Java 17. Điều này cho phép compile code Java 17-compatible trên máy có compiler mới hơn. Cần chạy runtime tests trên **JVM 17 thật** để bảo đảm ứng dụng và dependency graph tương thích.

Nếu chỉ đặt:

```kotlin
java {
    sourceCompatibility = JavaVersion.VERSION_17
    targetCompatibility = JavaVersion.VERSION_17
}
```

thì compiler có thể vẫn là JDK 21 nếu đó là compiler được chọn; việc sinh bytecode target 17 **không tự chặn mọi tham chiếu API chỉ tồn tại trên Java 21**. Vì thế `options.release.set(17)` là cách hạn chế Java standard APIs đáng tin hơn.

**Giới hạn của `--release`:** nó kiểm soát **JDK APIs và source/bytecode compatibility**, không bảo đảm mọi third-party library trên compile classpath chạy được với Java 17; library riêng vẫn có thể được biên dịch bằng Java 21. Cần kiểm soát dependency variants/JVM attributes và thử runtime tests thật.

### 5.1. Bảng class-file major version

| Java target | Major version của `.class` |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Khi JVM 17 cố tải class file major 65, thường xuất hiện:

```text
java.lang.UnsupportedClassVersionError:
... has been compiled by a more recent version of the Java Runtime
```

JDK compiler mà Gradle chạy là 21 không có nghĩa artifact đã compile phải có major 65: nếu `--release 17`, bytecode thường có **major 61**. Muốn kiểm tra file đã build, dùng `javap -verbose` như ở phần kiểm chứng.

## 6. JVM chạy kiểm thử: luôn xem `Test.javaLauncher`

Task `Test` của Java plugin không chạy JUnit trực tiếp trong JVM của Gradle Daemon. Nó **fork** process Java riêng. Theo mặc định, Java plugin kết nối launcher với **project toolchain**. Nhưng bạn có thể override cho từng task:

```kotlin
tasks.named<Test>("test") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(21))
    })
}
```

Đây là **đoạn cấu hình thay thế**, chỉ hoạt động khi có task `test`, Java toolchain service và runtime Java 21 khả dụng. Khi code được compile bằng Java 17, chạy test trên Java 21 thường khả thi, nhưng điều đó **không chứng minh** sản phẩm sẽ chạy trên Java 17 trong production.

**Quan trọng:** test classes cũng cần được biên dịch. Java plugin mặc định compile `src/test/java` với toolchain Java của project. Test worker Java 21 có thể chạy test bytecode Java 17; ngược lại, test JVM Java 17 **không thể** chạy test classes được compile cho Java 21.

### 6.1. Những thứ chỉ áp dụng cho test worker

`Test` có các cấu hình như:

- `javaLauncher`: dùng Java executable từ JDK nào.
- `maxHeapSize` / `minHeapSize`: heap của test process, **không thay** `org.gradle.jvmargs` của daemon.
- `jvmArgs(...)`: JVM flags của test worker (ví dụ `--add-opens` khi cần).
- `systemProperty("key", "value")`: truyền system property **vào test JVM**, không nhất thiết vào Gradle Daemon.
- `maxParallelForks`: số test worker processes có thể chạy đồng thời.
- `forkEvery`: số test classes tối đa trên một worker trước khi tạo process khác.
- `testLogging.showStandardStreams`: cho phép xem `System.out` từ test trong Gradle console.

Cấu hình:

```kotlin
tasks.named<Test>("test") {
    maxHeapSize = "1g"
    maxParallelForks = 2
    systemProperty("app.profile", "test")
    testLogging {
        showStandardStreams = true
    }
}
```

Đây là **đoạn riêng**, không dán trùng block nếu đã định nghĩa `test` ở demo phần 7; hãy hợp nhất các tùy chọn trong một block. Khi chạy song song nhiều tests, thiết kế test data/database/files để tránh race. JVM arguments tác động tới test worker, không phải code compiler hoặc client CLI.

### 6.2. Vì sao `System.getProperty("java.version")` đôi khi gây hiểu nhầm?

Nếu một unit test in:

```java
System.out.println(System.getProperty("java.version"));
```

nó báo version của **JVM thực sự đang thực thi test**, không báo compiler JDK, không báo launcher CLI, cũng không báo `Gradle Daemon JVM`. Đặt một dòng tương tự bên trong task `doLast` sẽ báo **build JVM**; cùng API nhưng chạy ở process khác nên giá trị có thể khác.

## 7. Demo độc lập: compile bằng JDK 17, kiểm thử trên JDK 17 hoặc 21

Đây là ví dụ **Gradle Kotlin DSL + Java 17 + JUnit Jupiter**, có thể kiểm tra cả **JVM thực thi build**, **compiler JDK**, **test worker JVM**. Cấu hình mặc định chỉ cần JDK 17; nếu muốn thử khác phiên bản, cài thêm JDK 21 hoặc cấu hình toolchain provisioning.

Yêu cầu: Gradle Wrapper tương thích với JDK dùng chạy Gradle và Java 17, Maven Central truy cập được lần đầu để resolve JUnit, và Gradle Java plugin. Không cần thêm Gradle plugin ngoài core Java plugin.

### 7.1. Cấu trúc

```text
java-jvm-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── gradlew
├── gradlew.bat
└── src/
    ├── main/java/example/Greeting.java
    └── test/java/example/GreetingTest.java
```

Dùng Wrapper đã commit trong repository. Khi tạo thư mục mới hoàn toàn, có thể cần Gradle cài tạm để chạy `gradle wrapper` lần đầu; sau đó dùng `./gradlew`/`.\gradlew.bat` để version ổn định.

`settings.gradle.kts`:

```kotlin
rootProject.name = "java-jvm-lab"
```

### 7.2. Toàn bộ `build.gradle.kts`

```kotlin
import org.gradle.api.tasks.compile.JavaCompile
import org.gradle.api.tasks.testing.Test

plugins {
    java
}

repositories {
    mavenCentral()
}

java {
    // JDK dùng compile, mặc định cũng dùng cho test.
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

// Giới hạn cú pháp, bytecode và Java APIs tới Java 17.
tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

// Dùng -PtestJavaVersion=21 để đổi riêng test worker sang JDK 21.
val testJavaVersion = providers.gradleProperty("testJavaVersion")
    .map { it.toInt() }
    .orElse(17)

tasks.named<Test>("test") {
    useJUnitPlatform()

    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(
            testJavaVersion.map { JavaLanguageVersion.of(it) }
        )
    })

    // Test sẽ tự xác nhận nó thực sự chạy bằng JDK được yêu cầu.
    systemProperty("expected.test.java", testJavaVersion.get().toString())

    testLogging {
        events("passed", "failed", "skipped")
        showStandardStreams = true
    }
}

// Chạy ở JVM thực sự thực thi Gradle build/task action.
tasks.register("reportBuildJvm") {
    group = "verification"
    doLast {
        println("GRADLE_BUILD_JVM_MAJOR=" + Runtime.version().feature())
        println("GRADLE_BUILD_JAVA_HOME=" + System.getProperty("java.home"))
    }
}

// In compiler đã được chọn. Vì đây là task action, nếu task
// UP-TO-DATE thì thông tin doFirst này không xuất hiện.
tasks.named<JavaCompile>("compileJava") {
    doFirst {
        val jdk = javaCompiler.get().metadata
        println("COMPILER_JDK_MAJOR=" + jdk.languageVersion.asInt())
        println("COMPILER_INSTALLATION=" + jdk.installationPath.asFile)
    }
}
```

**Giải thích từng nhóm:**

1. `java.toolchain=17` chọn compiler JDK 17 và default launcher Java 17 cho Java-plugin test task.
2. `options.release=17` giới hạn Java language/API/bytecode; dùng cả hai để rõ JDK **được chọn** và **mức Java được phép tạo output**.
3. `testJavaVersion` là Gradle property tùy chọn, mặc định 17. Nó **không đổi compiler toolchain**.
4. `Test.javaLauncher` dùng provider từ `javaToolchains.launcherFor`, không hardcode `C:/Program Files/Java/.../java.exe`.
5. `systemProperty("expected.test.java", ...)` đi vào **test JVM**. Test đọc nó để tự đối chiếu runtime version.
6. `reportBuildJvm` chỉ in phiên bản của **JVM đang chạy task action**, không khẳng định đây là compiler/test worker.
7. `compileJava.doFirst` cho biết compiler metadata. Khi `compileJava` đã `UP-TO-DATE`, code `doFirst` không chạy; dùng `--rerun-tasks` hoặc sửa source nếu cần quan sát.
8. JUnit Jupiter là **external test library**; `mavenCentral()` giải quyết test dependencies, không liên quan tới lựa chọn JDK hoặc Gradle Wrapper.

**Vì sao không gọi `java -version` trong `build.gradle.kts`?** Shell executable có thể khác Java compiler service do Gradle chọn; chạy external command ngay trong configuration làm build khó tái lập, giảm khả năng configuration cache và che giấu toolchain selection.

### 7.3. `src/main/java/example/Greeting.java`

```java
package example;

import java.util.Locale;

public final class Greeting {
    private Greeting() {
    }

    public static String shout(String input) {
        return input.toUpperCase(Locale.ROOT);
    }
}
```

Code dùng Java standard library, không cần external dependency. `Locale.ROOT` làm phép chuyển chữ hoa không phụ thuộc locale máy người chạy.

### 7.4. `src/test/java/example/GreetingTest.java`

```java
package example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {

    @Test
    void runsOnRequestedJvm() {
        int actual = Runtime.version().feature();
        int expected = Integer.parseInt(
            System.getProperty("expected.test.java")
        );

        System.out.println("TEST_JVM_MAJOR=" + actual);
        assertEquals(expected, actual);
        assertEquals("HELLO", Greeting.shout("hello"));
    }
}
```

Hàm `Runtime.version().feature()` chạy bên trong **test worker** và trả Java major version (17, 21...). `assertEquals` làm task fail nếu worker không dùng version cấu hình. Như vậy bài demo không chỉ in thông tin mà còn **kiểm tra được tính đúng đắn**.

### 7.5. Chạy trên Linux/macOS

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew -q reportBuildJvm
./gradlew --rerun-tasks compileJava test
```

Nếu build process chạy JDK 17, `reportBuildJvm` có một dòng:

```text
GRADLE_BUILD_JVM_MAJOR=17
```

Dòng `GRADLE_BUILD_JAVA_HOME=...` là path thực tế của máy, nên không có output cố định cho mọi môi trường.

Trong lần `compileJava` thực thi, action in:

```text
COMPILER_JDK_MAJOR=17
```

Đường `COMPILER_INSTALLATION=...` cũng khác theo máy và vendor.

Test worker in:

```text
TEST_JVM_MAJOR=17
```

Dòng này thường xuất hiện bên trong vùng `STANDARD_OUT` của test trong console vì `showStandardStreams = true`; **không phải toàn bộ log của Gradle chỉ có đúng ba dòng**. Với JUnit test pass, Gradle có thể hiển thị tên test method và `BUILD SUCCESSFUL`. Các phiên bản Gradle/console modes khác nhau có thể format log khác nhau.

**Khi build JVM khác Java 17:** nếu Gradle Daemon chạy trên Java 21, dòng đầu sẽ là `GRADLE_BUILD_JVM_MAJOR=21`, trong khi compiler vẫn in 17 và test worker mặc định vẫn in 17. Đây là minh chứng trực tiếp ba vai trò không đồng nhất.

### 7.6. Chạy trên Windows PowerShell

```powershell
.\gradlew.bat --version
.\gradlew.bat -q javaToolchains
.\gradlew.bat -q reportBuildJvm
.\gradlew.bat --rerun-tasks compileJava test
```

Các giá trị major kỳ vọng trong cấu hình mặc định vẫn là compiler 17 và test JVM 17, miễn là Gradle tìm được Java 17 toolchain. Đường `JAVA_HOME` và `COMPILER_INSTALLATION` có thể dùng dấu `\` trên Windows; không dùng slash/path cố định để khẳng định tính đúng.

### 7.7. Cố ý đổi **chỉ test JVM** sang Java 21

Nếu `javaToolchains` đã hiển thị JDK/JRE 21 tương thích, chạy:

```bash
./gradlew --rerun-tasks test -PtestJavaVersion=21
```

PowerShell:

```powershell
.\gradlew.bat --rerun-tasks test -PtestJavaVersion=21
```

Khi toolchain Java 21 có sẵn, test worker in:

```text
TEST_JVM_MAJOR=21
```

**Những thứ không thay đổi:**

- `compileJava`/`compileTestJava` vẫn dùng **Java 17 compiler** theo project toolchain.
- `options.release=17` vẫn yêu cầu bytecode/API Java 17.
- Gradle Daemon JVM không tự chuyển sang Java 21 chỉ vì `-PtestJavaVersion=21`.
- Project dependencies và JUnit versions không tự thay đổi.
- Test runner có thể có hành vi khác giữa Java 17 và 21 vì reflection, modules, VM flags, native libs hoặc third-party dependencies.

Nếu chỉ có JDK 17 và chưa có configured toolchain resolver, lệnh sẽ fail kiểu **No matching toolchains found for requested specification: Java 21**. Đó là **lỗi môi trường/toolchain availability**, không phải bằng chứng `Test.javaLauncher` vô tác dụng.

### 7.8. Kiểm chứng compiler và bytecode

Sau một lần compile thành công:

```bash
javap -verbose build/classes/java/main/example/Greeting.class
```

Tìm dòng:

```text
major version: 61
```

Vì `--release 17`, bytecode Java 17 có major version 61. Nếu chạy `javap` qua PATH của một JDK quá cũ, tool có thể không hiểu class format mới; nên dùng `javap` của JDK 17+.

PowerShell có thể lọc dòng:

```powershell
javap -verbose build\classes\java\main\example\Greeting.class |
    Select-String "major version"
```

Đây là một **lệnh PowerShell nhiều dòng có dấu pipe**, không phải ký hiệu nối lệnh Bash. Nếu muốn đơn giản hơn, viết cùng một dòng.

**Điểm quan trọng:** major 61 chỉ chứng minh class file tương thích về **định dạng bytecode** với Java 17; test chạy JVM 17 thật vẫn cần để phát hiện thiếu classes, native dependencies, reflection flags hoặc lỗi logic.

## 8. Groovy DSL tương đương

Nếu project dùng `build.gradle` thay cho `build.gradle.kts`:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

tasks.named('test', Test) {
    useJUnitPlatform()
    javaLauncher = javaToolchains.launcherFor {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

Đoạn này **minh họa riêng cách đặt toolchain/launcher**, không phải một `build.gradle` đầy đủ: nếu muốn chạy JUnit phải khai báo `repositories`, JUnit dependencies và test sources như demo; nếu chưa có JDK 21 thì chỉnh test launcher về 17.

**Cả hai DSL có cùng mô hình:** Java toolchain cho compiler/default tasks, `JavaCompile.options.release` cho Java API/bytecode target, `Test.javaLauncher` override JVM thực thi test. Đừng dùng đồng thời hai file `build.gradle` và `build.gradle.kts` trong cùng một project chỉ để đặt cấu hình hai lần.

## 9. Biên dịch Java 21 nhưng kiểm thử trên Java 17: khi nào không thể?

Giả sử project có:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
```

và không có `options.release.set(17)`. Khi compile, compiler Java 21 mặc định có thể sinh bytecode major 65 hoặc dùng API chỉ có Java 21. Nếu cố chạy test worker Java 17, JVM 17 **không thể load class major 65**; có thể thấy `UnsupportedClassVersionError` trước khi test method được gọi.

Một phương án hợp lệ cho **cross-compilation** khi toolchain JDK 21 được cấu hình:

```kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}

tasks.named<Test>("test") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
```

Đây là **một đoạn thay thế cấu hình build**, không dán chồng lên block demo phần 7. Compiler chạy JDK 21 nhưng sinh code mục tiêu Java 17, test JVM chạy Java 17 để kiểm chứng thực tế. Chỉ thực hiện khi đã cài/resolve cả JDK 17 và JDK 21.

**Không giả định `--release` sửa được third-party dependencies:** nếu test classpath chứa một library đã compile bằng Java 21, test JVM 17 vẫn có thể fail vì chính library đó. Dependency variant metadata của Gradle và kiểm thử runtime phải bao phủ toàn bộ graph.

## 10. JVM của `JavaExec`/`application.run` cũng độc lập

Task `Test` không đồng nghĩa `run`. Một Java application thông thường có task `JavaExec` khác để chạy `main`. Bạn có thể đặt launcher riêng:

```kotlin
// Đoạn dành cho project áp dụng plugin application.
tasks.named<JavaExec>("run") {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
```

Project cần có application plugin + `mainClass` đã cấu hình để task `run` hoạt động. JavaExec task này dùng Java 17 launcher, không bắt test worker hay Gradle Daemon đổi theo.

**Lưu ý khi debug integration test:** nếu test code tự chạy `java` bằng `ProcessBuilder("java", ...)` mà không nối tới toolchain, child process đó có thể lại dùng PATH của test worker/environment. Điều này khác với `Test.javaLauncher` do Gradle lựa chọn. Hãy cấu hình executable path từ `JavaToolchainService.launcherFor` khi task hỗ trợ Provider, thay vì dựa vào shell path ngầm định.

## 11. `JAVA_HOME`, `PATH` và IDE: cách chúng gây sai lệch

### 11.1. `JAVA_HOME` không nhất thiết bằng `java` trên PATH

Linux/macOS:

```bash
echo "$JAVA_HOME"
java -version
javac -version
./gradlew --version
```

Windows PowerShell:

```powershell
$env:JAVA_HOME
java -version
javac -version
.\gradlew.bat --version
```

Ba thông tin có thể khác: `java`/`javac` được tìm theo `PATH`, trong khi Wrapper có thể ưu tiên `JAVA_HOME` để khởi động client. Gradle Daemon lại có thể được pin bằng criteria/property riêng. Còn `JavaCompile` và `Test` theo explicit toolchain. Vì vậy **một lệnh `java -version` không xác nhận được cả build**.

### 11.2. IDE Gradle JVM khác Project SDK

Trong IntelliJ IDEA, `Project SDK`, `Language level`, `Gradle JVM` và cấu hình **Run/Debug** là các cài đặt không nhất thiết giống nhau. IDE có thể gọi Gradle bằng JVM 21 nhưng source được compile bằng Gradle toolchain 17. Một cấu hình Run/Debug của IDE có thể chọn JVM khác task `Test` của Gradle.

Để so local/CI:

1. Xem **Gradle JVM** trong IDE settings.
2. Chạy `./gradlew --version` trong terminal cùng project.
3. Đọc `reportBuildJvm` để xác định build process JVM.
4. Xem `javaToolchains` và compiler metadata/task output.
5. Xác nhận đang chạy tests qua **Gradle Test task** hay IDE-native test runner.
6. So sánh JVM của JUnit thực tế bằng test in `Runtime.version().feature()`.

Trong Eclipse/Buildship, ý tưởng tương tự: IDE's Gradle JDK có thể khác JRE/JDK dùng chạy code theo run configuration.

### 11.3. Daemon reuse và `--stop`

Gradle có thể tái sử dụng daemon đã tồn tại nếu JVM/Gradle version và flags tương thích. Đổi `JAVA_HOME` sau một build không bắt daemon đang chạy tự biến thành JDK khác; Gradle sẽ chọn daemon phù hợp hoặc khởi động một daemon mới theo criteria.

Khi điều tra daemon bị kẹt sau thay đổi môi trường:

```bash
./gradlew --status
./gradlew --stop
./gradlew --version
```

`--stop` dừng các daemon do phiên bản Gradle tương ứng quản lý; **không sửa** toolchain selection, `options.release` hay test launcher. Không dùng nó như cách chữa mặc định mọi lỗi compilation/test.

## 12. Multi-project: mỗi module và task có thể cần JVM khác

Một build gồm `:legacy-api`, `:server` và `:integration-tests` có thể có yêu cầu khác nhau:

| Project/task | Build JVM | Compiler | Test JVM | Mục đích |
| --- | --- | --- | --- | --- |
| `:legacy-api:compileJava` | JVM Gradle chung | JDK 17, `--release 11` | Không áp dụng | Thư viện còn hỗ trợ Java 11 |
| `:server:compileJava` | JVM Gradle chung | JDK 21, `--release 21` | Không áp dụng | Ứng dụng yêu cầu Java 21 |
| `:legacy-api:test` | JVM Gradle chung | Test bytecode theo target | JVM 11 hoặc 17 | Kiểm tra compatibility |
| `:server:test` | JVM Gradle chung | Test bytecode theo target | JVM 21 | Chạy code Java 21 |
| `:integration-tests:test` | JVM Gradle chung | Theo test sources | JVM 21 | Môi trường tích hợp |

Đây là **bảng thiết kế**, không phải kết quả chạy của demo. JVM Gradle được dùng chung cho configuration/build logic của từng project trong cùng build, còn mỗi project hoặc task có thể chọn toolchain khác nhau.

Cần khai báo ở đúng scope thay vì ép mọi subproject:

```kotlin
// :legacy-api/build.gradle.kts
plugins { `java-library` }

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
```

Ở ví dụ này JDK 17 compiler có thể cross-compile code Java 11 bằng `--release 11`. Nếu test thực sự phải chạy trên Java 11, phải cấu hình `Test.javaLauncher=11` và bảo đảm **test dependencies** cũng hỗ trợ Java 11. Không coi bytecode major 55 là đủ bằng chứng ứng dụng chạy đúng trên JRE 11.

**Toolchains không tự động xử lý mọi plugin compiler:** Kotlin/Android/Scala/Groovy có các plugin và task riêng; xem tài liệu phiên bản của từng plugin để biết có tích hợp toolchain và JVM target semantics thế nào. Bài này tập trung Java plugin và `JavaCompile`/`Test`.

## 13. Khi thiếu toolchain, Gradle có tự tải JDK không?

**Không phải lúc nào cũng có.** Gradle:

1. Xem toolchain specification về languageVersion/vendor/implementation.
2. Tìm installations đã được auto-detect và custom paths.
3. Chọn một installation phù hợp theo precedence rules.
4. Nếu không thấy, có thể tải JDK **nếu đã cấu hình toolchain download repositories/resolver**.
5. Nếu không có match và không có download resolver, báo lỗi; không tự suy ra rằng `JAVA_HOME` có JDK version mong muốn.

Từ Gradle 8.x, các build thường dùng **toolchain resolver plugins** ở settings, ví dụ công cụ Foojay resolver được Gradle tài liệu hóa. Cấu hình cụ thể phụ thuộc phiên bản plugin/Gradle Wrapper; tránh copy một version plugin resolver không tương thích.

Đoạn mẫu **chỉ để hiểu vị trí cấu hình**, cần chọn plugin và version thật theo tài liệu của môi trường:

```kotlin
// settings.gradle.kts, đặt bên cạnh pluginManagement nếu có.
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}
```

Plugin ID trên là plugin Foojay resolver được Gradle sử dụng trong hướng dẫn; **version trong đoạn minh họa là giá trị cần đối chiếu với Plugin Portal/Gradle compatibility**, không phải khuyến nghị dùng máy móc. Trong dự án cần reproducibility và security, tốt nhất chọn version đã được tổ chức chấp thuận và kiểm tra JDK download source.

Nếu CI không cho tải JDK, hãy cài sẵn đúng JDK versions và dùng `javaToolchains` để xác nhận detection. Ví dụ cài JDK 17 và JDK 21 rồi đặt `org.gradle.java.installations.fromEnv=JDK17,JDK21` khi không auto-detect được.

## 14. Các lỗi điển hình và cách xác định JVM sai

### 14.1. `UnsupportedClassVersionError`

Triệu chứng:

```text
java.lang.UnsupportedClassVersionError: ...
class file version 65.0, this runtime only recognizes up to 61.0
```

Diễn giải: một class đã compile cho Java 21 (major 65) đang được load vào Java 17 JVM (chỉ hỗ trợ đến major 61). Xác định **process nào đang load class**:

- Xảy ra trong Gradle startup/plugin ⇒ có thể **Build JVM** quá cũ so với Gradle/plugin.
- Xảy ra trong `Test` ⇒ **Test worker JVM** quá cũ so với class test/application/dependency.
- Xảy ra khi `run` ⇒ **Application JVM** quá cũ.

Giải pháp không phải luôn đổi `java.toolchain`: nếu test worker cần Java 21, sửa `Test.javaLauncher`; nếu artifact phải hỗ trợ Java 17, compile lại bằng `--release 17`, bảo đảm mọi dependency tương thích và kiểm thử trên Java 17.

### 14.2. `invalid source release: 21` hoặc `release version 21 not supported`

Task đang dùng compiler quá cũ để hiểu Java 21 hoặc cấu hình `--release` không phù hợp compiler JDK. Kiểm tra `JavaCompile.javaCompiler` và `options.release`. Một compiler Java 17 **không thể** phát sinh bytecode Java 21 bằng cách đặt `targetCompatibility=21`. Cần compiler Java 21 tương ứng, đồng thời kiểm tra Wrapper/plugin compatibility.

### 14.3. `No matching toolchains found`

Gradle không tìm thấy JDK/JRE thỏa specification hoặc không có download resolver. Chạy `./gradlew -q javaToolchains`, kiểm tra vendor/version/installation path và settings toolchain resolver. **Không tự kết luận Gradle Daemon phải nâng JDK**; một daemon Java 17 vẫn có thể yêu cầu compiler Java 21.

### 14.4. Test worker process không khởi động

Các nguyên nhân khác nhau:

- `Test.javaLauncher` trỏ runtime không tồn tại/incompatible.
- Test JVM args không hợp lệ, ví dụ `--add-opens` sai hoặc flags không hỗ trợ ở Java target.
- Heap size quá lớn hoặc worker vượt tài nguyên.
- Test framework/launcher thiếu trên `testRuntimeClasspath`.
- Runtime không tương thích test class bytecode.

Kiểm tra `--info` hoặc `--stacktrace`, test results và JavaLauncher metadata. Không nhầm lỗi Java executable với JUnit assertion failure — hai lỗi ở hai thời điểm khác nhau.

### 14.5. `No tests found` hoặc task `NO-SOURCE`

Nếu `src/test/java` trống/sai path, hoặc `Test` không được cấu hình đúng source set/framework, task có thể skip hoặc không tìm được test. Đó **không phải** bằng chứng đã chạy test bằng JDK đúng. Trong demo, assertion và `TEST_JVM_MAJOR` chỉ xuất hiện khi test thật chạy.

### 14.6. CI và IDE cho kết quả khác nhau

Nguyên nhân có thể gồm: Gradle Daemon JVM settings, toolchain availability/vendor, plugin version, Gradle Wrapper, IDE-native test runner, `JAVA_HOME`, `PATH` và JDKs được CI cung cấp. Cách sửa là **ghim toolchain và Runner requirements bằng build configuration**, rồi kiểm thử trên runner sạch, không chỉ đổi một biến môi trường và hy vọng mọi task thay đổi theo.

## 15. Quy trình chẩn đoán từng bước

**Bước 1 — xác định Gradle Wrapper version.**

```bash
./gradlew --version
```

Đối chiếu Gradle/Java compatibility matrix; nếu Wrapper không chạy được trên JDK đang dùng, phải khắc phục Gradle runtime trước khi nói đến compiler/test.

**Bước 2 — xác định JVM thực thi build.**

```bash
./gradlew -q reportBuildJvm
```

Trong demo, task này in `GRADLE_BUILD_JVM_MAJOR` và `GRADLE_BUILD_JAVA_HOME`; đó là bằng chứng trực tiếp tại **task action process**, không phải `java -version` của shell.

**Bước 3 — liệt kê JDKs Gradle có thể chọn.**

```bash
./gradlew -q javaToolchains
```

Đọc Java version, vendor, installation path, valid/invalid status. Nếu yêu cầu Java 21 mà chỉ có Java 17, cần cài/provision 21.

**Bước 4 — xem compiler thực tế.**

```bash
./gradlew --rerun-tasks compileJava --info
```

Trong demo, dòng `COMPILER_JDK_MAJOR=17` từ compiler metadata xuất hiện khi task thực thi. `--info` có thể bổ sung thông tin compiler/toolchain, nhưng format log không cố định giữa các Gradle versions.

**Bước 5 — xem test worker thật.**

```bash
./gradlew --rerun-tasks test
```

Trong demo, `TEST_JVM_MAJOR=17` đi kèm JUnit assertion. Nếu muốn thử Java 21:

```bash
./gradlew --rerun-tasks test -PtestJavaVersion=21
```

Nếu test không chạy, phải xử lý task `NO-SOURCE`/JUnit configuration trước khi coi việc chọn JVM đã được xác minh.

**Bước 6 — kiểm tra class-file version và Java APIs.**

```bash
javap -verbose build/classes/java/main/example/Greeting.class
```

Tìm `major version: 61` cho `--release 17`. Chạy test trên Java target nhỏ nhất mà sản phẩm hỗ trợ, vì bytecode version đúng chưa đủ xác minh runtime compatibility.

**Bước 7 — kiểm tra IDE/CI.** So sánh Gradle JVM, Wrapper, toolchains, test tasks, `JAVA_HOME` và Java installations. Tách lỗi **Gradle runtime**, **compiler**, **test worker**, **classpath/dependency** thành các nhóm riêng.

**Bước 8 — bảo vệ khả năng tái lập.** Commit Wrapper, `build.gradle.kts`, Daemon JVM criteria nếu dùng; ghi rõ toolchain JDK versions/vendor, có CI matrix cho target runtimes và test failures. Không hardcode absolute paths hay dựa vào IDE GUI để cứu CLI build.

## 16. Bảng troubleshooting nhanh

| Hiện tượng | Vai trò thường cần kiểm tra | Cách sửa đúng hướng |
| --- | --- | --- |
| Gradle không khởi động trên JDK vừa cài | Client/Daemon JVM so với Gradle Wrapper support | Dùng JVM được Wrapper hỗ trợ hoặc nâng Wrapper |
| `./gradlew --version` báo Java 21 nhưng `compileJava` dùng 17 | Daemon vs compiler | Đây có thể là **đúng** nếu `java.toolchain=17` |
| `java -version` báo 21, test in 17 | Shell vs `Test.javaLauncher` | Đây có thể là **đúng** nếu test launcher 17 |
| `javaToolchains` thấy JDK 21 nhưng compile vẫn 17 | Availability khác selection | Đọc `JavaCompile.javaCompiler` và toolchain spec |
| `UnsupportedClassVersionError` khi test | Test runtime cũ hơn class bytecode/dependency | Cấu hình launcher tương thích hoặc rebuild target đúng |
| Compiler báo `invalid source release: 21` | Compiler JDK không hỗ trợ Java 21 | Chọn compiler JDK 21 đúng |
| `options.release=17` nhưng test JVM=21 | Compile target vs runtime | Có thể hợp lệ; vẫn cần test Java 17 nếu support 17 |
| `sourceCompatibility=17` nhưng lỗi Java 21 API trên Java 17 | Source/target không kiểm soát API đầy đủ | Dùng `--release 17`, kiểm thử runtime 17 |
| `No matching toolchains found` | Toolchain installation/resolver | Cài JDK đúng/version/vendor hoặc cấu hình resolver |
| Test bị `UP-TO-DATE`, không in JVM | Gradle task actions không chạy | Dùng `--rerun-tasks test` hoặc thay đổi input hợp lệ |
| Test task `NO-SOURCE` | Không có test classes/source set | Tạo test đúng `src/test/java` và framework |
| Test heap/flags khác kỳ vọng | Test worker config | `maxHeapSize`/`jvmArgs` trên `Test`, không chỉnh `org.gradle.jvmargs` |
| Gradle daemon OOM | Build JVM config | Xem `org.gradle.jvmargs`; không phải `Test.maxHeapSize` |
| `:app:run` dùng Java khác test | JavaExec vs Test launcher | Khai báo `JavaExec.javaLauncher` riêng |
| IDE chạy khác CLI | Gradle JVM/IDE runner vs toolchains | So settings, Gradle Test runner, Wrapper và test Java |
| Chạy Java 17 class trên Java 21 được nhưng không ngược lại | JVM bytecode backward compatibility | Compile target đúng và test trên runtime tối thiểu |
| CI chạy test bằng JDK khác laptop | Different installations/daemon criteria | Pin versions/toolchains, xem `javaToolchains`, chạy matrix |
| JDK vendor khác nhau gây lỗi native/crypto | Toolchain vendor/runtime differences | Cân nhắc vendor criteria và CI coverage |

## 17. Một mẫu chiến lược CI có thể kiểm chứng

Đối với thư viện hứa hỗ trợ Java 17 nhưng nhóm phát triển chạy Gradle bằng JDK 21:

- **Gradle Daemon JVM:** JDK nằm trong Gradle Wrapper compatibility matrix (có thể 21), được chỉ định qua Daemon criteria hoặc CI.
- **Compiler:** JDK 17 hoặc JDK mới hơn kết hợp `--release 17` để bảo đảm class target.
- **Unit tests tối thiểu:** chạy trên **JVM 17 thật** để phát hiện API/bytecode incompatibility.
- **Runtime matrix:** chạy thêm cùng test suite trên Java 21 để phát hiện sự khác biệt hành vi.
- **Toolchain provisioning:** cài sẵn JDK 17/21 trên CI hoặc cấu hình resolver với nguồn JDK tin cậy.
- **Dependencies:** đảm bảo JUnit launcher/testRuntimeClasspath và third-party libraries phù hợp các runtime.
- **Build reproducibility:** dùng Wrapper, versions cố định, kiểm soát plugin compatibility và Gradle dependency verification khi cần.

Lệnh thử trên runner có đủ JDK:

```bash
./gradlew --rerun-tasks test -PtestJavaVersion=17
./gradlew --rerun-tasks test -PtestJavaVersion=21
```

Hai invocation sẽ chạy cùng test code ở hai JVM target, không tự tạo một task/cấu hình JUnit khác. Trên CI dùng **hai jobs/matrix entries** nếu muốn lưu kết quả độc lập và tránh cache/task output bị nhầm.

**Đừng chỉ chạy test trên JVM mới nhất:** một Java 17 library có thể chạy tốt trên Java 21 dù chứa API không tồn tại trên Java 17, nếu compiler/target không giới hạn đúng. Test trên **runtime tối thiểu được hỗ trợ** là một tiêu chí nghiệm thu riêng.

## 18. Câu hỏi tự kiểm tra

1. **Đã đặt `JAVA_HOME` sang Java 21, `java.toolchain=17`: `compileJava` dùng compiler nào?** Thường JDK 17 nếu Gradle tìm được matching toolchain; `JAVA_HOME` có thể ảnh hưởng client/build JVM nhưng không override toolchain đã khai báo.
2. **`java -version` trong terminal ra 17, test in 21: có mâu thuẫn không?** Không. Test worker dùng `Test.javaLauncher` có thể chọn Java 21.
3. **Gradle Daemon chạy Java 17 có thể compile bằng Java 21 không?** Có, nếu Gradle Wrapper/toolchain support và compiler Java 21 được cung cấp.
4. **`sourceCompatibility=17` có bảo đảm không dùng Java 21 APIs không?** Không. `options.release=17` bảo vệ standard JDK API compatibility tốt hơn.
5. **`--release 17` có tự tải JDK 17 không?** Không. Nó điều chỉnh compiler được chọn; compiler có thể là JDK mới hơn.
6. **Test có chạy trong Daemon không?** Test tasks thông thường fork worker JVM riêng, không chạy JUnit trực tiếp trong Gradle Daemon.
7. **`javaToolchains` list JDK 21 có nghĩa `Test` đã dùng 21?** Không. Phải xem `Test.javaLauncher` hoặc in version trong test.
8. **Có thể dùng `Test.maxHeapSize` để tăng heap Gradle Daemon không?** Không. Daemon dùng `org.gradle.jvmargs`/settings riêng.
9. **Nếu `compileJava` có outcome `UP-TO-DATE` mà không in compiler version, compiler JDK bị mất?** Không. Task action bị skip; dùng `--rerun-tasks` để quan sát.
10. **JDK 21 compiler + `--release 17` + test JVM 17 là mô hình hợp lệ không?** Có, khi tất cả source/dependencies/Gradle/toolchain supports tương thích.
11. **Nếu máy chỉ có JDK 17 nhưng task yêu cầu test JVM 21, Gradle sẽ tải chắc chắn không?** Không. Cần toolchain download repositories/resolver hoặc cài JDK 21 sẵn.
12. **Vì sao daemon criteria có thể khiến `JAVA_HOME` không quyết định build JVM?** Vì Gradle ưu tiên Daemon JVM criteria khi file cấu hình có hiệu lực.

## 19. Checklist trước khi đưa vào CI

- [ ] Dùng Gradle Wrapper đã pin, tra đúng Java compatibility matrix của Wrapper đó.
- [ ] Xác định JVM của client/Gradle Daemon, compiler và test worker **riêng**.
- [ ] Không lấy `java -version`/`javac -version` trên shell làm bằng chứng cho Gradle task selection.
- [ ] Khai báo `java.toolchain.languageVersion` cho Java compilation.
- [ ] Khi phải hỗ trợ Java thấp hơn compiler JDK, dùng `JavaCompile.options.release` và test trên target runtime thật.
- [ ] Cấu hình `Test.javaLauncher` có chủ đích nếu test JVM khác compiler/default.
- [ ] Kiểm tra `./gradlew -q javaToolchains` và toolchain availability trên CI.
- [ ] Nếu dùng auto-provisioning, có resolver/repos được quản trị và JDK được phép tải.
- [ ] Biết `org.gradle.java.home`, Daemon JVM criteria, `JAVA_HOME`, IDE Gradle JVM ưu tiên theo cách nào.
- [ ] Có JUnit/TestNG engine/launcher và đúng `src/test/java`; task không bị `NO-SOURCE`.
- [ ] Test output/assertion xác nhận Java major version thực dùng.
- [ ] Kiểm tra bytecode major bằng `javap -verbose` khi cần.
- [ ] Với `JavaExec`/application runner, chọn launcher riêng; không tự coi giống `Test`.
- [ ] CI chạy test trên runtime nhỏ nhất được support và thêm runtime khác khi cần.
- [ ] Không thay JVM version để che lỗi dependency, API, plugin hoặc class-file incompatibility.

## 20. Ghi nhớ

- **JVM chạy Gradle** điều khiển Gradle/Plugin/build logic; có client và daemon, không nhất thiết là một installation.
- **Java compiler** được chọn bởi Java toolchain/`JavaCompile.javaCompiler`; không bắt buộc giống Daemon JVM.
- **JVM chạy kiểm thử** được chọn bởi `Test.javaLauncher` và fork độc lập; có thể khác cả compiler lẫn Daemon.
- **`--release`** chọn Java language/API/bytecode target, **không** chọn JDK compiler hoặc test JVM.
- **`sourceCompatibility`/`targetCompatibility`** không thay thế `--release` khi cần chặn newer JDK APIs.
- **`JAVA_HOME`** là môi trường/launch default, không override explicit toolchains hoặc Daemon JVM criteria.
- **`javaToolchains` liệt kê JDKs; task metadata và test output mới xác nhận JDK thực sự được dùng**.
- **Chạy test trên Java phiên bản thấp nhất được hỗ trợ** để phát hiện vấn đề runtime, bất kể môi trường build đang chạy trên JDK nào.

## Tài liệu chính thức

- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): project/toolchain configuration, `JavaCompile.javaCompiler`, `Test.javaLauncher`, `--release`, detection và provisioning.
- [Gradle — Gradle Daemon](https://docs.gradle.org/current/userguide/gradle_daemon.html): Client JVM, Daemon JVM, `org.gradle.java.home` và Daemon JVM criteria.
- [Gradle — Java Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): Java versions dùng chạy Gradle so với Java toolchain support theo phiên bản Gradle.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): test worker JVM riêng, JUnit Jupiter, `Test` task options.
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html): toolchains, `--release`, source/target compatibility.
- [Gradle — Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): JavaCompile, Test, source sets và tasks.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.named` và `configureEach` lazy.
