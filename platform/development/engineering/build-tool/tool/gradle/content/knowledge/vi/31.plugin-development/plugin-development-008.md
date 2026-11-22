# Thông báo lỗi cấu hình rõ ràng và API tương thích về sau khi phát triển Gradle plugin

## 1. Hai trách nhiệm quan trọng của tác giả Gradle plugin

Một Gradle plugin tốt không chỉ chạy thành công trong môi trường của tác giả. Nó phải giúp người sử dụng biết **sai ở đâu, tại sao sai, sửa thế nào**, đồng thời giữ ổn định những phần của plugin mà các build scripts khác đã phụ thuộc.

Hai yêu cầu của bài học:

1. **Thông báo lỗi cấu hình có thể hành động:** nêu đúng plugin/task/property, điều kiện hợp lệ, nguyên nhân và hướng sửa; không để người dùng chỉ thấy `NullPointerException` hoặc `IllegalStateException: bad value`.
2. **API tương thích về sau:** thay đổi plugin ID, extension DSL, task names, public classes, properties, defaults, outputs, Gradle/JDK requirements và migration policy phải có kiểm soát.

Ví dụ lỗi nghèo ngữ cảnh:

~~~text
> Failed to apply plugin
> IllegalStateException: bad configuration
~~~

Ví dụ lỗi hữu ích:

~~~text
GRT-001 Invalid greeting configuration for :app:verifyGreeting:
greeting.message must contain non-whitespace text.
Set greeting { message.set("Hello") }.
~~~

Dòng ở ví dụ thứ hai có thể do mã plugin tạo ra. Toàn bộ **khung lỗi Gradle** như `FAILURE: Build failed...`, task path, thông báo đề nghị chạy `--stacktrace` và cách indent tùy Gradle version; không xây consumer test dựa vào nguyên văn toàn bộ console output.

Sau bài, bạn sẽ:

- Phân biệt lỗi **plugin application/configuration** với lỗi **task input validation/task execution**.
- Dùng `InvalidUserDataException` cho dữ liệu người dùng sai, `GradleException` cho lỗi build tổng quát, và **Gradle Problems API** để báo vấn đề có cấu trúc.
- Viết lỗi có property path, code, giới hạn, hướng sửa và tài liệu.
- Dùng `Property<T>`, `Provider<T>` và `convention` để không đọc cấu hình quá sớm.
- Xây **binary Gradle plugin bằng Java 17** qua `java-gradle-plugin` với extension/task rõ ràng.
- Chạy plugin trong một application consumer, tạo lỗi hợp lệ/cố ý và viết **Gradle TestKit functional tests**.
- Quản lý **hợp đồng API công khai**, deprecation, compatibility matrix, semantic versioning và migration.
- Tránh Gradle internal APIs, plugin order traps, Configuration Cache issues và các lỗi khó debug.

Các phần có đầy đủ tên file, cấu trúc project, mã Java và lệnh `javac`/`java` khi thích hợp. Các mảnh code riêng lẻ được ghi rõ là **mảnh bổ sung**, không phải chương trình độc lập.

## 2. Những gì người dùng thực sự coi là API của plugin

Một consumer thường viết:

~~~kotlin
plugins {
    id("dev.example.greeting")
}

greeting {
    message.set("Hello")
    maxLength.set(40)
}

tasks.named("check") {
    dependsOn("verifyGreeting")
}
~~~

Những thành phần sau trở thành hợp đồng:

| Thành phần | Ví dụ | Nếu thay đổi |
| --- | --- | --- |
| Plugin ID | `dev.example.greeting` | Consumer không resolve được plugin nếu ID cũ bị xóa. |
| Extension name | `greeting` | Kotlin/Groovy DSL block cũ không tồn tại. |
| Property name | `message`, `maxLength` | Getters/accessors/cấu hình đã viết có thể fail. |
| Property type | `Property<String>` | Đổi sang `String`/enum khác có thể phá source/binary compatibility. |
| Default | `message.convention("Hello")` | Output thay dù consumer không sửa script. |
| Validation rule | `maxLength` 1..120 | Siết giới hạn có thể làm build trước đây hợp lệ thất bại. |
| Task name | `verifyGreeting` | Lệnh CI `:app:verifyGreeting` không còn chạy. |
| Task input/output | `@Input` và report output paths | Up-to-date/cache, scripts tiêu thụ artifact bị ảnh hưởng. |
| Error code | `GRT-001` | Support và tests có thể dựa vào ID lỗi. |
| Public class | `GreetingExtension` | Client Java/Kotlin có thể import trực tiếp. |
| Supported Gradle/JDK | Ví dụ Gradle bản hỗ trợ Java 17 | Đổi min version ảnh hưởng CI và Wrapper. |
| Behavior | Task graph, plugin apply order | Build có thể khác kết quả dù source vẫn compile. |

**API không chỉ là Java methods.** DSL, plugin ID, defaults, output files, plugin application behavior và even error-code contract đều cần cân nhắc backward compatibility.

### Các mức tương thích

- **Source compatibility:** build script/client code cũ còn compile khi nâng plugin.
- **Binary compatibility:** class/client đã compile trước còn gọi được signatures cần thiết.
- **Behavioral compatibility:** output/artifact/task graph/defaults không đổi ngoài những thay đổi được thông báo.
- **Tooling compatibility:** plugin hoạt động trong Gradle CLI, IDE Tooling API, TestKit, Configuration Cache và những Gradle versions đã cam kết.

Một plugin có thể không xóa method nào nhưng đổi default output path; consumer vẫn compile nhưng quy trình release bị phá. Đó là **breaking behavioral change**.

## 3. Lỗi xuất hiện khi nào: application, configuration hay execution?

Gradle có initialization, configuration và task execution. Plugin thường được apply trong configuration.

~~~text
settings.gradle.kts
       |
       v
plugins { id("dev.example.greeting") }
       |
       v
GreetingPlugin.apply(Project)
       |
       +--> tạo extension greeting
       +--> đặt conventions
       +--> đăng ký VerifyGreetingTask (lazy)
       |
       v
consumer greeting { message.set("...") }
       |
       v
Gradle xác định task graph
       |
       v
task inputs được resolve/validate
       |
       v
VerifyGreetingTask.@TaskAction
       |
       +--> valid -> success
       +--> invalid -> InvalidUserDataException
~~~

Vì consumer cấu hình `greeting` **sau** khi Gradle apply plugin, không được đọc property quá sớm rồi báo lỗi giả.

### Ba loại lỗi phổ biến

| Lỗi | Khi nào đủ dữ liệu để báo? | Nơi xử lý |
| --- | --- | --- |
| Plugin bị apply lên root trong khi contract chỉ cho subproject | Ngay trong `Plugin.apply`. | Fail sớm bằng thông báo nêu target hợp lệ. |
| `greeting.message` chỉ có khoảng trắng | Sau khi cấu hình xong và property được resolve. | Task validation/`@TaskAction`. |
| Plugin không truy cập được output file | Khi task thực thi/ghi file. | Fail cùng đường dẫn output và cause, tránh leak secrets. |

**Không gọi `extension.getMessage().get()` trong `Plugin.apply`** chỉ để validate giá trị mà consumer vẫn có quyền `set(...)` ở những dòng sau. Khi cần một plugin-wide policy bắt buộc, cân nhắc validation task nối vào lifecycle phù hợp hoặc public domain-specific API có quy tắc rõ.

### `afterEvaluate` không phải giải pháp mặc định

