# Thiết kế extension để module khai báo nhu cầu thay vì sửa cơ chế trong Gradle

## 1. Mục tiêu và vấn đề thực tế

Trong một hệ thống có nhiều Java modules (`:api`, `:service`, `:cli`, `:sdk`), team muốn áp dụng chung những quy tắc như kiểm tra tài liệu public API, chọn JDK, quản lý task `check` và tạo báo cáo. Một lối triển khai dễ thấy là copy vào từng `build.gradle.kts`:

```kotlin
// Cách tiếp cận khó bảo trì khi lặp lại ở nhiều module.
tasks.register("checkApiDocs") {
    doLast {
        if (!file("README.md").exists()) {
            error("Missing API documentation")
        }
    }
}
tasks.named("check") {
    dependsOn("checkApiDocs")
}
```

Mỗi khi chính sách thay đổi, mọi module lại sửa task logic. Module nào không có API công khai thì xóa task, module cần yêu cầu đặc biệt thì thêm `if (project.name == "...")`. Dần dần build scripts chứa đầy implementation details, trách nhiệm policy không rõ, task outputs không khai báo và Gradle caching khó hoạt động đúng.

**Giải pháp** là thiết kế **shared build logic** dưới dạng Gradle plugin và công bố **typed extension**. Các modules chỉ cần khai báo thuộc tính hoặc nhu cầu của mình:

```kotlin
plugins {
    id("com.example.module-needs")
}

moduleNeeds {
    owner.set("api-team")
    publicApi.set(true)
    apiDocumentation.set(layout.projectDirectory.file("README.md"))
}
```

Module đang phát biểu: “Tôi thuộc team API; tôi có public API; file tài liệu của tôi ở đây”. Nó **không** tự quyết định phải tạo loại task nào, chạy task lúc nào, định dạng báo cáo gì hoặc cấu hình `check` thế nào. Toàn bộ cơ chế được một **plugin chung** đảm nhiệm.

Sau bài học, bạn sẽ:

1. Phân biệt `ExtensionContainer`, typed extension, Gradle `Property`/`Provider`, convention plugin và custom task.
2. Thiết kế extension dùng **ngôn ngữ nhu cầu**, không phơi bày cách thực thi.
3. Viết demo hoàn chỉnh với Java 17, Gradle Kotlin DSL và included build `build-logic`.
4. Kết nối extension properties sang task `@Input`/`@InputFile`/`@OutputFile` **không gọi `get()` sớm**.
5. Áp dụng cùng một plugin cho hai modules có yêu cầu khác nhau.
6. Gắn verification vào `check` bằng `TaskProvider`, tránh copy task definitions.
7. Phân biệt `convention()` với `set()` và các loại property khác nhau.
8. Xác nhận các case PASS/FAIL, cache, configuration cache, TestKit và CI.
9. Biết khi nào cần enum, nested extension, container hoặc tách plugin.
10. Tránh `afterEvaluate`, sửa trực tiếp task từ modules và bypass quality gate.

**Thông điệp cốt lõi:** **module khai báo *điều mình cần***; **shared plugin chịu trách nhiệm *thực hiện điều đó***. Extension là một **hợp đồng cấu hình**, không phải nơi đặt lại toàn bộ build engine.

## 2. Kiến trúc và trách nhiệm

```text
Module api / service
        |
        | moduleNeeds { owner; publicApi; apiDocumentation }
        v
Gradle ExtensionContainer
        |
        | Property<T>, RegularFileProperty, convention(...)
        v
ModuleNeedsExtension  (public DSL contract)
        |
        | Property / Provider wiring
        v
ModuleNeedsPlugin     (shared implementation)
        |
        +--- apply java-library + Java toolchain convention
        +--- register VerifyModuleNeedsTask lazily
        +--- check.dependsOn(verifier)
        |
        v
VerifyModuleNeedsTask
        |
        +--- @Input owner/publicApi
        +--- @Optional @InputFile apiDocumentation
        +--- @OutputFile report
        |
        v
module/build/reports/module-needs/status.txt
```

| Tầng | Ai sở hữu? | Được sửa điều gì? |
| --- | --- | --- |
| Module `build.gradle.kts` | Team phát triển module | Owner, có public API không, file tài liệu ở đâu |
| `ModuleNeedsExtension` | Team build/platform | Tên properties, types, defaults, public DSL |
| `ModuleNeedsPlugin` | Team build/platform | Apply plugins, tạo tasks, nối lifecycle |
| `VerifyModuleNeedsTask` | Team build/platform | Inputs/outputs, validation, báo cáo, caching |
| CI | DevOps/release engineering | Task invocation, artifact collection, merge/release gates |

Một nhu cầu tốt có tính **ổn định** khi implementation thay đổi. Ví dụ, team có thể đổi trình phân tích docs, thêm XML/JSON report hoặc nâng Gradle API mà không bắt tất cả module sửa `moduleNeeds { ... }`.

Các thuộc tính có ý nghĩa nên đưa vào extension:

- `publicApi: Property<Boolean>`: module có API cho bên ngoài sử dụng.
- `owner: Property<String>`: team chịu trách nhiệm.
- `apiDocumentation: RegularFileProperty`: file đầu vào mà module lựa chọn.
- `qualityProfile: Property<Enum>`: chính sách đã định nghĩa sẵn nếu có nhiều mức.
- `requiredCapabilities: SetProperty<String>`: nhu cầu capabilities (khi thực sự cần).

Những chi tiết **không nên** bắt modules tự quản lý:

- Tên và class của verification task.
- Task outputs path được CI thu thập.
- `@Input`/`@OutputFile` annotations.
- Cách tính Gradle task graph hay `check.dependsOn`.
- Nội dung shell command chạy analyzer.
- Quy tắc global về caching/Gradle Workers API.

Nếu extension yêu cầu module tự đặt `internalTaskName`, `taskDependsOn`, `scriptToExecute` và `disableEverything`, nó đã mất mục tiêu khai báo nhu cầu.

## 3. Extension khác gì task, plugin và dependency configuration?

**Plugin** là code được apply vào `Project`, có thể thêm tasks, extensions, configurations, dependencies và conventions.

**Extension** là object cấu hình được đăng ký trong `project.extensions` với một tên, ví dụ `moduleNeeds`. Gradle Kotlin DSL có thể tạo type-safe accessor cho extension được plugin áp dụng trong `plugins { }`:

```kotlin
moduleNeeds {
    publicApi.set(true)
}
```

**Task** thực hiện công việc khi Gradle xây execution graph; custom task có `@TaskAction` và task inputs/outputs.

**Configuration** (`implementation`, `runtimeClasspath`) quản lý dependency resolution và variants, không phải nơi lưu mọi giá trị cấu hình tùy ý của plugin.

**Convention** là giá trị mặc định của một managed property, ví dụ `owner.convention(project.name)`. Nó có thể được consumer override bằng `set(...)`.

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Extension name | `moduleNeeds` | API DSL của plugin |
| Extension property | `publicApi: Property<Boolean>` | Nhu cầu module |
| Default convention | `publicApi.convention(false)` | Fallback |
| Override | `publicApi.set(true)` | Module khai báo nhu cầu riêng |
| Task registration | `tasks.register("verifyModuleNeeds", ...)` | Định nghĩa cơ chế/lifecycle |
| Provider mapping | `task.publicApi.set(extension.publicApi)` | Nối cấu hình với task |
| Task action | `@TaskAction` | Kiểm tra và ghi output lúc execute |

**Không dùng extension như một biến global mutable** để modules có thể ghi vào tùy thời điểm. Mỗi project có extension instance riêng, không phải một object singleton dùng chung cho mọi modules.

## 4. Vì sao Gradle Provider API phù hợp với extension?

