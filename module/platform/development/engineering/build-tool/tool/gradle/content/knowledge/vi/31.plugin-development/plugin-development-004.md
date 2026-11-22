# Thiết kế extension có kiểu bằng managed properties

**Chủ đề:** Build Tool Gradle  
**Nhóm kiến thức:** Phát triển plugin

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Thiết kế một **plugin extension có kiểu** để người dùng cấu hình trong Groovy DSL mà không dựa vào các map hay extra properties động.
2. Giải thích ý nghĩa và điểm khác nhau của **Provider<T>**, **Property<T>**, **ListProperty<T>**, **SetProperty<T>**, **MapProperty<K,V>**, **RegularFileProperty**, **DirectoryProperty** và **ConfigurableFileCollection**.
3. Khai báo **Gradle-managed type** bằng một interface hoặc abstract class có các JavaBeans getter như **Property<String> getMessage()**, để Gradle tự cung cấp implementation.
4. Tạo extension bằng **project.getExtensions().create(...)**, đặt defaults bằng **convention(...)**, cho phép người dùng ghi đè bằng **set(...)**.
5. Nối extension sang một custom task bằng **task.getX().set(extension.getX())**, giữ Provider lười thay vì gọi **get()** quá sớm hoặc dùng **afterEvaluate**.
6. Mô hình hóa task inputs/outputs với **@Input**, **@InputFile**, **@InputFiles**, **@OutputFile**, **@OutputDirectory** và các annotations liên quan, tránh làm Gradle hiểu nhầm giá trị/caching.
7. Viết được một **binary Gradle plugin bằng Java 17** và cung cấp Groovy DSL consumer có thể chạy, sinh file UTF-8 với nội dung xác định.
8. Chạy một chương trình Java 17 nhỏ bằng **javac/java** để xác minh chính xác nội dung artifact mà plugin tạo.
9. Kiểm tra thay đổi cấu hình qua **-P**, lựa chọn convention, set, Provider.map, finalization, xử lý optional inputs và báo lỗi rõ ràng.
10. Viết **functional test** cho plugin bằng **Gradle TestKit + JUnit Jupiter**, kiểm tra plugin ID, typed DSL, task outcome và nội dung output.
11. Giải thích liên hệ giữa managed properties, **UP-TO-DATE**, **FROM-CACHE** và **Configuration Cache** mà không nhầm các cơ chế này là một.
12. Chẩn đoán các lỗi thường gặp: abstract getter không hợp lệ, missing value, kiểu file không đúng, afterEvaluate/get sớm, input không được theo dõi và Project reference trong task action.

**Nguyên lý cốt lõi:** Extension là **hợp đồng cấu hình**, task là **đơn vị thực thi**, còn Provider/Property là **kênh truyền dữ liệu có kiểu và lười**. Plugin nối extension properties tới task properties. Gradle nhìn thấy đúng task inputs/outputs để quyết định có phải chạy lại task không. Không dùng extension như nơi thực hiện I/O hoặc đọc Project model trong @TaskAction.

## 1. Tại sao cần extension có kiểu?

Một Gradle plugin thường phải cho người sử dụng đặt tên, bật/tắt tính năng, truyền danh sách, file đầu ra hoặc metadata. Một thiết kế cũ có thể dựa vào extra properties:

~~~groovy
// Anti-pattern: cấu hình kiểu động, khó kiểm tra và không lazy.
ext.greetingMessage = 'Hello'
ext.greetingEnabled = 'false'
ext.greetingOutput = 'build/greeting.txt'
~~~

Những giá trị này thiếu hợp đồng kiểu rõ ràng:
- 'false' là một **String**, không phải Boolean.
- Path là một String, không mang Provider/Gradle layout semantics.
- Tên property sai có thể chỉ bị phát hiện khi task chạy.
- Giá trị mặc định, validation, tài liệu và khả năng dùng Provider đều phải tự viết.
- Nếu plugin đọc extra property ngay trong apply(), nó có thể đọc trước khi build script cấu hình xong.

Một typed extension cho phép:

~~~groovy
greeting {
    message.set('Hello')
    recipient.set('Mai')
    uppercase.set(false)
    tags.set(['gradle', 'java17'])
    metadata.set([kind: 'lesson', level: 'basic'])
    outputFile.set(layout.buildDirectory.file('generated/greeting.txt'))
}
~~~

Trong đó message và recipient có kiểu Property<String>, uppercase là Property<Boolean>, tags là ListProperty<String>, metadata là MapProperty<String,String>, outputFile là RegularFileProperty.

**Giá trị của mô hình có kiểu:** API dễ khám phá, dễ test, nhận Provider values, đưa ra default, phân biệt file với directory, và giúp Gradle biết khi nào công việc cần thực thi.

### 1.1. Ba lớp trách nhiệm

~~~text
build.gradle (consumer)
     |
     v
greeting { message.set(...); outputFile.set(...) }
     |
     v
GreetingExtension                    ← MODEL CẤU HÌNH
     | Property<String>
     | ListProperty<String>
     | MapProperty<String,String>
     | RegularFileProperty
     |
     | set(Provider), không gọi get quá sớm
     v
GenerateGreetingTask                 ← MODEL THỰC THI
     | @Input, @OutputFile
     | @TaskAction
     v
build/generated/greeting.txt         ← ARTIFACT OUTPUT
~~~

Plugin.apply(Project) chỉ tạo extension, đặt conventions và đăng ký task. I/O thật diễn ra trong task action ở execution phase, không phải lúc plugin được apply.

### 1.2. Extension không phải task

| Thành phần | Vai trò | Hành động nên làm |
|---|---|---|
| **Extension** | Hợp đồng cấu hình công khai | Expose managed getters |
| **Plugin<Project>** | Thiết lập model và wiring | extensions.create, tasks.register |
| **Custom task** | Thực hiện công việc | @Input/@Output, @TaskAction |
| **Provider** | Truyền value có thể tính sau | map, flatMap, set(Provider) |
| **Build script** | Consumer chọn cấu hình | message.set(...), outputFile.set(...) |
| **Gradle task engine** | Quyết định task cần thực thi không | Dựa trên inputs/outputs và cache |

Không lấy việc một extension có kiểu làm bằng chứng task tự trở thành cacheable: **task type vẫn phải công bố đầu vào/đầu ra đúng**.

## 2. Provider và Property khác nhau thế nào?

### 2.1. Provider<T> — giá trị chỉ đọc

Provider<T> đại diện một value có thể chưa được tính ngay, ví dụ Gradle project property:

~~~groovy
def receiverProvider = providers.gradleProperty('recipientName')
        .orElse('Mai')

tasks.register('showReceiver') {
    doLast {
        println receiverProvider.get()
    }
}
~~~

Nếu invocation có **-PrecipientName=Lan**, task in Lan. Nếu không có property ấy, nó in Mai.

**Điều cần nhớ:** Provider.get() lấy value. Trong task action khi value sẵn sàng, đó là hợp lý. Trong Plugin.apply() để lấy file do task khác chưa sinh thì thường là quá sớm.