`project.afterEvaluate { ... }` có thể đọc giá trị sau khi project configuration xong, nhưng thường tạo coupling theo thứ tự và khó tương thích lazy configuration, Isolated Projects và Configuration Cache. Nếu chỉ cần xác minh thuộc tính mà task dùng, chọn `Property/Provider` và task validation. Nếu bắt buộc fail lúc configuration, phải mô hình hóa chính xác thời điểm dữ liệu cuối cùng đã có; không thêm hook bất kỳ để né lỗi `get()` sớm.

### Task input validation của Gradle khác domain validation

Một task có:

~~~java
@Input
public abstract Property<String> getMessage();
~~~

Nếu property **không có giá trị**, Gradle có thể fail input validation **trước `@TaskAction`**. Nếu nó có giá trị là chuỗi trắng, annotation `@Input` không tự hiểu business rule “không blank”; custom task action cần kiểm tra. Vì thế không hứa mọi lỗi sẽ có cùng error code khi config hoàn toàn thiếu.

## 4. Thông báo lỗi nên có những trường gì?

Template:

~~~text
<STABLE_ERROR_CODE> <WHAT failed> at <project/task>
Property: <extension.property>
Reason: <specific constraint violated>
Expected: <allowed values or type>
Fix: <copyable Gradle DSL example>
Docs: <stable documentation URL, if available>
~~~

Ví dụ:

~~~text
GRT-002 Invalid greeting configuration for :app:verifyGreeting.
Property: greeting.maxLength
Received: 0
Expected: integer from 1 through 120
Fix in app/build.gradle.kts: greeting { maxLength.set(40) }.
~~~

Điểm quan trọng:
1. Ghi **task path** khi biết, vì cùng plugin có thể được apply trên 20 modules.
2. Ghi **property path** mà người dùng thấy trong DSL, không chỉ tên field internal.
3. Dùng **mã lỗi cố định**, không đặt tên lỗi theo data ngẫu nhiên.
4. Nói **giá trị/giới hạn hợp lệ** và **hành động sửa** thực tế.
5. Nếu lỗi đến từ service/tool ngoài, thêm tên service/exit code/endpoint (đã redact).
6. Giữ exception **cause** để `--stacktrace` còn hữu ích.
7. Nếu có link docs, dùng URL migration/troubleshooting thật và ổn định.
8. Không dump password, token, private key, secret path hoặc raw configuration nhạy cảm.

### Ví dụ Kotlin DSL và Groovy DSL

Kotlin:

~~~kotlin
greeting {
    message.set("Hello")
    maxLength.set(40)
}
~~~

Groovy:

~~~groovy
greeting {
    message.set('Hello')
    maxLength.set(40)
}
~~~

Ngôn ngữ script của consumer không nhất thiết giống ngôn ngữ viết plugin. Thông báo có thể đưa snippet theo một DSL rõ ràng rồi link tài liệu có cả hai.

## 5. Chọn `InvalidUserDataException` và `GradleException`

Hai classes công khai trong Gradle:
- `org.gradle.api.InvalidUserDataException`, subclass của `GradleException`, phù hợp **giá trị người dùng cung cấp không hợp lệ**.
- `org.gradle.api.GradleException` cho **lỗi build/plugin tổng quát** và có constructor với cause.

Ví dụ:

~~~java
throw new InvalidUserDataException(
    "GRT-002: greeting.maxLength must be 1..120. "
    + "Configure greeting { maxLength.set(40) }."
);
~~~

Ví dụ xử lý lỗi I/O có cause thật:

~~~java
try {
    // Thực hiện I/O cần thiết trong task action.
} catch (IOException cause) {
    throw new GradleException(
        "GRT-020 Cannot write greeting report. "
        + "Check the output directory and permissions.",
        cause
    );
}
~~~

Hai đoạn này là **mảnh minh họa**, không phải file Java hoàn chỉnh. Nếu bạn gặp `IllegalArgumentException` hoặc `IllegalStateException` từ helper internal, không phải mọi lỗi đều cần wrap; nhưng lỗi user-facing phải có ngữ cảnh. Không biến exception do bug trong implementation thành thông điệp “bạn cấu hình sai” một cách không chính xác.

### Bảng chọn cơ chế báo lỗi

| Mục đích | Công cụ | Kết quả |
| --- | --- | --- |
| Người dùng nhập property sai | `InvalidUserDataException` | Fail với message. |
| Lỗi hoạt động của plugin khi task không thể tiếp tục | `GradleException` (giữ cause) | Fail với stacktrace có ích. |
| Cảnh báo recoverable và migration | `ProblemReporter.report` | Structured warning, build tiếp tục. |
| Lỗi fatal cần structured reporting | `ProblemReporter.throwing` | Kết hợp exception và ProblemId/details/solution. |
| Ghi tiến trình vận hành bình thường | `logger.lifecycle`/`logger.info` | Log, không thay issue reporting. |

**Không báo cùng một cảnh báo hai lần** bằng cả Problems API và `logger.warn`. Gradle có thể hiển thị nó hai lần trong `--warning-mode=all`/IDE.

## 6. Bài thực hành: Gradle plugin Java 17 thực sự và consumer

Lab tạo plugin ID `dev.example.greeting`. Plugin đăng ký extension `greeting` và task `verifyGreeting`; task đọc các `Property` từ extension, kiểm tra domain rule và phát lỗi có cách sửa.

### 6.1. Cây file

~~~text
plugin-error-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/
│       ├── main/java/dev/example/gradle/
│       │   ├── GreetingExtension.java
│       │   ├── VerifyGreetingTask.java
│       │   └── GreetingPlugin.java
│       └── test/java/dev/example/gradle/
│           └── GreetingPluginFunctionalTest.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/App.java
~~~

Yêu cầu:
- Gradle Wrapper ở root đã được tạo và tương thích với JDK 17.
- JDK 17 có sẵn hoặc được Gradle toolchain resolver provision.
- Maven Central khả dụng khi tải JUnit lần đầu.
- Không cần publish plugin, Maven Local hoặc Docker; included build cung cấp plugin source.

### 6.2. Root `settings.gradle.kts`

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "plugin-error-lab"
include("app")
~~~

`includeBuild("build-logic")` thêm **một build độc lập** để Plugin DSL resolve ID. `include("app")` mới tạo root-build subproject `:app`. Đừng thay bằng `include("build-logic")` rồi nghĩ hai cơ chế giống nhau.

### 6.3. Root `build.gradle.kts`

~~~kotlin
plugins {
    base
}
~~~

Root không apply `dev.example.greeting` cho mọi subproject; app chủ động apply.

### 6.4. `build-logic/settings.gradle.kts`

~~~kotlin
rootProject.name = "build-logic"
~~~

### 6.5. `build-logic/build.gradle.kts`

~~~kotlin
plugins {
    `java-gradle-plugin`
}

group = "dev.example"
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
            id = "dev.example.greeting"
            implementationClass = "dev.example.gradle.GreetingPlugin"
            displayName = "Greeting Validation Plugin"
            description = "Demonstrates actionable errors"
        }
    }
}