Một Java class thông thường có field:

```java
public boolean publicApi = false;
```

khó biểu diễn các mối liên kết lazy giữa source/consumer properties, Gradle tasks và file input fingerprints. Với Gradle managed type:

```java
public abstract Property<Boolean> getPublicApi();
```

module cấu hình `publicApi.set(true)`, còn plugin truyền **cả Provider**, không lấy giá trị ngay:

```java
task.getPublicApi().set(extension.getPublicApi());
```

Khi `TaskAction` chạy, task mới đọc `getPublicApi().get()`. Vì vậy việc plugin được apply trước module DSL không làm mất override.

### 4.1. `convention()` khác `set()`

```java
// Plugin thiết lập default.
extension.getPublicApi().convention(false);
extension.getOwner().convention(project.getName());
```

```kotlin
// Module khai báo khác default.
moduleNeeds {
    publicApi.set(true)
    owner.set("api-team")
}
```

- `convention(value)`: fallback nếu chưa có explicit value.
- `set(value)`: ghi explicit value.
- `set(provider)`: nối một Provider khác theo cách lazy.
- `get()`: yêu cầu resolve giá trị tại thời điểm gọi.
- `map(transformer)`: tạo Provider tính giá trị dẫn xuất.
- `flatMap(transformer)`: dùng khi kết quả transform cũng là Provider.
- `orElse(...)`: fallback cho một Provider.
- `isPresent()`: kiểm một Provider/property có giá trị.

**Tránh gọi `extension.getPublicApi().get()` trong `Plugin.apply()`** để quyết định có tạo task hay không: lúc đó module thường chưa chạy hết `moduleNeeds { ... }`, nên plugin dễ chỉ thấy default false.

### 4.2. Dùng `Provider.map` khi cần giá trị dẫn xuất

```java
// Ví dụ tùy chọn; không có trong baseline demo.
task.getOwner().set(
    extension.getOwner().map(String::trim)
);
```

Đây là phép biến đổi dữ liệu. **Không** để `Provider.map` viết file, gửi HTTP hoặc publish artifact; những việc có tác động phụ nên được làm trong task action có inputs/outputs được khai báo.

## 5. Demo độc lập: Java 17, hai modules, một shared plugin

Ta xây dựng:

- `build-logic`: Gradle **included build** cung cấp binary plugin `com.example.module-needs` được viết bằng Java.
- `:api`: Java library có public API, yêu cầu README.
- `:service`: Java library nội bộ phụ thuộc `:api`, không yêu cầu README.
- Plugin tạo `verifyModuleNeeds` và gắn nó vào `check` cho từng module.
- Mỗi module có output report riêng, không ghi đè nhau.

Demo không cần tải third-party Java library hay apply plugins ngoài core Gradle. Nó cần **JDK 17** và Gradle Wrapper hỗ trợ Java 17/toolchains. Trong project mới cần tạo Gradle Wrapper thật một lần (ví dụ `gradle wrapper` từ Gradle đã cài), sau đó commit các file Wrapper. Không tự chế tạo `gradle-wrapper.jar` giả.

### 5.1. Cấu trúc thư mục

```text
module-needs-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
│   ├── gradle-wrapper.jar
│   └── gradle-wrapper.properties
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/java/com/example/build/
│       ├── ModuleNeedsExtension.java
│       ├── VerifyModuleNeedsTask.java
│       └── ModuleNeedsPlugin.java
├── api/
│   ├── build.gradle.kts
│   ├── README.md
│   └── src/main/java/example/api/Greeting.java
└── service/
    ├── build.gradle.kts
    └── src/main/java/example/service/Main.java
```

### 5.2. Root `settings.gradle.kts`

```kotlin
pluginManagement {
    // Plugin build riêng, không phải Gradle subproject :build-logic.
    includeBuild("build-logic")
}

rootProject.name = "module-needs-lab"
include(":api", ":service")
```

**Giải thích:** `pluginManagement.includeBuild` làm các plugin được build-logic khai báo có thể resolve bằng `plugins { id("...") }`. Nó **khác** việc thêm Java library bằng `implementation(project(":..."))`. Included build có settings/tasks/repositories riêng.

Root `build.gradle.kts`:

```kotlin
plugins {
    base
}
```

Plugin `module-needs` chỉ được áp ở Java modules, không áp ở root aggregator.

### 5.3. `build-logic/settings.gradle.kts`

```kotlin
rootProject.name = "module-needs-build-logic"
```

Build logic có tên riêng để tránh nhầm namespace của included build với `:api`/`:service` của main build.

### 5.4. `build-logic/build.gradle.kts`

```kotlin
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
        create("moduleNeeds") {
            id = "com.example.module-needs"
            implementationClass = "com.example.build.ModuleNeedsPlugin"
            displayName = "Shared module requirements"
            description = "Modules declare needs, plugin implements checks"
        }
    }
}
```

`java-gradle-plugin` là plugin **core của Gradle** dành cho phát triển plugins, cung cấp Gradle API để compile `Plugin<Project>` và tạo plugin descriptors. `implementationClass` phải khớp package/class thật. Demo không đòi `maven-publish` hay publish lên Gradle Plugin Portal vì main build consume plugin trực tiếp từ included build.

### 5.5. `ModuleNeedsExtension.java` — typed public DSL

File `build-logic/src/main/java/com/example/build/ModuleNeedsExtension.java`:

```java
package com.example.build;

import org.gradle.api.file.RegularFileProperty;
import org.gradle.api.provider.Property;

/** Public contract cho các module sử dụng plugin. */
public abstract class ModuleNeedsExtension {

    /** Team chịu trách nhiệm module. */
    public abstract Property<String> getOwner();

    /** Module có public Java API hay không? */
    public abstract Property<Boolean> getPublicApi();

    /** File docs cần tồn tại nếu publicApi=true. */
    public abstract RegularFileProperty getApiDocumentation();
}
```

**Gradle managed type:** Gradle có thể sinh implementation cho những abstract getters này khi extension được tạo qua `ExtensionContainer.create`. Không `new ModuleNeedsExtension()`. Không thêm `@Input` vào extension: đó là annotation để khai báo **task input**, không phải annotation để mô tả DSL.

Module Kotlin DSL dùng `owner.set("...")` và `publicApi.set(true)`; các properties có kiểu rõ ràng và IDE có thể hỗ trợ completion.

### 5.6. `VerifyModuleNeedsTask.java` — task thực thi cơ chế

File `build-logic/src/main/java/com/example/build/VerifyModuleNeedsTask.java`:

```java
package com.example.build;

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
import org.gradle.api.tasks.InputFile;
import org.gradle.api.tasks.Optional;
import org.gradle.api.tasks.OutputFile;
import org.gradle.api.tasks.PathSensitive;
import org.gradle.api.tasks.PathSensitivity;
import org.gradle.api.tasks.TaskAction;

@CacheableTask
public abstract class VerifyModuleNeedsTask extends DefaultTask {

    @Input
    public abstract Property<String> getOwner();

    @Input
    public abstract Property<Boolean> getPublicApi();

    @Optional
    @InputFile
    @PathSensitive(PathSensitivity.RELATIVE)
    public abstract RegularFileProperty getApiDocumentation();

    @OutputFile
    public abstract RegularFileProperty getReportFile();

    @TaskAction
    public void verify() throws IOException {
        String owner = getOwner().get().trim();
        boolean publicApi = getPublicApi().get();

        if (owner.isEmpty()) {
            throw new GradleException(
                "moduleNeeds.owner must not be blank"
            );
        }
        if (publicApi && !getApiDocumentation().isPresent()) {
            throw new GradleException(
                "Public API needs moduleNeeds.apiDocumentation"
            );
        }
        if (publicApi &&
            !getApiDocumentation().get().getAsFile().isFile()) {
            throw new GradleException(
                "API documentation file is missing"
            );
        }

        Path path = getReportFile().get().getAsFile().toPath();
        Files.createDirectories(path.getParent());

        String report =
            "owner=" + owner + "\n" +
            "publicApi=" + publicApi + "\n" +
            "documentation=" +
                (publicApi ? "PRESENT" : "NOT_REQUIRED") + "\n";

        Files.writeString(path, report, StandardCharsets.UTF_8);

        getLogger().lifecycle(
            "MODULE_NEEDS_OK owner={} publicApi={}", owner, publicApi
        );
    }
}
```

