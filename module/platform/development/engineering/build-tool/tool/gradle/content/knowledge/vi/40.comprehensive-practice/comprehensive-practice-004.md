# Phát triển plugin nội bộ có extension, custom task và TestKit trong Gradle

## 1. Mục tiêu thực hành

Khi nhiều dự án Java phải lặp lại một đoạn `build.gradle.kts` để sinh tài liệu, kiểm tra quy tắc, tạo mã nguồn hoặc đóng gói theo chuẩn tổ chức, việc sao chép task từ repository này sang repository khác sẽ gây lệch phiên bản, khó test và khó quản trị. Một **binary Gradle plugin nội bộ** giúp đưa build logic thành một sản phẩm có ID, version, API cấu hình, tasks, bộ kiểm thử và vòng đời phát hành riêng.

Bài học xây dựng plugin thực tế tên `dev.example.hello-report`, phiên bản `1.0.0`, viết bằng **Java 17**, dùng **Gradle Kotlin DSL** để cấu hình và tiêu thụ. Plugin cung cấp:

- Extension `greeting` để build consumer thiết lập `salutation` và `recipient`.
- Custom task `generateGreeting` tạo file `build/generated/greeting.txt`.
- Task khai báo `@Input` và `@OutputFile`, được đánh dấu `@CacheableTask` vì với cùng input luôn tạo đúng bytes như nhau.
- Giá trị mặc định qua `Property.convention(...)`, nối extension→task bằng Provider thay vì gọi `get()` khi cấu hình.
- Unit tests kiểm tra logic Java không phụ thuộc Gradle.
- Functional tests bằng **Gradle TestKit**, sử dụng `GradleRunner` chạy một Gradle build thật trong thư mục tạm, `withPluginClasspath()` và kiểm tra `TaskOutcome`/nội dung file.
- Bản kiểm thử lỗi cấu hình, incremental up-to-date, publication thử nghiệm vào local Maven folder và một consumer áp plugin bằng `plugins { id(...) version ... }`.
- Checklist Configuration Cache, Build Cache correctness, TestKit compatibility matrix, plugin validation và quy trình phát hành nội bộ.

Bài cũng phân biệt **build logic chạy trong một repository** với **plugin dùng lại giữa nhiều repositories** và chỉ rõ các mảnh mở rộng không thuộc phần lab chạy độc lập.

### Kết quả kỳ vọng ở consumer

~~~kotlin
plugins {
    base
    id("dev.example.hello-report") version "1.0.0"
}

greeting {
    salutation.set("Xin chào")
    recipient.set("Ada")
}
~~~

Chạy task sẽ tạo file với **nội dung chính xác** (UTF-8, có newline cuối):

~~~text
Xin chào, Ada!
~~~

Trên console Gradle có thể hiển thị thêm `> Task :generateGreeting`, `BUILD SUCCESSFUL`, `UP-TO-DATE` hay `FROM-CACHE` tùy build trước đó. Đây là **nội dung file output**, không phải toàn bộ terminal transcript cố định.

## 2. Chọn cách đóng gói build logic phù hợp

| Phương án | Thích hợp khi | Điểm cần lưu ý |
| --- | --- | --- |
| Task trực tiếp trong `build.gradle.kts` | Một task ngắn, dùng riêng một build. | Khó tái sử dụng và test độc lập; dễ làm build script phình to. |
| `buildSrc` | Logic dùng chung trong một build, cần truy cập tự động. | Build logic trở thành một phần classpath build; thay đổi có thể ảnh hưởng cấu hình/cache nhiều projects. |
| Included build `build-logic` | Convention/plugins dùng chung trong monorepo, version cùng source. | Cần `pluginManagement { includeBuild(...) }` khi tiêu thụ plugin bằng Plugin DSL. |
| Binary plugin công bố vào Maven nội bộ | Nhiều repositories/teams cùng sử dụng, cần SemVer và release độc lập. | Phải bảo trì API/compatibility, plugin marker publication và quyền publish. |
| Gradle Plugin Portal | Plugin dự định phân phối công khai. | Không cần cho plugin nội bộ, có quy trình Plugin Publish riêng. |

Plugin trong bài là **binary project plugin**: Java class implement `Plugin<Project>` và được đóng gói JAR. Nó **không** phải Settings plugin `Plugin<Settings>`, không phải script plugin `apply(from = "...")` và cũng không phải Java application mà build consumer chạy bằng `java -jar`.

### Kiến trúc ba lớp

~~~text
Consumer build.gradle.kts
  |
  | plugins { id("dev.example.hello-report") version "1.0.0" }
  | greeting { recipient.set("Ada") }
  v
HelloReportPlugin implements Plugin<Project>
  |
  +--> extensions.create("greeting", GreetingExtension.class)
  |       recipient: Property<String>
  |       salutation: Property<String>
  |       conventions: "World", "Hello"
  |
  +--> tasks.register("generateGreeting", GenerateGreetingTask.class)
          |
          +--> @Input recipient <- extension.recipient
          +--> @Input salutation <- extension.salutation
          +--> @OutputFile reportFile <- build/generated/greeting.txt
          |
          v
          @TaskAction
          GreetingText.render(...) -> UTF-8 output file
~~~

**Ranh giới quan trọng:**
- `Plugin.apply(Project)` chỉ thiết lập model: extension, conventions, đăng ký/wire tasks. **Không** tạo output file hoặc gọi network trong `apply`.
- Extension đại diện **cấu hình công khai**, không phải nơi xử lý side effects.
- Custom task thực hiện công việc trong `@TaskAction`, mọi dữ liệu ảnh hưởng output được khai báo qua annotated properties.
- `GradleRunner` chạy build consumer như “người dùng thật”, không chỉ gọi trực tiếp Java method.

## 3. Plugin ID, implementation class và Gradle plugin metadata

Trong `gradlePlugin { plugins { create(...) { ... } } }`:

| Thành phần | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Plugin ID | `dev.example.hello-report` | Tên consumer dùng trong `plugins` DSL. |
| Plugin declaration name | `helloReport` | Tên nội bộ của declaration trong `gradlePlugin.plugins`. |
| Implementation class | `dev.example.gradle.HelloReportPlugin` | Class Java Gradle nạp và gọi `apply(Project)`. |
| Main Maven coordinates | `dev.example.build:internal-greeting-plugin:1.0.0` | JAR chứa implementation. |
| Plugin marker coordinates | `dev.example.hello-report:dev.example.hello-report.gradle.plugin:1.0.0` | Metadata để Plugin DSL tìm implementation qua Maven repository. |
| Task name | `generateGreeting` | Task path trong project đã apply plugin. |
| Extension name | `greeting` | DSL block cho consumer. |

**Plugin ID không phải tên Maven artifact**. Khi kết hợp `java-gradle-plugin` và `maven-publish`, Gradle tự tạo main `pluginMaven` publication và marker publication theo mỗi declaration. Không được nghĩ rằng chỉ publish JAR bằng `jar` hoặc `publishToMavenLocal` là đủ để Plugin DSL resolve ID trong mọi môi trường.

`java-gradle-plugin` còn hỗ trợ:
- Tạo plugin descriptors trong `META-INF/gradle-plugins/<plugin-id>.properties` với `implementation-class=...`.
- Thêm compile-only Gradle API dependency cần cho plugin implementation.
- Đưa `gradleTestKit()` vào test dependencies.
- Sinh `pluginUnderTestMetadata` cho `GradleRunner.withPluginClasspath()`.
- Tạo `validatePlugins` để phát hiện các khai báo task property sai.
- Khi kết hợp `maven-publish`, cấu hình publications như trên.

Không cần thủ công tạo resource plugin descriptor khi đã dùng `gradlePlugin.plugins` đúng.

