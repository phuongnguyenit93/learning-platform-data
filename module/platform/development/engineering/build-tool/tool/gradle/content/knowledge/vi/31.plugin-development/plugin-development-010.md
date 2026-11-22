# Thiết lập fixture, chạy nhiều phiên bản Gradle và kiểm tra task outcome khi phát triển plugin

## 1. Vì sao plugin Gradle cần functional tests?

Một plugin Gradle có thể compile thành công và unit tests của một helper Java cũng có thể xanh, nhưng plugin vẫn hỏng khi người dùng thật viết:

```groovy
plugins {
    id 'org.example.greeting'
}

tasks.named('writeGreeting') {
    // Plugin DSL, task configuration và output của người dùng.
}
```

Những lỗi như plugin ID không resolve, task chưa được đăng ký, thiếu runtime dependency, output path sai, input tracking sai, configuration cache không hoạt động hay một API chỉ tồn tại ở một phiên bản Gradle thường **không được phát hiện bằng unit test Java thuần**. Cần kiểm thử **một Gradle build thật** được tạo trong thư mục fixture nhỏ.

Gradle **TestKit** cung cấp `GradleRunner` để chạy một build thực sự trong môi trường test, rồi đọc `BuildResult`, `BuildTask` và `TaskOutcome`. Kiểm thử plugin theo cách này thường gọi là **functional test** hoặc **black-box integration test**.

Một vòng kiểm thử hữu ích:

```text
Plugin source
   |
   v
Compile plugin classes + plugin marker metadata
   |
   v
JUnit test tạo temporary Gradle project (fixture)
   |
   v
settings.gradle + build.gradle + optional inputs
   |
   v
GradleRunner + withPluginClasspath()
   |
   v
Chạy Gradle version A/B với task được chọn
   |
   v
BuildResult: output, tasks và task outcomes
   |
   v
Assert task outcome + output file contents + failure behavior
```

**Điểm khác biệt quan trọng:** unit test thường gọi method của plugin/helper trong một JVM test; TestKit chạy **build Gradle thật**, với plugin resolution, configuration, task graph và task execution. Vì thế không nên chỉ kiểm tra `result.getOutput().contains("BUILD SUCCESSFUL")`: hãy kiểm tra **task outcome** và **nội dung artifact** mà plugin tạo ra.

### Kết quả học tập

Bạn sẽ biết cách tạo fixture bằng JUnit Jupiter `@TempDir`; định nghĩa một binary Gradle plugin Java 17 và task có `@Input`/`@OutputFile`; dùng `GradleRunner.withProjectDir`, `withArguments`, `withPluginClasspath`, `build` và `buildAndFail`; chạy test qua hai bản Gradle `8.14.3` và `9.2.1`; khẳng định `SUCCESS`, `UP_TO_DATE`, `FROM_CACHE`, `NO_SOURCE`, `SKIPPED`, `FAILED`; cô lập caches; thiết kế test matrix/CI; và xử lý lỗi thường gặp của TestKit.

## 2. Ba mức độ kiểm thử plugin Gradle

| Cấp độ | Cách kiểm tra | Phát hiện tốt | Không thay thế |
| --- | --- | --- | --- |
| **Unit test Java/Kotlin** | Gọi trực tiếp helper classes, dùng JUnit/Mockito khi phù hợp. | Thuật toán, validation, format dữ liệu. | Plugin application và Gradle execution thật. |
| **ProjectBuilder test** | `ProjectBuilder.builder().build()` tạo model Project để gọi `Plugin.apply`. | Một phần configuration/extension/task registration. | Full task execution, plugin resolution, Gradle runtime đầy đủ. |
| **TestKit functional test** | `GradleRunner` chạy fixture Gradle project. | `plugins { }`, task execution/outcomes, caching, outputs, compatibility. | Performance load test, kiểm chứng deployment/repository thật nếu fixture chỉ local. |

Tài liệu Gradle nói rõ `GradleRunner` dùng Tooling API để chạy build trong **process riêng**, nên code plugin của test JVM **không tự xuất hiện** ở classpath build đang được test. Cần cung cấp plugin-under-test classpath hoặc publish plugin ra repository cho fixture resolve.

### 2.1. TestKit không phải JUnit

`gradleTestKit()` cấp các API như `GradleRunner`, `BuildResult`, `TaskOutcome`, nhưng **không** chứa `@Test`, `@TempDir` hoặc `@ParameterizedTest`. Bạn vẫn cần JUnit Jupiter (hoặc Spock/TestNG). Trong bài lab, dùng JUnit 5 cùng Java 17 để có test methods và fixture directory riêng biệt.

### 2.2. Khi nào nên dùng fixture thật?

Tạo fixture để kiểm tra:
- Plugin ID áp dụng được trong `plugins { }`.
- Plugin đăng ký task ở đúng path `:writeGreeting`.
- `-Pwho=Team` đổi được input.
- Task tạo `build/greetings/message.txt` với bytes/nội dung mong muốn.
- Chạy lại inputs không đổi cho kết quả `UP_TO_DATE`.
- Bật build cache và xóa output có thể cho `FROM_CACHE`.
- Input không hợp lệ gây build fail có kiểm soát.
- Gradle versions nằm trong support policy đều chạy được.

Một test tốt kiểm tra **hành vi bên ngoài**; chỉ inspect implementation internals làm test dễ vỡ khi refactor plugin không đổi contract.

## 3. GradleRunner và những API chủ chốt

| API | Tác dụng |
| --- | --- |
| `GradleRunner.create()` | Tạo runner. |
| `withProjectDir(File)` | Chỉ tới root directory chứa fixture Settings/build scripts. |
| `withArguments(String...)` | Truyền tasks và CLI flags, ví dụ `writeGreeting`, `--build-cache`, `-Pwho=Team`. |
| `withPluginClasspath()` | Inject plugin-under-test classpath theo metadata do `java-gradle-plugin` tạo. |
| `withPluginClasspath(Iterable<File>)` | Chỉ định plugin classpath thủ công khi cần custom setup. |
| `withGradleVersion(String)` | Chọn Gradle distribution cụ thể cho build dưới test. |
| `withGradleInstallation(File)` | Chọn Gradle installation có sẵn trên máy. |
| `withGradleDistribution(URI)` | Chọn Gradle distribution từ URI. |
| `withTestKitDir(File)` | Cố định nơi TestKit lưu runtime state/Gradle User Home để cô lập và tái dùng có chủ đích. |
| `build()` | Chạy build **kỳ vọng thành công**; build fail sẽ làm test nhận exception. |
| `buildAndFail()` | Chạy build **kỳ vọng thất bại**; build thành công sẽ làm test nhận exception. |
| `BuildResult.getOutput()` | Text output của build dưới test, dùng cho log/failure diagnostics. |
| `BuildResult.task(":name")` | Tìm `BuildTask` theo full task path, có thể trả `null`. |
| `BuildTask.getOutcome()` | Enum outcome thay vì parse chuỗi `UP-TO-DATE` thủ công. |
| `BuildResult.getTasks()` | Tập `BuildTask` được ghi nhận. |

**`result.task(":writeGreeting")` khác `result.task("writeGreeting")`.** API dùng **task path** thường có dấu `:` trước tên root task. Nếu test đòi task không có trong task graph, `result.task(...)` có thể là `null`; cần `assertNotNull` trước khi xem outcome. Một task bị loại hoàn toàn bằng `-x` khác task **đã nằm trong graph nhưng có outcome SKIPPED**.

## 4. Sáu TaskOutcome và semantics chính xác

Gradle TestKit API có enum:

| TaskOutcome | Nghĩa chính xác | Tình huống dễ tạo |
| --- | --- | --- |
| `SUCCESS` | Task đã chạy và thực thi actions thành công. | Lần đầu chạy `writeGreeting`. |
| `UP_TO_DATE` | Task không chạy lại vì inputs/outputs vẫn up-to-date. | Chạy lại cùng fixture và tham số, output còn nguyên. |
| `FROM_CACHE` | Task bỏ qua work và lấy output từ build cache. | Cacheable task + `--build-cache` + cache entry sẵn + output thiếu. |
| `NO_SOURCE` | Task bỏ qua vì những file inputs có `@SkipWhenEmpty` trống. | `compileJava` khi Java plugin được áp dụng nhưng fixture không có Java sources. |
| `SKIPPED` | Task không được thực thi vì lý do khác như `onlyIf` false. | Task `ignored` dùng `onlyIf { false }`. |
| `FAILED` | Task cố thực thi nhưng bị lỗi. | Input validation của `writeGreeting` phát sinh exception. |

**Những outcome này không hoán đổi.** `UP_TO_DATE` không có nghĩa task vừa thực thi thành công; `FROM_CACHE` không chứng minh task action đã chạy; `NO_SOURCE` không phải một case `SUCCESS`; `SKIPPED` không nhất thiết do `-x`; `FAILED` không được kiểm chứng bằng `build()` khi fail là điều mong đợi — phải dùng `buildAndFail()`.

