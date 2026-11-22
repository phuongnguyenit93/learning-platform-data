# Kiểm thử logic đơn vị và build chức năng bằng Gradle TestKit

## 1. Vì sao Gradle plugin cần nhiều tầng kiểm thử?

Một Gradle plugin có thể chứa cả logic Java thuần, cấu hình Gradle Project, custom task type và các thao tác thực thi task. Chỉ kiểm tra một hàm Java bằng JUnit chưa đủ bảo đảm plugin thực sự hoạt động khi người dùng viết `plugins { id '...' }` trong `build.gradle`. Ngược lại, chỉ chạy một build chức năng (functional build) cho mọi trường hợp sẽ chậm, khó khoanh vùng lỗi và không thuận tiện để kiểm tra tất cả nhánh logic.

Bài thuộc **Build Tool Gradle → Phát triển plugin**, tập trung vào hai trụ cột:

- **Unit tests:** kiểm tra logic nhỏ bằng JUnit 5, không cần khởi động một Gradle build mới. Khi cần kiểm tra plugin configuration, có thể dùng `ProjectBuilder` để tạo Project nhẹ và xác minh tasks/extensions được đăng ký.
- **Functional tests:** dùng **Gradle TestKit** (API `GradleRunner`) tạo một project fixture, áp dụng plugin như người dùng thật, thực thi một hoặc nhiều Gradle tasks, rồi khẳng định output, task outcomes và kết quả thất bại/thành công.

Các tầng này bổ sung cho nhau, không thay thế nhau. Một task có thể được đăng ký chính xác trong ProjectBuilder nhưng lỗi tại `@TaskAction`, hoặc một task chạy tốt ở local nhưng thiếu annotation input/output làm hỏng caching. Vì vậy phải chọn loại test theo **điều cần chứng minh**.

**Sau bài này bạn sẽ làm được:**

1. Phân biệt unit, ProjectBuilder configuration, integration và functional tests.
2. Tạo một **binary Gradle plugin Java 17+** bằng `java-gradle-plugin`, với logic thuần, managed extension và custom task.
3. Viết unit tests JUnit Jupiter cho output, Unicode, invalid input.
4. Dùng ProjectBuilder kiểm tra plugin apply, extension default và task wiring mà không gọi task actions.
5. Dùng TestKit `GradleRunner` để chạy fixture thực, dùng `build()` cho thành công và `buildAndFail()` cho lỗi có chủ đích.
6. Hiểu `withPluginClasspath()`, `pluginUnderTestMetadata`, `TaskOutcome`, TestKit directories và version compatibility.
7. Tách functional tests thành task/source set riêng khi cần tốc độ CI và báo cáo độc lập.
8. Tránh các lỗi phổ biến với `Project` trong task actions, test cache, version matrix, stdout và plugin resolution.

Bài sử dụng **Groovy DSL** (`build.gradle`), **Java 17+**, **JUnit Jupiter 5.11.4**, và Gradle Wrapper tương thích. Những ví dụ gắn nhãn “mở rộng” hoặc “phương án thay thế” không được dán vào baseline nếu chưa làm đúng các bước chuyển đổi.

## 2. Chọn đúng tầng kiểm thử cho Gradle plugin

| Tầng | Đối tượng | Công cụ | Có chạy một Gradle build độc lập? | Có thực thi task actions? |
| --- | --- | --- | --- | --- |
| Unit logic thuần | Hàm format, parse, validate, mapping. | JUnit Jupiter/AssertJ/Mockito tùy nhu cầu. | **Không**. | Không. |
| Unit cấu hình Project | Plugin có apply được, extension/task convention có đúng? | `ProjectBuilder` + JUnit. | **Không**; tạo model Project trong quá trình test. | Thông thường **không**. |
| Integration logic | Nhiều classes, filesystem/service adapters, collaborators. | JUnit + test fixtures, fake services. | Không bắt buộc. | Có thể, nhưng không tự chứng minh plugin DSL hoạt động. |
| Functional build | Consumer áp plugin bằng `plugins { }`, task chạy, file/report/output. | **Gradle TestKit + GradleRunner**. | **Có**, qua Tooling API. | **Có** khi task được chọn. |
| Manual smoke | Dùng plugin trong một dự án mẫu thật. | Gradle Wrapper/Composite Build. | Có. | Có. |

**Quy tắc:** logic Java thuần nên được kiểm tra **nhanh và đầy đủ** bằng unit tests. Hành vi mà chỉ Gradle biết (plugin ID, managed extensions, task configuration, task outcomes, lifecycle, classpath, actual execution) cần **functional tests** hoặc kiểm tra bằng Gradle API phù hợp.

### 2.1. Vì sao ProjectBuilder không đủ?

`ProjectBuilder.builder().build()` tạo Project trong test JVM, giúp bạn apply plugin và inspect `Task`/`Extension` objects. Nhưng nó **không mô phỏng đầy đủ build lifecycle**, dependency resolution, project settings, execution order hay user-facing task outcomes như một build thực. Tài liệu Gradle nhấn mạnh `ProjectBuilder` phù hợp cấu hình; **GradleRunner** phù hợp functional behavior.

### 2.2. Vì sao TestKit không thay hết unit tests?

Một lần gọi `GradleRunner.build()` có thể cần startup Gradle, evaluate fixture, tạo classloaders và execute task graph. Một validator có 30 edge cases có thể được kiểm tra trong vài millisecond bằng JUnit mà không tạo 30 Gradle builds. Nếu lỗi phát sinh ở format/parse, unit tests cho thông báo trực tiếp hơn functional build logs.

**Thiết kế tốt:** rút nghiệp vụ dễ kiểm tra ra các **pure Java classes** rồi cho task gọi chúng. Functional tests xác nhận toàn bộ đường từ plugin ID → extension → task property → task action → stdout/file output.

## 3. Kiến trúc lab: một plugin, ba đối tượng kiểm thử

Plugin mẫu có ID **`example.greeting`**, cung cấp:

- `GreetingFormatter.format(String)`: logic Java thuần; trả về `Hello, Team!` và từ chối null/blank.
- `GreetingExtension`: Gradle managed extension với `Property<String> recipient`, giá trị mặc định `Gradle`.
- `GreetingTask`: custom task type có `@Input Property<String>` và `@TaskAction` in lời chào.
- `GreetingPlugin`: đăng ký extension `greeting` và task `greet`; nối convention của task với extension bằng Provider/Property API.

Luồng:

```text
Consumer build.gradle
    |
    +-- plugins { id 'example.greeting' }
    |     |
    |     +-- GreetingPlugin.apply(Project)
    |             |
    |             +-- extension "greeting"
    |             |       recipient = "Gradle" (default)
    |             |
    |             +-- task "greet" : GreetingTask
    |                     recipient.convention(extension.recipient)
    |
    +-- greeting { recipient.set('Team') }  [optional]
    |
    v
Gradle executes :greet
    |
    +-- @TaskAction
    +-- GreetingFormatter.format(recipient.get())
    +-- stdout "Hello, Team!"
```

**Hai đường kiểm tra khác nhau:**

1. Unit test gọi trực tiếp `GreetingFormatter.format`; ProjectBuilder inspect extension và task property.
2. TestKit tạo một `build.gradle` trong thư mục tạm, request `example.greeting`, gọi `greet` thật và assert output + `TaskOutcome`.

## 4. Chuẩn bị môi trường và cấu trúc project

Cần JDK **17+**; Gradle Wrapper được pin ở một bản Gradle hỗ trợ JVM đang dùng (Gradle 9.x cần Gradle Daemon chạy Java 17+). Ví dụ dùng Groovy DSL; JUnit Jupiter và JUnit Platform Launcher tải từ Maven Central lần đầu, nên cần network hoặc dependency cache hợp lệ.

Tạo cây thư mục:

```text
greeting-gradle-plugin/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/example/plugin/
    │   ├── GreetingFormatter.java
    │   ├── GreetingExtension.java
    │   ├── GreetingTask.java
    │   └── GreetingPlugin.java
    └── test/java/example/plugin/
        ├── GreetingFormatterTest.java
        ├── GreetingPluginConfigurationTest.java
        └── GreetingPluginFunctionalTest.java
```

Gradle Wrapper files phải tồn tại từ `gradle init` hoặc được tạo bằng `gradle wrapper` từ một Gradle đã cài phù hợp. File `build.gradle` một mình **không tự sinh ra** các script `gradlew`/`gradlew.bat`.

### 4.1. File settings.gradle

```groovy
rootProject.name = 'greeting-gradle-plugin'
```

### 4.2. File build.gradle hoàn chỉnh