dependencies {
    testImplementation(gradleTestKit())
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
~~~

`java-gradle-plugin` tạo plugin descriptors và cấu hình Gradle APIs/Plugin TestKit integration. Không cần tự tạo file `META-INF/gradle-plugins/dev.example.greeting.properties` khi dùng `gradlePlugin.plugins.create(...)` theo cách này. Tọa độ `group/version` là metadata của plugin-producing build; consumer ở cùng composite apply ID không cần publish.

`java.toolchain=17` chọn compiler JDK 17 cho plugin source. **Plugin JAR được biên dịch với Java 17** yêu cầu Gradle runtime JVM có khả năng load class-file Java 17; không tuyên bố hỗ trợ JVM 11 nếu chưa compile target phù hợp.

### 6.6. Extension `GreetingExtension.java`

~~~java
package dev.example.gradle;

import org.gradle.api.provider.Property;

public abstract class GreetingExtension {
    public abstract Property<String> getMessage();

    public abstract Property<Integer> getMaxLength();
}
~~~

Gradle hỗ trợ **managed abstract extension type** thông qua `Project.getExtensions().create(...)`. Property getters là public DSL contract; đừng đổi tên/return type trong minor release mà không có chiến lược migration.

### 6.7. Task `VerifyGreetingTask.java`

~~~java
package dev.example.gradle;

import org.gradle.api.DefaultTask;
import org.gradle.api.InvalidUserDataException;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.TaskAction;

public abstract class VerifyGreetingTask extends DefaultTask {
    @Input
    public abstract Property<String> getMessage();

    @Input
    public abstract Property<Integer> getMaxLength();

    @TaskAction
    public void verify() {
        String message = getMessage().get();
        int maxLength = getMaxLength().get();

        if (maxLength < 1 || maxLength > 120) {
            throw new InvalidUserDataException(
                "GRT-002 Invalid greeting configuration for "
                + getPath()
                + ": greeting.maxLength must be between 1 and 120 "
                + "(received " + maxLength + "). "
                + "Set greeting { maxLength.set(40) }."
            );
        }

        if (message.isBlank()) {
            throw new InvalidUserDataException(
                "GRT-001 Invalid greeting configuration for "
                + getPath()
                + ": greeting.message must contain non-whitespace text. "
                + "Set greeting { message.set(\"Hello\") }."
            );
        }

        if (message.length() > maxLength) {
            throw new InvalidUserDataException(
                "GRT-003 Invalid greeting configuration for "
                + getPath()
                + ": greeting.message length (" + message.length()
                + ") exceeds greeting.maxLength (" + maxLength + "). "
                + "Shorten the message or raise maxLength."
            );
        }

        getLogger().lifecycle("GREETING_CONFIG_OK=" + message);
    }
}
~~~

Điểm cần đọc kỹ:

1. `@Input` cho Gradle biết các properties tham gia task input model. Một property thiếu giá trị có thể bị Gradle input validation bắt trước TaskAction.
2. `Property.get()` được gọi lúc task action, **không** trong plugin apply, vì lúc đó consumer đã cấu hình xong.
3. `message.isBlank()` là Java API được hỗ trợ trên JDK 17.
4. Các lỗi có **mã cố định**, task path, property và ví dụ sửa.
5. Error `GRT-003` chỉ công bố độ dài chứ không dump nội dung message.
6. Task không tạo file output, không tự xưng là cacheable. Nó chạy validation và in lifecycle log khi được thực thi.
7. Đây là **domain validation ở task execution time**. Lệnh `help` có thể vẫn thành công dù consumer đặt message blank; chỉ khi task được yêu cầu hoặc được nối vào task khác mới phát hiện.

### 6.8. `GreetingPlugin.java`

~~~java
package dev.example.gradle;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public class GreetingPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        GreetingExtension extension =
            project.getExtensions().create(
                "greeting", GreetingExtension.class
            );

        extension.getMessage().convention("Hello from Gradle");
        extension.getMaxLength().convention(40);

        project.getTasks().register(
            "verifyGreeting",
            VerifyGreetingTask.class,
            task -> {
                task.setGroup("verification");
                task.setDescription(
                    "Validates the greeting plugin configuration"
                );

                // Nối Provider, không lấy giá trị sớm.
                task.getMessage().set(extension.getMessage());
                task.getMaxLength().set(extension.getMaxLength());
            }
        );
    }
}
~~~

**Phân tích API:**
- `Plugin<Project>`: plugin dành cho Gradle Project, không phải Settings/Gradle init target.
- `extensions.create` đăng ký public DSL block `greeting`.
- `convention` tạo defaults, consumer có thể `set`.
- `tasks.register` trả TaskProvider, dùng task configuration avoidance.
- `task.getMessage().set(extension.getMessage())` chuyển **Provider** từ extension sang task input, giữ tính lazy.
- Không dùng `afterEvaluate` và không gọi `get()` trong `apply`.
- Plugin cố tình **không** apply `java`: một project không cần Java vẫn có thể dùng task validation này.
- Nếu plugin cần integration với Java plugin, hãy apply required plugin hoặc dùng `pluginManager.withPlugin` theo contract, tránh phụ thuộc plugin order.

### 6.9. Consumer `app/build.gradle.kts`

~~~kotlin
plugins {
    id("dev.example.greeting")
    application
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.app.App")
}

greeting {
    message.set("Hello Gradle")
    maxLength.set(40)
}

// Khi app:check được gọi, kiểm tra cấu hình plugin.
tasks.named("check") {
    dependsOn("verifyGreeting")
}
~~~

Ở đây:
- `application` apply Java plugin conventions và tạo `run`/`check` tasks.
- `greeting` typed Kotlin accessor sinh nhờ plugin được apply qua `plugins` block.
- `check` explicitly phụ thuộc `verifyGreeting`. Đây là policy của sample, không phải Gradle tự nối mọi custom plugin tasks vào `check`.
- `run` **không** tự phụ thuộc `verifyGreeting`. Nếu nghiệp vụ bắt buộc validated config trước khi chạy app, cần nối task dependency hoặc validate trong task thực sự tiêu thụ config.

### 6.10. Java main `app/src/main/java/demo/app/App.java`

~~~java
package demo.app;

public final class App {
    private App() {
    }

    public static void main(String[] args) {
        System.out.println(
            "APP_JAVA_FEATURE=" + Runtime.version().feature()
        );
        System.out.println("ARG_COUNT=" + args.length);
    }
}
~~~

Với Java 17 toolchain thực sự và hai arguments, stdout của Java main:

~~~text
APP_JAVA_FEATURE=17
ARG_COUNT=2
~~~

Runtime feature được đo trực tiếp. Nếu chạy app bằng shell `java` thuộc JDK khác 17, dòng đầu sẽ phản ánh JDK đó.

### 6.11. Chạy lab

Từ root:

~~~bash
./gradlew --version
./gradlew projects
./gradlew :app:tasks --all

# Plugin với config hợp lệ.
./gradlew :app:verifyGreeting

# Java/Application check còn kéo verify task.
./gradlew :app:check

# App Java 17.
./gradlew -q :app:run --args="alpha beta"

# Kiểm thử và build plugin-producing build.
./gradlew :build-logic:test
./gradlew :build-logic:build
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat :app:verifyGreeting
.\gradlew.bat :app:check
.\gradlew.bat -q :app:run --args="alpha beta"
.\gradlew.bat :build-logic:test
~~~

Dòng lifecycle log do task verify in khi được thực thi:

~~~text
GREETING_CONFIG_OK=Hello Gradle
~~~

`--quiet` có thể ẩn lifecycle log; đừng đòi dòng này khi dùng `-q :app:verifyGreeting`. Java main vẫn in hai dòng đã nêu, chưa tính thêm Gradle warnings/logging tùy môi trường.

### 6.12. Ba cấu hình lỗi có chủ ý

**A. Blank message:** thay block greeting bằng:

~~~kotlin
greeting {
    message.set("   ")
    maxLength.set(40)
}
~~~

Chạy `./gradlew :app:verifyGreeting`, exception **message** chính xác:

~~~text
GRT-001 Invalid greeting configuration for :app:verifyGreeting: greeting.message must contain non-whitespace text. Set greeting { message.set("Hello") }.
~~~

