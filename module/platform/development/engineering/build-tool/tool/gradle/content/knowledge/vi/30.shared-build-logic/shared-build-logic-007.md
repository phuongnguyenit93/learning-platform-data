# Quản lý dependency của build logic tách khỏi dependency ứng dụng trong Gradle

## 1. Cùng là `dependencies` nhưng không phải cùng một classpath

Một dự án Java sử dụng Gradle có ít nhất **hai thế giới mã nguồn** cùng xuất hiện trong quá trình build:

1. **Build logic**: mã giúp Gradle hiểu cần áp dụng plugin nào, tạo/cấu hình task nào, kiểm tra project ra sao và tổ chức quy trình build như thế nào. Nó chạy trong quá trình **Gradle thực thi build**, thường trên Gradle JVM và plugin/build-script classloaders.
2. **Application/library code**: mã `src/main/java` hoặc `src/main/kotlin` mà dự án đang tạo ra. Nó được biên dịch thành classes/JAR, chạy trên JVM của ứng dụng hoặc được thư viện bên ngoài sử dụng.

Hai thế giới này đều có thể khai báo thư viện Java, nhưng **lý do và nơi chúng cần thư viện hoàn toàn khác nhau**.

Ví dụ:

- Một convention plugin dùng **Guava** để chuẩn hóa nhãn task trong build. Guava phải có mặt khi **plugin được chạy bởi Gradle**, không phải vì ứng dụng Java cần Guava.
- Ứng dụng dùng **Apache Commons Lang** trong phương thức `Main.main`. Commons Lang phải có mặt trên **compile/runtime classpath của ứng dụng**, không phải dependency bắt buộc để compile convention plugin.
- JUnit Jupiter phục vụ **unit tests của ứng dụng**; nó không tự trở thành library runtime của ứng dụng và cũng không tự là test dependency của project chứa build logic.

Kết luận quan trọng:

> **`implementation(...)` có ý nghĩa trong phạm vi project và plugin đã khai báo nó.** `implementation("com.google.guava:guava:...")` trong `build-logic/build.gradle.kts` không tự thêm Guava vào `app:runtimeClasspath`. Muốn ứng dụng dùng Guava, phải khai báo dependency tương ứng ở app hoặc để một plugin chủ động thêm dependency vào project app.

Đây là kỹ thuật cốt lõi khi xây dựng **build logic dùng chung**: giữ cho build tools không trộn với thư viện nghiệp vụ, tránh classpath phình to, xung đột versions và rủi ro đưa công cụ build vào sản phẩm đã phát hành.

## 2. Sơ đồ các classpath và repository độc lập

```text
                      Gradle invocation
                              |
        +---------------------+---------------------+
        |                                           |
        v                                           v
  BUILD LOGIC WORLD                         APPLICATION WORLD
        |                                           |
        +-- settings.gradle.kts                     +-- app/build.gradle.kts
        |     pluginManagement                      |     plugins { ... }
        |                                           |
        +-- included build: build-logic              +-- src/main/java
        |     build.gradle.kts                       |
        |       plugins { java-gradle-plugin }       +-- implementation(commons-lang3)
        |       implementation(Guava)                |
        |                                           +-- src/test/java
        +-- JavaConventionsPlugin.java               |     testImplementation(JUnit)
        |     ConventionInfoTask.java                |
        |       imports Guava CaseFormat             +-- compileClasspath/runtimeClasspath
        |                                           |     commons-lang3
        v                                           v
  Gradle plugin classpath                       Application classpath
  Guava hỗ trợ plugin/task                      Commons Lang hỗ trợ Main
        |                                           |
        +------ plugin có thể CẤU HÌNH app ---------+
               nhưng dependency plugin KHÔNG
               tự chuyển thành dependency app
```

Có thể hình dung một plugin như một **công cụ trong xưởng**, còn application dependencies như **linh kiện trong sản phẩm**. Búa, thước hay thiết bị kiểm thử phục vụ công đoạn sản xuất; không tự được đóng gói vào sản phẩm khi nó rời xưởng.

Điều này là **mô hình khái niệm**, không khẳng định Gradle chỉ có đúng hai Java classloaders. Thực tế còn Gradle runtime, settings script, build scripts, plugin classloaders, included builds, annotation processors và toolchains. Điểm cần bảo toàn là **phạm vi dependency resolution và classpath của từng mục đích**.

### 2.1. Bảng phân biệt nhanh

| Nơi cấu hình | Dependency phục vụ | Có tự nằm trên runtime classpath ứng dụng? |
| --- | --- | --- |
| `build-logic/build.gradle.kts` → `implementation` | Mã custom plugin/task trong build logic | **Không** |
| `buildSrc/build.gradle.kts` → `implementation` | Mã build logic trong `buildSrc` | **Không** |
| `buildscript { dependencies { classpath(...) } }` | Legacy build script/plugin classpath | **Không** |
| `plugins { id("...") version "..." }` | Gradle plugin áp dụng cho project | **Không**, trừ khi plugin chủ động thêm app dependency |
| `pluginManagement.repositories` | Tìm plugin markers/implementations theo plugin DSL | Không phải app runtime repository |
| `app/dependencies { implementation(...) }` | Mã chính ứng dụng khi compile và chạy | **Có** trên runtime classpath của app |
| `app/dependencies { runtimeOnly(...) }` | Mã chỉ cần khi chạy | **Có** trên runtime classpath |
| `app/dependencies { testImplementation(...) }` | Compile/chạy test trong test source set | Không tự vào main runtime classpath |
| `app/dependencies { compileOnly(...) }` | Compile nhưng không được đưa vào main runtime bởi khai báo đó | Không |
| `annotationProcessor(...)` | Processor chạy khi JavaCompile biên dịch | Không mặc định là app runtime |
| `gradlePluginPortal()` | Repository tìm plugin artifacts | Không tự làm application repository |

**Một thư viện có thể xuất hiện ở nhiều phạm vi nếu bạn khai báo nó ở nhiều nơi.** Khi Guava vừa là tool dependency của plugin vừa là implementation dependency của app, hai khai báo có thể dùng versions khác nhau, tùy Gradle/plugin compatibility và graph riêng. Không nên cố dựa vào Guava do Gradle/plugin đã tải để app biên dịch.

## 3. Nhiều cơ chế build logic và phạm vi dependency của chúng

Gradle hỗ trợ nhiều cách tổ chức mã build logic. Cần biết chúng chạy ở đâu để đặt dependency vào đúng nơi.

### 3.1. Build script trực tiếp

Một project có thể viết logic ngay trong `build.gradle.kts`:

```kotlin
plugins {
    java
}

tasks.register("printInfo") {
    doLast {
        println("Build logic in this build script")
    }
}
```

Đoạn script được Gradle đánh giá để cấu hình tasks; nó không trở thành Java class của ứng dụng. Khi script phức tạp hoặc nhiều modules dùng chung, nên trích thành plugin/convention plugin có cấu trúc và kiểm thử riêng.

### 3.2. `buildSrc`

`buildSrc` là thư mục đặc biệt được Gradle phát hiện ở root của build. Gradle biên dịch source ở đó rồi đưa classes/build logic của nó vào classpath build scripts của build chính.

Ví dụ:

```text
root/
├── settings.gradle.kts
├── build.gradle.kts
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/java/dev/learning/BuildHelper.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/...
```

Nếu `buildSrc` cần thư viện khi biên dịch helper:

```kotlin
// buildSrc/build.gradle.kts
plugins {
    `java-gradle-plugin`
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.google.guava:guava:33.3.0-jre")
}
```

Guava ở đây là dependency của **buildSrc project**. Việc `BuildHelper.java` có thể dùng `CaseFormat` không làm `app/src/main/java` tự import được Guava.

`buildSrc` rất tiện cho bước đầu, nhưng Gradle thường phải biên dịch và quan sát thay đổi `buildSrc` trước khi cấu hình main build. Với dự án lớn, `buildSrc` có thể làm nhiều build scripts/configuration phụ thuộc chung vào một phạm vi build logic rộng. Do đó **included build `build-logic` chuyên dụng** thường phù hợp hơn cho logic dùng chung quy mô lớn. Đây là khuyến nghị tổ chức, không phải `buildSrc` bị cấm.

### 3.3. Included build `build-logic`

Một thư mục `build-logic` có `settings.gradle.kts`, `build.gradle.kts` và source độc lập có thể là một **included build**. Nó có dependency repositories, configurations và plugin tasks của riêng mình.

Ví dụ trong root settings:

```kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "dependency-boundaries-lab"
include("app")
```

Khi `build-logic` tạo Gradle plugins, `pluginManagement.includeBuild(...)` giúp plugin resolution ở main build tìm plugin từ source local **sớm đủ để áp dụng trong `plugins { ... }`**.