### 2.2. Property<T> — vừa có thể cấu hình vừa là Provider

Property<T> hỗ trợ:
- **set(value)**: đặt explicit value.
- **set(provider)**: kết nối lazy tới nguồn khác.
- **convention(value/provider)**: fallback.
- **get()**: query value khi cần.
- **isPresent()** và **getOrElse(...)**: xử lý absence.
- **finalizeValue()**, **finalizeValueOnRead()**, **disallowChanges()**: khóa hoặc chốt cấu hình có kiểm soát.

Ví dụ:

~~~groovy
def title = objects.property(String)
title.convention('Untitled')
title.set(providers.gradleProperty('documentTitle').orElse('Hello'))
~~~

Nếu không có documentTitle, title là Hello vì **set(Provider)** đã đặt explicit nguồn value; convention Untitled không được dùng.

### 2.3. convention và set không giống nhau

| API | Ý nghĩa | Override |
|---|---|---|
| **convention('Hello')** | Default khi chưa cấu hình explicit | set(...) sẽ thắng |
| **set('Hi')** | Giá trị tường minh | set khác có thể thay nếu chưa finalized |
| **set(provider)** | Nguồn tính lười | Không cần lấy value ngay |
| **finalizeValue()** | Query và khóa value ngay | Không thay được sau đó |
| **finalizeValueOnRead()** | Query lần đầu rồi khóa | Không thay được sau lần đọc |
| **disallowChanges()** | Ngăn thay đổi state | Không nên dùng trước khi consumer cấu hình |

Plugin thường đặt **convention**; consumer build.gradle đặt **set**. Nếu plugin finalize extension ngay trong apply(), block greeting bên dưới plugins block có thể báo lỗi không cho sửa value.

### 2.4. Collection properties

| Kiểu | Nội dung | Ví dụ |
|---|---|---|
| Property<String> | Một chuỗi | message |
| Property<Boolean> | True/false | uppercase |
| Property<Integer> | Số nguyên wrapper | retryCount |
| ListProperty<String> | Danh sách có thứ tự | tags |
| SetProperty<String> | Tập giá trị duy nhất | modules |
| MapProperty<String,String> | Key-value có kiểu | metadata |
| RegularFileProperty | Một file | outputFile |
| DirectoryProperty | Một directory | generatedDir |
| ConfigurableFileCollection | Tập file và quan hệ producer | sourceFiles |

Java generics không dùng kiểu primitive: **Property<Boolean>**, không phải Property<boolean>.

Trong collection property:
- **set(...)** đặt cả list/map mới.
- **add/addAll** có thể thêm phần tử trong ListProperty/SetProperty.
- **put/putAll** có thể cập nhật MapProperty.
- **convention(...)** vẫn là default, bị explicit state override.
- Với output bytes deterministic, đừng dựa vào iteration order không được bảo đảm của Map/Set: cần sắp xếp keys/elements theo một quy tắc ổn định.

### 2.5. Provider.map và flatMap

~~~groovy
def name = providers.gradleProperty('recipientName')
        .orElse('Mai')
def normalized = name.map { it.strip() }
~~~

map tạo Provider được biến đổi **khi giá trị cần được query**. Nếu transformation trả một Provider khác, dùng flatMap thay vì Provider<Provider<T>>:

~~~groovy
def mode = providers.gradleProperty('mode').orElse('dev')
def label = mode.flatMap { value ->
    providers.gradleProperty(value == 'prod' ? 'prodLabel' : 'devLabel')
}
~~~

Hai đoạn trên là snippets minh họa, không cần chèn vào build.gradle của lab. Chúng cho thấy công thức xử lý giá trị nằm ở **Provider graph**, không nhất thiết phải tính ngay lúc plugin áp dụng.

## 3. Managed type và JavaBeans abstract getters

Gradle có thể tự tạo implementation cho một interface/abstract class có các getter managed được công nhận.

**Mẫu đúng:**

~~~java
import org.gradle.api.provider.Property;

public abstract class GreetingExtension {
    public abstract Property<String> getMessage();
}
~~~

Getter tên **getMessage** theo JavaBeans convention, trả một supported managed property type, có visibility public/protected và không cần setter String riêng.

**Mẫu sai:**

~~~java
// Không phải một JavaBeans managed getter:
public abstract Property<String> message();
~~~

Với các managed property getters, Gradle dùng generated/decorated implementation và tự khởi tạo Property objects. Không tự new một abstract extension hoặc tự xây những Property getters bằng null placeholders.

### 3.1. Extension được đăng ký thế nào?

Trong Plugin<Project>.apply:

~~~java
GreetingExtension extension = project.getExtensions()
        .create("greeting", GreetingExtension.class);
~~~

Sau khi plugin được áp, consumer dùng:

~~~groovy
greeting {
    message.set('Hello')
}
~~~

Tên **greeting** đến từ tham số đầu tiên của extensions.create. Nó cần không trùng tên extensions do các plugins khác đã đăng ký.

### 3.2. Không cần setter kiểu cũ

~~~java
// Không tự thêm setter này vào managed type:
public void setMessage(String value) {
    // ...
}
~~~

Consumer gọi **getMessage().set(...)** hoặc thuộc tính tương ứng trong Groovy DSL. Nếu cần giữ public API cũ, hãy có migration/deprecation plan thay vì ghép setters cũ làm Gradle không nhận dạng managed type.

### 3.3. Khi nào dùng ObjectFactory?

Với managed extension abstract getters, **extensions.create** đủ để Gradle tạo object. ObjectFactory vẫn hữu ích khi:
- Cần tạo Property thủ công trong một class không managed.
- Cần objects.newInstance để tạo object có constructor injection.
- Cần domainObjectContainer cho nhiều đối tượng có tên.
- Cần cấu hình nested object phức tạp hoặc file collection theo model riêng.

Ví dụ tạo property thủ công:

~~~groovy
def name = objects.property(String)
name.convention('Gradle')
~~~

**Đây là một lựa chọn cho build logic**, không phải lý do tự viết Property field và setters trong abstract managed extension.

## 4. Bí quyết thiết kế: nối extension với task mà không gọi get sớm

Hình dung:

~~~text
GreetingExtension.message  : Property<String>
                |
                | task.getMessage().set(extension.getMessage())
                v
GenerateGreetingTask.message: @Input Property<String>
                |
                | Gradle query lúc task cần value
                v
Generated output text
~~~

**Đúng:**

~~~java
task.getMessage().set(extension.getMessage());
~~~

**Kém:**

~~~java
task.getMessage().set(extension.getMessage().get());
~~~

Phiên bản thứ hai đọc value tại thời điểm configuration; có thể đóng băng default trước khi consumer cấu hình, hoặc fail nếu Provider chưa có value. Phiên bản đầu giữ value relationship tới lúc Gradle cần.

### 4.1. Không cần afterEvaluate

Một code smell:

~~~groovy
afterEvaluate {
    tasks.getByName('generateGreeting').message =
            greeting.message.get()
}
~~~