**B. Invalid maxLength:**

~~~kotlin
greeting {
    message.set("Hello")
    maxLength.set(0)
}
~~~

Message:

~~~text
GRT-002 Invalid greeting configuration for :app:verifyGreeting: greeting.maxLength must be between 1 and 120 (received 0). Set greeting { maxLength.set(40) }.
~~~

**C. Message dài hơn giới hạn:**

~~~kotlin
greeting {
    message.set("Hello from Gradle")
    maxLength.set(5)
}
~~~

Chuỗi `Hello from Gradle` có 17 UTF-16 code units, nên message:

~~~text
GRT-003 Invalid greeting configuration for :app:verifyGreeting: greeting.message length (17) exceeds greeting.maxLength (5). Shorten the message or raise maxLength.
~~~

Đây là **ba lựa chọn thay thế**, không thêm cả ba vào file lab cùng lúc. Format lỗi Gradle bao quanh exception message sẽ thay đổi theo Gradle version; chỉ phần message plugin phát là cố định do Java code ở mục 6.7.

### 6.13. Kiểm tra Java độc lập với Gradle

Từ root, Linux/macOS:

~~~bash
mkdir -p build/manual
javac -encoding UTF-8 -d build/manual \
    app/src/main/java/demo/app/App.java
java -cp build/manual demo.app.App alpha beta
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual | Out-Null
javac -encoding UTF-8 -d build/manual app/src/main/java/demo/app/App.java
java -cp build/manual demo.app.App alpha beta
~~~

Khi JVM shell là JDK 17, stdout:

~~~text
APP_JAVA_FEATURE=17
ARG_COUNT=2
~~~

Lệnh này chỉ kiểm thử Java source/runtime, **không** xác minh Gradle plugin registration hoặc TestKit. Muốn chắc Gradle build logic đúng, phải chạy Wrapper tasks ở trên.

## 7. Khi nào validation phải xảy ra sớm trong `Plugin.apply`?

Nếu một invariant đã chắc chắn ngay khi plugin được apply, fail sớm có thể phù hợp. Ví dụ plugin chỉ được dùng ở subproject, không cho root:

~~~java
@Override
public void apply(Project project) {
    if (project == project.getRootProject()) {
        throw new InvalidUserDataException(
            "GRT-010 Plugin 'dev.example.greeting' must be "
            + "applied to a subproject, not root project '"
            + project.getName() + "'. "
            + "Move the plugin ID to app/build.gradle.kts."
        );
    }

    // Đăng ký extension/tasks.
}
~~~

Đây là **mảnh thay thế**, không áp vào GreetingPlugin của lab (lab không yêu cầu subproject-only). Đừng dựng một rule “chỉ cho subproject” không cần thiết rồi làm plugin thiếu tính tái sử dụng.

Cách phân biệt thời điểm lỗi:

~~~bash
# Nếu lỗi ngay application/configuration, help có thể fail.
./gradlew help

# Nếu lỗi trong verify task action, gọi verify mới thấy.
./gradlew :app:verifyGreeting
~~~

“Fail fast” có nghĩa **fail khi đã đủ dữ liệu và trước khi tạo output sai**, không phải “đọc mọi property ngay trong Plugin.apply”.

## 8. Gradle Problems API cho lỗi có cấu trúc

Gradle **Problems API** cung cấp structured diagnostics:
- `ProblemGroup`/`ProblemId` để phân loại và gom nhóm.
- `ProblemReporter.report(...)` cho warning recoverable.
- `ProblemReporter.throwing(...)` cho fatal problem gắn exception.
- `details(...)`, `solution(...)`, `documentedAt(...)`, optional AdditionalData.
- Output qua CLI, IDE/Tooling API và HTML Problems report khi có problem được báo.
- `--warning-mode=all` giúp thấy warnings chi tiết hơn trong console.

**Điều kiện phiên bản:** đây là API của Gradle hiện đại và có evolution qua các releases. Plugin muốn hỗ trợ Gradle cũ phải kiểm tra version/Javadoc hoặc giữ path `InvalidUserDataException` tương thích. Không compile against Problems API mới rồi quảng cáo hỗ trợ Gradle version không có class đó.

### 8.1. Inject `Problems` vào task

Mảnh Java minh họa một class riêng:

~~~java
import javax.inject.Inject;

import org.gradle.api.DefaultTask;
import org.gradle.api.GradleException;
import org.gradle.api.problems.ProblemId;
import org.gradle.api.problems.Problems;
import org.gradle.api.tasks.TaskAction;

public abstract class ExampleProblemTask extends DefaultTask {
    private final Problems problems;

    @Inject
    public ExampleProblemTask(Problems problems) {
        this.problems = problems;
    }

    @TaskAction
    public void demonstrate() {
        ProblemId id = problems.getGroups()
            .getGradle()
            .getBuildDefinition()
            .problemId("Greeting configuration is invalid");

        throw problems.getReporter().throwing(
            new GradleException("Invalid greeting configuration"),
            id,
            spec -> spec
                .details("The greeting message is missing")
                .solution(
                    "Set greeting.message in build.gradle(.kts)"
                )
        );
    }
}
~~~

Đây **không phải file bổ sung cần chạy trong lab**. Muốn dùng, thêm package, class vào plugin source, đăng ký task và thay `demonstrate()` bằng validation thật; code trên luôn fail có chủ đích.

- `ProblemId` phải ổn định và mô tả **loại vấn đề**, không nhét message/tên project/giá trị biến thiên vào ID.
- `Gradle > Build Definition` là một nhóm thích hợp cho cấu hình build/plugin không hợp lệ.
- `throwing(...)` gắn exception vào structured problem để IDE/Tooling API có bối cảnh.
- `report(...)` dành cho cảnh báo còn recoverable, không làm build fail một cách mặc định.
- Với một issue, chỉ report **một lần**; tránh gọi reporter và logger.warn cùng lúc.

### 8.2. Deprecation warnings với Problems API

Một plugin chuyển từ `greeting.text` sang `greeting.message` có thể báo warning:

~~~kotlin
val warningId = problems.groups.gradle.buildDefinition
    .problemId("Legacy greeting DSL is used")

problems.reporter.report(warningId) {
    details("greeting.text is deprecated")
    solution("Use greeting.message instead")
}
~~~

Đây là **mảnh Kotlin minh họa** khi `problems` đã được inject vào class; không phải file build.gradle.kts độc lập. Nhóm `Gradle > Deprecation` theo hướng dẫn Problems API dành riêng cho **Gradle core deprecations**, nên plugin custom không tự report vào nhóm reserved đó. Dùng nhóm phù hợp như Build Definition hoặc plugin-specific group.

Cảnh báo có thể không in toàn văn ở console mặc định mà xuất hiện trong Problems HTML report; muốn nhìn warning:

~~~bash
./gradlew :app:verifyGreeting --warning-mode=all
~~~

Khi có problems, Gradle thường tạo report ở `build/reports/problems/problems-report.html`; nếu không có reported problems, không có lý do bắt buộc report tồn tại.

### 8.3. Bảo mật báo lỗi

Đừng report đầy đủ API token/password vào exception hoặc `AdditionalData`. Message nên chỉ ghi key, yêu cầu hợp lệ và cách sửa:

~~~text
GRT-030 Publishing credentials are missing for target internal-repo.
Configure secret environment variables in your CI settings.
~~~

Không in raw token/secret dù dùng `--debug`. Thông tin có thể đi vào CI artifacts, IDE telemetry hoặc log storage.

