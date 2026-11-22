# Đăng ký task lười và kết nối extension với đầu vào task trong Gradle Plugin

## 1. Bài toán của người phát triển plugin

Khi một dự án Java cần thêm khả năng riêng cho build — sinh resource, tạo file cấu hình mẫu, đóng gói metadata, chạy bộ kiểm tra, tạo báo cáo hoặc chuẩn hóa compiler options — cách ban đầu thường là viết một task trong `build.gradle.kts`. Khi nhiều dự án phải dùng cùng hành vi, logic ấy nên được đóng gói thành **Gradle plugin**.

Một plugin tốt không chỉ đăng ký được task. Nó cần trả lời ba câu hỏi:

1. **Khi nào Gradle cần tạo/cấu hình task?** Nếu project chỉ gọi `help`, plugin không nên tự mở file, resolve configurations hoặc tạo outputs không liên quan.
2. **Người dùng cấu hình plugin qua đâu?** Các giá trị như tên ứng dụng, thông điệp, đường dẫn output, tool version nên có một **extension typed** thay vì hardcode.
3. **Giá trị từ extension đi vào task ra sao?** Cần dùng `Property<T>`, `Provider<T>` và `RegularFileProperty` để giữ lazy evaluation, tracking input/output và Configuration Cache compatibility.

Mô hình đúng:

~~~text
plugins { id("org.example.greeting") }
                 |
                 v
          GreetingPlugin.apply(Project)
                 |
                 +--> create extension "greeting"
                 |       |
                 |       +--> prefix: Property<String>
                 |       +--> recipient: Property<String>
                 |       +--> outputFile: RegularFileProperty
                 |
                 +--> tasks.register("generateGreeting", GenerateGreetingTask)
                 |       |
                 |       +--> @Input prefix <- extension.prefix
                 |       +--> @Input recipient <- extension.recipient
                 |       +--> @OutputFile outputFile <- extension.outputFile
                 |
                 +--> tasks.register("printGreeting", PrintGreetingTask)
                         |
                         +--> @InputFile <- generateGreeting.outputFile
                                  |
                                  +--> Gradle suy ra dependency đến producer
~~~

Đây là **data flow**. Task consumer cần producer output; Gradle có thể tự lên lịch producer trước. Plugin không phải đọc extension giá trị sớm, cũng không cần chạy generator trong `apply`.

**Kết quả mong đợi:** gọi `./gradlew -q printGreeting` trên ví dụ Java 17 bên dưới in `Greeting file: Hello, Ada!`, tự sinh file `build/generated/greetings/greeting.txt`. Người dùng có thể đổi `greeting.recipient`, Gradle sẽ cập nhật đúng input cho task, không phải sửa mã plugin.

## 2. Phân biệt task registration, configuration và execution

Gradle có ba giai đoạn khái niệm: initialization, configuration và execution. Khi plugin được áp dụng trong configuration phase, phương thức `apply(Project)` thường chạy để **đăng ký mô hình build**. Nó **không nên thực hiện công việc của task**.

| Việc | Thời điểm hợp lý | Ví dụ |
| --- | --- | --- |
| Tạo extension | Configuration | `extensions.create("greeting", ...)` |
| Khai báo giá trị mặc định | Configuration, qua lazy property | `recipient.convention("Gradle")` |
| Đăng ký task | Configuration với lazy API | `tasks.register("generateGreeting", ...)` |
| Nối extension vào task properties | Lazy task configuration action | `task.getRecipient().set(extension.getRecipient())` |
| Nối output producer vào input consumer | Lazy task configuration | `consumer.getInputFile().set(generator.flatMap(...))` |
| Đọc/ghi file thật | Task execution | Method có `@TaskAction` |
| Đọc input property cụ thể | Khi task cần thực thi | `getRecipient().get()` trong `@TaskAction` |
| Kiểm tra task up-to-date | Gradle task execution engine | `@Input` + `@OutputFile` |
| Lưu/reuse task graph | Configuration Cache khi bật và tương thích | `--configuration-cache` |

### 2.1. register khác create

**Ưu tiên:**

~~~kotlin
val taskProvider = tasks.register("hello")
~~~

`register` trả về `TaskProvider`; Gradle chỉ cần realize/configure task khi có lý do phù hợp, như task được chọn vào graph hoặc một API cần nó. Không phải mọi task được đăng ký đều bị cấu hình ngay.

**Tránh khi không cần:**

~~~kotlin
val task = tasks.create("hello")
~~~

`create` tạo/cấu hình task eagerly ngay lúc gọi. Trong build có hàng trăm modules và nhiều plugins, các task không được gọi cũng góp thêm chi phí cấu hình. Không giả định một lệnh `./gradlew help` phải tạo mọi task của mọi plugin.

### 2.2. Không dùng task graph thứ tự như data flow

Một plugin có producer viết file và consumer đọc file phải mô hình hóa quan hệ qua **đầu ra và đầu vào**. Nếu chỉ viết `consumer.mustRunAfter(generator)`, Gradle **không tự đưa generator vào graph** nếu nó chưa được yêu cầu bởi dependency khác. Nếu consumer nhận `Provider<RegularFile>` của producer output, Gradle có cả dữ liệu và thông tin task tạo ra dữ liệu ấy.

## 3. TaskProvider, Property và Provider có vai trò gì?

| API | Kiểu | Đặc điểm |
| --- | --- | --- |
| `TaskProvider<T>` | Tham chiếu đến task | Task có thể chưa được realize; dùng `configure`, `map`, `flatMap` |
| `Property<T>` | Mutable lazy property | `set(T)`, `set(Provider<T>)`, `convention(...)` |
| `Provider<T>` | Read-only value provider | `map`/`flatMap`/`zip` và `get` khi thật sự cần |
| `RegularFileProperty` | Lazy file property | Giữ path file và producer metadata |
| `DirectoryProperty` | Lazy directory property | Output/input directory typed |
| `ListProperty<T>` | Lazy list property | Reusable lists, có thể `add`/`addAll` |
| `MapProperty<K,V>` | Lazy map property | Typed key-value configuration |
| `ConfigurableFileCollection` | File collection | Classpath, many inputs, built-by provenance |
| `ProviderFactory` | Factory cho nguồn values | `gradleProperty`, `environmentVariable`, `systemProperty`, `provider` |
| `ProjectLayout` | Layout directories/files | `layout.buildDirectory.file(...)` |

**`Property<T>` là mutable provider**: người dùng có thể set, plugin có thể đặt convention, task có thể nhận provider của property. `Provider<T>` cho consumer đọc giá trị về sau nhưng không cho chỉnh trực tiếp. Tránh đọc giá trị với `get()` quá sớm chỉ để chép vào một String.

### 3.1. Vì sao String thông thường là chưa đủ?

Sai kiểu:

~~~java
String name = extension.getRecipient().get();
task.getRecipient().set(name);
~~~

Nếu thực hiện khi `apply`/task configuration, biểu thức đã **chốt giá trị sớm**. Người dùng có thể định nghĩa `greeting { recipient.set("Ada") }` sau khi plugin được apply; code trên có thể đọc default trước khi build script cấu hình xong. Nó cũng biến provider relationship thành String thường, khó truy vết input nguồn.

Tốt hơn:

~~~java
task.getRecipient().set(extension.getRecipient());
~~~

Dòng này không đọc nội dung hiện tại mà **nối hai properties**. Khi task chạy, nó nhận giá trị đã được người dùng cấu hình. Gradle có thể track input qua `@Input`.

### 3.2. Ưu tiên typed properties

Một file output không nên được cấu hình bằng arbitrary String rồi cộng đường dẫn thủ công, ví dụ `project.getBuildDir() + "/..."`. Dùng `RegularFileProperty` nối với `ProjectLayout` để giữ build-directory relocation và provenance tốt hơn.

## 4. Thiết kế plugin: extension là cấu hình, task là hành vi

Một thiết kế nhỏ có ba thành phần:

1. **GreetingExtension**: nơi người dùng khai báo `prefix`, `recipient` và `outputFile`.
2. **GenerateGreetingTask**: task có `@Input`/`@OutputFile`; thực hiện tạo file trong `@TaskAction`.
3. **GreetingPlugin**: được Gradle gọi khi áp dụng plugin; tạo extension, đặt conventions, đăng ký tasks và nối properties.

Thêm một consumer task **PrintGreetingTask** để minh họa cách nối output file producer thành input file consumer, không cần `dependsOn` thủ công.

**Phân biệt rõ:**

- Extension **không phải task**. Người dùng cấu hình qua `greeting { ... }`; nó không chứa work action.
- Task **không nên hỏi Project hoặc extension container** trong `@TaskAction`. Mọi dữ liệu cần thiết phải nằm trong annotated task properties.
- Plugin `apply` **không được tạo file** hoặc khởi chạy external process. Nó chỉ thiết lập build model.
- Một task có thể có các defaults riêng, nhưng trong ví dụ defaults được đặt ở extension để người dùng có một DSL thống nhất.

## 5. Cấu trúc demo hoàn chỉnh Java 17+

Ta dùng một **included build `build-logic`** để phát triển binary plugin viết bằng Java; root build là project tiêu thụ plugin. Đây là cách tổ chức giúp build logic có ranh giới riêng. Không cần publish plugin lên Plugin Portal để chạy demo.