Trong một số cấu trúc khác, `includeBuild("build-logic")` nằm ngoài `pluginManagement` cũng có thể tham gia composite builds và plugin resolution theo mô hình phù hợp. Nhưng bài này dùng dạng trong `pluginManagement` cho **plugin-producing build** để ý định rõ ràng. Không nhầm nó với `include(":build-logic")`: latter sẽ đăng ký subproject, không tạo một included build riêng.

### 3.4. Plugin đã publish trên Plugin Portal/Maven repository

Khi plugin được phát hành để nhiều dự án dùng:

```kotlin
plugins {
    id("some.public.plugin") version "1.2.3"
}
```

Gradle cần resolve plugin ID, version, marker và implementation từ những plugin repositories thích hợp. Các JAR đó phục vụ **Gradle build logic**; không tự biến thành app dependencies.

Trong bài, ID/version trên là **minh họa cú pháp**, không phải lời khẳng định có plugin thực tên `some.public.plugin`. Ví dụ runnable sẽ dùng plugin local `dev.learning.java-conventions` do chính build tạo.

## 4. Phân biệt repository dùng cho plugin, build logic và ứng dụng

Cùng là `mavenCentral()` hoặc `gradlePluginPortal()`, nhưng **nơi khai báo** quyết định phạm vi dùng.

### 4.1. `pluginManagement.repositories`

Trong `settings.gradle.kts` của main build:

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

Danh sách này chủ yếu giải quyết **plugin requests** từ `plugins { ... }` và plugin resolution của build tương ứng. Nếu một plugin chỉ có trong repository nội bộ, cần cấu hình plugin repository phù hợp tại đây hoặc qua các cơ chế plugin resolution được Gradle hỗ trợ.

**Không** suy ra ứng dụng sẽ tải được `org.apache.commons:commons-lang3` chỉ vì main build có `pluginManagement.repositories.mavenCentral()`.

### 4.2. `app.repositories` hoặc `dependencyResolutionManagement.repositories`

Trong `app/build.gradle.kts`:

```kotlin
repositories {
    mavenCentral()
}
```

Đây là nơi project `:app` resolve các dependencies `implementation`, `testImplementation`, `runtimeOnly` v.v. Nếu tổ chức dùng tập trung repositories ở settings:

```kotlin
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
```

thì cần tuân theo repository mode của build. Với `RepositoriesMode.FAIL_ON_PROJECT_REPOS`, không nên thêm `repositories` vào từng project nữa. Ví dụ runnable của bài dùng cách khai báo **tại app project** để thấy ranh giới rõ.

### 4.3. `build-logic.repositories`

Included build `build-logic` là một Gradle build riêng, nên nó phải có nguồn lấy **dependency của plugin implementation**:

```kotlin
// build-logic/build.gradle.kts
repositories {
    mavenCentral()
}

dependencies {
    implementation("com.google.guava:guava:33.3.0-jre")
}
```

Không phải vì main build có `app.repositories.mavenCentral()` mà `build-logic` tự mượn repository này. Nếu build logic cần private Maven repository, phải cấu hình phù hợp **trong build logic/settings của nó**, không khai báo nhầm ở `:app`.

### 4.4. `buildscript.repositories` và legacy classpath

Legacy plugin/build logic có thể viết:

```kotlin
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath("org.apache.commons:commons-lang3:3.14.0")
    }
}
```

Đây là **build script classpath**, không phải `app:implementation`. Một library có mặt ở đó có thể được build script/plugin sử dụng trong bối cảnh classloader phù hợp, nhưng Java source của ứng dụng vẫn cần dependency của chính nó khi import lớp đó.

`buildscript` hữu ích khi làm việc với một số legacy plugins; với plugin hiện đại, thường ưu tiên `plugins { ... }`, `pluginManagement` và convention plugins để dễ hiểu plugin resolution/versions.

### 4.5. Bảng repository và configuration

| Câu hỏi | Nơi cần kiểm tra |
| --- | --- |
| Plugin ID từ `plugins` được tìm ở đâu? | `settings.pluginManagement.repositories` hoặc plugin-producing included build |
| JAR giúp chạy custom Gradle plugin được tìm ở đâu? | Repositories của project build plugin, ví dụ `build-logic.repositories` |
| Commons Lang được `:app` tải ở đâu? | `:app.repositories` hoặc `dependencyResolutionManagement.repositories` |
| Legacy plugin classpath được tải ở đâu? | `buildscript.repositories` |
| App test libraries được tìm ở đâu? | Cùng project dependency repositories nhưng configuration `testImplementation`/`testRuntimeOnly` |
| Plugin publish ra repository nào? | `publishing.repositories` của plugin-producing build |
| App/library artifacts publish ra repository nào? | `publishing.repositories` của project ứng dụng/thư viện |

**Repository không phải classpath.** Repository cho biết Gradle có thể tìm artifacts ở đâu; **configuration/dependency declaration** quyết định artifact có thuộc graph nào. Có `mavenCentral()` mà không khai báo `implementation` cũng không tự đặt Commons Lang vào compile classpath của app.

## 5. Bài thực hành hoàn chỉnh: Java 17, hai dependency graphs độc lập

Ta xây project gồm:

- Một **included build `build-logic`** viết **binary Gradle plugin bằng Java 17**.
- Plugin đó dùng **Guava `CaseFormat`** trong một task Gradle `conventionInfo`.
- Một **app Java 17** áp dụng plugin trên, nhưng trong source ứng dụng chỉ dùng **Apache Commons Lang `StringUtils`**.
- App có unit test JUnit 5, để làm rõ test dependency cũng có phạm vi riêng.
- Các lệnh xem `runtimeClasspath` của app và build-logic chứng minh **Guava không tự xuất hiện trong graph của app**.

### 5.1. Cấu trúc thư mục

```text
dependency-boundaries-lab/
├── settings.gradle.kts
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/java/dev/learning/
│       ├── JavaConventionsPlugin.java
│       └── ConventionInfoTask.java
└── app/
    ├── build.gradle.kts
    └── src/
        ├── main/java/demo/Main.java
        └── test/java/demo/MainTest.java
```

Không cần tạo sẵn `build/`. Gradle tạo output khi compile/run. Với project mới, nếu chưa có Gradle Wrapper, cần Gradle tương thích đã cài để sinh Wrapper một lần.

**Môi trường:** Gradle hiện đại hỗ trợ Java 17 (ví dụ Gradle 8.5+), JDK 17 được Gradle nhận diện, Maven Central hoặc dependency cache phù hợp. Ví dụ không cần Android SDK, Kotlin application plugin, Docker hay credential repository.

### 5.2. Root `settings.gradle.kts`

```kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "dependency-boundaries-lab"
include("app")
```

Phân tích:

- `includeBuild("build-logic")` đăng ký plugin-producing build cục bộ.
- `include("app")` đăng ký **subproject ứng dụng** trong main build.
- `build-logic` có `settings` riêng, không phải `:build-logic` subproject của root.
- Root project name là `dependency-boundaries-lab`; nó không ảnh hưởng tọa độ Commons Lang/Guava.
- Chưa cần thêm plugin repository ngoài mặc định vì các Gradle plugins sử dụng trong lab là built-in hoặc plugin local của included build.

### 5.3. `build-logic/settings.gradle.kts`

```kotlin
rootProject.name = "build-logic"
```

Một build độc lập nên có identity dễ phân biệt. Nếu có nhiều included builds trong dự án thật, hãy tránh tên build trùng khiến Gradle khó định danh project/task paths.

### 5.4. `build-logic/build.gradle.kts`

```kotlin
plugins {
    `java-gradle-plugin`
}

repositories {
    mavenCentral()
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

dependencies {
    // Chỉ phục vụ compile/runtime của custom Gradle plugin.
    implementation("com.google.guava:guava:33.3.0-jre")
}

gradlePlugin {
    plugins {
        create("javaConventions") {
            id = "dev.learning.java-conventions"
            implementationClass = "dev.learning.JavaConventionsPlugin"
        }
    }
}
```

Plugin `java-gradle-plugin` (Gradle Plugin Development plugin) giúp đăng ký plugin ID/implementation class, cung cấp Gradle API cho plugin compilation theo cơ chế của nó và tạo plugin descriptors.

**Guava nằm trong `dependencies` của project `build-logic`**, không nằm trong `app`. Nó được tải để mã `ConventionInfoTask` có thể import `com.google.common.base.CaseFormat`. Phần plugin implementation và các dependency cần thiết phải có thể được Gradle load khi plugin/task chạy.

Không gọi `implementation("com.google.guava:guava:...")` trong app chỉ để “cho plugin chạy được”: đó sẽ là cách thêm Guava vào graph ứng dụng không cần thiết, không sửa đúng nguyên nhân nếu build-logic thiếu classpath.