## 4. Cấu trúc lab độc lập, có publisher và consumer

~~~text
internal-plugin-lab/
├── plugin/
│   ├── gradlew
│   ├── gradlew.bat
│   ├── gradle/wrapper/...
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/dev/example/gradle/
│       │   ├── GreetingText.java
│       │   ├── GreetingExtension.java
│       │   ├── GenerateGreetingTask.java
│       │   └── HelloReportPlugin.java
│       └── test/java/dev/example/gradle/
│           ├── GreetingTextTest.java
│           └── HelloReportPluginFunctionalTest.java
└── consumer/
    ├── settings.gradle.kts
    └── build.gradle.kts
~~~

Các đường dẫn trong các lệnh sử dụng thư mục `plugin/` hoặc `consumer/` làm working directory theo phần tương ứng. **Plugin build và consumer build là hai Gradle builds riêng**, không cùng một multi-project build. Consumer dùng local Maven repository được tạo bởi plugin project trước, mô phỏng cách một repository khác tải plugin nội bộ.

Yêu cầu môi trường:
- Gradle Wrapper hợp lệ đã được commit trong `plugin/`, sử dụng một Gradle version hỗ trợ Java 17 và APIs trong bài; nên chạy/kiểm tra với Gradle hiện hành của tổ chức.
- JDK 17 tồn tại hoặc Gradle toolchain resolver đã được cấu hình để provision JDK.
- Có thể tải JUnit Jupiter 5.11.4 từ Maven Central cho lần đầu chạy tests.
- Windows dùng `.\gradlew.bat`; Unix/macOS dùng `./gradlew`.
- `maven-publish` trong lab chỉ ghi một directory local; không cần Maven server hay release credentials.

### Plugin `plugin/settings.gradle.kts`

~~~kotlin
rootProject.name = "internal-greeting-plugin"
~~~

`rootProject.name` xác định tên module chính trong Maven publication, khác plugin ID `dev.example.hello-report`. Điều này giúp bạn kiểm chứng cả **main artifact** và **plugin marker** khi publish.

## 5. `plugin/build.gradle.kts` đầy đủ

~~~kotlin
plugins {
    `java-gradle-plugin`
    `maven-publish`
}

group = "dev.example.build"
version = "1.0.0"

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}

gradlePlugin {
    plugins {
        create("helloReport") {
            id = "dev.example.hello-report"
            implementationClass = "dev.example.gradle.HelloReportPlugin"
            displayName = "Internal Hello Report Plugin"
            description = "Creates a deterministic greeting report"
        }
    }
}

dependencies {
    // java-gradle-plugin already provides Gradle API and gradleTestKit().
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}

publishing {
    repositories {
        maven {
            name = "localStaging"
            url = uri(layout.buildDirectory.dir("local-repo"))
        }
    }
}
~~~

**Tại sao không thêm `implementation(gradleApi())` và `testImplementation(gradleTestKit())`?** `java-gradle-plugin` đã tự cung cấp API classpath và TestKit convention theo tài liệu Gradle 9.x; thêm lần nữa không cần cho lab. JUnit framework vẫn phải khai báo riêng.

**Tại sao có `maven-publish`?** Để thử publication nội bộ mà không tạo repository thật. `java-gradle-plugin` chỉ tự tạo plugin marker Maven publications khi `maven-publish` cùng hiện diện. Các publications tự động được tạo cuối configuration phase; không tự định nghĩa một `MavenPublication` khác tên `pluginMaven` làm phát sinh hai JARs publish trùng.

**Tại sao không apply `java` riêng?** `java-gradle-plugin` tự apply Java Library plugin. Java toolchain mặc định của plugin build sẽ compile task/plugin sources với compiler Java 17.

**Điều gì chưa có ở đây?** Publish remote credentials, signing, SBOM, CI tag gate và source compatibility matrix cần thiết cho production. Chúng được đề cập cuối bài; lab local không giả vờ có server nội bộ.

## 6. Logic Java thuần: dễ kiểm thử không cần Gradle

File `plugin/src/main/java/dev/example/gradle/GreetingText.java`:

~~~java
package dev.example.gradle;

public final class GreetingText {
    private GreetingText() {
    }

    public static String render(String salutation, String recipient) {
        if (recipient == null || recipient.isBlank()) {
            throw new IllegalArgumentException(
                "recipient must not be blank"
            );
        }
        if (salutation == null || salutation.isBlank()) {
            throw new IllegalArgumentException(
                "salutation must not be blank"
            );
        }

        return salutation + ", " + recipient + "!\n";
    }

    public static void main(String[] args) {
        String recipient = args.length > 0 ? args[0] : "World";

        System.out.print(render("Hello", recipient));
        System.out.println("ARG_COUNT=" + args.length);
    }
}
~~~

`String.isBlank()` có trên Java 17. `render` là hàm thuần: cùng input string tạo **cùng UTF-8 text content** (trong Java là Unicode string), không phụ thuộc clock, random, môi trường hay đường dẫn workspace. Sử dụng `\n` cố định để report có bytes ổn định qua Windows/Unix.

### Kiểm tra độc lập bằng `javac` và `java`

Từ thư mục `plugin/`, trên Linux/macOS:

~~~bash
mkdir -p build/manual-classes

javac -encoding UTF-8 \
  -d build/manual-classes \
  src/main/java/dev/example/gradle/GreetingText.java

java -cp build/manual-classes \
  dev.example.gradle.GreetingText Ada
~~~

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual-classes | Out-Null

javac -encoding UTF-8 -d build/manual-classes src/main/java/dev/example/gradle/GreetingText.java

java -cp build/manual-classes dev.example.gradle.GreetingText Ada
~~~

**Java stdout chính xác:**

~~~text
Hello, Ada!
ARG_COUNT=1
~~~

Không có `Gradle` log trong trường hợp gọi Java main thủ công. Chỉ file `GreetingText.java` có thể biên dịch bằng một lệnh `javac` độc lập như trên; các file `GreetingExtension`, `GenerateGreetingTask` và `HelloReportPlugin` cần Gradle API classpath, nên phải compile bằng Gradle Wrapper và `java-gradle-plugin`.

## 7. Extension Java: cấu hình công khai có defaults và Providers

File `plugin/src/main/java/dev/example/gradle/GreetingExtension.java`:

~~~java
package dev.example.gradle;

import org.gradle.api.provider.Property;

public abstract class GreetingExtension {
    public abstract Property<String> getSalutation();
    public abstract Property<String> getRecipient();
}
~~~

Gradle tạo implementation cho abstract managed property getters khi extension được khởi tạo qua `ExtensionContainer.create(...)`. Không cần tự tạo constructor nhận `ObjectFactory` hoặc mutable string fields cho một extension đơn giản như lab.

Consumer dùng DSL:

~~~kotlin
greeting {
    salutation.set("Xin chào")
    recipient.set("Ada")
}
~~~

Hai properties là **Gradle `Property<String>`**, không phải Java Bean `setSalutation(String)` thông thường. Dùng Provider API cho phép:
- Có defaults do plugin đặt bằng `convention`.
- Consumer override bằng `set(...)`.
- Tạo chain từ `providers.gradleProperty(...)` hoặc `providers.environmentVariable(...)`.
- Trì hoãn đọc giá trị tới task execution, hỗ trợ configuration cache và incremental builds.
- Fingerprint task inputs qua annotations ở task type.

**Không đánh dấu extension property bằng `@Input` rồi tưởng task tự track input**. Task phải có `@Input` riêng; extension chỉ cung cấp data. Các managed properties trong extension cũng chưa tự thực thi công việc.

### Convention khác `set` ở đâu?