~~~text
lazy-plugin-demo/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── src/
│   └── main/
│       └── java/
│           └── demo/
│               └── GreetingReader.java
└── build-logic/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/
        ├── main/
        │   └── java/
        │       └── org/
        │           └── example/
        │               └── gradle/
        │                   ├── GreetingExtension.java
        │                   ├── GenerateGreetingTask.java
        │                   ├── PrintGreetingTask.java
        │                   └── GreetingPlugin.java
        └── test/
            └── java/
                └── org/
                    └── example/
                        └── gradle/
                            └── GreetingPluginFunctionalTest.java
~~~

Các file `src/test` được thêm ở phần kiểm thử TestKit; muốn chạy các task chính trước, chưa nhất thiết phải tạo file test. Cần **Gradle Wrapper thật** đã được tạo bằng Gradle version tương thích Java 17 và `java-gradle-plugin`, không thể chỉ tạo một script tên `gradlew` rỗng.

### 5.1. Lựa chọn bản Gradle/JDK

Ví dụ dùng Java language level 17 và public Gradle APIs như `Plugin<Project>`, `TaskProvider`, `Property`, `RegularFileProperty`, `DefaultTask` và `@TaskAction`. Dùng Gradle Wrapper hiện hành tương thích JDK 17 và các APIs này. Gradle 9.x yêu cầu JVM chạy Gradle phù hợp với compatibility matrix; không suy chỉ từ “có JDK 17” rằng mọi plugin trong một build cũ đều tương thích.

Plugin code có thể **biên dịch bằng Gradle Java toolchain 17**, nhưng nó dùng Gradle API nên **không thể chỉ biên dịch toàn bộ plugin bằng `javac` độc lập mà không có Gradle API trên classpath**. Phần 14 có một chương trình Java 17 đọc output file để bạn kiểm tra bằng `javac`/`java` thuần JDK.

## 6. Root settings.gradle.kts: đăng ký plugin build

**File `settings.gradle.kts`:**

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "lazy-plugin-demo"
~~~

`pluginManagement.includeBuild` đưa plugin build vào **plugin resolution** đủ sớm cho root `plugins { id("org.example.greeting") }`. Nó khác với `include(":build-logic")`: cái sau sẽ biến thư mục thành một subproject của root và **không tự đăng ký plugin marker/implementation theo cùng cơ chế**.

Ở demo, plugin nằm local nên không cần external plugin repository. Nếu dự án thật dùng plugins được publish từ plugin portal hoặc internal registry, đặt `pluginManagement.repositories` tương ứng trong root settings. Included `build-logic` vẫn có settings riêng.

## 7. Included build-logic/settings.gradle.kts

**File `build-logic/settings.gradle.kts`:**

~~~kotlin
rootProject.name = "greeting-build-logic"
~~~

Đây là Gradle build riêng, không phải Java application module. Nó giữ plugin implementation/test và có thể được Gradle build khi root cần resolve local plugin.

Không đặt `includeBuild("build-logic")` bên trong settings của chính `build-logic`; làm vậy có thể tạo recursion/cycle. Cũng không phải root `gradle/libs.versions.toml` được tự động chia sẻ cho included build; nếu cần catalog, khai báo/import một cách chủ đích trong settings của build-logic.

## 8. Included build-logic/build.gradle.kts

**File `build-logic/build.gradle.kts`:**

~~~kotlin
plugins {
    `java-gradle-plugin`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

gradlePlugin {
    plugins {
        create("greetingPlugin") {
            id = "org.example.greeting"
            implementationClass = "org.example.gradle.GreetingPlugin"
        }
    }
}
~~~

`java-gradle-plugin`:

- Áp dụng phần Java cần để compile plugin implementation.
- Cung cấp Gradle API dependency cần cho Java plugin class.
- Hỗ trợ khai báo plugin ID và implementation class.
- Sinh plugin descriptors để Gradle resolve plugin bằng ID, không cần viết thủ công file `META-INF/gradle-plugins/...properties` trong demo.
- Tích hợp công cụ kiểm thử plugin/TestKit khi được cấu hình.

`gradlePlugin.plugins.create("greetingPlugin")` là **định danh nội bộ trong build logic DSL**; người dùng apply **plugin ID** `org.example.greeting`, không dùng tên `greetingPlugin`.

**Không có third-party dependency runtime** cho plugin demo, nên không cần Maven repository để compile các classes chính. Nếu thêm JUnit để test plugin ở phần sau, build-logic sẽ cần `repositories { mavenCentral() }` hoặc mirror được phê duyệt.

## 9. GreetingExtension.java: managed extension có typed properties

**File `build-logic/src/main/java/org/example/gradle/GreetingExtension.java`:**

~~~java
package org.example.gradle;

import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;

public interface GreetingExtension {
    Property<String> getPrefix();

    Property<String> getRecipient();

    RegularFileProperty getOutputFile();
}
~~~

Đây là một **Gradle-managed extension interface**. Khi `project.getExtensions().create("greeting", GreetingExtension.class)` được gọi, Gradle tạo implementation phù hợp cho managed getters. Không tự viết fields `String` và boilerplate setters chỉ để có typed DSL.

Điều thú vị: interface không có constructor, không khởi tạo `Property` bằng `new`. Gradle cung cấp implementations cho những getters thuộc managed properties model. Người dùng có thể viết Kotlin DSL:

~~~kotlin
greeting {
    prefix.set("Hello")
    recipient.set("Ada")
    outputFile.set(layout.buildDirectory.file("generated/greetings/greeting.txt"))
}
~~~

Đây là snippet cấu hình **trong root consumer `build.gradle.kts`**, sau khi plugin được apply. Các values sẽ được nối tới task inputs bằng provider, không bị đọc sớm.

### 9.1. Extension có cần @Input không?

**Không.** Annotated inputs/outputs dùng cho **task Gradle sẽ thực thi**. Extension là nơi người dùng cấu hình. Task mới là nơi `@Input`, `@InputFile` và `@OutputFile` giúp Gradle thực hiện up-to-date checks và caching.

Extension có thể có validation/conventions; nhưng nếu task đọc extension trực tiếp ở execution phase, Gradle không tự hiểu đó là một task input hợp lệ. Phải nối extension property vào task property đã annotate.

## 10. GenerateGreetingTask.java: task tạo file có hợp đồng I/O

**File `build-logic/src/main/java/org/example/gradle/GenerateGreetingTask.java`:**

~~~java
package org.example.gradle;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

@CacheableTask
public abstract class GenerateGreetingTask extends DefaultTask {
    @Input
    public abstract Property<String> getPrefix();

    @Input
    public abstract Property<String> getRecipient();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();

    @TaskAction
    public void generate() throws IOException {
        String text = getPrefix().get()
                + ", " + getRecipient().get() + "!\n";

        Path output = getOutputFile().get().getAsFile().toPath();
        Files.createDirectories(output.getParent());
        Files.writeString(output, text, StandardCharsets.UTF_8);
    }
}
~~~

Đây là **task type Java hoàn chỉnh**, được compile trong plugin build. Chưa có task instance cho đến khi plugin đăng ký. Gradle có thể tạo managed implementations cho abstract getters trong task class.

Giải thích chi tiết:

- `extends DefaultTask`: task thuộc Gradle model.
- `@Input Property<String> getPrefix()`: giá trị prefix ảnh hưởng nội dung file.
- `@Input Property<String> getRecipient()`: tên người nhận cũng ảnh hưởng output.
- `@OutputFile RegularFileProperty getOutputFile()`: Gradle biết file chính xác mà task tạo.
- `@TaskAction`: method thực hiện I/O **chỉ khi Gradle execute task**.
- `getPrefix().get()` và `getRecipient().get()` nằm **trong task action**, khi property đã được Gradle cấu hình đầy đủ. Đây là thời điểm đọc hợp lý.
- `Files.createDirectories(...)` tạo parent directory dưới build; không đòi directory phải tồn tại trong configuration phase.
- `Files.writeString(..., UTF_8)` ghi file deterministic và newline tường minh `\n`, nên output không phụ thuộc default charset/line separator.
- `@CacheableTask` phù hợp **cho ví dụ này** vì output là hàm xác định của declared inputs và implementation, không đọc clock, random, network hay hidden files.

**Rất quan trọng:** `@CacheableTask` không phải bùa phép. Nếu generator thực tế đọc file schema, template, Git revision, tool version hoặc environment variable, bạn phải khai báo chúng thành inputs phù hợp; nếu không Build Cache có thể trả nội dung stale.

### 10.1. Vì sao không hardcode output path trong action?

Sai:

~~~java
// ANTI-PATTERN: khong khai bao output va doc Project trong task action.
Path out = getProject().getRootDir().toPath()
        .resolve("generated/message.txt");
~~~

Task action truy cập `Project` là một vấn đề với Configuration Cache, và output file không được khai báo khiến Gradle khó theo dõi tính đúng của task. Dùng `@OutputFile`/`RegularFileProperty` như demo.

### 10.2. Vì sao không dùng String field?

Sai:

~~~java
private String recipient = "Gradle";
~~~

và task action đọc field này mà không có `@Input`. Gradle có thể không biết khi tên thay đổi. Dùng managed `Property<String>` và annotated getters để value tham gia input snapshots.

## 11. PrintGreetingTask.java: task nhận output của producer

**File `build-logic/src/main/java/org/example/gradle/PrintGreetingTask.java`:**

~~~java
package org.example.gradle;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.tasks.InputFile;
import org.gradle.api.tasks.PathSensitive;
import org.gradle.api.tasks.PathSensitivity;
import org.gradle.api.tasks.TaskAction;

public abstract class PrintGreetingTask extends DefaultTask {
    @InputFile
    @PathSensitive(PathSensitivity.NONE)
    public abstract RegularFileProperty getInputFile();

    @TaskAction
    public void print() throws IOException {
        String content = Files.readString(
                getInputFile().get().getAsFile().toPath(),
                StandardCharsets.UTF_8
        ).stripTrailing();

        getLogger().quiet("Greeting file: " + content);
    }
}
~~~

Đây là **consumer task**, có `@InputFile` để Gradle biết nó đọc file nào. `@PathSensitive(PathSensitivity.NONE)` có nghĩa nội dung file quan trọng, còn path file không cần góp vào fingerprint nếu task chỉ đọc bytes/text. Nếu logic sử dụng tên/đường dẫn file để tạo output, cần chọn normalization khác phù hợp.

Task này chỉ in thông tin ra log, **không khai báo một output artifact**. Vì thế không gắn `@CacheableTask`: không thể coi việc đã in ở lần trước là một output file còn trên disk. Khi task được chạy, hành động in thường thực thi mỗi lượt, còn producer có thể `UP-TO-DATE`/`FROM-CACHE`.

**Vì sao dùng logger `quiet`?** Khi chạy `./gradlew -q printGreeting`, mức log QUIET vẫn hiển thị dòng quan trọng từ action. Nếu dùng `logger.lifecycle` thì `-q` thường ẩn dòng đó. Đừng lạm dụng println cho dữ liệu nhạy cảm; task này chỉ in một lời chào mẫu.

## 12. GreetingPlugin.java: đăng ký hai task bằng register và nối properties

**File `build-logic/src/main/java/org/example/gradle/GreetingPlugin.java`:**

~~~java
package org.example.gradle;

import org.gradle.api.Plugin;
import org.gradle.api.Project;
import org.gradle.api.tasks.TaskProvider;

public final class GreetingPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        GreetingExtension greeting = project.getExtensions()
                .create("greeting", GreetingExtension.class);

        greeting.getPrefix().convention("Hello");
        greeting.getRecipient().convention(
                project.getProviders()
                        .gradleProperty("greetingRecipient")
                        .orElse("Gradle")
        );
        greeting.getOutputFile().convention(
                project.getLayout().getBuildDirectory()
                        .file("generated/greetings/greeting.txt")
        );

        TaskProvider<GenerateGreetingTask> generator =
                project.getTasks().register(
                        "generateGreeting",
                        GenerateGreetingTask.class,
                        task -> {
                            task.setGroup("greeting");
                            task.setDescription(
                                    "Generate a greeting text file"
                            );

                            task.getPrefix().set(
                                    greeting.getPrefix()
                            );
                            task.getRecipient().set(
                                    greeting.getRecipient()
                            );
                            task.getOutputFile().set(
                                    greeting.getOutputFile()
                            );
                        }
                );

        project.getTasks().register(
                "printGreeting",
                PrintGreetingTask.class,
                task -> {
                    task.setGroup("greeting");
                    task.setDescription(
                            "Print the text produced by generateGreeting"
                    );

                    task.getInputFile().set(
                            generator.flatMap(
                                    GenerateGreetingTask::getOutputFile
                            )
                    );
                }
        );
    }
}
~~~