## 9. API công khai: điều gì cần giữ ổn định?

Gradle plugin public contract bao gồm:
- **Plugin ID**, plugin marker/descriptor và supported target type.
- **Extension name**, public getters/setters, `Property<T>` return types.
- **Task names/types**, CLI options, expected inputs/outputs.
- **Behavioral defaults**, task dependencies, output path/format.
- **Error IDs** nếu đã document, deprecation warnings và migration behavior.
- **Minimum Gradle/JVM**, third-party plugin integration và classpath requirements.

### Hành vi được xem là breaking

| Thay đổi | Rủi ro |
| --- | --- |
| Xóa `dev.example.greeting` ID | Existing consumers không apply được. |
| Đổi DSL `greeting` thành `salutation` | Kotlin/Groovy scripts fail. |
| Đổi `getMessage(): Property<String>` sang `String getMessage()` | Source/binary signature breaking. |
| Siết `maxLength` từ 120 xuống 20 | Cấu hình đang hợp lệ đột nhiên fail. |
| Đổi `message.convention(...)` | Output thay dù consumer không sửa. |
| Đổi `verifyGreeting` sang `validateGreeting` | CI pipelines báo Task not found. |
| Thêm `check.dependsOn(verifyGreeting)` vào plugin | Nhiều builds sẽ chạy việc mới; có thể fail/chậm thêm. |
| Đổi output path của report | Scripts và artifact consumers tìm file cũ. |
| Đổi plugin Java bytecode target từ 11 sang 17 | Runtime JVM 11 không load được plugin class. |
| Dùng Gradle API chỉ có ở bản mới | Older Wrapper fail `NoSuchMethodError`/`NoClassDefFoundError`. |
| Thay error code `GRT-001` | Support/tests phụ thuộc code có thể vỡ. |

Không coi **toàn văn exception stacktrace** là public API. Có thể cải thiện wording khi vẫn giữ semantic category, error code và actionable information.

### Gradle public API khác internal

Dùng những APIs được Gradle docs xác định public, như `org.gradle.api.Plugin`, `Project`, `Property`, `TaskProvider` và các task annotations thích hợp. Tránh phụ thuộc `org.gradle.internal.*`/unpublished implementation details: những classes đó có thể đổi không theo compatibility guarantee.

Cũng cần theo dõi:
- `@Incubating`: API đang phát triển, có thể thay đổi khi chưa ổn định.
- `@Deprecated`: API đã có đường thay thế, cần đọc Upgrade Guide/Timeline.
- Gradle plugin API version/variants khi xây plugin hỗ trợ nhiều versions.
- ABI của external libraries mà plugin bundle.

**Đừng nhầm** task annotation `@Internal` với “Gradle internal API”. `@Internal` trên task property có nghĩa Gradle không coi nó là input/output tracked, và phải dùng đúng semantics; không dùng để che property thật sự ảnh hưởng output.

## 10. Migration API: đổi `text` thành `message` có kiểm soát

Giả sử một version cũ của plugin dùng:

~~~kotlin
greeting {
    text.set("Hello")
}
~~~

Version mới muốn:

~~~kotlin
greeting {
    message.set("Hello")
}
~~~

Nếu xóa `getText()` tức thì, tất cả scripts cũ fail. Một giải pháp chuyển tiếp là alias.

### 10.1. Giữ getter cũ như alias

Thay **toàn bộ GreetingExtension.java** trong lab bằng phiên bản:

~~~java
package dev.example.gradle;

import org.gradle.api.provider.Property;

public abstract class GreetingExtension {
    public abstract Property<String> getMessage();

    public abstract Property<Integer> getMaxLength();

    @Deprecated
    public Property<String> getText() {
        return getMessage();
    }
}
~~~

Cả tên `text` và `message` cùng trỏ vào **một backing Property**:
- Consumer cũ `text.set(...)` vẫn gán vào value logic.
- Consumer mới `message.set(...)` hoạt động.
- Java/Kotlin code import class có thể vẫn gọi `getText()`.
- `@Deprecated` báo hiệu khi compile Java code dùng API cũ; nó **không tự đảm bảo** warning trong Gradle DSL runtime. Nếu cần, thêm Problems warning có kiểm soát.

**Không dán hai versions của GreetingExtension.java cùng tên trong một project**.

### 10.2. Kế hoạch release

| Giai đoạn | Hành động | Consumer experience |
| --- | --- | --- |
| v1.x | `text` là property chính. | Build cũ chạy. |
| v2.0 chuyển tiếp | Thêm `message`, giữ `text` alias, cung cấp migration docs. | Cả cú pháp cũ/mới hoạt động. |
| v2.x | Ghi nhận warnings/usage, test cả hai và các plugin versions được hỗ trợ. | Có thời gian sửa build scripts. |
| v3.0 nếu policy cho phép | Xóa alias sau thời hạn được thông báo. | Breaking change rõ trong major release. |

Đây là **kế hoạch minh họa**, không phải release history của plugin lab.

### 10.3. Đổi plugin ID

Muốn từ `dev.example.greeting` sang `dev.example.build-greeting`, có thể đăng ký hai IDs ở `gradlePlugin.plugins` trong giai đoạn chuyển tiếp:

~~~kotlin
create("legacyGreeting") {
    id = "dev.example.greeting"
    implementationClass = "dev.example.gradle.GreetingPlugin"
}

create("newGreeting") {
    id = "dev.example.build-greeting"
    implementationClass = "dev.example.gradle.GreetingPlugin"
}
~~~

Đây là **mảnh cấu hình thay thế**, không dán đồng thời với `create("greeting")` của lab nếu gây duplicate ID. Nếu consumer apply **cả hai IDs**, Gradle có thể apply implementation qua hai IDs và task/extension registration trùng. Thiết kế guard/idempotence hoặc policy tránh double-application, và test trường hợp này. Cùng một implementation class không bảo đảm Gradle luôn chỉ gọi `apply` một lần khi có hai plugin IDs khác nhau.

## 11. Tránh plugin-order dependency

Một plugin nên hoạt động bất kể người dùng đặt nó trước hay sau plugin mà nó tích hợp.

Nếu **bắt buộc cần Java plugin**, có thể apply trong `Plugin.apply`:

~~~java
@Override
public void apply(Project project) {
    project.getPluginManager().apply("java");
    // Đăng ký Java conventions.
}
~~~

Đây là mảnh cho plugin khác, **không phải GreetingPlugin mặc định** (plugin lab không cần tự apply Java).

Nếu chỉ cần tích hợp **khi Java plugin hiện diện**, dùng callback:

~~~java
project.getPluginManager().withPlugin(
    "java",
    applied -> {
        project.getLogger().info(
            "Java plugin available for optional integration."
        );
    }
);
~~~

`withPlugin` đáp ứng cả trường hợp plugin đã apply trước và được apply sau. Mã thực tế cần cấu hình task/extension bằng public APIs, không chỉ in log. Dùng plugin-manager callback thay vì `afterEvaluate` chỉ để đoán thứ tự.

### Task names của plugin khác không phải mặc nhiên stable

Nếu plugin khác cung cấp extension DSL công khai, nên cấu hình qua extension. Nếu cần task wiring, ưu tiên task type/public interface thay vì hard-code undocumented task names. Nâng third-party plugin có thể đổi generated task names; tests cần kiểm tra integration.

## 12. Provider API giúp plugin extensible và ít lỗi timing