- `property.convention("World")` đặt default được dùng khi consumer không set override.
- `property.set("Ada")` là explicit value của consumer.
- `task.getRecipient().set(extension.getRecipient())` là **liên kết Provider**, không lấy value ngay.
- `task.getRecipient().set(extension.getRecipient().get())` lấy value **eagerly khi cấu hình** và có thể bỏ qua override hoặc env/config được áp sau; tránh cách này.
- Dùng `finalizeValueOnRead`/`disallowChanges` chỉ khi plugin có contract configuration lifecycle thực sự cần; đừng khóa extension quá sớm khiến consumer không cấu hình được.

## 8. Custom task: khai báo inputs/outputs và chỉ làm IO khi chạy

File `plugin/src/main/java/dev/example/gradle/GenerateGreetingTask.java`:

~~~java
package dev.example.gradle;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.api.DefaultTask;
import org.gradle.api.GradleException;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

@CacheableTask
public abstract class GenerateGreetingTask extends DefaultTask {

    @Input
    public abstract Property<String> getSalutation();

    @Input
    public abstract Property<String> getRecipient();

    @OutputFile
    public abstract RegularFileProperty getReportFile();

    @TaskAction
    public void writeReport() {
        String text = GreetingText.render(
            getSalutation().get(),
            getRecipient().get()
        );

        Path destination = getReportFile()
            .get().getAsFile().toPath();

        try {
            Files.createDirectories(destination.getParent());
            Files.writeString(
                destination,
                text,
                StandardCharsets.UTF_8
            );
        } catch (IOException cause) {
            throw new GradleException(
                "Failed to write greeting report",
                cause
            );
        }
    }
}
~~~

### Giải thích các annotation

| Thành phần | Gradle dùng để làm gì? |
| --- | --- |
| `@CacheableTask` | Cho phép Build Cache lưu/phục hồi output khi task đủ điều kiện. |
| `@Input` | Dấu `salutation` và `recipient` là dữ liệu ảnh hưởng bytes đầu ra. |
| `@OutputFile` | Gradle biết file được tạo và có thể kiểm tra up-to-date/store/restore. |
| `RegularFileProperty` | Kiểu Provider-based cho một output file, không phải string path trần. |
| `@TaskAction` | Phương thức chỉ chạy khi task execution thực sự cần. |
| `Files.writeString(..., UTF_8)` | Bytes output ổn định, không lệ thuộc default charset. |

**Vì sao task có thể cache?** Với cùng task implementation và hai input strings, `GreetingText.render` tạo đúng cùng text, file path thuộc `build/`, không network, không timestamp/random. Không có side effects khác. Nếu sau này task đọc HTTP, system clock, Git HEAD, environment variable hoặc file khác thì **phải khai báo như input** hoặc tắt cache khi không thể bảo đảm deterministic.

**Vì sao không dùng `getProject()` bên trong `writeReport`?** Project model là configuration-time API và thường không được dùng từ task execution nếu muốn Configuration Cache tương thích. Task action chỉ truy cập annotated task properties và Java IO. Plugin `apply` bên dưới mới sử dụng `Project` để đăng ký task và set conventions.

### Up-to-date checks và Build Cache

- Lần đầu task chạy thường có outcome `SUCCESS`.
- Lần hai cùng workspace, inputs và output không thay đổi: thường `UP-TO-DATE`.
- Sau `clean` và bật `--build-cache`, nếu cache đã có entry hợp lệ, task có thể `FROM-CACHE`.
- Nếu output bị sửa/xóa hoặc property thay đổi, task cần chạy lại hoặc dùng entry khác.
- `--no-build-cache` chỉ tắt task output Build Cache; up-to-date checks vẫn hoạt động.
- `--rerun-tasks` buộc actions chạy để chẩn đoán, không nên là mặc định mọi CI.
- `@CacheableTask` không đảm bảo cache hit: còn phụ thuộc key, full inputs/outputs contract, Gradle cache enablement và task validation.

## 9. Plugin implementation: đăng ký lazy task, nối extension→task

File `plugin/src/main/java/dev/example/gradle/HelloReportPlugin.java`:

~~~java
package dev.example.gradle;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class HelloReportPlugin implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        GreetingExtension extension = project.getExtensions()
            .create("greeting", GreetingExtension.class);

        extension.getSalutation().convention("Hello");
        extension.getRecipient().convention("World");

        project.getTasks().register(
            "generateGreeting",
            GenerateGreetingTask.class,
            task -> {
                task.setGroup("documentation");
                task.setDescription(
                    "Writes a deterministic greeting report"
                );

                task.getSalutation().set(
                    extension.getSalutation()
                );
                task.getRecipient().set(
                    extension.getRecipient()
                );
                task.getReportFile().convention(
                    project.getLayout()
                        .getBuildDirectory()
                        .file("generated/greeting.txt")
                );
            }
        );
    }
}
~~~

**Phân tích đúng dòng quan trọng:**

1. `Plugin<Project>` cho biết plugin áp dụng cho project, có thể apply ở root hoặc subproject.
2. `extensions.create("greeting", GreetingExtension.class)` đăng ký một extension do Gradle quản lý.
3. `convention("Hello")`/`convention("World")` tạo defaults, không cướp quyền override.
4. `tasks.register(...)` trả một `TaskProvider` và tránh tạo/configure task sớm không cần thiết; không dùng `tasks.create(...)`.
5. Hai lệnh `set(extension.getX())` giữ **Provider link**, giúp cập nhật giá trị consumer ở configuration phase và fingerprint chính xác khi task thực thi.
6. `layout.buildDirectory.file(...)` tạo một `Provider<RegularFile>`; không hard-code `project.getBuildDir()`/absolute path.
7. Không gọi `task.getRecipient().get()` trong `apply`, không mở file, không resolve dependencies/network, không khởi động process.
8. Không ép mọi project phải apply `java` plugin, vì task này chỉ tạo file text. Nếu plugin cần Java extension/tasks, cân nhắc áp `java-base` hoặc phản ứng khi Java plugin xuất hiện; **đừng áp thêm plugin bất ngờ**.

### Gọi plugin ở subproject

Nếu một multi-project build apply plugin trong `:service`, task có path `:service:generateGreeting` và file output dưới `service/build/generated/greeting.txt`; nếu apply ở root, task `:generateGreeting`. `tasks.register` không tự tạo task ở mọi subproject.

**Đừng dùng `allprojects { apply(plugin = "...") }` như chính sách mặc định**; áp plugin có chủ đích qua convention plugins hoặc từng subproject. Cũng không tạo task mọi module khi plugin chỉ được áp tại root.

## 10. Unit test cho logic thuần Java

File `plugin/src/test/java/dev/example/gradle/GreetingTextTest.java`:

~~~java
package dev.example.gradle;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingTextTest {

    @Test
    void rendersExactBytesContract() {
        assertEquals(
            "Hello, Ada!\n",
            GreetingText.render("Hello", "Ada")
        );
    }

    @Test
    void rejectsBlankRecipient() {
        assertThrows(
            IllegalArgumentException.class,
            () -> GreetingText.render("Hello", "  ")
        );
    }

    @Test
    void rejectsBlankSalutation() {
        assertThrows(
            IllegalArgumentException.class,
            () -> GreetingText.render(" ", "Ada")
        );
    }
}
~~~

Unit tests chạy nhanh, không cần tạo Gradle project fixture. Chúng xác nhận algorithm và validation; **không** chứng minh Gradle đã đăng ký extension/task đúng, plugin ID có resolve được hoặc report file thực sự được tạo. Phần đó phải dùng TestKit.

## 11. Functional tests: chạy một Gradle build thật với TestKit