Đây là phần trung tâm của bài. Phân tích từng bước:

1. `project.getExtensions().create("greeting", ...)` thêm DSL extension được người dùng cấu hình.
2. `convention("Hello")` đặt default prefix; `convention(gradleProperty(...).orElse("Gradle"))` đọc giá trị project property **lazily** nếu người dùng không set một value khác.
3. `outputFile.convention(layout.buildDirectory.file(...))` chọn file output dưới build directory theo Provider.
4. `tasks.register(..., GenerateGreetingTask.class, task -> ...)` đăng ký generator mà không bắt buộc tạo/execute task ngay lập tức.
5. `task.getPrefix().set(greeting.getPrefix())` giữ provider chain từ extension tới annotated task input; cùng nguyên tắc với recipient và outputFile.
6. `TaskProvider<GenerateGreetingTask> generator` là handle mà producer chưa cần được realize.
7. `tasks.register("printGreeting", ...)` đăng ký consumer lazily.
8. `generator.flatMap(GenerateGreetingTask::getOutputFile)` lấy output provider từ producer task, không gọi `generator.get()`.
9. `consumer.getInputFile().set(outputProvider)` chuyển **cả giá trị file và producer metadata** đến input consumer; Gradle có thể suy ra quan hệ producer–consumer.
10. **Không có `get()` trên extension values trong `apply`** và không đọc file trong task registration action.

**Đồ thị được tạo khi yêu cầu `printGreeting`:**

~~~text
extension.greeting.prefix --------+
                                  +--> generateGreeting @Input
extension.greeting.recipient -----+                 |
extension.greeting.outputFile --> @OutputFile       |
                                                  v
                                          greeting.txt
                                                  |
                                                  v
                                   printGreeting @InputFile
                                                  |
                                                  v
                                        logger.quiet(...)
~~~

Khi gọi `generateGreeting`, chỉ producer cần thực thi. Khi gọi `printGreeting`, consumer có dependency ngầm vào producer vì input nối từ output provider. Khi gọi `help`, không task action nào được chạy chỉ vì plugin đã apply.

## 13. Root build.gradle.kts: người dùng cấu hình extension

**File `build.gradle.kts` ở root `lazy-plugin-demo`:**

~~~kotlin
plugins {
    id("org.example.greeting")
}

greeting {
    prefix.set("Hello")
    recipient.set("Ada")
}
~~~

**Không cần khai báo task bằng tay**. Plugin tạo `generateGreeting` và `printGreeting`. Root consumer cũng không cần apply `java` nếu chỉ sử dụng các task tạo/đọc file của plugin.

`prefix.set("Hello")` trùng default để giúp người học nhìn rõ cơ chế. `recipient.set("Ada")` **ghi đè convention** vốn đọc `-PgreetingRecipient` hoặc mặc định `Gradle`. Sau khi người dùng đã explicit set recipient, `-PgreetingRecipient=X` không tự thắng explicit configuration này.

### 13.1. Đổi output path bằng extension

Nếu muốn output ở nơi khác, thêm vào cùng block:

~~~kotlin
greeting {
    prefix.set("Hello")
    recipient.set("Ada")
    outputFile.set(
        layout.buildDirectory.file("generated/custom/hello.txt")
    )
}
~~~

Đây là **phương án thay thế**, không phải một block thứ hai cần copy cùng lúc. Task `generateGreeting` và `printGreeting` đều sẽ nhận đường dẫn mới qua provider chain. Không phải sửa Java plugin class.

### 13.2. Đổi prefix

~~~kotlin
greeting {
    prefix.set("Xin chào")
    recipient.set("Lan")
}
~~~

Nếu chọn snippet thay thế này, output file sẽ là:

~~~text
Xin chào, Lan!
~~~

và `printGreeting` sẽ in `Greeting file: Xin chào, Lan!`. Không có network, locale hoặc randomness trong thuật toán, nên kết quả xác định theo values.

## 14. Chạy demo và kiểm tra kết quả bằng Java 17+

### 14.1. Chạy tasks qua Gradle Wrapper

Linux/macOS:

~~~bash
./gradlew -q printGreeting
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -q printGreeting
~~~

**Dòng từ task action:**

~~~text
Greeting file: Hello, Ada!
~~~

Khi build thành công, file dự kiến được tạo tại:

~~~text
build/generated/greetings/greeting.txt
~~~

**Nội dung chính xác của file, bao gồm newline cuối:**

~~~text
Hello, Ada!
~~~

Đoạn `text` block phía trên hiển thị một dòng nội dung; implementation ghi thêm một ký tự xuống dòng `\n`. Các warning JVM/Gradle tùy môi trường có thể xuất hiện dù bật `-q`; dòng trên là output quan trọng từ plugin.

### 14.2. Kiểm tra trực tiếp producer

~~~bash
./gradlew generateGreeting --console=plain
~~~

Lệnh này chỉ yêu cầu producer, không cần consumer `printGreeting`. Nếu inputs/outputs không đổi ở lượt chạy tiếp theo, Gradle có thể đánh dấu `generateGreeting` là `UP-TO-DATE` hoặc `FROM-CACHE` theo cấu hình Build Cache.

### 14.3. Java helper đọc chính output đã sinh

Vì mã **plugin** dùng Gradle API, nếu cần một lệnh `javac/java` thuần JDK để kiểm chứng file, tạo helper sau.

**File `src/main/java/demo/GreetingReader.java` ở root consumer:**

