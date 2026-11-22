# Precompiled script plugin với Groovy DSL hoặc Kotlin DSL trong Gradle

## 1. Vì sao cần precompiled script plugin?

Trong một dự án Gradle nhiều module, các file `build.gradle.kts` hoặc `build.gradle` thường lặp những quy tắc giống nhau: phiên bản Java, cách chạy JUnit, repositories, kiểm tra code style, convention cho publishing hoặc cách đăng ký task. Nếu sao chép từng block vào mọi module, một thay đổi chính sách (ví dụ chuyển lên Java 17) phải cập nhật ở nhiều nơi, dễ bị lệch cấu hình.

**Precompiled script plugin** (plugin script biên dịch sẵn) cho phép chuyển các block Gradle DSL đó vào **một file script riêng được Gradle biên dịch thành plugin thực sự**. Sau đó mỗi module tự áp plugin qua `plugins { id("...") }`.

Cơ chế tổng quát:

~~~text
build-logic (hoặc buildSrc)
    └── src/main/kotlin/company.java-conventions.gradle.kts
        hoặc src/main/groovy/java-conventions.gradle
                    |
                    v
            Gradle compile script
                    |
                    v
             plugin ID được tạo
                    |
                    v
core/build.gradle.kts -> plugins { id("company.java-conventions") }
app/build.gradle.kts  -> plugins { id("company.java-conventions") }
                    |
                    v
     cùng chính sách Java/toolchain/test ở mỗi project
~~~

Đây là **cách chia sẻ build logic**, không phải dependency cho classpath của Java application. Mã Java thuộc `src/main/java` vẫn khác mã Gradle plugin thuộc `build-logic/src/main/kotlin` hoặc `src/main/groovy`.

Sau bài học, bạn có thể:

- Phân biệt **script plugin được apply từ file**, **precompiled script plugin** và **binary plugin**.
- Dựng included build `build-logic` hoặc `buildSrc` để cung cấp convention plugins.
- Viết precompiled script plugin bằng **Kotlin DSL (`.gradle.kts`)** hoặc **Groovy DSL (`.gradle`)**, đặt đúng plugin ID và apply vào subproject.
- Hiểu `kotlin-dsl` so với `groovy-gradle-plugin`, source directories và package rules.
- Biết khi nào dùng `pluginManagement { includeBuild("build-logic") }`.
- Khai báo external plugin **trong classpath của build-logic**, tránh lỗi `version`/`apply false` không được hỗ trợ trong chính precompiled script plugin.
- Sử dụng `plugins` block để Gradle sinh type-safe accessors kịp thời.
- Tạo ví dụ **Java 17 nhiều module** dùng một convention plugin chung, có `javac`/`java` và stdout kiểm chứng.
- Tránh cấu hình chéo `subprojects { }`, tách version catalog giữa các builds, chẩn đoán lỗi unresolved plugin/extension.
- Xây dựng quy tắc để plugin dễ test, an toàn với lazy configuration, Configuration Cache và CI.

Các ví dụ chính dùng Gradle Wrapper và Kotlin DSL. Phần Groovy được trình bày như **phương án thay thế độc lập**, không dán lẫn hai cách tạo cùng plugin ID vào một build.

## 2. Ba phương pháp viết build logic

| Cách | Định dạng | Dùng lúc nào? | Nhược điểm |
| --- | --- | --- | --- |
| **Script plugin truyền thống** | `common.gradle`/`common.gradle.kts`, apply từ file. | Một đoạn thử nghiệm nhỏ hoặc build cũ. | Dễ phân tán logic, khó được type-safe accessors đầy đủ, ít phù hợp tổ chức lớn. |
| **Precompiled script plugin** | `src/main/kotlin/*.gradle.kts` hoặc `src/main/groovy/*.gradle`. | Chia sẻ quy tắc build giữa modules, convention plugins. | Cần một plugin-producing build, compile plugin code và hiểu classpath riêng. |
| **Binary plugin** | Class Java/Kotlin/Groovy implement `Plugin<Project>`, compile thành plugin JAR. | Logic phức tạp, nhiều API, phát hành nhiều builds/tổ chức. | Phải viết implementation class và cấu hình phát hành, test như phần mềm thực. |

### Script plugin truyền thống

~~~kotlin
// app/build.gradle.kts
apply(from = "../gradle/java-settings.gradle.kts")
~~~

Lệnh `apply(from = ...)` đánh giá một script file vào build hiện tại; nó **không** tạo một plugin có ID ổn định như `company.java-conventions`. Khi build logic lớn, script apply rải rác khó tìm nguồn cấu hình và khó hỗ trợ type-safe API.

### Precompiled script plugin

~~~kotlin
// app/build.gradle.kts
plugins {
    id("company.java-conventions")
}
~~~

Plugin đã được build-logic hoặc buildSrc biên dịch, đăng ký bằng ID. Gradle có thể resolve/apply nó sớm thông qua Plugin DSL; logic có tên rõ và các modules tự cho thấy convention đang áp.

### Binary plugin

~~~kotlin
// Minh họa hình thức class plugin, chưa phải file Java/Kotlin đầy đủ.
class ExamplePlugin : Plugin<Project> {
    override fun apply(target: Project) {
        target.plugins.apply("java")
    }
}
~~~

Mảnh Kotlin trên dùng APIs Gradle, cần đặt vào plugin project đúng và khai báo ID để Gradle apply. Với quy tắc tương đối ngắn như Java toolchain/test dependencies, **precompiled script plugin thường dễ đọc hơn**.

## 3. Hai lựa chọn lưu plugin: `buildSrc` và included `build-logic`

### `buildSrc`

Gradle nhận diện thư mục đặc biệt `buildSrc` trong root project; biên dịch build logic bên trong trước khi cấu hình các project build scripts. Classes/plugins của `buildSrc` có trên classpath build scripts của root build.

~~~text
workspace/
├── settings.gradle.kts
├── build.gradle.kts
├── app/build.gradle.kts
└── buildSrc/
    ├── build.gradle.kts
    └── src/main/kotlin/java-conventions.gradle.kts
~~~

**Ưu điểm:** setup nhanh, không cần `includeBuild("buildSrc")` trong Settings. **Nhược điểm:** thay đổi `buildSrc` có thể invalidate phần cấu hình của nhiều project; khó tách phạm vi/chu kỳ phát triển khi repository lớn. `buildSrc` là một build riêng, không đơn giản là một thư mục Java source thông thường của app.

### Included `build-logic`

~~~text
workspace/
├── settings.gradle.kts
├── app/build.gradle.kts
└── build-logic/
    ├── settings.gradle.kts
    ├── build.gradle.kts
    └── src/main/kotlin/company.java-conventions.gradle.kts
~~~

Trong root Settings:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "workspace"
include("app")
~~~

Đây là một **composite build dùng để cung cấp plugin**. `build-logic` có Settings, repositories, dependencies và source riêng. Plugin ID do source file của build-logic sinh ra, được consumer áp bằng Plugin DSL.

Ưu điểm: build logic có ranh giới rõ, dễ phát triển/test độc lập và tổ chức nhiều convention plugins. Không nhầm `includeBuild("build-logic")` với `include("build-logic")`: cái trước thêm **một build khác**, cái sau tạo **subproject** thông thường.