- Callback chạy muộn nhưng vẫn ở configuration phase.
- getByName có thể eager-realize task.
- get() lấy value sớm và khó truyền Provider.
- Plugin phụ thuộc thứ tự áp dụng/cấu hình.

Dùng tasks.register và **set(Provider)** đã diễn đạt đúng quan hệ.

### 4.2. Extension @Input không thay task @Input

Extension là model cấu hình. Chỉ đặt @Input trên getter của extension **không bảo đảm** Gradle track một task đang đọc extension qua Project API.

Custom task phải có managed getter gắn **@Input** hoặc input annotation phù hợp. Plugin nối extension provider tới task property. Đây mới là contract mà up-to-date check và caching cần.

## 5. Bài lab: binary plugin Java 17, consumer Groovy DSL

Bài lab tạo một Gradle plugin tên **com.example.typed-greeting**. Plugin expose typed extension và task generateGreeting. Task ghi file UTF-8 có 3 dòng cố định, sử dụng message, recipient, uppercase, tags, metadata và outputFile.

**Không cần server, secrets hay external library cho logic plugin.** Phần functional test tùy chọn dùng JUnit Jupiter.

### 5.1. Cấu trúc thư mục

~~~text
typed-extension-lab/
├── settings.gradle
├── build.gradle
├── gradlew                       # khi đã tạo Wrapper
├── gradlew.bat
├── gradle/wrapper/...
├── src/main/java/demo/
│   └── ReadGreeting.java        # kiểm tra artifact bằng javac/java
└── build-logic/
    ├── settings.gradle
    ├── build.gradle
    └── src/
        ├── main/java/com/example/gradle/
        │   ├── GreetingExtension.java
        │   ├── GenerateGreetingTask.java
        │   └── GreetingPlugin.java
        └── test/java/com/example/gradle/
            └── GreetingPluginFunctionalTest.java
~~~

- **build-logic** là một included build riêng chuyên biên dịch plugin.
- **Root build.gradle** tiêu thụ plugin qua plugins DSL.
- **ReadGreeting.java** là chương trình Java thuần, không chứa Gradle API imports.
- Cần JDK 17 và Gradle version tương thích; dùng Wrapper đã được tạo/commit trong project hoặc chạy gradle wrapper bằng Gradle đã cài trước.

### 5.2. Root settings.gradle

~~~groovy
pluginManagement {
    includeBuild('build-logic')
}

rootProject.name = 'typed-extension-lab'
~~~

Lệnh pluginManagement.includeBuild làm plugin binary ở build-logic khả dụng cho plugins block của root. Không dùng include('build-logic') như một subproject thông thường.

### 5.3. build-logic/settings.gradle

~~~groovy
rootProject.name = 'build-logic'
~~~

### 5.4. build-logic/build.gradle

~~~groovy
plugins {
    id 'java-gradle-plugin'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.encoding = 'UTF-8'
}

gradlePlugin {
    plugins {
        typedGreeting {
            id = 'com.example.typed-greeting'
            implementationClass = 'com.example.gradle.GreetingPlugin'
        }
    }
}

// Phục vụ TestKit/JUnit test ở phần sau.
dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**java-gradle-plugin** là Gradle core plugin; nó hỗ trợ đóng gói plugin descriptors và Gradle API classpath. **implementationClass** phải khớp tên Java class. Plugin ID consumer là **com.example.typed-greeting**, không phải tên khai báo typedGreeting.

### 5.5. GreetingExtension.java — public configuration API

**build-logic/src/main/java/com/example/gradle/GreetingExtension.java**

~~~java
package com.example.gradle;

import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.ListProperty;
import org.gradle.api.provider.MapProperty;
import org.gradle.api.provider.Property;

public abstract class GreetingExtension {

    public abstract Property<String> getMessage();

    public abstract Property<String> getRecipient();

    public abstract Property<Boolean> getUppercase();

    public abstract ListProperty<String> getTags();

    public abstract MapProperty<String, String> getMetadata();

    public abstract RegularFileProperty getOutputFile();
}
~~~

Đây là **abstract Gradle-managed type**, không có fields/setters/constructor đặc biệt. Gradle tạo implementation. Không cần @Input/@OutputFile trên extension vì extension không thực thi task.

### 5.6. GenerateGreetingTask.java — inputs/outputs có kiểu

**build-logic/src/main/java/com/example/gradle/GenerateGreetingTask.java**

~~~java
package com.example.gradle;

import java.io.File;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;

import org.gradle.api.DefaultTask;
import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.ListProperty;
import org.gradle.api.provider.MapProperty;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.CacheableTask;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.TaskAction;

@CacheableTask
public abstract class GenerateGreetingTask extends DefaultTask {

    @Input
    public abstract Property<String> getMessage();

    @Input
    public abstract Property<String> getRecipient();

    @Input
    public abstract Property<Boolean> getUppercase();

    @Input
    public abstract ListProperty<String> getTags();

    @Input
    public abstract MapProperty<String, String> getMetadata();

    @OutputFile
    public abstract RegularFileProperty getOutputFile();

    @TaskAction
    public void generate() throws IOException {
        String line = getMessage().get() + ", "
                + getRecipient().get() + "!";

        if (getUppercase().get()) {
            line = line.toUpperCase(Locale.ROOT);
        }

        StringBuilder text = new StringBuilder();
        text.append(line).append('\n');
        text.append("tags=")
                .append(String.join(",", getTags().get()))
                .append('\n');

        text.append("metadata=");
        boolean first = true;
        Map<String, String> sorted = new TreeMap<>(
                getMetadata().get()
        );

        for (Map.Entry<String, String> entry : sorted.entrySet()) {
            if (!first) {
                text.append(';');
            }
            text.append(entry.getKey())
                    .append(':')
                    .append(entry.getValue());
            first = false;
        }
        text.append('\n');

        File target = getOutputFile().get().getAsFile();
        Files.createDirectories(target.toPath().getParent());
        Files.writeString(
                target.toPath(),
                text.toString(),
                StandardCharsets.UTF_8
        );

        getLogger().lifecycle("Generated greeting at {}", target);
    }
}
~~~

**Đọc từng phần:**
1. Các getters là managed task properties do Gradle khởi tạo.
2. @Input trên **mọi value ảnh hưởng bytes** của output.
3. @OutputFile trên outputFile để Gradle biết artifact được tạo ở đâu.
4. @CacheableTask đánh dấu task type có khả năng cache khi outputs deterministic và inputs đầy đủ.
5. @TaskAction chỉ lấy get() ở execution time.
6. UTF-8, LF newline và Locale.ROOT giúp output ổn định.
7. TreeMap sắp xếp metadata keys để serialization deterministic.
8. Không gọi project.getExtensions() hay chạm Project state trong task action.
9. Không gọi Files.writeString ở plugin.apply().

**Cacheability không tự bật cache:** Muốn nhận FROM-CACHE phải bật build cache và có cache entry phù hợp. UP-TO-DATE có thể hoạt động dù cache tắt.