~~~java
package demo;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class GreetingReader {
    private GreetingReader() {
    }

    public static void main(String[] args) throws IOException {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: GreetingReader <file-path>"
            );
        }

        String text = Files.readString(
                Path.of(args[0]), StandardCharsets.UTF_8
        );
        System.out.print(text);
    }
}
~~~

Helper này không cần Gradle API. Đầu tiên tạo file bằng `generateGreeting`, sau đó biên dịch/run Java:

Linux/macOS:

~~~bash
./gradlew generateGreeting
mkdir -p out
javac --release 17 -encoding UTF-8 \
    -d out src/main/java/demo/GreetingReader.java
java -cp out demo.GreetingReader build/generated/greetings/greeting.txt
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat generateGreeting
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src\main\java\demo\GreetingReader.java
java -cp out demo.GreetingReader build\generated\greetings\greeting.txt
~~~

**Stdout chính xác của Java helper với default consumer config `Ada`:**

~~~text
Hello, Ada!
~~~

Đây là **một chương trình Java 17 độc lập** đọc kết quả plugin đã sinh; nó không phải Java implementation của plugin và không tự đăng ký Gradle task nào. `out/` do lệnh `javac` tạo là output local, khác `build/generated` do Gradle task quản lý.

### 14.4. Vì sao không tự gọi javac cho plugin code?

Các Java classes `GreetingPlugin`, `GenerateGreetingTask` và `GreetingExtension` import `org.gradle.api.*`. Nếu chạy `javac` không có Gradle API trên classpath sẽ báo `package org.gradle.api does not exist`. Đúng quy trình của plugin là `./gradlew :build-logic:build` hoặc build root áp dụng plugin, để `java-gradle-plugin` cung cấp Gradle API classpath. Dùng `javac` thuần cho helper không nhập nhằng hai loại mã nguồn này.

## 15. Phân tích lazy chain theo thời gian

Bốn thời điểm quan trọng:

**T1 — Gradle bắt đầu configuration:** plugin được apply; extension và task registration được khai báo.

**T2 — Build script của người dùng cấu hình:**

~~~kotlin
greeting {
    recipient.set("Ada")
}
~~~

Lúc này `GenerateGreetingTask` có thể vẫn chưa được realize. Extension property nhớ value mới.

**T3 — Gradle chọn task graph:** với `printGreeting`, Gradle cần resolve task inputs/dependencies; `generator.flatMap(...)` mang provenance tới producer output. Generator được scheduled trước consumer.

**T4 — Task execution:** Gradle snapshot declared inputs/outputs, so sánh up-to-date/cache, rồi gọi `@TaskAction` khi cần. Producer dùng `recipient.get()` lúc này và ghi file. Consumer đọc output file đã tồn tại.

Sơ đồ khác:

~~~text
Project configuration
  |-- create extension + defaults
  |-- register GenerateGreetingTask (lazy)
  |-- register PrintGreetingTask (lazy)
  |-- user sets greeting.recipient = "Ada"
  |
  v
Task graph for printGreeting
  |-- infer producer task from output provider
  |-- get @Input and @OutputFile metadata
  |
  v
Task execution
  |-- generateGreeting writes greeting.txt when necessary
  |-- printGreeting reads greeting.txt
~~~

**Không được hiểu sai:** lazy registration **không có nghĩa** Gradle không bao giờ cấu hình task. Nó có nghĩa task chỉ được realize/configure khi cần cho requested graph hoặc một API khác có lý do truy cập nó. Nếu một plugin khác dùng eager collection APIs, task vẫn có thể bị realize sớm.

## 16. convention, set, map và flatMap

### 16.1. convention là giá trị mặc định, set là giá trị được chọn tường minh

~~~java
greeting.getRecipient().convention("Gradle");
~~~

Nếu người dùng không set, giá trị sẽ là `Gradle`.

~~~kotlin
greeting {
    recipient.set("Ada")
}
~~~

`set` chọn giá trị mới. Một extension property có thể nhận một `Provider<String>` thay vì String cứng:

~~~kotlin
greeting {
    recipient.set(
        providers.gradleProperty("recipientName").orElse("Ada")
    )
}
~~~

Khi đó `./gradlew -PrecipientName=Lan printGreeting` khiến output dự kiến là `Hello, Lan!`. Đây là **cấu hình thay thế** cho block root mục 13; nếu vẫn còn một `recipient.set("Ada")` sau nó, giá trị explicit cuối sẽ thắng. Với tasks có nhiều người/plug-in cấu hình, nên thống nhất ai có quyền set.

### 16.2. map: biến đổi giá trị, không ép lấy ngay

~~~kotlin
val upperRecipient: Provider<String> =
    greeting.recipient.map { it.uppercase() }
~~~

Đây là snippet tùy chọn trong `build.gradle.kts` có typed accessor. Nó tạo một Provider mới, chỉ cần tính khi consumer yêu cầu. Nếu muốn truyền tới một task property:

~~~kotlin
tasks.named("generateGreeting", org.example.gradle.GenerateGreetingTask::class.java) {
    recipient.set(upperRecipient)
}
~~~

**Cảnh báo:** với plugin Java trong included build, việc tham chiếu trực tiếp implementation class `org.example.gradle.GenerateGreetingTask` từ consumer Kotlin DSL có thể yêu cầu classpath/API design thích hợp. Đây là **snippet khái niệm**; để giữ plugin API bền vững, người dùng nên cấu hình extension thay vì phụ thuộc public task implementation class. Ví dụ cơ bản không cần đoạn này.

### 16.3. flatMap: lấy provider từ provider của object

Trong plugin:

~~~java
generator.flatMap(GenerateGreetingTask::getOutputFile)
~~~

`generator` là `TaskProvider<GenerateGreetingTask>`. Phần method reference trả về `RegularFileProperty`, vốn cũng là Provider của file. `flatMap` nối hai cấp laziness thành `Provider<RegularFile>`, đồng thời bảo toàn thông tin task đã tạo output.

Nếu dùng `generator.map(task -> task.getOutputFile().get())`, đoạn `get()` bên trong có thể ép lấy file value trong lúc provider được truy vấn và làm mất một phần lợi ích provenance/provider composition. Ưu tiên `flatMap` khi callback trả về một Provider.

### 16.4. zip: kết hợp hai providers

Nếu một task API cần một chuỗi tổng hợp, có thể dùng:

~~~kotlin
val combined: Provider<String> =
    greeting.prefix.zip(greeting.recipient) { prefix, recipient ->
        prefix + ", " + recipient + "!"
    }
~~~

Đây là **snippet độc lập về ý tưởng**, không thay thế hai `@Input` properties của producer demo. Nếu dùng `combined` làm task input, phải annotate input property tương ứng; tránh bỏ sót các inputs gốc ảnh hưởng kết quả.

### 16.5. orElse và optional inputs

`providers.gradleProperty("greetingRecipient").orElse("Gradle")` cho value mặc định khi CLI/file property vắng. Với input bắt buộc, có thể không đặt convention để Gradle báo lỗi khi task được yêu cầu mà chưa được cấu hình. Không dùng `getOrElse("...")` trong `apply` để biến lazy provider thành String sớm.

## 17. Nối output producer với input consumer thay cho dependsOn cứng

Mối quan hệ chuẩn của demo:

~~~java
task.getInputFile().set(
    generator.flatMap(GenerateGreetingTask::getOutputFile)
);
~~~

Gradle nhận một provider biết **file output thuộc producer nào**. Vì consumer input gắn trực tiếp vào output provider, task dependency có thể được suy ra. Khi output path đổi, consumer cũng tự nhận path mới.

### 17.1. Anti-pattern: chỉ truyền đường dẫn giống nhau

~~~java
// ANTI-PATTERN: chi giong chuoi path, khong noi producer provenance.
consumer.getInputFile().set(
    project.getLayout().getBuildDirectory()
            .file("generated/greetings/greeting.txt")
);
~~~

Nếu không có task dependency khác, Gradle không chắc generator được scheduled trước consumer. Build có thể PASS trên laptop vì file cũ còn đó, nhưng FAIL ở clean CI. Đừng chỉ dùng `mustRunAfter`: nó không tự schedule generator.

### 17.2. dependsOn vẫn có trường hợp phù hợp

Khi consumer có prerequisite không thể biểu diễn qua task output, có thể dùng:

~~~java
task.dependsOn(generator);
~~~

trong task configuration action. Tuy nhiên, nếu consumer cần file thì **vẫn nên biểu diễn file như `@InputFile`/`RegularFileProperty`**, không chỉ phụ thuộc vào task. Data-driven wiring thường rõ và ít sai hơn explicit task ordering.

### 17.3. Task-produced directories

Khi một generator tạo **nhiều files**, `@OutputDirectory DirectoryProperty` là hợp đồng phù hợp. Nếu Java plugin cần compile generated Java sources, có thể nối task provider với `SourceDirectorySet.srcDir(TaskProvider)` trong source set. Cách này giúp Gradle vừa nhận generated source root vừa suy ra producer task.

Đây là **mở rộng khái niệm**, không thuộc demo greeting.txt. Không đưa file Java source vào `resources` rồi mong `compileJava` tự xử lý.

## 18. Inputs/outputs quyết định incremental build và cache

Gradle nhìn vào inputs và outputs để biết task có thể skip hay lấy kết quả từ cache. Với producer:

~~~java
@Input Property<String> getPrefix()
@Input Property<String> getRecipient()
@OutputFile RegularFileProperty getOutputFile()
~~~

Nếu `prefix`/`recipient` và implementation không đổi, file vẫn có nội dung đúng, `generateGreeting` có thể được báo `UP-TO-DATE`. Với Build Cache bật và cacheable task hợp lệ, Gradle có thể lấy output từ cache.

### 18.1. Thí nghiệm

Lượt đầu:

~~~bash
./gradlew clean generateGreeting --no-build-cache --console=plain
~~~

**Lưu ý:** root demo chỉ áp dụng greeting plugin, không áp dụng Java/Base plugin nên **không tự có task `clean`**. Nếu muốn chạy nguyên câu lệnh trên, cần apply plugin `base` ở root build; hoặc đơn giản **không gọi clean** và xóa file output thủ công trong workspace demo khi cần. Lệnh phù hợp với demo nguyên bản:

~~~bash
./gradlew generateGreeting --no-build-cache --console=plain
./gradlew generateGreeting --no-build-cache --info --console=plain
~~~

Lượt sau, producer có thể `UP-TO-DATE` nếu file/inputs không đổi. Khi người dùng thay `greeting.recipient` từ `Ada` sang `Lan`, Gradle thấy `@Input` khác; task phải tạo nội dung mới và cache key thay đổi.

### 18.2. Không nên gắn cache annotation cho mọi task

`PrintGreetingTask` chỉ in console, không có file output. Vì vậy **không dùng `@CacheableTask`** cho consumer này. Producer tạo file có deterministic content và declared inputs nên có cơ sở để cache.

Nếu generator thực tế đọc `src/main/schema/api.yaml` thì phải khai báo thêm `@InputFile` và path normalization. Nếu nó gọi external code generator, classpath/tool version và non-file arguments có thể là inputs. Bỏ sót một input dễ tạo cache bị lỗi.

### 18.3. Không ghi nhiều task vào cùng output file

Nếu hai tasks khác nhau cùng ghi `build/generated/greetings/greeting.txt`, Gradle có overlapping outputs; up-to-date/cache và parallel execution có thể sai. Mỗi generated file/directory cần một task owner hoặc pipeline staging rõ.

### 18.4. Build Cache khác Configuration Cache

- Build Cache quản lý **outputs của task**; phụ thuộc declared inputs/implementation.
- Configuration Cache quản lý **cấu hình/task graph**; phụ thuộc configuration inputs và task state serializability.
- Dependency cache quản lý artifacts/metadata từ repositories.

Một build có thể dùng Configuration Cache nhưng task producer vẫn rerun do input changed. Hoặc task `UP-TO-DATE` trong khi Configuration Cache vừa miss vì một setting thay đổi. Đừng dùng một loại cache để chứng minh loại khác đúng.

## 19. Configuration Cache: task action chỉ làm việc với chính task properties

Đây là một tiêu chí quyết định chất lượng plugin.

**Đúng trong demo:**

~~~java
@TaskAction
public void generate() throws IOException {
    String text = getPrefix().get()
            + ", " + getRecipient().get() + "!\n";
    Path path = getOutputFile().get().getAsFile().toPath();
    Files.createDirectories(path.getParent());
    Files.writeString(path, text, StandardCharsets.UTF_8);
}
~~~

Task action chỉ dùng properties của chính task và Java filesystem API.

**Không nên:**

~~~java
@TaskAction
public void generate() {
    // KHONG NEN: execution-time Project/Extension access.
    Object recipient = getProject().getExtensions()
            .getByName("greeting");
}
~~~

Ngoài việc đọc sai type, việc lấy Project/extension lúc execution khiến task khó tương thích Configuration Cache và Gradle không biết extension value nào là `@Input` thực. **Không dùng `getProject()` trong task action** để lấy DSL extension; nối properties lúc plugin configuration.

### 19.1. Thử Configuration Cache

~~~bash
./gradlew printGreeting --configuration-cache --console=plain
./gradlew printGreeting --configuration-cache --console=plain
~~~

Ở lượt đầu Gradle có thể lưu configuration state; lượt sau có thể reuse nếu inputs không đổi và môi trường tương thích. Console có thể ghi thông điệp về cache; không tuyên bố một chuỗi log tuyệt đối vì Gradle versions/machine khác nhau.

Gradle có thể phát hiện thêm những plugin khác trong project không hỗ trợ Configuration Cache; điều đó không chứng minh demo plugin sai. Xem Configuration Cache report để xác định task/type và lý do thực tế.

### 19.2. Không capture Project trong task action closures

Ví dụ anti-pattern Groovy/Kotlin:

~~~kotlin
tasks.register("badTask") {
    doLast {
        println(project.name)
    }
}
~~~

`project` được truy cập trong execution phase. Với Configuration Cache, có thể phát sinh lỗi hoặc deprecated behavior tùy Gradle version. Nếu thật sự muốn task in project name, tạo typed `@Input Property<String>` và set `project.name` trong task configuration, rồi task action đọc property.

### 19.3. External environment inputs

Khi plugin cần lấy biến môi trường:

~~~java
task.getRecipient().set(
    project.getProviders()
        .environmentVariable("GREETING_RECIPIENT")
        .orElse("Gradle")
);
~~~

Đây là **snippet tùy chọn** để thay wiring recipient. Nó giữ provider lazy, giúp input changes gắn với task. Không gọi `System.getenv("GREETING_RECIPIENT")` rồi chép sớm nếu bạn muốn giảm configuration invalidation; cũng không dùng environment để vô tình đưa secrets vào output/log của một task.

## 20. Task configuration avoidance trong plugin code

Ngoài `register`, những API quan trọng:

- `tasks.named("taskName", Type.class)`: lấy TaskProvider cho task đã đăng ký.
- `TaskProvider.configure(action)`: bổ sung cấu hình lazy.
- `tasks.withType(SomeTask.class).configureEach(action)`: cấu hình task type mà không eagerly realize mọi task.
- `project.getPluginManager().withPlugin("java", callback)`: chạy cấu hình khi plugin kia đã/được áp dụng, không dựa vào apply order.
- `Provider.map(...)` và `flatMap(...)`: biến đổi/nối dữ liệu không gọi `get()` sớm.
- `ProjectLayout.getBuildDirectory()`: lazy output layout thay hardcode path.
- `Property.convention(...)`: default có thể bị user override.

Tránh những API eager khi không cần:

- `tasks.create(...)`;
- `tasks.getByName(...)`;
- `tasks.withType(...).all(...)` trong trường hợp nó realize mọi existing tasks;
- `TaskProvider.get()` trong `apply`;
- `configuration.resolve()` hoặc `files(...)` rồi duyệt file sớm;
- `afterEvaluate(...)` như phương án mặc định để đọc extension values.

### 20.1. withPlugin tốt hơn afterEvaluate cho plugin-order integration

Khi plugin của bạn muốn tác động đến JavaCompile chỉ **nếu Java plugin hiện diện**, ưu tiên callback plugin lifecycle:

~~~java
project.getPluginManager().withPlugin("java", applied -> {
    project.getTasks()
            .withType(org.gradle.api.tasks.compile.JavaCompile.class)
            .configureEach(task -> {
                task.getOptions().setEncoding("UTF-8");
            });
});
~~~

Đây là **snippet mở rộng** và không cần cho greeting plugin demo. `withPlugin` xử lý trường hợp Java plugin đã được áp dụng trước hoặc sẽ được áp dụng sau. Không apply Java plugin bừa bãi chỉ để đăng ký custom greeting text task.

### 20.2. afterEvaluate không phải bắt buộc để lấy extension value cuối

Sai kiểu:

~~~java
project.afterEvaluate(p -> {
    String name = greeting.getRecipient().get();
    // Do something with name...
});
~~~

Dùng `afterEvaluate` có thể phụ thuộc thứ tự callback, làm plugins kết hợp khó đoán và tạo unnecessary configuration read. Với managed properties, hãy đặt:

~~~java
task.getRecipient().set(greeting.getRecipient());
~~~

và để task engine resolve input khi cần. Trường hợp thật sự cần afterEvaluate cho legacy APIs là ngoại lệ có lý do rõ, không phải mặc định.

### 20.3. Đừng dùng eager task queries để “xác nhận plugin đã đăng ký”

Một plugin không cần `project.getTasks().getByName("generateGreeting")` ngay sau `register` để xác nhận sự tồn tại của task. TaskProvider chính là handle trả về; nếu registration thất bại, Gradle đã có exception thích hợp. Realize task để “test” có thể vô hiệu hóa lazy configuration.

## 21. Groovy DSL consumer tương đương

Nếu root sử dụng `build.gradle` thay vì `build.gradle.kts`, một consumer block:

~~~groovy
plugins {
    id 'org.example.greeting'
}

greeting {
    prefix.set('Hello')
    recipient.set('Ada')
}
~~~

Đây là **cú pháp Groovy DSL thay thế**, vẫn dùng plugin implementation Java 17 ở `build-logic`. `Property.set(...)` hoạt động trong Groovy vì extension expose Gradle `Property`. Trong một số build scripts có dynamic property syntax, có thể viết assignment, nhưng dùng `set(...)` giúp người mới nhìn rõ property API.