| API | Ý nghĩa | Lưu ý compatibility |
| --- | --- | --- |
| `convention(value)` | Default nếu consumer chưa set. | Dễ override. |
| `set(value)` | Gán tường minh. | Thắng convention. |
| `set(provider)` | Nối lazy source. | Không resolve ngay. |
| `get()` | Resolve value. | Tránh trong apply trước consumer configuration. |
| `getOrNull()`/`getOrElse(...)` | Đọc có nullable/fallback. | Không che error của input required. |
| `finalizeValue()` | Resolve ngay và khóa property. | Dễ quá sớm. |
| `finalizeValueOnRead()` | Khóa khi đọc lần đầu, lazily. | Hợp cho staged configuration. |
| `disallowChanges()` | Ngăn direct changes, có thể tiếp tục theo Provider đến khi finalized. | Document thời điểm khóa. |
| `disallowUnsafeRead()` | Ngăn đọc không an toàn trong project configuration. | Hỗ trợ chống premature read. |

Ví dụ consumer:

~~~kotlin
greeting {
    message.set(
        providers.gradleProperty("teamGreeting")
            .orElse("Hello")
    )
}
~~~

Hoặc environment:

~~~kotlin
greeting {
    message.set(
        providers.environmentVariable("TEAM_GREETING")
            .orElse("Hello")
    )
}
~~~

Provider API thể hiện dependence vào Gradle properties/environment thay vì truy cập `System.getenv` tùy ý trong code plugin. Điều này giúp Gradle theo dõi configuration inputs và hỗ trợ Configuration Cache.

**Không gọi `extension.getMessage().finalizeValue()` ngay trong apply** chỉ để “chặn mọi thay đổi”, vì consumer còn cấu hình DSL phía sau. Thay đổi thời điểm khóa giá trị cũng là behavioral API change và cần tests.

## 13. Task inputs, outputs và Configuration Cache

Một plugin sinh report file thay vì chỉ validate cần khai báo rõ:

~~~java
public abstract class GenerateGreetingReportTask extends DefaultTask {
    @Input
    public abstract Property<String> getMessage();

    @OutputFile
    public abstract RegularFileProperty getReportFile();

    @TaskAction
    public void generate() {
        // Ghi deterministic report từ declared inputs.
    }
}
~~~

Đây là **mảnh**, thiếu imports/package và nội dung generate thực; không phải file chạy độc lập.

Khi production:
- `@Input` cho những giá trị ảnh hưởng output.
- `@OutputFile`/`@OutputDirectory` cho outputs.
- `@Optional` cho field thật sự optional; tránh đánh dấu required input là optional chỉ để che lỗi.
- `@Nested` cho structured beans cần Gradle track.
- `@Internal` chỉ cho property **không ảnh hưởng** outputs/up-to-date model.
- Dùng output Provider để consumer đọc kết quả, không hard-code path.

Một anti-pattern:

~~~java
@TaskAction
public void executeTask() {
    String secret = getProject().getProperties()
        .get("mySecret").toString();
    // Dùng Project model trong task action.
}
~~~

Đây là **phản ví dụ**, dễ vi phạm Configuration Cache và có rủi ro lộ secret. Wire `Property`/`Provider` trong configuration, còn task action chỉ đọc declared inputs. Không đưa password vào `@Input` rồi log value: cả việc tracking, sensitivity và secret handling cần policy riêng.

### Đổi output path có thể phá consumer

Nếu `build/reports/greeting.txt` chuyển thành `build/generated/greeting.json`, consumers đang copy file cũ sẽ fail. Cần property `reportFile` có convention, migration timeline, test bằng output Provider và release notes. Không chỉ nói “method signatures chưa đổi nên backward-compatible”.

## 14. Gradle TestKit: kiểm tra cả thành công và lỗi

Gradle TestKit dùng `GradleRunner` để chạy một **fixture Gradle build thực** trong thư mục tạm. Nó kiểm thử plugin ID resolution, extension DSL, task setup, error message và output; đây là lớp test quan trọng hơn chỉ tạo Java object bằng `new`.

`java-gradle-plugin` hỗ trợ tạo metadata để `withPluginClasspath()` truyền plugin-under-test vào fixture build. JUnit Jupiter runtime được khai báo trong `build-logic/build.gradle.kts` của lab.

### 14.1. `GreetingPluginFunctionalTest.java`

~~~java
package dev.example.gradle;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertTrue;

class GreetingPluginFunctionalTest {
    @TempDir
    Path projectDir;

    private void createFixture(String value) throws IOException {
        Files.writeString(
            projectDir.resolve("settings.gradle"),
            "rootProject.name = 'fixture'\n"
        );

        Files.writeString(
            projectDir.resolve("build.gradle"),
            "plugins { id 'dev.example.greeting' }\n"
                + "greeting {\n"
                + "    message.set('" + value + "')\n"
                + "    maxLength.set(40)\n"
                + "}\n"
        );
    }

    @Test
    void succeedsWithValidConfiguration() throws Exception {
        createFixture("Hello TestKit");

        BuildResult result = GradleRunner.create()
            .withProjectDir(projectDir.toFile())
            .withPluginClasspath()
            .withArguments("verifyGreeting", "--console=plain")
            .build();

        assertTrue(
            result.getOutput().contains(
                "GREETING_CONFIG_OK=Hello TestKit"
            )
        );
    }

    @Test
    void failsWithClearMessageForBlankValue() throws Exception {
        createFixture("   ");

        BuildResult result = GradleRunner.create()
            .withProjectDir(projectDir.toFile())
            .withPluginClasspath()
            .withArguments("verifyGreeting", "--console=plain")
            .buildAndFail();

        String output = result.getOutput();
        assertTrue(output.contains("GRT-001"));
        assertTrue(
            output.contains(
                "greeting.message must contain non-whitespace text"
            )
        );
        assertTrue(
            output.contains(
                "Set greeting { message.set(\"Hello\") }"
            )
        );
    }
}
~~~

Phân tích:
- `@TempDir` cấp thư mục fixture riêng cho từng test.
- Test fixture dùng **Groovy DSL** `build.gradle` để kiểm tra plugin viết bằng Java vẫn apply từ Groovy; consumer chính của lab dùng Kotlin DSL.
- `withPluginClasspath()` lấy plugin-under-test từ metadata của `java-gradle-plugin`.
- `build()` mong thành công; `buildAndFail()` mong thất bại.
- Tests kiểm tra stable code `GRT-001` và actionable text, **không** assert nguyên toàn bộ stacktrace/Gradle console frame.
- `createFixture` nối các chuỗi cố định do tests kiểm soát; không đưa input chưa escape có ký tự apostrophe vào Groovy script.
- TestKit có thể tải Gradle distribution/repositories nếu chưa cache, nên CI phải chuẩn bị network hoặc caches.

### 14.2. Chạy tests

~~~bash
./gradlew :build-logic:test
./gradlew :build-logic:build
./gradlew :app:verifyGreeting
./gradlew :app:check
~~~

**Phân biệt lỗi:** nếu TestKit fixture không thể tải plugin/runtime/JUnit vì repository unreachable, đó là môi trường; không sửa expected GRT-001 để “test xanh”. Đọc cause và test reports.

### 14.3. Nên có ít nhất ba tầng test

| Tầng | Mục tiêu |
| --- | --- |
| Unit tests của domain validator | Blank, max length, bounds, message formatting. |
| TestKit functional tests | Apply ID, DSL, Provider wiring, tasks, success/fail, output. |
| Consumer compatibility matrix | Nhiều Gradle/JDK versions, Groovy/Kotlin, plugin order, config cache và published artifact. |

Một functional test “build successful” không bảo đảm mọi API migrations hoạt động. Cần thêm tests cho **legacy alias**, các task outputs và lỗi khi áp plugin ở project/DSL khác.