### 5.7. GreetingPlugin.java — extension và task wiring

**build-logic/src/main/java/com/example/gradle/GreetingPlugin.java**

~~~java
package com.example.gradle;

import java.util.List;
import java.util.Map;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class GreetingPlugin implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        GreetingExtension extension = project.getExtensions()
                .create("greeting", GreetingExtension.class);

        extension.getMessage().convention("Hello");
        extension.getRecipient().convention("Gradle");
        extension.getUppercase().convention(false);
        extension.getTags().convention(List.of("general"));
        extension.getMetadata().convention(
                Map.of("module", "demo")
        );
        extension.getOutputFile().convention(
                project.getLayout().getBuildDirectory()
                        .file("generated/greeting.txt")
        );

        project.getTasks().register(
                "generateGreeting",
                GenerateGreetingTask.class,
                task -> {
                    task.setGroup("documentation");
                    task.setDescription(
                            "Generates a greeting from typed properties"
                    );

                    task.getMessage().set(
                            extension.getMessage()
                    );
                    task.getRecipient().set(
                            extension.getRecipient()
                    );
                    task.getUppercase().set(
                            extension.getUppercase()
                    );
                    task.getTags().set(
                            extension.getTags()
                    );
                    task.getMetadata().set(
                            extension.getMetadata()
                    );
                    task.getOutputFile().set(
                            extension.getOutputFile()
                    );
                }
        );
    }
}
~~~

**Trọng tâm của bài học:**
- extensions.create đăng ký typed extension greeting.
- convention đặt defaults cho consumer override.
- tasks.register đăng ký task lazy.
- Mỗi **task.getX().set(extension.getX())** nối Provider, **không gọi extension.getX().get()**.
- OutputFile convention dùng buildDirectory Provider, không cố định root disk path.
- Plugin.apply không tạo file, không đợi afterEvaluate và không gọi task actions.

### 5.8. Root build.gradle — consumer Groovy DSL

**typed-extension-lab/build.gradle**

~~~groovy
plugins {
    id 'com.example.typed-greeting'
}

greeting {
    message.set('Hello')

    // -PrecipientName=Lan sẽ override default Mai từ Provider.
    recipient.set(
        providers.gradleProperty('recipientName').orElse('Mai')
    )

    uppercase.set(false)
    tags.set(['gradle', 'java17'])
    metadata.set([kind: 'lesson', level: 'basic'])

    outputFile.set(
        layout.buildDirectory.file('generated/greeting.txt')
    )
}
~~~

**Lưu ý:**
- Đây là Gradle **Groovy DSL** dù plugin implementation là **Java 17**.
- Extension có tên greeting nên block phải đúng tên ấy.
- getMessage() được Groovy DSL expose dưới short name message.
- recipient.set(Provider) giữ lazy value từ Gradle property.
- metadata là MapProperty<String,String>, không phải raw Map thuộc project.ext.
- Không cần application/java plugin cho root chỉ để chạy generateGreeting.

### 5.9. Chạy lab

Linux/macOS:

~~~bash
./gradlew generateGreeting --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat generateGreeting --console=plain
~~~

Khi task thực thi, nó tạo:

~~~text
build/generated/greeting.txt
~~~

**Nội dung UTF-8 chính xác của file:**

~~~text
Hello, Mai!
tags=gradle,java17
metadata=kind:lesson;level:basic
~~~

Task log của Gradle có thể chứa các dòng khác (tên task, trạng thái UP-TO-DATE, BUILD SUCCESSFUL...), vì vậy không nhầm **nội dung file** với **stdout toàn bộ Gradle invocation**.

### 5.10. Đổi value qua CLI mà không sửa plugin

~~~bash
./gradlew generateGreeting -PrecipientName=Lan --console=plain
~~~

Giá trị Provider từ build.gradle bây giờ là Lan. File trở thành:

~~~text
Hello, Lan!
tags=gradle,java17
metadata=kind:lesson;level:basic
~~~

Thay input có thể khiến task thực thi hoặc phục hồi đúng cache output. Không cần sửa Java plugin code hoặc dùng afterEvaluate.

Nếu consumer thay recipient.set(Provider) bằng recipient.set('Mai') cố định, -PrecipientName=Lan sẽ **không tự ghi đè** explicit value ấy.

### 5.11. Thử uppercase

Sửa block greeting trong root build.gradle:

~~~groovy
greeting {
    message.set('Hello')
    recipient.set('Mai')
    uppercase.set(true)
    tags.set(['gradle', 'java17'])
    metadata.set([kind: 'lesson', level: 'basic'])
    outputFile.set(layout.buildDirectory.file('generated/greeting.txt'))
}
~~~

Sau khi chạy task để cập nhật output:

~~~text
HELLO, MAI!
tags=gradle,java17
metadata=kind:lesson;level:basic
~~~

Locale.ROOT giúp uppercase ổn định giữa các máy. Sau phép thử, trả uppercase.set(false) và recipient Provider nếu muốn tiếp tục baseline.

### 5.12. Nếu không đặt block greeting

Chỉ áp plugin:

~~~groovy
plugins {
    id 'com.example.typed-greeting'
}
~~~

Các conventions trong plugin.apply() cho output mặc định:

~~~text
Hello, Gradle!
tags=general
metadata=module:demo
~~~

Đây là bằng chứng convention chỉ là default, còn set của consumer có thể thay. Nếu plugin ép finalizeValue() trước khi build.gradle cấu hình, việc override sẽ lỗi — vì thế không finalize quá sớm.

## 6. Kiểm chứng artifact bằng Java 17 thuần

Gradle plugin classes cần Gradle API để compile; không lấy GreetingPlugin.java chạy độc lập bằng javac/java thiếu Gradle API. Tuy nhiên file text mà plugin tạo có thể được kiểm chứng bằng một chương trình Java 17 nhỏ.

### 6.1. src/main/java/demo/ReadGreeting.java

~~~java
package demo;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public final class ReadGreeting {
    private ReadGreeting() {
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Expected one output file argument"
            );
        }

        String content = Files.readString(
                Path.of(args[0]),
                StandardCharsets.UTF_8
        );
        System.out.print(content);
    }
}
~~~

Reader không cần Gradle API và chỉ in bytes/text từ file plugin đã tạo.

### 6.2. Linux/macOS

Khôi phục cấu hình consumer như mục 5.8, rồi:

~~~bash
./gradlew generateGreeting --console=plain
mkdir -p build/manual-classes
javac -encoding UTF-8 -d build/manual-classes \
  src/main/java/demo/ReadGreeting.java
java -cp build/manual-classes demo.ReadGreeting \
  build/generated/greeting.txt
~~~

**Stdout riêng của Java ReadGreeting.main chính xác:**

~~~text
Hello, Mai!
tags=gradle,java17
metadata=kind:lesson;level:basic
~~~

### 6.3. Windows PowerShell