`FROM_CACHE` chỉ xuất hiện khi build dưới test sử dụng caching và task cacheable. `NO_SOURCE` là outcome riêng được Gradle hỗ trợ từ phiên bản 3.4; nếu ma trận hỗ trợ Gradle rất cũ, semantics enum/task logging có thể khác. Bài lab chọn **8.14.3** và **9.2.1**, cả hai là bản phát hành có thật và hỗ trợ chạy với JDK 17.

## 5. Thiết kế fixture: chính xác, tạm thời và không chạm dự án thật

### 5.1. Vì sao dùng @TempDir?

JUnit Jupiter `@TempDir` tạo một thư mục tạm cho mỗi test case theo lifecycle thích hợp, giúp:
- Không sửa `build.gradle`, source files hay outputs của plugin project thật.
- Các tests không tranh nhau cùng `.gradle` hoặc `build/` directory.
- Dễ tạo các tình huống riêng: thiếu Java source, input trống, skipped task, cache hit.
- Test không lệ thuộc trạng thái của một run trước nếu không chủ đích dùng chung fixture.

Ví dụ:

```java
@TempDir
Path testProjectDir;
```

Các file fixture có thể được ghi bằng Java 17 `Files.writeString` với UTF-8. Mỗi test tạo `settings.gradle` và `build.gradle` vào directory này, rồi cung cấp `testProjectDir.toFile()` cho runner.

### 5.2. Những thành phần fixture tối thiểu

```text
/tmp/junit-fixture-12345/
├── settings.gradle
├── build.gradle
├── .testkit/               (TestKit storage, do test tạo)
├── .gradle/                (Gradle project state)
└── build/
    └── greetings/
        └── message.txt    (output từ plugin task)
```

Thư mục temp thực tế phụ thuộc OS/JUnit, không được hard-code `/tmp` trên Windows. Không commit `.testkit` hoặc `.gradle` của fixture vào source repository. Nếu cần debug, lưu temporary fixture/snapshot ở CI artifact storage theo policy nhưng xóa/cache đúng kỳ hạn.

### 5.3. Test fixture phải phản ánh contract người dùng

Nếu plugin được sử dụng qua `plugins { id 'org.example.greeting' }`, fixture phải apply plugin theo cách đó. Một test chỉ gọi `new GreetingPlugin().apply(project)` không kiểm tra plugin marker, resolution hay classloader. Nếu plugin cần `settings.gradle.kts`, version catalog, external repository, file input hoặc project dependency, fixture phải cung cấp chúng đủ và *không* lấy ngầm từ máy developer.

## 6. Bài lab hoàn chỉnh: binary Gradle plugin Java 17

Bài này tạo một plugin nhỏ tên `org.example.greeting`, đăng ký task `writeGreeting`. Task có:
- Property input `recipient`.
- Output file `build/greetings/message.txt`.
- Action ghi `Hello, <recipient>!` và newline UTF-8.
- Input validation: recipient trống gây build fail.
- `@CacheableTask` để minh họa `FROM_CACHE`.

Plugin sẽ được build bằng core `java-gradle-plugin` và kiểm thử bằng TestKit/JUnit 5. Ví dụ Gradle build script bên dưới dùng Kotlin DSL; fixture test build script dùng Groovy DSL để kiểm tra chính thao tác plugin application qua cả hai DSL về nguyên tắc.

### 6.1. Cây thư mục chính xác

```text
greeting-gradle-plugin/
├── settings.gradle.kts
├── build.gradle.kts
└── src/
    ├── main/java/org/example/
    │   ├── GreetingFormatter.java
    │   ├── GreetingTask.java
    │   └── GreetingPlugin.java
    └── test/java/org/example/
        └── GreetingPluginFunctionalTest.java
```

Bài lab này **không tạo file Maven publication**. `java-gradle-plugin` đăng ký plugin ID và generate plugin descriptors/marker metadata phục vụ build logic; TestKit inject compiled implementation để fixture apply mà không cần publish trước.

### 6.2. settings.gradle.kts

```kotlin
rootProject.name = "greeting-gradle-plugin"
```

### 6.3. build.gradle.kts: cấu hình producer plugin

```kotlin
plugins {
    `java-gradle-plugin`
}

group = "org.example"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

gradlePlugin {
    plugins {
        create("greeting") {
            id = "org.example.greeting"
            implementationClass = "org.example.GreetingPlugin"
            displayName = "Greeting example plugin"
            description = "Generates a greeting text file"
        }
    }
}

dependencies {
    // java-gradle-plugin đã hỗ trợ TestKit; khai báo explicit để rõ ý.
    testImplementation(gradleTestKit())

    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testImplementation("org.junit.jupiter:junit-jupiter-params:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.test {
    useJUnitPlatform()
}
```

**Giải thích:**

- `java-gradle-plugin` đăng ký plugin-under-test metadata, Gradle API classes cần cho `Plugin<Project>` và TestKit integration.
- `gradlePlugin.plugins.create("greeting")` đặt plugin ID thật `org.example.greeting` cùng implementation class. Plugin ID này là **giá trị fixture dùng trong `plugins { }`**, không phải Maven coordinates.
- `testImplementation(gradleTestKit())` cung cấp `GradleRunner`/`TaskOutcome`. Với `java-gradle-plugin`, TestKit integration đã được Gradle thiết lập; khai báo tường minh giúp người học nhìn thấy dependency.
- `junit-jupiter-params` cấp `@ParameterizedTest` và `@ValueSource` cho version matrix.
- `testRuntimeOnly(junit-platform-launcher)` giúp test task chạy JUnit Platform đúng.
- `java.toolchain=17` build plugin classes thành Java 17-compatible bytecode. Gradle 8.14.3/9.2.1 đều hỗ trợ chạy trên JDK 17; chọn Gradle Wrapper producer tương thích.
- Source code plugin được chạy **trong Gradle build dưới test**, không phải trong một application runtime `java -jar`.

### 6.4. Java helper độc lập — GreetingFormatter.java

**`src/main/java/org/example/GreetingFormatter.java`:**

```java
package org.example;

import java.util.Objects;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String message(String who) {
        String name = Objects.requireNonNull(who, "who").strip();
        if (name.isEmpty()) {
            throw new IllegalArgumentException(
                "recipient must not be blank"
            );
        }
        return "Hello, " + name + "!";
    }

    public static void main(String[] args) {
        System.out.println(message(" Gradle "));
    }
}
```

Đây là **Java 17 standard library code**, có thể biên dịch và chạy ngoài Gradle:

```bash
mkdir -p manual-out
javac --release 17 -d manual-out src/main/java/org/example/GreetingFormatter.java
java -cp manual-out org.example.GreetingFormatter
```

**Stdout chính xác:**

```text
Hello, Gradle!
```

`GreetingFormatter.message(" ")` ném `IllegalArgumentException` có message `recipient must not be blank`. Đây là case được test bằng `buildAndFail()` qua task Gradle.

### 6.5. Custom task — GreetingTask.java

**`src/main/java/org/example/GreetingTask.java`:**

```java
package org.example;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

@CacheableTask
public abstract class GreetingTask extends DefaultTask {
    @Input
    public abstract Property<String> getRecipient();

    @OutputFile
    public abstract RegularFileProperty getDestination();

    @TaskAction
    public void writeGreeting() throws IOException {
        String message = GreetingFormatter.message(getRecipient().get());

        Path output = getDestination().get().getAsFile().toPath();
        Files.createDirectories(output.getParent());
        Files.writeString(
            output,
            message + "\n",
            StandardCharsets.UTF_8
        );

        getLogger().lifecycle("WROTE_GREETING=" + message);
    }
}
```

**Vì sao dùng typed properties?**

- `@Input Property<String>` cho Gradle theo dõi `recipient` và nhận biết khi input đổi.
- `@OutputFile RegularFileProperty` cho Gradle biết file nào task tạo, có thể kiểm tra up-to-date hoặc restore từ cache.
- `@CacheableTask` cho phép cache output nếu task hành xử deterministic và inputs/outputs đúng. Đây là trách nhiệm của plugin author; annotation không sửa được task có hidden input.
- `Files.writeString(..., UTF_8)` tạo bytes rõ ràng và newline `\n` cố định.
- Task action không tham chiếu `Project`/Gradle script instance trong execution time, thân thiện với Configuration Cache.
- `getLogger().lifecycle` giúp quan sát action ở lần `SUCCESS`; khi task `UP_TO_DATE` hoặc `FROM_CACHE`, action không chạy và log marker này không nhất thiết có.

**Không biên dịch class này bằng JDK `javac` đơn lẻ**: nó import Gradle API (`DefaultTask`, `RegularFileProperty`, annotations). Hãy compile bằng `./gradlew classes` của plugin producer. Chỉ `GreetingFormatter.java` là class độc lập chạy bằng `javac` ở mục trước.