## 15. Ma trận tương thích Gradle/JDK và tooling

Plugin authors phải công bố và kiểm thử **dải phiên bản**, không chỉ Gradle trên laptop hiện tại.

| Trục | Test case nên có |
| --- | --- |
| Gradle runtime | Minimum supported Gradle, current stable, version đang chuẩn bị nâng. |
| Daemon JVM | Minimum supported JVM của plugin và một JVM mới đã được Gradle hỗ trợ. |
| Plugin compile bytecode | Java target tương thích JVM consumer. |
| App compile toolchain | Contract của application, có thể khác Daemon JVM. |
| Kotlin/Groovy consumer | `build.gradle.kts` và `build.gradle`. |
| Plugin application order | Required/optional plugins trước và sau plugin tự phát triển. |
| Missing/invalid values | Blank message, maxLength 0/121, missing required property. |
| Cache | `--configuration-cache` lần 1/lần 2, task up-to-date/output tracking. |
| Build structure | Single/multi-project, included build plugin resolution. |
| Release migration | Old DSL alias, new DSL name, stable task path. |

### TestKit chạy với Gradle version được chọn

~~~java
GradleRunner.create()
    .withProjectDir(projectDir.toFile())
    .withPluginClasspath()
    .withGradleVersion("9.2.0")
    .withArguments("verifyGreeting")
    .build();
~~~

Đây là **mảnh API** giả định đã có `projectDir` và plugin-under-test. Nó có thể cần tải Gradle distribution phù hợp và **không chứng minh** plugin hỗ trợ version đó chỉ vì gọi `withGradleVersion`. API/plugin dependencies compile trên Gradle mới có thể fail ở runtime cũ; test thật và compatibility adapters/variants khi cần.

### Phân biệt ba Java versions

1. **JVM chạy Gradle Daemon**: phải load được plugin bytecode.
2. **JDK compile plugin**: `java-gradle-plugin`/JavaCompile target trong `build-logic`.
3. **Toolchain compile/run Java application**: do `app/java.toolchain` lựa chọn.

Một plugin biên dịch class-file major 61 (Java 17) không chạy được trên JVM 11, bất kể app target Java 11/17. Đây là **binary compatibility contract**, không phải chỉ chi tiết build tool.

## 16. Semantic versioning và migration

Một chính sách tham khảo:
- **PATCH:** bugfix không làm gãy documented API/behavior; cải thiện error wording nhưng giữ stable error codes.
- **MINOR:** thêm property/feature có default backward-compatible, giữ aliases.
- **MAJOR:** có thể loại API cũ đã deprecate và có migration guide rõ.

Những thay đổi tưởng nhỏ vẫn có thể breaking:
- Default `message` thay đổi làm outputs khác.
- Validation từ warning chuyển sang fatal ở configuration time.
- `check` tự chạy task mới, làm CI chậm/fail.
- Task output path/classifier đổi.
- `Property.finalizeValue()` sớm hơn trước.
- Minimum Gradle/JDK tăng mà không thông báo.

### Alias property cũ `text` sang `message`

Phiên bản **thay thế** `GreetingExtension.java`:

~~~java
package dev.example.gradle;

import org.gradle.api.provider.Property;

public abstract class GreetingExtension {
    public abstract Property<String> getMessage();

    public abstract Property<Integer> getMaxLength();

    @Deprecated
    public Property<String> getText() {
        return getMessage();
    }
}
~~~

`getText()` trả cùng backing Property, nên DSL cũ `text.set("Hi")` và mới `message.set("Hi")` đều tác động giá trị chung. Nhưng `@Deprecated` là Java annotation; **không tự đảm bảo Gradle warning trong DSL**. Nếu muốn người dùng thấy cảnh báo, thêm Problems reporting/guide có kiểm soát.

Một migration policy minh họa:

| Giai đoạn | Chính sách |
| --- | --- |
| v1.x | `text` được hỗ trợ. |
| v2.x | Thêm `message`, giữ `text` alias, khuyến khích migration. |
| v2.x sau đó | Tests cả old/new DSL, document replacement và thời hạn. |
| v3.0 | Có thể bỏ alias nếu policy cho phép breaking change. |

Không tự suy đây là version thật của lab; đó là lịch deprecation mẫu.

### Đổi plugin ID

Nếu chuyển `dev.example.greeting` sang `dev.example.build-greeting`, có thể tạm register **hai plugin IDs**:

~~~kotlin
create("legacyGreeting") {
    id = "dev.example.greeting"
    implementationClass = "dev.example.gradle.GreetingPlugin"
}

create("newGreeting") {
    id = "dev.example.build-greeting"
    implementationClass = "dev.example.gradle.GreetingPlugin"
}
~~~

Đây là **mảnh thay thế trong `gradlePlugin.plugins`**. Nếu consumer apply hai IDs cùng lúc, Gradle có thể đăng ký extension/task trùng. Plugin cần idempotence/guard rõ và TestKit case cho double application; cùng class không đảm bảo apply một lần trên hai IDs.

## 17. Plugin order, Configuration Cache và Gradle public APIs

### Không phụ thuộc thứ tự plugin IDs

Nếu một plugin thật sự cần Java plugin:

~~~java
@Override
public void apply(Project project) {
    project.getPluginManager().apply("java");
    // Sau đó cấu hình Java conventions.
}
~~~

Đây là **mảnh** cho plugin có contract required Java, không thay GreetingPlugin lab vốn độc lập.

Nếu chỉ tích hợp **khi Java plugin có mặt**, dùng callback:

~~~java
project.getPluginManager().withPlugin(
    "java",
    applied -> {
        project.getLogger().info(
            "Java plugin available for optional integration."
        );
    }
);
~~~

Callbacks hỗ trợ trường hợp Java plugin đã apply hoặc apply sau; tránh hard-code thứ tự `plugins` blocks trong consumer.

### Không dùng Gradle internals

Tránh `org.gradle.internal.*` và undocumented implementation methods. Ưu tiên documented public APIs và đọc Upgrade Guide. Các APIs `@Incubating` có rủi ro thay đổi, và `@Deprecated` cần timeline migration.

### Tránh truy cập Project model từ task action

Phản ví dụ:

~~~java
@TaskAction
public void run() {
    String value = getProject().getProperties()
        .get("teamGreeting").toString();
}
~~~

Đây là **anti-pattern** cho Configuration Cache/Isolated Projects và thiếu input tracking. Nên wire `Property<String>` từ `providers.gradleProperty(...)` trong configuration và task chỉ đọc annotated input.

### Output/task API cũng cần ổn định

Nếu plugin tạo report:

~~~java
public abstract class ReportTask extends DefaultTask {
    @Input
    public abstract Property<String> getMessage();

    @OutputFile
    public abstract RegularFileProperty getReportFile();

    @TaskAction
    public void generate() {
        // Ghi deterministic report từ declared inputs.
    }
}
~~~

Mảnh Java này cần imports/package và implementation thật. Dùng `@OutputFile`, Provider wiring, stable output path/format. Không gắn `@Internal` lên input ảnh hưởng output chỉ để né Gradle validation, vì cache có thể phục hồi report cũ sai.