### 5.5. Mã Java đăng ký plugin

**File `build-logic/src/main/java/dev/learning/JavaConventionsPlugin.java`:**

```java
package dev.learning;

import org.gradle.api.Plugin;
import org.gradle.api.Project;

public final class JavaConventionsPlugin implements Plugin<Project> {
    @Override
    public void apply(Project project) {
        project.getPluginManager().apply("java");

        project.getTasks().register(
                "conventionInfo",
                ConventionInfoTask.class
        );
    }
}
```

Lớp triển khai `Plugin<Project>`, được Gradle gọi khi project áp dụng ID `dev.learning.java-conventions`.

- `apply("java")` yêu cầu project app có Java plugin.
- `register("conventionInfo", ...)` tạo một task cho app.
- Plugin **không thêm Guava vào `app.dependencies`**.
- Task type `ConventionInfoTask` do build logic cung cấp, không phải một class ứng dụng.

Trong project thật, convention plugin có thể cấu hình toolchain, compiler flags, test framework hoặc quality checks, nhưng không phải tùy chỉnh nào cũng nên thực hiện vô điều kiện. Bài lab cố tình giữ plugin nhỏ và dễ kiểm tra để tập trung vào dependency isolation.

### 5.6. Custom task thật sự gọi Guava

**File `build-logic/src/main/java/dev/learning/ConventionInfoTask.java`:**

```java
package dev.learning;

import com.google.common.base.CaseFormat;
import org.gradle.api.DefaultTask;
import org.gradle.api.tasks.TaskAction;

public abstract class ConventionInfoTask extends DefaultTask {
    @TaskAction
    public void printConventionInfo() {
        String label = CaseFormat.LOWER_HYPHEN.to(
                CaseFormat.UPPER_CAMEL,
                "build-logic"
        );

        getLogger().lifecycle("Build logic helper: " + label);
    }
}
```

Lệnh `CaseFormat.LOWER_HYPHEN.to(CaseFormat.UPPER_CAMEL, "build-logic")` trả về **`BuildLogic`**. Đây là nơi dependency Guava **được sử dụng thật** bởi một Gradle task implementation.

Task này chỉ ghi một dòng diagnostic, không tạo output files và không được thiết kế để cache. Gradle có thể chạy task trong mọi invocation được yêu cầu; đây là hành vi phù hợp cho một task minh họa. Với task biến đổi file trong production, phải khai báo `@Input`/`@OutputFile` hoặc các Gradle Property APIs và đảm bảo tương thích configuration cache.

### 5.7. `app/build.gradle.kts`

```kotlin
plugins {
    application
    id("dev.learning.java-conventions")
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}

repositories {
    mavenCentral()
}

dependencies {
    // Chỉ app cần Commons Lang để chạy Main.main.
    implementation("org.apache.commons:commons-lang3:3.14.0")

    // Test dependencies thuộc test classpath của app.
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
}

application {
    mainClass.set("demo.Main")
}

tasks.test {
    useJUnitPlatform()
}
```

Chú ý:

- `application` là Gradle built-in plugin, cung cấp task `run`.
- `id("dev.learning.java-conventions")` tìm plugin từ included `build-logic`; không cần publish plugin lên Portal.
- Custom plugin `apply("java")` và Application plugin cùng yêu cầu Java plugin; Gradle áp dụng Java plugin theo cơ chế idempotent, không tạo hai Java plugins xung đột chỉ vì được yêu cầu ở hai nơi.
- `repositories.mavenCentral()` trong app dùng cho Commons Lang và JUnit của app; **không thay thế** `repositories` trong build-logic.
- `implementation(commons-lang3)` đưa Commons Lang vào main compile/runtime classpaths.
- `testImplementation(JUnit)` không tự thêm JUnit vào `app:runtimeClasspath` dành cho source main.
- Không có `implementation(Guava)` trong app: app không cần Guava để build hoặc chạy Java code chính.

### 5.8. Mã ứng dụng

**File `app/src/main/java/demo/Main.java`:**

```java
package demo;

import org.apache.commons.lang3.StringUtils;

public final class Main {
    private Main() {
    }

    public static String greeting(String name) {
        return "Hello, " + StringUtils.capitalize(name) + "!";
    }

    public static void main(String[] args) {
        String name = args.length == 0 ? "gradle" : args[0];
        System.out.println(greeting(name));
    }
}
```

`Main` import `StringUtils` từ Commons Lang vì đó là **ứng dụng cần** thư viện này. Không import Guava `CaseFormat`; class đó thuộc code plugin của build logic.

**File `app/src/test/java/demo/MainTest.java`:**

```java
package demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

final class MainTest {
    @Test
    void createsGreeting() {
        assertEquals("Hello, Gradle!", Main.greeting("gradle"));
    }
}
```

Test sử dụng JUnit Jupiter từ `app:testImplementation`. Plugin build logic không cần JUnit Jupiter của app để compile mã plugin.

### 5.9. Tạo Gradle Wrapper và chạy

Nếu repo đã có Gradle Wrapper, giữ Wrapper có sẵn. Nếu dựng project hoàn toàn mới, máy cần bản Gradle tương thích để chạy một lần:

```bash
gradle wrapper
```

Sau đó, từ thư mục **`dependency-boundaries-lab`**:

Linux/macOS:

```bash
./gradlew --version
./gradlew :app:conventionInfo --console=plain
./gradlew :app:run --quiet
./gradlew :app:test --console=plain
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat :app:conventionInfo --console=plain
.\gradlew.bat :app:run --quiet
.\gradlew.bat :app:test --console=plain
```

Khi build-logic, Java toolchain và dependencies được chuẩn bị đúng:

**Dòng do custom Gradle task `conventionInfo` ghi ở mức lifecycle:**

```text
Build logic helper: BuildLogic
```

**Stdout do ứng dụng `Main.main` tạo khi chạy `:app:run --quiet`:**

```text
Hello, Gradle!
```

Gradle có thể in thêm các dòng task và build status cho `conventionInfo` vì đang chạy `--console=plain`, nhưng chuỗi của custom task là chính xác như trên. Lệnh `:app:test` cần hoàn thành không có assertion failures.

**Các lệnh trên không khẳng định app đã chứa Guava.** Nó chứng minh plugin chạy được với Guava ở classpath build logic, còn ứng dụng dùng Commons Lang của chính mình.

## 6. Chứng minh hai dependency graphs không trộn nhau

### 6.1. Xem app compile/runtime classpaths

Đứng tại root project:

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
```

Với lab:

- `compileClasspath` của app chứa `org.apache.commons:commons-lang3:3.14.0`.
- `runtimeClasspath` của app cũng chứa Commons Lang vì `implementation`.
- `testRuntimeClasspath` chứa những dependency cần cho app tests, gồm JUnit/JUnit Platform theo cấu hình.
- **Guava không được app yêu cầu qua `implementation`, nên không phải dependency của app chỉ vì plugin dùng nó.**

Nếu một plugin khác hoặc dependency khác của app chủ động kéo Guava vào, graph thực sẽ khác. Điều đúng cần nói là: **plugin dependency không tự được copy sang app runtime graph**; không phải “Guava tuyệt đối không thể xuất hiện trong mọi build”.

### 6.2. Xem build-logic runtimeClasspath riêng

Dùng Wrapper ở root để yêu cầu Gradle chạy một task trên thư mục build-logic độc lập:

```bash
./gradlew -p build-logic dependencies --configuration runtimeClasspath
```

Windows PowerShell:

```powershell
.\gradlew.bat -p build-logic dependencies --configuration runtimeClasspath
```

Output của project `build-logic` có `com.google.guava:guava:33.3.0-jre` cùng các transitive dependencies tương ứng. Project build-logic không tự có dependency `org.apache.commons:commons-lang3:3.14.0` chỉ vì app đã khai báo Commons Lang.

Nếu muốn dùng tasks của included build từ root, có thể xem build identity trong composite và gọi path thích hợp theo Gradle version; cách `-p build-logic` ở trên rõ ràng về project directory mà ta muốn quan sát.

### 6.3. So sánh bằng `dependencyInsight`

Ở app:

```bash
./gradlew :app:dependencyInsight \
    --dependency commons-lang3 \
    --configuration runtimeClasspath