### 6.6. Gradle plugin — GreetingPlugin.java

**`src/main/java/org/example/GreetingPlugin.java`:**

```java
package org.example;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class GreetingPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getTasks().register(
            "writeGreeting",
            GreetingTask.class,
            task -> {
                task.getRecipient().convention(
                    project.getProviders()
                        .gradleProperty("who")
                        .orElse("Gradle")
                );
                task.getDestination().convention(
                    project.getLayout().getBuildDirectory()
                        .file("greetings/message.txt")
                );
            }
        );
    }
}
```

Plugin sử dụng `tasks.register` để đăng ký task **lazily**, không tạo và cấu hình toàn bộ tasks sớm bằng `tasks.create`. `providers.gradleProperty("who")` đọc project property `-Pwho=...` theo Provider API; default `Gradle`. Output file nằm dưới `layout.buildDirectory` và được thay bằng convention/override nếu người dùng cần.

Plugin **không** tự apply `java` plugin vào fixture. Chức năng `writeGreeting` chỉ cần Gradle APIs, không phụ thuộc project Java sources. Điều này cho phép test `NO_SOURCE` bằng cách fixture apply `java` riêng mà không tác động task greeting.

## 7. Tạo JUnit fixture và GradleRunner

Đây là file functional test **đầy đủ** cho các cases cơ bản và Gradle version matrix. Mỗi test tạo một Gradle project ở `@TempDir` riêng, không sửa producer build scripts.

### 7.1. GreetingPluginFunctionalTest.java

**`src/test/java/org/example/GreetingPluginFunctionalTest.java`:**

```java
package org.example;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.BuildTask;
import org.gradle.testkit.runner.GradleRunner;
import org.gradle.testkit.runner.TaskOutcome;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class GreetingPluginFunctionalTest {
    @TempDir
    Path projectDir;

    private void fixture(String additionalBuildScript)
            throws IOException {

        Files.writeString(
            projectDir.resolve("settings.gradle"),
            "rootProject.name = 'greeting-fixture'\n",
            StandardCharsets.UTF_8
        );

        Files.writeString(
            projectDir.resolve("build.gradle"),
            "plugins { id 'org.example.greeting' }\n"
                + additionalBuildScript,
            StandardCharsets.UTF_8
        );

        Files.createDirectories(projectDir.resolve(".testkit"));
    }

    private GradleRunner runner(String... arguments) {
        return GradleRunner.create()
            .withProjectDir(projectDir.toFile())
            .withTestKitDir(projectDir.resolve(".testkit").toFile())
            .withPluginClasspath()
            .withArguments(arguments);
    }

    private static TaskOutcome outcome(
            BuildResult result, String taskPath) {

        BuildTask task = result.task(taskPath);
        assertNotNull(
            task,
            "Expected task " + taskPath + ", output:\n"
                + result.getOutput()
        );
        return task.getOutcome();
    }

    private Path outputFile() {
        return projectDir.resolve("build/greetings/message.txt");
    }

    @Test
    void firstRunWritesExpectedOutput() throws IOException {
        fixture("");

        BuildResult result = runner(
            "writeGreeting", "-Pwho=Team"
        ).build();

        assertEquals(
            TaskOutcome.SUCCESS, outcome(result, ":writeGreeting")
        );
        assertEquals(
            "Hello, Team!\n",
            Files.readString(outputFile(), StandardCharsets.UTF_8)
        );
        assertTrue(
            result.getOutput().contains("WROTE_GREETING=Hello, Team!")
        );
    }

    @Test
    void secondRunIsUpToDate() throws IOException {
        fixture("");

        BuildResult first = runner(
            "writeGreeting", "-Pwho=Team"
        ).build();

        BuildResult second = runner(
            "writeGreeting", "-Pwho=Team"
        ).build();

        assertEquals(
            TaskOutcome.SUCCESS, outcome(first, ":writeGreeting")
        );
        assertEquals(
            TaskOutcome.UP_TO_DATE, outcome(second, ":writeGreeting")
        );
        assertEquals(
            "Hello, Team!\n",
            Files.readString(outputFile(), StandardCharsets.UTF_8)
        );
    }

    @Test
    void invalidRecipientFailsAsExpected() throws IOException {
        fixture("");

        BuildResult result = runner(
            "writeGreeting", "-Pwho="
        ).buildAndFail();

        assertEquals(
            TaskOutcome.FAILED, outcome(result, ":writeGreeting")
        );
        assertTrue(
            result.getOutput().contains("recipient must not be blank")
        );
        assertFalse(Files.exists(outputFile()));
    }

    @Test
    void onlyIfFalseProducesSkipped() throws IOException {
        fixture(
            "tasks.register('ignored') {\n"
                + "    onlyIf { false }\n"
                + "    doLast { println('UNEXPECTED_ACTION') }\n"
                + "}\n"
        );

        BuildResult result = runner("ignored").build();

        assertEquals(
            TaskOutcome.SKIPPED, outcome(result, ":ignored")
        );
        assertFalse(
            result.getOutput().contains("UNEXPECTED_ACTION")
        );
    }

    @Test
    void emptyJavaSourcesProduceNoSource() throws IOException {
        fixture("apply plugin: 'java'\n");

        BuildResult result = runner("compileJava").build();

        assertEquals(
            TaskOutcome.NO_SOURCE, outcome(result, ":compileJava")
        );
    }

    @ParameterizedTest
    @ValueSource(strings = {"8.14.3", "9.2.1"})
    void compatibleWithMultipleGradleVersions(String version)
            throws IOException {

        fixture("");

        BuildResult result = runner(
            "writeGreeting", "-Pwho=Matrix"
        ).withGradleVersion(version).build();

        assertEquals(
            TaskOutcome.SUCCESS, outcome(result, ":writeGreeting")
        );
        assertEquals(
            "Hello, Matrix!\n",
            Files.readString(outputFile(), StandardCharsets.UTF_8)
        );
    }
}
```

**Hai điều kiện khi chạy nguyên bài lab:**

1. Producer phải compile bằng Gradle Wrapper/JDK tương thích, có `java-gradle-plugin` và plugin metadata.
2. TestKit cần Gradle distributions `8.14.3`/`9.2.1` sẵn trong cache hoặc được phép tải từ distribution service/mirror. Máy air-gapped chưa có distributions sẽ fail trước khi test behavior, không chứng minh plugin không tương thích.

### 7.2. Lệnh chạy plugin tests

Từ thư mục `greeting-gradle-plugin` có Gradle Wrapper:

```bash
./gradlew --version
./gradlew classes
./gradlew test
./gradlew test --tests org.example.GreetingPluginFunctionalTest
./gradlew check
```

Đây là các task của **producer plugin build**, còn `GradleRunner` bên trong mỗi test запуска một fixture Gradle build độc lập. Không chạy `gradle writeGreeting` ở producer vì plugin được compile và đăng ký nhưng **chưa được apply vào producer project**. Task `:writeGreeting` chỉ tồn tại trong fixture đã apply `org.example.greeting`.

### 7.3. Các assertion kiểm tra điều gì?

- Test đầu: task là `SUCCESS`, output file đúng UTF-8, có message từ `getLogger().lifecycle`.
- Test thứ hai: chạy cùng fixture/args hai lần; lần 2 `UP_TO_DATE` vì `@Input`/`@OutputFile` đã khai báo.
- Test thất bại: `buildAndFail()` chứng minh build phải fail; `FAILED` và message xác nhận đúng nguyên nhân.
- Test `ignored`: `onlyIf { false }` tạo task trong graph nhưng không chạy action; outcome là `SKIPPED`.
- Test `compileJava`: Java plugin có mặt nhưng fixture không có Java sources; `NO_SOURCE`.
- Test version matrix: chạy plugin trên **hai Gradle distributions thật**, assert task/outcome/file content với mỗi bản.

**Không chỉ assert `result.getOutput().contains("BUILD SUCCESSFUL")`**; chuỗi log có thể thay đổi theo Gradle version/logging. `TaskOutcome` và output files là những kiểm tra trực tiếp hơn. Khi cần kiểm tra log, dùng marker duy nhất do plugin chủ động in như `WROTE_GREETING=Hello, Team!`, không parse toàn bộ Gradle console.

## 8. Kiểm thử FROM_CACHE với cacheable task

`FROM_CACHE` đòi hỏi task cacheable, build cache được bật, có cache entry phù hợp và outputs cần restore. `@CacheableTask` trên `GreetingTask` là một phần cần thiết; nếu không có annotation/cấu hình caching, chỉ chạy `--build-cache` **không đủ** để task lấy từ cache.

### 8.1. Thêm test method vào cùng class

Thêm một method **bên trong `GreetingPluginFunctionalTest`**, không tạo class/fixture thứ hai:

```java
@Test
void missingOutputCanBeRestoredFromCache() throws IOException {
    fixture("");

    Path settings = projectDir.resolve("settings.gradle");
    Files.writeString(
        settings,
        Files.readString(settings, StandardCharsets.UTF_8)
            + "buildCache {\n"
            + "    local {\n"
            + "        directory = file('fixture-build-cache')\n"
            + "    }\n"
            + "}\n",
        StandardCharsets.UTF_8
    );

    BuildResult first = runner(
        "writeGreeting", "--build-cache", "-Pwho=Cache"
    ).build();

    assertEquals(
        TaskOutcome.SUCCESS, outcome(first, ":writeGreeting")
    );
    assertEquals(
        "Hello, Cache!\n",
        Files.readString(outputFile(), StandardCharsets.UTF_8)
    );

    Files.delete(outputFile());

    BuildResult restored = runner(
        "writeGreeting", "--build-cache", "-Pwho=Cache"
    ).build();

    assertEquals(
        TaskOutcome.FROM_CACHE, outcome(restored, ":writeGreeting")
    );
    assertEquals(
        "Hello, Cache!\n",
        Files.readString(outputFile(), StandardCharsets.UTF_8)
    );
}
```

`fixture-build-cache` là một **local build cache riêng nằm trong temporary project**, được cấu hình bằng Settings của fixture. Cả hai GradleRunner invocations dùng cùng project directory và cùng `.testkit` storage. Thứ tự:
1. Lần đầu: task action chạy và ghi output, cache entry được lưu.
2. Xóa **chỉ output file**, không xóa cache.
3. Lần sau: Gradle không còn output để coi là UP_TO_DATE, nhưng có cached output với cùng input snapshot; kỳ vọng `FROM_CACHE`.
4. Verify file đã được phục hồi đúng bytes.

**Cảnh báo thực tế:** caching có thể bị tắt/bị điều chỉnh bởi init scripts hoặc chính sách doanh nghiệp; nếu test `FROM_CACHE` không ổn định, kiểm tra report `--info`, task caching disabled reasons và local cache configuration. Không sửa assertion từ `FROM_CACHE` thành `SUCCESS` chỉ để bỏ qua lỗi cache; hãy giải thích vì sao cache bị vô hiệu.

### 8.2. Phân biệt UP_TO_DATE và FROM_CACHE

`UP_TO_DATE` dựa trên outputs vẫn còn và task inputs/outputs không đổi; `FROM_CACHE` dựa trên cached task outputs được restore. Khi test muốn chứng minh `FROM_CACHE`, cần **xóa output hoặc dùng project khác** và bảo đảm cache entry vẫn được chia sẻ. Nếu chỉ chạy task hai lần mà giữ file, outcome thường là `UP_TO_DATE` — điều đó không chứng minh caching có lỗi.

### 8.3. Cẩn trọng về trạng thái môi trường

Task caching dựa trên input fingerprint và task implementation identity. Nếu plugin classpath hoặc task implementation đổi giữa hai invocations, cache key có thể khác, đúng ra sẽ là `SUCCESS`. Với TestKit:
- Giữ nguyên producer/plugin code giữa hai lần trong một test.
- Dùng `withTestKitDir` hoặc cache directory có chủ đích để không mất entry.
- Không dùng global Gradle User Home của developer làm test dependency.
- Không đánh dấu `@CacheableTask` cho task có network/random/timestamp/hidden inputs chưa khai báo.

## 9. Chạy nhiều phiên bản Gradle với withGradleVersion

Trong bài lab:

```java
@ParameterizedTest
@ValueSource(strings = {"8.14.3", "9.2.1"})
void compatibleWithMultipleGradleVersions(String version)
        throws IOException {
    fixture("");
    BuildResult result = runner("writeGreeting", "-Pwho=Matrix")
        .withGradleVersion(version)
        .build();

    assertEquals(
        TaskOutcome.SUCCESS, outcome(result, ":writeGreeting")
    );
}
```

**Mỗi row parameter là một build Gradle thật.** TestKit có thể tải Gradle distribution tương ứng nếu chưa cache. Hai phiên bản `8.14.3` (Gradle 8.x) và `9.2.1` (Gradle 9.x) là ví dụ hỗ trợ JDK 17; chúng không được chọn vì “mới nhất” mà để kiểm thử **hai major release lines**. Team nên dùng matrix đúng support policy của plugin, ví dụ:
- Minimum supported Gradle version.
- Phiên bản LTS/ổn định đang được phần lớn consumers dùng (nếu tổ chức xác định).
- Bản mới nhất mà pipeline hỗ trợ ở thời điểm release.
- Phiên bản prerelease/RC chỉ khi team có chính sách thử sớm và chấp nhận failures tương ứng.

### 9.1. Java và Gradle compatibility phải giao nhau

Muốn chạy Gradle 8.14.3 và 9.2.1, phải có **JVM runtime tương thích với cả hai**. Bài lab dùng Java 17:
- Gradle 8.14.3 hỗ trợ chạy trên JDK 17.
- Gradle 9.2.1 có yêu cầu JVM tối thiểu Java 17.
- Plugin classes được compile target Java 17.
- Plugin API sử dụng trong `GreetingPlugin` phải tồn tại ở cả hai.

Nếu bạn compile plugin bằng Java 21 bytecode, rồi TestKit chạy fixture Gradle JVM 17, sẽ có `UnsupportedClassVersionError` trước khi kiểm thử task. Nếu chọn một Gradle version quá cũ cho JDK hiện tại, Tooling API/daemon compatibility có thể fail ngay khi khởi chạy.

**`withGradleVersion` chỉ chọn Gradle distribution, không phải một API tổng quát để chọn mọi JDK runtime của fixture.** Với JDK matrix, thường chạy test suite trên các CI jobs có `JAVA_HOME`/toolchains tương ứng và chọn từng cặp JDK/Gradle được compatibility matrix hỗ trợ. Tách ma trận Gradle versions khỏi Java matrix để dễ debug.

### 9.2. Không tự động dùng một version string mơ hồ

`withGradleVersion("8.14.3")` cố định một release cụ thể. `withGradleVersion("latest")` không phải cách hay để kiểm tra compatibility có thể tái hiện. Nếu team có job “latest Gradle”, job có thể resolve release mới từ official metadata trước khi chạy, nhưng **luôn ghi lại exact distribution version** và kiểm soát network/trust.

### 9.3. withGradleInstallation và withGradleDistribution

Khi môi trường CI air-gapped, GradleRunner có:
- `withGradleInstallation(File)`: dùng distribution đã cài tại path được quản lý.
- `withGradleDistribution(URI)`: dùng distribution URI đã biết và được phê duyệt.
- `withGradleVersion(String)`: cơ chế thông dụng nhất cho version matrix.

Không gọi cả ba trong một builder chain rồi suy đoán precedence. Chọn **một** nguồn Gradle distribution mỗi test. Nếu sử dụng mirror nội bộ, quản lý checksum của Gradle distributions và có retention thay vì tải không kiểm soát.

## 10. Kotlin DSL fixture và Groovy DSL fixture

Producer build script `build.gradle.kts` dùng Kotlin, nhưng fixture ví dụ sử dụng Groovy để kiểm tra plugin application. Để mở rộng kiểm thử DSL, bạn có thể tạo fixture **Kotlin DSL** thay cho `build.gradle`:

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "greeting-fixture"
```

**`build.gradle.kts`:**

```kotlin
plugins {
    id("org.example.greeting")
}

tasks.named<org.example.GreetingTask>("writeGreeting") {
    recipient.set("Kotlin")
}
```

**Lưu ý về classpath:** typed reference tới `org.example.GreetingTask` trong Kotlin build script có thể phụ thuộc việc plugin-under-test được inject đúng và script classpath resolution. Để fixture tối giản không lộ implementation class, có thể dùng project property:

```kotlin
plugins {
    id("org.example.greeting")
}
// Task dùng -Pwho=Kotlin để cấu hình qua public input convention.
```

Lệnh fixture vẫn là `writeGreeting -Pwho=Kotlin`. Output file chứa:

```text
Hello, Kotlin!
```

Groovy DSL tương đương:

```groovy
plugins {
    id 'org.example.greeting'
}
// Task dùng -Pwho=Groovy.
```

Nếu muốn test cả hai DSL, dùng `@ParameterizedTest` với mỗi fixture script filename/content tương ứng. **Không tạo đồng thời `build.gradle` và `build.gradle.kts` trong một fixture** rồi giả định Gradle sẽ chọn đúng bản.

### 10.1. Nếu plugin dùng extension DSL thay vì project property

Plugin thực tế thường có:
- `extensions.create("greeting", GreetingExtension.class)`.
- `Property<String>` trên extension.
- Task lấy convention từ extension property.
- Groovy/Kotlin DSL cho users.

Khi đó fixture phải test **configuration DSL contract** (default, overrides, invalid values, plugin order) chứ không chỉ CLI `-Pwho`. Bài lab chọn project property cho dễ chạy độc lập, nhưng phương pháp TestKit hoàn toàn giống nhau.

## 11. Producer build.gradle Groovy tương đương

Nếu repository phát triển plugin dùng Groovy DSL thay vì Kotlin DSL, `java-gradle-plugin` và TestKit vẫn có cùng API. Giữ các Java sources từ mục 6 và test class JUnit từ mục 7; thay hai scripts producer:

**`settings.gradle`:**

```groovy
rootProject.name = 'greeting-gradle-plugin'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java-gradle-plugin'
}