```groovy
plugins {
    id 'java-gradle-plugin'
}

group = 'example.plugin'
version = '1.0.0'

repositories {
    mavenCentral()
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}

gradlePlugin {
    plugins {
        greeting {
            id = 'example.greeting'
            implementationClass =
                'example.plugin.GreetingPlugin'
        }
    }
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

**Giải thích:**

1. `java-gradle-plugin` là plugin chính thức hỗ trợ phát triển Gradle binary plugins, áp dụng Java library behavior, thêm Gradle API cho compile và tích hợp TestKit.
2. `gradlePlugin.plugins.greeting` đăng ký plugin ID `example.greeting` với Java implementation `example.plugin.GreetingPlugin`. Tên block `greeting` không phải plugin ID.
3. `options.release=17` yêu cầu compiler tạo bytecode và giới hạn Java APIs ở Java 17. Nó không tự cài JDK; cần JDK compiler thích hợp.
4. JUnit BOM `5.11.4` đồng bộ Jupiter và Platform versions, còn `junit-jupiter` cung cấp API/engine. Launcher dùng để Gradle chạy trên JUnit Platform ổn định.
5. `useJUnitPlatform()` cho task `test` nhận `@Test` của JUnit Jupiter.
6. `java-gradle-plugin` **tự thêm** `gradleTestKit()` vào test dependencies theo convention và tạo plugin-under-test metadata; lab không phải khai báo thêm `testImplementation gradleTestKit()` thủ công.
7. Khi build plugin, Gradle còn có `pluginDescriptors`, `pluginUnderTestMetadata`, `validatePlugins`. Chúng phục vụ plugin registration, TestKit classpath và validation, không phải tất cả đều là những JUnit test cases.

**Không dùng `id 'java'` thay `java-gradle-plugin` trong lab này:** Java plugin thông thường không tự đăng ký plugin descriptors hoặc tích hợp TestKit metadata cho plugin-under-test.

## 5. Mã production: logic thuần có thể unit test

### 5.1. File src/main/java/example/plugin/GreetingFormatter.java

```java
package example.plugin;

public final class GreetingFormatter {
    private GreetingFormatter() {
    }

    public static String format(String recipient) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                    "recipient must not be blank");
        }
        return "Hello, " + recipient + "!";
    }
}
```

**Vì sao tách class này?** Nó không import `Project`, `Task` hoặc TestKit. Hàm có input/output cụ thể, không đọc filesystem hay network, không phụ thuộc Gradle Daemon. Kiểm thử các nhánh null, blank, Unicode và happy path cực nhanh.

**Hành vi xác định:**

| Input | Hành vi |
| --- | --- |
| `"Gradle"` | Trả `"Hello, Gradle!"`. |
| `"Team"` | Trả `"Hello, Team!"`. |
| `"Việt Nam"` | Trả `"Hello, Việt Nam!"`. |
| `""`, `"   "`, `null` | Ném `IllegalArgumentException` với message `recipient must not be blank`. |

`String.isBlank()` là API Java 11+, hợp lệ với Java 17. Hàm cố ý **không trim** chuỗi nonblank: `format(" Team ")` giữ dấu cách; nếu yêu cầu nghiệp vụ cần trim, phải đổi đặc tả và unit tests tương ứng.

### 5.2. File src/main/java/example/plugin/GreetingExtension.java

```java
package example.plugin;

import org.gradle.api.provider.Property;

public abstract class GreetingExtension {
    public abstract Property<String> getRecipient();
}
```

Đây là **Gradle managed abstract type**; Gradle tạo implementation khi plugin gọi `extensions.create(...)`. Không cần tự `new GreetingExtension()` hoặc viết constructor thủ công. `Property<String>` biểu diễn cấu hình có thể lấy provider/convention lazily.

### 5.3. File src/main/java/example/plugin/GreetingTask.java

```java
package example.plugin;

import org.gradle.api.DefaultTask;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.TaskAction;
import org.gradle.work.DisableCachingByDefault;

@DisableCachingByDefault(
        because = "This task only prints to the console.")
public abstract class GreetingTask extends DefaultTask {

    @Input
    public abstract Property<String> getRecipient();

    @TaskAction
    public void printGreeting() {
        String text = GreetingFormatter.format(
                getRecipient().get());
        System.out.println(text);
    }
}
```

**Tại sao cấu hình như thế?**

- `@Input` đánh dấu `recipient` là input của task, giúp Gradle biết property nào ảnh hưởng đến behavior.
- `Property<String>` là managed task property, không phải mutable field tự định nghĩa mà Gradle không nhìn thấy.
- `@TaskAction` đánh dấu method được Gradle gọi khi task thực thi. Unit test một class thuần không chứng minh method này đã chạy.
- `GreetingFormatter.format` được gọi từ TaskAction; nếu blank, task thất bại như yêu cầu.
- `System.out.println` được dùng **chỉ trong ví dụ** để dễ kiểm tra exact stdout; trong plugin thật thường dùng `getLogger().lifecycle(...)` và thiết kế output artifacts/report đúng mục đích.
- Task **không tạo output file** nên không thể được tuyên bố là `@CacheableTask`. Annotation `@DisableCachingByDefault` diễn đạt rõ lý do không cache; không được viết test mong thấy `TaskOutcome.FROM_CACHE` cho task này.
- `printGreeting()` chỉ truy cập managed property và class thuần; không bắt/deref một live `Project` object trong task action. Đây là cách viết thân thiện hơn với Configuration Cache.

### 5.4. File src/main/java/example/plugin/GreetingPlugin.java

```java
package example.plugin;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class GreetingPlugin implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        GreetingExtension extension =
                project.getExtensions().create(
                        "greeting", GreetingExtension.class);

        extension.getRecipient().convention("Gradle");

        project.getTasks().register(
                "greet", GreetingTask.class, task -> {
                    task.setGroup("demo");
                    task.setDescription(
                            "Prints a configurable greeting.");
                    task.getRecipient().convention(
                            extension.getRecipient());
                });
    }
}
```

**Đọc luồng cấu hình:**

1. `GreetingPlugin implements Plugin<Project>`: dùng trong `build.gradle` của project.
2. `extensions.create("greeting",...)`: đăng ký extension để consumer viết `greeting { recipient.set('Team') }`.
3. `extension.getRecipient().convention("Gradle")`: đặt default, **không cưỡng chế override** mọi cấu hình của user.
4. `tasks.register("greet", GreetingTask.class,...)`: tạo task lazily, Gradle có thể không realize task nếu invocation không yêu cầu.
5. `task.getRecipient().convention(extension.getRecipient())`: nối task input với Provider/Property của extension. Khi consumer đổi `greeting.recipient`, task nhận giá trị mới mà không cần đọc extension trực tiếp trong TaskAction.
6. Không cần call `afterEvaluate` để đợi consumer đặt property; provider convention được resolve theo Gradle model.
7. Không áp Java plugin vào consumer, vì task chào không cần source set Java. Plugin development build cần `java-gradle-plugin`, nhưng plugin đang viết không nhất thiết phải tạo JavaCompile task cho mọi project áp dụng nó.

**Kết quả cấu hình:** một project apply `example.greeting` sẽ có task `:greet` và extension `greeting`. Đây chính là điều ProjectBuilder sẽ kiểm tra trước, rồi TestKit xác nhận thực thi thật.

## 6. Unit tests cho logic thuần bằng JUnit Jupiter

**File** `src/test/java/example/plugin/GreetingFormatterTest.java`:

```java
package example.plugin;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingFormatterTest {

    @Test
    void formatsNormalRecipient() {
        assertEquals(
                "Hello, Team!",
                GreetingFormatter.format("Team"));
    }

    @Test
    void supportsUnicode() {
        assertEquals(
                "Hello, Việt Nam!",
                GreetingFormatter.format("Việt Nam"));
    }

    @Test
    void rejectsEmpty() {
        IllegalArgumentException error =
                assertThrows(
                        IllegalArgumentException.class,
                        () -> GreetingFormatter.format(""));
        assertEquals(
                "recipient must not be blank",
                error.getMessage());
    }

    @Test
    void rejectsBlankAndNull() {
        assertThrows(
                IllegalArgumentException.class,
                () -> GreetingFormatter.format("   "));
        assertThrows(
                IllegalArgumentException.class,
                () -> GreetingFormatter.format(null));
    }
}
```

**Có 4 JUnit test methods**. Test thứ tư kiểm tra hai invalid inputs trong một method. Khi chạy, không có Java stdout vì test code không gọi `System.out.println` và không chạy task greet.

Linux/macOS:

```bash
./gradlew test --tests example.plugin.GreetingFormatterTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests example.plugin.GreetingFormatterTest
```

Với source và build script đúng, cả **4 tests PASS**. Không đoán output Gradle chính xác đến từng dòng: testLogging có thể liệt kê tên tests/trạng thái và Gradle có thể in task execution warnings.

**Bài học:** pure unit test phát hiện lỗi nghiệp vụ như chữ Unicode, error message, null handling. Nó **chưa kiểm tra** plugin ID `example.greeting`, extension wiring hay execution của `greet`.

### 6.1. Test discovery và JUnit Platform

Với JUnit Jupiter, dùng `@Test` của package `org.junit.jupiter.api`. Build script phải có API/engine ở test classpath và `useJUnitPlatform()` trong `Test` task. Nếu quên engine/launcher, có thể gặp lỗi “cannot create test task” hoặc không tìm test engine, tùy Gradle/JUnit version. Đừng sửa bằng cách chuyển `@Test` sang JUnit 4 một cách tùy tiện.

Trong CI, test XML reports mặc định thường ở `build/test-results/test/`, HTML ở `build/reports/tests/test/index.html`. Khi lọc bằng `--tests`, reports chỉ phản ánh **tập tests được chọn**, không đại diện toàn bộ 8 tests của lab.

## 7. Unit cấu hình plugin bằng ProjectBuilder

`ProjectBuilder` đến từ Gradle test fixtures API (`org.gradle.testfixtures.ProjectBuilder`) và có thể được dùng trong test JVM của plugin build. Nó tạo một Project để bạn:

- Apply plugin implementation trực tiếp.
- Kiểm tra extension có tồn tại, có default value.
- Kiểm tra task được đăng ký và thuộc đúng type.
- Đọc task properties/configuration thông qua API.

**File** `src/test/java/example/plugin/GreetingPluginConfigurationTest.java`:

```java
package example.plugin;