~~~powershell
.\gradlew.bat generateGreeting --console=plain
New-Item -ItemType Directory -Force build\manual-classes | Out-Null
javac -encoding UTF-8 -d build\manual-classes src\main\java\demo\ReadGreeting.java
java -cp build\manual-classes demo.ReadGreeting build\generated\greeting.txt
~~~

Java reader có cùng ba dòng output. Dấu phân tách classpath không quan trọng ở đây vì -cp chỉ có một thư mục.

**Không coi việc chạy Reader là một lượt TestKit plugin test:** Reader chỉ kiểm tra kết quả file, TestKit sẽ kiểm tra plugin wiring từ Gradle build tạm.

## 7. Kiểu file trong extension: tránh dùng String path

Với file input:

~~~java
public abstract RegularFileProperty getSpecFile();
~~~

Custom task có getter:

~~~java
@InputFile
@PathSensitive(PathSensitivity.RELATIVE)
public abstract RegularFileProperty getSpecFile();
~~~

Đoạn này minh họa một task khác, không thuộc GenerateGreetingTask.java. Khi task đọc nội dung spec file, @InputFile giúp Gradle theo dõi **nội dung file**, thay vì chỉ lưu một String filename.

Với output file:
- Dùng **@OutputFile RegularFileProperty**.
- Đặt default với project.layout.buildDirectory.file(...).
- Ghi file trong @TaskAction.
- Tránh nhiều tasks cùng sở hữu một file output.

Với output directory:

~~~java
@OutputDirectory
public abstract DirectoryProperty getGeneratedDirectory();
~~~

Với nhiều input files:

~~~java
@InputFiles
@PathSensitive(PathSensitivity.RELATIVE)
public abstract ConfigurableFileCollection getSources();
~~~

Đây là các getter của **task type**, cần import annotations và class types tương ứng trong file Java thật.

**Không thể thay tất cả bằng Property<File> hoặc ListProperty<String> paths** mà vẫn mong Gradle hiểu tự động producer dependencies, file snapshots và path normalization.

## 8. Optional properties và validation

Nếu một giá trị thực sự optional:

~~~java
@Optional
@Input
public abstract Property<String> getDescription();
~~~

Task có thể đọc:

~~~java
String description = getDescription().getOrElse("");
~~~

**Không gọi get() trên Property vắng value rồi mong nó trả null.** Gradle có thể báo thiếu giá trị.

Nếu muốn required value, không đặt convention và cho Gradle/task validation báo thiếu input khi task cần dùng. Với giá trị có default hợp lý, dùng convention để đảm bảo value khả dụng.

### 8.1. Domain validation khác type checking

Typed Property<Integer> chỉ đảm bảo value thuộc loại Integer, không tự đảm bảo số retries nằm trong 0..20.

Ví dụ task action:

~~~java
int maxRetries = getMaxRetries().get();
if (maxRetries < 0 || maxRetries > 20) {
    throw new org.gradle.api.GradleException(
            "maxRetries must be between 0 and 20"
    );
}
~~~

Đây là snippet của một task khác; bài lab chính không có maxRetries. Với Provider-based values, đặt domain validation ở điểm có thể query value hợp lệ, không gọi get() hàng loạt trong Plugin.apply() để “kiểm tra sớm” rồi phá laziness.

### 8.2. Nested managed configuration

Plugin lớn có thể có các group:

~~~text
report {
    output {
        format = 'html'
        prettyPrint = true
    }
}
~~~

Thay raw Map<String,Object> cho group output, có thể dùng một **managed nested type** với Property<String> getFormat() và Property<Boolean> getPrettyPrint().

Nếu task cần track object lồng nhau, dùng **@Nested** trên task getter và đảm bảo các nested getters có input annotations phù hợp. Không cho rằng @Nested tự biến bất kỳ object/field nào thành hợp lệ để cache.

Với nhiều đối tượng có tên (dev/staging/prod), cân nhắc **NamedDomainObjectContainer<T>** để có identities và typed configuration actions.

## 9. Functional test cho plugin bằng Gradle TestKit

Gradle TestKit kiểm tra plugin từ góc nhìn người tiêu thụ: nó tạo một Gradle build tạm, áp plugin ID, cấu hình extension, chạy task rồi so output.

build-logic/build.gradle ở mục 5.4 đã khai báo JUnit Jupiter và useJUnitPlatform. Gradle Plugin Development Plugin cung cấp TestKit plugin-under-test metadata cần cho **withPluginClasspath()** trong quá trình test.

### 9.1. GreetingPluginFunctionalTest.java

**build-logic/src/test/java/com/example/gradle/GreetingPluginFunctionalTest.java**

~~~java
package com.example.gradle;

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
    void generatesFileUsingTypedExtension() throws IOException {
        Files.writeString(
                projectDir.resolve("settings.gradle"),
                "rootProject.name = 'plugin-test'\n",
                StandardCharsets.UTF_8
        );

        String script = String.join(
                "\n",
                "plugins { id 'com.example.typed-greeting' }",
                "greeting {",
                "    message.set('Hello')",
                "    recipient.set('Test')",
                "    uppercase.set(true)",
                "    tags.set(['unit'])",
                "    metadata.set([suite: 'functional'])",
                "    outputFile.set(",
                "        layout.buildDirectory.file('generated/greeting.txt')",
                "    )",
                "}",
                ""
        );

        Files.writeString(
                projectDir.resolve("build.gradle"),
                script,
                StandardCharsets.UTF_8
        );

        BuildResult result = GradleRunner.create()
                .withProjectDir(projectDir.toFile())
                .withArguments("generateGreeting", "--stacktrace")
                .withPluginClasspath()
                .build();

        assertNotNull(result.task(":generateGreeting"));
        assertEquals(
                TaskOutcome.SUCCESS,
                result.task(":generateGreeting").getOutcome()
        );

        String output = Files.readString(
                projectDir.resolve("build/generated/greeting.txt"),
                StandardCharsets.UTF_8
        );

        assertEquals(
                "HELLO, TEST!\n"
                        + "tags=unit\n"
                        + "metadata=suite:functional\n",
                output
        );
    }
}
~~~

**Đây là functional test đầy đủ cho happy path:**
- @TempDir tạo workspace Gradle tạm.
- Test tạo settings.gradle và build.gradle như một user.
- GradleRunner.withPluginClasspath nạp plugin đang được test.
- Task generateGreeting phải có và thành công.
- Output file phải khớp chính xác expected UTF-8 string.
- Không phụ thuộc console logs, vốn có thể khác giữa phiên bản Gradle.

### 9.2. Chạy TestKit

Từ project root:

~~~bash
./gradlew -p build-logic test --console=plain
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat -p build-logic test --console=plain
~~~

Chỉ test class cụ thể:

~~~bash
./gradlew -p build-logic test \
  --tests "com.example.gradle.GreetingPluginFunctionalTest"
~~~

Cần JUnit dependencies đã được resolve và Gradle/JDK tương thích. Nếu TestKit build thất bại, xem stacktrace/test report thay vì xóa assertion hoặc bỏ task type annotations.

### 9.3. Những trường hợp nên test thêm