Gradle TestKit cung cấp `GradleRunner` để khởi động build trong thư mục tạm, kiểm tra task outcomes và file outputs. Khi dùng `java-gradle-plugin`:
- `pluginUnderTestMetadata` được sinh để TestKit biết plugin classpath.
- `withPluginClasspath()` tự inject classpath, không phải publish plugin vào local Maven trước.
- Trong test fixture, áp ID qua **`plugins { id("dev.example.hello-report") }`**, không dùng `apply(plugin = "...")` khi kiểm tra auto injection convention.
- Chạy qua Gradle thật nhưng dùng project fixture tách biệt; đây là functional/integration test của plugin, không chỉ gọi Java class.

### 11.1. Complete `HelloReportPluginFunctionalTest.java`

File `plugin/src/test/java/dev/example/gradle/HelloReportPluginFunctionalTest.java`:

~~~java
package dev.example.gradle;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.gradle.testkit.runner.TaskOutcome;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class HelloReportPluginFunctionalTest {

    @TempDir
    Path projectDir;

    private void fixture(String buildScript) throws IOException {
        Files.writeString(
            projectDir.resolve("settings.gradle.kts"),
            "rootProject.name = \"fixture\"\n",
            StandardCharsets.UTF_8
        );

        Files.writeString(
            projectDir.resolve("build.gradle.kts"),
            buildScript,
            StandardCharsets.UTF_8
        );
    }

    private GradleRunner runner(String... requestedTasks) {
        List<String> args = new ArrayList<>(
            Arrays.asList(requestedTasks)
        );

        args.add("--no-build-cache");
        args.add("--no-configuration-cache");
        args.add("--stacktrace");

        return GradleRunner.create()
            .withProjectDir(projectDir.toFile())
            .withArguments(args)
            .withPluginClasspath();
    }

    private Path reportPath() {
        return projectDir.resolve(
            "build/generated/greeting.txt"
        );
    }

    @Test
    void defaultExtensionValuesCreateReport() throws IOException {
        fixture(
            "plugins { id(\"dev.example.hello-report\") }\n"
        );

        BuildResult result = runner("generateGreeting").build();

        assertEquals(
            TaskOutcome.SUCCESS,
            result.task(":generateGreeting").getOutcome()
        );
        assertEquals(
            "Hello, World!\n",
            Files.readString(
                reportPath(),
                StandardCharsets.UTF_8
            )
        );
    }

    @Test
    void configuredExtensionChangesTaskOutput() throws IOException {
        fixture(
            "plugins { id(\"dev.example.hello-report\") }\n"
            + "greeting {\n"
            + "    salutation.set(\"Xin chào\")\n"
            + "    recipient.set(\"Ada\")\n"
            + "}\n"
        );

        BuildResult result = runner("generateGreeting").build();

        assertEquals(
            TaskOutcome.SUCCESS,
            result.task(":generateGreeting").getOutcome()
        );
        assertEquals(
            "Xin chào, Ada!\n",
            Files.readString(
                reportPath(),
                StandardCharsets.UTF_8
            )
        );
    }

    @Test
    void secondRunIsUpToDate() throws IOException {
        fixture(
            "plugins { id(\"dev.example.hello-report\") }\n"
        );

        runner("generateGreeting").build();

        BuildResult second = runner("generateGreeting").build();

        assertEquals(
            TaskOutcome.UP_TO_DATE,
            second.task(":generateGreeting").getOutcome()
        );
        assertEquals(
            "Hello, World!\n",
            Files.readString(
                reportPath(),
                StandardCharsets.UTF_8
            )
        );
    }

    @Test
    void blankRecipientFailsTheBuild() throws IOException {
        fixture(
            "plugins { id(\"dev.example.hello-report\") }\n"
            + "greeting { recipient.set(\"  \") }\n"
        );

        BuildResult result = runner("generateGreeting")
            .buildAndFail();

        assertEquals(
            TaskOutcome.FAILED,
            result.task(":generateGreeting").getOutcome()
        );
        assertTrue(
            result.getOutput().contains(
                "recipient must not be blank"
            )
        );
    }
}
~~~

### 11.2. Test này kiểm tra được những gì?

- **Default case:** extension tồn tại, defaults được áp, task chạy và ghi file.
- **Configuration case:** consumer thay `salutation` và `recipient`, Provider wiring giữ đúng giá trị.
- **Incremental case:** lần hai cùng source/outputs nhận `UP_TO_DATE` vì `@Input`/`@OutputFile` được khai báo.
- **Failure case:** invalid business input làm task fail, `GradleRunner.buildAndFail()` không che lỗi, assertion tìm thông điệp.
- **Plugin classpath:** sử dụng plugin ID thật trong `plugins` DSL, do `withPluginClasspath()` hỗ trợ.

Trong các tests trên, `--no-build-cache` để lần đầu không `FROM_CACHE` từ cache cũ; `--no-configuration-cache` để cô lập bài TestKit cơ bản khỏi kiểm thử serialization riêng. **Một test không nên assert mọi lần đầu đều `SUCCESS` nếu nó đang bật shared Build Cache và đã có entry đúng.**

### 11.3. `build()` và `buildAndFail()` khác nhau

- `GradleRunner.build()` kỳ vọng build thành công; nếu fail, test ném exception.
- `GradleRunner.buildAndFail()` kỳ vọng build fail; nếu build success, test ném exception.
- `BuildResult.getOutput()` là output Gradle process, không chỉ output report file.
- `BuildResult.task(":generateGreeting").getOutcome()` đọc task outcome; nếu task không có, `task(...)` có thể null — đây là dấu hiệu fixture/plugin declaration sai.
- `withPluginClasspath()` sử dụng metadata do `java-gradle-plugin` tạo; nếu file metadata không tồn tại sẽ có lỗi classpath metadata thay vì “plugin không được tìm thấy” trong fixture.
- `@TempDir` của JUnit Jupiter tạo project dir cho từng test invocation, tránh tests tranh chấp output.

**Không** cho TestKit fixture chạy Maven publish/upload secrets hoặc đọc production environment. Functional tests chạy build logic thật nên vẫn có quyền của user/runner, không phải sandbox bảo mật chống mã độc.

## 12. Chạy plugin tests và xem validation

Từ `internal-plugin-lab/plugin/`:

~~~bash
# Kiểm tra version và tasks do Plugin Development plugin tạo.
./gradlew --version
./gradlew tasks --all

# Compile plugin, unit tests và TestKit functional tests.
./gradlew clean test --stacktrace --console=plain

# Gradle static validation cho custom task types/properties.
./gradlew validatePlugins --stacktrace --console=plain

# Verification + plugin descriptor/JAR.
./gradlew check jar --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test --stacktrace --console=plain
.\gradlew.bat validatePlugins --stacktrace --console=plain
.\gradlew.bat check jar --console=plain
~~~

**Kỳ vọng về test count của mã lab:** class `GreetingTextTest` có 3 JUnit cases; class `HelloReportPluginFunctionalTest` có 4 JUnit cases, tổng **7 tests** khi các class/methods được JUnit Platform phát hiện như khai báo. Một số Gradle tasks khác (compile, pluginDescriptors, pluginUnderTestMetadata) chạy trước test; không được đồng nhất log Gradle toàn build với số JUnit tests.

Để xem outputs:
- Plugin test XML: `plugin/build/test-results/test/`.
- HTML: `plugin/build/reports/tests/test/index.html`.
- Plugin implementation JAR: `plugin/build/libs/internal-greeting-plugin-1.0.0.jar`.
- Plugin descriptor: entry `META-INF/gradle-plugins/dev.example.hello-report.properties` trong JAR.
- Task validation: `validatePlugins` sẽ báo annotation issues nếu task types không tuân API constraints; không tắt validation warnings như giải pháp lâu dài.