**Từng annotation có lý do riêng:**

| Annotation | Property | Ý nghĩa |
| --- | --- | --- |
| `@CacheableTask` | Class task | Cho phép task output được cache nếu conditions phù hợp |
| `@Input` | `owner`, `publicApi` | Giá trị cần fingerprint để biết khi nào rerun |
| `@Optional @InputFile` | `apiDocumentation` | File có thể không được khai báo khi module không cần docs |
| `@PathSensitive(RELATIVE)` | `apiDocumentation` | Không hash absolute file path không cần thiết |
| `@OutputFile` | `reportFile` | Gradle biết nơi task tạo output |
| `@TaskAction` | `verify()` | Chạy khi Gradle thực thi task, không chạy lúc configuration |

**Quan trọng:** `@Optional` chỉ nói task input có thể **không hiện diện**; nó không hủy quy tắc nghiệp vụ. Code vẫn yêu cầu docs khi `publicApi=true`.

Nếu module **có đặt path** cho `apiDocumentation` nhưng file không tồn tại, Gradle có thể ném **input file validation error trước task action**. Nếu module **chưa đặt property** mà `publicApi=true`, task action sẽ ném thông điệp `Public API needs ...`. Cả hai bảo đảm thiếu docs không bị coi là thành công.

Report được ghi bằng UTF-8, chỉ gồm dữ liệu deterministic; owner/publicApi/file là task inputs, file report là declared output. `@CacheableTask` không tự làm mọi trường hợp cache được nếu inputs không ổn định hoặc action có side effects ngoài output.

### 5.7. `ModuleNeedsPlugin.java` — áp policy, nối extension với task

File `build-logic/src/main/java/com/example/build/ModuleNeedsPlugin.java`:

```java
package com.example.build;

import org.gradle.api.Plugin;
import org.gradle.api.Project;
import org.gradle.api.Task;
import org.gradle.api.plugins.JavaPluginExtension;
import org.gradle.api.tasks.TaskProvider;
import org.gradle.jvm.toolchain.JavaLanguageVersion;

public final class ModuleNeedsPlugin implements Plugin<Project> {

    @Override
    public void apply(Project project) {
        // Plugin dành cho Java library modules.
        project.getPluginManager().apply("java-library");

        JavaPluginExtension java =
            project.getExtensions().getByType(
                JavaPluginExtension.class
            );
        java.getToolchain().getLanguageVersion()
            .convention(JavaLanguageVersion.of(17));

        // 1) Public DSL object.
        ModuleNeedsExtension extension =
            project.getExtensions().create(
                "moduleNeeds", ModuleNeedsExtension.class
            );

        // 2) Defaults; module có thể override bằng set().
        extension.getOwner().convention(project.getName());
        extension.getPublicApi().convention(false);

        // 3) Register task lazily, không read get() quá sớm.
        TaskProvider<VerifyModuleNeedsTask> verifier =
            project.getTasks().register(
                "verifyModuleNeeds",
                VerifyModuleNeedsTask.class,
                task -> {
                    task.setGroup("verification");
                    task.setDescription(
                        "Verify declared module requirements"
                    );

                    task.getOwner().set(extension.getOwner());
                    task.getPublicApi().set(extension.getPublicApi());
                    task.getApiDocumentation().set(
                        extension.getApiDocumentation()
                    );

                    task.getReportFile().set(
                        project.getLayout().getBuildDirectory()
                            .file("reports/module-needs/status.txt")
                    );
                }
            );

        // 4) check là lifecycle task do java-library tạo.
        project.getTasks().named("check").configure(
            (Task check) -> check.dependsOn(verifier)
        );
    }
}
```

**Cơ chế cốt lõi:**

1. `apply("java-library")` định nghĩa convention cho Java library modules. Nó cung cấp `implementation`, `compileJava`, `classes` và `check`.
2. Java toolchain 17 được đặt bằng `convention()`, **không khóa override**. Nếu phải enforce Java 17, cần policy validation riêng.
3. `extensions.create(...)` đăng ký typed extension. Mỗi project nhận instance của mình.
4. `owner.convention(project.getName())` là fallback; module có thể đặt owner team thật.
5. `publicApi.convention(false)` là mặc định cho module nội bộ.
6. `tasks.register` trả về `TaskProvider`; không chạy task action khi apply plugin.
7. `task.getOwner().set(extension.getOwner())` và `task.getPublicApi().set(extension.getPublicApi())` **giữ quan hệ Provider**; không resolve sớm.
8. `getApiDocumentation().set(extension.getApiDocumentation())` giữ optional file property, để Gradle xử lý input file.
9. Report path được plugin quản lý trong **build directory của từng module**, không ghi chung ở root.
10. `tasks.named("check").configure(...dependsOn(verifier))` gắn verification vào lifecycle, không ép modules nhớ thêm `dependsOn`.

**Tại sao không dùng `afterEvaluate`?** Với Provider wiring, plugin không cần chờ hết configuration rồi mutate task; consumer có thể set extension sau khi plugin đã được apply, và task vẫn đọc giá trị khi thực thi. Cách này ít rủi ro về task realization và configuration cache hơn.

### 5.8. `api/build.gradle.kts` và Java API

```kotlin
plugins {
    id("com.example.module-needs")
}

moduleNeeds {
    owner.set("api-team")
    publicApi.set(true)
    apiDocumentation.set(layout.projectDirectory.file("README.md"))
}
```

File `api/README.md`:

```markdown
# Greeting API

This module provides a small Java API.
```

File `api/src/main/java/example/api/Greeting.java`:

```java
package example.api;

public final class Greeting {
    private Greeting() {
    }

    public static String text() {
        return "Hello from shared build logic";
    }
}
```

**Module chỉ khai báo:** API của mình công khai, team sở hữu là `api-team` và có README. Module **không** cần tạo verification task, sửa `check` hay cấu hình report path.

### 5.9. `service/build.gradle.kts` và Java consumer

```kotlin
plugins {
    id("com.example.module-needs")
}

dependencies {
    implementation(project(":api"))
}

moduleNeeds {
    owner.set("service-team")
    // Không đặt publicApi -> dùng convention false.
}
```

File `service/src/main/java/example/service/Main.java`:

```java
package example.service;

import example.api.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.text());
    }
}
```

`service` không public API theo policy demo, nên **không cần tài liệu**. Nó không sửa plugin để bỏ verification; nó dùng default `publicApi=false`, và vẫn có task `verifyModuleNeeds` để ghi báo cáo/status.

### 5.10. Chạy Gradle và dự đoán kết quả

Trên Linux/macOS, từ root:

```bash
./gradlew --version
./gradlew :api:verifyModuleNeeds :service:verifyModuleNeeds --rerun-tasks
./gradlew check
./gradlew :service:classes
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat :api:verifyModuleNeeds :service:verifyModuleNeeds --rerun-tasks
.\gradlew.bat check
.\gradlew.bat :service:classes
```

Lần task action thực thi với inputs hợp lệ, log do plugin tạo có hai dòng, thứ tự có thể thay đổi nếu chạy song song:

```text
MODULE_NEEDS_OK owner=api-team publicApi=true
MODULE_NEEDS_OK owner=service-team publicApi=false
```

Đây **không phải toàn bộ Gradle console output**: Gradle còn hiển thị task names, outcomes và tổng kết `BUILD SUCCESSFUL`. Khi task đã `UP-TO-DATE` hoặc `FROM-CACHE`, action có thể không chạy và không in hai dòng trên; report vẫn có thể tồn tại. `--rerun-tasks` giúp quan sát action trong demo.

**Báo cáo của API** ở `api/build/reports/module-needs/status.txt`:

```text
owner=api-team
publicApi=true
documentation=PRESENT
```

**Báo cáo của service** ở `service/build/reports/module-needs/status.txt`:

```text
owner=service-team
publicApi=false
documentation=NOT_REQUIRED
```

Hai file **khác đường dẫn module**, không ghi đè nhau. `check` sẽ phụ thuộc verifier của mỗi module được áp plugin.

### 5.11. Chạy Java code riêng với Gradle verification

Sau khi `:service:classes` compile main Java sources, bạn có thể chạy chương trình qua Java classpath thủ công để kiểm code Java:

Linux/macOS:

```bash
java -cp "service/build/classes/java/main:api/build/classes/java/main" \
    example.service.Main
```

Windows PowerShell:

```powershell
java -cp "service\build\classes\java\main;api\build\classes\java\main" example.service.Main
```

Stdout **chính xác từ `Main.main`**:

```text
Hello from shared build logic
```

Dấu `:` phân tách classpath ở Unix, `;` ở Windows. Chạy ứng dụng bằng `java -cp` **không tự chạy Gradle verifier**; nó chỉ chứng minh source đã compile và API dependency hoạt động. Muốn gate quality, gọi `./gradlew check`.

### 5.12. Thử một lỗi thực: public API thiếu docs

Trên một bản thử nghiệm, giữ `api/build.gradle.kts`:

```kotlin
moduleNeeds {
    owner.set("api-team")
    publicApi.set(true)
    // Cố ý không cung cấp apiDocumentation.
}
```

Chạy:

```bash
./gradlew :api:verifyModuleNeeds --rerun-tasks
```

Task fail có thông điệp từ code:

```text
Public API needs moduleNeeds.apiDocumentation
```

**Không sửa plugin để cho module này bypass check.** Module phải khai báo `apiDocumentation` hoặc thay lại `publicApi` nếu trước đó khai báo sai. Nếu path được cung cấp nhưng file không tồn tại, Gradle input file validation có thể thất bại trước `@TaskAction`.

### 5.13. Thêm module mới không sửa cơ chế

Khi thêm `:sdk`, root settings thêm `include(":sdk")`. Trong `sdk/build.gradle.kts`:

```kotlin
plugins {
    id("com.example.module-needs")
}

moduleNeeds {
    owner.set("sdk-team")
    publicApi.set(true)
    apiDocumentation.set(layout.projectDirectory.file("README.md"))
}
```

Đây là **mẫu module mới**, cần tạo README và Java source nếu có API. Tất cả verifier/wiring/report cơ chế vẫn nằm trong plugin. Nếu ngày mai nhóm platform đổi file output thành JSON, chỉ plugin phải sửa, trừ khi extension contract thay đổi.

## 6. Khi nào nên dùng Property, ListProperty, SetProperty, MapProperty?

**Không thiết kế một extension như map các chuỗi tùy ý** nếu có thể dùng typed properties.

| Nhu cầu | Type nên dùng | Ví dụ |
| --- | --- | --- |
| String/Boolean/Integer single value | `Property<T>` | `owner`, `publicApi` |
| Một file | `RegularFileProperty` | `apiDocumentation` |
| Một thư mục | `DirectoryProperty` | `schemaDirectory` |
| Nhiều files | `ConfigurableFileCollection` | `policyFiles` |
| Danh sách có thứ tự | `ListProperty<T>` | `targetEnvironments` |
| Tập không trùng | `SetProperty<T>` | `capabilities` |
| Key-value metadata | `MapProperty<K,V>` | `labels` |
| Một nhóm config có thuộc tính con | Managed nested type | `documentation { ... }` |
| Một tập các phần tử đặt tên | `NamedDomainObjectContainer<T>` | `apiSpecs { register(...) }` |

### 6.1. Ví dụ khai báo thêm các property types

Trong một phiên bản extension nâng cao:

```java
public abstract ListProperty<String> getTargetEnvironments();
public abstract SetProperty<String> getRequiredCapabilities();
public abstract MapProperty<String, String> getLabels();
public abstract DirectoryProperty getSchemaDirectory();
public abstract ConfigurableFileCollection getPolicyFiles();
```

Các getters trên là **đoạn mở rộng, không tồn tại trong baseline `ModuleNeedsExtension.java`**. Khi triển khai thật, cần imports, defaults và task inputs/report behavior tương ứng; không chỉ thêm getters rồi hy vọng Gradle sẽ biết làm gì với chúng.

Trong module Kotlin DSL khi đã thêm APIs:

```kotlin
moduleNeeds {
    targetEnvironments.set(listOf("staging", "production"))
    requiredCapabilities.add("metrics")
    labels.put("tier", "internal")
    schemaDirectory.set(layout.projectDirectory.dir("schemas"))
    policyFiles.from(layout.projectDirectory.file("policy.yml"))
}
```

**Chọn đúng kiểu giúp Gradle/IDE phát hiện sai sớm.** `Property<Boolean>` tốt hơn `Map<String,String>` với key `"publicApi"="yes"`. `SetProperty` phù hợp capabilities không có ý nghĩa thứ tự; `ListProperty` phù hợp chuỗi bước mà thứ tự thật sự quan trọng.

### 6.2. ObjectFactory và Gradle-managed types

`project.getObjects()` cung cấp `ObjectFactory`, có thể tạo property mới:

```java
Property<String> label =
    project.getObjects().property(String.class);
label.convention("default-label");
```

Đây là **đoạn minh họa** trong code plugin. Với abstract getters của extension demo, Gradle đã cấp managed properties khi gọi `extensions.create(...)`, không cần tạo thủ công từng `Property`.

### 6.3. Khi nào dùng enum?

Một quality level nên được giới hạn:

```java
public enum QualityLevel {
    BASIC,
    STRICT
}
```

Thay vì:

```kotlin
moduleNeeds {
    // Một API giả định với string dễ typo:
    qualityLevel.set("strcit")
}
```

hướng tốt hơn là `Property<QualityLevel>`, để module chọn `QualityLevel.STRICT`. Enum value là hợp đồng public API; thêm/đổi/loại giá trị cần migration. Đây là **gợi ý mở rộng**, không nằm trong full demo.

## 7. Lazy task configuration: giữ sự khác nhau giữa configuration và execution

Gradle có ba pha lớn: initialization → configuration → execution. Plugin `apply()` chạy ở **configuration phase**, module `moduleNeeds { }` cũng cấu hình dữ liệu ở pha đó. `@TaskAction` chỉ chạy khi task nằm trong execution graph.

**Sai khi plugin gọi `.get()` quá sớm:**

```java
boolean publicApi = extension.getPublicApi().get();
if (publicApi) {
    project.getTasks().register("verifyModuleNeeds", ...);
}
```

Có thể plugin lúc này chỉ nhìn thấy default false. Module gọi `publicApi.set(true)` sau đó cũng không giúp task đã không được đăng ký.

**Đúng:** plugin luôn register verifier và set task input bằng Provider:

```java
task.getPublicApi().set(extension.getPublicApi());
```

Task action đọc `get()` tại execution time.

### 7.1. TaskProvider và task configuration avoidance

