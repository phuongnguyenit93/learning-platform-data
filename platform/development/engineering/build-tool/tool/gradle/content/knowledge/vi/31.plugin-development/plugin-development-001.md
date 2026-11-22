# Cấu trúc dự án plugin và Java Gradle Plugin Development plugin

## 1. Mục tiêu: chuyển logic build lặp lại thành một Gradle plugin có thể kiểm thử

Khi một tổ chức có nhiều ứng dụng hoặc thư viện Java, các quy tắc build dễ bị copy vào nhiều file `build.gradle`: tạo task, cấu hình Java toolchain, kiểm tra license, chuẩn hóa resources, xuất báo cáo, kiểm thử integration, hoặc đặt conventions cho module. Cách copy/paste có nhược điểm:

- Cùng một lỗi phải sửa ở nhiều project.
- Developer có thể quên áp một quy tắc.
- Khó kiểm thử riêng build logic với các trường hợp PASS/FAIL.
- Không có plugin ID và version rõ ràng để chia sẻ.
- Các task được viết trực tiếp trong build script dễ tạo side effects/configuration-cache issues.
- Khi publication hoặc API Gradle thay đổi, không có nơi quản lý compatibility thống nhất.

**Gradle binary plugin** giải quyết bằng cách đóng gói Java/Groovy/Kotlin code thành JAR, công bố plugin ID và triển khai `Plugin<Project>`. Build khác áp plugin qua `plugins { id '...' }` và sử dụng task/extension do plugin tạo.

Bài này nằm trong chủ đề **Phát triển plugin**, tập trung vào **cấu trúc một dự án plugin độc lập** và core plugin `java-gradle-plugin` (*Java Gradle Plugin Development plugin*).

**Sau bài học, bạn có thể:**
1. Phân biệt script plugin, precompiled script plugin và binary plugin.
2. Khai `id 'java-gradle-plugin'` và `gradlePlugin { plugins { ... } }` bằng Gradle Groovy DSL.
3. Tạo plugin Java 17 dùng `Plugin<Project>`, một extension được quản lý bởi Gradle, một typed task có `@Input` và `@OutputFile`.
4. Hiểu `gradleApi()`, plugin descriptor ở `META-INF/gradle-plugins`, `pluginDescriptors`, `validatePlugins` và `pluginUnderTestMetadata`.
5. Viết JUnit 5 + Gradle TestKit functional test qua `GradleRunner.withPluginClasspath()` và xác nhận output thực.
6. Áp plugin chưa publish vào build khác qua `pluginManagement { includeBuild(...) }`.
7. Phân biệt plugin implementation artifact và plugin marker artifact khi dùng `maven-publish`.
8. Biết các lỗi phổ biến về plugin ID, implementation class, classpath, TestKit, Gradle/JDK versions và publishing.
9. Thiết kế plugin tránh cấu hình quá sớm, đọc file trong configuration hoặc sửa project khác không có chủ đích.

Các ví dụ sử dụng **Java 17**, **Gradle Groovy DSL** và Gradle Wrapper. Lệnh Unix-like là `./gradlew`, PowerShell Windows là `.\gradlew.bat`. Với plugin Java 17, Gradle runtime của consumer phải chạy trên JVM tương thích để có thể load class của plugin.

## 2. Ba cách chia sẻ build logic trong Gradle

| Cách | Định nghĩa | Trường hợp phù hợp | Khả năng tái sử dụng |
| --- | --- | --- | --- |
| **Script plugin** | Một `.gradle` áp qua `apply from: ...` | Logic nhỏ/legacy, ít khuyến nghị cho build mới | Hạn chế, khó test/version |
| **Precompiled script plugin** | `.gradle.kts` hoặc `.gradle` được biên dịch trong build-logic | Convention plugins ngắn, gần DSL | Tốt trong repository hoặc included build |
| **Binary plugin** | Java/Kotlin/Groovy class implements `Plugin<T>`, packaged JAR | Logic phức tạp, plugin API, task types/extension, chia sẻ nhiều builds | Tốt, có thể version và publish |

Bài này xây **binary plugin bằng Java**, không nhầm với việc chỉ thêm một custom task vào `build.gradle`.

Gradle có nhiều loại plugin target:
- `Plugin<Project>`: áp vào một Gradle **Project**, ví dụ tạo tasks/extensions cho module.
- `Plugin<Settings>`: áp vào Settings lifecycle, thường để kiểm soát settings/plugin management.
- `Plugin<Gradle>`: áp vào đối tượng Gradle cho một số logic cấp invocation.

Trong bài, chọn **`Plugin<Project>`** vì nhiệm vụ là tạo một task trong project. Không gắn một project plugin vào `settings.gradle` như thể nó là Settings plugin.

### 2.1. `java-gradle-plugin` là gì?

`java-gradle-plugin` là **core Gradle plugin** giúp tác giả **phát triển Gradle plugins trong một Java/JVM project**. Nó:

- Tự áp **Java Library plugin** (`java-library`).
- Thêm Gradle API vào `compileOnlyApi` thông qua `gradleApi()` để code plugin compile được với `org.gradle.api.*`.
- Cung cấp hỗ trợ **Gradle TestKit** cho tests.
- Đọc `gradlePlugin.plugins` declarations để sinh plugin descriptors.
- Tạo các tasks `pluginDescriptors`, `pluginUnderTestMetadata`, `validatePlugins`.
- Hỗ trợ cấu hình plugin marker publications khi áp thêm `maven-publish`/`ivy-publish`.
- Kết nối plugin development với convention về Java source sets và plugin test classpath.

Vì vậy, với binary plugin Java thông thường, bạn **không cần** tự viết `src/main/resources/META-INF/gradle-plugins/<id>.properties` nếu đã khai plugin trong `gradlePlugin.plugins`. Plugin Development plugin tạo descriptor giúp Gradle phát hiện plugin class.

**Phân biệt:** `java-gradle-plugin` không phải plugin Java bình thường mà consumer phải áp để **sử dụng** plugin của bạn. Nó thuộc **dự án xây plugin**. Consumer chỉ áp **plugin ID bạn định nghĩa**.

## 3. Cấu trúc một dự án binary plugin độc lập

Ví dụ plugin tạo một file văn bản chứa lời chào, có cấu hình qua extension `greeting` và một task `writeGreeting`:

~~~text
greeting-plugin/
├── settings.gradle
├── build.gradle
├── src/
│   ├── main/
│   │   └── java/
│   │       └── dev/
│   │           └── acme/
│   │               └── greeting/
│   │                   ├── GreetingPlugin.java
│   │                   ├── GreetingExtension.java
│   │                   ├── GreetingTask.java
│   │                   └── GreetingText.java
│   └── test/
│       └── java/
│           └── dev/
│               └── acme/
│                   └── greeting/
│                       └── GreetingPluginFunctionalTest.java
├── consumer/
│   ├── settings.gradle
│   └── build.gradle
├── gradlew
├── gradlew.bat
└── gradle/
    └── wrapper/
        ├── gradle-wrapper.jar
        └── gradle-wrapper.properties
~~~

**Phạm vi:**
- Root `greeting-plugin` là **một Gradle build** chuyên tạo binary plugin.
- `src/main/java` chứa code mà plugin JAR sẽ đóng gói.
- `src/test/java` chứa functional test của plugin, không thuộc plugin artifact.
- `consumer` là **Gradle build riêng**, có `settings.gradle` riêng để thử dùng plugin qua included build. Root `settings.gradle` không `include 'consumer'`, nên consumer **không** là subproject của plugin producer.
- Gradle Wrapper đảm bảo nhóm/CI dùng cùng Gradle distribution đã chọn.
- `build/` được sinh khi chạy tasks, **không** commit những build outputs.
- Plugin descriptor sẽ được tạo dưới `build/`/JAR khi build, không cần tự đặt file thủ công tại `src/main/resources`.

**Plugin ID dùng trong bài:** `dev.acme.greeting`.

**Implementation class:** `dev.acme.greeting.GreetingPlugin`.

**Task được đăng ký:** `writeGreeting`.

**Extension:** `greeting`, property `recipient`.

**Task output dự kiến:** `build/generated/greeting/message.txt`.

Mỗi tên có nhiệm vụ riêng. Không nhầm plugin ID `dev.acme.greeting` với Maven `group`, với root project name `greeting-plugin` hoặc tên task `writeGreeting`.

## 4. `settings.gradle` và `build.gradle` của dự án plugin