import org.gradle.api.Project;
import org.gradle.testfixtures.ProjectBuilder;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class GreetingPluginConfigurationTest {

    @Test
    void registersExtensionAndTaskWithDefaults() {
        Project project = ProjectBuilder.builder()
                .withName("test-project")
                .build();

        project.getPluginManager().apply(GreetingPlugin.class);

        GreetingExtension extension = project
                .getExtensions()
                .getByType(GreetingExtension.class);
        assertNotNull(extension);
        assertEquals(
                "Gradle",
                extension.getRecipient().get());

        GreetingTask task = (GreetingTask) project
                .getTasks()
                .getByName("greet");
        assertNotNull(task);
        assertEquals(
                "Gradle",
                task.getRecipient().get());
    }
}
```

**Có 1 unit test** ở lớp này. Nó dùng ProjectBuilder, không dùng GradleRunner.

**Giới hạn của assert này:**

- `ProjectBuilder` apply class `GreetingPlugin.class` **trực tiếp**; test không kiểm tra plugin descriptor hay request qua `plugins { id 'example.greeting' }`.
- `getTasks().getByName("greet")` có thể realize task để inspect; không phải execution của `@TaskAction`.
- Giá trị `recipient` được assert trước khi chạy Gradle task thật.
- Nó không bảo đảm plugin chạy đúng ở mọi Gradle version, không chứng minh input/output annotations đủ cho validation, không thử Gradle CLI arguments và task graph.

**Không cố gọi `task.getActions().get(0).execute(task)` như một cách giả lập Gradle execution.** Task action có lifecycle, state, file system services và task graph assumptions; cần TestKit để kiểm tra end-to-end.

### 7.1. Mockito/MockK có thay ProjectBuilder không?

Mocks hữu ích khi test một service/hàm phức tạp có collaborators rõ ràng. Nhưng mock toàn bộ `Project`, `TaskContainer`, `ExtensionContainer`, Providers và plugin manager dễ tạo một “Gradle giả” hành xử khác Gradle thật. Với cấu hình plugin, ProjectBuilder là lựa chọn tương đối nhẹ. Với behavior thực thi, TestKit là lựa chọn đáng tin cậy hơn.

**Mẹo tách code:** logic phức tạp đặt trong pure Java services với inputs/outputs rõ, unit test chúng mà không cần mock Project. Plugin chỉ nối Gradle model vào services qua managed properties.

## 8. Functional testing bằng Gradle TestKit

TestKit cung cấp `org.gradle.testkit.runner.GradleRunner`, API chạy một Gradle build **riêng** thông qua Tooling API. Nó không chỉ gọi task action trong cùng JVM như một unit test.

Các bước của một functional test:

1. Tạo thư mục fixture tạm.
2. Ghi `settings.gradle` và `build.gradle` của fixture.
3. Đặt plugin-under-test lên fixture plugin classpath.
4. Tạo runner với `withProjectDir(...)`, `withArguments(...)` và `withPluginClasspath()`.
5. Dùng `build()` nếu kỳ vọng thành công, hoặc `buildAndFail()` nếu kỳ vọng thất bại.
6. Assert `BuildResult.getOutput()`, `result.task(":greet").getOutcome()` và files tạo bởi task nếu có.

### 8.1. withPluginClasspath() hoạt động ra sao?

Plugin test project và GradleRunner fixture **không dùng chung classloader mặc định**. Nếu không setup classpath, fixture:

```groovy
plugins {
    id 'example.greeting'
}
```

có thể báo `Plugin [id: 'example.greeting'] was not found` vì plugin chưa publish.

`java-gradle-plugin` tích hợp TestKit qua:

- `gradleTestKit()` dependency trong test source set.
- `pluginUnderTestMetadata` task, tạo metadata liệt kê implementation classpath của plugin đang phát triển.
- `GradleRunner.withPluginClasspath()` đọc metadata đó và inject plugin classes/dependencies vào **build fixture** để `plugins { }` resolve được.

Tài liệu Gradle nhấn mạnh automatic injection này áp dụng khi fixture **request plugin bằng plugins DSL**. Nó không cần `publishToMavenLocal` hay sửa `~/.gradle/caches` bằng tay.

**Giới hạn:** nếu plugin implementation chỉ có `compileOnly` dependency tới API của một plugin bên ngoài, fixture có thể gặp `ClassNotFoundException` do thiếu classes ở runtime. Khi đó cần dependency/runtime strategy phù hợp, hoặc test fixture resolve plugin từ local Maven repository theo hướng dẫn Gradle; đừng nghĩ `withPluginClasspath()` tự đóng gói mọi loại compileOnly dependency.

### 8.2. File src/test/java/example/plugin/GreetingPluginFunctionalTest.java

```java
package example.plugin;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.gradle.testkit.runner.TaskOutcome;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GreetingPluginFunctionalTest {

    @TempDir
    Path projectDir;

    private void writeFixture(String extraConfiguration)
            throws IOException {
        Files.writeString(
                projectDir.resolve("settings.gradle"),
                "rootProject.name = 'greeting-fixture'\n");

        Files.writeString(
                projectDir.resolve("build.gradle"),
                "plugins { id 'example.greeting' }\n"
                        + extraConfiguration + "\n");
    }

    private GradleRunner runner() {
        return GradleRunner.create()
                .withProjectDir(projectDir.toFile())
                .withArguments(
                        "greet",
                        "--stacktrace",
                        "--console=plain")
                .withPluginClasspath();
    }

    @Test
    void defaultGreetingRunsSuccessfully()
            throws IOException {
        writeFixture("");

        BuildResult result = runner().build();

        assertTrue(result.getOutput()
                .contains("Hello, Gradle!"));
        assertNotNull(result.task(":greet"));
        assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":greet").getOutcome());
    }

    @Test
    void configuredRecipientIsUsed() throws IOException {
        writeFixture(
                "greeting { recipient.set('Team') }");

        BuildResult result = runner().build();

        assertTrue(result.getOutput()
                .contains("Hello, Team!"));
        assertNotNull(result.task(":greet"));
        assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":greet").getOutcome());
    }

    @Test
    void blankRecipientFailsTheBuild() throws IOException {
        writeFixture(
                "greeting { recipient.set('   ') }");

        BuildResult result = runner().buildAndFail();

        assertTrue(result.getOutput()
                .contains("recipient must not be blank"));
        assertNotNull(result.task(":greet"));
        assertEquals(
                TaskOutcome.FAILED,
                result.task(":greet").getOutcome());
    }
}
```

**Có 3 TestKit functional test methods.** Trong baseline tổng cộng:

- `GreetingFormatterTest`: 4 tests.
- `GreetingPluginConfigurationTest`: 1 ProjectBuilder test.
- `GreetingPluginFunctionalTest`: 3 TestKit functional tests.
- **Tổng: 8 JUnit tests**, trong đó **3 lần chạy Gradle fixture**.

**Tính độc lập:**

- Mỗi method của JUnit Jupiter dùng instance test class riêng theo lifecycle mặc định, và `@TempDir` tạo directory riêng cho fixture. Không dùng chung `build.gradle` mutable giữa các tests.
- `Files.writeString` (Java 11+) tạo file fixture thực. `\n` trong Java string là ký tự xuống dòng, **không phải hai ký tự backslash+n trong file cuối**.
- `withPluginClasspath()` là điều kiện để plugin local được request bằng `plugins { id 'example.greeting' }`.
- `withArguments("greet", ... )` chạy **task greet** của fixture, không chạy task `test` trong plugin project.
- `result.task(":greet")` tìm task theo **Gradle task path**; assertNotNull giúp phát hiện trường hợp plugin ID/apply hoặc task creation sai.
- `TaskOutcome.SUCCESS`/`FAILED` kiểm chứng Gradle đã thực thi task và có outcome tương ứng, mạnh hơn chỉ tìm một chuỗi log.
- Test invalid input dùng **`buildAndFail()`** để nói “build thất bại đúng như thiết kế”. Dùng `build()` ở đây sẽ ném exception test runner ngay cả khi behavior plugin là đúng.
- `--stacktrace` giúp stderr/log của failure có root cause, phù hợp khi assert message `recipient must not be blank`. Không nên dùng full stacktrace text làm golden snapshot vì phiên bản Gradle/JDK khác nhau sẽ khiến chi tiết thay đổi.

### 8.3. Chạy tất cả tests

Linux/macOS:

```bash
./gradlew clean test --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test --console=plain
```

Với Gradle/JDK/Maven Central tương thích, **8 tests PASS**. TestKit có thể tốn thời gian hơn unit tests do chạy các builds riêng; log Gradle có thể khác giữa lần chạy, nên không bịa một transcript console chính xác cho tất cả Gradle tasks.

Để chỉ chạy pure unit tests:

```bash
./gradlew test \
  --tests example.plugin.GreetingFormatterTest