1. Không có greeting block → dùng conventions.
2. -PrecipientName đổi output khi build script dùng Provider từ property.
3. uppercase true/false tạo hai output tương ứng.
4. Sửa một input khiến task out-of-date khi cần.
5. Chạy lần hai không đổi cho kết quả UP-TO-DATE khi output còn hợp lệ.
6. Bật build cache và khôi phục output khi cache key phù hợp.
7. --configuration-cache có thể lưu và reuse configuration.
8. outputFile thay đổi vẫn có output hợp lệ đúng nơi.
9. Missing required value báo lỗi rõ.
10. Metadata map có key insertion order khác nhưng output vẫn deterministic.
11. Task không ghi file khi chỉ yêu cầu ./gradlew help.
12. Cấu hình kiểu sai được báo lỗi thay vì silently cast.

Đây là các **gợi ý mở rộng**, không phải mọi test đã được thực thi trong bài học này.

## 10. Managed properties, UP-TO-DATE và Configuration Cache

### 10.1. Khi nào Gradle bỏ qua task?

Task GenerateGreetingTask khai báo mọi value ảnh hưởng output bằng @Input và file bằng @OutputFile. Nếu task đã chạy thành công và inputs/outputs không đổi, task có thể:

~~~text
> Task :generateGreeting UP-TO-DATE
~~~

Nếu build cache được bật và cache entry hợp lệ:

~~~text
> Task :generateGreeting FROM-CACHE
~~~

**Hai trường hợp đều không chạy lại @TaskAction trong invocation đó.** Chúng khác với việc task executed nhưng vẫn tạo ra file có nội dung giống cũ.

### 10.2. Thử cache đúng cách

~~~bash
./gradlew generateGreeting --console=plain
./gradlew generateGreeting --console=plain
./gradlew generateGreeting --build-cache --console=plain
./gradlew generateGreeting --rerun-tasks --no-build-cache --console=plain
~~~

- Lượt 1 có thể execute nếu chưa có output.
- Lượt 2 có thể UP-TO-DATE.
- --build-cache cho phép cache lookup/store, nhưng không đảm bảo FROM-CACHE.
- --rerun-tasks ép xử lý task graph thay vì normal up-to-date/cache shortcuts.
- Các kết quả cụ thể còn phụ thuộc workspace và cache state.

### 10.3. Configuration Cache khác output cache

~~~bash
./gradlew generateGreeting --configuration-cache --console=plain
./gradlew generateGreeting --configuration-cache --console=plain
~~~

Configuration Cache giảm công việc cấu hình/task graph ở invocation tương thích; nó **không phải** kho chứa greeting.txt. Task vẫn có outcome riêng: executed, UP-TO-DATE, FROM-CACHE hoặc khác.

Thiết kế task dùng managed @Input/@Output properties và không đọc Project trong task action là một bước quan trọng hướng tới tương thích Configuration Cache.

**Không thể tuyên bố managed properties tự đảm bảo tương thích:** Các callbacks, build services, classloaders, custom plugins hoặc actions khác vẫn có thể vi phạm yêu cầu Configuration Cache.

### 10.4. Project reference trong task action là anti-pattern

~~~java
// Không dùng đoạn này trong GenerateGreetingTask.
@TaskAction
public void badAction() {
    String message = getProject()
            .getExtensions()
            .getByType(GreetingExtension.class)
            .getMessage()
            .get();
    getLogger().lifecycle(message);
}
~~~

Task action truy cập Project model ở execution time, không khai báo @Input Property của chính task. Thiết kế tốt hơn là plugin.apply wiring extension Provider vào task @Input property rồi task action chỉ đọc getMessage().get().

### 10.5. Không làm I/O ở Plugin.apply()

Anti-pattern:

~~~java
// Anti-pattern minh họa:
public void apply(Project project) {
    java.nio.file.Files.writeString(
            java.nio.file.Path.of("build/greeting.txt"),
            "Hello"
    );
}
~~~

Ngoài vấn đề checked exception trong snippet này, bản chất còn sai: khi người dùng chạy ./gradlew help, plugin cũng thực hiện side effect. Gradle không thấy task input/output contract. **Phải đưa I/O vào @TaskAction của task có @OutputFile**.

## 11. Những vấn đề thiết kế API cần cân nhắc

### 11.1. Không dùng String path cho mọi loại file

| Bài toán | Typed API phù hợp |
|---|---|
| Người dùng chọn một input file | RegularFileProperty |
| Task tạo một output file | @OutputFile RegularFileProperty |
| Task tạo một output directory | @OutputDirectory DirectoryProperty |
| Task đọc nhiều input files | @InputFiles ConfigurableFileCollection |
| Task nhận một chuỗi giá trị | Property<String> |
| Task nhận danh sách có thứ tự | ListProperty<T> |
| Task nhận cấu hình key-value | MapProperty<K,V> |

Đường dẫn có thể được nối bằng project.layout.buildDirectory.file(...) hoặc dir(...). File input cần normalization khi path có ý nghĩa/không có ý nghĩa với kết quả.

### 11.2. Không finalize extension quá sớm

Nếu trong Plugin.apply() bạn gọi extension.getMessage().finalizeValue(), consumer chưa cấu hình xong đã bị khóa. Dòng message.set('Hello') trong greeting {} có thể fail.

Chỉ finalize khi có lý do cần tính bất biến và đúng lifecycle. Gradle đã có cơ chế chốt task property khi task thực thi; đừng dùng finalization để chữa sai lazy wiring.

### 11.3. Validation có kiểu vẫn cần business rules

Property<Integer> cho retryCount không tự đảm bảo giá trị 0..10. Property<String> cho URL không tự đảm bảo URL hợp lệ. Một plugin production cần validation có thông báo rõ và thời điểm phù hợp.

Nếu Provider value chỉ có khi task được yêu cầu, validate ở task input/action thay vì bắt buộc get() tại configuration time.

### 11.4. Secrets không tự an toàn chỉ vì Property<T>

Managed Property không mã hóa token. Tránh:
- In secrets vào logger hoặc report.
- Đưa secret vào cached output.
- Dùng @CacheableTask cho task có network side effect mà không xem xét.
- Dùng @Internal để che một value thực sự ảnh hưởng task output, dẫn đến cache không đúng.

Với credentials, dùng APIs/secret manager đúng môi trường và chính sách cache phù hợp. Một task upload artifact lên remote thường không phải pure deterministic cacheable file-generation task.

### 11.5. Multi-project và ownership

Mỗi project có extension và tasks riêng. Nếu app cần artifact từ core, hãy dùng project dependency/outgoing artifact variant. Không lấy project(':core').extensions hoặc project(':core').tasks làm kênh trao đổi state nội bộ. Điều này quan trọng với Isolated Projects và build logic dễ bảo trì.

## 12. Troubleshooting các lỗi thực tế

### Lỗi 1 — Unknown property greeting

**Nguyên nhân:** Plugin chưa được áp hoặc extension chưa được đăng ký.