### 4.1. `settings.gradle`

~~~groovy
rootProject.name = 'greeting-plugin'
~~~

Đây là project name, ảnh hưởng mặc định tên plugin implementation JAR và Maven artifactId nếu publish. Không quyết định plugin ID trong `plugins { id ... }`.

### 4.2. `build.gradle` — toàn bộ file runnable

~~~groovy
plugins {
    id 'java-gradle-plugin'
}

group = 'dev.acme'
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
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

gradlePlugin {
    plugins {
        register('greeting') {
            id = 'dev.acme.greeting'
            implementationClass = 'dev.acme.greeting.GreetingPlugin'
        }
    }
}
~~~

**Giải thích từng khối:**

1. `id 'java-gradle-plugin'` là core plugin Gradle cho **dự án tác giả plugin**. Nó tự áp `java-library` và thêm Gradle API dependency, nên không cần `id 'java-library'` hoặc `implementation gradleApi()` lặp trong lab.
2. `group` và `version` mô tả implementation artifact nếu sau này publish Maven.
3. `java.toolchain.languageVersion=17` chọn Java 17 compiler cho mã plugin. Điều này **không ép** mọi consumer Java project compile bằng Java 17; nó chỉ đặt toolchain cho **plugin project**.
4. `mavenCentral()` dùng để resolve **JUnit Jupiter/JUnit Platform** test dependencies. Nó không phải nơi tự động publish plugin.
5. `testImplementation junit-jupiter` cung cấp JUnit 5 API/engine; `testRuntimeOnly junit-platform-launcher` giúp chạy tests trên JUnit Platform.
6. `useJUnitPlatform()` cấu hình Gradle Test task sử dụng JUnit Platform.
7. `gradlePlugin.plugins.register('greeting')` là tên **plugin declaration trong Gradle build model**, không phải ID consumer nhìn thấy. Nó có thể khác ID thực.
8. `id = 'dev.acme.greeting'` là ID thực để dùng trong `plugins { id 'dev.acme.greeting' }`.
9. `implementationClass` phải là **tên Java class đầy đủ package**, class đó implement `Plugin<Project>` và có thể được Gradle load/instantiate.
10. `java-gradle-plugin` hỗ trợ TestKit, bao gồm plugin-under-test classpath metadata. Vì vậy tests trong default `src/test/java` có thể dùng `GradleRunner.withPluginClasspath()` mà không tự xây một plugin JAR rồi copy tới fixture.

**Về versions:** JUnit 5.11.4/launcher 1.11.4 được chọn làm ví dụ khớp nhau, không phải khẳng định mới nhất. Cần Gradle Wrapper và JDK runtime tương thích phiên bản Gradle dùng. Plugin JAR biên dịch target Java 17 sẽ không load trên JVM quá cũ.

### 4.3. `java-gradle-plugin` có tự publish lên Plugin Portal không?

**Không.** Áp plugin development giúp tạo JAR, descriptors và publishing metadata khi kết hợp plugin khác, nhưng **không tự upload** lên Gradle Plugin Portal.

Muốn phát hành:
- Maven repository riêng: áp thêm `maven-publish`, cấu hình `publishing.repositories`; Gradle có thể tự tạo implementation/marker publications.
- Gradle Plugin Portal: cần **Plugin Publish Plugin** (`com.gradle.plugin-publish`), metadata/credentials phù hợp và task `publishPlugins` theo cơ chế Portal.

Việc Gradle Plugin Development plugin có hỗ trợ publish metadata **không** đồng nghĩa ai chạy `build` sẽ upload artifact.

## 5. Code Java 17: plugin, extension và task đúng chuẩn Gradle

Bài lab tách ba trách nhiệm:
- `GreetingPlugin` **register** extension/task, nối Providers.
- `GreetingExtension` chứa **cấu hình của người dùng**.
- `GreetingTask` chứa **hành động thực thi** và khai inputs/outputs.
- `GreetingText` chứa **logic Java thuần** có thể biên dịch và thử riêng.

Tách như vậy giúp tránh gom logic I/O, configuration và string processing trong một `Plugin.apply` method.

### 5.1. `src/main/java/dev/acme/greeting/GreetingText.java`

~~~java
package dev.acme.greeting;

/** Pure Java formatting logic, independent of the Gradle API. */
public final class GreetingText {

    private GreetingText() {
    }

    public static String message(String recipient) {
        return "Hello, " + recipient + "!\n";
    }

    public static void main(String[] args) {
        String recipient = args.length == 0 ? "Gradle" : args[0];
        System.out.print(message(recipient));
    }
}
~~~

**Đây là một Java 17 class độc lập**, không import Gradle API. Có thể kiểm tra logic bằng `javac`/`java` ngay cả khi chưa build plugin:

~~~bash
javac -encoding UTF-8 --release 17 -d standalone-out src/main/java/dev/acme/greeting/GreetingText.java
java -cp standalone-out dev.acme.greeting.GreetingText Team
~~~

**Stdout chính xác:**

~~~text
Hello, Team!
~~~

Nếu không truyền argument:

~~~bash
java -cp standalone-out dev.acme.greeting.GreetingText
~~~

Stdout:

~~~text
Hello, Gradle!
~~~

**Quan trọng:** hai lệnh này **chỉ chứng minh Java utility hoạt động**, không chứng minh plugin ID/descriptors/Gradle task wiring đúng. Plugin còn cần `gradlePlugin` setup và functional tests ở các phần sau. Mã Java trong plugin project thường phụ thuộc Gradle API nên **không** thể `javac GreetingPlugin.java` riêng chỉ với JDK classpath.

### 5.2. `src/main/java/dev/acme/greeting/GreetingExtension.java`

~~~java
package dev.acme.greeting;

import org.gradle.api.provider.Property;

/** User-facing configuration for the greeting plugin. */
public abstract class GreetingExtension {

    public abstract Property<String> getRecipient();
}
~~~

Đây là một **Gradle-managed abstract type**:
- Property được cung cấp qua Gradle object model khi plugin tạo extension bằng `project.getExtensions().create(...)`.
- `Property<String>` là lazy, có thể nhận giá trị trực tiếp hoặc `Provider<String>`.
- Không cần tự gọi `new GreetingExtension()` hoặc tự cấp phát một concrete field.
- Extension không cần biết `Project` và không thực hiện file I/O.

Người dùng cấu hình qua Groovy DSL:

~~~groovy
greeting {
    recipient.set('Team')
}
~~~

Đây là snippet consumer. Khi `recipient` không được cấu hình, plugin sẽ dùng default `Gradle`.

### 5.3. `src/main/java/dev/acme/greeting/GreetingTask.java`

~~~java
package dev.acme.greeting;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

/** Writes exactly one deterministic UTF-8 output file. */
public abstract class GreetingTask extends DefaultTask {

    @Input
    public abstract Property<String> getRecipient();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();

    @TaskAction
    public void writeGreeting() throws IOException {
        Path path = getOutputFile().get().getAsFile().toPath();

        Files.createDirectories(path.getParent());
        Files.writeString(
            path,
            GreetingText.message(getRecipient().get()),
            StandardCharsets.UTF_8
        );
    }
}
~~~

**Vì sao thiết kế task như vậy?**

- `GreetingTask extends DefaultTask`: typed Gradle task có thể đăng ký qua `tasks.register`.
- `@Input Property<String>`: Gradle biết giá trị recipient ảnh hưởng output. Khi người dùng đổi `Team` thành `Dev`, task phải được chạy lại để cập nhật file.
- `@OutputFile RegularFileProperty`: Gradle biết output file cụ thể để theo dõi up-to-date/producer-consumer.
- `@TaskAction`: file I/O chỉ xảy ra ở **execution phase**, không ở project configuration.
- `Files.createDirectories`: tạo parent directory khi task chạy.
- `Files.writeString(..., StandardCharsets.UTF_8)`: encoding rõ ràng, không lệ thuộc system default charset.
- `GreetingText.message(...)` thuần Java giúp tách logic dễ test.
- Không sử dụng `new File("C:\\Users\\...")`, `System.getProperty("user.dir")` hoặc đường dẫn tuyệt đối của một developer.
- Không ghi file vào `src/main/java`, `src/main/resources` hoặc thư mục chung giữa nhiều projects.

Task action sử dụng chỉ các property values đã khai; không capture `Project` hoặc truy cập `project.getExtensions()` trong execution, nên cấu trúc phù hợp hơn với configuration cache.