```

Chỉ chạy ProjectBuilder test:

```bash
./gradlew test \
  --tests example.plugin.GreetingPluginConfigurationTest
```

Chỉ chạy TestKit functional tests:

```bash
./gradlew test \
  --tests example.plugin.GreetingPluginFunctionalTest
```

Đây là **name filters của Gradle Test task**, không tạo một task `functionalTest` riêng. Ở baseline cả ba classes nằm trong `src/test/java`, nên cùng thuộc task `test`.

### 8.4. Dùng TestKit để kiểm tra lỗi thay vì che giấu chúng

Nếu muốn chứng minh một plugin xử lý **build failure**, test nên:

1. Tạo fixture có input sai.
2. Gọi `buildAndFail()`.
3. Assert task `FAILED` và error message có thông tin hữu ích.
4. Không assert chính xác toàn bộ stacktrace hoặc path tạm.

Ngược lại, nếu test dự kiến thành công mà dùng `buildAndFail()`, nó sẽ fail vì runner nhận success không phù hợp kỳ vọng. Chọn đúng method là một phần của test specification.

**Lưu ý:** `buildAndFail()` báo “build thất bại đúng kỳ vọng”, **chưa chắc** thất bại **đúng nguyên nhân**. Vì vậy luôn assert message, task path hoặc file state liên quan, không chỉ gọi runner.

## 9. Kiểm tra plugin thật từ một consumer build tối giản

Để thử thủ công ngoài TestKit, trước tiên publish plugin tới Maven Local hoặc ghép plugin development build bằng **Composite Build**. Không cần làm bước này cho TestKit vì `withPluginClasspath()` đã cung cấp plugin vào fixture.

Ví dụ khi plugin project ở directory `greeting-gradle-plugin/` và consumer là directory sibling `demo-consumer/`, file `demo-consumer/settings.gradle`:

```groovy
pluginManagement {
    includeBuild('../greeting-gradle-plugin')
}

rootProject.name = 'demo-consumer'
```

File `demo-consumer/build.gradle`:

```groovy
plugins {
    id 'example.greeting'
}

greeting {
    recipient.set('Team')
}
```

Dùng Wrapper của consumer đã có:

```bash
./gradlew greet --console=plain
```

Output của task:

```text
Hello, Team!
```

**Khác nhau:** consumer dùng `pluginManagement.includeBuild` để resolve plugin source thật; TestKit test chỉ cần `withPluginClasspath()` từ plugin-under-test metadata. Đừng đòi fixture TestKit copy entire plugin project vào thư mục `@TempDir` nếu test dựa trên automatic injection.

Đây là một **consumer smoke test thủ công**, khác 3 TestKit test methods. Nó có ích để phát hiện vấn đề bố cục/publishing/composite resolution mà TestKit injected classpath không nhất thiết tái hiện.

## 10. GradleRunner API cần nắm chắc

### 10.1. Các hàm quan trọng

| API | Ý nghĩa |
| --- | --- |
| `GradleRunner.create()` | Tạo test runner. |
| `withProjectDir(File)` | Chỉ định fixture project directory; cần chứa build script hợp lệ. |
| `withArguments(String...)` | Chỉ định task names và Gradle CLI flags cho fixture. |
| `withPluginClasspath()` | Dùng plugin-under-test classpath metadata từ `java-gradle-plugin`. |
| `build()` | Kỳ vọng build thành công; ném exception nếu build fail. |
| `buildAndFail()` | Kỳ vọng build thất bại; ném exception nếu build success. |
| `withGradleVersion("9.0")` | Chọn một Gradle distribution cụ thể khi test cross-version. |
| `withTestKitDir(File)` | Chỉ định TestKit directory dành cho runner. |
| `withDebug(true)` | Cho phép debug build logic khi cần; có tác động đến execution environment. |
| `forwardOutput()` | Chuyển build output tới test process console, hữu ích khi debug. |

Không nhầm `withArguments` của runner với args của Java application: chúng là **Gradle command-line arguments**, ví dụ `greet`, `--stacktrace`, `--offline`, `--configuration-cache`.

### 10.2. BuildResult và TaskOutcome

`BuildResult` cho phép:

- `getOutput()`: lấy log/output mà runner bắt được.
- `task(":greet")`: lấy `BuildTask` theo task path, có thể trả `null` nếu task không nằm trong kết quả.
- `task(":greet").getOutcome()`: lấy `TaskOutcome`.

Các outcomes thường cần biết:

| Outcome | Diễn giải |
| --- | --- |
| `SUCCESS` | Task đã chạy thành công. |
| `FAILED` | Task đã chạy và thất bại. |
| `UP_TO_DATE` | Task có inputs/outputs không đổi nên được bỏ qua execution theo up-to-date checks. |
| `FROM_CACHE` | Outputs được khôi phục từ Gradle build cache. |
| `SKIPPED` | Task bị skip vì điều kiện/disabled/skip reason. |
| `NO_SOURCE` | Task kiểu source processing/compilation không có nguồn cần xử lý. |

**Không assert mọi task bắt buộc SUCCESS nếu mô hình có cache/up-to-date behavior.** Với một `@CacheableTask` có file output thật, lần chạy thứ hai có thể là `UP_TO_DATE` hoặc `FROM_CACHE`. Bài lab dùng task in console **không có output file**, nên mỗi TestKit fixture được tạo mới và task thực thi với SUCCESS/FAILED như code đã kiểm tra.

### 10.3. Những gì không nên assert bằng chuỗi output

Ví dụ brittle:

```java
// PHẢN VÍ DỤ: không nên chụp chính xác mọi dòng Gradle log.
assertEquals("BUILD SUCCESSFUL in 1s\n", result.getOutput());
```

Vì stdout bao gồm Gradle task information, warnings, daemon noise, durations và plugin logs tùy Gradle/JDK. Thay vào đó:

```java
assertTrue(result.getOutput().contains("Hello, Team!"));
assertEquals(
        TaskOutcome.SUCCESS,
        result.task(":greet").getOutcome());
```

Đây là **fragment trong test có `result` đã được tạo**, không phải Java class độc lập. Với file output, assert file contents/hash còn mạnh hơn console output.

### 10.4. stdout và logger trong Gradle task

Lab dùng `System.out.println` để TestKit capture nhất quán một marker. Trong plugin production, nên dùng Gradle logger:

```java
getLogger().lifecycle(
        GreetingFormatter.format(getRecipient().get()));