### Kiểm tra JAR descriptor

~~~bash
jar tf build/libs/internal-greeting-plugin-1.0.0.jar
~~~

Trong danh sách cần tìm:

~~~text
META-INF/gradle-plugins/dev.example.hello-report.properties
dev/example/gradle/HelloReportPlugin.class
dev/example/gradle/GenerateGreetingTask.class
dev/example/gradle/GreetingExtension.class
dev/example/gradle/GreetingText.class
~~~

Thông thường JAR cũng có `META-INF/MANIFEST.MF` và package directory entries; chúng không được liệt kê hết ở đây. Muốn kiểm tra descriptor content, dùng `unzip -p ...` trên Unix hoặc giải nén bằng tool tương đương để xác nhận `implementation-class=dev.example.gradle.HelloReportPlugin`.

## 13. Build Cache và Configuration Cache: mở rộng tests

Plugin sẽ được dùng trên nhiều workspaces/CI runners. Bên cạnh “chạy được”, cần kiểm tra **correctness khi Gradle tái sử dụng output hoặc configuration**.

### 13.1. Build Cache: cùng input → cùng bytes

Trong TestKit lab cơ bản đã vô hiệu hóa Build Cache. Ở consumer có thể thực hành:

~~~bash
# Consumer đã áp plugin và base, dùng wrapper plugin build.
../plugin/gradlew --build-cache generateGreeting
../plugin/gradlew --build-cache generateGreeting

# Task base:clean xoá consumer build/ output, không xóa Gradle cache.
../plugin/gradlew --build-cache clean generateGreeting
~~~

Kỳ vọng thông thường:
- Lượt đầu chạy action, có thể lưu Build Cache entry.
- Lượt hai `UP-TO-DATE` vì output vẫn tồn tại.
- Lượt ba, sau `clean` và khi có entry phù hợp, `FROM-CACHE`.

**Không cam kết `FROM-CACHE` nếu cache đang disabled, key thay, task không được store hoặc repository cache có issue.** Dùng `--info`/`-Dorg.gradle.caching.debug=true` để phân tích cache key. Nếu cần so no-cache control: `--no-build-cache --rerun-tasks`.

**Nếu task thêm input file:** annotate `@InputFile`/`@InputFiles`, chọn `@PathSensitive(PathSensitivity.RELATIVE)` khi semantics phụ thuộc relative path, hoặc `@Classpath` khi input là classpath. Đừng dùng `@Internal` để giấu input thật. Chỉ dùng `@CacheableTask` khi task deterministic/relocatable và không có side effect ngoài tracked outputs.

### 13.2. Configuration Cache: khác Build Cache

Configuration Cache lưu task graph/configuration state, **không** thay thế task output cache. Với plugin này:
- `apply` làm việc ở configuration time, đăng ký Provider/task.
- `@TaskAction` chỉ đọc task input/output properties, không gọi `Project`.
- Extension→task wiring dựa Provider, không dùng eager `project.afterEvaluate` hay `get()`.
- Không giữ mutable Project/Gradle model trong static global state.

Trong consumer:

~~~bash
../plugin/gradlew --configuration-cache generateGreeting
../plugin/gradlew --configuration-cache generateGreeting
~~~

Lần hai thường có dòng `Reusing configuration cache.` nếu build/settings/plugin configuration inputs không đổi. Đồng thời task có thể `UP-TO-DATE` — đó là **hai tối ưu độc lập**.

Để thêm TestKit CC functional test, có thể tạo helper runner không thêm `--no-configuration-cache` và chạy hai lần với `--configuration-cache`, assert output chứa `Reusing configuration cache.`. Nếu test thất bại, đọc HTML report do Gradle tạo và xem task action có truy cập `Project`/`Configuration` hay closure chụp state không serialize được.

### 13.3. TestKit phiên bản Gradle khác

`GradleRunner.withGradleVersion("...")` cho phép test plugin trên version Gradle cụ thể khi bạn cần compatibility matrix. Ví dụ mảnh Java:

~~~java
GradleRunner.create()
    .withProjectDir(projectDir.toFile())
    .withGradleVersion("9.9.0")
    .withArguments("generateGreeting", "--stacktrace")
    .withPluginClasspath()
    .build();
~~~

Đây là **mảnh code**, giả định `projectDir` và fixture đã được tạo như mục 11. TestKit có thể download Gradle distribution và cần network. Không chạy version matrix tùy tiện tới những Gradle releases không hỗ trợ Java runtime/toolchains của plugin. Một Gradle plugin build với Java 17 classes sẽ yêu cầu Gradle runtime hỗ trợ Java 17 khi load implementation.

### 13.4. TestKit và isolated Gradle User Home

Functional tests chạy Gradle builds con, nên có thể ảnh hưởng Gradle User Home/cache/daemon của máy. Nếu CI có test parallel hoặc dùng shared runner, cân nhắc chỉ định TestKit directory/Gradle User Home riêng, giới hạn concurrency và bảo đảm fixtures không chia sẻ output paths. Không biến `GradleRunner.withDebug(true)` thành mặc định; debug có thể chạy Gradle build trong cùng JVM và tạo side-effect/compatibility khác thực tế. Tránh đưa production secrets vào TestKit runner environment.

## 14. Publish vào local Maven repository và thử bằng consumer thật

TestKit không cần publish plugin, nhưng publish ra **file-based Maven repository** là bài kiểm tra khác: nó xác nhận plugin marker và metadata được tạo đúng để **một Gradle build độc lập** resolve ID/version.

Từ `internal-plugin-lab/plugin/`:

~~~bash
./gradlew clean check validatePlugins \
  publishAllPublicationsToLocalStagingRepository \
  --stacktrace --console=plain
~~~

PowerShell:

~~~powershell
.\gradlew.bat clean check validatePlugins publishAllPublicationsToLocalStagingRepository --stacktrace --console=plain
~~~

Plugin Development + Maven Publish tạo:
- Main `pluginMaven` publication chứa JAR implementation, metadata.
- `helloReportPluginMarkerMaven` publication cho ID `dev.example.hello-report`.
- Marker dependency trỏ đến main plugin artifact.
- File-based repository dưới `plugin/build/local-repo/`.
- Không có credential/network upload production; chỉ ghi vào thư mục build của plugin project.

### Expected Maven coordinates

~~~text
dev.example.build:internal-greeting-plugin:1.0.0
dev.example.hello-report:dev.example.hello-report.gradle.plugin:1.0.0
~~~

**Hai tọa độ khác nhau và cả hai đều quan trọng.** Nếu chỉ thấy main JAR mà marker POM thiếu, consumer `plugins { id("dev.example.hello-report") version "1.0.0" }` có thể fail plugin resolution.

### 14.1. Consumer `consumer/settings.gradle.kts`

~~~kotlin
pluginManagement {
    repositories {
        // A file-based repository produced by the sibling plugin build.
        maven {
            url = uri("../plugin/build/local-repo")
        }

        // Fallback for other external plugins, not required for lab ID.
        gradlePluginPortal()
    }
}

rootProject.name = "hello-consumer"
~~~

**`pluginManagement` phải ở Settings**, không phải `repositories { mavenCentral() }` trong consumer build script. Repository dùng để resolve **plugin marker** khác repository dùng để resolve application dependencies. Nếu file repository chưa được publish, consumer không thể lấy ID/version từ đó.

### 14.2. Consumer `consumer/build.gradle.kts`

~~~kotlin
plugins {
    base
    id("dev.example.hello-report") version "1.0.0"
}

greeting {
    salutation.set("Xin chào")
    recipient.set("Ada")
}
~~~