**Không được tự động thêm `@CacheableTask` chỉ vì đã có `@Input` và `@OutputFile`.** Caching là một quyết định về tính deterministic/relocatable, side effects và correctness. Task này có output đơn giản, nhưng trong plugin thực tế cần đánh giá toàn bộ inputs/tool versions trước khi opt-in build cache.

### 5.4. `src/main/java/dev/acme/greeting/GreetingPlugin.java`

~~~java
package dev.acme.greeting;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

/** Registers the extension and the task without doing work in apply(). */
public final class GreetingPlugin implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        GreetingExtension extension = project.getExtensions().create(
            "greeting",
            GreetingExtension.class
        );

        extension.getRecipient().convention("Gradle");

        project.getTasks().register(
            "writeGreeting",
            GreetingTask.class,
            task -> {
                task.setGroup("documentation");
                task.setDescription("Writes a UTF-8 greeting text file");

                task.getRecipient().convention(
                    extension.getRecipient()
                );

                task.getOutputFile().convention(
                    project.getLayout()
                        .getBuildDirectory()
                        .file("generated/greeting/message.txt")
                );
            }
        );
    }
}
~~~

**Giải thích:**

1. `Plugin<Project>` là interface Gradle dùng để áp plugin vào project.
2. `apply(Project)` được gọi trong **configuration phase**, nên chỉ đăng ký object/configuration, không ghi file.
3. `extensions.create("greeting", GreetingExtension.class)` tạo một extension mà consumer cấu hình được.
4. `getRecipient().convention("Gradle")` cung cấp default nhưng cho phép consumer override bằng `.set(...)`.
5. `tasks.register(...)` **lazy task registration**, không cấu hình thực thi task ngay khi plugin áp.
6. `task.getRecipient().convention(extension.getRecipient())` nối task input tới extension Property qua provider API, không snapshot thành giá trị quá sớm.
7. `project.getLayout().getBuildDirectory().file(...)` tạo file provider dưới `build/` của **project áp plugin**, không phải dưới root plugin producer hoặc máy developer.
8. `setGroup`/`setDescription` để `./gradlew tasks --all` hiển thị rõ.

**Vì sao không viết trực tiếp `project.getTasks().create("writeGreeting")` rồi `doLast`?** Code kiểu đó khó chia sẻ type, testability và có thể cấu hình eager. Task type với managed properties hỗ trợ Gradle lifecycle/up-to-date tracking rõ ràng hơn.

### 5.5. Chuyển giá trị cấu hình nhưng vẫn lazy

Khi consumer cấu hình:

~~~groovy
greeting {
    recipient.set('Team')
}
~~~

Task `writeGreeting` nhận `Team` khi thực thi. Nếu không cấu hình, nhận `Gradle`. Plugin không cần gọi `extension.getRecipient().get()` trong `apply` để lấy giá trị quá sớm; điều đó có thể phá khả năng override hoặc đọc provider trước thời điểm thích hợp.

## 6. Build plugin và kiểm tra descriptor/JAR

Từ root `greeting-plugin`:

~~~bash
./gradlew clean build
./gradlew validatePlugins
./gradlew tasks --all
~~~

Nếu đã có Gradle Wrapper tương thích và JDK 17, build sẽ compile Java plugin classes và chạy JUnit/TestKit tests. Dependencies JUnit Jupiter cần được resolve từ Maven Central hoặc cache.

**Các task tiêu biểu do `java-gradle-plugin` thêm:**

| Task | Vai trò |
| --- | --- |
| `pluginDescriptors` | Sinh plugin descriptor resources từ `gradlePlugin.plugins` declarations |
| `validatePlugins` | Kiểm tra public API của custom tasks/artifact transforms, annotations của properties và vấn đề validation |
| `pluginUnderTestMetadata` | Sinh classpath metadata cho TestKit/plugin-under-test |
| `compileJava` | Compile plugin implementation và task/extension Java |
| `jar` | Đóng gói classes và plugin descriptors vào binary JAR |
| `test` | JUnit tests, trong lab có GradleRunner functional test |
| `check` | Lifecycle verification, bao gồm tests và checks do plugins nối vào |

Chạy:

~~~bash
jar tf build/libs/greeting-plugin-1.0.0.jar
~~~

Tìm các entries trọng tâm:

~~~text
dev/acme/greeting/GreetingPlugin.class
dev/acme/greeting/GreetingExtension.class
dev/acme/greeting/GreetingTask.class
dev/acme/greeting/GreetingText.class
META-INF/gradle-plugins/dev.acme.greeting.properties
~~~

Kiểm tra descriptor trong JAR bằng công cụ giải nén hoặc `jar xf` vào **một thư mục kiểm tra tạm** (không giải nén bừa vào source root). Nội dung chính được tạo theo convention:

~~~properties
implementation-class=dev.acme.greeting.GreetingPlugin
~~~

**Descriptor path chính xác gắn với plugin ID:** `META-INF/gradle-plugins/dev.acme.greeting.properties`.

Nếu file descriptor thiếu, hãy kiểm tra:
- Plugin declaration trong `gradlePlugin.plugins` có thật không?
- `id` có đúng `dev.acme.greeting`?
- `implementationClass` có khớp package/class không?
- Java class có compile thành class file trong JAR không?
- Task `pluginDescriptors` đã chạy và resource được đóng gói chưa?
- Bạn có vô tình tạo manual descriptor conflict với generated descriptor không?

**Không nhầm:** `pluginDescriptors` sinh file để Gradle **load plugin từ JAR**, còn **plugin marker artifact** là metadata Maven/Ivy dùng khi consumer tìm plugin bằng `plugins {}` từ repository.

## 7. Functional test bằng JUnit 5 + Gradle TestKit

### 7.1. Vì sao unit test thuần chưa đủ?

Một unit test cho `GreetingText.message` chứng minh string formatting đúng, nhưng không chứng minh:
- `plugins { id 'dev.acme.greeting' }` có resolve plugin ID được không.
- `Plugin.apply` có tạo extension/task không.
- Task input/output annotations hợp lệ không.
- File được tạo đúng đường dẫn và đúng bytes không.
- Consumer có override extension property được không.

Gradle **TestKit** giải quyết bằng `GradleRunner`, chạy một **Gradle build thật** trong fixture project độc lập từ JUnit test. TestKit dùng Tooling API, có thể tạo task graph và kiểm tra `TaskOutcome`/file output.

### 7.2. Tại sao `withPluginClasspath()` cần thiết?

GradleRunner chạy một build riêng, không tự thấy classpath của JUnit JVM. `withPluginClasspath()` đưa plugin-under-test code và dependencies vào classpath để fixture có thể áp plugin qua `plugins {}`.

Khi dùng `java-gradle-plugin` và default `src/test/java` source set, Gradle tự tạo `pluginUnderTestMetadata` và cung cấp plugin classpath metadata cho TestKit. Bạn chỉ cần gọi:

~~~java
GradleRunner.create()
    .withProjectDir(projectDir.toFile())
    .withArguments("writeGreeting", "--stacktrace")
    .withPluginClasspath()
    .build();
~~~

**Cực kỳ quan trọng:** việc auto-inject plugin classpath theo cơ chế này hoạt động khi fixture áp plugin qua **`plugins {}` DSL**, không phải giả định áp bằng mọi cơ chế legacy `apply plugin:` đều tự được resolve. Không dùng `testImplementation files('build/libs/...')` thủ công như một cách “khắc phục” vĩnh viễn.

### 7.3. `src/test/java/dev/acme/greeting/GreetingPluginFunctionalTest.java`

~~~java
package dev.acme.greeting;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.gradle.testkit.runner.TaskOutcome;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

class GreetingPluginFunctionalTest {

    @TempDir
    Path projectDir;

    @Test
    void defaultRecipientWritesExpectedFile() throws IOException {
        createFixture(
            "plugins { id 'dev.acme.greeting' }\n"
        );

        BuildResult result = runGreeting();

        assertNotNull(result.task(":writeGreeting"));
        assertEquals(
            TaskOutcome.SUCCESS,
            result.task(":writeGreeting").getOutcome()
        );

        Path generatedFile = projectDir.resolve(
            "build/generated/greeting/message.txt"
        );
        assertEquals(
            "Hello, Gradle!\n",
            Files.readString(generatedFile, StandardCharsets.UTF_8)
        );
    }