```

Lệnh một dòng nếu shell không hỗ trợ backslash:

```bash
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
```

Ở build-logic:

```bash
./gradlew -p build-logic dependencyInsight --dependency guava --configuration runtimeClasspath
```

`dependencyInsight` giúp thấy vì sao module/version được chọn trong **configuration đang hỏi**. Đừng chạy `:app:dependencyInsight --dependency guava` rồi kết luận Guava “không có ở bất kỳ đâu” khi lệnh chỉ xét graph của app.

### 6.4. Thử import Guava vào application source

Trên **bản sao** project, thêm import và lời gọi sau vào code app:

```java
// Mảnh minh họa đặt trong app, không phải file Java độc lập:
import com.google.common.base.CaseFormat;
```

```java
// Mảnh phương thức/biểu thức dùng trong app:
String label = CaseFormat.LOWER_HYPHEN.to(
        CaseFormat.UPPER_CAMEL,
        "app-source"
);
```

Nếu app không khai báo Guava và không có dependency khác đưa Guava vào compile classpath, `:app:compileJava` **không thể resolve `com.google.common.base.CaseFormat`**. Build logic dùng Guava không cứu được lỗi compiler của app.

**Cách sửa đúng tùy mục đích:**

- Nếu đây thực sự là chức năng ứng dụng: thêm `implementation("com.google.guava:guava:33.3.0-jre")` trong **`app/build.gradle.kts`**, đánh giá API/license/security/runtime.
- Nếu chỉ cần chuẩn hóa nhãn task Gradle: giữ code Guava ở **build-logic**, bỏ import khỏi app.
- Nếu một plugin muốn áp đặt common dependency cho app: plugin phải **chủ động cấu hình app dependency** (xem mục 8), không kỳ vọng classpath tự tràn qua ranh giới.

Sau thí nghiệm, khôi phục `Main.java` bản gốc để project chạy như mục 5.

## 7. Tại sao một plugin có dependency riêng vẫn có thể thêm app dependency?

Cần phân biệt hai thao tác:

1. **Plugin sử dụng thư viện để tự chạy**: `build-logic.dependencies.implementation(Guava)` làm Gradle plugin task dùng được `CaseFormat`.
2. **Plugin cấu hình dependencies cho project mà nó áp dụng**: `project.getDependencies().add("implementation", "...")` làm **application project** nhận một dependency mới.

Cùng là plugin nhưng hai hành vi khác nhau.

### 7.1. Ví dụ plugin cố ý thêm dependency vào app

Mảnh Java để đặt trong `apply(Project project)` của custom plugin **nếu chính sách tổ chức muốn làm vậy**:

```java
project.getPluginManager().apply("java");

project.getDependencies().add(
        "implementation",
        "com.google.guava:guava:33.3.0-jre"
);
```

Khi plugin được app áp dụng, Guava sẽ trở thành dependency trong `app:implementation`, được resolve qua repositories của app. **Đó là một quyết định cấu hình tường minh, không phải hệ quả tự động từ Guava nằm trong build-logic.**

Mảnh này không cần thêm vào project lab; nếu thêm thì thí nghiệm `app không có Guava` ở mục 6 sẽ không còn đúng.

### 7.2. Quy tắc áp dụng dependency qua convention plugin

Một convention plugin có thể thêm các dependencies **có chủ đích** để thống nhất:

- JUnit test runtime / testImplementation khi team quy định.
- Logging API hoặc annotation processor dùng chung.
- Plugin kiểm tra code quality với tool dependencies riêng.
- Dependency platform/BOM theo policy.
- Library dùng trong generated code khi thật sự cần.

Nhưng cần tránh giấu quá nhiều dependencies quan trọng ở nơi developers không nhìn thấy. Convention plugin nên có tên rõ, tài liệu chính sách, khả năng chẩn đoán graph và test đảm bảo cấu hình không thêm nhầm runtime dependencies.

### 7.3. Không gọi `project.dependencies.add` trước khi configuration tồn tại

Trong plugin code, một configuration như `implementation` thường được tạo khi Java plugin đã áp dụng. Nếu plugin thêm dependency trước khi áp dụng Java plugin, có thể gặp lỗi configuration không tồn tại.

Do đó thứ tự minh họa:

```java
project.getPluginManager().apply("java");
project.getDependencies().add(
        "implementation",
        "org.apache.commons:commons-lang3:3.14.0"
);
```

có ý nghĩa khi custom plugin thật sự muốn thống nhất Commons Lang ở app. Nhưng cách này cũng làm plugin ảnh hưởng app dependency graph; nên chỉ dùng khi đúng yêu cầu, không dùng để sửa thiếu dependency của chính plugin build-logic.

## 8. `plugins` DSL, `buildscript` và dependency của plugin khác nhau ở đâu?

### 8.1. `plugins { id(...) }`: yêu cầu plugin theo ID

Ví dụ:

```kotlin
plugins {
    id("dev.learning.java-conventions")
}
```

Khi plugin nằm trong included build đã được đăng ký ở `pluginManagement.includeBuild`, Gradle tìm implementation từ build-logic local, compile plugin và load code của nó.

Nếu dùng plugin từ repository:

```kotlin
plugins {
    id("org.example.analysis") version "1.2.3"
}
```

đây chỉ là **cú pháp minh họa**; `org.example.analysis` không được khẳng định là plugin tồn tại. Version thường giúp xác định plugin marker và implementation artifact. Plugin repositories được cấu hình tại `pluginManagement` của build liên quan.

### 8.2. `buildscript { classpath(...) }`: classpath của build script

Ví dụ legacy:

```kotlin
buildscript {
    repositories {
        mavenCentral()
    }
    dependencies {
        classpath("org.apache.commons:commons-lang3:3.14.0")
    }
}
```

Nó không làm Commons Lang tự xuất hiện trong `:app:compileClasspath`. Đây là thêm classpath để **chạy build script hoặc legacy plugin code**, không phải khai báo dependency cho output Java application.

Nếu mã Gradle script dùng plugin từ `buildscript.classpath`, có thể áp dụng theo cơ chế legacy `apply(plugin = "...")` khi plugin ID và descriptor phù hợp. Với plugin hiện đại, `plugins` DSL thường dễ quản lý phiên bản và repository hơn.

### 8.3. `build-logic implementation`: dependency để build/execute plugin

Khi `build-logic` có:

```kotlin
dependencies {
    implementation("com.google.guava:guava:33.3.0-jre")
}
```

nó tạo dependency trong **project build-logic**. Điều đó khác `buildscript.classpath` vì Guava được biên dịch/đóng gói trong **Gradle plugin implementation dependency graph** của một build độc lập. Kết quả cuối cùng vẫn là Guava phục vụ plugin code, **không phải app runtime dependency**.

### 8.4. `app implementation`: dependency sản phẩm

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.14.0")
}
```

Mục tiêu là app compile/run với Commons Lang. Khi Application plugin tạo distribution, Commons Lang có thể được đặt trong thư mục `lib` runtime của app; Guava chỉ dùng bởi convention plugin thì không có lý do tự xuất hiện ở đây.

### 8.5. Cùng tên `implementation` nhưng configuration khác

Trong mỗi project, plugin `java` hoặc `java-library` tạo những configurations phục vụ Java source của **project đó**. Build-logic là project Java riêng, app là project Java riêng.

Vì vậy câu hỏi đúng không chỉ là “đã khai báo `implementation` chưa?”, mà là:

- `implementation` **ở project nào?**
- Plugin nào đã tạo configuration?
- Task nào tiêu thụ configuration?
- Artifact nào bị đưa vào runtime/compile classpath?
- Repository nào được dùng để resolve configuration đó?

## 9. Plugin marker và implementation artifacts

Một external Gradle plugin thường có hai lớp tọa độ:

1. **Plugin ID/version** được request trong `plugins` DSL.
2. **Artifact implementation** chứa code plugin và những dependencies mà plugin cần để chạy.

Gradle Plugin Portal/marker artifacts giúp ánh xạ plugin request tới implementation. Nếu plugin đã được đăng ký trong included build qua `java-gradle-plugin`, Gradle có thể giải quyết nó từ **source build** thay vì phải publish plugin marker ra repository.

Đừng giả định việc thêm:

```kotlin
repositories {
    mavenCentral()
}
```

trong `app/build.gradle.kts` sẽ sửa lỗi:

```text
Plugin [id: 'org.example.plugin'] was not found
```

Plugin resolution thường cần cấu hình `pluginManagement.repositories` hoặc included plugin build; còn app project repository phục vụ các dependency configurations của ứng dụng.

### 9.1. Plugin dependency transitive và xung đột versions

Plugin implementation có thể phụ thuộc vào Guava, ASM, Kotlin, Groovy hoặc nhiều library khác. Những thư viện này có thể nằm trên plugin classloaders, nhưng không nên dựa vào chúng như classpath cho Java app source.

Nếu hai plugins cần versions không tương thích của cùng library, có thể phát sinh xung đột classloader hoặc API linkage trong build logic. Hướng debug là:

- Xem plugin IDs/versions và Gradle Wrapper version.
- Xem `build-logic:dependencies` hoặc legacy `buildEnvironment` đúng scope.
- Kiểm tra Java runtime chạy Gradle, plugin compatibility và classloaders.
- Không “chữa” bằng cách sửa ngẫu nhiên `app:implementation`; điều đó thường không thay đổi Gradle plugin classpath.