**Đừng** copy Groovy `id '...'` vào Kotlin DSL. Với Kotlin, dùng `id("org.example.greeting")` và `recipient.set("Ada")`.

### 21.1. Kotlin plugin implementation cũng theo nguyên tắc tương tự

Nếu plugin được viết bằng Kotlin:

~~~kotlin
abstract class GenerateGreetingTask : DefaultTask() {
    @get:Input
    abstract val recipient: Property<String>

    @get:OutputFile
    abstract val outputFile: RegularFileProperty

    @TaskAction
    fun generate() {
        val text = "Hello, " + recipient.get() + "!\n"
        outputFile.get().asFile.apply {
            parentFile.mkdirs()
            writeText(text, Charsets.UTF_8)
        }
    }
}
~~~

**Đây là snippet task type Kotlin riêng, không phải phần của Java plugin demo**; cần các imports Gradle API và Kotlin Gradle Plugin Development classpath phù hợp. Điểm khác cú pháp là `@get:Input` trên Kotlin property getter, còn Java dùng `@Input` trên getter method.

Nguyên tắc không đổi: typed managed properties, `tasks.register`, task action chỉ đọc own properties và provider wiring.

## 22. Phân biệt extension property và task property khi debug

Một lỗi phổ biến: user đã đặt extension `greeting.recipient = "Ada"`, nhưng output vẫn `Gradle`.

Kiểm tra theo thứ tự:

1. Plugin đã apply đúng ID `org.example.greeting` chưa?
2. Extension name đúng `greeting` chưa?
3. Có một build script khác ghi đè `recipient.set(...)` sau đó không?
4. Plugin có dùng `task.getRecipient().set(greeting.getRecipient())` hay đã gọi `get()` sớm?
5. Task name đang chạy có thật sự là `generateGreeting`/`printGreeting` của plugin này không?
6. Property default đặt qua `convention` hay plugin đã dùng `set` không cho user override?
7. File output thực tế có trùng đường dẫn consumer đang đọc không?
8. Task producer có `@Input` cho recipient không?
9. Plugin task action có đọc `task.getRecipient()` hay đọc một field/extension khác?
10. Có một output file stale từ build cũ, hoặc Gradle đang đọc từ workspace khác không?
11. Nếu muốn override bằng `-P`, root build còn `recipient.set("Ada")` explicit không?
12. Configuration Cache/Build Cache reports có giải thích vì sao task được skip/cache hay không?

**Không sửa bằng cách vô hiệu hóa mọi cache trước.** Cache chỉ che lộ sai input modelling; khi sửa đúng contract, Gradle sẽ rerun task do input thay đổi.

## 23. Kiểm thử plugin bằng Gradle TestKit

Một plugin có thể hoạt động đúng trong một sample project nhưng fail khi áp dụng ở project thực, khi output được đổi, hoặc dưới Configuration Cache. **Gradle TestKit** giúp tạo một test project tạm rồi chạy Gradle như consumer thật.

### 23.1. Bổ sung dependencies cho build-logic

Thêm vào **`build-logic/build.gradle.kts`** (giữ phần `plugins/java/gradlePlugin` đã có):

~~~kotlin
repositories {
    mavenCentral()
}