```

Đây là **phần thay thế body in** trong `GreetingTask`, không phải một hàm độc lập. Với `lifecycle` log, Gradle `--quiet` có thể suppress message; test lúc đó cần chọn log level phù hợp và không mặc định thấy text. Khi test outcome/output, hãy hiểu chính xác loại log mà plugin sinh ra.

## 11. Unit test, ProjectBuilder hay TestKit: chọn theo câu hỏi

### 11.1. “Hàm chuẩn hóa tên input có đúng không?”

Dùng unit test thuần, kiểm tra null, empty, blank, Unicode, maximum size, normalization và exception message. Không cần GradleRunner.

### 11.2. “Plugin apply xong có task greet và default Gradle không?”

Dùng ProjectBuilder, inspect extensions/tasks theo API. Nhưng không giả định task action đã chạy.

### 11.3. “Plugin ID request trong plugins {} có hoạt động không?”

Dùng TestKit với fixture `plugins { id 'example.greeting' }` và `withPluginClasspath()`. ProjectBuilder apply class trực tiếp nên không kiểm tra plugin descriptor mapping.

### 11.4. “Task dùng extension input thật và in đúng output?”

Dùng TestKit `build()` với `greeting { recipient.set('Team') }`, assert message và `TaskOutcome.SUCCESS`.

### 11.5. “Nhập blank phải làm build thất bại với lỗi rõ?”

Dùng TestKit `buildAndFail()`; assert task FAILED và error message.

### 11.6. “Build cache và incremental build có đúng không?”

Phải dùng một custom task **thật sự có output files**, annotations `@Input`/`@OutputFile` hoặc `@OutputDirectory`, và `@CacheableTask` khi contract phù hợp. Chạy fixture nhiều lần với `--build-cache`, thay đổi inputs, kiểm tra file contents và TaskOutcome; task chỉ in stdout của lab **không** đại diện cho cacheable task.

### 11.7. “Plugin chạy trên Gradle version khác được không?”

Dùng `withGradleVersion` trong TestKit, matrix supported Gradle/JDK combinations; lưu ý một số behavior/API có thể khác version. Không chỉ giả định CI dùng Java 17 là mọi Gradle version cũ đều chạy được.

## 12. Tách functional tests thành source set/task riêng

Trong baseline, cả 8 tests nằm trong `src/test/java` và chạy chung `test`. Đối với plugin lớn, có thể muốn:

- `test` chỉ chạy unit/ProjectBuilder tests, nhanh trên mọi commit.
- `functionalTest` chạy TestKit builds, tốn thời gian hơn và có reports riêng.
- `check` phụ thuộc cả hai để CI quality gate vẫn đầy đủ.

Đây là **phương án mở rộng**. Nếu áp dụng, phải **di chuyển** `GreetingPluginFunctionalTest.java` từ `src/test/java/example/plugin` sang `src/functionalTest/java/example/plugin`, tránh tồn tại cả hai copies.

### 12.1. Cấu hình thêm trong plugin build

Sau các blocks baseline `plugins`, `repositories`, `dependencies`, **bổ sung** vào cuối `build.gradle`:

```groovy
def functionalTest = sourceSets.create('functionalTest')

configurations.named('functionalTestImplementation') {
    extendsFrom configurations.testImplementation
}
configurations.named('functionalTestRuntimeOnly') {
    extendsFrom configurations.testRuntimeOnly
}

gradlePlugin {
    testSourceSets functionalTest
}

tasks.register('functionalTest', Test) {
    group = 'verification'
    description = 'Runs Gradle TestKit functional tests.'
    testClassesDirs = functionalTest.output.classesDirs
    classpath = functionalTest.runtimeClasspath
    useJUnitPlatform()
    shouldRunAfter tasks.named('test')
}

tasks.named('check') {
    dependsOn tasks.named('functionalTest')
}
```

Giải thích:

1. `sourceSets.create('functionalTest')` tạo source roots `src/functionalTest/java`, `src/functionalTest/resources` và configurations liên quan.
2. `functionalTestImplementation.extendsFrom(testImplementation)` cho source set mới dùng JUnit/TestKit dependencies đã khai báo; `functionalTestRuntimeOnly` kế thừa launcher runtime.
3. `gradlePlugin.testSourceSets functionalTest` yêu cầu plugin development plugin chuẩn bị **plugin-under-test metadata** cho source set này, giúp `withPluginClasspath()` hoạt động khi functional tests không nằm ở `test` source set.
4. `testClassesDirs` và `classpath` được gán **đúng functionalTest source set**. Không dùng test source set classesDirs cũ.
5. `shouldRunAfter test` chỉ ràng buộc thứ tự **nếu cả hai tasks cùng trong graph**; không tự thêm unit test vào dependency của functionalTest.
6. `check.dependsOn functionalTest` làm CI lifecycle chạy functional tests, ngoài unit `test` vốn đã được Java plugin nối vào check.
7. `gradlePlugin.testSourceSets` không tự tạo task `functionalTest` từ source set. Bạn phải đăng ký Test task hoặc dùng JVM Test Suite DSL tương thích.

**Chú ý về configuration inheritance:** đoạn dùng `extendsFrom` để tái sử dụng JUnit/TestKit dependencies cho lab; trong production cần quản lý dependency buckets rõ để tránh vô tình chuyển những test-only libraries không cần thiết vào functionalTest runtime. Alternative là khai báo `functionalTestImplementation`/`functionalTestRuntimeOnly` trực tiếp và giữ graph tối thiểu.

### 12.2. Lệnh chạy sau khi tách

```bash
./gradlew clean test functionalTest --console=plain
./gradlew check --console=plain
./gradlew functionalTest \
  --tests example.plugin.GreetingPluginFunctionalTest
```

**Kết quả kỳ vọng:**

| Task | Tests của lab |
| --- | --- |
| `test` | 4 Formatter + 1 ProjectBuilder = **5** |
| `functionalTest` | 3 TestKit tests = **3** |
| `check` | Bao gồm cả hai tasks theo cấu hình. |

Reports khi có task riêng:

```text
build/reports/tests/test/index.html
build/test-results/test/
build/reports/tests/functionalTest/index.html
build/test-results/functionalTest/
```

Khi chạy một lần các tasks rồi chạy lại không thay inputs, Gradle có thể báo `UP-TO-DATE`. Không dùng sự vắng mặt của log `passed` ở lần hai để khẳng định tests đã biến mất.

### 12.3. JVM Test Suite plugin như lựa chọn tổ chức khác

Các Gradle versions hiện đại hỗ trợ JVM Test Suite DSL `testing { suites { ... } }`, giúp định nghĩa source sets/test targets và dependencies ở mức suite. Với plugin development project, cần đảm bảo `gradlePlugin.testSourceSets` hoặc metadata setup tương ứng cho **functional** suite.

Đừng mặc định việc chỉ thêm một suite tên `functionalTest` sẽ tự làm `withPluginClasspath()` nhận plugin classes. Quan trọng nhất vẫn là **plugin-under-test classpath metadata** và đúng source set nơi tests chạy.

## 13. GradleRunner chạy trong môi trường nào?

### 13.1. Fixture được cách ly, nhưng không phải một máy ảo mới

GradleRunner tạo/build trong một **fixture project directory** và có TestKit Gradle user-home/test directories tách biệt. Nó chạy qua Tooling API, thường khởi tạo Gradle Daemon dành cho tests. Không mặc định kế thừa toàn bộ `~/.gradle/gradle.properties`, local init scripts hay credentials của developer.

Tuy nhiên fixture vẫn có thể chịu ảnh hưởng từ **JDK, OS, filesystem, environment variables và toolchain installation**. Đừng kết luận “isolation” là 100% sandbox bảo mật hoặc network isolation.

### 13.2. Quản lý filesystem và thư mục tạm

JUnit `@TempDir` giúp mỗi test có fixture riêng. Nếu test tạo file output, assert path **tương đối từ `projectDir`** và dùng Java NIO:

```java
Path output = projectDir.resolve("build/generated/message.txt");
assertTrue(Files.exists(output));
```

Đây là **fragment** cho một task có file output; task `greet` của lab chỉ in stdout nên không có `build/generated/message.txt`. Không thêm assertion này vào baseline mà không tạo output thật.

TestKit có `withTestKitDir(File)` khi cần kiểm soát nơi giữ runner data, hữu ích trong CI. Không xóa Gradle User Home toàn cục giữa các tests; dùng temp directories và resource cleanup phù hợp.

### 13.3. Chạy song song và sử dụng Gradle Daemons

Nhiều functional tests có thể sinh nhiều Gradle invocations/daemons; chúng đắt hơn pure unit tests. Nếu CI bị quá tải RAM/CPU hoặc lẫn logs:

- Tách TestKit suite/worker count phù hợp.
- Giảm số fixtures không cần thiết, gộp assertions trong một build khi hợp lý.
- Đảm bảo tests không dùng chung mutable directory.
- Không thiết kế test phụ thuộc thứ tự execution của các test methods.
- Có thể chạy functional tests ở CI stage khác nhưng vẫn được `check` hoặc release gate yêu cầu.

### 13.4. Khi debug breakpoint không chạy như mong đợi

Code plugin trong fixture có thể chạy ở **Gradle process khác** với JUnit test JVM. Vì vậy breakpoint đặt trong `GreetingTask.printGreeting()` không nhất thiết dừng khi bạn chỉ debug JUnit process.

TestKit hỗ trợ:

```java
GradleRunner.create()
        .withProjectDir(projectDir.toFile())
        .withPluginClasspath()
        .withArguments("greet")
        .withDebug(true);