`base` tạo lifecycle `clean` để thực hành restore cache. Trong plugin implementation không áp Base/Java plugin vì chính task không cần chúng.

### 14.3. Dùng Wrapper của plugin build để chạy consumer

Từ `internal-plugin-lab/consumer/`, Unix/macOS:

~~~bash
../plugin/gradlew -p . generateGreeting --console=plain

# Đọc file được task tạo.
cat build/generated/greeting.txt

# Xem task registration và thuộc group documentation.
../plugin/gradlew -p . tasks --all
~~~

Windows PowerShell:

~~~powershell
..\plugin\gradlew.bat -p . generateGreeting --console=plain
Get-Content build/generated/greeting.txt
..\plugin\gradlew.bat -p . tasks --all
~~~

Expected contents file:

~~~text
Xin chào, Ada!
~~~

Gradle task console có thể kết thúc `BUILD SUCCESSFUL` sau đó; không được khẳng định `cat` sẽ in thông tin Gradle. Nếu plugin project và consumer ở hai repository trên hai máy khác, mỗi project nên có **Wrapper riêng**; dùng wrapper sibling ở đây chỉ để lab không cần tạo Wrapper thứ hai.

### 14.4. Thay configuration và chứng minh task invalidation

Đổi `recipient.set("Ada")` thành `recipient.set("Linh")` trong consumer build:

~~~kotlin
greeting {
    salutation.set("Xin chào")
    recipient.set("Linh")
}
~~~

Chạy lại `generateGreeting`. Kết quả file phải là:

~~~text
Xin chào, Linh!
~~~

Vì `recipient` là `@Input` của task, Gradle phải xử lý output tương ứng input mới — có thể execute action hoặc dùng một cache entry đã lưu đúng input mới, **không** giữ stale `Ada` report.

## 15. Một lựa chọn khác: dùng included build thay vì Maven staging

Nếu plugin chỉ phục vụ một monorepo, có thể dùng composite build thay vì xuất bản vào repository trước.

Ví dụ structure:

~~~text
monorepo/
├── settings.gradle.kts
├── build.gradle.kts
└── build-logic/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/java/... (plugin classes)
~~~

`monorepo/settings.gradle.kts` có phần:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")

    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "monorepo"
~~~

`monorepo/build-logic/build.gradle.kts` có thể dùng `java-gradle-plugin` và `gradlePlugin.plugins` tương tự plugin lab (đổi project name/group/version tùy muốn). Root/subproject `build.gradle.kts` áp plugin:

~~~kotlin
plugins {
    id("dev.example.hello-report")
}
~~~

Ở composite/included plugin build, Gradle tự tìm plugin implementation từ included build, thường **không cần khai báo version** cho plugin local này. Không cần publish marker ra Maven repo để test nội bộ monorepo.

**Đừng nhầm `includeBuild("build-logic")` với `include("build-logic")`**. Included build là một Gradle build riêng, còn `include` tạo subproject dùng chung Settings. Cấu hình `pluginManagement.includeBuild` phải được đặt sớm khi muốn resolve plugin bằng `plugins` DSL.

Khi tổ chức có nhiều repositories độc lập, binary plugin publish vào private Maven repository thường phù hợp hơn vì có version pinning và hỗ trợ rollback.

## 16. Định hướng thiết kế API extension và task khi plugin lớn lên

Lab có hai string properties, nhưng plugin nội bộ thực có thể cần:

| Nhu cầu | Gradle Provider type | Annotation ở task phù hợp |
| --- | --- | --- |
| Chuỗi, boolean, số | `Property<T>` | `@Input`. |
| Danh sách/map giá trị | `ListProperty<T>`/`MapProperty<K,V>` | `@Input` nếu là serializable values. |
| File đầu vào | `RegularFileProperty` | `@InputFile` và `@PathSensitive`. |
| Thư mục đầu vào | `DirectoryProperty`/`ConfigurableFileCollection` | `@InputDirectory`/`@InputFiles`. |
| File output | `RegularFileProperty` | `@OutputFile`. |
| Thư mục output | `DirectoryProperty` | `@OutputDirectory`. |
| Compile/runtime classpath | `ConfigurableFileCollection` | `@Classpath`, hoặc `@CompileClasspath` theo semantics. |
| Nested structured config | Managed type + `@Nested` getters | Gradle fingerprint nested annotated properties. |
| Secret không ảnh hưởng output | Provider/env/service injection với policy phù hợp | Không tự đưa secret vào artifact/cache; xem xét không cache task có external side effect. |
| Untracked execution metadata | API chuyên biệt khi thực sự không track được | Không gắn `@CacheableTask` mù. |

### Khi thêm input file

Ví dụ đoạn code **minh họa trong một task type**:

~~~java
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
public abstract RegularFileProperty getTemplateFile();
~~~

Cần imports `org.gradle.api.tasks.InputFile`, `PathSensitive`, `PathSensitivity` và `org.gradle.api.file.RegularFileProperty`. Task action phải thực sự đọc template file và dùng nó trong output, còn plugin/app consumer phải cấp default/required value. **Đây không phải file Java hoàn chỉnh**, chỉ thêm getter vào task có sẵn.

`PathSensitivity.RELATIVE` giúp không đưa absolute checkout path vào cache key khi relative file name/path có ngữ nghĩa. Không chuyển sang `PathSensitivity.NONE` bừa bãi nếu generator phụ thuộc path/name. Với classpath inputs hãy dùng `@Classpath` thay vì fingerprint mọi absolute JAR path như file thường.

### Convention cho output directory

Nếu task sinh nhiều files, dùng `@OutputDirectory DirectoryProperty` thay vì một `@OutputFile`; bảo đảm chỉ một task sở hữu directory cụ thể, không để hai tasks ghi đè `build/generated/` cùng lúc.

### Tách plugin capabilities và defaults

- Plugin có thể đăng ký task/types mà không apply Java plugin khi không cần.
- Nếu task chỉ có ý nghĩa khi `java` plugin xuất hiện, dùng `project.getPluginManager().withPlugin("java", applied -> { ... })` để react theo thời điểm apply.
- Tránh `afterEvaluate`, global mutable statics, eager `tasks.all { ... }` và `task.get()` không cần thiết; chúng làm configuration chậm và khó tương thích Configuration Cache.
- Nếu muốn áp default conventions cho nhiều modules, giữ cấu hình overrideable và document property names.
- Đừng lấy `System.getenv(...)` trực tiếp trong `@TaskAction` mà bỏ qua `@Input` tracking; hãy đưa Provider của biến môi trường vào task property ở configuration.

## 17. Những lỗi TestKit phổ biến và cách xử lý