dependencies {
    testImplementation(gradleTestKit())
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Đây là **snippet bổ sung**, không phải build script thay thế hoàn chỉnh. Gradle `java-gradle-plugin` tích hợp metadata giúp `GradleRunner.withPluginClasspath()` đưa plugin đang test vào test build. `junit-jupiter:5.11.4` được pin để demo; không khẳng định đây là bản mới nhất hiện tại.

### 23.2. Functional test Java 17

**File `build-logic/src/test/java/org/example/gradle/GreetingPluginFunctionalTest.java`:**

~~~java
package org.example.gradle;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class GreetingPluginFunctionalTest {
    @TempDir
    Path projectDir;

    @Test
    void connectsExtensionToTaskAndRunsConsumer() throws Exception {
        Files.writeString(
                projectDir.resolve("settings.gradle.kts"),
                "rootProject.name = \"test-consumer\"\n",
                StandardCharsets.UTF_8
        );

        Files.writeString(
                projectDir.resolve("build.gradle.kts"),
                "plugins { id(\"org.example.greeting\") }\n"
                        + "greeting { recipient.set(\"Ada\") }\n",
                StandardCharsets.UTF_8
        );

        BuildResult result = GradleRunner.create()
                .withProjectDir(projectDir.toFile())
                .withPluginClasspath()
                .withArguments(
                        "printGreeting",
                        "--stacktrace",
                        "--console=plain"
                )
                .build();

        assertTrue(
                result.getOutput().contains(
                        "Greeting file: Hello, Ada!"
                )
        );

        Path generated = projectDir.resolve(
                "build/generated/greetings/greeting.txt"
        );

        assertEquals(
                "Hello, Ada!\n",
                Files.readString(
                        generated,
                        StandardCharsets.UTF_8
                )
        );
    }
}
~~~

**Đây là functional test hoàn chỉnh** cho plugin demo (khi các files trước đã có). Nó kiểm tra cả console lẫn file output. Nếu generator chưa được scheduled từ output provider của consumer, một clean temp directory sẽ giúp phát hiện lỗi.

Chạy:

~~~bash
./gradlew :build-logic:test --console=plain
~~~

Tùy cách included build được khai báo trong `pluginManagement` và Gradle version, CLI task path có thể là `:build-logic:test` hoặc included build identity khác. Cách không nhập nhằng là mở folder `build-logic` và chạy Gradle ở đó bằng Wrapper tương thích:

~~~bash
cd build-logic
../gradlew test --console=plain
~~~

Nếu test dependencies không resolve, xem repositories cho **build-logic**, không chỉ root app. Đừng giả định root `repositories { ... }` áp sang included build.

### 23.3. Kiểm tra thay đổi extension và output path

Có thể bổ sung tests riêng để kiểm tra:

- Người dùng chọn `recipient.set("Lan")` thì file thành `Hello, Lan!\n`.
- Người dùng chọn `outputFile.set(layout.buildDirectory.file("custom/hello.txt"))`, cả producer/consumer đều dùng đường dẫn mới.
- Không có customization thì output mặc định `Hello, Gradle!\n`.
- Chạy `printGreeting` trên clean temp project tự gọi producer.
- Chạy producer hai lần liên tiếp có thể `UP-TO-DATE`.
- Task action không đọc `Project` và tương thích `--configuration-cache`.
- User `-PgreetingRecipient=...` chỉ tác động khi extension recipient không bị explicit override.
- Task names/extension name không xung đột với plugins khác.

Với output có credentials hoặc dữ liệu nhạy cảm, đừng đưa raw secrets vào TestKit log. Demo chỉ có lời chào công khai.

## 24. Kiểm tra lazy behavior và task graph

Một vài lệnh hữu ích:

~~~bash
./gradlew help --console=plain
./gradlew tasks --group greeting --console=plain
./gradlew printGreeting --dry-run --console=plain
./gradlew generateGreeting --info --console=plain
./gradlew printGreeting --configuration-cache --console=plain
~~~

**Giải thích:**

- `help`: không được tạo file chỉ do plugin được apply.
- `tasks --group greeting`: liệt kê hai tasks được plugin đăng ký; task discovery có thể realize tasks tùy Gradle/version/plugin interactions, nên không dùng nó như bằng chứng tuyệt đối về số task đã được configure.
- `printGreeting --dry-run`: hiển thị producer và consumer dự kiến (thường báo SKIPPED); **không tạo file output**.
- `generateGreeting --info`: xem lý do task UP-TO-DATE/rerun, nhớ cẩn trọng với logs có secrets.
- `--configuration-cache`: thử lưu/reuse task graph, xem diagnostics nếu có lỗi.
- `--rerun-tasks`: buộc Gradle chạy lại tasks, không phải chữa sai wiring input/output.

### 24.1. Chẩn đoán task được realize sớm

Nếu plugin apply tăng thời gian của mọi lệnh, tìm:

- `tasks.create` hoặc `tasks.getByName` trong `apply`.
- `tasks.all { ... }` hoặc `withType(...).all` gọi quá rộng.
- `TaskProvider.get()` trong configuration.
- `files(...).getFiles()` khiến inputs bị snapshot/resolve sớm.
- `Configuration.resolve()` trong configuration.
- `provider.get()` hoặc `outputFile.get()` trước khi người dùng set value.
- Đăng ký listener/`afterEvaluate` để đọc extension.
- Plugin áp dụng quá nhiều plugins phụ cho mọi projects.

Dùng Build Scan/Profiler khi cần đo thực tế; không suy một plugin tốt hay xấu chỉ từ số tasks được in bởi `tasks`.

## 25. Trường hợp extension cung cấp file input thay vì String

Một code generator thực tế có thể đọc template/schema và viết output. Khi đó extension có thể có:

~~~java
public interface CodegenExtension {
    RegularFileProperty getSchemaFile();
    DirectoryProperty getOutputDirectory();
}
~~~

**Đây là snippet interface minh họa**, cần imports `RegularFileProperty` và `DirectoryProperty`, và task type khác thực hiện code generation. Task nên có:

~~~java
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
public abstract RegularFileProperty getSchemaFile();

@OutputDirectory
public abstract DirectoryProperty getOutputDirectory();
~~~

Khi plugin đăng ký task:

~~~java
task.getSchemaFile().set(extension.getSchemaFile());
task.getOutputDirectory().set(extension.getOutputDirectory());
~~~

Gradle sẽ theo dõi schema file và output directory theo contracts. Với input file đơn mà chỉ contents quan trọng, `PathSensitivity.NONE` cũng có thể phù hợp; chọn `RELATIVE` khi relative path tham gia vào output semantics. Nếu schema đổi, task có cơ sở chạy lại.

### 25.1. Khi task cần classpath

Nếu generator dùng external Java tools, model tool classpath với `@Classpath ConfigurableFileCollection` hoặc API phù hợp; executable/tool version cũng ảnh hưởng output. Không chỉ khai báo schema và output rồi chạy một chương trình bên ngoài có version thay đổi không được track.

### 25.2. Generated Java source và SourceSet

Nếu generator tạo `.java` files, output thường nằm ở:

~~~text
build/generated/sources/<generator>/main
~~~

Nối task output vào `sourceSets.main.java.srcDir(taskProvider)` khi Java plugin đã có, thay vì chỉ thêm path String. Khi consumer nhận TaskProvider với `@OutputDirectory`, Gradle giữ thông tin producer, compile task biết cần generator trước.

**Không coi generated file trong `build/` là source do developer quản lý** và không ghi vào `src/main/java` từ task action. Có một task owner cho mỗi directory.

## 26. An toàn và chính sách khi phát triển plugin

Một plugin là code được thực thi **trong quá trình build**, có thể chạm filesystem, network, process environment và credentials. Vì vậy:

- Chỉ apply plugin từ trusted source/repository.
- Pin plugin versions, dùng dependency verification và policy kiểm soát khi phù hợp.
- Không chạy `Exec`, network requests hoặc ghi file ngay trong `Plugin.apply`.
- Không dùng plugin để đọc secrets nếu task không thật sự cần.
- Không in API keys/passwords qua logger/console.
- Không đặt credentials vào generated resources/JARs hoặc cacheable outputs.
- Sử dụng `providers.environmentVariable`/Gradle credentials APIs và task properties có scope phù hợp.
- Tránh custom task ghi/chỉnh sửa files ngoài build directory trừ khi có yêu cầu rõ.
- Không cho nhiều producer tasks ghi cùng output path.
- Không đánh dấu tasks phụ thuộc clock/random/network nhưng thiếu input annotations là `@CacheableTask`.
- Không dùng privileged build agent cho plugin untrusted trong CI.
- Tách publish/deploy tasks khỏi build/check lifecycle nếu chúng có external side effects.
- Test plugin trên một sample consumer project với clean directory và Configuration Cache.

**Lưu ý bảo mật với Configuration Cache:** các task properties có thể được serialize khi lưu task graph; không coi cache directory là nơi lưu mật khẩu an toàn. Dùng provider/secret scopes và tuyệt đối không log values bí mật.

## 27. Bảng lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| `Plugin [id: 'org.example.greeting'] was not found` | Chưa có `pluginManagement.includeBuild("build-logic")` hoặc descriptor sai | Xem root settings/`gradlePlugin` |
| `ClassNotFoundException: GreetingPlugin` | `implementationClass` không khớp package/class | Kiểm tra Java file và plugin DSL |
| `Extension with name 'greeting' does not exist` | Plugin chưa apply hoặc extension name khác | Dùng đúng plugin ID và `create("greeting", ...)` |
| `Unresolved reference: greeting` trong Kotlin DSL | Plugin chưa có typed accessor ở script compile | Kiểm tra plugins block/plugin resolution |
| `Could not create an instance of GreetingExtension` | Managed property interface không hợp lệ | Dùng typed getters Gradle supports |
| Task `generateGreeting` không xuất hiện | Plugin không register/khác project | Kiểm tra `tasks` trong đúng project |
| Output vẫn là `Gradle` dù set `Ada` | Plugin đọc `get()` sớm hoặc override sau | Nối provider bằng `set(extension.property)` |
| Input property has no value | Task thiếu `set`/`convention` | Đặt required input/default có chủ đích |
| File không xuất hiện khi chạy `printGreeting` | Consumer input path không mang producer dependency | `flatMap` từ task output provider |
| `File not found` trên clean build | Hardcoded path, generator không scheduled | Dùng provider provenance, xem `--dry-run` |
| Gradle báo implicit dependency validation | Task consumer đọc output khác nhưng không declare dependency | Nối `@InputFile` tới `@OutputFile` provider |
| Task luôn chạy lại | `@Input`/`@OutputFile` thiếu hoặc output bị đổi ngoài task | Khai báo đầy đủ inputs/outputs |
| Task UP-TO-DATE dù input thực đổi | Input ẩn hoặc đọc extension ngoài contract | Thêm annotated task property |
| Build Cache trả file sai | Generator non-deterministic hoặc overlapping outputs | Sửa task contracts, kiểm tra hidden inputs |
| Configuration Cache báo lỗi execution-time Project access | Task action gọi `getProject()` hoặc extension container | Chuyển data sang typed task properties |
| `No task 'clean'` | Root chỉ áp greeting plugin, không có Base/Java | Dùng producer trực tiếp hoặc apply `base` |
| `javac` báo package org.gradle.api không tồn tại | Compile plugin source bằng JDK thuần thiếu Gradle API | Dùng `java-gradle-plugin` trong Gradle |
| TestKit không resolve JUnit | build-logic thiếu repository | Khai báo Maven Central/mirror trong build-logic |
| `-PgreetingRecipient=Lan` không có tác dụng | Root `recipient.set("Ada")` đã explicit override convention | Đổi consumer wiring hoặc bỏ explicit set |
| Task consumer in file cũ | Two tasks ghi chung path hoặc cache/dir sai | Xác định producer owner/outputs |
| `--dry-run` không tạo output | Đó là semantics của dry-run | Chạy task thật sau khi xem graph |
| Gradle task group không hiện | Chưa set group hoặc task chưa registered | Đặt `task.setGroup("greeting")` |
| Task `printGreeting` vẫn execute khi generator UP-TO-DATE | Consumer chỉ in console, không có file output | Đây là hành vi mong đợi |
| Test thay path output nhưng consumer không theo | Consumer hardcode path thay vì provider | Nối `generator.flatMap(...getOutputFile)` |

### 27.1. Quy trình debug sáu bước

1. **Plugin resolution:** kiểm tra `pluginManagement.includeBuild` và Gradle plugin ID.
2. **Extension:** đúng tên, đúng property getters, đúng convention và explicit values?
3. **Task registration:** plugin có dùng `tasks.register` và task class đúng?
4. **Property wiring:** task input có nhận provider từ extension, không phải String snapshot sớm?
5. **Producer/consumer wiring:** consumer input có lấy provider từ output của producer?
6. **Execution/caching:** task action chỉ đọc declared task inputs, output được tạo đúng file, Gradle reporting giải thích skip/cache?

## 28. Bài tập thực hành có đáp án

**Câu 1.** `tasks.register` khác `tasks.create` thế nào?  
**Đáp án:** `register` cung cấp lazy TaskProvider, `create` eagerly creates/configures task.

**Câu 2.** Plugin `apply` có nên viết file `greeting.txt` ngay khi được apply không?  
**Đáp án:** không; I/O thuộc `@TaskAction` khi task được execute.

**Câu 3.** Plugin muốn user cấu hình tên người nhận, tạo API nào?  
**Đáp án:** typed extension với `Property<String> getRecipient()`.

**Câu 4.** Task cần tên người nhận, annotation nào?  
**Đáp án:** `@Input` trên getter của task property.

**Câu 5.** Task tạo một file cụ thể, annotation/property nào?  
**Đáp án:** `@OutputFile RegularFileProperty`.

**Câu 6.** Vì sao không `task.getRecipient().set(extension.getRecipient().get())`?  
**Đáp án:** `get()` lấy value sớm, bỏ provider chain và có thể đọc default trước user config.

**Câu 7.** Dòng wiring đúng extension→task?  
**Đáp án:** `task.getRecipient().set(greeting.getRecipient())`.

**Câu 8.** Vì sao `convention("Gradle")` khác `set("Gradle")`?  
**Đáp án:** convention là default; explicit set trong consumer có quyền override.

**Câu 9.** Demo root user set `recipient="Ada"`; `printGreeting` in gì?  
**Đáp án:** `Greeting file: Hello, Ada!`.

**Câu 10.** File producer tạo ở đâu theo default?  
**Đáp án:** `build/generated/greetings/greeting.txt`.

**Câu 11.** File chứa newline cuối không?  
**Đáp án:** có, Java generator nối `\n` sau dấu `!`.

**Câu 12.** Đổi recipient thành Lan, task nào được yêu cầu chạy lại khi output stale?  
**Đáp án:** `generateGreeting` vì `@Input` đã đổi; `printGreeting` đọc file mới khi được yêu cầu.

**Câu 13.** Consumer cần output producer, API nối gì?  
**Đáp án:** `generator.flatMap(GenerateGreetingTask::getOutputFile)` rồi set vào `@InputFile`.

**Câu 14.** `mustRunAfter` có tự schedule generator không?  
**Đáp án:** không; chỉ ordering khi cả hai tasks đã ở graph.

**Câu 15.** Vì sao `PrintGreetingTask` không nên `@CacheableTask`?  
**Đáp án:** nó chỉ in console, không tạo output artifact để cache/skip có ý nghĩa.

**Câu 16.** `@CacheableTask` của generator có hợp lý không?  
**Đáp án:** có cho ví dụ deterministic với declared inputs; không đúng nếu có hidden time/network state.

**Câu 17.** Task action có nên gọi `getProject().getExtensions().getByName("greeting")`?  
**Đáp án:** không; đọc extension lúc execution phá separation/input tracking và Configuration Cache compatibility.

**Câu 18.** `TaskProvider.get()` trong plugin `apply` có lợi ích gì?  
**Đáp án:** thường không; realize task sớm, nên giữ TaskProvider và `configure`/`flatMap`.

**Câu 19.** Plugin chỉ nên tùy chỉnh `JavaCompile` khi có plugin Java; API nào phù hợp?  
**Đáp án:** `pluginManager.withPlugin("java", callback)` và `withType(JavaCompile).configureEach`.

**Câu 20.** `afterEvaluate` có cần để extension recipient nhận value cuối?  
**Đáp án:** không; nối lazy property provider từ extension tới task.

**Câu 21.** Ưu điểm của `layout.buildDirectory.file(...)`?  
**Đáp án:** lazy file provider, tôn trọng build directory nếu được thay đổi.

**Câu 22.** `-PgreetingRecipient=Lan` không override `recipient.set("Ada")` trong demo, tại sao?  
**Đáp án:** project property chỉ là convention; explicit set của consumer thắng.

**Câu 23.** Muốn dùng `-PrecipientName=Lan` làm input thật, cấu hình ra sao?  
**Đáp án:** `recipient.set(providers.gradleProperty("recipientName").orElse("Ada"))` trong consumer DSL.

**Câu 24.** `@InputFile` cần normalization trong build cache?  
**Đáp án:** nên có `@PathSensitive` phù hợp; `NONE` nếu chỉ contents quyết định behavior, `RELATIVE` khi relative path quan trọng.

**Câu 25.** Một generator tạo nhiều Java files, nên dùng output gì?  
**Đáp án:** `@OutputDirectory DirectoryProperty` và nối source set bằng task provider.

**Câu 26.** Task producer có thể `UP-TO-DATE` trong khi consumer print vẫn chạy không?  
**Đáp án:** có; consumer không có output file để skip/cache.

**Câu 27.** Plugin compiled Java 17 có thể chạy `javac` trực tiếp không kèm Gradle API không?  
**Đáp án:** không; plugin import `org.gradle.api.*` nên cần Gradle API classpath.

**Câu 28.** Lệnh `javac` ở mục 14 kiểm tra điều gì?  
**Đáp án:** helper Java 17 đọc file do plugin sinh; không compile plugin implementation.

**Câu 29.** TestKit `withPluginClasspath` phục vụ việc gì?  
**Đáp án:** cung cấp plugin-under-test cho temporary Gradle test build.

**Câu 30.** Demo muốn đổi output path và để consumer tự theo, phải sửa gì?  
**Đáp án:** thay extension `outputFile`, không hardcode input path ở Print task.

**Câu 31.** `-q` có hiện `logger.quiet` không?  
**Đáp án:** có; mức QUIET được hiển thị, trái với nhiều lifecycle logs.

**Câu 32.** Root chỉ apply greeting plugin, gọi `./gradlew clean` luôn có task này không?  
**Đáp án:** không; cần Base/Java plugin hoặc task clean riêng.

**Câu 33.** Vì sao `TaskProvider.flatMap` hợp lý hơn hardcode file path?  
**Đáp án:** giữ lazy value, producer provenance và implicit task dependency.

**Câu 34.** Có cần thêm `dependsOn(generator)` bên cạnh `inputFile.set(generator.flatMap(...))` trong demo?  
**Đáp án:** không; provider wiring đã biểu diễn data dependency.

**Câu 35.** Khi nào cần `@OutputDirectory` thay `@OutputFile`?  
**Đáp án:** khi task sở hữu một thư mục chứa tập files generated, không phải một file đơn.

**Câu 36.** Một custom task cần API key bí mật: nên ghi key vào generated output cho dễ kiểm thử không?  
**Đáp án:** không; dùng secret management phù hợp, không log/cache secrets không cần thiết.

## 29. Checklist dành cho plugin author

- [ ] Plugin chỉ đăng ký build model trong `apply`, không chạy I/O/task action?
- [ ] Sử dụng `tasks.register` thay vì eager `create`?
- [ ] Dùng `TaskProvider`, `tasks.named` và `configureEach` khi cần?
- [ ] Extension có typed `Property`/file properties thay raw mutable fields?
- [ ] Mặc định dùng `convention`, không ghi đè explicit user configuration?
- [ ] Task có `@Input`/`@InputFile`/`@OutputFile`/`@OutputDirectory` đầy đủ?
- [ ] Extension→task được nối bằng `set(provider)`, không đọc `get()` sớm?
- [ ] Producer→consumer được nối bằng `flatMap` output provider?
- [ ] Không dùng `mustRunAfter` để thay actual task dependency?
- [ ] Task action chỉ đọc own annotated task properties?
- [ ] Không gọi `getProject()` hoặc extension container trong task execution?
- [ ] Output đặt dưới `layout.buildDirectory` với task owner duy nhất?
- [ ] Generator deterministic trước khi dùng `@CacheableTask`?
- [ ] Các input file paths dùng `@PathSensitive` hợp lý?
- [ ] Không cache console-only/side-effect-only task như file producer?
- [ ] Không lộ secrets trong output, cache hoặc task logs?
- [ ] Không resolve configurations hoặc traverse files trong plugin `apply`?
- [ ] Tích hợp plugin khác qua `withPlugin`, không phụ thuộc apply order?
- [ ] Không lạm dụng `afterEvaluate` để đọc DSL extension?
- [ ] Plugin ID/implementationClass khớp file class/package?
- [ ] Build logic có Gradle Wrapper/JDK/Gradle API compatibility rõ?
- [ ] Included `build-logic` có settings và plugin resolution riêng?
- [ ] Có TestKit functional test trong clean temporary directory?
- [ ] Test xác nhận cả content file và consumer task dependency?
- [ ] Chạy thử `--configuration-cache` ít nhất hai lượt?
- [ ] Kiểm tra output đổi khi extension input đổi?
- [ ] Kiểm tra consumer theo được khi extension output path đổi?
- [ ] Có phân biệt `-P` convention và user explicit `set`?
- [ ] Docs giải thích CLI tasks, expected output và failure diagnostics?
- [ ] Plugin scope chỉ apply vào projects cần thiết, không bắt mọi subproject dùng vô điều kiện?

## 30. Tài liệu tham khảo chính thức

- [Gradle — Binary Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_binary.html): `Plugin<Project>`, extension, task registration và `java-gradle-plugin`.
- [Gradle — Writing Plugins](https://docs.gradle.org/current/userguide/writing_plugins.html): plugin development trong build logic hoặc standalone plugin.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register`, `TaskProvider`, `tasks.named` và lazy configuration.
- [Gradle — Configuring Tasks Lazily](https://docs.gradle.org/current/userguide/lazy_configuration.html): property defaults, task registration và deferred configuration.
- [Gradle — Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): `Property`, `Provider`, `convention`, `map`/`flatMap`/`zip`.
- [Gradle — Implementing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): `DefaultTask`, input/output annotations, managed properties và `@TaskAction`.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): producer/consumer wiring, lazy output, cacheable work và tránh eager `get()`.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): không đọc Project/extension trong task execution, provider-backed inputs.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): task graph caching và compatibility.
- [Gradle — Testing Binary Plugins](https://docs.gradle.org/current/userguide/test_kit.html): GradleRunner, `withPluginClasspath` và functional testing.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): `build-logic` included build và plugin ownership.
- [Gradle — Working with Files](https://docs.gradle.org/current/userguide/working_with_files.html): task output providers, file collections và task dependencies.
- [Gradle — Incremental Builds](https://docs.gradle.org/current/userguide/incremental_build.html): declared inputs/outputs, `UP-TO-DATE`.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): cacheable task outputs và input fingerprints.

**Kết luận:** Plugin Gradle có thiết kế tốt cần tạo **extension typed để nhận cấu hình**, **task typed có annotated inputs/outputs**, rồi nối chúng bằng **Provider APIs** thay vì đọc giá trị sớm. `tasks.register` và `TaskProvider` cho phép lazy task creation; `extension.property → task.input` giữ cấu hình cuối của người dùng, còn `producer.output → consumer.input` qua `flatMap` giúp Gradle tự suy ra task dependency. `@TaskAction` chỉ thực hiện I/O khi task chạy. Khi kết hợp `convention`, `Property.set(Provider)`, `RegularFileProperty`, Configuration Cache và TestKit, plugin trở nên dễ dùng, incremental/cache đúng và bền vững với build nhiều module.