```

Đây là **fragment cấu hình runner** cho debug, không phải một test hoàn chỉnh. Sử dụng `withDebug(true)` khi cần và hiểu tác động đến execution mode; không mặc định bật trong mọi CI build. Với lỗi chức năng đơn giản, `--stacktrace`, `--info` và fixture output thường đủ.

## 14. Kiểm thử plugin với nhiều Gradle/JDK versions

Plugin có thể hoạt động với Gradle version xây nó nhưng lỗi khi consumer dùng phiên bản cũ/mới hơn. TestKit cho phép chọn version cụ thể:

```java
GradleRunner.create()
        .withProjectDir(projectDir.toFile())
        .withPluginClasspath()
        .withGradleVersion("9.0")
        .withArguments("greet")
        .build();
```

Đây là **fragment** giả định fixture đã tạo như mục 8.2. `9.0` là một Gradle release thực; trong CI nên test versions nằm trong **support matrix** mà bạn công bố, không tự giả định “cứ số lớn nhất là tốt”.

Các lưu ý:

1. TestKit có thể cần tải Gradle distribution được chỉ định nếu chưa có trong cache.
2. JVM chạy fixture phải tương thích Gradle distribution đó.
3. Plugin Java classes cần bytecode target tương thích JVM Gradle chạy, không chỉ JVM ứng dụng mà plugin cấu hình.
4. API Gradle thay đổi qua versions; plugin dựa vào internal Gradle API có rủi ro cao.
5. Một thay đổi làm build thành công trên Gradle mới nhưng không tương thích Gradle cũ cần test trực tiếp thay vì chỉ unit test Java.
6. Nếu consumer dùng Kotlin DSL, ngoài fixture Groovy DSL nên có ít nhất một Kotlin DSL fixture `build.gradle.kts` khi plugin public API/extension DSL hướng tới cả hai.
7. Khi cần test khác OS/JDK vendor, TestKit alone không giả lập Windows/Linux hay đổi Java installation tùy ý; CI matrix phải thật sự chạy trên môi trường đó.

**Không dùng literal `"9.x"` làm tham số `withGradleVersion`**: đó không phải version hợp lệ. Chọn exact release, ví dụ `"9.0"`, và kiểm tra support matrix.

## 15. Testing configuration cache, build cache và incremental tasks

### 15.1. Configuration Cache

Task code có thể compile/run được nhưng vẫn vi phạm Configuration Cache nếu giữ tham chiếu trực tiếp `Project` hoặc các live Gradle model objects vào execution phase.

Lab cố tình viết:

```java
@TaskAction
public void printGreeting() {
    String text = GreetingFormatter.format(
            getRecipient().get());
    System.out.println(text);
}
```

Đây là fragment của `GreetingTask`: task action đọc `Property<String>` do Gradle quản lý, không gọi `getProject()` hay truy vấn extensions at execution.

Một functional test có thể mở rộng runner arguments:

```java
BuildResult result = GradleRunner.create()
        .withProjectDir(projectDir.toFile())
        .withPluginClasspath()
        .withArguments(
                "greet",
                "--configuration-cache",
                "--stacktrace")
        .build();
```

Đây là **fragment**; `projectDir`/fixture đã có. Nó xác minh một lần chạy không lỗi, nhưng muốn test cache reuse cần **chạy lại** trên cùng fixture và kiểm tra output/report phù hợp. Đừng coi chỉ thấy `BUILD SUCCESSFUL` là bằng chứng toàn plugin tương thích configuration cache trong mọi tasks.

### 15.2. Build Cache

Build cache phù hợp khi task có outputs xác định, input/output annotations rõ và không có side effects ngoài khai báo. TestKit có thể truyền `--build-cache`, kiểm tra file đã tạo và `TaskOutcome.FROM_CACHE`.

**Không viết test mong FROM_CACHE với `GreetingTask`**: nó chỉ in console, không có output files, còn được chú thích `@DisableCachingByDefault`. Muốn minh họa FROM_CACHE một cách đúng, trước tiên phải thiết kế một task thực sự cacheable, khai báo `@Input`, `@OutputFile` và `@CacheableTask`, rồi chạy các builds với cache còn giữ, outputs được xóa hợp lệ và inputs không đổi.

### 15.3. Incremental tests

`TaskOutcome.UP_TO_DATE` nghĩa là Gradle có bằng chứng task inputs/outputs không đổi; nó **không** nghĩa plugin code chưa được test, và cũng không tự chứng minh caching đúng. Functional test muốn kiểm tra task re-execution khi input đổi phải tạo fixture outputs và kiểm tra task rerun khi sửa input.

**Nhớ:** `Configuration Cache` lưu mô hình cấu hình task graph, còn `Build Cache` lưu outputs của tasks. Hai cơ chế khác nhau, cần test riêng.

## 16. Negative tests, edge cases và test matrix

Một plugin production nên có ma trận ít nhất:

| Case | Unit test | Functional TestKit |
| --- | --- | --- |
| Default value hợp lệ. | Format “Gradle”. | Apply plugin, `greet` thành công. |
| User override extension. | Format “Team”. | `greeting { recipient.set('Team') }` và stdout. |
| Unicode. | Format “Việt Nam”. | Thêm fixture Unicode khi parsing/logging là yêu cầu thật. |
| Empty/blank/null. | Kiểm tra exception/message. | Blank property làm task fail đúng nguyên nhân. |
| Plugin ID sai. | Không có ý nghĩa trong pure unit. | Fixture resolution báo plugin not found. |
| Plugin applied twice. | Có thể kiểm tra ProjectBuilder. | Fixture yêu cầu plugin bằng hai paths, xác minh idempotence. |
| Java/Gradle compatibility. | Java-only test không đủ. | Cross-version runner/CI matrix. |
| Task input/output annotations. | Inspect metadata/API. | `validatePlugins` + TaskKit/GradleRunner. |
| Caching behavior. | Logic determinism. | Task có outputs, `--build-cache` và outcome. |
| Missing external plugin API. | Mocks có thể che thiếu classpath. | Fixture có dependency resolution thực hoặc local repo. |
| Plugin publication. | Không. | Một consumer fixture resolve từ Maven local/testing repo như published artifact. |

**Test levels theo mục tiêu:** không bắt mọi branch của validator tạo GradleRunner; cũng không để một smoke build PASS thay thế tất cả unit tests.

### 16.1. Kiểm thử lỗi thiếu plugin ID

Nếu `gradlePlugin.plugins.greeting.id` bị đổi thành `example.hello` nhưng fixture vẫn viết `example.greeting`, TestKit sẽ không resolve plugin ID cũ.

Sự cố cần kiểm tra ở:

- `gradlePlugin { plugins { ... id ... implementationClass ... } }`.
- `pluginDescriptors` output.
- `withPluginClasspath()` và fixture `plugins { }`.
- Không sửa Java `GreetingFormatter` chỉ vì lỗi plugin discovery.

### 16.2. Kiểm thử lỗi task configuration

Nếu bạn xóa `GreetingPlugin.getTasks().register("greet",...)`, ProjectBuilder test fail khi `getByName("greet")` không tìm thấy task; TestKit fixture fail vì task `greet` không tồn tại. Hai tests bắt được lỗi ở mức khác nhau; một cái nhanh hơn, cái kia sát người dùng hơn.

### 16.3. Kiểm thử nhầm build fail nguyên nhân khác

Với negative test, `buildAndFail()` **chỉ** kiểm tra build thực sự fail. Nếu fixture thiếu JDK, plugin không resolve, hoặc repository bị chặn thì build cũng fail. Do đó phải kết hợp:

```java
assertTrue(result.getOutput()
        .contains("recipient must not be blank"));
assertEquals(TaskOutcome.FAILED,
        result.task(":greet").getOutcome());