### 9.2. Build logic dependency không nhất thiết có trên JAR classpath của app

Kể cả khi Guava đã tải xuống trong `~/.gradle/caches` cho plugin, file cache chỉ chứng minh Gradle có artifact trên đĩa. Nó **không chứng minh artifact là một thành phần của `:app:runtimeClasspath`**.

Cache lưu artifacts phục vụ nhiều configurations/projects. Để xác định graph, luôn dùng `dependencies --configuration ...` hoặc `dependencyInsight` đúng project/configuration.

## 10. Precompiled script convention plugin: một phương án khác

Thay vì viết binary plugin Java, Gradle có thể biên dịch script convention plugin `.gradle.kts` trong một included build.

Ví dụ một **phương án độc lập**:

```text
build-logic/
├── settings.gradle.kts
├── build.gradle.kts
└── src/main/kotlin/
    └── dev.learning.java-conventions.gradle.kts
```

**File `build-logic/build.gradle.kts` trong phương án này:**

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
```

**File `build-logic/src/main/kotlin/dev.learning.java-conventions.gradle.kts`:**

```kotlin
plugins {
    `java-library`
}

java {
    toolchain.languageVersion.set(JavaLanguageVersion.of(17))
}
```

Đây là **một lựa chọn thay thế cho `java-gradle-plugin` + Java classes** ở bài lab, không phải tập file cần trộn vào ví dụ chính. Với precompiled script plugin, plugin ID thường được suy ra từ tên file script (bỏ `.gradle.kts`); phần implementation được biên dịch trong build-logic.

Nếu convention script cần một **external Gradle plugin** được áp dụng bên trong:

- Dependency artifact của external plugin có thể phải được khai báo trong `build-logic.dependencies` để script compiler/plugin implementation có nó.
- Trong một precompiled script plugin, thường apply plugin ID **không kèm version** trong khối `plugins` của convention script vì version được quản lý qua dependency của build logic.
- Plugin portal của build-logic phục vụ resolution cần thiết cho việc compile plugin build logic.
- Không đặt external plugin implementation dependency trong `app:implementation` để chữa lỗi plugin ID not found.

Ví dụ về một plugin external sẽ phụ thuộc vào **tọa độ implementation artifact và phiên bản thật**, không phải lúc nào cũng trùng hoàn toàn với plugin ID. Cần tra tài liệu đúng plugin và xác nhận Gradle version compatibility trước khi khai báo.

### 10.1. Vì sao không dùng `subprojects { ... }` để ép mọi quy tắc?

Một root script có thể viết:

```kotlin
subprojects {
    plugins.apply("java")
}
```

nhưng đây là kiểu **cross-project configuration**, dễ làm khó nhận biết project nhận policy từ đâu, tạo configuration-time coupling và cản trở một số tối ưu Gradle.

Convention plugins thường giúp:

- Mỗi project khai báo rõ plugin policy mà nó áp dụng.
- Build logic có source/tests/dependencies riêng.
- Thay đổi được review như source code.
- Tách dependencies phục vụ plugin khỏi graph của app.
- Tái sử dụng across builds khi publish plugin hoặc includeBuild.

Không nhất thiết chuyển một project rất nhỏ sang cấu trúc plugin phức tạp, nhưng khi logic dùng chung tăng nhanh, đây là hướng có lợi.

## 11. Version catalogs trong build logic và trong app

Version catalog ở main build thường nằm:

```text
gradle/libs.versions.toml
```

và xuất hiện như `libs` accessor trong các project thuộc main build nếu được cấu hình mặc định. **Included build `build-logic` là một build riêng**, do đó **không tự kế thừa version catalog của main build** chỉ nhờ `includeBuild("build-logic")`.

### 11.1. Hai catalog không tự đồng nhất

Giả sử main build có:

```toml
[versions]
commons = "3.14.0"

[libraries]
commons-lang3 = { module = "org.apache.commons:commons-lang3", version.ref = "commons" }
```

App có thể viết:

```kotlin
dependencies {
    implementation(libs.commons.lang3)
}
```

nhưng build-logic không mặc định có cùng `libs` accessor nếu chưa cấu hình version catalog riêng hoặc import catalog phù hợp.

### 11.2. Chia sẻ catalog bằng import khi thật sự cần

Một phương án trong **`build-logic/settings.gradle.kts`** nếu main repo có file `gradle/libs.versions.toml`:

```kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}

rootProject.name = "build-logic"
```

Đây là **phương án thay thế** cho file settings ngắn trong lab. Nó yêu cầu file catalog được tạo thật và đường dẫn relative phù hợp. Không dán vào lab nếu project không có file TOML tương ứng.

Dù chia sẻ **version definitions**, các dependency configurations vẫn là riêng: `build-logic.dependencies.implementation(libs.guava)` và `app.dependencies.implementation(libs.guava)` là hai khai báo ở **hai project khác nhau**. Một alias chung không biến graph thành một classpath chung.

### 11.3. Plugin aliases và plugin version management

Ở main build, có thể quản lý plugin versions trong `pluginManagement` hoặc version catalog. Included build dùng external plugin có thể cần versions riêng theo Gradle/Kotlin DSL/plugin compatibility.

Đừng assume main `libs.plugins.*` có sẵn trong `build-logic`, và cũng đừng xóa version ở mọi nơi chỉ vì muốn một chỗ quản lý chung. Mục tiêu là **version policy rõ ràng** mà vẫn giữ dependency boundaries.

## 12. Toolchain cho Java app và JVM chạy Gradle plugin

Có thể xuất hiện ba Java-related versions:

| Java context | Điều gì đang chạy? | Cách xem/cấu hình |
| --- | --- | --- |
| Gradle runtime JVM | Gradle daemon và plugin code | `./gradlew --version`, IDE Gradle JVM |
| Java toolchain cho `build-logic` | Compiler biên dịch custom plugin classes | `build-logic/java.toolchain` |
| Java toolchain cho `app` | Compiler biên dịch Java application | `app/java.toolchain` |

Bài lab chọn Java 17 toolchain cho cả build-logic và app để đơn giản. Nhưng **toolchain không tự chép thư viện plugin sang runtime classpath ứng dụng**.

Một plugin compiled cho Java 21 bytecode có thể không chạy trên Gradle daemon Java 17, dù app target Java 17 vẫn hoàn toàn hợp lệ. Ngược lại app có thể target Java 11, nhưng plugin cần chạy trên Gradle runtime Java 17 nếu Gradle/plugin version yêu cầu. Đây là hai compatibility contracts khác nhau.

### 12.1. `options.release` không thay dependency scopes

Nếu app dùng:

```kotlin
tasks.withType<JavaCompile>().configureEach {
    options.release.set(11)
}
```

thì JavaCompile giới hạn source/bytecode/Java SE API baseline 11 cho task đó. Nó **không tự thay đổi** `build-logic.dependencies.implementation(Guava)` hay chuyển Guava sang app graph. JDK compatibility và dependency classpath là hai trục cấu hình độc lập.

### 12.2. Plugin code phải hợp JVM chạy Gradle

Nếu build-logic custom plugin đang được Gradle tải, JVM chạy Gradle phải có khả năng load bytecode và APIs mà plugin sử dụng. Gradle toolchain để biên dịch plugin vẫn cần được chọn phù hợp với yêu cầu chạy plugin.

Không áp `options.release.set(8)` cho toàn bộ build logic chỉ vì app phát hành Java 8, trừ khi có chủ đích cần Gradle plugin hỗ trợ JVM 8 và Gradle version phù hợp (các Gradle hiện đại có JVM runtime tối thiểu riêng). Chọn target của plugin theo Gradle runtime compatibility, target của app theo sản phẩm.

## 13. Testing dependency của build logic khác testing dependency của app

Ứng dụng có:

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
}
```

Nếu muốn viết unit tests riêng cho plugin trong `build-logic`, phải khai báo test dependencies **ở `build-logic/build.gradle.kts`**.

Ví dụ mảnh bổ sung:

```kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.2")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.10.2")
    testImplementation(gradleTestKit())
}

tasks.test {
    useJUnitPlatform()
}
```

`gradleTestKit()` hỗ trợ Gradle TestKit khi kiểm thử plugin. Những đoạn này là **tùy chọn cho build-logic**, không phải yêu cầu để lab `conventionInfo` chạy. Việc app đã có JUnit Jupiter không tự khiến build-logic test source compile được.

### 13.1. Tại sao nên dùng TestKit cho convention plugin?

Plugin code có thể đăng ký/cấu hình tasks sai, thêm dependency không chủ ý hoặc không tương thích Gradle version khác. Unit test cho helper logic là hữu ích, nhưng nhiều vấn đề chỉ phát hiện khi Gradle thực thi một build thật.