## 18. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| `Plugin not found: dev.example.greeting` | ID/descriptor sai hoặc chưa include build-logic. | Kiểm tra `pluginManagement.includeBuild`, `gradlePlugin.plugins`, implementationClass. |
| `Class not found GreetingPlugin` | Package/implementationClass không khớp. | Đối chiếu Java package/file path. |
| `Unresolved reference greeting` | Extension không đăng ký, plugin không apply sớm. | Dùng `plugins { id(...) }` và đúng extension name. |
| `Cannot change finalized property` | Property đọc/finalize trước consumer set. | `convention` và Provider wiring, tránh `get()` sớm. |
| `:app:verifyGreeting` không có | Plugin chưa apply ở app hoặc đổi task name. | Xem `:app:tasks --all`, kiểm tra version. |
| `help` pass nhưng verify fail | Domain validation trong TaskAction. | Đúng theo lab; chạy verify hoặc nối `check`. |
| `run` pass nhưng config greeting sai | `run` không phụ thuộc verify. | Nối dependency nếu nghiệp vụ yêu cầu. |
| `No value has been specified for property` | Required `@Input` thiếu. | Đặt convention hoặc cấu hình, không đánh dấu @Optional tùy tiện. |
| `NoSuchMethodError` khi nâng Gradle | Plugin dùng API version khác runtime. | Kiểm tra public APIs/compatibility matrix. |
| `Unsupported class file major version` | Plugin bytecode yêu cầu JVM mới hơn. | Đổi target hoặc nâng supported Daemon JVM. |
| Problems warning không hiện | Mặc định warning có thể nằm ở report. | `--warning-mode=all` và mở Problems report. |
| Warning hiển thị hai lần | Reporter và logger.warn cùng issue. | Chọn một cách báo. |
| `GRT-001` wording không còn giống test | Assert nguyên full console output. | Assert stable error code/semantic fields. |
| TestKit `withPluginClasspath` lỗi | Plugin-under-test metadata/classpath chưa đúng. | Dùng `java-gradle-plugin`, test dependencies chuẩn. |
| TestKit không tải Gradle/JUnit | Network/cache/CI environment. | Phân biệt infra failure với plugin failure. |
| Old DSL `text` không tồn tại | Getter cũ bị xóa. | Giữ alias/deprecation migration. |
| Hai plugin IDs trùng implementation tạo duplicate tasks | Plugin apply hai lần qua hai IDs. | Guard/idempotence + functional test. |
| Plugin chỉ chạy khi Java plugin đứng trước | Phụ thuộc apply order. | Apply required plugin hoặc `withPlugin`. |
| Task report có cache lỗi | Thiếu declared inputs/outputs. | `@Input`, `@OutputFile`, Providers. |
| Log có password/token | Exception dump raw values. | Chỉ nêu property key, redact secrets. |

## 19. Checklist trước khi phát hành plugin

- [ ] Plugin ID/extension/task names được công bố rõ.
- [ ] Public getters/property types có chiến lược backward compatibility.
- [ ] Defaults dùng `convention` nếu consumer cần override.
- [ ] Không đọc input quá sớm trong `Plugin.apply`.
- [ ] Phân biệt validation khi configuration với khi task execution.
- [ ] Exceptions có code, project/task/property, expected value và hướng sửa.
- [ ] Problems API dùng khi cần structured warnings/failures, không duplicate logger.
- [ ] Lỗi không in secrets hoặc sensitive AdditionalData.
- [ ] `@Input`/`@OutputFile`/`@Optional` dùng đúng bản chất.
- [ ] `tasks.register`/Providers hỗ trợ lazy configuration.
- [ ] Không dùng Gradle internal/undocumented APIs.
- [ ] Plugin hoạt động với hai thứ tự apply có ý nghĩa.
- [ ] Tests cho Kotlin/Groovy consumer DSL.
- [ ] Gradle TestKit success/failure tests có assertions vào error codes.
- [ ] Kiểm tra Configuration Cache và Gradle versions/JDK versions đã cam kết.
- [ ] Không nâng minimum supported Gradle/JVM trong patch một cách im lặng.
- [ ] Migration giữ alias/deprecation khi cần.
- [ ] Changelog nêu behavioral changes, task graph/output changes.
- [ ] CI kiểm thử plugin JAR/artifact được publish, không chỉ source build.
- [ ] Tài liệu ghi lệnh chẩn đoán `--stacktrace`, `--info`, `--warning-mode=all`.

## 20. Câu hỏi tự kiểm tra

1. Vì sao `InvalidUserDataException` phù hợp cho user-supplied configuration sai?
2. `Plugin.apply` có nên gọi `extension.getMessage().get()` ngay không, và vì sao?
3. Validation trong `@TaskAction` khác lỗi `Plugin.apply` khi chạy `./gradlew help` thế nào?
4. `@Input` có tự hiểu quy tắc message không blank không?
5. Vì sao message error nên có task path và property path?
6. Có nên in raw token vào Problems API AdditionalData không?
7. `ProblemReporter.report` và `throwing` khác nhau thế nào?
8. Nếu warning đã được report, có nên log warning đó thêm lần nữa không?
9. Default `message.convention` khác `set` thế nào?
10. Vì sao `finalizeValue()` sớm có thể phá consumer build?
11. Đổi plugin ID có phải breaking change không?
12. Đổi `Property<String>` getter sang `String` có thể phá binary compatibility ra sao?
13. Giữ `getText() { return getMessage(); }` có lợi ích gì?
14. `@Deprecated` có tự đảm bảo console warning khi người dùng DSL gọi property cũ không?
15. Tại sao không assert toàn bộ Gradle stacktrace trong TestKit?
16. `withPluginClasspath()` lấy plugin-under-test từ đâu?
17. `buildAndFail()` dùng trong trường hợp nào?
18. App compile bằng Java 17 có nghĩa Gradle Daemon chạy Java 17 không?
19. Vì sao không nên dùng `org.gradle.internal.*` trong public plugin?
20. `pluginManager.withPlugin` giúp tránh lỗi nào?
21. Một task sinh report cần khai báo những input/output nào?
22. Đổi output path có thể breaking dù Java method signatures không đổi không?
23. TestKit `withGradleVersion` có tự đảm bảo compatibility không?
24. Cần những trục nào trong Gradle/JDK/DSL compatibility matrix?
25. Có nên áp đồng thời plugin ID cũ và mới mà không test idempotence không?

## 21. Tài liệu Gradle chính thức

- [Gradle — Binary Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_binary.html): `java-gradle-plugin`, `Plugin<Project>`, extension/task design và descriptors.
- [Gradle — Reporting Plugin Problems](https://docs.gradle.org/current/userguide/reporting_problems.html): `Problems`, `ProblemId`, `ProblemReporter.report`/`throwing`, HTML report.
- [Gradle — InvalidUserDataException](https://docs.gradle.org/current/javadoc/org/gradle/api/InvalidUserDataException.html): lỗi do user-supplied build data không hợp lệ.
- [Gradle — Public APIs](https://docs.gradle.org/current/userguide/public_apis.html): ổn định public vs internal APIs.
- [Gradle — General Best Practices](https://docs.gradle.org/current/userguide/best_practices_general.html): plugin order, apply conventions và compatibility.
- [Gradle — Best Practices for Tasks](https://docs.gradle.org/current/userguide/best_practices_tasks.html): tránh hard-code undocumented task names.
- [Gradle — Lazy Configuration](https://docs.gradle.org/current/userguide/lazy_configuration.html): `Provider`, `convention`, `finalizeValueOnRead`.
- [Gradle — Gradle TestKit](https://docs.gradle.org/current/userguide/test_kit.html): `GradleRunner`, `withPluginClasspath`, `buildAndFail`.
- [Gradle — Compatibility Matrix](https://docs.gradle.org/current/userguide/compatibility.html): Gradle/JDK support.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): task action constraints và input tracking.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): `pluginManagement.includeBuild` trong plugin development.