    @Test
    void configuredRecipientOverridesDefault() throws IOException {
        createFixture(
            "plugins { id 'dev.acme.greeting' }\n"
                + "greeting { recipient.set('Team') }\n"
        );

        BuildResult result = runGreeting();

        assertNotNull(result.task(":writeGreeting"));
        assertEquals(
            TaskOutcome.SUCCESS,
            result.task(":writeGreeting").getOutcome()
        );

        Path generatedFile = projectDir.resolve(
            "build/generated/greeting/message.txt"
        );
        assertEquals(
            "Hello, Team!\n",
            Files.readString(generatedFile, StandardCharsets.UTF_8)
        );
    }

    private void createFixture(String buildScript) throws IOException {
        Files.writeString(
            projectDir.resolve("settings.gradle"),
            "rootProject.name = 'fixture'\n",
            StandardCharsets.UTF_8
        );
        Files.writeString(
            projectDir.resolve("build.gradle"),
            buildScript,
            StandardCharsets.UTF_8
        );
    }

    private BuildResult runGreeting() {
        return GradleRunner.create()
            .withProjectDir(projectDir.toFile())
            .withArguments("writeGreeting", "--stacktrace")
            .withPluginClasspath()
            .build();
    }
}
~~~

**Vì sao đây là một functional test tốt cho lab?**

- `@TempDir` tạo fixture directory tách biệt; hai tests không ghi chung `build/`.
- `settings.gradle`/`build.gradle` fixture là project thực, áp plugin theo **plugin ID**.
- `withPluginClasspath()` cung cấp plugin-under-test dependency resolution.
- `BuildResult.task(":writeGreeting").getOutcome()` xác nhận Gradle task đã được thực thi thành công.
- `Files.readString(...)` kiểm tra **exact UTF-8 content**, bao gồm dấu xuống dòng cuối.
- Một test kiểm tra default `Gradle`, test kia kiểm tra user override `Team`.
- Không assert toàn bộ Gradle log, vì thông báo Gradle thay đổi theo version/OS/caching.

Chạy:

~~~bash
./gradlew test
./gradlew validatePlugins
./gradlew check
~~~

**Kỳ vọng:** có **hai JUnit functional tests PASS** và plugin property validation không báo lỗi cho task type của lab. TestKit khởi chạy các Gradle builds thật nên có thể tốn thời gian hơn unit test thuần. Kết quả `test` có thể hiện `UP-TO-DATE` ở lần sau nếu inputs không đổi.

Nếu bạn cố tình đổi expected content thành `"Hello, Other!\n"`, JUnit test sẽ FAIL. Đó là bằng chứng rằng TestKit đang kiểm tra hành vi thực, không chỉ kiểm tra plugin class compile.

### 7.4. Khi cần chạy nhiều Gradle versions?

TestKit có `GradleRunner.withGradleVersion("...")` và lựa chọn Gradle distributions để kiểm tra compatibility. Nhưng:
- Phải dùng Gradle versions tương thích với Java 17/plugin bytecode.
- Một Gradle version cũ có thể không hiểu Java/Gradle APIs mới.
- TestKit và Tooling API có compatibility bounds.
- CI nhiều matrix versions sẽ tốn thời gian/download distributions.

**Không cần** `withGradleVersion(...)` trong lab khi bạn chỉ test bằng Gradle Wrapper đang sử dụng. Với plugin thương mại hoặc plugin public, thêm matrix Gradle/JDK versions có lý do và theo compatibility matrix.

### 7.5. Dùng riêng functional test source set

Dự án lớn có thể tách:
- `src/test/java` cho unit tests.
- `src/functionalTest/java` cho GradleRunner tests.

Khi đó phải cấu hình `jvm-test-suite`/custom source set, thêm JUnit/TestKit dependencies thích hợp, và cho Gradle Plugin Development plugin biết:

~~~groovy
gradlePlugin {
    testSourceSets(sourceSets.functionalTest)
}
~~~

Đây là **snippet nâng cao**, chỉ hợp lệ khi `sourceSets.functionalTest` đã được định nghĩa. Nếu chưa tạo, sẽ lỗi. Lab **không cần** phần này vì dùng default `src/test/java` và Gradle tự cấu hình TestKit classpath.

## 8. Consumer áp plugin chưa publish qua included build

### 8.1. Tại sao không cần publish trước?

Trong thời gian phát triển, Gradle composite/included build cho phép consumer dùng plugin source ngay tại workspace. Đối với plugin ID được khai trong `plugins {}` DSL, cách đáng tin là cấu hình **`pluginManagement.includeBuild`** trong consumer `settings.gradle`.

### 8.2. `consumer/settings.gradle`

~~~groovy
pluginManagement {
    includeBuild('..')
}

rootProject.name = 'greeting-consumer'
~~~

Vì `consumer` nằm **bên trong** directory `greeting-plugin`, đường dẫn `'..'` trỏ tới parent plugin project. `includeBuild` trong `pluginManagement` đăng ký build tạo plugin để Gradle resolution tìm plugin ID.

**Không dùng path tuyệt đối** như `C:/Users/Alice/projects/greeting-plugin` vì làm project không chạy được trên CI/máy đồng nghiệp. Nếu consumer và plugin là hai directories ngang hàng, đường dẫn sẽ là `'../greeting-plugin'`. Path luôn được resolve tương đối theo settings directory chứa `settings.gradle`.

### 8.3. `consumer/build.gradle`

~~~groovy
plugins {
    id 'dev.acme.greeting'
}

greeting {
    recipient.set('Team')
}
~~~

Consumer không khai `version '1.0.0'` vì plugin được lấy từ **included build**, không phải published plugin marker artifact trên external repository.

### 8.4. Chạy consumer

Từ plugin root trên Linux/macOS:

~~~bash
cd consumer
../gradlew writeGreeting --quiet
cat build/generated/greeting/message.txt
~~~

Stdout của lệnh `cat`:

~~~text
Hello, Team!
~~~

Lệnh `writeGreeting --quiet` có thể không in dòng gì nếu task không tự log; **file output mới là kết quả**, không phải console log Gradle. Có thể kiểm tra trạng thái tasks:

~~~bash
../gradlew tasks --all
../gradlew writeGreeting --info
../gradlew writeGreeting --configuration-cache
~~~

`--configuration-cache` dùng để **thử** compatibility với Gradle version hiện có, không phải cam kết mọi custom plugin đều configuration-cache safe chỉ vì dùng `tasks.register`.

Trên Windows PowerShell, từ plugin root:

~~~powershell
Set-Location consumer
..\gradlew.bat writeGreeting --quiet
Get-Content 'build/generated/greeting/message.txt'
~~~

Output text:

~~~text
Hello, Team!
~~~

**Quan trọng:** đây là hai Gradle builds khác nhau (plugin build và consumer build), không phải `:consumer` subproject. `consumer/settings.gradle` là build root riêng; `includeBuild('..')` chỉ đăng ký plugin build để giải quyết plugin ID.

### 8.5. Lợi ích của included build

- Dùng source plugin mới nhất ngay trong workspace.
- Không cần upload artifact hoặc override Maven Local.
- Consumer áp plugin bằng đúng cú pháp `plugins {}`.
- Gradle có thể build plugin implementation trước khi apply trong consumer.
- Giảm nguy cơ debug sai plugin version từ Gradle cache/repository.

Nếu plugin build có external dependencies, plugin project vẫn phải khai repositories/dependencies riêng; **included builds không tự chia sẻ mọi repository/project configuration** với consumer.

## 9. Plugin descriptor khác Plugin Marker Artifact

Đây là sự nhầm lẫn phổ biến trong phát triển plugin.

### 9.1. Descriptor trong JAR

Path:

~~~text
META-INF/gradle-plugins/dev.acme.greeting.properties
~~~

Nội dung đại ý:

~~~properties
implementation-class=dev.acme.greeting.GreetingPlugin
~~~

Descriptor trả lời: **“Khi plugin ID này có mặt trên plugin classpath, class nào thực thi `Plugin.apply`?”**

`java-gradle-plugin` sinh descriptor từ `gradlePlugin.plugins`. Nếu plugin ID khác implementation class package, descriptor vẫn hợp lệ miễn mapping chính xác.

### 9.2. Marker artifact ở Maven repository

Khi plugin được publish qua Maven và consumer dùng:

~~~groovy
plugins {
    id 'dev.acme.greeting' version '1.0.0'
}
~~~

Gradle plugin resolution thường tìm **marker module** có tọa độ:

~~~text
dev.acme.greeting:dev.acme.greeting.gradle.plugin:1.0.0
~~~