### Chọn phương án nào?

- Một build nhỏ, rất ít conventions: `buildSrc` có thể đủ.
- Multi-project lớn hoặc cần plugin logic tách biệt: included `build-logic` thường hợp lý hơn.
- Plugin cần được publish cho những repositories không có chung source tree: một **plugin project/published binary plugin** có thể phù hợp.
- Nếu root chỉ cần vài convention đơn giản, tránh tạo hệ thống plugin phức tạp không cần thiết.

**Bài thực hành chính chọn included `build-logic`**, để thấy rõ mọi file được đặt ở đâu. `buildSrc` sẽ là phương án thay thế ở mục 8.

## 4. Kotlin DSL: plugin-producing build dùng `kotlin-dsl`

Plugin tạo bằng **Kotlin DSL** thường được đặt ở `src/main/kotlin` trong build-logic:

~~~text
build-logic/
├── settings.gradle.kts
├── build.gradle.kts
└── src/main/kotlin/
    └── com/acme/java-conventions.gradle.kts
~~~

`build-logic/build.gradle.kts`:

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

**Lưu ý cú pháp:** ``kotlin-dsl`` ở đây được biểu diễn là Kotlin identifier có backticks khi dùng thực tế:

~~~kotlin
plugins {
    id("org.gradle.kotlin.kotlin-dsl")
}
~~~

Cách dùng thông thường trong Gradle vẫn là `plugins { `kotlin-dsl` }`; các ví dụ còn lại ghi đúng dạng đó. Không thêm version tùy ý cho plugin phát triển Kotlin DSL nếu chưa kiểm tra compatibility với Gradle runtime đang dùng.

`kotlin-dsl` giúp:
- Cấu hình môi trường biên dịch Kotlin DSL scripts.
- Biên dịch những file `.gradle.kts` trong plugin source set.
- Sinh plugin adapters/registrations để plugin có thể apply bằng ID.
- Cung cấp Gradle APIs và type-safe Kotlin DSL tooling phù hợp.
- Hỗ trợ IDE completion và compile-time checking của logic dùng chung.

**Khác biệt classpath:** `repositories` ở `build-logic/build.gradle.kts` dùng để resolve **dependencies của build-logic**, không phải tự động cấu hình `mavenCentral()` cho các Java subprojects. Nếu convention muốn Java modules dùng Maven Central, hãy đặt `repositories { mavenCentral() }` **trong chính precompiled plugin**, như ở lab mục 5.

## 5. Lab Kotlin DSL đầy đủ: Java 17, hai modules và một convention plugin

Mục tiêu:
- Root build có `:core` và `:app`.
- Included `build-logic` cung cấp plugin ID `com.acme.java-conventions`.
- Convention plugin áp Java plugin, đặt toolchain 17, repositories/JUnit dependencies, và cấu hình Test tasks.
- `:core` chứa class Java dùng lại; `:app` là ứng dụng chạy main class.
- Hai modules **không** copy-paste block Java toolchain/JUnit dài dòng, mà chỉ gọi `id("com.acme.java-conventions")`.
- `:app:run` cho stdout chính xác để chứng minh Java source/classpath, còn `:core:test` và `:app:test` xác minh JUnit setup.

### 5.1. Cây thư mục hoàn chỉnh

~~~text
precompiled-conventions-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── gradlew
├── gradlew.bat
├── gradle/wrapper/...
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/kotlin/com/acme/
│       └── java-conventions.gradle.kts
├── core/
│   ├── build.gradle.kts
│   ├── src/main/java/demo/core/Greeting.java
│   └── src/test/java/demo/core/GreetingTest.java
└── app/
    ├── build.gradle.kts
    ├── src/main/java/demo/app/Main.java
    └── src/test/java/demo/app/MainTest.java
~~~

Giả định Gradle Wrapper đã được tạo và trỏ đến bản Gradle tương thích với JDK 17 và Kotlin DSL plugin. Lần đầu chạy tests có thể cần mạng để tải JUnit từ Maven Central. Nếu máy chưa có JDK 17, phải cài JDK hoặc cấu hình Java toolchain resolver; khai báo `JavaLanguageVersion.of(17)` không tự đảm bảo Gradle có nơi tải JDK.

### 5.2. Root `settings.gradle.kts`

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "precompiled-conventions-lab"
include("core", "app")
~~~

**Ý nghĩa:**

1. `pluginManagement.includeBuild("build-logic")` đưa plugin-producing build vào **plugin resolution**, được xử lý sớm.
2. `gradlePluginPortal()` là repository để resolve những plugin khác nếu cần, **không** thay thế Maven Central của Java dependencies.
3. `include("core", "app")` tạo subprojects `:core` và `:app`.
4. `build-logic` **không** phải subproject `:build-logic` theo cơ chế `include`; nó có build identity riêng.
5. Không khai báo `include("build-logic")` song song chỉ để làm plugin sẵn dùng.

### 5.3. Root `build.gradle.kts`

~~~kotlin
plugins {
    base
}
~~~

Root có Base lifecycle tasks như `build`/`check`, nhưng **không tự apply convention lên mọi module**. Mỗi module khai báo plugin trong `plugins` block của chính mình. Điều này tránh cấu hình chéo `subprojects { plugins.apply(...) }` khó quan sát.

### 5.4. `build-logic/settings.gradle.kts`

~~~kotlin
rootProject.name = "build-logic"
~~~

Đây là Settings độc lập của included build. Nếu cần quản lý plugin resolution riêng hoặc version catalogs riêng cho build-logic, cấu hình **trong Settings này**, không mặc định dùng lại Settings của root.

### 5.5. `build-logic/build.gradle.kts`

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

Trong lab này precompiled script chỉ dùng core Gradle Java plugin; do đó **không cần thêm external plugin implementation dependency** vào `build-logic.dependencies`. Mục 11 sẽ trình bày trường hợp external plugin.

### 5.6. `build-logic/src/main/kotlin/com/acme/java-conventions.gradle.kts`

~~~kotlin
package com.acme

plugins {
    java
}

// Áp dụng lên mỗi Project khi Project đó yêu cầu plugin này.
repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