group = 'org.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

gradlePlugin {
    plugins {
        greeting {
            id = 'org.example.greeting'
            implementationClass = 'org.example.GreetingPlugin'
            displayName = 'Greeting example plugin'
            description = 'Generates a greeting text file'
        }
    }
}

dependencies {
    testImplementation gradleTestKit()
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testImplementation 'org.junit.jupiter:junit-jupiter-params:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Đây là **một build script thay thế** cho bản Kotlin, không đặt cả hai trong cùng project. Test fixture có thể vẫn dùng Groovy/Kotlin DSL độc lập với DSL của producer.

## 12. Nếu muốn một functionalTest suite riêng

Trong bài lab đơn giản, functional tests nằm ở `src/test/java` và chạy bằng task `test`. Với plugin lớn, có thể tách:
- `src/test/java`: unit tests, chạy nhanh.
- `src/functionalTest/java`: TestKit functional tests, có thể tải Gradle distributions.
- `src/integrationTest/java`: tương tác với môi trường/kho ngoài nếu cần.

Gradle `java-gradle-plugin` hỗ trợ cấu hình test source sets cho plugin-under-test metadata; nếu tách khỏi mặc định `test`, phải **nói rõ source set nào được dùng để inject plugin classpath**.

Một snippet cấu hình **phần mở rộng có chủ đích**, không độc lập với build.gradle producer ở trên:

```kotlin
// Trong build.gradle.kts đã áp dụng java-gradle-plugin.
val functionalTest = sourceSets.create("functionalTest")

val functionalTestTask = tasks.register<Test>("functionalTest") {
    group = "verification"
    description = "Runs Gradle TestKit functional tests"
    testClassesDirs = functionalTest.output.classesDirs
    classpath = functionalTest.runtimeClasspath
    useJUnitPlatform()
}

gradlePlugin {
    testSourceSets(functionalTest)
}

tasks.check {
    dependsOn(functionalTestTask)
}
```

**Còn phải khai báo JUnit Jupiter/launcher dependencies và source set classpath** tương ứng nếu không kế thừa từ `test`. Đoạn trên minh họa task wiring và `testSourceSets`, không nên dán nó vào một build không có dependencies/Java tests rồi kỳ vọng tự chạy đầy đủ.

Tài liệu Gradle cũng có **JVM Test Suite plugin** để tổ chức các suites theo convention; `java-gradle-plugin` tích hợp với JVM Test Suite. Chọn một phương pháp phù hợp phiên bản Gradle mà bạn support và kiểm tra `withPluginClasspath()` đang lấy đúng metadata của test suite. Nếu vừa sử dụng `test` vừa `functionalTest`, hãy tránh chạy version matrix nặng hai lần không cần thiết.

## 13. Kiểm thử task outcomes theo từng lớp semantics

### 13.1. SUCCESS: xác minh outputs, không chỉ task status

Một `SUCCESS` chỉ có nghĩa task action hoàn tất không lỗi. Nó không chứng minh nội dung output đúng. Trong test `firstRunWritesExpectedOutput`, assert **cả** `TaskOutcome.SUCCESS` và `Files.readString(...)` bằng `"Hello, Team!\n"`. Đó là behavior contract thực tế của plugin.

### 13.2. UP_TO_DATE: hai lần chạy không đổi inputs

Task chỉ có cơ hội `UP_TO_DATE` nếu:
- Có khai báo input/output được Gradle theo dõi.
- Output của lần đầu vẫn tồn tại và không bị sửa đổi.
- Input `recipient` vẫn cùng giá trị.
- Task implementation/Gradle state không thay đổi một cách làm invalidation.

Nếu task có no outputs hoặc side effects chưa khai báo, Gradle có thể chạy lại mỗi lần. Một test `UP_TO_DATE` thất bại có thể chỉ ra task không mô hình hóa inputs/outputs đúng.

### 13.3. FROM_CACHE: cần cache key và dữ liệu đã lưu

Một build cache hit không chỉ dựa vào tên task. Gradle tính fingerprint từ task implementation, inputs, output properties, classpath metadata theo yêu cầu. Để test, cần chủ động tạo cached output, xóa output local, chạy lại trong setup ổn định. Nếu cache bị disabled, sẽ chạy `SUCCESS` thay vì `FROM_CACHE`.

### 13.4. NO_SOURCE: không phải lỗi plugin

Với `compileJava`, nếu Java plugin đã áp dụng nhưng fixture không có Java source, `NO_SOURCE` thường là điều đúng. Đừng coi nó là test failure nếu mục tiêu là chứng minh task được Gradle xử lý đúng khi không có source.

### 13.5. SKIPPED: test task có mặt trong graph

Task `ignored` có `onlyIf { false }` nên sẽ có outcome `SKIPPED`. Còn khi dùng `-x ignored`, Gradle có thể không ghi task đó trong BuildResult, vì task đã bị loại khỏi graph; `result.task(":ignored")` có thể `null`, không được tùy tiện ép outcome.

### 13.6. FAILED: kiểm tra lỗi có nghĩa và không để lại artifact

`buildAndFail()` trả `BuildResult` khi build **thất bại đúng kỳ vọng**. Verify task `:writeGreeting` là `FAILED` và output chứa message `recipient must not be blank`. Ở lab, validation chạy trước khi viết output, vì vậy `Files.exists(outputFile())` false. Nếu task đã ghi partial output trước khi throw, cần xác định output cleanup policy, không mặc định task fail đồng nghĩa không còn file.

## 14. BuildResult.getOutput không thay thế task outcome

Một đoạn test mong manh:

```java
assertTrue(result.getOutput().contains("BUILD SUCCESSFUL"));
assertTrue(result.getOutput().contains("writeGreeting"));
```

Nó có thể pass dù task `writeGreeting` bị `UP_TO_DATE` trong khi test muốn xác minh action chạy, hoặc dù log chứa tên task từ một thông báo khác. Output format có thể thay đổi qua Gradle versions.

Cách tốt hơn:

```java
BuildTask task = result.task(":writeGreeting");
assertNotNull(task);
assertEquals(TaskOutcome.SUCCESS, task.getOutcome());

assertEquals(
    "Hello, Team!\n",
    Files.readString(
        projectDir.resolve("build/greetings/message.txt"),
        StandardCharsets.UTF_8
    )
);
```

Dùng `result.getOutput()` để debug và assert **messages do plugin kiểm soát**, không parse toàn bộ console. Đừng dùng regular expression chung cho log framework khi đã có enum outcome chính thức.

## 15. Kiểm thử task path và multi-project fixture

Ở fixture một project, task path của root thường là `:writeGreeting`. Với multi-project build:

```text
fixture/
├── settings.gradle
├── build.gradle
└── app/build.gradle
```

`settings.gradle`:

```groovy
rootProject.name = 'multi-fixture'
include 'app'
```

`app/build.gradle`:

```groovy
plugins {
    id 'org.example.greeting'
}
```

Runner:

```java
BuildResult result = GradleRunner.create()
    .withProjectDir(projectDir.toFile())
    .withPluginClasspath()
    .withArguments(":app:writeGreeting", "-Pwho=Module")
    .build();
```

Assert task path **`:app:writeGreeting`**, và output file nằm ở `app/build/greetings/message.txt`. Nếu fixture dùng `withTestKitDir` trong test helper, giữ cách cô lập như trước. Đây là **snippet minh họa**; cần tạo đủ files/directories và plugin classpath như trong fixture helper khi dùng thực tế.

Multi-project fixture hữu ích khi plugin có logic phụ thuộc project path, task dependencies giữa modules hoặc configuration inheritance. Nhưng với plugin chỉ xử lý một task, fixture một project chạy nhanh và rõ hơn.

## 16. TestKitDir, Gradle User Home và isolation

`GradleRunner` quản lý build bằng Tooling API và dedicated daemon/storage, khác với việc gọi `gradlew` trong shell người dùng. Theo Gradle docs:
- TestKit có working storage riêng theo test/runner, và có thể chỉ định `withTestKitDir(File)`.
- Build dưới test không nên giả định sẽ kế thừa mọi nội dung `~/.gradle/gradle.properties`/repository của developer.
- TestKit daemons là riêng so với daemons của các Gradle invocations thông thường và được quản lý bởi TestKit.
- `withTestKitDir` dùng để **cố định nơi lưu state** cho tests cần lặp cùng fixture/cache; nơi đó vẫn là implementation detail, đừng viết code truy cập file nội bộ của TestKit.

### 16.1. Isolation không đồng nghĩa không có network

`withGradleVersion` có thể tải Gradle distribution nếu version chưa được cache. Fixture có thể resolve external plugins/dependencies nếu build script cấu hình repositories. Vì vậy một test “offline” phải:
1. Pre-provision Gradle distributions.
2. Tránh external dependencies trong fixture hoặc cache/mirror được duyệt.
3. Truyền `--offline` khi appropriate, nhưng biết rằng `--offline` không thể tự tạo artifacts chưa cache.
4. Phân biệt failure do network/repository với failure của plugin behavior.

Bài lab có plugin chỉ dùng Gradle API/JDK; **fixture** không cần Maven Central để build source app. **Producer** cần JUnit dependency từ Maven Central hoặc cache. Không nên nói TestKit hoàn toàn không phụ thuộc network trong version matrix.

### 16.2. Parallel test pitfalls

Nếu các tests cùng ghi chung `/tmp/test-fixture` hoặc một global Gradle User Home, chúng có thể:
- Overwrite `build.gradle` của nhau.
- Tranh file locks/cache.
- Nhận `UP_TO_DATE`/`FROM_CACHE` do run khác tạo.
- Gây flaky tests khi CI chạy parallel.

`@TempDir` per-test và TestKitDir riêng giảm rủi ro. Với các test cố ý share cache, thiết kế một shared cache directory có kiểm soát và phân biệt input fingerprints, tránh dùng cache của developer làm nguồn chân lý.

## 17. Java compatibility và TestKit cross-version matrix

Gradle TestKit `withGradleVersion` chọn Gradle distribution cho fixture, nhưng compatibility cần xem xét nhiều lớp:

| Lớp | Điều phải kiểm tra |
| --- | --- |
| **JVM chạy Gradle dưới test** | Gradle version có hỗ trợ JDK runtime đang dùng? |
| **Java bytecode của plugin** | Gradle JVM có load được class file version không? |
| **Gradle API calls** | Plugin có gọi method chỉ thêm ở bản Gradle mới hơn không? |
| **Embedded Kotlin/Groovy** | Nếu plugin/build logic dùng Kotlin/Groovy APIs, version chênh giữa Gradle distributions có thể gây lỗi. |
| **Third-party plugins** | Plugin dependencies có hỗ trợ Gradle version đang test không? |
| **Tasks/options** | Một API/task property đã deprecated/removed có thể gây fail ở major version mới. |
| **Tooling API/TestKit** | Runner/under-test version nằm trong compatibility range được hỗ trợ không? |

Lỗi `UnsupportedClassVersionError` thường thuộc Java classfile version, không nhất thiết do Gradle TaskOutcome. `NoSuchMethodError`/`ClassNotFoundException` khi apply plugin có thể chỉ ra Gradle API/classpath mismatch. `InvalidRunnerConfigurationException` có thể đến từ TestKit configuration không hợp lệ. Bất cứ lỗi nào cũng nên báo rõ **Gradle version** của matrix row.

### 17.1. Minimum supported version là quyết định sản phẩm

Nếu plugin cần Gradle 9-only API, đừng cố ép nó pass Gradle 8.14.3 bằng việc thay assertion. Hãy:
- Định nghĩa rõ minimum supported Gradle version.
- Tránh gọi API mới trong code paths dùng ở Gradle cũ hoặc có compatibility branch được test.
- Nâng minimum khi cần, ghi changelog và migration guide.
- Cập nhật version matrix theo support policy và CI JDK matrix.

## 18. Chạy cross-version tests trong CI mà không làm quá tải pipeline

Một chiến lược có thể gồm:
- **PR nhanh:** unit tests + TestKit một Gradle version chính, vài fixture cốt lõi.
- **Merge/main:** minimum supported và latest supported Gradle, nhiều plugin DSL cases.
- **Release gate:** toàn bộ Gradle/JDK supported combinations, build cache/configuration cache, negative cases và publication consumer smoke.
- **Nightly/weekly:** prerelease Gradle để phát hiện deprecation/breaking changes sớm.

Không nên tạo Cartesian matrix quá rộng nếu mỗi job tải hàng trăm MB Gradle distribution mà không mang thêm rủi ro cần kiểm soát. Chọn representative versions theo contract và ghi rõ lý do.

### 18.1. Làm test selection rõ ràng

```bash
./gradlew test
./gradlew test --tests org.example.GreetingPluginFunctionalTest
./gradlew test --tests '*GreetingPluginFunctionalTest.compatibleWithMultipleGradleVersions*'
```

Với parameterized tests, Gradle `--tests` filter behavior phụ thuộc Gradle/JUnit Platform version; nếu selection không như mong muốn, test cả class bằng `--tests org.example.GreetingPluginFunctionalTest` trước. Không dùng test filtering như cách lách một compatibility failure khi phát hành stable plugin.

### 18.2. CI logs và diagnostics

Khi matrix row fail, record:
- Target Gradle version.
- Plugin producer Gradle version/Wrapper.
- JVM vendor/version.
- Test fixture build/settings files (không chứa secrets).
- Full `BuildResult.output`.
- Task path/outcome nếu task tồn tại.
- Exception stacktrace/test report.
- Distribution/cache source và checksum policy.

Nếu có cache miss/network failure, rerun với distribution đã provisioned; không biến “download fail” thành claim plugin API không tương thích.

## 19. Configuration Cache testing cho plugin

Bài lab task được viết bằng `Property`/`RegularFileProperty` và không capture `Project` trong `@TaskAction`, nên có cấu trúc thuận lợi cho Configuration Cache. Có thể thêm functional test:

```java
@Test
void worksWithConfigurationCache() throws IOException {
    fixture("");

    BuildResult first = runner(
        "writeGreeting", "-Pwho=CC", "--configuration-cache"
    ).build();

    BuildResult second = runner(
        "writeGreeting", "-Pwho=CC", "--configuration-cache"
    ).build();

    assertEquals(
        TaskOutcome.SUCCESS, outcome(first, ":writeGreeting")
    );
    assertEquals(
        TaskOutcome.UP_TO_DATE, outcome(second, ":writeGreeting")
    );
    assertEquals(
        "Hello, CC!\n",
        Files.readString(outputFile(), StandardCharsets.UTF_8)
    );
}
```

Đây là test bổ sung vào class cùng fixture helper. Nếu plugin thật dùng hidden configuration inputs, Project access từ task action hoặc untracked environment, Configuration Cache có thể fail/stale. Không chỉ assert output chứa “cache reused” vì text của Gradle có thể thay đổi; kiểm tra task behavior và dùng Gradle Configuration Cache report để xử lý failures.

**Cần phân biệt:** Configuration Cache lưu *configuration/task graph*, Build Cache lưu *task outputs*, UP_TO_DATE dựa trên local output/input state. Một task UP_TO_DATE không tự chứng minh Configuration Cache đã được reused; nếu muốn kiểm chứng cache reuse, cần report hoặc kiểm tra riêng evidence theo Gradle version.

## 20. Kiểm thử plugin dưới cả settings.gradle và build.gradle

Plugin phát triển cho `Plugin<Project>` như `GreetingPlugin` phải được apply ở **project** `build.gradle`. Nó không phải Settings plugin. Nếu một plugin implement `Plugin<Settings>` hoặc `Plugin<Gradle>`, fixture phải test đúng entry point:
- Settings plugin được apply trong `settings.gradle(.kts)`.
- Project plugin được apply trong `build.gradle(.kts)`.
- Settings/pluginManagement resolution có lifecycle khác `Project` configuration.

Đừng thử plugin ID trong file sai lifecycle rồi kết luận TestKit broken. Khi plugin cần init script, enterprise repository hoặc composite build, fixture phải tạo những files ấy có chủ đích và ghi rõ assumptions.

## 21. Plugin-under-test classpath: vấn đề thường bị bỏ sót

`withPluginClasspath()` hoạt động khi `java-gradle-plugin` cung cấp metadata đúng và fixture dùng `plugins { id '...' }`. Theo Gradle docs, cơ chế auto injection này:
- Lấy plugin implementation classes và dependencies từ producer plugin-under-test metadata.
- Không tự publish plugin lên Maven/Plugin Portal.
- Có các hạn chế với plugins dùng `compileOnly` để phụ thuộc API của plugin khác.

Nếu plugin của bạn dùng `compileOnly` dependency tới external plugin API, TestKit injected classpath có thể thiếu classes cần thiết, gây `ClassNotFoundException`. Tài liệu Gradle khuyến nghị cho trường hợp này **publish plugin vào local Maven repository** rồi để fixture resolve từ repository đó, thay vì chỉ dùng `withPluginClasspath()`.

### 21.1. Vì sao `plugins { }` quan trọng?

Nếu fixture dùng legacy pattern `apply plugin: 'org.example.greeting'` mà không có plugin classpath tương ứng, auto injection có thể không hoạt động giống `plugins { id '...' }`. Bài lab dùng `plugins` block để TestKit tự inject classpath và kiểm thử plugin ID resolution theo con đường được docs hỗ trợ.

### 21.2. Khi phải test published plugin thực tế

TestKit injection kiểm tra code/plugin-under-test classes nhưng không phải là bằng chứng plugin marker đã publish đúng lên Plugin Portal hay Maven repository. Release-quality tests có thể:
1. Publish plugin vào private/file Maven staging repository.
2. Tạo fixture có `pluginManagement.repositories` trỏ đúng staging repo.
3. Apply plugin bằng ID + version như consumer thật.
4. Verify GAV/plugin marker resolution và task behavior.
5. So staging artifact checksum/signature với bản phát hành.

Đây là test bổ sung cho TestKit black-box loop, đặc biệt quan trọng khi plugin có runtime dependencies hoặc marker metadata phức tạp.

## 22. Build result failure vs exception trong chính test

Chọn API đúng:
- `runner(...).build()` khi build **phải thành công**.
- `runner(...).buildAndFail()` khi build **phải thất bại**.

Nếu bạn gọi `build()` cho input sai, GradleRunner sẽ throw `UnexpectedBuildFailure`, và JUnit test fail trước khi xem `TaskOutcome.FAILED`. Nếu bạn gọi `buildAndFail()` cho input hợp lệ, nó sẽ throw `UnexpectedBuildSuccess`.

Khi muốn kiểm tra thông điệp failure và outcome:
```java
BuildResult failed = runner(
    "writeGreeting", "-Pwho="
).buildAndFail();

assertEquals(
    TaskOutcome.FAILED, outcome(failed, ":writeGreeting")
);
assertTrue(
    failed.getOutput().contains("recipient must not be blank")
);
```

**Không suppress exceptions từ `GradleRunner` rồi tự coi test pass**. Exceptions về classpath/distribution/test environment cũng cần được phân loại, không được đổi thành “plugin behavior failed” khi chưa chạy task.

## 23. Những tình huống test cần được quản lý theo fixture

| Fixture variant | Mục tiêu |
| --- | --- |
| Empty root project + plugin applied | Plugin ID và task registration. |
| Project property `-Pwho=Team` | Configuration input override. |
| Empty `who` | Validation failure có message rõ. |
| Two successive builds | UP_TO_DATE và input tracking. |
| Deleted output + build cache | FROM_CACHE và restore output. |
| Java plugin + no sources | NO_SOURCE. |
| Task `onlyIf { false }` | SKIPPED. |
| Kotlin DSL `build.gradle.kts` | Plugin resolution/Kotlin DSL compatibility. |
| Multi-project `:app` | Task path, module-scoped output, cross-project wiring. |
| Older/newer Gradle versions | API/bytecode/runtime support matrix. |
| `--configuration-cache` repeat | Configuration reuse safety và task correctness. |
| External repository fixture | Plugin publication/marker/compileOnly behavior. |
| Invalid output path/permissions | Helpful failure messaging, no silent partial artifacts. |
| Inputs changed between runs | SUCCESS rebuild với output mới, không false UP_TO_DATE. |

Không cần tạo tất cả fixtures trong mọi plugin nhỏ. Chọn cases dựa trên behavior contract và rủi ro: Gradle plugin publish công khai nên ít nhất có tests cho plugin application, tasks/outputs, invalid inputs và minimum/latest supported Gradle.

## 24. Kiểm thử input thay đổi: không UP_TO_DATE giả

Thêm method sau vào class `GreetingPluginFunctionalTest` nếu muốn kiểm thử Gradle input fingerprint:

```java
@Test
void changingInputRunsTaskAgain() throws IOException {
    fixture("");

    BuildResult first = runner(
        "writeGreeting", "-Pwho=Alice"
    ).build();

    BuildResult second = runner(
        "writeGreeting", "-Pwho=Bob"
    ).build();

    assertEquals(
        TaskOutcome.SUCCESS, outcome(first, ":writeGreeting")
    );
    assertEquals(
        TaskOutcome.SUCCESS, outcome(second, ":writeGreeting")
    );
    assertEquals(
        "Hello, Bob!\n",
        Files.readString(outputFile(), StandardCharsets.UTF_8)
    );
}
```

Với `@Input Property<String>` đã khai báo, Gradle thấy input đổi và chạy task lại. Nếu task báo `UP_TO_DATE` dù input đổi, rất có thể author **không khai báo input** hoặc đang đọc hidden state ngoài Gradle task model.

## 25. Cách tái hiện bug của người dùng thành fixture

Một bug report có thể là “plugin chạy tốt Gradle 8.x nhưng không chạy Gradle 9.x với Kotlin DSL” hoặc “second build không UP_TO_DATE”. Đừng sửa plugin ngay và chỉ chạy unit tests. Hãy tạo fixture tối thiểu:

1. Ghi đúng target Gradle/JDK versions và plugin version.
2. Tạo build script apply đúng plugin ID và configuration từ report.
3. Tạo chính các input files cần thiết, bỏ những dependency không liên quan.
4. Dùng `GradleRunner.withGradleVersion(...)` để tái hiện version.
5. Đưa task vào graph bằng explicit task path và arguments.
6. Assert failure/success outcome + output file content.
7. Sau khi fix, chạy test cũ trên affected version và các supported versions khác.
8. Giữ fixture như regression test trong repository.

Một test tái hiện lỗi theo behavior contract bền hơn ảnh chụp console log dài. Nếu issue liên quan đúng một Gradle minor version, thêm case đó vào matrix tạm thời, và gộp phiên bản vào support matrix lâu dài nếu có rủi ro tương tự.

## 26. Troubleshooting TestKit và GradleRunner

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| `Plugin [id: 'org.example.greeting'] was not found` | Plugin ID không được đăng ký, `withPluginClasspath` thiếu metadata hoặc fixture không dùng `plugins {}`. | Kiểm tra `gradlePlugin.plugins`, `implementationClass`, TestKit integration. |
| `InvalidPluginMetadataException` | `withPluginClasspath()` không tìm thấy/đọc được metadata. | Dùng `java-gradle-plugin`, test source set chính xác, metadata generation. |
| `NoClassDefFoundError`/`ClassNotFoundException` | Plugin runtime dependency thiếu, `compileOnly` external API trong TestKit classpath. | Kiểm tra dependency scopes; dùng staged publication fixture nếu cần. |
| `UnsupportedClassVersionError` | Plugin bytecode target mới hơn JVM dùng chạy tested Gradle. | Điều chỉnh Java toolchain/target và test matrix JDK. |
| `Could not find method ...` trên Gradle cũ | Plugin gọi Gradle API chưa tồn tại ở target version. | Chốt minimum Gradle, dùng compatibility branch hoặc bỏ version không support. |
| `GradleRunner.build()` ném `UnexpectedBuildFailure` | Build fail nhưng test kỳ vọng success. | Xem output/stacktrace, xác định có cần `buildAndFail()` hay sửa code. |
| `GradleRunner.buildAndFail()` ném `UnexpectedBuildSuccess` | Build không fail như negative test dự kiến. | Kiểm tra input validation fixture/CLI args. |
| `result.task(...) == null` | Task path sai, task không vào graph, excluded task hoặc build fail quá sớm. | Xem `getTasks()` và full paths, `:app:task` khi multi-project. |
| Test kỳ vọng `SUCCESS` nhưng nhận `UP_TO_DATE` | Fixture state được tái dùng hoặc test đã chạy task trước đó. | Dùng @TempDir, reset output, khẳng định test run order. |
| Test kỳ vọng `UP_TO_DATE` nhưng nhận `SUCCESS` | Hidden inputs, output bị xóa, task thiếu @Input/@Output, plugin classpath đổi. | Kiểm tra task validation và inputs. |
| Test kỳ vọng `FROM_CACHE` nhưng nhận `SUCCESS` | Chưa cacheable, `--build-cache` thiếu, cache entry không ghi/không được chia sẻ. | Kiểm tra `@CacheableTask`, cache dir và `--info`. |
| Test kỳ vọng `FROM_CACHE` nhưng nhận `UP_TO_DATE` | Output vẫn còn, Gradle không cần restore. | Xóa output trước lần run thứ hai. |
| `compileJava` nhận `NO_SOURCE` | Fixture không có Java sources. | Bình thường nếu đang test no-source; thêm source nếu test compile behavior. |
| `SKIPPED` nhưng marker action không chạy | `onlyIf { false }` là skip có chủ đích. | Assert SKIPPED, không kỳ vọng stdout của action. |
| Version matrix fail trước khi apply plugin | Gradle distribution chưa được tải/cache, proxy/firewall hoặc JVM mismatch. | Provision distribution, kiểm tra JAVA_HOME/compatibility. |
| Test chạy được trên dev nhưng CI fail | Global cache/repo/network/env assumptions. | @TempDir, isolated TestKitDir, pinned versions, mirror/credentials hợp lệ. |
| Lỗi configuration cache | Task action capture Project, unmanaged external state hoặc untracked inputs. | Dùng Provider/Property, report và sửa task logic. |
| Fixture Kotlin DSL compile fail | Build-script classpath/accessors hoặc script syntax khác Groovy. | Tạo fixture kts riêng, kiểm tra plugin apply và generated accessors. |
| Task action chạy nhưng file không có | Sai output path, file đặt vào producer build dir, task không khai báo OutputFile. | Dựa vào fixture projectDir, assert full path và task metadata. |
| Parallel tests flaky do locks | Chia sẻ projectDir/TestKitDir/caches sai cách. | @TempDir per-test, cache directory riêng khi không chủ định chia sẻ. |

### 26.1. Những lệnh chẩn đoán hữu ích

```bash
# Bên producer plugin:
./gradlew --version
./gradlew classes
./gradlew test --stacktrace
./gradlew test --tests org.example.GreetingPluginFunctionalTest --info

# Xem từng test method nếu cần:
./gradlew test --tests '*GreetingPluginFunctionalTest.firstRunWritesExpectedOutput*'

# Thử Configuration Cache của producer (khác fixture tests):
./gradlew test --configuration-cache
```

`--info`/`--stacktrace` giúp tìm logs và dependency resolution; stdout toàn Gradle không có dạng cố định. Với TestKit distribution download issues, hãy kiểm tra network/caches trước khi kết luận plugin hỏng.

## 27. Các sai lầm trong thiết kế assertions

**Sai 1 — chỉ assert log:** `assertTrue(output.contains("SUCCESS"))` không biết đó là task outcome thật hay một chuỗi người dùng in ra.

**Sai 2 — assert `FROM_CACHE` khi output vẫn còn:** nhiệm vụ đó thường `UP_TO_DATE`, phải xóa output hoặc dùng second fixture có chung cache.

**Sai 3 — dùng `-x task` để tạo `SKIPPED`:** exclude task khỏi graph có thể khiến `BuildResult.task` là null.

**Sai 4 — gọi `build()` cho negative test:** test nhận exception thay vì cho phép inspect result; dùng `buildAndFail()`.

**Sai 5 — không dùng `assertNotNull` với BuildTask:** NPE che mất task path/graph problem.

**Sai 6 — không test file content:** TaskOutcome.SUCCESS có thể xảy ra dù plugin tạo sai nội dung.

**Sai 7 — dùng một thư mục fixture cho mọi test:** tests không độc lập, flaky khi chạy song song.

**Sai 8 — chỉ test producer Gradle version:** plugin có thể dùng API bị remove trong phiên bản người dùng dùng.

**Sai 9 — test Gradle cũ bằng JDK không được hỗ trợ:** lỗi JVM runtime không phải lỗi plugin contract.

**Sai 10 — giả định `withPluginClasspath()` là published plugin test:** injection không chứng minh marker/dependency metadata trên Maven/Plugin Portal đúng.

## 28. Checklist đưa vào pipeline phát triển plugin

### Thiết kế fixture

- [ ] Mỗi test có project directory tạm độc lập.
- [ ] Có Settings/build script phù hợp Groovy/Kotlin DSL của consumer.
- [ ] Plugin ID trong fixture khớp `gradlePlugin.plugins`.
- [ ] `withPluginClasspath` lấy đúng metadata từ producer plugin.
- [ ] Test không dùng home/repositories/credentials của developer một cách ngầm định.
- [ ] Outputs được assert ở **fixture path**, không phải producer's `build/`.

### Test behavior

- [ ] Có case `SUCCESS` và kiểm tra output files.
- [ ] Có case input đổi và test task chạy lại.
- [ ] Có case `UP_TO_DATE` khi input/output giữ nguyên.
- [ ] Có case `FROM_CACHE` nếu task tuyên bố cacheable.
- [ ] Có negative case `FAILED` với message có ích và `buildAndFail`.
- [ ] Khi plugin có Java integration, kiểm tra `NO_SOURCE` đúng semantics.
- [ ] Nếu có `onlyIf`/skip policy, kiểm tra `SKIPPED`.
- [ ] Test task full path và kiểm tra result.task không null.
- [ ] Dùng assertions từ `TaskOutcome`, không parse console thuần.

### Compatibility và CI

- [ ] Gradle version matrix phản ánh minimum/latest supported versions.
- [ ] JDK runtime hỗ trợ từng Gradle distribution trong matrix.
- [ ] Có cache/mirror/preprovision cho Gradle distributions để CI ổn định.
- [ ] Plugin source/bytecode target phù hợp minimum Gradle JVM.
- [ ] Configuration Cache test cho logic dùng Providers/task APIs.
- [ ] Build/TestKit suites không bị phụ thuộc vào PR chưa review hoặc secret không an toàn.
- [ ] Test reports và Gradle/JDK/fixture diagnostics được lưu khi fail.

## 29. Bảng quyết định nhanh

| Nhu cầu | Cách làm |
| --- | --- |
| Test một method Java độc lập | JUnit unit test; nếu thuần JDK có thể chạy bằng javac/java. |
| Test `Plugin.apply` cấu hình task | ProjectBuilder hoặc TestKit; TestKit kiểm tra full build. |
| Test plugin chạy từ `plugins {}` | `java-gradle-plugin` + `withPluginClasspath()` + fixture. |
| Fixture không sửa repository thật | JUnit `@TempDir Path`. |
| Chọn Gradle version | `withGradleVersion("8.14.3")`, `withGradleVersion("9.2.1")`. |
| Test version matrix | JUnit `@ParameterizedTest` + `@ValueSource`. |
| Test task lần đầu | `build()` và `TaskOutcome.SUCCESS`. |
| Test chạy lần hai | Cùng inputs/outputs -> `UP_TO_DATE`. |
| Test build cache | `@CacheableTask` + `--build-cache` + xóa output -> `FROM_CACHE`. |
| Test không có Java source | Apply java plugin, gọi `compileJava` -> `NO_SOURCE`. |
| Test onlyIf false | Có task trong graph -> `SKIPPED`. |
| Test input không hợp lệ | `buildAndFail()` -> `FAILED` và failure message. |
| Xem output thực | `BuildResult.getOutput()` và assert file bytes/text. |
| Tìm task outcome | `result.task(":writeGreeting").getOutcome()`, kiểm tra null. |
| Test multi-project fixture | `:app:writeGreeting` và `app/build/...`. |
| Giữ TestKit storage riêng | `withTestKitDir(...)`. |
| Kiểm tra Configuration Cache | `--configuration-cache` hai lần và compare behavior/report. |
| Test published binary/marker | Publish vào staging repo và resolve từ fixture, không chỉ injection. |

**Kết luận:** Kiểm thử Gradle plugin đáng tin phải chạy một **Gradle build thực sự trong fixture độc lập**, không chỉ gọi Java methods. `GradleRunner` và `TaskOutcome` giúp xác minh plugin application, task behavior, up-to-date/caching, no-source/skip/failure semantics và output files. `withGradleVersion` cung cấp cross-version matrix, nhưng phải kiểm soát Gradle/JDK compatibility, distributions, classpaths và TestKit environment. Nên giữ fixtures tối giản, assert dựa trên behavior, chạy minimum/latest Gradle support policy và đưa regression cases vào CI trước khi phát hành plugin.

### Tài liệu chính thức

- [Gradle — Testing Build Logic with TestKit](https://docs.gradle.org/current/userguide/test_kit.html): GradleRunner, plugin-under-test injection, versions, TestKitDir, build cache.
- [Gradle — Testing Plugins](https://docs.gradle.org/current/userguide/testing_gradle_plugins.html): functional tests, TestKit và phân biệt ProjectBuilder.
- [Gradle — Binary Plugin Testing](https://docs.gradle.org/current/userguide/testing_binary_plugin_advanced.html): fixtures, plugin author test patterns.
- [Gradle — GradleRunner API](https://docs.gradle.org/current/javadoc/org/gradle/testkit/runner/GradleRunner.html): withGradleVersion, withPluginClasspath, build, buildAndFail.
- [Gradle — TaskOutcome API](https://docs.gradle.org/current/javadoc/org/gradle/testkit/runner/TaskOutcome.html): SUCCESS, UP_TO_DATE, FROM_CACHE, NO_SOURCE, SKIPPED, FAILED.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): JDK/JVM/Gradle compatibility.
- [Gradle — Java Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): gradlePlugin block, TestKit metadata.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cacheable tasks, cache keys, troubleshooting.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): task inputs/outputs và UP_TO_DATE.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): config cache và task requirements.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): @TempDir, @ParameterizedTest, @ValueSource.
- [Gradle 8.14.3 release notes](https://docs.gradle.org/8.14.3/release-notes.html), [Gradle 9.2.1 release notes](https://docs.gradle.org/9.2.1/release-notes.html): phiên bản dùng trong ma trận ví dụ.