Marker POM trỏ tới **implementation artifact** thực, chẳng hạn:

~~~text
dev.acme:greeting-plugin:1.0.0
~~~

Đây là **hai Maven modules khác chức năng**:
- Implementation module cung cấp JAR thật với plugin classes/descriptors/dependencies.
- Marker module cho phép plugin DSL map ID + version tới implementation module.

**Plugin marker không phải một bản sao JAR khác có bytecode.** Nếu bạn tự publish implementation JAR mà không publish marker, consumer có thể bị lỗi `Plugin ... was not found` dù implementation artifact có trong Maven repo.

## 10. Dùng `maven-publish` để tạo implementation và marker publications

Bổ sung `id 'maven-publish'` vào **plugin project** khi muốn xuất bản tới một Maven repository. Đây là **biến thể mở rộng** của build.gradle phần 4; không copy nguyên hai `plugins {}` blocks vào cùng file.

~~~groovy
plugins {
    id 'java-gradle-plugin'
    id 'maven-publish'
}

group = 'dev.acme'
version = '1.0.0'

gradlePlugin {
    plugins {
        register('greeting') {
            id = 'dev.acme.greeting'
            implementationClass = 'dev.acme.greeting.GreetingPlugin'
        }
    }
}

publishing {
    repositories {
        maven {
            name = 'localPluginRepo'
            url = layout.buildDirectory.dir('plugin-repo')
        }
    }
}
~~~

Đây là **snippet publishing**, khi áp vào lab phải giữ thêm Java toolchain/repositories/JUnit dependencies/test config ở phần 4. `java-gradle-plugin` kết hợp `maven-publish` tự tạo Maven publications (khi `automatedPublishing` không tắt), ví dụ:

- `pluginMaven`: implementation JAR/module.
- `greetingPluginMarkerMaven`: marker publication tương ứng tên declaration `greeting`.

Tên task publication sẽ dựa trên publication và repository names. Kiểm tra thực tế:

~~~bash
./gradlew tasks --all
./gradlew publish
~~~

Với đích duy nhất `build/plugin-repo`, `publish` của ví dụ chỉ tạo Maven folder local, không gửi Internet.

**Cẩn thận:** `publish` trong project thực tế có thể upload đến **mọi publishing repositories** đã cấu hình. Không chạy bừa bãi nếu đã khai Nexus/Artifactory hoặc repository công khai.

### 10.1. Consumer dùng Maven marker thay included build

Sau khi đã publish vào `build/plugin-repo`, có thể thay **toàn bộ `consumer/settings.gradle`** bằng:

~~~groovy
pluginManagement {
    repositories {
        maven {
            url = uri('../build/plugin-repo')
        }
        gradlePluginPortal()
    }
}

rootProject.name = 'greeting-consumer'
~~~

`consumer/build.gradle` lúc này:

~~~groovy
plugins {
    id 'dev.acme.greeting' version '1.0.0'
}

greeting {
    recipient.set('Team')
}
~~~

Chạy consumer:

~~~bash
cd consumer
../gradlew writeGreeting
~~~

Nó sẽ tìm marker/implementation module qua Maven file repository đã khai. **Đây là chế độ thay thế** `pluginManagement.includeBuild('..')` của lab, không phải yêu cầu áp đồng thời cả hai nguồn. Nếu consumer vẫn `includeBuild('..')`, kết quả có thể lấy plugin source thay vì artifact vừa publish, làm bài kiểm tra publication không còn chính xác.

### 10.2. Phát hành Gradle Plugin Portal

Để plugin public có thể tìm trên Gradle Plugin Portal, cần **Plugin Publish Plugin** và thiết lập Portal account/credentials/metadata. Một build mới có thể sử dụng plugin ngoài:

~~~groovy
plugins {
    id 'com.gradle.plugin-publish' version '2.2.1'
}
~~~

Phiên bản trên là **ví dụ đã có trên Gradle Plugin Portal**, không có nghĩa là phiên bản mới nhất cho mọi môi trường. Từ các phiên bản hiện hành, Plugin Publish Plugin tự áp Java Gradle Plugin Development plugin và Maven Publish plugin. Cần khai plugin ID, implementation class và các Portal metadata như tên, mô tả, URL/SCM/tags theo yêu cầu.

Lệnh kiểm tra publication không upload:

~~~bash
./gradlew publishPlugins --validate-only
~~~

Lệnh upload thực:

~~~bash
./gradlew publishPlugins
~~~

**Không thực hiện task upload khi chưa có quyền/credential của tổ chức.** Plugin Portal publication khác `maven-publish` vào một Maven repo riêng. Đừng nghĩ có marker Maven rồi mặc nhiên plugin được duyệt trên Portal.

## 11. Plugin API và implementation details an toàn

### 11.1. Không ghi output trong `apply(Project)`

**Sai:**

~~~java
@Override
public void apply(Project project) {
    Path file = project.getLayout().getBuildDirectory()
        .file("generated/greeting/message.txt")
        .get().getAsFile().toPath();

    // Sai về lifecycle: tạo file ngay trong configuration phase.
    Files.writeString(file, "Hello!\n");
}
~~~

Đây là **anti-pattern minh họa**, không phải file compilable vì bỏ exception handling/imports. Nó tạo side effect ngay khi project configuration, kể cả khi người dùng chỉ chạy `help`, `tasks` hoặc một task không liên quan.

**Đúng:** `apply` đăng ký task; `@TaskAction` mới thực hiện I/O, và file output nằm trong `RegularFileProperty` có `@OutputFile`.

### 11.2. Không cấu hình task eager khi không cần

**Kém hơn:**

~~~java
project.getTasks().create("writeGreeting", GreetingTask.class);
~~~

**Tốt hơn:**

~~~java
project.getTasks().register("writeGreeting", GreetingTask.class);
~~~

`register` tạo TaskProvider, trì hoãn cấu hình nếu task không cần. Đối với plugin có nhiều tasks, task configuration avoidance giảm chi phí cho những builds không chạy task đó.

### 11.3. Managed properties và Provider API

Gradle properties `Property<T>`, `RegularFileProperty`, `DirectoryProperty`, `ConfigurableFileCollection` hỗ trợ:
- Wiring inputs/outputs/dependencies.
- Lazy evaluation và conventions.
- User override.
- Task up-to-date checks.
- Gradle configuration cache compatibility khi không capture unsupported state.

**Chú ý:** `Provider` không tự biến dữ liệu tùy tiện thành an toàn. Nếu provider đọc network/time/environment hoặc file mà task không khai input đúng, output có thể không deterministic. Với secrets, tránh tự print provider values trong logs.

### 11.4. Tách plugin configuration khỏi project-specific assumptions

Plugin không nên:
- Giả định mọi project có Java plugin.
- Tự sửa `rootProject.buildDir`.
- Đọc mutable task state của project khác.
- Tự force apply các plugin heavyweight nếu người dùng không muốn.
- Trộn `System.getenv("HOME")` với absolute path local.
- Giả định mọi module có `src/main/java`.

Nếu plugin **cần Java plugin**, có thể dùng:

~~~java
project.getPluginManager().withPlugin("java", applied -> {
    // Configurations only relevant when Java plugin is present.
});
~~~

Đây là **snippet minh họa**, không phải một Java source file độc lập. `withPlugin` là cách phản ứng khi plugin khác xuất hiện, thay vì eager access `project.getExtensions().getByType(JavaPluginExtension.class)` trước khi Java plugin được áp.

### 11.5. Task validation annotations

Một custom task nên khai:
- `@Input` cho giá trị scalar (ví dụ recipient).
- `@InputFile`/`@InputFiles` cho file inputs.
- `@InputDirectory` cho directory input, kèm `@PathSensitive` khi phù hợp.
- `@OutputFile`/`@OutputDirectory` cho files/directories được tạo.
- `@Internal` chỉ cho properties thực sự không ảnh hưởng output.
- `@Optional` khi input có thể không được cung cấp.
- `@Nested` cho nested bean chứa input properties.

Gradle `validatePlugins` có thể phát hiện annotation thiếu, incompatible task property types, hoặc validation problems. Nhưng **PASS không chứng minh plugin business logic đúng**; TestKit/functional tests vẫn cần.

## 12. Gradle API classpath, dependency và Java compatibility

### 12.1. `gradleApi()` và `gradleTestKit()`