Gradle TestKit có thể chạy một fixture project tạm:

- Áp dụng plugin bằng ID.
- Gọi một task do plugin tạo.
- Xác nhận task outcome và log mong đợi.
- Kiểm tra plugin không đưa dependency không mong muốn vào `runtimeClasspath`.
- Thử plugin trên Gradle/JDK versions được tổ chức hỗ trợ.

**Không** chạy TestKit bằng cách tự động kết nối đến production repository và ghi đè artifacts. Dùng fixtures/repositories an toàn, pin dependencies và kiểm soát network access.

### 13.2. Đừng nhầm test runtime của plugin với test runtime của ứng dụng

`build-logic:testRuntimeClasspath` có thể chứa Gradle TestKit, JUnit hoặc Guava. `app:testRuntimeClasspath` có thể chứa Commons Lang và JUnit. Chúng là **hai graphs riêng**, dù sử dụng một số artifacts cùng version.

Một lỗi test plugin không nên được “sửa” bằng cách thêm implementation dependency vào app. Đọc đúng task và project path mà error stacktrace chỉ ra.

## 14. Annotation processors, code generation và tool dependencies

Build logic không chỉ gồm Gradle plugins. Một số công cụ chạy trong quá trình build:

- Annotation processors được `javac` chạy khi compile source.
- Code generators tạo Java/Kotlin sources hoặc resources.
- Checkstyle/PMD/SpotBugs tools chạy trong verification tasks.
- Javadoc/doclet, formatting tools hoặc API compatibility scanners.
- Kotlin compiler plugins hoặc bytecode transformers.

Tùy plugin, các công cụ này dùng **configurations riêng**, không nhất thiết là `app:implementation` hay `build-logic:implementation`.

### 14.1. Ví dụ annotation processor

Trong Java application project:

```kotlin
dependencies {
    annotationProcessor("org.example:codegen-processor:1.2.3")
}
```

Đây là **tọa độ minh họa**, không khẳng định có artifact thật. Về ý định, processor phục vụ compile task và có classpath riêng; nó **không tự trở thành runtime dependency của app**.

Nếu generated source dùng một thư viện runtime cụ thể, app vẫn cần khai báo dependency phù hợp. Công cụ sinh source và thư viện mà generated code gọi là **hai nhu cầu khác nhau**.

### 14.2. Tool dependency của scanner

Checkstyle plugin có configuration riêng phục vụ Checkstyle tool và những extensions; code quality tool JAR không có lý do nằm trong `app:runtimeClasspath`. Nếu chỉ vì áp dụng Checkstyle mà JAR app chứa Checkstyle dependencies, cần xem lại cách đóng gói hoặc dependencies được thêm vào app sai.

Tương tự một scanner vulnerability dùng thư viện HTTP client trong plugin không có nghĩa app phải dùng client đó. Đừng đưa mọi dependency hỗ trợ build vào `implementation` của Java app.

## 15. Rủi ro khi trộn dependency scopes

### 15.1. Classpath pollution

Nếu copy toàn bộ libraries của build logic sang app `implementation`, app compile classpath phình to, thời gian resolution/analysis tăng, và có thể vô tình dựa trên library không thuộc API/sản phẩm.

Ví dụ app không cần Guava nhưng thêm vì convention plugin dùng nó:

```kotlin
dependencies {
    implementation("com.google.guava:guava:33.3.0-jre")
}
```

Lệnh này thực sự đổi app's dependency graph. Nếu package/distribution sao chép runtime dependencies, Guava và transitives có thể được đưa vào sản phẩm. Tránh khai báo “cho chắc” khi mã app không cần.

### 15.2. Conflict versions giữa công cụ build và ứng dụng

Một plugin có thể cần Guava version A trong Gradle JVM, ứng dụng cần Guava version B trong runtime. Nếu hai graph tách biệt, chúng có thể được quản lý riêng, nhưng plugin classloader vẫn có thể có xung đột với **plugin khác**.

Cố ép cả plugin và app về cùng một version mà không biết compatibility có thể gây lỗi ở cả hai. Cần kiểm tra:

- Build logic tool/version compatibility.
- App API/ABI/runtime compatibility.
- Gradle plugin API/JVM requirements.
- Runtime graph của application.
- Những transitive dependency constraints/versions được resolve.

### 15.3. Tăng attack surface của artifact

Nếu một package tool không cần thiết bị đưa vào app runtime, artifact trở nên lớn hơn, có thêm libraries phải cập nhật lỗ hổng và có thể tăng surface để phát hiện CVE. Ngược lại, dependency build logic cũng là thành phần đáng tin cậy vì plugin code chạy với quyền của build process/CI.

**Tách classpath không có nghĩa bỏ qua bảo mật build dependencies.** Cả hai phải được kiểm soát, nhưng bằng chính sách phù hợp với quyền và môi trường chạy của từng nhóm.

### 15.4. Không suy ra từ `~/.gradle/caches`

Có thể nhìn thấy `guava-33.3.0-jre.jar` trong Gradle dependency cache sau khi build. Điều đó không nói nó thuộc app JAR. Artifact cache lưu files cho nhiều project/configurations.

Hãy kiểm tra **graph của project và cấu hình phù hợp**. `./gradlew :app:dependencies --configuration runtimeClasspath` là câu trả lời đáng tin hơn việc tìm tên file Guava trên đĩa.

## 16. Dependency locking và verification theo từng build

Included build `build-logic` có thể là một build riêng với cấu hình dependencies và version policy riêng. Main build cũng có thể dùng dependency locking/verification riêng cho app.

### 16.1. Cấu hình version rõ, hạn chế dynamic versions

Với plugin/tool dependencies:

```kotlin
dependencies {
    implementation("com.google.guava:guava:33.3.0-jre")
}
```

Version cụ thể giúp review thay đổi và tái lập lỗi dễ hơn. Tránh tùy tiện:

```kotlin
// KHÔNG KHUYẾN NGHỊ cho build logic cần tái lập:
dependencies {
    implementation("com.google.guava:guava:+")
}
```

Dynamic version có thể làm CI hôm nay chọn plugin dependency khác hôm qua và ảnh hưởng build behavior, ngay cả khi app dependencies không thay đổi.

### 16.2. Version catalog chung không thay lock state riêng

Dùng một `libs.versions.toml` cho cả app và build-logic có thể giúp **nhất quán version requests**, nhưng không tự đồng nhất dependency graphs, build cache hoặc lockfiles. Gradle dependency locking cần được áp dụng/duy trì trong phạm vi build/configurations liên quan.

Nếu project build-logic và app resolve transitive dependencies với constraints khác nhau, kết quả vẫn có thể khác nhau. Điều đó không nhất thiết sai vì hai dự án có mục tiêu sử dụng khác nhau.

### 16.3. Dependency verification và supply chain

Plugin dependencies được thực thi trong build process, có thể đọc source/credentials hoặc ghi output; vì thế cần đặc biệt chú trọng:

1. Chỉ dùng plugins từ nguồn tin cậy, version rõ ràng.
2. Kiểm tra checksums/signatures/dependency verification khi chính sách yêu cầu.
3. Giới hạn repository và lọc groups/credentials đúng.
4. Tránh plugin repository “bất kỳ URL nào” không kiểm soát.
5. Hạn chế quyền token CI, không in secrets trong plugin logs.
6. Cập nhật dependencies của build logic khi có CVE/bug phù hợp.
7. Không đánh đồng việc plugin chạy thành công với việc app code đã được kiểm tra.

Build logic ở included build có thể cần cấu hình dependency verification riêng; không mặc định mọi policy của main build tự được tái áp dụng ở build độc lập.

## 17. Configuration cache và tác động khi thay build logic

Một ưu điểm của convention plugin là logic có nguồn và cấu trúc rõ hơn so với việc lặp các đoạn cấu hình ở root `subprojects`.

Tuy nhiên, khi sửa `build-logic`:

- Plugin classes hoặc behavior có thể thay đổi.
- Gradle có thể cần biên dịch lại build-logic.
- Các project dùng plugin cần được cấu hình/đánh giá lại khi đầu vào liên quan thay đổi.
- Configuration cache và build cache chỉ có ích nếu các task/plugin tương thích và khai báo state/inputs đúng.
- Classpath changes có thể làm vô hiệu hóa cache của những phần phụ thuộc plugin tương ứng.

Không suy ra “chuyển vào `build-logic` chắc chắn làm mọi build nhanh hơn” mà không đo. Giá trị chính là **phạm vi rõ ràng, tái sử dụng, bảo trì, khả năng test và isolation**.

### 17.1. Tránh giữ Project reference trong task action

Trong plugin/task production, không nên viết anonymous task action giữ tham chiếu tới `Project` rồi đọc tùy tiện Gradle model tại execution phase. Điều này có thể làm configuration cache không tương thích.