| Lỗi/triệu chứng | Nguyên nhân thường gặp | Bước điều tra |
| --- | --- | --- |
| `Plugin [id: 'dev.example.hello-report'] was not found` trong TestKit | Plugin ID sai, metadata injection thiếu, fixture dùng `apply` kiểu khác. | Kiểm tra `gradlePlugin.plugins.id`, `implementationClass`, `withPluginClasspath()` và `pluginUnderTestMetadata`. |
| `InvalidPluginMetadataException` | `plugin-under-test-metadata.properties` không có trên test runtime classpath. | Dùng `java-gradle-plugin`, đúng test source set/task, không xóa metadata task. |
| `NoClassDefFoundError` khi apply | Thiếu dependency/Gradle API version không tương thích. | `dependencies`, main/test runtime classpath, Gradle version matrix. |
| `Cannot create instance of abstract type` | Managed extension/task không có đúng property getter, constructor service injection sai. | So Gradle managed types docs; dùng abstract getters và `ObjectFactory` đúng. |
| `validatePlugins` cảnh báo missing annotation | Getter chưa được đánh dấu input/output/internal hoặc dùng annotation sai. | Đánh dấu đúng `@Input`/`@OutputFile`/`@Nested`, không blanket `@Internal`. |
| `TaskOutcome.SUCCESS` test đầu tiên không ổn định | Shared cache đã warm hoặc output fixture không sạch. | `@TempDir` mới, `--no-build-cache`; tránh assert log exact. |
| Test `secondRunIsUpToDate` báo SUCCESS | Input/output/task implementation thay đổi giữa hai runs hoặc output bị xóa/sửa. | Giữ fixture/runner args ổn định, debug `--info`. |
| Test báo `FROM_CACHE` dù kỳ vọng `SUCCESS` | Build Cache bật và có cache entry. | Tắt Build Cache cho test outcome deterministic. |
| Extension override không đổi report | Plugin gọi `extension.getX().get()` sớm hoặc task không map Provider. | Dùng `task.getX().set(extension.getX())`. |
| Task chạy ở configuration | File IO đặt trong `Plugin.apply`/task registration block. | Chuyển IO vào `@TaskAction`. |
| Task không cacheable | Không có `@CacheableTask` hoặc output/input validation fail. | `validatePlugins`, `--info`, inspect output ownership. |
| Configuration Cache fails | Task action dùng `Project`, captured state hoặc unsupported APIs. | Đọc configuration cache report, dùng task properties/Provider. |
| Unit test pass nhưng consumer fail | Plugin marker thiếu, repository sai hoặc phiên bản không được publish. | Test local Maven publishing và độc lập consumer Plugin DSL. |
| `generateGreeting` task không xuất hiện | Plugin chưa apply ở project mục tiêu hoặc ID khác. | `./gradlew :module:tasks --all`, kiểm tra `plugins` block. |
| `greeting { }` unresolved reference ở Kotlin DSL | Plugin apply bằng legacy `apply(plugin = ...)` khiến accessor không được sinh đúng, hoặc plugin chưa resolve. | Dùng Plugin DSL `plugins { id(...) }`; nếu legacy apply, dùng `extensions.configure<GreetingExtension>` với import/classpath. |
| `publish...ToLocalStagingRepository` không tồn tại | Thiếu `maven-publish` hoặc repository/publication names khác. | `./gradlew tasks --all`, kiểm tra `gradlePlugin` và Maven Publish. |
| Plugin marker có nhưng implementation JAR thiếu | Publication main sai/không được tạo. | Kiểm tra `pluginMaven`, `publishAllPublications...`, Maven dependency marker POM. |
| Consumer resolve được nhưng task file sai | Input defaults, encoding hoặc custom report path khác. | Inspect actual file, TestKit behavior assertions, Gradle task inputs. |
| Local tests chạy mà CI không | JDK/Gradle/OS dependency, network, Gradle User Home. | Pin Wrapper/JDK, test compatibility, avoid machine-specific paths. |

**Cách gỡ lỗi có hệ thống:**

~~~bash
./gradlew test --stacktrace --info
./gradlew validatePlugins --stacktrace
./gradlew pluginDescriptors pluginUnderTestMetadata
./gradlew tasks --all
./gradlew dependencies --configuration testRuntimeClasspath
~~~

Những lệnh trên chạy trong **plugin project**. `pluginDescriptors`/`pluginUnderTestMetadata` chỉ sinh metadata, không thay thế TestKit functional tests.

## 18. TestKit, plugin publishing và release pipeline

Một plugin nội bộ trở thành **build-time dependency chạy mã** trong consumer builds. Phát hành plugin có thể tác động toàn bộ CI/CD của tổ chức, nên phải kiểm soát:

1. Plugin ID dùng namespace reverse-domain do tổ chức sở hữu; tránh ID trùng core/external plugins.
2. Version cố định, có SemVer/compatibility policy; không overwrite cùng version bằng JAR khác bytes.
3. Thử tests unit, TestKit functional, `validatePlugins` và local Maven consumer.
4. Kiểm tra Gradle compatibility matrix/Java runtime compatibility.
5. Pin Gradle Wrapper/JDK và versions JUnit/third-party plugin dependencies.
6. Chạy tests với `--configuration-cache` nếu quảng bá hỗ trợ.
7. Chạy cache correctness tests cho những tasks có `@CacheableTask`.
8. Chỉ publish từ protected tag/branch CI job, không cấp release credentials cho PR.
9. Cấu hình repository authentication bằng typed credentials/Gradle Providers hoặc short-lived tokens; không commit passwords.
10. Tách local staging và production Maven repository, kiểm tra plugin marker/main artifacts.
11. Consumer project nên pin plugin version; thử upgrade trên canary trước rollout rộng.
12. Lưu changelog, deprecation policy, compatibility notes và rollback command.
13. Theo dõi plugin resolution errors và Gradle deprecations sau release.
14. Dùng dependency verification và review Gradle build logic/plugin JAR như một phần software supply chain.

### CI mẫu: chỉ kiểm tra trên PR

~~~yaml
name: Internal Gradle plugin CI