Gradle có dependency helper methods:
- `gradleApi()`: public API classes của Gradle build runtime.
- `gradleTestKit()`: GradleRunner/TestKit tools cho functional tests.
- `localGroovy()`: Groovy libraries đi kèm Gradle, nếu thật sự cần Groovy build logic.

`java-gradle-plugin` tự thiết lập Gradle API cho plugin compilation và TestKit classpath cho mặc định tests. Thêm `implementation gradleApi()`/`testImplementation gradleTestKit()` vào lab thường không cần; ghi lặp dễ làm người đọc nghĩ Gradle API là third-party dependency với version phải điền riêng.

Nếu bạn đổi sang custom functional test source set, phải kiểm tra TestKit classpath metadata và test source set configuration thực, khi đó có thể cần khai các dependencies thủ công.

### 12.2. Không bundle Gradle runtime tùy tiện

Một plugin binary JAR không nên nhúng toàn bộ Gradle API implementation hoặc những dependency vốn do Gradle runtime cung cấp rồi tạo classloader conflicts. Sử dụng Gradle API compile-time dependency qua plugin development model.

Với thư viện bên ngoài mà plugin cần:
- Khai đúng `implementation` hoặc dependency scope thích hợp.
- Pin/điều phối versions khi phát hành plugin dùng chung.
- Xem xét conflicts với các plugins khác/classloaders.
- Dùng shading/relocation khi có lý do thật, không trộn dependencies tùy tiện.
- Không đọc hoặc in credentials trong plugin execution logs.

### 12.3. Toolchain của plugin khác toolchain của consumer

Plugin được viết và compile ở Java 17 nghĩa là plugin class files có Java 17 bytecode. Để **load plugin class**, Gradle daemon JVM phải chạy phiên bản Java hỗ trợ bytecode đó. Nhưng project consumer có thể compile một Java library target khác thông qua Java toolchain phù hợp.

Không tự mặc định plugin chỉ hỗ trợ Gradle 9 hoặc mọi Gradle 7/8/9. API/plugin compatibility cần được test theo **Gradle compatibility matrix** và JDK runtime được nhà phát triển hỗ trợ. Với Gradle versions cũ, các API như managed properties/task provider/plugin marker behavior có thể khác.

## 13. Tổ chức plugin dùng cho nhiều modules

Có hai tình huống khác nhau:

### 13.1. Build logic chỉ dùng trong một repository

Sử dụng build `build-logic` độc lập và thêm:

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}
~~~

vào **settings.gradle** của build tiêu thụ. Đây là mô hình rất phù hợp cho conventions nội bộ, có test và không cần phát hành Maven artifact mỗi lần sửa. Build `build-logic` có `settings.gradle`/`build.gradle` riêng và source plugin.

**Không nhầm** `includeBuild(...)` với `include 'module'`:
- `include 'core'` tạo subproject trong cùng build.
- `includeBuild('build-logic')` tham gia một **composite build**, giữ project/build configuration của included build độc lập.

### 13.2. Plugin chia sẻ nhiều repositories/teams

Binary plugin độc lập có thể publish lên Maven private repository hoặc Gradle Plugin Portal. Các consumers:
- Dùng `plugins { id 'dev.acme.greeting' version '1.0.0' }`.
- Khai plugin repository trong `pluginManagement.repositories` nếu không dùng Portal.
- Nâng plugin version có kế hoạch.
- Chạy tests/compatibility matrix khi nâng plugin.

Không viết `apply from: '../../../shared.gradle'` xuyên nhiều repositories nếu đã có nhu cầu version/dependency/compatibility quản lý tập trung.

### 13.3. Một plugin project có thể khai nhiều plugin IDs

Trong `gradlePlugin.plugins`, có thể khai nhiều declarations, mỗi declaration có ID/implementationClass riêng. Một implementation JAR có thể chứa nhiều plugin classes; Maven publish có thể tạo marker artifact **riêng cho mỗi ID**.

Không nhầm “một declaration name” với Java package. IDs phải đủ duy nhất và đặt theo namespace mà tổ chức kiểm soát, tránh trùng với core/community plugins.

## 14. Các chế độ kiểm thử và CI

| Mức kiểm thử | Công cụ | Kiểm tra điều gì? |
| --- | --- | --- |
| Pure Java unit test | JUnit 5 | Logic như `GreetingText.message` |
| Plugin configuration unit test | ProjectBuilder hoặc mocks khi thích hợp | Extension/task registration cơ bản |
| Functional test | Gradle TestKit `GradleRunner` | Build fixture áp plugin ID, chạy task, kiểm tra output |
| Integration/compatibility | GradleRunner nhiều versions/JDKs | Tương thích API/DSL/runtime |
| Plugin validation | `validatePlugins` | Input/output annotations và public work item types |
| Consumer smoke test | Included build hoặc published marker | Real plugin resolution và sử dụng plugin |

Trong lab, hai functional tests đủ chứng minh default/configured behavior. Với plugin production, nên bổ sung:
- Input thay đổi → task rerun, file đổi đúng.
- Input giữ nguyên → task có thể `UP-TO-DATE` theo Gradle semantics.
- File bị xóa → task chạy lại và tạo file.
- Output directory khác do user set → task honor provider.
- `--configuration-cache` lần một/lần hai.
- Multi-project: plugin áp vào hai projects tạo hai output paths riêng.
- Failure path: invalid/missing inputs có thông báo rõ.
- Compatibility với Gradle/JDK versions được tổ chức cam kết.
- Không làm thay đổi source files khi chỉ chạy `help` hoặc `tasks`.

### 14.1. Kiểm tra configuration cache

Trong consumer:

~~~bash
../gradlew writeGreeting --configuration-cache
../gradlew writeGreeting --configuration-cache
~~~

Quan sát lần thứ hai Gradle có reuse configuration cache không, và output file vẫn đúng. Plugin của lab giữ `Project` ở configuration phase và chỉ dùng managed task properties trong execution, là pattern nên dùng; nhưng compatibility còn phụ thuộc Gradle/tool versions và toàn bộ code của plugins khác trong build.

### 14.2. CI ví dụ

Một pipeline CI có thể:

~~~yaml
name: Gradle plugin verification

on: [push, pull_request]

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
      - name: Validate and test plugin
        run: ./gradlew clean check validatePlugins
      - name: Inspect plugin archive
        run: jar tf build/libs/greeting-plugin-1.0.0.jar
~~~

**Đây là mẫu CI**, không buộc sử dụng GitHub. Trên CI production, pin/review action versions và cấp permissions tối thiểu theo security policy. Không tự chạy `publishPlugins` trong Pull Request không tin cậy.

### 14.3. Phân biệt build vs release pipeline

**Verification:**
- Compile plugin classes.
- Run `validatePlugins`.
- Run TestKit/JUnit tests.
- Inspect JAR descriptors.
- Test compatibility/configuration cache theo mức cần.

**Release:**
- Chọn version/tags chính xác.
- Tạo binary/plugin marker artifacts.
- Kiểm tra POM/license/SCM metadata và artifact integrity.
- Chỉ upload từ trusted context có credentials.
- Không overwrite release version immutable.
- Thông báo compatibility/release notes cho consumers.

Task `./gradlew build` không phải lệnh `publishPlugins`.

## 15. Bẫy thực tế và nguyên nhân

### 15.1. Plugin ID không phải tên class

Nếu consumer khai:

~~~groovy
plugins {
    id 'dev.acme.greeting'
}
~~~

Gradle resolution cần:
- Có included plugin build, hoặc plugin marker trong configured plugin repositories.
- Descriptor mapping ID sang implementation class trong JAR.
- Class `dev.acme.greeting.GreetingPlugin` thực sự có trong JAR và implements `Plugin<Project>`.

Nếu ID trong `gradlePlugin` là `dev.acme.greeter` nhưng consumer dùng `dev.acme.greeting`, nó sẽ báo plugin not found dù class compile thành công.

### 15.2. `Plugin.apply` chỉ đăng ký, task action mới làm việc

Không gọi external process/network/file write trong `apply` nếu thực chất là task work. Khi consumer chạy `help`, Gradle vẫn cần configure build nhưng không nên thay source/generated files. Tách inputs/outputs và dùng `@TaskAction`.

### 15.3. Tránh đọc `Property.get()` quá sớm

Một extension có default `Gradle` nhưng consumer override `Team`. Nếu plugin gọi `get()` trong `apply` để snapshot trước khi consumer cấu hình DSL, task có thể luôn dùng default. Nối task property tới provider:

~~~java
task.getRecipient().convention(extension.getRecipient());
~~~