```

Đây là **fragment sau khi có `BuildResult result`**. Trong code đầy đủ mục 8.2 có `assertNotNull(result.task(":greet"))` trước khi dereference.

## 17. Troubleshooting: tại sao unit tests PASS nhưng TestKit FAIL?

| Triệu chứng | Nguyên nhân có thể | Cách điều tra |
| --- | --- | --- |
| `Plugin [id: 'example.greeting'] was not found` | Plugin ID mismatch, quên `withPluginClasspath()` hoặc thiếu metadata. | Kiểm tra Gradle plugin declaration, `pluginUnderTestMetadata`, fixture plugins block. |
| `InvalidPluginMetadataException` | Không tìm thấy/đọc được `plugin-under-test-metadata.properties` cho TestKit. | Dùng `java-gradle-plugin`, test source set đúng, `gradlePlugin.testSourceSets` nếu đã tách. |
| `NoClassDefFoundError` / `ClassNotFoundException` | Missing plugin runtime dependency, `compileOnly` API hoặc classpath injection thiếu. | Phân biệt compile vs runtime graph, cân nhắc fixture publish local repo cho external plugins. |
| `ProjectBuilder` PASS nhưng `greet` fail | ProjectBuilder chỉ inspect configuration, không execute task action. | TestKit `build()`, đọc stacktrace/task outcome. |
| `@TaskAction` không được gọi | Task không được chọn, bị skip hoặc plugin đăng ký task khác. | `withArguments("greet")`, `result.task(":greet")`, `--info`. |
| `No tests found` | Sai JUnit API/engine, source set path, filter hoặc thiếu `useJUnitPlatform()`. | Xem `src/test/java`, JUnit deps, testCompileClasspath/testRuntimeClasspath. |
| `TaskOutcome.UP_TO_DATE` thay vì SUCCESS | Fixture/task outputs được tái sử dụng, không execute action. | Xem Gradle up-to-date model, tạo fixture riêng hoặc chọn đúng outcome expectation. |
| `TaskOutcome.FROM_CACHE` không xuất hiện | Task không cacheable, thiếu outputs hoặc cache disabled. | Xem `@CacheableTask`, `@OutputFile`, `--build-cache`. |
| Lệnh `build()` ném exception khi test failure dự kiến | Test gọi runner method sai kỳ vọng. | Dùng `buildAndFail()` và assert nguyên nhân. |
| Negative test PASS vì sai nguyên nhân | Build failure từ syntax/dependency resolution chứ không từ validator. | Assert message và `TaskOutcome.FAILED` của task đích. |
| TestKit output có warning/time khác | Gradle/JDK/daemon/config khác, log không ổn định. | Assert marker/file content và outcomes, không snapshot nguyên stdout. |
| TestKit fixture không dùng Maven Central của plugin project | Build fixture là project riêng. | Tự thêm repositories vào fixture khi fixture cần resolve dependencies. |
| ProjectBuilder unit test dùng `getByName` fail | Task chưa được đăng ký, plugin chưa apply hoặc sai tên task. | Apply plugin class đúng, kiểm tra `tasks.named` và plugin implementation. |
| `validatePlugins` báo task property lỗi | Thiếu @Input/@Output, sai task property type, nội bộ task không khai báo đúng. | Sửa typed task annotations/properties, không tắt validation hàng loạt. |
| Build fail `UnsupportedClassVersionError` | JDK Gradle Daemon quá cũ cho plugin bytecode. | Xem `./gradlew --version`, Java release/toolchain, supported Gradle JVM. |
| Java 17 `isBlank()` không compile | Compiler/API target thấp hơn Java 11 hoặc source code sai. | Dùng JDK 17+ compiler, `options.release=17`. |
| GradleRunner fixture script parse fail | Java string tạo ra Groovy DSL sai quote/newline. | Đọc file trong `@TempDir` hoặc log fixture, kiểm tra `\n`. |
| TestKit tests chậm/hang | Network resolution, nhiều daemons, fixture có task dài hoặc deadlock. | Isolate project, giảm parallelism, dùng --info, pin deps, timeouts hợp lý. |
| TestKit debug không dừng ở TaskAction | Build chạy process khác với test JVM. | Dùng `withDebug(true)` khi phù hợp hoặc runner logs. |
| `functionalTest` không tồn tại | Chỉ tạo source set mà chưa register Test task. | Cấu hình `tasks.register('functionalTest', Test)` và classpath đúng. |
| `withPluginClasspath()` fail sau khi tách source set | Metadata vẫn trỏ `test` hoặc không được tạo cho functionalTest. | `gradlePlugin { testSourceSets functionalTest }`, kiểm tra dependencies. |
| JUnit test ở `src/functionalTest/java` không xuất hiện dưới `test` | Đã tách source sets theo thiết kế. | Chạy `functionalTest`, kiểm tra reports riêng. |
| CI offline fail | Gradle Wrapper/JUnit/plugin dependencies chưa cache. | Preseed dependencies, cho build fetch qua repository được duyệt; `--offline` không tự tạo JAR. |
| IDE chạy tests khác CLI | Gradle distribution, TestKit metadata, Java runner khác. | Chạy `./gradlew assemble test` từ Wrapper; kiểm tra IDE Gradle settings. |

### 17.1. Quy trình chẩn đoán bảy bước

1. **Kiểm tra JDK/Gradle:** `./gradlew --version`, Java compiler và wrapper distribution đã pin chưa?
2. **Kiểm tra plugin registration:** `gradlePlugin.plugins.greeting.id` và `implementationClass` đúng Java package/class chưa?
3. **Kiểm tra source/test frameworks:** JUnit Jupiter API, engine, Launcher và `useJUnitPlatform()`.
4. **Chạy pure unit tests trước:** nếu formatter sai, sửa pure Java logic; đừng debug GradleRunner khi chưa cần.
5. **Chạy ProjectBuilder test:** xác nhận task/extension được đăng ký và wired đúng.
6. **Chạy TestKit với `--stacktrace`:** xem fixture được ghi ra, plugin ID, BuildResult output và task outcome.
7. **Chạy `validatePlugins` / test cache/version matrix** khi vấn đề liên quan task metadata/Gradle compatibility.

Các lệnh kiểm tra:

```bash
./gradlew --version
./gradlew clean test --console=plain
./gradlew test --tests example.plugin.GreetingFormatterTest
./gradlew test --tests example.plugin.GreetingPluginConfigurationTest
./gradlew test --tests example.plugin.GreetingPluginFunctionalTest
./gradlew validatePlugins --console=plain
./gradlew -q dependencies --configuration testRuntimeClasspath
```

Nếu build bị fail từ dependency resolution, đọc chính xác lỗi repository/version; không sửa `GreetingTask` một cách ngẫu nhiên.

## 18. Chất lượng test và CI cho plugin project

Một plugin là **build logic được thực thi trong môi trường build**, thường trước khi application code của consumer chạy. Vì vậy quality gates nên mạnh hơn chỉ “jar compile được”.

**Đề xuất pipeline:**

1. Pin Gradle Wrapper và Java toolchain/Gradle JVM requirements.
2. Chạy `compileJava` cho plugin, plugin descriptors/metadata generation.
3. Chạy **unit tests** của pure Java logic và ProjectBuilder.
4. Chạy **TestKit functional tests** cho success, configuration override, validation failure.
5. Chạy **validatePlugins** để bắt task input/output/annotation issues.
6. Khi relevant, chạy Configuration Cache functional tests và cacheable-task tests.
7. Test support matrix cho Gradle/JDK versions đã cam kết.
8. Có ít nhất một consumer smoke project/composite test; nếu publish plugin, thử **published marker resolution** ở fixture.
9. Lưu JUnit XML/HTML reports, Gradle logs và fixture diagnostics khi fail.
10. Chỉ release/publish artifact sau khi tất cả gates cần thiết PASS.

Với baseline lab, có thể chạy một lệnh:

```bash
./gradlew clean check --console=plain
```

Vì Java plugin mặc định gắn `test` vào `check`, nó sẽ chạy **8 JUnit tests** (trừ khi bạn đã dùng phương án tách source set). Plugin development plugin còn có plugin validation tasks phù hợp; để chắc chắn chạy validation trước release, gọi explicit:

```bash
./gradlew check validatePlugins --console=plain
```

Đừng giả định `check` mặc định bao gồm **mọi custom functionalTest suite** khi bạn chỉ tạo source set. Mục 12 đã thêm `check.dependsOn(functionalTest)` rõ ràng cho phương án tách.

### 18.1. Test naming và phân tách reports

Nên đặt tên rõ:

- `GreetingFormatterTest` — pure unit logic.
- `GreetingPluginConfigurationTest` — ProjectBuilder configuration test.
- `GreetingPluginFunctionalTest` — TestKit build behavior.
- Một test suite độc lập `functionalTest` nếu CI muốn reports và cadence riêng.

Tách tests theo **loại behavior và chi phí**, không chỉ vì tên class chứa chữ `Functional`. Functional tests cần fixture setup và cleanup; nếu để toàn bộ tests trong `test` thì `./gradlew test` chạy tất cả đúng như baseline.

### 18.2. Security và isolation

TestKit không phải security sandbox tuyệt đối. Plugin code chạy trong Gradle process của fixture, có thể đọc filesystem/network trong phạm vi tài khoản CI. Không chạy plugin source chưa được review ở CI runner chứa secrets nhạy cảm. Fixture nên dùng fake credentials, temp directories, stub services và repository policies được duyệt. Tránh để tests ghi thư mục dùng chung hoặc `~/.gradle` trừ khi đã có lý do cụ thể.

### 18.3. Không bịa “đã chạy” khi mới đọc source

Một bài học minh họa có thể nêu **kết quả dự kiến** dựa trên mã nguồn. Khi áp dụng vào project thực, chỉ gọi tests “PASS” sau khi Gradle thật đã chạy và reports được kiểm tra. `TaskOutcome.SUCCESS` trong code là **assertion dự kiến**; không tự là chứng cứ rằng CI đã chạy lệnh.

## 19. Bài tập thực hành

**Bài 1 — Pure logic:** Thêm test `GreetingFormatter.format("Alice")` trả về `Hello, Alice!`. Vì sao không cần GradleRunner? Vì format không phụ thuộc Gradle API.

**Bài 2 — Error handling:** Thêm unit test `format("  ")` ném `IllegalArgumentException` và message đúng. Có cần tạo fixture build.gradle để test một hàm thuần không? Không.

**Bài 3 — ProjectBuilder:** Thêm assertion `task.getGroup()` bằng `demo`. Điều gì chưa được chứng minh? Task action chưa chạy thật.

**Bài 4 — Plugin ID:** Đổi ID trong `gradlePlugin.plugins.greeting` thành `example.salutation` nhưng fixture vẫn dùng `example.greeting`. TestKit lỗi pha nào? Plugin resolution; sửa ID trong fixture.

**Bài 5 — Default functional:** Dùng GradleRunner apply plugin và chạy `greet`, assert `Hello, Gradle!` cùng `TaskOutcome.SUCCESS`.

**Bài 6 — Override extension:** Trong fixture thêm `greeting { recipient.set('Team') }`. Vì sao task nhận Team dù đã đăng ký trước? Vì task input convention lấy từ managed extension property.

**Bài 7 — Negative test:** Đặt `recipient.set('   ')`, dùng `buildAndFail()`, assert task FAILED và message `recipient must not be blank`. Vì sao chỉ gọi `buildAndFail()` là chưa đủ? Build có thể fail vì nguyên nhân không liên quan.

**Bài 8 — TestKit metadata:** Xóa `withPluginClasspath()` khỏi runner. Vì sao fixture plugin ID có thể không resolve? Plugin chưa publish, fixture không tự nhìn thấy plugin classes của test process.

**Bài 9 — GradleRunner vs ProjectBuilder:** Nêu ba việc ProjectBuilder làm được và ba việc cần GradleRunner. Gợi ý: inspect extension/task registration vs execute real task, inspect TaskOutcome, report build failure.

**Bài 10 — Reports:** Chạy chỉ `GreetingFormatterTest` qua `--tests`; vì sao HTML report không chứa 3 TestKit cases? Vì name filter đã chọn subset.

**Bài 11 — Separate suite:** Chuyển `GreetingPluginFunctionalTest.java` vào `src/functionalTest/java`, thêm cấu hình mục 12. Chạy `test` và `functionalTest`. Kỳ vọng lần lượt **5** và **3** tests, nếu source chuyển không trùng.

**Bài 12 — Caching:** Thử thêm `--build-cache` cho task `greet`. Tại sao không mong FROM_CACHE? Task chỉ in console và được disable caching; chưa có output file.

**Bài 13 — Version matrix:** Dùng `withGradleVersion("9.0")`, chạy fixture. Những thành phần nào có thể cần network và JDK phù hợp? Gradle distribution, plugin dependencies và Java runtime.

**Bài 14 — Configuration Cache:** Thử `--configuration-cache` với fixture. Vì sao không được lưu live `Project` vào task action? Configuration Cache cần task execution state được Gradle quản lý/serialize an toàn.

**Bài 15 — CI:** Tạo pipeline có unit, TestKit functional, validatePlugins, sample consumer và reports. Tại sao không chỉ dùng `./gradlew jar` để quyết định publish?

### Tự kiểm tra nhanh

1. **Unit test Java logic có cần TestKit không?** Không.
2. **ProjectBuilder có chạy full Gradle build không?** Không.
3. **GradleRunner có chạy build thật không?** Có, qua Tooling API.
4. **`java-gradle-plugin` có tích hợp TestKit không?** Có.
5. **`withPluginClasspath()` giúp gì?** Đưa plugin-under-test vào fixture plugin classpath.
6. **Fixture dùng plugin DSL nào?** `plugins { id 'example.greeting' }`.
7. **`build()` dùng khi nào?** Kỳ vọng build thành công.
8. **`buildAndFail()` dùng khi nào?** Kỳ vọng build thất bại.
9. **`TaskOutcome.SUCCESS` nghĩa gì?** Task thực thi thành công.
10. **`TaskOutcome.FAILED` nghĩa gì?** Task đã thất bại.
11. **`TaskOutcome.FROM_CACHE` có tự xảy ra cho task chỉ in console không?** Không theo lab.
12. **`@Input` đánh dấu gì?** Task input property.
13. **Managed `Property<String>` có lợi ích gì?** Gradle quản lý value/providers/lazy wiring.
14. **`@TempDir` dùng gì?** Fixture directory riêng cho test.
15. **TestKit fixture có dùng chung build.gradle của plugin project không?** Không.
16. **Một baseline có mấy JUnit tests?** 8: 4 + 1 + 3.
17. **Có cần publish plugin trước TestKit không?** Không khi dùng automatic classpath injection.
18. **`validatePlugins` có thay functional tests không?** Không.
19. **Configuration Cache có giống Build Cache không?** Không.
20. **`gradlePlugin.testSourceSets` cần chú ý khi nào?** Khi functional tests chạy ở source set tùy chỉnh.

## 20. Tài liệu chính thức

- **Gradle — Testing Build Logic with TestKit:** `GradleRunner`, `withPluginClasspath()`, `build()`/`buildAndFail()`, test fixture isolation, cross-version testing, caching/debug: https://docs.gradle.org/current/userguide/test_kit.html
- **Gradle — Testing Gradle Plugins:** unit/ProjectBuilder vs functional testing, cách chọn tầng và cấu hình test suites: https://docs.gradle.org/current/userguide/testing_gradle_plugins.html
- **Gradle — Gradle Plugin Development Plugin:** `java-gradle-plugin`, `gradleTestKit()`, `pluginDescriptors`, `pluginUnderTestMetadata`, `validatePlugins`: https://docs.gradle.org/current/userguide/java_gradle_plugin.html
- **Gradle — ProjectBuilder API:** https://docs.gradle.org/current/javadoc/org/gradle/testfixtures/ProjectBuilder.html
- **Gradle — GradleRunner API:** https://docs.gradle.org/current/javadoc/org/gradle/testkit/runner/GradleRunner.html
- **Gradle — Test task / JUnit Platform:** `useJUnitPlatform()`, reports, filters: https://docs.gradle.org/current/userguide/java_testing.html
- **Gradle — Implementing Custom Tasks:** managed task properties, `@Input`, `@TaskAction`, validation: https://docs.gradle.org/current/userguide/implementing_custom_tasks.html
- **Gradle — Task Configuration Avoidance:** `tasks.register`, `configureEach`: https://docs.gradle.org/current/userguide/task_configuration_avoidance.html
- **Gradle — Configuration Cache:** build logic execution state restrictions: https://docs.gradle.org/current/userguide/configuration_cache.html
- **Gradle — Build Cache / Cacheable Tasks:** `@CacheableTask`, task outputs và cache behavior: https://docs.gradle.org/current/userguide/build_cache.html
- **JUnit 5.11.4 User Guide:** JUnit Jupiter `@Test`, assertions, `@TempDir`: https://docs.junit.org/5.11.4/user-guide/

**Kết luận:** Một Gradle plugin tốt cần **unit tests** cho logic thuần, **ProjectBuilder tests** cho registration/configuration và **Gradle TestKit functional tests** để chứng minh plugin thực sự áp dụng và chạy trong Gradle consumer build. `java-gradle-plugin` tạo plugin descriptors cùng TestKit metadata; `GradleRunner.withPluginClasspath()` giúp fixture resolve plugin local qua `plugins { }` mà không publish. Dùng `build()` với thành công, `buildAndFail()` với lỗi dự kiến, kiểm tra cả output và TaskOutcome, phân biệt caching modes và giữ fixtures độc lập. Khi plugin lớn lên, tách functionalTest source set/task, gắn vào `check` và thêm matrix Gradle/JDK cùng `validatePlugins` trước khi phát hành.