on:
  pull_request:
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  verify-plugin:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: plugin
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - uses: gradle/actions/setup-gradle@v6

      - name: Validate and run TestKit tests
        run: ./gradlew clean check validatePlugins --stacktrace

      - name: Publish candidate to local file repository
        run: ./gradlew publishAllPublicationsToLocalStagingRepository

      - name: Archive reports on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: plugin-test-reports
          path: plugin/build/reports/tests/**
          if-no-files-found: ignore
~~~

**Giải thích:** workflow này chỉ chạy verification và local staging; **không publish production**, không có Maven token. Production release nên là workflow/job riêng chỉ chạy trên protected tags và approvals, có repository URL/credential policy, checksum/provenance và immutable version enforcement. Runner release không nên dùng chung Gradle User Home/caches với untrusted PR.

Với plugin published Maven, task `publishAllPublicationsToLocalStagingRepository` dùng đúng local repository; khi thêm remote repository, tránh gọi aggregate `publish` trong PR vì có thể chạm nhiều endpoints.

## 19. So sánh API thiết kế tốt và phản ví dụ

| Chỗ cần quyết định | Cách nên làm | Phản ví dụ |
| --- | --- | --- |
| Đăng ký task | `tasks.register(...)`. | `tasks.create(...)` khởi tạo eager. |
| Defaults | `Property.convention(...)`. | `Property.set(...)` quá sớm làm khó override. |
| Map extension→task | `task.getX().set(extension.getX())`. | `task.getX().set(extension.getX().get())` lúc configuration. |
| File output | `layout.buildDirectory.file(...)`. | Hard-coded absolute `/tmp/...` hay source tree. |
| Work timing | `@TaskAction`. | Files.writeString trong `apply`. |
| Input declaration | `@Input`/`@InputFile`/... đầy đủ. | Input đọc ngầm từ env/mạng/clock. |
| Caching | `@CacheableTask` khi deterministic. | Cache task deploy/email/publish có side effects. |
| Test logic | JUnit unit tests. | Chỉ println rồi đọc log thủ công. |
| Test plugin contract | TestKit `GradleRunner`. | Chỉ khởi tạo Plugin class bằng `new` rồi cho rằng Gradle DSL hoạt động. |
| Test plugin resolution | Publish marker+main và independent consumer. | Chỉ chạy TestKit injected plugin classpath. |
| Test CC | Hai invocation cùng task graph với `--configuration-cache`. | Một lần store rồi kết luận reuse pass. |
| Plugin release | Protected job + version pinning. | Untrusted PR push shared plugin repository. |

### Ba loại test không thể thay nhau

**Unit test:** `GreetingTextTest` chứng minh định dạng string và validation.

**Functional TestKit:** `HelloReportPluginFunctionalTest` chứng minh Gradle dùng plugin ID, extension, task action, outputs/outcomes.

**Published-consumer test:** `consumer` chứng minh main JAR + marker POM cùng repository được resolve bằng Plugin DSL như repository khác thực sự dùng.

Một hệ thống production nên có cả ba, và bổ sung compatibility matrix cho Gradle/JDK versions được hỗ trợ.

## 20. Checklist tự kiểm tra trước khi phát hành plugin

- [ ] Plugin ID thuộc namespace nội bộ, không trùng.
- [ ] `implementationClass` đúng package/class và JAR descriptor tồn tại.
- [ ] Có extension managed properties với defaults phù hợp.
- [ ] Consumer override properties mà không cần truy cập internals.
- [ ] Plugin `apply` chỉ configure/register, không chạy IO.
- [ ] Tasks đăng ký lazy bằng `TaskProvider`.
- [ ] Task inputs/outputs được annotation đầy đủ.
- [ ] `@CacheableTask` chỉ dùng khi task deterministic/relocatable.
- [ ] Output path thuộc build directory và không overlap với tasks khác.
- [ ] Unit tests kiểm tra logic thuần.
- [ ] TestKit fixture tạm có `settings.gradle.kts`/`build.gradle.kts`.
- [ ] TestKit dùng `withPluginClasspath()` đúng conventions.
- [ ] Functional tests kiểm tra default, override, up-to-date và invalid input.
- [ ] `validatePlugins` không báo property annotation issues.
- [ ] TestKit classpath metadata được tạo tự động.
- [ ] Test Configuration Cache store/reuse nếu quảng bá tương thích.
- [ ] Test Build Cache restore sau clean và đúng output bytes.
- [ ] Main Maven plugin artifact được publish vào local staging.
- [ ] Plugin marker publication được publish cùng main.
- [ ] Independent consumer resolve và apply ID/version được.
- [ ] `Gradle Wrapper` và JDK 17 được pin/validated.
- [ ] Plugin source và transitive dependencies được review bảo mật.
- [ ] CI PR không có credentials publish production.
- [ ] SemVer/deprecation/rollback policy rõ ràng.
- [ ] Không dùng `mavenLocal()` làm bằng chứng duy nhất cho remote consumer.
- [ ] Release artifact immutable và có provenance/signature nếu policy yêu cầu.

## 21. Bài tập mở rộng và câu hỏi tự kiểm tra

**Bài tập A — Thêm tham số output file:** đưa `RegularFileProperty getOutputFile()` vào extension, cho default từ `layout.buildDirectory.file(...)`, map tới task output property. Kiểm tra TestKit khi consumer đổi output path. Không hard-code absolute paths.

**Bài tập B — Thêm template input file:** đưa `RegularFileProperty getTemplateFile()` vào task với `@InputFile`/`@PathSensitive(RELATIVE)`, khai báo nguồn input trong extension/consumer, assert nội dung output đổi khi template đổi. Test relocate checkout path nhưng giữ relative path.

**Bài tập C — Config Cache:** thêm TestKit test gọi `--configuration-cache` hai lần và kiểm tra `Reusing configuration cache.`. Tìm và sửa một ví dụ intentionally dùng `getProject()` từ task action để hiểu report.

**Bài tập D — Plugin version 1.1:** thêm property optional có default an toàn, giữ compatible DSL. Tạo local staging v1.1.0 và consumer canary pin version mới; so JAR/marker, không overwrite 1.0.0.

Câu hỏi tự kiểm tra:

1. Khi nào nên dùng binary plugin thay vì task trong `build.gradle.kts`?
2. `Plugin<Project>` và `Plugin<Settings>` có cùng target không?
3. Sự khác nhau giữa plugin ID, declaration name, task name và Maven coordinates?
4. `java-gradle-plugin` tự làm những gì cho API/descriptor/TestKit?
5. Vì sao `maven-publish` cần kết hợp để có plugin marker publication?
6. `GreetingExtension` là một managed abstract type bằng cách nào?
7. `Property.convention(...)` khác `Property.set(...)` ra sao?
8. Vì sao không gọi `extension.getRecipient().get()` sớm trong `apply`?
9. `tasks.register(...)` khác `tasks.create(...)` như thế nào?
10. Tại sao `@Input` đặt ở task chứ không chỉ extension?
11. `@OutputFile` giúp Gradle thực hiện những tối ưu nào?
12. `@CacheableTask` có bảo đảm mọi task được `FROM-CACHE` không?
13. Vì sao task có side effects trên network không nên output-cache tùy tiện?
14. `UP-TO-DATE` có đồng nghĩa `FROM-CACHE` không?
15. `GradleRunner.withPluginClasspath()` lấy metadata từ đâu?
16. Vì sao TestKit fixture dùng `plugins { id(...) }` trong bài?
17. `GradleRunner.buildAndFail()` dùng khi nào?
18. `TaskOutcome.SUCCESS` và `UP_TO_DATE` khác nhau ở lần chạy thứ hai?
19. TestKit có kiểm tra được publication marker từ một Maven repository chưa?
20. Vì sao cần independent consumer test?
21. `pluginManagement.repositories` khác `repositories` của application project thế nào?
22. Plugin marker POM dùng coordinate có cấu trúc gì?
23. Gradle Configuration Cache khác task output Build Cache ở điểm nào?
24. Với Java class dùng Gradle APIs, vì sao không chỉ chạy `javac` mà thiếu classpath?
25. `@PathSensitive(RELATIVE)` phù hợp với loại input nào?
26. Vì sao output directory bị overlap là rủi ro caching?
27. Nếu `validatePlugins` báo missing annotation, có nên gắn `@Internal` cho hết không?
28. Khi nâng plugin version, cần kiểm tra Gradle/JDK compatibility và consumer ở đâu?
29. Nếu một plugin version được dùng bởi hàng chục CI pipelines, vì sao release credentials phải được bảo vệ?
30. Ba cấp kiểm thử unit, TestKit và published-consumer có vai trò riêng gì?

## 22. Tài liệu chính thức

- [Gradle — Binary Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_binary.html): `Plugin<Project>`, extension, custom tasks, lazy mapping và conventions.
- [Gradle — Implementation Options for Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): script/plugin buildSrc/included build/binary plugins.
- [Gradle — Java Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): `java-gradle-plugin`, `pluginDescriptors`, `pluginUnderTestMetadata`, `validatePlugins`, main/marker Maven publication.
- [Gradle — Testing Build Logic with TestKit](https://docs.gradle.org/current/userguide/test_kit.html): `GradleRunner`, `withPluginClasspath()`, build fixture, Gradle version matrix.
- [Gradle — Testing Plugins](https://docs.gradle.org/current/userguide/testing_gradle_plugins.html): unit vs functional tests, source set layouts và TestKit.
- [Gradle — Best Practices for Testing](https://docs.gradle.org/current/userguide/best_practices_testing.html): custom plugin functional tests.
- [Gradle — Preparing to Publish Plugins](https://docs.gradle.org/current/userguide/preparing_to_publish.html): local staging Maven repository và independent consumer.
- [Gradle — Maven Publish](https://docs.gradle.org/current/userguide/publishing_maven.html): publication tasks và repository models.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): `@CacheableTask`, output caching, correctness.
- [Gradle — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): annotated task inputs/outputs và up-to-date.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): configuration reuse và task action restrictions.
- [Gradle — Creating and Registering Tasks](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): lazy task registration/Provider graph.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Property`, `Provider`, conventions và lazy task values.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): `includeBuild` cho local plugin resolution.
- [Gradle — Gradle Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html): controlled Gradle version và distribution verification.