Trong demo:

```java
TaskProvider<VerifyModuleNeedsTask> verifier =
    project.getTasks().register(
        "verifyModuleNeeds",
        VerifyModuleNeedsTask.class,
        task -> { /* cấu hình lazy */ }
    );
```

`tasks.register` đăng ký task, không bắt nó realize ngay. `TaskProvider` có thể được truyền thẳng vào `check.dependsOn`. `tasks.named("check")` lấy provider cho task đã được đăng ký thay vì gọi `tasks.getByName(...)` để eagerly realize.

Các API nên ưu tiên:

- `tasks.register` cho task mới.
- `tasks.named` cho task có tên đã biết.
- `tasks.withType(...).configureEach` cho một nhóm tasks.
- `plugins.withId` / `pluginManager.withPlugin` nếu cần chờ plugin khác apply.
- `Provider.map`/`flatMap` cho giá trị dẫn xuất.

Tránh dùng `tasks.create`/`tasks.getByName`/`afterEvaluate` khi có cách lazy rõ ràng hơn.

### 7.2. `afterEvaluate` không phải giải pháp mặc định

```java
project.afterEvaluate(p -> {
    // Sửa task sau khi module đã được cấu hình.
});
```

Cách này thường là dấu hiệu plugin không mô hình hóa configuration inputs đúng. Nó có thể đụng thứ tự plugin khác, cấu hình muộn và làm configuration cache khó tương thích. Provider wiring và plugin callbacks thường giải quyết cùng nhu cầu theo hướng được Gradle hỗ trợ tốt hơn.

### 7.3. Chỉ apply plugin ở modules phù hợp

Demo plugin gọi `apply("java-library")`, vì thế nó là **Java library convention**. Không áp thẳng vào Android/iOS/resource-only modules rồi buộc chúng phải có `compileJava`/`check` tương tự. Khi muốn một plugin cross-language, tách phần verification trung lập và dùng `withPlugin("java")`/callbacks để tích hợp vào Java khi hiện diện.

Đừng dùng root `subprojects { apply(plugin = "...") }` bừa bãi rồi nghĩ mọi module đều có cùng nhu cầu. Ưu tiên explicit plugin application hoặc organizational conventions được quản trị.

## 8. Làm sao báo cáo vẫn đúng khi module thay đổi?

Task trong demo khai báo inputs và output:

- `owner`: `@Input`.
- `publicApi`: `@Input`.
- `apiDocumentation`: `@Optional @InputFile` và path sensitivity.
- `reportFile`: `@OutputFile`.
- `@CacheableTask`: cho phép build cache khi conditions phù hợp.

Do đó:

1. Lần đầu task tạo report.
2. Lần tiếp theo inputs/outputs không đổi, task có thể `UP-TO-DATE`.
3. Đổi owner sẽ đổi input fingerprint; cần chạy lại hoặc lấy cached result đúng.
4. Đổi nội dung README được dùng làm input sẽ làm fingerprint khác.
5. Xóa report khiến output thiếu; Gradle có thể chạy task lại hoặc phục hồi từ build cache nếu bật.
6. `--rerun-tasks` yêu cầu thực thi lại actions ngay cả khi tasks up-to-date.
7. `clean` xóa build outputs, nhưng khi build cache bật Gradle có thể phục hồi output mà không chạy action.

**Không nhầm build cache với configuration cache.** Build cache tái sử dụng **task outputs**, còn configuration cache tái sử dụng **configured task graph**. Plugin cần có inputs/outputs chính xác cho build cache, đồng thời không truy cập Project model từ task action để tương thích configuration cache.

### 8.1. Ví dụ kiểm tra

```bash
./gradlew :api:verifyModuleNeeds
./gradlew :api:verifyModuleNeeds
./gradlew :api:verifyModuleNeeds --rerun-tasks
./gradlew :api:verifyModuleNeeds --configuration-cache
./gradlew :api:verifyModuleNeeds --configuration-cache
```

Xem Gradle task outcomes; đừng phụ thuộc vào việc một dòng log được in lại khi task không thực thi.

### 8.2. Tránh đầu vào ngầm và tác động phụ

Không làm trong `@TaskAction` mà không khai báo input:

- `System.getenv("TEAM")` thay đổi report, nhưng environment không được đưa vào task input.
- Gọi HTTP lấy remote config và ghi vào report không có input tracking.
- Dùng timestamp hiện tại, random ID hoặc hostname trong report được đánh dấu cacheable.
- Ghi file ngoài `@OutputFile`/`@OutputDirectory` đã khai báo.
- Truy cập `project.getProjectDir()` hoặc other `Project` model từ execution phase.
- Đọc file bằng raw IO trong configuration phase mà Gradle không theo dõi.

Khi cần environment setting, dùng `providers.environmentVariable("TEAM")` ở plugin configuration và ánh xạ nó vào task `@Input`. Khi cần remote network action, tạo task/service có hợp đồng riêng và cân nhắc cacheability, không giấu trong `Provider.map`.

## 9. API tốt cần ngắn gọn và khó bị lạm dụng

Một extension không nên trở thành “điều khiển từ xa” cho mọi chi tiết Gradle.

**Tốt:**

```kotlin
moduleNeeds {
    owner.set("api-team")
    publicApi.set(true)
    apiDocumentation.set(layout.projectDirectory.file("README.md"))
}
```

**Không nên cho module tự làm:**

```kotlin
// Anti-pattern minh họa, không tồn tại trong demo:
moduleNeeds {
    taskName.set("verifyCustom")
    gradleInternalClassName.set("...")
    shellCommand.set("...")
    disableAllChecks.set(true)
}
```

Vì những thuộc tính này buộc module hiểu cách hoạt động bên trong, gây phụ thuộc vào implementation details và có thể mở đường bypass quality/security gates.

Nếu một ngoại lệ là thật (legacy/generated code), nên tạo **request exception có scope**, ví dụ mã ticket/expiry/owner, và kiểm duyệt trong plugin/CI; không chỉ expose `ignoreAllValidation.set(true)`.

### 9.1. Defaults vs enforcement

`convention(false)` là default chứ không phải ràng buộc không cho modules override. Tương tự `java.toolchain.languageVersion.convention(17)` cho phép module set JDK 21 nếu policy không khóa.

Khi giá trị phải **bắt buộc** hay **immutable**, cần validation hoặc cơ chế finalize/disallow change ở thời điểm đúng. Không gọi `finalizeValue()` quá sớm trong `Plugin.apply()` rồi khiến module `set(...)` ném lỗi khó hiểu.

Nếu organization muốn bắt buộc owner thật, có thể bỏ convention `owner=project.name` và yêu cầu explicit owner; đây là thay đổi có thể làm nhiều modules fail, cần rollout và migration policy.

### 9.2. Không thêm property chỉ vì có use case đơn lẻ chưa rõ

Mỗi property công khai mang chi phí dài hạn: documentation, defaults, migration, backward compatibility, tests và bảo mật. Đặt câu hỏi:

1. Nhu cầu này có xuất hiện ở nhiều modules?
2. Module có thật sự là nơi biết giá trị?
3. Plugin có thể giữ cơ chế tập trung nếu expose property này không?
4. Giá trị có thể validate bằng type/enum không?
5. Có thể set default an toàn?
6. Có phải exception cần phê duyệt thay vì quyền tự do?
7. Thay implementation sau này có buộc module DSL đổi không?

Nếu câu 7 là “có”, extension nhiều khả năng đang expose cách làm hơn là nhu cầu.

## 10. Nested extension và container: dùng khi đủ phức tạp

Với hai giá trị publicApi/docs, **flat extension** là phù hợp. Nếu một module có nhiều tài liệu hoặc endpoints cần kiểm, có thể thiết kế nested DSL:

```kotlin
moduleNeeds {
    documentation {
        required.set(true)
        sourceFile.set(layout.projectDirectory.file("README.md"))
        format.set(DocFormat.HTML)
    }
}
```

Đây là **API thiết kế tương lai**, không thể chạy bằng ba Java class demo. Để triển khai cần managed nested object/type, DSL configuration action và task property wiring.

Khi có nhiều phần tử đặt tên, Gradle hỗ trợ `NamedDomainObjectContainer<T>`:

```kotlin
moduleNeeds {
    apiSpecs {
        register("rest") {
            sourceFile.set(layout.projectDirectory.file("openapi.yaml"))
        }
        register("events") {
            sourceFile.set(layout.projectDirectory.file("asyncapi.yaml"))
        }
    }
}
```

Cũng chỉ là **ví dụ thiết kế API** cho plugin nâng cao. Cần type `Named`/`ApiSpec`, registration và task mapping; không có trong runnable demo.

**Không tạo container cho một Boolean đơn giản.** Chỉ dùng nested DSL khi nó rõ hơn và nhiều property thuộc cùng một khái niệm.

## 11. Chọn binary plugin, precompiled script plugin hay buildSrc?

| Lựa chọn | Khi phù hợp | Lưu ý |
| --- | --- | --- |
| `subprojects { ... }` ở root | Dự án nhỏ, logic ít | Dễ tạo cross-project coupling; khó mở rộng |
| `buildSrc` | Logic dùng chung ngay trong một build | Tự động có mặt trên classpath; thay đổi có thể gây rebuild nhiều scripts |
| Included build `build-logic` | Monorepo, cần tách lifecycle/plugin dependencies | Có settings riêng; dùng `pluginManagement.includeBuild` khi resolve plugin |
| Precompiled `*.gradle.kts` plugin | Tập hợp conventions từ plugins có sẵn | Có thể khai báo extensions và tasks, tùy độ phức tạp |
| Java/Kotlin binary plugin | Typed extension, custom task classes, tests/API dài hạn | Nhiều code hơn nhưng ranh giới API rõ |
| Published plugin artifact | Nhiều repositories cần chung policy | Cần versioning, release, plugin repository/credentials |

Demo chọn **included build + Java binary plugin** vì có cả typed extension và custom task type. Với convention đơn giản chỉ đặt Java toolchain/JUnit defaults, một precompiled script plugin có thể gọn hơn.

Gradle có tài liệu precompiled plugins sử dụng:

```kotlin
interface GreetingExtension {
    val message: Property<String>
}

val extension =
    project.extensions.create<GreetingExtension>("greeting")

extension.message.convention("Hello from Gradle")
```

Đây là một **đoạn ví dụ** trong precompiled `*.gradle.kts` plugin với imports/setup tương ứng; chưa phải full runnable project. Điểm cốt lõi: không bắt buộc dùng binary Java plugin mới tạo được extension.

### 11.1. Mỗi included build có môi trường cấu hình riêng

`build-logic` có `settings.gradle.kts`/`build.gradle.kts` của chính nó. Không tự dùng plugin catalogs hoặc dependency repositories của main build. Nếu nó cần external dependencies, phải khai báo repositories/versions cho chính included build. Không copy private tokens vào build-logic source.

### 11.2. Tính tương thích Gradle/Java

Java 17 compiler trong demo không bắt JVM chạy Gradle Daemon cũng chính xác là 17, miễn là Gradle Wrapper hỗ trợ runtime JDK đó và toolchain có sẵn. Nếu build-logic không tìm được JDK 17, lỗi toolchain xảy ra trước khi plugin được compile. Xem `./gradlew -q javaToolchains` và Gradle Java compatibility matrix.

## 12. TestKit: kiểm tra contract thay vì chỉ nhìn build thành công

Khi plugin dùng cho nhiều modules, không thể chỉ “thử tay `check` một lần” là đủ. Nên có:

- Unit tests cho validation logic.
- Gradle TestKit functional tests chạy build thật.
- Integration tests nhiều modules, đúng source sets và task graph.
- CI thử Gradle Wrapper/JDK versions được hỗ trợ.
- Checks `--configuration-cache` và build cache.
- Negative tests cho owner rỗng và publicApi thiếu docs.

### 12.1. Thêm JUnit Jupiter vào build-logic tests

Phần này **tùy chọn**. Baseline không yêu cầu Maven Central; nếu muốn test bằng JUnit, thêm vào `build-logic/build.gradle.kts`:

```kotlin
repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.14.1")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

`java-gradle-plugin` tích hợp Gradle TestKit và plugin-under-test metadata. JUnit Jupiter vẫn cần dependencies/test engine và `useJUnitPlatform()` như trên. Với corporate mirror, thay `mavenCentral()` bằng repository policy của tổ chức.

### 12.2. Functional test đầy đủ cho case pass

File `build-logic/src/test/java/com/example/build/ModuleNeedsFunctionalTest.java`:

```java
package com.example.build;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.gradle.testkit.runner.BuildResult;
import org.gradle.testkit.runner.GradleRunner;
import org.gradle.testkit.runner.TaskOutcome;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ModuleNeedsFunctionalTest {

    @TempDir
    Path tempDir;

    @Test
    void publicApiNeedsFileAndGeneratesReport() throws IOException {
        Files.writeString(
            tempDir.resolve("settings.gradle"),
            "rootProject.name = 'sample'\n",
            StandardCharsets.UTF_8
        );

        Files.writeString(
            tempDir.resolve("build.gradle"),
            "plugins { id 'com.example.module-needs' }\n" +
            "moduleNeeds {\n" +
            "  owner.set('test-team')\n" +
            "  publicApi.set(true)\n" +
            "  apiDocumentation.set(layout.projectDirectory.file('README.md'))\n" +
            "}\n",
            StandardCharsets.UTF_8
        );

        Files.writeString(
            tempDir.resolve("README.md"),
            "# Public API\n",
            StandardCharsets.UTF_8
        );

        BuildResult result = GradleRunner.create()
            .withProjectDir(tempDir.toFile())
            .withArguments("verifyModuleNeeds", "--stacktrace")
            .withPluginClasspath()
            .build();

        assertEquals(
            TaskOutcome.SUCCESS,
            result.task(":verifyModuleNeeds").getOutcome()
        );

        String report = Files.readString(
            tempDir.resolve("build/reports/module-needs/status.txt")
        );
        assertTrue(report.contains("owner=test-team"));
        assertTrue(report.contains("publicApi=true"));
        assertTrue(report.contains("documentation=PRESENT"));
    }
}
```

- `@TempDir` tạo sandbox build riêng.
- Test fixture dùng **Groovy DSL** để chứng minh binary plugin cũng dùng được ngoài Kotlin DSL.
- `withPluginClasspath()` giúp TestKit nạp plugin-under-test do `java-gradle-plugin` cấu hình.
- `GradleRunner.build()` chạy Gradle thật trong project temp.
- Test kiểm cả task outcome lẫn file output; chỉ assert `BUILD SUCCESSFUL` là quá ít.

Trường hợp negative nên tạo fixture có `publicApi.set(true)` nhưng **không** cấu hình `apiDocumentation`, rồi dùng `buildAndFail()` và assert thông điệp lỗi. Không thể chỉ gọi `buildAndFail()` trên fixture pass rồi hy vọng test lỗi có ý nghĩa.

### 12.3. Test default, override và failure

Một bộ functional tests tối thiểu cần các case:

| Case | Input extension | Kỳ vọng |
| --- | --- | --- |
| Default | Không cấu hình `moduleNeeds` | Owner mặc định project name, `publicApi=false` |
| Override | `owner="api-team"` | Report dùng owner mới |
| Public API | `publicApi=true` + docs file | PASS, `documentation=PRESENT` |
| Missing docs | `publicApi=true`, không file property | FAIL, thông điệp hướng dẫn |
| Path sai | Có `apiDocumentation` nhưng file không tồn tại | Input file validation FAIL |
| Owner blank | `owner="   "` | FAIL |
| Re-run | Inputs không đổi | `UP-TO-DATE` hoặc `FROM-CACHE` |
| Input change | README/owner đổi | Task input fingerprint thay đổi |
| Lifecycle | Chạy `check` | `verifyModuleNeeds` nằm trong task graph |
| Multi-project | Hai modules | Báo cáo riêng theo project |
| Config cache | `--configuration-cache` hai lần | Không có model access violation |

**Bài test ở phần 12.2 chỉ bao phủ một case**, không phải chứng nhận toàn bộ các case đã được chạy. Khi dùng thực tế, phát triển các tests còn lại theo policy.

## 13. CI, release và kiểm soát coverage

Một pipeline có thể chạy:

```bash
./gradlew --version
./gradlew :api:check :service:check
./gradlew :service:classes
```

Khi đã thêm JUnit/TestKit ở build-logic, gọi test của **included build** theo task path tương ứng hoặc từ build directory riêng với Wrapper tương thích. Trong demo, build-logic có root name `module-needs-build-logic`, nên một build-tree task path thường là `:module-needs-build-logic:test`; xác minh bằng Gradle task graph thực tế.

**CI phải biết modules nào bắt buộc dùng plugin.** Một module không apply `com.example.module-needs` sẽ không có task verifier, và `check` có thể pass vì chỉ chạy Java tests. Khi policy yêu cầu áp plugin ở tất cả public Java modules, cần gate/inspection hoặc organizational convention riêng để phát hiện thiếu plugin. Không để việc không có tasks trở thành “PASS” giả.

### 13.1. Báo cáo thất bại vẫn phải được lưu

Nếu `verifyModuleNeeds` fail vì missing docs, task có thể chưa tạo report. CI phải giữ Gradle logs/error messages, và nếu có các reports thành công từ modules khác thì lưu lại. Không dùng `ignoreFailures` hoặc tắt `check` để bảo đảm pipeline xanh.

### 13.2. Rollout shared plugin có kiểm soát

- Đặt defaults an toàn cho modules cũ.
- Tạo migration examples theo DSL Kotlin/Groovy.
- Test plugin trên nhóm representative modules.
- Review tác động của thay đổi policy/defaults.
- Giữ tên extension/task ổn định khi CI phụ thuộc.
- Có owner cho plugin implementation và review exceptions.
- Tự động kiểm TestKit trên mỗi PR sửa build-logic.
- Pin Gradle Wrapper và Java toolchain.
- Ghi changelog cho public plugin API.
- Đo task performance/cache misses khi thêm checks mới.

## 14. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| `Unresolved reference: moduleNeeds` | Plugin chưa apply trong `plugins`/accessor chưa sinh | Kiểm plugin ID, includeBuild, IDE sync |
| `Plugin ... was not found` | `pluginManagement.includeBuild` path/metadata sai | Kiểm root settings và build-logic |
| `Could not find implementation class` | `implementationClass` không trùng package/source | Kiểm Java files và plugin registration |
| `Cannot create extension` | Managed type không hợp lệ/constructor sai | Dùng abstract properties/ObjectFactory |
| `Unknown property publicApi` | Đang dùng plugin version cũ hoặc getter thiếu | Đồng bộ extension API |
| Module set true nhưng task đọc false | Plugin `get()` quá sớm hoặc `set(false)` override | Dùng `convention(false)`, Provider wiring |
| `apiDocumentation` missing | Public API chưa cấp file | Đặt RegularFileProperty đúng |
| Input file validation failed | Path có nhưng file không tồn tại | Tạo/sửa README, không bypass |
| Owner blank | `owner.set("   ")` | Sửa owner thật |
| Task `UP-TO-DATE`, không có log action | Gradle skip đúng do inputs/outputs unchanged | Xem report, dùng `--rerun-tasks` khi thử |
| Task `FROM-CACHE` | Build cache phục hồi report | Bình thường nếu inputs đúng |
| `check` không gọi verifier | Quên `dependsOn` hoặc plugin không apply | Xem task graph và plugin code |
| `classes` không gọi verifier | `classes` chỉ compile/resources | Chạy `check` |
| Reports hai modules ghi đè | Plugin ghi file ở root output path chung | Dùng mỗi module buildDirectory |
| `afterEvaluate` gây lỗi cấu hình muộn | Mutation sau khi provider/task finalized | Chuyển sang lazy configuration |
| Configuration cache error | Task action truy cập `Project`/env ngầm | Truyền giá trị qua `@Input` properties |
| Cache reuse sai | Input/output thiếu annotation | Model task inputs đầy đủ |
| Java toolchain not found | Thiếu JDK 17/resolver | Chạy `javaToolchains`, cài đúng JDK |
| Module không dùng Java bị plugin apply | Plugin convention không đúng loại project | Tách policy/callback cho phù hợp |
| Root build `check` pass nhưng module thiếu plugin | Chưa gate plugin application coverage | Kiểm modules eligible trong CI |
| Nhiều flags mâu thuẫn | Extension API thiếu ràng buộc | Dùng typed enum/validation/nested contract |
| Plugin code thay đổi nhưng IDE vẫn lỗi | Build-logic recompilation/sync chưa cập nhật | Chạy Wrapper CLI, reimport IDE |

### 14.1. Quy trình debug gọn

```bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew :api:tasks --all
./gradlew :api:check --dry-run
./gradlew :api:verifyModuleNeeds --rerun-tasks --info
./gradlew :service:verifyModuleNeeds --rerun-tasks --info
./gradlew check --configuration-cache
```

`--dry-run` chỉ mô phỏng graph, không xác minh task đã thực thi. Đọc actual task outcomes và `build/reports/module-needs/status.txt`; với plugin compile error, giải quyết `build-logic` trước khi phân tích module DSL.

## 15. Các anti-patterns cần tránh

### 15.1. Branch theo `project.name` trong shared logic

```kotlin
// Khó bảo trì: module identity bị hardcode ở shared mechanism.
if (project.name == "api") {
    // Register docs check.
}
```

Khi đổi tên module hoặc thêm `:sdk`, policy bị bỏ sót. Thay bằng `moduleNeeds { publicApi.set(true) }`. Nếu tổ chức có metadata chính thức từ catalog, plugin có thể đọc Provider ở đó; không nên phụ thuộc chuỗi hardcode tùy hứng.

### 15.2. Cho module tự mutate internal tasks

```kotlin
// Anti-pattern: module phải hiểu task internals của plugin.
tasks.named("verifyModuleNeeds") {
    enabled = false
}
```

Dùng nó để né quality gate tạo rủi ro. Module nên khai báo nhu cầu thật; exception policy phải được plugin/CI review.

### 15.3. Gắn mọi property vào một map string

```kotlin
// Không nên khi có typed DSL:
extra["publicApi"] = "yes"
extra["owner"] = "api-team"
```

String keys/value không bảo đảm kiểu, dễ typo, thiếu IDE completion và Provider input contract. Chỉ dùng `extra` cho trường hợp thực sự không cần plugin contract lâu dài.

### 15.4. Sửa Gradle task ở configuration phase để tạo output

```kotlin
// Anti-pattern: chạy công việc ngay khi Gradle chỉ định cấu hình.
file("build/reports/result.txt").writeText("ready")
```

Điều này chạy cả với `./gradlew help`, không khai báo task inputs/outputs và có thể làm hỏng caching. Output phải do task action/Work API có declared outputs tạo.

### 15.5. Một plugin nhiều feature flags vô hạn

```kotlin
// Không phải API tốt nếu mỗi module bật/tắt sâu vào nội tạng:
moduleNeeds {
    skipCompileChecks.set(true)
    customCheckTaskName.set("x")
    replaceVerificationImplementation.set(true)
}
```

Khi capabilities thật sự độc lập, tách plugins như `company.java-library`, `company.api-policy`, `company.test-policy` hoặc `company.publish-policy`. Mỗi plugin cung cấp một hợp đồng nhỏ có owner/semantics rõ.

## 16. Bài tập tự kiểm tra

1. **Extension được đăng ký bằng API nào?** `project.extensions.create("moduleNeeds", ModuleNeedsExtension.class)`.
2. **Module cần biết class `VerifyModuleNeedsTask` không?** Không, module chỉ dùng typed extension.
3. **`convention(false)` có cho module set true không?** Có.
4. **`set(extension.getOwner())` có khác `set(extension.getOwner().get())` không?** Có; cách đầu giữ Provider relation, cách sau resolve sớm.
5. **Tại sao dùng `RegularFileProperty` thay path String?** File input metadata, lazy wiring và Gradle normalization tốt hơn.
6. **`@Optional` có bỏ yêu cầu docs khi `publicApi=true` không?** Không; policy trong task vẫn kiểm.
7. **`@Input` cần thiết để làm gì?** Khai báo dữ liệu ảnh hưởng task output/up-to-date/cache.
8. **`@CacheableTask` tự làm mọi side effects an toàn?** Không; chỉ cho phép cache khi contract inputs/outputs đúng.
9. **`@OutputFile` của demo có nằm ở root chung không?** Không; mỗi module có buildDirectory riêng.
10. **`tasks.register` có thực thi task action ngay không?** Không.
11. **Vì sao tránh `afterEvaluate`?** Dễ gây mutation muộn; Provider/tasks.named giúp wiring lazy hơn.
12. **`check` được nối ở đâu?** Bên trong plugin, không phải mỗi module.
13. **`./gradlew :service:classes` có thay `:service:check` không?** Không.
14. **Module không apply plugin có task verifier không?** Không; CI phải kiểm coverage khi cần.
15. **Khi muốn thêm tập capabilities không trùng, dùng type gì?** `SetProperty<String>`.
16. **Khi muốn hỗ trợ nhiều named API specs, dùng gì?** Có thể dùng `NamedDomainObjectContainer` sau khi nhu cầu đủ phức tạp.
17. **TestKit khác test hàm thuần ở đâu?** Nó chạy một Gradle build thật và kiểm DSL/task graph/outcomes.
18. **Dùng `Plugin<Project>` nghĩa là gì?** Plugin áp cho từng project/module.
19. **Nếu module là Android thay Java library, làm gì?** Chọn plugin/convention phù hợp, không áp Java convention bừa bãi.
20. **Nguyên tắc nào quyết định extension property mới?** Module hiểu và khai báo được nhu cầu, còn plugin tiếp tục sở hữu cơ chế.

## 17. Checklist nghiệm thu

- [ ] Plugin API cho phép modules khai báo yêu cầu, không bắt modules copy task logic.
- [ ] Extension name rõ, không trùng plugin extensions khác.
- [ ] Có typed managed properties thay các field/`extra` strings tùy ý.
- [ ] Defaults dùng `convention()` và có policy cho mandatory values.
- [ ] Optional inputs được đánh dấu đúng `@Optional`; rules nghiệp vụ vẫn được validate.
- [ ] Plugin nối providers tới task inputs mà không gọi `get()` trong `apply()`.
- [ ] Task có `@Input`/`@InputFile`/`@OutputFile` đầy đủ.
- [ ] Report outputs tách theo mỗi module; không tạo file ở configuration phase.
- [ ] `TaskProvider`/`tasks.register`/`tasks.named` dùng thay eager task creation.
- [ ] Không phụ thuộc `afterEvaluate` hay hardcoded `project.name` branching.
- [ ] `check` lifecycle bao gồm verifier cho modules áp plugin.
- [ ] Error messages chỉ rõ property thiếu/sai, không làm CI xanh giả.
- [ ] Có test/defaults/override/fail cases, multi-project và configuration-cache checks.
- [ ] Code/build-logic được quản lý version, review và TestKit kiểm thử.
- [ ] Không dùng credential/token trong extension examples hoặc reports.
- [ ] Với policy bắt buộc, CI phát hiện modules quên áp plugin.
- [ ] Module build files vẫn ngắn: nói nhu cầu, không nói cách thực hiện.
- [ ] Java 17/Gradle Wrapper/toolchains đáp ứng compatibility requirements.
- [ ] Khi thay extension API, có migration/deprecation plan.
- [ ] Exceptions phải có scope và approval, không `disableAllChecks`.
- [ ] Có thể thêm module mới mà không sửa plugin implementation chỉ để nhận diện tên module.

## 18. Ghi nhớ

- **Extension là hợp đồng DSL công khai** để modules khai báo nhu cầu.
- **Plugin** chịu trách nhiệm áp conventions, đăng ký tasks và nối lifecycle.
- **Task type** chứa input/output annotations, validation và công việc thực thi.
- **`convention()` thiết lập fallback**, **`set()` thiết lập giá trị cụ thể**, **`set(Provider)` giữ lazy dataflow**.
- **Không `get()` extension quá sớm trong `Plugin.apply()`**; module chưa chắc đã cấu hình xong.
- **`tasks.register` + `TaskProvider` + `tasks.named("check")`** giữ wiring lazy và tập trung.
- **Public API thì yêu cầu docs** là chính sách; module chỉ khai báo `publicApi=true` và file.
- **`build-logic` là included build cho plugin resolution**, không phải một project Java API của ứng dụng.
- **Cache/configuration cache cần inputs/outputs rõ**, không giải quyết bằng việc in logs ở `doLast`.
- **Thiết kế extension ít thuộc tính, có ý nghĩa, typed và test được** là chìa khóa để build logic dùng chung phát triển bền vững.

## Tài liệu chính thức

- [Gradle — Introduction to Plugins](https://docs.gradle.org/current/userguide/custom_plugins.html): plugins, conventions, extension containers và project scope.
- [Gradle — Implementing Gradle Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): precompiled/binary plugins.
- [Gradle — Precompiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html): typed extension, defaults và mapping properties.
- [Gradle — Java Gradle Plugin Development](https://docs.gradle.org/current/userguide/java_gradle_plugin.html): `java-gradle-plugin`, metadata, TestKit.
- [Gradle — Add an Extension](https://docs.gradle.org/current/userguide/part2_add_extension.html): plugin extension API.
- [Gradle — Properties and Providers](https://docs.gradle.org/current/userguide/custom_gradle_types.html): `Property`, `Provider`, `convention`, lazy values.
- [Gradle — Custom Tasks](https://docs.gradle.org/current/userguide/implementing_custom_tasks.html): inputs/outputs, `@TaskAction`.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `register`, `named`, `configureEach`.
- [Gradle — Toolchains for JVM Projects](https://docs.gradle.org/current/userguide/toolchains.html): Java toolchain defaults.
- [Gradle — Testing Plugins](https://docs.gradle.org/current/userguide/testing_gradle_plugins.html): TestKit functional testing.
- [Gradle — TestKit](https://docs.gradle.org/current/userguide/test_kit.html): GradleRunner, plugin classpath injection.
- [Gradle — Build Cache](https://docs.gradle.org/current/userguide/build_cache.html): task cache behavior.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): execution model and provider limitations.
- [Gradle — Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): included build logic and sharing conventions.