**Cách xử lý:** Kiểm tra main plugins block, plugin ID và project.extensions.create("greeting", GreetingExtension.class). Không thêm afterEvaluate để chờ một extension không tồn tại.

### Lỗi 2 — Plugin with ID com.example.typed-greeting not found

**Nguyên nhân:** Thiếu pluginManagement.includeBuild('build-logic'), java-gradle-plugin chưa cấu hình, hoặc implementationClass/ID sai.

**Cách xử lý:** Kiểm tra root settings.gradle, build-logic/build.gradle và GreetingPlugin.java package. Không tự thêm plugin portal để tìm plugin local chưa được build.

### Lỗi 3 — Could not create an instance of GreetingExtension

**Nguyên nhân:** Managed getter sai JavaBeans convention, kiểu getter không được hỗ trợ hoặc abstract class có abstract method khác mà Gradle không thể implement.

**Cách xử lý:** Public abstract getX() với Property/ListProperty/MapProperty/RegularFileProperty; tránh setters và constructors không tương thích. Với constructor injection, dùng @Inject/ObjectFactory đúng API.

### Lỗi 4 — Cannot query value because it has no value available

**Nguyên nhân:** Property chưa được set và không có convention, task gọi get().

**Cách xử lý:** Đặt convention nếu có default; nếu required thì thông báo/validation rõ, không tự dùng null.

### Lỗi 5 — Ghi trong greeting {} nhưng task vẫn dùng default

**Nguyên nhân:** Plugin đã query extension.getMessage().get() quá sớm thay vì set(Provider), hoặc finalize extension trước khi consumer set.

**Cách xử lý:** task.getMessage().set(extension.getMessage()); không cần afterEvaluate.

### Lỗi 6 — Không thể sửa property sau khi finalized

**Nguyên nhân:** finalizeValue/disallowChanges gọi quá sớm.

**Cách xử lý:** Để consumer cấu hình trước khi chốt, giữ lazy relationships và dùng conventions.

### Lỗi 7 — String "false" không hoạt động như Boolean false

**Nguyên nhân:** Dynamic map hoặc Groovy coercion bị hiểu sai.

**Cách xử lý:** Property<Boolean> và uppercase.set(false) với literal Boolean.

### Lỗi 8 — Task báo UP-TO-DATE dù input nghiệp vụ đã đổi

**Nguyên nhân:** Task không khai báo một value ảnh hưởng output dưới @Input hoặc plugin lưu stale value ở configuration time.

**Cách xử lý:** Audit mọi getX() trong @TaskAction, liên kết đúng @Input và Provider wiring.

### Lỗi 9 — Task luôn chạy lại dù dữ liệu không đổi

**Nguyên nhân:** Inputs nondeterministic, output thiếu @OutputFile, file bị xóa/ghi ngoài Gradle hoặc cache không phù hợp.

**Cách xử lý:** Xem --info logs, outputs, @Input model và các tác nhân bên ngoài; không chỉ ép UP-TO-DATE.

### Lỗi 10 — Output file ở sai thư mục

**Nguyên nhân:** Dùng new File("build/...") relative to process working directory hoặc hardcode path.

**Cách xử lý:** RegularFileProperty và project.layout.buildDirectory.file(...) để Gradle dùng project layout đúng.

### Lỗi 11 — Files.writeString báo NoSuchFileException

**Nguyên nhân:** Parent directory chưa tồn tại.

**Cách xử lý:** Files.createDirectories(target.toPath().getParent()) trước khi ghi, như task lab.

### Lỗi 12 — Thay đổi metadata khiến output có thứ tự khác nhau

**Nguyên nhân:** Serialize Map không ổn định.

**Cách xử lý:** Dùng TreeMap/sorted keys để có deterministic output, đặc biệt nếu @CacheableTask.

### Lỗi 13 — Một Gradle Property -P không đổi output

**Nguyên nhân:** Consumer set giá trị literal thay vì Provider, hoặc sai property name.

**Cách xử lý:** recipient.set(providers.gradleProperty('recipientName').orElse('Mai')) và truyền -PrecipientName=Lan.

### Lỗi 14 — ConfigCache fail khi @TaskAction đọc Project

**Nguyên nhân:** Task execution đọc Project.extensions hoặc Project.version.

**Cách xử lý:** Truyền managed inputs vào task từ plugin.apply, không giữ Project reference trong task action.

### Lỗi 15 — Task tạo file khi chỉ chạy ./gradlew help

**Nguyên nhân:** I/O nằm ở Plugin.apply hoặc configuration closure.

**Cách xử lý:** Di chuyển vào @TaskAction có @OutputFile; help không nên sinh greeting artifact.

### Lỗi 16 — TestKit không chạy

**Nguyên nhân:** Test đặt sai source set, thiếu JUnit Jupiter runtime, Gradle TestKit plugin classpath chưa được cấu hình hoặc Java/Gradle compatibility sai.

**Cách xử lý:** Kiểm tra build-logic/src/test/java, junit-bom/testRuntimeOnly launcher, java-gradle-plugin và GradleRunner.withPluginClasspath.

### Lỗi 17 — File path được khai báo là @Input String nhưng file contents đổi không invalidate

**Nguyên nhân:** Gradle theo dõi String path, không biết file content là input.

**Cách xử lý:** @InputFile RegularFileProperty với path sensitivity phù hợp; project.layout/Provider wiring.

### Lỗi 18 — Một task có side effect remote nhưng được đánh dấu @CacheableTask

**Nguyên nhân:** Task không còn là pure artifact generation, việc bỏ qua action có thể bỏ qua upload thực tế.

**Cách xử lý:** Thiết kế riêng upload task và policy cache; đừng giả định có typed properties thì remote side effects cacheable.

### Lỗi 19 — ListProperty.set ghi đè các tags đang có

**Nguyên nhân:** set đặt explicit collection mới, không phải append.

**Cách xử lý:** Dùng add/addAll khi muốn cộng thêm phần tử.

### Lỗi 20 — Plugin đã có typed extension nhưng vẫn cần afterEvaluate để lấy value

**Nguyên nhân:** Plugin đang đọc scalar value quá sớm hoặc wiring sai.

**Cách xử lý:** Dùng task.getX().set(extension.getX()) và lazy task registration; callback không cần thiết.

## 13. Checklist thiết kế extension trước khi phát hành

1. Tên extension rõ ràng, không trùng extensions phổ biến.
2. Public API có typed managed getters theo JavaBeans getX().
3. Không có unsupported abstract methods/setters trong managed class.
4. Không có hidden Project state read trong task action.
5. Các defaults dùng convention, không chốt quá sớm.
6. Required properties có thông báo lỗi đủ rõ.
7. File properties dùng RegularFileProperty/DirectoryProperty thay String.
8. Collections dùng ListProperty/MapProperty/SetProperty đúng semantics.
9. Task registrations dùng tasks.register và TaskProvider.
10. Extension values được wiring qua task Property.set(Provider).
11. Mọi dữ liệu ảnh hưởng outputs có input annotation.
12. Output file/dir có annotation và producer độc quyền phù hợp.
13. Task deterministic nếu được @CacheableTask.
14. Không tạo side effects trong plugin.apply.
15. Task action không đọc Project/Settings/Gradle model.
16. Gradle property/env Provider được sử dụng có chủ đích.
17. Không log tokens/secrets.
18. Có functional TestKit test và ít nhất một negative test.
19. Đã kiểm tra UP-TO-DATE, build cache và Configuration Cache theo policy.
20. Có hướng dẫn migration khi extension API đổi.
21. Tài liệu Groovy/Kotlin DSL có đúng tên getter và plugin ID.
22. Plugin được kiểm tra trên Gradle/JDK versions mà team hỗ trợ.