Bài lab dùng một **typed task class** `ConventionInfoTask` với `@TaskAction`; không cần capture `Project` trong closure. Với task xử lý file thật, hãy truyền dữ liệu qua Gradle `Property`/`Provider` và khai báo inputs/outputs.

### 17.2. In log không thay thế test

`conventionInfo` cho thấy Guava được load và gọi thành công trong plugin, nhưng một diagnostic log **không phải unit test toàn diện**. Với plugin bắt buộc cho CI/production, cần plugin validation và integration tests đủ tốt.

## 18. Một số câu hỏi về dependency của external Gradle plugins

### 18.1. Nếu convention plugin muốn áp dụng external plugin?

Có thể cần đưa **implementation artifact của external plugin** vào `build-logic.dependencies` và áp dụng plugin ID trong convention plugin. Đây là dependency cho **build logic**, không phải app `implementation`.

Một plugin public có thể có:

- Plugin ID khác artifact coordinates.
- Plugin marker trỏ tới implementation module riêng.
- Transitive dependencies yêu cầu JDK/Gradle versions nhất định.
- Repository riêng cho plugin marker hoặc implementation.

Do đó cần đọc tài liệu của đúng plugin/version, thay vì suy luận:

```text
plugin id = artifactId = Gradle module name
```

luôn đúng. Điều đó **không được bảo đảm**.

### 18.2. Khi nào đặt plugin version ở root?

Plugin version có thể được quản lý qua `pluginManagement.plugins`, version catalogs hoặc convention plugin dependency model, tùy cách plugin được áp dụng. Nếu một external plugin được áp dụng trong precompiled convention plugin, việc quản lý version thường nằm ở build-logic dependencies thay vì thêm `version` vào precompiled script plugin request.

Điều quan trọng là biết **ai thực sự resolve plugin**: main build's `plugins` DSL, legacy `buildscript` hay build-logic project. Mỗi trường hợp dùng repository và dependency configuration khác nhau.

### 18.3. Nếu plugin yêu cầu Java cao hơn application?

Plugin code chạy trên Gradle JVM. App code chạy trên app runtime. Về nguyên tắc plugin Java 17 có thể giúp build một library target Java 11 nếu Gradle runtime/JDK/compiler hỗ trợ thiết kế đó. Không cần phát hành plugin dependencies kèm library để đáp ứng yêu cầu đó.

## 19. Chẩn đoán lỗi và quy trình sửa đúng lớp

| Lỗi/triệu chứng | Nguyên nhân hay gặp | Nơi cần sửa |
| --- | --- | --- |
| `Package com.google.common.base does not exist` trong `ConventionInfoTask` | Build-logic thiếu Guava compile dependency | `build-logic/dependencies`, build-logic repositories |
| `NoClassDefFoundError: com/google/common/base/CaseFormat` khi chạy plugin task | Plugin runtime classpath không có Guava hoặc xung đột classloader | Build-logic runtime dependency/plugin packaging |
| `Package org.apache.commons.lang3 does not exist` trong `app/Main.java` | App thiếu Commons Lang compile dependency | `app/dependencies`, app repositories |
| App không import được Guava dù plugin đang dùng được | Hai scopes tách biệt đúng như thiết kế | Chỉ thêm Guava vào app nếu app thực sự cần |
| `Plugin [id: 'dev.learning.java-conventions'] was not found` | `pluginManagement.includeBuild` sai path hoặc plugin ID/registration sai | Root settings và `gradlePlugin` |
| `Plugin [id: 'external.plugin'] was not found` | Thiếu plugin repo/marker/version | `pluginManagement.repositories` hoặc plugin resolution |
| App không resolve `commons-lang3` nhưng plugin tải được Guava | App thiếu project dependency repository hoặc network | App repositories/settings dependencyResolutionManagement |
| Build logic không resolve Guava dù app tải Commons Lang | Build-logic thiếu own repository | `build-logic.repositories` |
| `Task 'conventionInfo' not found` | Plugin không được apply hoặc task đăng ký ở project khác | `app/plugins`, JavaConventionsPlugin, task path |
| `UnsupportedClassVersionError` khi load plugin | Gradle runtime JVM quá cũ cho plugin bytecode | Gradle JVM / build-logic compilation target |
| `UnsupportedClassVersionError` khi chạy app | Application runtime quá cũ cho app bytecode | App toolchain/release target hoặc runtime |
| Plugin Gradle chạy lỗi `NoSuchMethodError` | Plugin API/classpath version conflict | Gradle/plugin versions, build-logic transitive dependencies |
| App runtime thiếu Commons Lang | Đóng gói classpath không chứa implementation dependency | App runtimeClasspath/distribution |
| App có thêm Guava không mong muốn | Plugin chủ động thêm dependency hoặc app dependency transitively kéo vào | `:app:dependencies --configuration runtimeClasspath` |
| `buildSrc` code thấy Guava nhưng app code không thấy | BuildSrc classpath là build logic, không phải app | Thiết kế đúng; xem app implementation |
| `libs` accessor không có trong included build | Version catalog chưa được import vào build độc lập | `build-logic/settings.gradle.kts` |
| Test Gradle plugin thiếu JUnit | App test dependency không tự phục vụ build-logic tests | `build-logic/testImplementation` |
| Build chậm sau sửa plugin | Rebuild/configuration cache invalidation hoặc plugin tasks | Phân tích task graph, Gradle performance tools |
| `repository ... not found` khi plugin request | Plugin repositories và project repositories bị nhầm | Settings pluginManagement vs project repositories |
| Scan báo CVE ở Guava của plugin | Build logic có dependency riêng và quyền CI nhạy cảm | Upgrade/test build-logic Guava, review plugin |
| Scan báo CVE ở Commons Lang của app | Ứng dụng dùng library trong sản phẩm | Upgrade/test app dependency graph |
| CI local pass nhưng remote fail | Toolchain, network, plugin repo/credentials khác | Kiểm tra môi trường từng build và pin versions |
| `dependencies` hiển thị trống ở project root | Hỏi nhầm project/configuration | Chạy `:app:dependencies` hoặc `-p build-logic` |

### 19.1. Debug theo lớp

**Bước 1 — xác định stacktrace xảy ra ở đâu.** `ConventionInfoTask.java`, `JavaConventionsPlugin.java`, `app/Main.java` hay một plugin bên ngoài? Vị trí lỗi giúp chọn build cần sửa.

**Bước 2 — kiểm tra Gradle/plugin/JDK:**

```bash
./gradlew --version
./gradlew javaToolchains
./gradlew :app:tasks --all
```

**Bước 3 — xem đúng dependency graph:**

```bash
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew -p build-logic dependencies --configuration runtimeClasspath
```

**Bước 4 — xem nguyên nhân version selection:**

```bash
./gradlew :app:dependencyInsight --dependency commons-lang3 --configuration runtimeClasspath
./gradlew -p build-logic dependencyInsight --dependency guava --configuration runtimeClasspath
```

**Bước 5 — phân biệt plugin resolution với project dependency resolution.** Nếu plugin ID không tìm được, xem settings `pluginManagement`/registration. Nếu app Java import không được, xem `app:compileClasspath`.

**Bước 6 — chạy lại một task nhỏ đúng scope:**

```bash
./gradlew :app:conventionInfo --stacktrace --console=plain
./gradlew :app:compileJava --stacktrace --console=plain
./gradlew :app:run --console=plain
```

Không xóa cả Gradle caches như bước đầu tiên. Nếu thông tin resolution đúng nhưng task sử dụng output cũ, mới xem up-to-date inputs, Gradle logs và trạng thái caches phù hợp.

## 20. Groovy DSL tương đương cho phần cấu hình

Nếu dự án sử dụng Groovy DSL, tư duy ranh giới vẫn giữ nguyên. Đây là **phương án thay thế** cho một số file Kotlin DSL, không phải script cần chạy đồng thời.

**Root `settings.gradle`:**

```groovy
pluginManagement {
    includeBuild('build-logic')
}

rootProject.name = 'dependency-boundaries-lab'
include 'app'
```

**`build-logic/build.gradle`:**

```groovy
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

dependencies {
    implementation 'com.google.guava:guava:33.3.0-jre'
}

gradlePlugin {
    plugins {
        javaConventions {
            id = 'dev.learning.java-conventions'
            implementationClass = 'dev.learning.JavaConventionsPlugin'
        }
    }
}
```

**`app/build.gradle`:**