để task lấy giá trị sau khi configuration hoàn chỉnh.

### 15.4. `gradlePlugin.plugins` và manual descriptor mâu thuẫn

Nếu tự tạo `META-INF/gradle-plugins/dev.acme.greeting.properties` rồi lại để plugin development plugin sinh descriptor:
- Có thể tạo duplicate resource entry.
- File manual trỏ tới class cũ.
- Kiểm tra descriptor trong JAR khó biết bản nào được dùng.

Chỉ chọn một cơ chế phù hợp. Với lab này, dùng `gradlePlugin.plugins` làm nguồn sự thật duy nhất.

### 15.5. TestKit không thấy plugin

Nguyên nhân thường gặp:
- Không dùng `withPluginClasspath()`.
- Plugin project không áp `java-gradle-plugin`.
- Functional test ở custom source set nhưng chưa khai `gradlePlugin.testSourceSets(...)`.
- Fixture không áp plugin qua `plugins {}` DSL.
- Plugin ID/implementation class sai.
- Test fixture file `build.gradle` chứa lỗi cú pháp, không phải code plugin lỗi.

Đừng tự chèn implementation Jar vào classpath một cách vô hướng; xác định missing plugin-under-test metadata/classpath trước.

### 15.6. `validatePlugins` báo task property thiếu annotation

Khi thêm `getInputFile()`/`getTargetDirectory()` mà thiếu `@InputFile`/`@OutputDirectory`, Gradle có thể báo validation issue. Không dán `@Internal` lên mọi property cho build “PASS”; phải khai đúng semantic input/output để cache/incremental behavior hợp lệ.

### 15.7. Plugin marker không có trong Maven repo

Nếu chỉ publish `pluginMaven` implementation Jar, Gradle `plugins { id ... version ... }` có thể không resolve. Cần bật automated marker publications hoặc cấu hình plugin resolution strategy có chủ đích. Với `java-gradle-plugin + maven-publish`, Gradle tạo markers theo plugin declarations khi `automatedPublishing` được bật.

### 15.8. Plugin compiled Java 17 nhưng Gradle runtime cũ

Plugin JAR Java 17 có class file version 61. Nếu Gradle đang chạy JVM 11 hoặc 8, có thể gặp `UnsupportedClassVersionError`. Sửa Gradle runtime/JDK compatibility hoặc chọn compile target thấp hơn nếu API/plugin logic hỗ trợ; không đánh đồng với Java toolchain của consumer source.

### 15.9. Plugin code dựa vào internal Gradle APIs

Đừng import classes thuộc `org.gradle.api.internal` hoặc `org.gradle.internal` chỉ vì chúng xuất hiện trên classpath. Internal APIs không có compatibility guarantees như public API, có thể thay khi nâng Gradle. Ưu tiên các public interfaces, managed properties, Worker API và chính thức documented extension points.

### 15.10. Plugin tự sửa modules khác

Một `Plugin<Project>` áp tại `:app` không nên tự cấu hình `project(':core')` qua mutable state. Nếu cần shared conventions, apply cùng plugin riêng vào từng module; nếu cần data, khai project dependency/variant, không trực tiếp truy cập output paths.

## 16. Bảng lỗi và hướng giải quyết

| Hiện tượng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| `Plugin ... not found` | Không có included build/plugin marker, sai ID | Xem `settings.gradle pluginManagement`/ID/repository |
| `UnknownPluginException` trong fixture TestKit | Thiếu `withPluginClasspath` hoặc metadata | Kiểm tra `java-gradle-plugin` và source sets |
| `Cannot find symbol Plugin/Project` | Không có Gradle API compile classpath | Áp `java-gradle-plugin`, không chỉ Java plugin |
| `implementationClass not found` | Sai package/class name hoặc compile fail | Kiểm tra path, `package`, plugin declaration |
| `META-INF/gradle-plugins` descriptor thiếu | Không có plugin declaration hoặc resource task sai | Chạy `pluginDescriptors` và `jar tf` |
| `validatePlugins` fail | Thiếu input/output annotations | Sửa task managed properties/annotations |
| `Task writeGreeting not found` | Plugin chưa áp vào project | Kiểm tra `plugins { id 'dev.acme.greeting' }` |
| Extension `greeting` not found | apply không tạo extension, plugin khác shadow tên | Kiểm tra `extensions.create` và ID |
| Output file không có | Task chưa chạy hoặc provider output khác | Chạy `writeGreeting --info`, xem output path |
| Output luôn `Hello, Gradle!` | Đọc recipient quá sớm/bỏ wiring | Nối Task Property với extension provider |
| Output tái tạo vô lý mỗi lần | Task inputs/outputs sai, nondeterministic action | Kiểm tra annotations, task history/`--info` |
| TestKit fixture dùng JUnit 5 nhưng test `NO-SOURCE` | Sai source path/test framework setup | `src/test/java`, JUnit deps, `useJUnitPlatform()` |
| TestKit launch báo thiếu Gradle distribution | GradleRunner environment/network/caches | Kiểm tra Wrapper/Tooling API/compatibility |
| `UnsupportedClassVersionError` | Plugin JAR target Java cao hơn daemon JVM | Chọn Gradle runtime JDK phù hợp |
| Plugin Maven JAR có nhưng `plugins {}` không resolve | Thiếu plugin marker artifact | Bật marker publishing và pluginManagement repo |
| Consumer test dùng plugin source thay marker | `includeBuild` vẫn còn | Thử Maven mode bằng settings độc lập |
| Plugin compilation dùng dependency version khác runtime | Plugin classpath conflict | Kiểm tra dependencies, Java API, shading |
| Config cache report lỗi | Task action capture Project/file IO config | Dùng Providers và execution-time work |
| Plugin code lỗi sau Gradle upgrade | Dùng deprecated/internal Gradle APIs | Dùng public API, test compatibility matrix |
| `publishPlugins` bị 401 | Portal credentials/permissions thiếu | Chỉ chạy trong trusted release CI |
| Build upload nhầm | `publish`/`publishPlugins` gọi ngoài chủ đích | Tách verification/release jobs |

### 16.1. Lệnh debug nhanh

~~~bash
./gradlew projects
./gradlew tasks --all
./gradlew compileJava --stacktrace
./gradlew pluginDescriptors --info
./gradlew validatePlugins --info
./gradlew test --info
./gradlew check
./gradlew jar
jar tf build/libs/greeting-plugin-1.0.0.jar
~~~

Với consumer:

~~~bash
../gradlew tasks --all
../gradlew writeGreeting --stacktrace
../gradlew writeGreeting --configuration-cache
~~~

Không coi `--dry-run` là functional test: `./gradlew writeGreeting --dry-run` chỉ mô tả task sẽ chạy, không tạo file output để xác minh.

## 17. Bài tập có đáp án

### Bài 1 — Plugin ID vs class

**Câu hỏi:** Consumer gọi `id 'dev.acme.greeting'`. Có bắt buộc implementation class tên `Greeting` không?

**Đáp án:** Không. `gradlePlugin.plugins` map ID tới fully qualified class `dev.acme.greeting.GreetingPlugin`. Tên declaration `greeting` cũng không cần trùng ID.

### Bài 2 — Khai plugin project

**Câu hỏi:** Core plugin nào giảm boilerplate khi viết Java Gradle Plugin?

**Đáp án:** `id 'java-gradle-plugin'`. Nó tự áp Java Library plugin, Gradle API dependency, plugin descriptors, plugin validation và TestKit integration.

### Bài 3 — Source vị trí nào?

**Câu hỏi:** Với `package dev.acme.greeting`, `GreetingPlugin.java` phải ở đâu theo Java convention?

**Đáp án:** `src/main/java/dev/acme/greeting/GreetingPlugin.java`, chứa `public final class GreetingPlugin implements Plugin<Project>`.

### Bài 4 — Khi nào ghi file?

**Câu hỏi:** Có nên `Files.writeString` ngay trong `Plugin.apply` không?

**Đáp án:** Không. `apply` chỉ register/configure. File I/O thuộc `@TaskAction` execution, output được khai `@OutputFile`.

### Bài 5 — Managed properties

**Câu hỏi:** Tại sao Task dùng `Property<String>` và `RegularFileProperty` thay hard-coded String path?

**Đáp án:** Gradle biết inputs/outputs, hỗ trợ provider wiring, up-to-date, lazy evaluation, configuration cache khi triển khai đúng.