dependencies {
    testImplementation(platform("org.junit:junit-bom:5.11.4"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Đây là **file precompiled script plugin đầy đủ**:

- `package com.acme` là package declaration của Kotlin DSL script.
- Filename `java-conventions.gradle.kts` đóng góp phần cuối `java-conventions` cho plugin ID.
- Package + filename cho plugin ID **`com.acme.java-conventions`**.
- `plugins { java }` áp core Java plugin lên mỗi consumer project; vì áp sớm, script có `java { ... }` type-safe accessor.
- `repositories { mavenCentral() }` cấu hình repositories của **consumer Project**, không phải build-logic plugin dependency repository.
- `testImplementation(...)` và `testRuntimeOnly(...)` thêm JUnit vào test configurations của consumer project.
- `tasks.withType<Test>().configureEach` cấu hình các Test tasks lazy, kể cả những task được đăng ký sau, thay vì eagerly tìm tên.
- `useJUnitPlatform()` cho JUnit Jupiter tests được Gradle Test task chạy đúng.
- `JavaLanguageVersion.of(17)` chọn Java 17 toolchain cho Java plugin tasks theo Gradle conventions.

**Nguồn gốc plugin ID:** không tự suy ID từ Java package `demo.core` hay root project name; ID dựa vào package của **script file plugin** và tên file đã loại `.gradle.kts`.

### 5.7. `core/build.gradle.kts`

~~~kotlin
plugins {
    id("com.acme.java-conventions")
    `java-library`
}
~~~

`java-library` thêm những conventions và dependency configurations như `api`/`implementation` cho module thư viện. Nó áp Java plugin, giống plugin convention cũng áp Java; việc apply cùng core Java plugin nhiều lần được Gradle quản lý idempotent.

Nếu chỉ cần Java class không phải library API, `id("com.acme.java-conventions")` đã đủ để có Java tasks. Trong bài, `java-library` giúp đặt đúng mục đích: `:core` cung cấp library cho app.

Không viết thêm `java { toolchain { ... } }` ở đây nếu project đồng ý dùng mặc định của team. Muốn override theo nhu cầu của một module, xem mục 12.

### 5.8. `core/src/main/java/demo/core/Greeting.java`

~~~java
package demo.core;

public final class Greeting {
    private Greeting() {
    }

    public static String text() {
        return "Hello from core";
    }
}
~~~

### 5.9. `core/src/test/java/demo/core/GreetingTest.java`

~~~java
package demo.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void returnsExpectedText() {
        assertEquals("Hello from core", Greeting.text());
    }
}
~~~

Nhờ convention plugin đã cấu hình JUnit dependencies và `useJUnitPlatform()`, project `core` không cần tự viết lại block test dependencies.

### 5.10. `app/build.gradle.kts`

~~~kotlin
plugins {
    id("com.acme.java-conventions")
    application
}

dependencies {
    implementation(project(":core"))
}

application {
    mainClass.set("demo.app.Main")
}
~~~

`application` là core Application plugin, tạo `run` và application distributions. Vì convention plugin đã apply `java`, `application` vẫn có thể apply những khả năng bổ sung của nó.

`implementation(project(":core"))` là **Java project dependency** từ `:app` sang `:core`. Nó giúp compiler/runtime classpath thấy class `demo.core.Greeting`, không phải chỉ là quan hệ task execution `dependsOn(":core:build")`.

### 5.11. `app/src/main/java/demo/app/Main.java`

~~~java
package demo.app;

import demo.core.Greeting;

public final class Main {
    private Main() {
    }

    public static String line() {
        return "PRECOMPILED_OK=" + Greeting.text();
    }

    public static void main(String[] args) {
        System.out.println(line());
        System.out.println("ARG_COUNT=" + args.length);
    }
}
~~~

### 5.12. `app/src/test/java/demo/app/MainTest.java`

~~~java
package demo.app;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class MainTest {
    @Test
    void usesCoreLibrary() {
        assertEquals("PRECOMPILED_OK=Hello from core", Main.line());
    }
}
~~~

### 5.13. Lệnh chạy và output

Từ root của `precompiled-conventions-lab`:

~~~bash
./gradlew --version
./gradlew projects

# Xác nhận ID được resolve và Java compile tasks đã có.
./gradlew :core:tasks --all
./gradlew :app:tasks --all

# Build Java library và app.
./gradlew :core:build
./gradlew :app:build

# Test hai modules qua selector từ root.
./gradlew test

# Chạy chương trình.
./gradlew -q :app:run --args="alpha beta"

# Thử một lần với plugin build riêng.
./gradlew :build-logic:build
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat projects
.\gradlew.bat :core:build
.\gradlew.bat :app:build
.\gradlew.bat test
.\gradlew.bat -q :app:run --args="alpha beta"
~~~

**Stdout do `Main.main` in chính xác hai dòng:**

~~~text
PRECOMPILED_OK=Hello from core
ARG_COUNT=2
~~~

Task `run` có thể in thêm Gradle/daemon messages, đặc biệt nếu không dùng `-q` hoặc hệ thống có warnings. Hai dòng ở trên là **stdout của Java code**, không phải toàn bộ transcript được bảo đảm của Gradle.

Tests `:core:test` và `:app:test` đều phải pass khi classpath và JDK/JUnit đã setup đúng. Không cần log từng test được in để coi assertions pass; xem `build/reports/tests/test/index.html` của mỗi module hoặc Gradle task outcomes. Nếu muốn xem reports dưới `core/build/reports/tests/test` và `app/build/reports/tests/test`, đường dẫn phụ thuộc project `buildDirectory` còn mặc định.

**Lưu ý:** `./gradlew test` từ root chọn test tasks trong subproject hierarchy, **không tự chạy tests của included `build-logic`** chỉ vì plugin được consume. Để kiểm thử build logic riêng, gọi `:build-logic:build` hoặc task test cụ thể theo build-tree path khi nó tồn tại.

### 5.14. Thử `javac`/`java` độc lập với Gradle

Tại root, Linux/macOS:

~~~bash
mkdir -p build/manual/core build/manual/app

javac -encoding UTF-8 -d build/manual/core \
    core/src/main/java/demo/core/Greeting.java

javac -encoding UTF-8 -cp build/manual/core \
    -d build/manual/app \
    app/src/main/java/demo/app/Main.java

java -cp build/manual/core:build/manual/app \
    demo.app.Main alpha beta
~~~

PowerShell:

~~~powershell
New-Item -ItemType Directory -Force build/manual/core | Out-Null
New-Item -ItemType Directory -Force build/manual/app | Out-Null
javac -encoding UTF-8 -d build/manual/core core/src/main/java/demo/core/Greeting.java
javac -encoding UTF-8 -cp build/manual/core -d build/manual/app app/src/main/java/demo/app/Main.java
java -cp "build/manual/core;build/manual/app" demo.app.Main alpha beta
~~~

Kết quả vẫn:

~~~text
PRECOMPILED_OK=Hello from core
ARG_COUNT=2
~~~

Đây là bài kiểm tra **source Java và Java classpath**, không chứng minh Gradle đã resolve precompiled script plugin hoặc chạy tests. Phải dùng Wrapper và `:app:tasks`/`:core:test`/`:app:run` để kiểm tra build logic thật.

Trên Linux/macOS, Java classpath separator là `:`; trên Windows là `;`. Dấu hai chấm này **không đồng nghĩa** dấu `:` của Gradle task path.

## 6. Groovy DSL: tạo plugin tương đương bằng `groovy-gradle-plugin`

Cùng ý tưởng có thể được viết với **Groovy DSL**. Gradle hỗ trợ precompiled `.gradle` scripts thông qua plugin **`groovy-gradle-plugin`** trong build-logic. Nó khác Gradle core `groovy` plugin vốn phục vụ biên dịch **mã Groovy của ứng dụng**.

Để không gây xung đột plugin names/classpaths, xem đây là **project layout thay thế riêng**, không tạo song song hai plugin trùng ID ở cùng source set.

### 6.1. Cấu trúc Groovy

~~~text
precompiled-groovy-lab/
├── settings.gradle
├── build-logic-groovy/
│   ├── settings.gradle
│   ├── build.gradle
│   └── src/main/groovy/java-common-conventions.gradle
├── core/
│   ├── build.gradle
│   └── src/main/java/demo/core/Greeting.java
└── app/
    ├── build.gradle
    └── src/main/java/demo/app/Main.java
~~~

Có thể tái sử dụng **các Java classes và JUnit test classes của lab mục 5**, đặt ở đúng `src/main/java` và `src/test/java`. Không đổi Java source chỉ vì Gradle build scripts chuyển từ Kotlin DSL sang Groovy DSL.

### 6.2. Root `settings.gradle`

~~~groovy
pluginManagement {
    includeBuild('build-logic-groovy')
    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'precompiled-groovy-lab'
include 'core', 'app'
~~~

### 6.3. `build-logic-groovy/settings.gradle`

~~~groovy
rootProject.name = 'build-logic-groovy'
~~~

### 6.4. `build-logic-groovy/build.gradle`

~~~groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

Plugin `groovy-gradle-plugin` cấu hình source set plugin scripts ở `src/main/groovy`, tạo adapter/plugin metadata và compile Groovy scripts để consumer có thể apply ID từ filename.

### 6.5. `build-logic-groovy/src/main/groovy/java-common-conventions.gradle`

~~~groovy
plugins {
    id 'java'
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
    testImplementation platform('org.junit:junit-bom:5.11.4')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Tên file `java-common-conventions.gradle` tạo plugin ID **`java-common-conventions`**. Trong ví dụ Groovy này không dùng `package`. Theo hướng dẫn precompiled script của Gradle, Groovy DSL precompiled script plugins **không sử dụng package declaration theo cách Kotlin DSL được hỗ trợ**; giữ file trong `src/main/groovy` và ID theo filename là cách minh bạch nhất.

**Đối chiếu với Kotlin DSL:**

| Kotlin DSL | Groovy DSL |
| --- | --- |
| `src/main/kotlin/*.gradle.kts` | `src/main/groovy/*.gradle` |
| `plugins { `kotlin-dsl` }` trong plugin build | `plugins { id 'groovy-gradle-plugin' }` |
| `id("java")` hoặc `java` | `id 'java'` |
| `JavaLanguageVersion.of(17)` + `.set(...)` | Gán `languageVersion = JavaLanguageVersion.of(17)` |
| `tasks.withType<Test>().configureEach { }` | `tasks.withType(Test).configureEach { }` |
| Có thể khai báo Kotlin `package` để tạo prefix ID | Tránh `package` trong Groovy precompiled script, dùng filename ID |
| Static typing, accessors rõ | Dynamic DSL thuận tiện nhưng nhiều lỗi được phát hiện lúc chạy/configuration |

### 6.6. Consumer `core/build.gradle`

~~~groovy
plugins {
    id 'java-common-conventions'
    id 'java-library'
}
~~~

### 6.7. Consumer `app/build.gradle`

~~~groovy
plugins {
    id 'java-common-conventions'
    id 'application'
}

dependencies {
    implementation project(':core')
}

application {
    mainClass = 'demo.app.Main'
}
~~~

Vì Java source vẫn là `Greeting` và `Main` như lab Kotlin, lệnh:

~~~bash
./gradlew -q :app:run --args="alpha beta"
~~~

vẫn in:

~~~text
PRECOMPILED_OK=Hello from core
ARG_COUNT=2
~~~

Ở phương án Groovy, root `build.gradle` có thể rỗng hoặc chỉ áp `base` nếu muốn có root lifecycle tasks; không được nhầm file `build.gradle` của **consumer** với file `build.gradle` của **build-logic-groovy**.

### 6.8. Có thể consumer dùng Kotlin DSL nhưng plugin viết bằng Groovy không?

Có. Gradle Plugin DSL giải quyết plugin theo **ID**, không bắt buộc ngôn ngữ consumer script trùng ngôn ngữ source của plugin. Ví dụ trong app Kotlin:

~~~kotlin
plugins {
    id("java-common-conventions")
    application
}
~~~

vẫn có thể apply plugin được biên dịch từ `.gradle` Groovy, miễn plugin build được include/resolve đúng. Tương tự, consumer Groovy build script có thể apply precompiled plugin được viết bằng Kotlin DSL.

**Đừng nhầm ngôn ngữ của plugin source với Java/Groovy/Kotlin của source ứng dụng.** Một project hoàn toàn viết Java 17 vẫn có thể có build logic Kotlin DSL hoặc Groovy DSL.

## 7. So sánh Kotlin DSL và Groovy DSL khi viết precompiled plugin

| Tiêu chí | Kotlin DSL | Groovy DSL |
| --- | --- | --- |
| Script extension | `.gradle.kts` | `.gradle` |
| Plugin build plugin | `kotlin-dsl` | `groovy-gradle-plugin` |
| Thư mục mặc định | `src/main/kotlin` | `src/main/groovy` |
| Type-safe accessors | Mạnh, sinh từ plugins applied sớm. | Groovy DSL dynamic, có DSL conveniences riêng. |
| Compiler diagnostics | Nhiều sai sót được bắt khi biên dịch Kotlin DSL plugin. | Nhiều truy cập dynamic chỉ lỗi khi runtime/configuration. |
| Plugin ID | Filename + Kotlin package nếu khai báo. | Chủ yếu filename trong ví dụ precompiled Groovy. |
| Cách áp plugin bên ngoài | ID trong precompiled `plugins`, implementation trên build-logic classpath. | Cùng nguyên tắc. |
| Consumer DSL | Có thể là Groovy hoặc Kotlin. | Có thể là Groovy hoặc Kotlin. |
| Khuyến nghị mới | Thường ưu tiên khi muốn code completion/refactoring mạnh. | Có giá trị với codebase đang dùng Groovy, team quen Groovy. |
| Test/CI | Chạy TestKit hoặc build-logic tests như một plugin project. | Tương tự. |

Không có lý do phải đổi tất cả Java source files khi chuyển build scripts từ Groovy sang Kotlin. Nhưng khi **chuyển precompiled plugin source**, cần chuyển cả **host plugin build** (`groovy-gradle-plugin` ↔ `kotlin-dsl`), các DSL property assignments, plugin ID/package, dependencies và test expectations.

## 8. Phương án `buildSrc` thay cho `build-logic`

Nếu muốn giảm số Settings declarations trong dự án nhỏ, bạn có thể dùng `buildSrc`:

~~~text
small-project/
├── settings.gradle.kts
├── app/build.gradle.kts
└── buildSrc/
    ├── build.gradle.kts
    └── src/main/kotlin/java-conventions.gradle.kts
~~~

`buildSrc/build.gradle.kts`:

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
~~~

`buildSrc/src/main/kotlin/java-conventions.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

`app/build.gradle.kts`:

~~~kotlin
plugins {
    id("java-conventions")
}
~~~

**Không cần** `includeBuild("buildSrc")` trong main `settings.gradle.kts`: Gradle nhận diện `buildSrc` tự động tại root. Đây là **cấu trúc thay thế**, không copy nội dung `build-logic` bên lab chính vào `buildSrc` rồi áp hai plugin cùng chức năng tùy tiện.

Lợi ích: setup đơn giản. Cái giá: mọi build scripts của root build có thể chịu ảnh hưởng khi buildSrc logic thay đổi, gây invalidation, và việc kiểm thử/tổ chức dependencies dễ trở nên khó quản lý ở codebase lớn. Vì thế trong multi-project lớn, included `build-logic` thường được dùng để đóng gói convention plugins tách biệt.

### `buildSrc` có phải subproject `:buildSrc`?

Không theo nghĩa `include("buildSrc")`. Nó là cơ chế build logic tự động được Gradle quản lý như build riêng. Khi cần chạy tests của buildSrc, xem task addressing/Gradle version; không giả định thêm include subproject.

## 9. ID plugin được suy ra từ filename, package và scope

### 9.1. Project plugin

File:

~~~text
build-logic/src/main/kotlin/code-quality.gradle.kts
~~~

có ID:

~~~text
code-quality
~~~

File:

~~~text
build-logic/src/main/kotlin/com/acme/java-conventions.gradle.kts
~~~

với dòng:

~~~kotlin
package com.acme
~~~

có ID:

~~~text
com.acme.java-conventions
~~~

Path thư mục theo convention giúp code dễ điều hướng, nhưng ID prefix đến từ **package declaration hợp lệ** và plugin filename. Chỉ tạo thư mục `com/acme` mà không có `package com.acme` **không phải cơ chế chắc chắn để tạo prefix plugin ID**.

Plugin ID:
- Không dùng tiền tố dành riêng `org.gradle` cho plugin nội bộ.
- Không được đụng ID của core Gradle plugins.
- Phải nhất quán giữa filename/package và `plugins { id("...") }` của consumer.
- Không phụ thuộc tên Java class trong app.

### 9.2. Settings plugin và init plugin: suffix file khác

| Source script | Plugin target | Dùng ở đâu? |
| --- | --- | --- |
| `quality.gradle.kts` hoặc `quality.gradle` | `Plugin<Project>` | `build.gradle(.kts)` của project. |
| `quality.settings.gradle.kts` hoặc `quality.settings.gradle` | `Plugin<Settings>` | `settings.gradle(.kts)`. |
| `quality.init.gradle.kts` hoặc `quality.init.gradle` | `Plugin<Gradle>` | Init-script/global Gradle scope. |

Chẳng hạn một precompiled script file tên `quality.settings.gradle.kts` có plugin ID **`quality`** (suffix `.settings.gradle.kts` biểu thị target, không mặc định trở thành đoạn `.settings` trong plugin ID). Khi consumer apply nó từ Settings:

~~~kotlin
pluginManagement {
    includeBuild("settings-logic")
}

plugins {
    id("quality")
}

rootProject.name = "sample"
~~~

Đây là **mảnh Settings minh họa**: chỉ chạy được khi `settings-logic` thực sự tạo Settings-target plugin ID `quality`. Không lấy một Project-target plugin `quality.gradle.kts` rồi apply vào Settings, vì plugin target sai.

Plugin ID và plugin target là **hai khái niệm khác nhau**: tên file quyết định cả phần ID và `Project/Settings/Gradle` scope, nhưng các hậu tố như `.settings.gradle.kts` phải được đọc đúng ý nghĩa.

### 9.3. Không có `version` hoặc `apply false` ngay trong precompiled `plugins`

Trong một project `build.gradle.kts` thông thường, bạn có thể thấy:

~~~kotlin
plugins {
    id("some.external.plugin") version "1.2.3" apply false
}
~~~

Nhưng **đoạn trên là cú pháp cho project Plugin DSL thông thường, không hợp lệ bên trong precompiled script plugin file**. Theo hướng dẫn Gradle, precompiled script plugin `plugins { }` **không hỗ trợ** `version "..."` và `apply false`.

Thay vì chọn version bên trong precompiled file, đưa plugin implementation vào **dependencies của plugin-producing build**, rồi precompiled file apply bằng ID không kèm version. Mục tiếp theo làm rõ.

## 10. External plugin trong precompiled script plugin: hai lớp cấu hình

Giả sử team có convention plugin muốn áp một Gradle plugin bên ngoài. Phải tách:

1. **Plugin implementation classpath**: dependencies của `build-logic`, để script compiler và runtime tìm được plugin classes.
2. **Plugin application**: `plugins { id("external.plugin.id") }` bên trong precompiled script, để mỗi consumer Project thực sự apply plugin đó.

### 10.1. Ví dụ external Gradle plugin theo tài liệu Gradle

`build-logic/build.gradle.kts`:

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}

dependencies {
    implementation("com.bmuschko:gradle-docker-plugin:6.4.0")
}
~~~

Precompiled script file `build-logic/src/main/kotlin/docker-conventions.gradle.kts`:

~~~kotlin
plugins {
    id("com.bmuschko.docker-remote-api")
}
~~~

**Đây là ví dụ về khai báo classpath và plugin ID từ tài liệu Gradle, không phải lab Docker runnable.** Plugin version `6.4.0` là mốc tài liệu minh họa; muốn chạy trên Gradle/JDK mới phải kiểm tra compatibility của version thật. Plugin có thể đòi Docker daemon, credentials và nhiều setup khác.

Tại đây:
- Version của implementation được khai báo **một lần** ở `build-logic.dependencies.implementation`.
- Precompiled script `plugins` chỉ ghi ID, **không** `version "6.4.0"`.
- `apply false` trong precompiled script không được hỗ trợ.
- Nếu muốn plugin classes nằm trên classpath **nhưng chưa apply**, chỉ thêm dependency trong `build-logic` và **không đặt ID trong precompiled `plugins`**.
- `repositories { ... }` ở plugin-producing build chỉ giải quyết artifact classes của plugin; consumer repository cho Java dependencies vẫn là câu chuyện khác.

### 10.2. Plugin marker artifact và implementation module

Một external plugin thường có **plugin marker** theo dạng:

~~~text
plugin.id:plugin.id.gradle.plugin:version
~~~

Marker ánh xạ plugin ID đến implementation module. Trong `build-logic.dependencies` có thể dùng module implementation trực tiếp hoặc marker coordinate nếu Gradle/plugin repository hỗ trợ. Không dùng:

~~~kotlin
// Phản ví dụ về ý định: đây là Java app dependency, không cung cấp
// plugin implementation cho precompiled script plugin build.
dependencies {
    implementation("com.bmuschko:gradle-docker-plugin:6.4.0")
}
~~~

trong **app** rồi nghĩ `docker-conventions` sẽ compile được. Dependency phải được khai báo **trong build-logic build**. Các code fragments trông giống nhau, nhưng placement **quyết định classpath**.

### 10.3. Type-safe accessors chỉ có khi plugin đã apply sớm

Nếu precompiled script có:

~~~kotlin
plugins {
    `java-library`
}
~~~

thì `java { toolchain { ... } }` và các accessors cho Java plugin có thể được sinh cho script compilation. Nếu bạn bỏ `java-library` khỏi `plugins` và chỉ viết:

~~~kotlin
apply(plugin = "java-library")

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
~~~

trong cùng precompiled script, Kotlin DSL compiler **có thể không có** type-safe `java` accessor tại thời điểm compile body vì Plugin DSL không apply sớm. Khi buộc apply muộn, dùng typed extensions API (`extensions.configure<JavaPluginExtension> { ... }`) và đúng imports/classpath, hoặc tốt nhất áp plugin trong `plugins` block.

Tương tự, `apply false` ở root không tạo task/extension trên consumer; Project nào cần plugin phải **apply thật**.

### 10.4. Version catalogs và plugin aliases trong build-logic

Một file `gradle/libs.versions.toml` của root build **không tự xuất hiện** dưới tên `libs` trong included `build-logic`. Included build có Settings/version catalogs riêng. Nếu muốn dùng chung catalogs, phải import/khai báo catalog cho build-logic với Settings API phù hợp.

Mặt khác, bạn **không thể luôn copy** một dòng `alias(libs.plugins.somePlugin)` từ project bình thường sang precompiled script `plugins`. Các plugin aliases từ version catalog không được hỗ trợ ở đây như project scripts; external plugin cần implementation classpath trong plugin-producing build và `id("...")` trong precompiled file.

Bên trong precompiled script, muốn đọc library versions có thể dùng `VersionCatalogsExtension` hoặc dependency notation có version rõ, tùy Gradle version/organization policy. **Đừng nhầm** `libs.plugins` (plugin request) với `libs.someLibrary` (module dependency).

## 11. Chia cấu hình Gradle thành convention, không áp plugin bừa bãi

Precompiled script plugin được gọi là **convention plugin** khi nó gom các lựa chọn chung như JDK version, test framework, compiler flags, code style và publishing conventions.

### 11.1. Sử dụng mặc định dễ override

Plugin có thể cung cấp default dùng `convention(...)` thay vì ghi cứng `set(...)` cho mọi consumer. Ví dụ khi bạn có một extension riêng:

~~~kotlin
interface TeamChecksExtension {
    val enabled: Property<Boolean>
}

val checks = extensions.create<TeamChecksExtension>("teamChecks")

checks.enabled.convention(true)
~~~

Đây là **mảnh Kotlin DSL minh họa**, không phải build script độc lập; interface có thể đặt trong build-logic source type và cần Gradle API imports. `convention(true)` định nghĩa mặc định; consumer có thể `teamChecks { enabled.set(false) }` nếu extension tồn tại và accessors được Gradle sinh ở thời điểm phù hợp.

Trái lại, `set(true)` là phép gán tường minh, có thể làm khó khả năng thay thế default sau khi convention plugin được apply, tùy thứ tự cấu hình. Với những giá trị cố định do policy bắt buộc (JDK security floor), set có thể hợp lý; với options cho từng module, convention là lựa chọn tốt hơn.

### 11.2. Chọn phạm vi plugin đúng

Không phải mọi module đều cần:
- Java Library plugin (một ứng dụng có thể cần Application plugin).
- Maven Publish plugin (chỉ libraries phát hành cần).
- Docker plugin (chỉ services containerized cần).
- Full integration test infrastructure (unit-only library có thể không cần).

Thay vì một `company.all-conventions` plugin áp mọi thứ, có thể tách:
- `company.java-conventions`: Java toolchain, Java test defaults.
- `company.library-conventions`: Java Library và publication conventions.
- `company.application-conventions`: Application/distributions.
- `company.quality-conventions`: Checkstyle/SpotBugs/formatting nếu có dependencies.
- `company.integration-test-conventions`: thêm test suite riêng.

**Những ID là gợi ý thiết kế**, không tự tồn tại nếu bạn chưa viết đúng files/compile plugin. Đừng apply plugin ID tưởng tượng rồi nghĩ Gradle sẽ tự tạo.

### 11.3. Vì sao `subprojects { ... }` không thay thế hoàn toàn?

Root có thể làm:

~~~kotlin
subprojects {
    plugins.apply("java")
}
~~~

Nhưng cấu hình chéo làm module không tự thể hiện nguồn cấu hình, dễ coupling/làm chậm configuration và khó tương thích các tối ưu như Configuration Cache/isolated projects. Một convention plugin áp **trong chính project build script** rõ trách nhiệm và có thể test độc lập hơn.

Không coi mọi `subprojects` là “luôn sai”; chúng vẫn là Gradle API, nhưng team nên ưu tiên explicit plugin application và lazy configuration cho build logic có thể mở rộng.

## 12. Laziness, typed tasks và Configuration Cache

### 12.1. Đừng eager-configure hàng trăm task

Nên dùng:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Thay vì một pattern eager như:

~~~kotlin
tasks.withType<Test>().all {
    useJUnitPlatform()
}
~~~

`configureEach` cấu hình khi task thật sự được hiện thực hóa, phù hợp Gradle task configuration avoidance. Với custom tasks:

~~~kotlin
tasks.register("printBuildPolicy") {
    group = "help"
    doLast {
        println("BUILD_POLICY=java17")
    }
}
~~~

Đây là **mảnh precompiled plugin bổ sung**; khi áp plugin vào `:core`, task sẽ có path `:core:printBuildPolicy`. Khi áp vào `:app`, path sẽ là `:app:printBuildPolicy`. Cùng plugin tạo task **riêng trong từng Project**, không một task global.

### 12.2. Không dùng task action để truy cập `project` bừa bãi

Một custom task cấu hình bằng `doLast` mà truy cập `project.configurations`/`project.properties` ở execution time có thể làm Configuration Cache fail. Khi logic phức tạp, nên tạo **custom task class** với typed properties `@Input`/`@OutputFile`, khai báo providers tại configuration time và chỉ đọc inputs trong `@TaskAction`.

Precompiled script plugins phù hợp để **register/configure** tasks, nhưng logic action dài, I/O phức tạp hoặc cần unit tests kỹ nên tách thành task type trong source Kotlin/Java/Groovy của `build-logic`, rồi precompiled script chỉ wire tasks.

### 12.3. Plugin có thay đổi Project configuration, không thay runtime app tự động

Khi Java source in `PRECOMPILED_OK=...`, đó là JVM application output. Những thay đổi trong Gradle plugin chỉ ảnh hưởng build model: chọn compiler, test runtime, plugin-generated tasks, artifact configs. Một plugin class chỉ tồn tại trên build-logic classpath **không** tự thành library dependency cho ứng dụng Java.

## 13. Test plugin và chẩn đoán đúng từng lớp

### 13.1. Kiểm tra plugin ID được resolve

~~~bash
./gradlew :core:help
./gradlew :app:help
./gradlew :core:tasks --all
./gradlew :app:tasks --all
~~~

Nếu Gradle báo `Plugin [id: 'com.acme.java-conventions'] was not found`, nguyên nhân thường nằm ở Settings `pluginManagement.includeBuild`, đường dẫn build-logic, file/package/ID hoặc build-logic compilation. **Đừng** sửa bằng cách thêm `implementation("com.acme:...")` vào Java app dependencies; đó là hai classpaths khác nhau.

### 13.2. Build logic là một build riêng

~~~bash
./gradlew :build-logic:build
~~~

Dạng build-tree task path ở trên áp dụng khi included build identity là `build-logic` và không có namespace collision. Nó giúp tách lỗi compilation của convention plugin khỏi lỗi Java source trong app. Có thể chạy riêng từ thư mục `build-logic` nếu có Gradle/Wrapper thích hợp, nhưng nhớ rằng nó có Settings/repositories riêng.

### 13.3. Xem task graph

~~~bash
./gradlew :app:build --dry-run
./gradlew :core:test --dry-run
./gradlew :app:run --info
~~~

`--dry-run` chỉ báo graph dự kiến, **không** chạy Java compiler/tests; `--info` in thêm diagnostic log. Khi task bị `UP-TO-DATE` hoặc `FROM-CACHE`, việc không thấy log compiler action mới không chứng minh Gradle bỏ qua plugin.

### 13.4. Kiểm tra Java toolchain

~~~bash
./gradlew --version
./gradlew -q javaToolchains
./gradlew :core:compileJava --info --rerun-tasks
./gradlew :app:test --info --rerun-tasks
~~~

`javaToolchains` báo **JDK installations có sẵn**, không tự chứng minh task cụ thể dùng cài đặt nào. Đọc `JavaCompile.javaCompiler`/`Test.javaLauncher` và `--info` logs khi cần. `./gradlew --version` phản ánh Gradle runtime JVM, có thể khác Java 17 compiler/test toolchain.

### 13.5. Test chính convention plugin như phần mềm

Nếu build logic quan trọng hoặc được chia sẻ nhiều repositories:
- Viết tests cho custom task types/extensions nếu có.
- Dùng Gradle TestKit (`GradleRunner`) để tạo một **fixture project**, apply plugin ID, chạy build và assert outputs.
- Kiểm thử trên dải Gradle versions/JDK versions mà team hỗ trợ.
- Test cả **lỗi**: thiếu JDK, external plugin classpath sai, plugin ID không resolve, task up-to-date sai.
- Không chỉ test Java class `Greeting`/`Main` rồi coi đó là test cho `company.java-conventions`; đó là test của application/lib, không xác minh mọi quy tắc build logic.

Đối với lab mục 5, có thể thực hiện smoke-test bằng `:core:tasks`/`:app:test`/`:app:run`. Với production plugin, TestKit là lớp xác nhận tốt hơn.

## 14. Những lỗi thường gặp và cách sửa

| Lỗi/triệu chứng | Vì sao? | Cách sửa |
| --- | --- | --- |
| `Plugin id 'com.acme.java-conventions' not found` | Settings không include build-logic, file sai path, package/filename khác ID. | Kiểm tra `pluginManagement.includeBuild`, `src/main/kotlin/com/acme` và `package com.acme`. |
| `Plugin [id: 'java-conventions'] not found` | Consumer dùng ID không có package trong khi plugin source có `package com.acme`. | Apply `com.acme.java-conventions`. |
| Plugin Groovy không xuất hiện | Chưa áp `groovy-gradle-plugin`, file `.gradle` không ở `src/main/groovy`. | Sửa plugin-producing build source set/filename. |
| Kotlin script plugin không compile | Chưa áp `kotlin-dsl` hoặc source sai extension, Gradle/JDK incompatible. | Cấu hình đúng plugin build và kiểm tra stacktrace. |
| `plugins { id(...) version "..." }` trong precompiled file bị lỗi | Precompiled `plugins` không hỗ trợ `version`. | Đưa implementation/version vào `build-logic.dependencies`. |
| `apply false` bị từ chối | Precompiled script plugin không hỗ trợ `apply false`. | Bỏ request hoặc chỉ để plugin trên classpath build-logic. |
| External plugin báo “not found” trong precompiled script | Implementation không nằm trên **build-logic** classpath. | Thêm dependency plugin artifact trong `build-logic/build.gradle.kts`. |
| External plugin version classpath conflict | Version bị khai báo trùng giữa root, plugin build, buildSrc hoặc consumer. | Xác định một nguồn implementation/version rõ, kiểm tra compatibility. |
| `Unresolved reference: java` trong Kotlin plugin | Java plugin chưa apply sớm qua `plugins`, accessor chưa sinh. | `plugins { java }` hoặc typed extension API. |
| JUnit tests không được phát hiện | Thiếu JUnit Jupiter/launcher hoặc `useJUnitPlatform()`. | Đặt dependencies + Test config trong convention/consumer đúng. |
| Main class không chạy | App không apply `application` hoặc chưa có `mainClass`. | `plugins { application }` và `application.mainClass`. |
| `Greeting` không tìm thấy | `implementation(project(":core"))` thiếu trong app. | Khai báo Java project dependency đúng. |
| Gradle Daemon Java 21 nhưng compiler Java 17 | Đây là hai JVM khác nhau. | Thường không phải lỗi; xác minh Java toolchain per task. |
| Maven Central ở build-logic nhưng consumer thiếu dependencies | Plugin-building repositories khác target Java repositories. | Đặt `repositories { mavenCentral() }` trong precompiled plugin hoặc consumer. |
| `libs.plugins.*` không có trong build-logic | Version catalog root không tự chia sẻ sang included build. | Import catalog riêng; external plugin classpath đúng. |
| `alias(libs.plugins.x)` không dùng được trong precompiled `plugins` | Version catalog alias không được hỗ trợ như project script block. | `id("x")` + implementation dependency ở build-logic. |
| `:build-logic:build` không tồn tại | Build identity khác, included build chưa được nối, hoặc task path khác. | Xem Settings, `projects` và included build tasks. |
| `:app:build` không chạy `:core:test` | Project dependency chỉ kéo những producers cần cho app, không full core tests. | Chạy `./gradlew test` từ root hoặc `:core:test` rõ. |
| App không thấy code plugin class ở runtime | Plugin class chỉ thuộc build logic classpath. | Thêm Java library dependency thật nếu app cần class. |
| Thay đổi convention làm nhiều projects reconfigure | Build logic thay đổi, cấu hình cache bị invalidated. | Giữ plugin scope hẹp, convention plugin thay cross-project script mutation. |
| Plugin dùng project API trong task action, cache fail | Task action không khai báo input/provider đúng. | Dùng custom task types với typed properties và configuration-cache-safe APIs. |
| Plugin áp lên mọi module không cần Java | Root `subprojects` apply chung hoặc convention quá rộng. | Tách conventions theo vai trò module. |

### Workflow debug từng bước

1. Đọc file root `settings.gradle.kts`: `pluginManagement.includeBuild("build-logic")` có đúng vị trí sớm không?
2. Đọc `build-logic/settings.gradle.kts` và `build-logic/build.gradle.kts`: `kotlin-dsl` hoặc `groovy-gradle-plugin` đã áp đúng chưa?
3. Kiểm tra filename/extension/source directory.
4. Kiểm tra package declaration (Kotlin) và plugin ID consumer sử dụng.
5. Nếu có external plugin, xác minh implementation dependency ở **build-logic** và repository của build-logic.
6. Chạy `./gradlew :build-logic:build --stacktrace` để tách compilation error.
7. Chạy `./gradlew :core:help --info` để xác nhận plugin application.
8. Chạy `./gradlew :core:tasks --all` và `:app:tasks --all` để xem Java/Application tasks thực sự có mặt.
9. Chạy `./gradlew :app:dependencies --configuration runtimeClasspath` để kiểm tra Java project dependency.
10. Chạy `./gradlew :app:test` và `:app:run`; so sánh stdout với expected.
11. Nếu chỉ IDE fail, refresh Gradle model/Wrapper và kiểm tra IDE Gradle JVM.
12. Khi CI fail, kiểm tra path, permission, JDK, plugin repo/network và credentials; không copy log chứa secrets lên public ticket.

## 15. Checklist code review

- [ ] Đã chọn đúng hình thức: precompiled script plugin, không chỉ `apply(from)`.
- [ ] Plugin-producing build được đặt ở `buildSrc` hoặc included `build-logic` có chủ đích.
- [ ] Kotlin dùng `kotlin-dsl`, `src/main/kotlin/*.gradle.kts`.
- [ ] Groovy dùng `groovy-gradle-plugin`, `src/main/groovy/*.gradle`.
- [ ] Filename, package và consumer plugin ID khớp chính xác.
- [ ] Không dùng ID bắt đầu bằng `org.gradle` hoặc đè core plugin ID.
- [ ] Project plugin/Settings plugin/init plugin có suffix file và target phù hợp.
- [ ] `pluginManagement.includeBuild` được dùng nếu local plugin phải resolve qua Plugin DSL sớm.
- [ ] Không nhầm `includeBuild` với `include` của multi-project.
- [ ] Repositories và version catalogs của build-logic độc lập với main build.
- [ ] Không đặt `version`/`apply false` trong precompiled `plugins`.
- [ ] External plugin implementation/version nằm trên build-logic classpath.
- [ ] Shared conventions chỉ apply những plugins mà consumer thực sự cần.
- [ ] Java 17 toolchain/JUnit config nằm trong đúng precompiled plugin và có tests.
- [ ] Consumers apply plugin ID trong chính `plugins` block; không dựa vào root mutation ẩn.
- [ ] `tasks.withType<Test>().configureEach` thay cho eager task configuration khi phù hợp.
- [ ] Task action dùng declared inputs/outputs/providers nếu có logic I/O phức tạp.
- [ ] `:app:run` và `:app:test` đã được chạy trong môi trường thực trước release.
- [ ] Build-logic được kiểm thử riêng bằng smoke tests hoặc Gradle TestKit.
- [ ] Version/plugin compatibility được pin và đánh giá khi nâng Gradle Wrapper.
- [ ] CI không lộ secrets hoặc hard-code developer-local paths.
- [ ] Document rõ những conventions có thể override và những policy bắt buộc.

## 16. Câu hỏi tự kiểm tra

1. **Precompiled script plugin là gì?** Là Gradle DSL script được Gradle biên dịch thành plugin classes/metadata để apply theo plugin ID.
2. **Khác gì so với `apply(from = "...")`?** Precompiled plugin có ID, được compile và tích hợp Plugin DSL sớm; script apply truyền thống đánh giá file vào script hiện tại.
3. **Plugin Kotlin DSL dùng extension gì?** `.gradle.kts` trong plugin source set.
4. **Plugin Groovy DSL dùng extension gì?** `.gradle`.
5. **`kotlin-dsl` nằm ở đâu?** Trong `plugins` của plugin-producing build `build-logic`/`buildSrc`.
6. **`groovy-gradle-plugin` nằm ở đâu?** Trong plugin-producing build của Groovy precompiled scripts.
7. **`includeBuild("build-logic")` thêm subproject không?** Không, thêm một build riêng.
8. **Dùng `pluginManagement.includeBuild` làm gì?** Đưa local plugin build vào plugin resolution trước consumer `plugins`.
9. **Có cần includeBuild cho `buildSrc` không?** Không; Gradle tự nhận diện `buildSrc`.
10. **`com.acme.java-conventions` sinh từ đâu?** Kotlin package `com.acme` + filename `java-conventions.gradle.kts`.
11. **Đổi Java package `demo.core` có đổi plugin ID không?** Không.
12. **Có thể consumer Groovy apply plugin viết Kotlin DSL không?** Có, qua ID.
13. **Có thể consumer Kotlin apply plugin viết Groovy DSL không?** Có, qua ID.
14. **`version "x"` có dùng được trong precompiled `plugins` không?** Không.
15. **`apply false` có dùng được trong precompiled `plugins` không?** Không.
16. **Version external plugin đặt ở đâu?** Dependency implementation/classpath của plugin-producing build.
17. **`repositories` ở build-logic có tự thêm Maven Central cho app không?** Không.
18. **Cần gì để `java { toolchain ... }` có typed accessor?** Java plugin apply sớm trong precompiled `plugins` hoặc dùng typed extensions API.
19. **`:app:build` có tự chạy `:core:test` không?** Không chỉ vì app dependency; chạy root `test` nếu cần hai tests.
20. **Plugin classes có tự có trên app runtime classpath không?** Không.
21. **`configureEach` giúp gì?** Giảm eager task configuration và hỗ trợ task registration sau.
22. **Bộ lệnh nào kiểm tra plugin end-to-end?** `:build-logic:build`, `:core:tasks`, `:app:test`, `:app:run`.
23. **Tại sao dùng TestKit cho build logic?** Kiểm thử việc apply plugin và cấu hình tasks trong fixture Gradle build.
24. **Khi nào nên tách thành binary plugin/custom task class?** Khi plugin logic phức tạp, cần typed inputs/outputs, nhiều tests hoặc publish đa build.
25. **Nếu hai modules đều áp convention, chúng có một Test task chung không?** Không, plugin cấu hình Test tasks **riêng của từng Project**.

## 17. Tài liệu Gradle chính thức

- [Gradle — Pre-compiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html): source file/ID/package, Project/Settings/Gradle targets, extensions, external plugins, `version`/`apply false` restrictions.
- [Gradle — Implementing Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): script, precompiled script và binary plugin trade-offs.
- [Gradle — Groovy Gradle Plugin](https://docs.gradle.org/current/userguide/groovy_gradle_plugin.html): `groovy-gradle-plugin`, `src/main/groovy`, plugin adapters/compilation tasks.
- [Gradle — Sharing Build Logic](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): `buildSrc`, `build-logic` included build, convention plugins vs cross-project configuration.
- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html): cách tổ chức conventions.
- [Gradle — Writing Plugins](https://docs.gradle.org/current/userguide/writing_plugins.html): precompiled scripts, binary plugins và testing.
- [Gradle — Kotlin DSL](https://docs.gradle.org/current/userguide/kotlin_dsl.html): `.gradle.kts`, type-safe accessors, script compilation.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): catalogs trong builds và giới hạn plugin aliases.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): `pluginManagement.includeBuild`/`includeBuild`, identity và task addressing.
- [Gradle — TestKit](https://docs.gradle.org/current/userguide/test_kit.html): integration tests cho Gradle plugin với `GradleRunner`.
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html): `tasks.register` và `configureEach`.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): task actions, build logic và restrictions.