```groovy
plugins {
    id 'application'
    id 'dev.learning.java-conventions'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

application {
    mainClass = 'demo.Main'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Java source/plugin classes ở mục 5 không cần thay khi chuyển DSL. Mỗi build dùng **một** DSL file thích hợp; đừng để cả `build.gradle` và `build.gradle.kts` cùng thư mục với nội dung song song rồi mong Gradle gộp chúng.

## 21. Khi nào build logic dependency được đưa vào sản phẩm một cách hợp lệ?

Có những trường hợp công cụ build tạo code hoặc đóng gói các thư viện phụ thuộc, nhưng việc đưa một JAR vào sản phẩm phải là **quyết định có thể giải thích**, không phải hệ quả ngoài ý muốn.

Ví dụ hợp lệ:

- Plugin thống nhất `testImplementation(JUnit)` cho mọi app có test suite theo policy.
- Plugin áp dụng một BOM/platform vào các Java projects được chọn.
- Plugin thêm một runtime library vì generated code của framework yêu cầu nó.
- Plugin tạo một plugin-specific configuration cho tool execution.
- Build pipeline đóng gói agent/launcher cần thiết vào distribution nếu được thiết kế như vậy.

Ví dụ không hợp lý:

- App không dùng Guava nhưng copy Guava vào `app:implementation` chỉ vì plugin dùng Guava.
- Đưa `gradleApi()` hoặc các thư viện Gradle runtime vào application JAR.
- Đặt Maven repository credentials vào `src/main/resources` để plugin có thể truy cập.
- Dùng `fileTree("~/.gradle/caches")` làm app runtime classpath.
- Cố import classes của build-logic trong `app/src/main/java` thay vì tạo một shared library được công bố đúng.

Nếu ứng dụng thật sự cần dùng **một loại Java code** vốn đang nằm trong build logic, nên xem xét tách nó thành **library domain-neutral** với API/contract rõ ràng, rồi để build logic và app khai báo dependency độc lập vào library đó. Đừng phụ thuộc thẳng vào Gradle plugin implementation artifact như một thư viện nghiệp vụ.

## 22. Bài tập thực hành

**Bài tập A — tạo lab.** Tạo file/cây thư mục mục 5, chạy `:app:conventionInfo` và `:app:run --quiet`. Xác nhận dòng Gradle task `Build logic helper: BuildLogic` và stdout app `Hello, Gradle!`.

**Bài tập B — đối chiếu graphs.** Chạy `:app:dependencies --configuration runtimeClasspath` và `-p build-logic dependencies --configuration runtimeClasspath`. Ghi lại Commons Lang và Guava thuộc project/configuration nào.

**Bài tập C — cố tình import Guava ở app.** Trên bản sao, thêm `CaseFormat` trong app `Main.java` mà không khai báo dependency. Dự đoán lỗi compiler. Vì sao build-logic đã có Guava không giúp app?

**Bài tập D — sửa đúng lớp.** Nếu app thực sự cần `CaseFormat`, thêm Guava vào `app.dependencies.implementation` và chạy lại compile. Sau đó xóa dependency nếu app không cần để phục hồi nguyên tắc dependency tối thiểu.

**Bài tập E — thiếu Guava trong build-logic.** Tạm bỏ `implementation(Guava)` tại `build-logic` và chạy `:app:conventionInfo`. Lỗi xảy ra ở plugin compilation hay app compilation? Khôi phục dependency đúng build.

**Bài tập F — plugin chủ động thêm app dependency.** Trong bản sao plugin, dùng `project.getDependencies().add("implementation", Guava coordinate)` sau khi áp dụng Java plugin. Quan sát `app:runtimeClasspath` có Guava. Giải thích sự khác biệt giữa thao tác này và dependency trong `build-logic`.

**Bài tập G — repositories.** Tạm bỏ `mavenCentral()` ở `build-logic` trong một môi trường cache sạch. Vì sao app repositories không tự cung cấp Guava cho included build? Khôi phục cấu hình.

**Bài tập H — plugin resolution.** Bỏ `pluginManagement.includeBuild("build-logic")` rồi thử áp dụng custom plugin local. Lỗi báo về plugin ID ở đâu? Vì sao thêm `mavenCentral()` vào app.repositories không phải cách sửa đúng?

**Bài tập I — test classpaths.** Thêm unit test Gradle plugin trong `build-logic` và cài JUnit/TestKit dependencies riêng. Tại sao `app:testImplementation` không giúp plugin tests compile?

**Bài tập J — version catalog.** Tạo catalog chung và import vào `build-logic/settings.gradle.kts`, dùng alias cho Guava. Vì sao catalog alias giống nhau không trộn hai configurations?

**Bài tập K — security review.** Giả sử Guava của plugin bị CVE nhưng app không dùng Guava. Hãy phân loại ảnh hưởng tới Gradle CI build environment và app runtime, đồng thời đề xuất cách nâng cấp/kiểm thử đúng build.

**Bài tập L — kiểm thử plugin độc lập.** Dùng Gradle TestKit để áp dụng convention plugin vào fixture project, kiểm tra task `conventionInfo` và xác minh plugin không tự thêm Guava vào app runtime.

**Bài tập M — chuyển DSL.** Viết lại root/settings, `build-logic` và app với Groovy DSL theo mục 20 nhưng giữ Java sources. Chạy lại các lệnh kiểm tra output.

**Bài tập N — compiler version.** Thay app toolchain thành một baseline khác trong một bản sao và giải thích vì sao plugin code có compatibility với JVM chạy Gradle độc lập với Java target của app.

**Bài tập O — anti-pattern.** Một team đưa `gradleApi()` và JUnit của build tools vào `app:implementation`. Hãy lập checklist xác định dependencies nào cần dời sang build-logic/test/tool configurations.

### Câu hỏi tự kiểm tra

1. Build logic và application code chạy ở hai giai đoạn/context nào?
2. Vì sao `build-logic.dependencies.implementation(Guava)` không tự vào app runtimeClasspath?
3. `buildSrc` được Gradle dùng cho mục đích gì?
4. `build-logic` khác một subproject `:build-logic` như thế nào?
5. `pluginManagement.includeBuild` giúp plugin resolution tại thời điểm nào?
6. `pluginManagement.repositories` khác `app.repositories` như thế nào?
7. `buildscript.classpath` khác `app.implementation` ra sao?
8. Vì sao external plugin ID có thể khác Maven implementation coordinates?
9. Plugin có thể chủ động thêm dependency vào application bằng API nào?
10. Khi plugin thêm vào `implementation`, configuration đó phải tồn tại từ plugin nào?
11. Vì sao plugin dùng Guava nhưng app dùng Commons Lang vẫn chạy được?
12. Lệnh nào xem runtime graph của app?
13. Lệnh nào xem runtime graph của project build-logic?
14. `dependencyInsight` hỗ trợ debug version selection trong scope nào?
15. `gradlePluginPortal()` có tự cho app tải Maven library không?
16. `testImplementation` của app có sẵn cho plugin tests không?
17. Gradle TestKit thường thuộc dependency scope của build nào?
18. Version catalog ở root có tự xuất hiện trong included build không?
19. Shared version catalog có đồng nghĩa shared dependency graph không?
20. Annotation processor có tự trở thành app runtime library không?
21. Vì sao cần kiểm tra JVM chạy Gradle khi plugin bị `UnsupportedClassVersionError`?
22. Vì sao app toolchain version không tự quyết định plugin classpath?
23. Nếu Guava bị báo CVE trong plugin, có thể bỏ qua vì app không dùng không?
24. Một convention plugin nên được test những hành vi cấu hình nào?
25. Thay `--refresh-dependencies` có sửa được project plugin ID không tồn tại không?
26. Khi nào nên chuyển logic lặp từ root `subprojects` sang convention plugin?
27. Làm sao chứng minh một thư viện không có trong main app runtime graph?
28. Nếu một code helper cần dùng cả ở app và plugin, nên tổ chức thư viện đó thế nào?

**Tài liệu chính thức:**
- [Gradle — Sharing Build Logic using buildSrc](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html)
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html)
- [Gradle — Working with Plugins](https://docs.gradle.org/current/userguide/plugins_intermediate.html)
- [Gradle — Gradle Plugin Development Plugin](https://docs.gradle.org/current/userguide/java_gradle_plugin.html)
- [Gradle — Declaring Repositories Basics](https://docs.gradle.org/current/userguide/declaring_repositories_basics.html)
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html)
- [Gradle — Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)

**Ghi nhớ:** `build-logic`, `buildSrc`, `buildscript.classpath` và plugin resolution phục vụ **Gradle build**, còn `app:implementation`/`runtimeOnly`/`testImplementation` phục vụ **Java project theo từng classpath**. Dependency của plugin **không tự được sao chép vào ứng dụng**; chỉ khi plugin/app khai báo rõ mới xuất hiện trong app graph. Hãy đặt thư viện đúng project/configuration, cấu hình repositories đúng nơi, kiểm tra `dependencies`/`dependencyInsight` trên cả hai builds, và thử ứng dụng lẫn convention plugin độc lập.