### Bài 6 — TestKit

**Câu hỏi:** `withPluginClasspath()` giúp gì?

**Đáp án:** Inject plugin-under-test vào GradleRunner fixture build để `plugins {}` resolve được plugin chưa publish.

### Bài 7 — Default configuration

**Câu hỏi:** Consumer không khai `greeting.recipient`, output của `writeGreeting` là gì?

**Đáp án:** File chứa chính xác `Hello, Gradle!` và một ký tự newline ở cuối.

### Bài 8 — Override configuration

**Câu hỏi:** Consumer khai `greeting { recipient.set('Team') }`. Output file?

**Đáp án:** `Hello, Team!` kèm final newline ở `build/generated/greeting/message.txt`.

### Bài 9 — Included build

**Câu hỏi:** Dùng `pluginManagement { includeBuild('..') }` trong consumer thì có cần publish plugin lên Maven trước không?

**Đáp án:** Không. Gradle build plugin from source khi cần để resolve ID.

### Bài 10 — Plugin marker

**Câu hỏi:** Plugin implementation artifact `dev.acme:greeting-plugin:1.0.0` có đủ cho `plugins { id 'dev.acme.greeting' version '1.0.0' }` không?

**Đáp án:** Không nhất thiết. Plugin DSL thông thường cần marker `dev.acme.greeting:dev.acme.greeting.gradle.plugin:1.0.0` hoặc resolution strategy/included plugin build. Java Gradle Plugin Development + Maven Publish có thể tự tạo marker publication.

### Bài 11 — Java compat

**Câu hỏi:** Plugin project compile target Java 17 nhưng consumer Gradle daemon chạy Java 11. Điều gì có thể xảy ra?

**Đáp án:** `UnsupportedClassVersionError` khi load plugin class. Toolchain của consumer code không thay daemon JVM ngay lập tức.

### Bài 12 — `validatePlugins`

**Câu hỏi:** Task viết output file nhưng getter không có `@OutputFile`. Cần làm gì?

**Đáp án:** Thêm annotation đúng cho `RegularFileProperty`, khai các inputs khác và chạy lại `validatePlugins`; không dùng `@Internal` để che output thật.

### Bài 13 — Test coverage

**Câu hỏi:** Unit test `GreetingText.message` PASS, có chứng minh plugin ID/tasks đúng chưa?

**Đáp án:** Chưa. Cần GradleRunner functional test áp plugin qua `plugins {}` và thực sự chạy `writeGreeting`.

### Bài 14 — Chia sẻ build logic

**Câu hỏi:** Trong monorepo, nên chép cùng plugin code vào 20 `build.gradle` hay dùng included build/convention plugin?

**Đáp án:** Dùng included build hoặc convention plugin để giảm duplication và giữ một nơi kiểm thử logic. Với nhiều repositories có thể publish binary plugin có version.

### Bài 15 — Thực hành end-to-end

1. Tạo project `greeting-plugin` với đủ files phần 3–5.
2. Chạy `./gradlew compileJava` và `./gradlew jar`.
3. Dùng `jar tf`, kiểm tra plugin classes và `META-INF/gradle-plugins/dev.acme.greeting.properties`.
4. Chạy `./gradlew validatePlugins`, sửa nếu có validation problems.
5. Chạy `./gradlew test` và xem hai TestKit tests PASS.
6. Chạy Java-only `GreetingText` bằng `javac`/`java`, đối chiếu stdout.
7. Tạo consumer `settings.gradle` với `pluginManagement.includeBuild('..')`, `build.gradle` áp plugin ID.
8. Chạy `../gradlew writeGreeting`, kiểm tra file và newline.
9. Thay recipient `Team` thành `Dev`, chạy lại; output phải đổi thành `Hello, Dev!`.
10. Chạy `--configuration-cache` hai lần để thử config cache.
11. Bổ sung `maven-publish` với file Maven repository riêng, publish và kiểm tra có implementation + marker module.
12. Thử consumer ở Maven marker mode bằng settings không còn includeBuild, đúng `version '1.0.0'`.
13. Cố tình đổi implementationClass sai trong một branch thử nghiệm và quan sát `jar`/plugin resolution validation; khôi phục trước commit.
14. Kiểm tra Gradle daemon JDK và plugin bytecode level để hiểu compatibility.

**Tiêu chí đạt:** Bạn hiểu cấu trúc Java Gradle plugin project, khai được ID và implementation class, viết typed task + extension bằng Provider API, chạy được TestKit/consumer, đọc plugin descriptor/marker, và phân biệt build plugin với publish plugin.

## 18. Checklist trước khi đưa plugin vào dự án thật

- [ ] Chọn đúng loại plugin: Project/Settings/Gradle; không nhầm script plugin với binary plugin.
- [ ] Dự án plugin độc lập có `settings.gradle`, `build.gradle` và đúng Java source packages.
- [ ] Áp `java-gradle-plugin`; không lặp Gradle API dependency vô ích.
- [ ] `gradlePlugin.plugins` có plugin ID unique, implementationClass tồn tại.
- [ ] Plugin descriptor được sinh đúng ở `META-INF/gradle-plugins`.
- [ ] Code `Plugin.apply` chỉ register/configure, không ghi file hoặc làm network work.
- [ ] Dùng `tasks.register`, `Property/Provider/RegularFileProperty` thay eager reads/absolute paths.
- [ ] Typed tasks có `@Input`/`@OutputFile` và declarations phù hợp.
- [ ] Task outputs nằm dưới module build directory, không chồng lấn source/task outputs khác.
- [ ] `validatePlugins` PASS, JUnit/TestKit functional tests PASS.
- [ ] TestKit fixtures áp plugin theo `plugins {}` và dùng `withPluginClasspath()`.
- [ ] Có test default, override, error path và output exact bytes/newlines.
- [ ] Gradle/JDK toolchain/consumer compatibility được kiểm chứng.
- [ ] Plugin runtime không dựa vào internal Gradle API.
- [ ] Consumer local dùng included build có đường dẫn tương đối, không hard-code máy developer.
- [ ] Maven publication có implementation và plugin marker nếu dùng published `plugins {}`.
- [ ] Thử published marker trong consumer độc lập, không chỉ composite substitution.
- [ ] Release metadata, license/SCM và repository credentials đúng chính sách.
- [ ] Không để secrets trong build script hoặc TestKit fixtures/logs.
- [ ] Kiểm tra configuration-cache/parallel behavior khi plugin hỗ trợ.
- [ ] Không cấp Plugin Portal deployment credentials cho untrusted CI jobs.
- [ ] Không overwrite release version hoặc thay binary mà giữ cùng plugin version.
- [ ] Cập nhật release notes/compatibility docs khi nâng Gradle API/plugin behavior.

## 19. Tài liệu Gradle chính thức

- [Gradle — Java Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): `java-gradle-plugin`, `gradlePlugin.plugins`, descriptor generation, `validatePlugins`, TestKit metadata và Maven marker publications.
- [Gradle — Implementing Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): script/precompiled/binary plugin choices.
- [Gradle — Writing Plugins](https://docs.gradle.org/current/userguide/writing_plugins.html): binary plugins và cách xây/chia sẻ Gradle build logic.
- [Gradle — Testing Gradle Plugins](https://docs.gradle.org/current/userguide/testing_gradle_plugins.html): unit/integration/functional testing levels.
- [Gradle — Testing Build Logic with TestKit](https://docs.gradle.org/current/userguide/test_kit.html): GradleRunner, `withPluginClasspath` và plugin-under-test injection.
- [Gradle — Plugin Development API](https://docs.gradle.org/current/javadoc/org/gradle/plugin/devel/plugins/JavaGradlePluginPlugin.html): Java Gradle Plugin Development plugin implementation.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): `pluginManagement.includeBuild` và included-build plugin resolution.
- [Gradle — Publishing Gradle Plugins](https://docs.gradle.org/current/userguide/publishing_gradle_plugins.html): marker module, Plugin Publish Plugin và Portal publication.
- [Gradle — Gradle Plugin Portal](https://plugins.gradle.org/): plugin IDs, published versions và release metadata.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `TaskProvider` và `register`.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): managed properties/Provider API.
- [Gradle — Gradle Task Validation](https://docs.gradle.org/current/userguide/validation_problems.html): task property annotations/validation diagnostics.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration-cache compatible plugin design.
- [Gradle — Java Toolchains](https://docs.gradle.org/current/userguide/toolchains.html): compile toolchain/runtime compatibility.