## 14. Bài tập và gợi ý đáp án

**Bài 1.** Extension có chức năng chính là thu cấu hình hay thực thi I/O?  
**Đáp:** Thu cấu hình. Task action mới tạo artifact.

**Bài 2.** Provider<String> và Property<String> khác nhau ở đâu?  
**Đáp:** Provider đọc value lazy; Property còn có set/convention để cấu hình.

**Bài 3.** Vì sao Property<boolean> không hợp lệ trong Java?  
**Đáp:** Generic type argument phải là reference type; dùng Boolean.

**Bài 4.** Managed getter của message nên đặt tên gì?  
**Đáp:** getMessage() theo JavaBeans convention.

**Bài 5.** Vì sao không new GreetingExtension trực tiếp?  
**Đáp:** Đó là abstract managed type; Gradle tạo implementation qua extensions.create.

**Bài 6.** Khác nhau giữa set và convention?  
**Đáp:** convention là fallback, set explicit value thắng convention nếu chưa finalized.

**Bài 7.** Vì sao task.message.set(extension.message) tốt hơn task.message.set(extension.message.get())?  
**Đáp:** Giữ Provider relationship và không query value quá sớm.

**Bài 8.** Đặt @Input chỉ trên extension có đủ để Gradle cache task đúng không?  
**Đáp:** Không. Task phải có @Input/@Output phù hợp và được wiring.

**Bài 9.** Một output file nên dùng Property<String> hay RegularFileProperty?  
**Đáp:** RegularFileProperty với @OutputFile trên task.

**Bài 10.** Nếu Property chưa có value/convention, gọi get() sẽ ra gì?  
**Đáp:** Gradle báo thiếu value, không mặc định trả null.

**Bài 11.** Trong lab, -PrecipientName=Lan thay được content vì sao?  
**Đáp:** Consumer truyền providers.gradleProperty('recipientName').orElse('Mai') tới recipient.set.

**Bài 12.** Task có @CacheableTask có chắc FROM-CACHE không?  
**Đáp:** Không. Phụ thuộc build cache bật, cache key/entry hợp lệ và outputs.

**Bài 13.** Vì sao output metadata được sắp xếp bằng TreeMap?  
**Đáp:** Để deterministic ordering và ổn định cacheable output bytes.

**Bài 14.** Khi thay một file input, nên track đường dẫn String hay nội dung file?  
**Đáp:** @InputFile + RegularFileProperty, path sensitivity phù hợp.

**Bài 15.** Vì sao không đọc extension bằng Project.getExtensions trong @TaskAction?  
**Đáp:** Nó tạo coupling với Project execution state, dễ vi phạm Configuration Cache và thiếu input modeling.

**Bài 16.** Khi cần nhiều environment objects có tên, dùng gì ngoài Map<String,Object>?  
**Đáp:** NamedDomainObjectContainer của typed managed elements.

**Bài 17.** Vì sao không finalize extension trong Plugin.apply()?  
**Đáp:** Consumer chưa cấu hình xong, set có thể bị từ chối.

**Bài 18.** TestKit kiểm gì mà javac/java Reader không kiểm?  
**Đáp:** Plugin application, DSL registration, task wiring/outcomes trong một Gradle build tạm.

**Bài 19.** Cùng file output nhưng task báo UP-TO-DATE nghĩa là @TaskAction có chạy lại không?  
**Đáp:** Không, task action được bỏ qua.

**Bài 20.** Secret string nằm trong typed Property có tự được mã hóa không?  
**Đáp:** Không. Cần chính sách credentials/logs/cache riêng.

**Bài 21.** Khi ListProperty.set([...]) được gọi hai lần, có phải hai lists được nối không?  
**Đáp:** Không. set sau thay explicit collection, muốn cộng thêm dùng add/addAll.

**Bài 22.** Vì sao typed extension hỗ trợ migration multi-project?  
**Đáp:** Mỗi project tự apply/configure một API rõ ràng, không cần truy cập Project.extensions ở module khác.

## 15. Tài liệu chính thức

- [Gradle User Manual — Binary Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_binary.html): plugin/extension/task anatomy, managed getters, conventions và lazy wiring.
- [Gradle User Manual — Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): java-gradle-plugin, descriptors và validatePlugins.
- [Gradle User Manual — Properties and Providers](https://docs.gradle.org/current/userguide/properties_providers.html): Gradle-managed types, JavaBeans properties và Provider APIs.
- [Gradle User Manual — Configuring Tasks Lazily](https://docs.gradle.org/current/userguide/lazy_configuration.html): set, convention, map, flatMap, finalization và typed file properties.
- [Gradle User Manual — Managed Types and Properties](https://docs.gradle.org/current/userguide/custom_gradle_types.html): các kiểu Property và interface/abstract managed objects.
- [Gradle User Manual — Developing Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): DefaultTask, @TaskAction, @Input/@Output.
- [Gradle User Manual — Incremental Build](https://docs.gradle.org/current/userguide/incremental_build.html): task inputs/outputs và UP-TO-DATE behavior.
- [Gradle User Manual — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task caching và cacheability.
- [Gradle User Manual — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): Project references trong task actions và Gradle configuration state.
- [Gradle User Manual — Gradle TestKit](https://docs.gradle.org/current/userguide/test_kit.html): GradleRunner và withPluginClasspath.
- [Gradle API — Property](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/Property.html): set/convention/finalization.
- [Gradle API — ListProperty](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/ListProperty.html): add/addAll/set.
- [Gradle API — MapProperty](https://docs.gradle.org/current/javadoc/org/gradle/api/provider/MapProperty.html): put/putAll/set.
- [Gradle API — RegularFileProperty](https://docs.gradle.org/current/javadoc/org/gradle/api/file/RegularFileProperty.html): typed regular file Provider.

**Ghi nhớ:** Hãy khai báo extension bằng **abstract JavaBeans managed getters**, đặt defaults bằng **convention**, để consumer dùng **set**, và nối giá trị qua **task Property.set(extension Property)** thay vì đọc get() sớm. Đặt **@Input/@OutputFile** trên task, tạo output trong **@TaskAction** và dùng TestKit để kiểm chứng plugin DSL. Managed properties tăng tính rõ ràng, lazy wiring và khả năng tích hợp Gradle caching nhưng không thay việc model hóa inputs/outputs, bảo vệ secrets hay kiểm tra business correctness.