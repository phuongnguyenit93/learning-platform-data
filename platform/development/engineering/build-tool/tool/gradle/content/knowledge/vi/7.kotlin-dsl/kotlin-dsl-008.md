# Chuyển build script từ Groovy DSL sang Kotlin DSL trong Gradle

## 1. Mục tiêu và những gì thực sự thay đổi

Gradle hỗ trợ **Groovy DSL** (file `build.gradle`, `settings.gradle`) và **Kotlin DSL** (file `build.gradle.kts`, `settings.gradle.kts`). Chuyển từ Groovy sang Kotlin là thay **ngôn ngữ của build script** và cách gọi API Gradle. Các khái niệm Project, Plugin, Task, Configuration, Dependency, Provider và vòng đời build vẫn là những khái niệm Gradle như trước.

**Không nhầm lẫn ba việc khác nhau:**

- **Đổi DSL:** thay cú pháp và tên file cấu hình của Gradle, chẳng hạn `dependencies { implementation 'g:a:v' }` thành `dependencies { implementation("g:a:v") }`.
- **Nâng Gradle/plugin:** thay phiên bản Gradle Wrapper, Java toolchain hoặc plugin; việc này có thể làm thay đổi hành vi và nên được kiểm tra riêng.
- **Chuyển ngôn ngữ ứng dụng:** thay mã Java bằng Kotlin hay ngược lại. Chuyển DSL **không yêu cầu** chuyển mã ứng dụng hoặc cài Kotlin JVM plugin cho một dự án thuần Java.

Migration thành công khi các project và plugin được cấu hình đúng, dependencies được resolve tương đương, task quan trọng vẫn tồn tại, test/build chạy thành công, artifact cần thiết không đổi bất ngờ, và pipeline/IDE dùng đúng tên file mới.

## 2. Kiểm kê file, chọn thứ tự chuyển và chốt baseline

| Mục đích | Tên Groovy DSL | Tên Kotlin DSL |
| --- | --- | --- |
| Settings của build | `settings.gradle` | `settings.gradle.kts` |
| Root project | `build.gradle` | `build.gradle.kts` |
| Project con | `app/build.gradle` | `app/build.gradle.kts` |
| Script cấu hình được apply | `gradle/quality.gradle` | `gradle/quality.gradle.kts` |
| Init script (nếu dùng) | `init.gradle` | `init.gradle.kts` |

Gradle cho phép **các project khác nhau dùng hai DSL trong cùng một multi-project build**. Bạn có thể chuyển từng file hoặc từng module, không buộc chuyển toàn bộ trong một commit. Trong cùng thư mục project, hãy chỉ giữ **một build script hoạt động** được Gradle nhận là nguồn cấu hình; giữ bản cũ trong hệ thống quản lý phiên bản. Khi đổi tên script được apply từ chỗ khác, cập nhật đường dẫn người gọi.

Trước khi chuyển, trên nhánh có thể quay lại được, ghi lại các đầu vào và kết quả hiện tại:

```bash
./gradlew --version
./gradlew projects
./gradlew tasks --all
./gradlew build
```

Với dự án lớn, chạy thêm các task quan trọng của module như `:app:build`, `:app:test`, `:app:run`, `:service:bootJar` hoặc task publish/codegen nếu chúng thật sự tồn tại. Lưu tên artifact, dependency graph, báo cáo test và các project path. Không lấy việc “script compile được” làm bằng chứng đầy đủ rằng toàn bộ behavior đã được giữ nguyên.

**Chiến lược chuyển an toàn:** chuẩn hóa cú pháp Groovy trước; chuyển `settings.gradle` và từng `build.gradle` theo phạm vi nhỏ; sau mỗi thay đổi chạy lại Gradle Wrapper; cuối cùng mới xử lý plugin Groovy động, CI và refactor build logic. Tránh trộn migration DSL với cập nhật plugin/Gradle không liên quan, vì khi lỗi sẽ khó phân biệt nguyên nhân.

## 3. Khác biệt cú pháp Groovy và Kotlin cần thuộc

Groovy cho phép bỏ ngoặc tròn khi gọi phương thức và hỗ trợ kiểu động. Kotlin kiểm tra kiểu khi biên dịch script, phân biệt chuỗi với ký tự, dùng `val`/`var` thay vì `def`, và cần lời gọi hàm rõ ràng.

| Thành phần | Groovy DSL | Kotlin DSL |
| --- | --- | --- |
| Chuỗi | `'java'` hoặc `"java"` | `"java"`; `'j'` là kiểu `Char` |
| Gọi method | `id 'java'` | `id("java")` |
| Gán property | `group = 'com.acme'` | `group = "com.acme"` |
| Biến local | `def mode = 'dev'` | `val mode = "dev"` hoặc `var mode = "dev"` |
| List | `['dev', 'prod']` | `listOf("dev", "prod")` |
| Map | `[dev: 1, prod: 3]` | `mapOf("dev" to 1, "prod" to 3)` |
| In ra màn hình | `println 'Hello'` | `println("Hello")` |
| Chuỗi có biến | `"mode=${mode}"` | `"mode=$mode"` hoặc `"mode=${mode}"` |
| Extra property | `ext.channel = 'beta'` | `extra["channel"] = "beta"` |
| Đăng ký task | `tasks.register('hello') { }` | `tasks.register("hello") { }` |
| Apply script | `apply from: 'quality.gradle'` | `apply(from = "quality.gradle")` |

**Phân biệt assignment và method:** `group = "com.acme"` là gán property `group` trên Project; `implementation("g:a:v")` là lời gọi API dependency. Thêm `()` cho mọi dòng Groovy sẽ gây lỗi khi dòng đó thực chất là property. Ngược lại, đổi lời gọi `implementation '...'` thành `implementation = "..."` cũng sai.

Đối với điều kiện, Groovy truth khác Kotlin:

```groovy
def targets = []
if (!targets) {
    println 'Không có target'
}
```

```kotlin
val targets = emptyList<String>()
if (targets.isEmpty()) {
    println("Không có target")
}
```

Groovy chấp nhận list rỗng, số `0`, chuỗi rỗng... như false trong điều kiện; Kotlin cần một `Boolean` rõ ràng. Cú pháp Elvis `?:` cũng khác: trong Groovy chọn fallback khi giá trị là “falsey”, trong Kotlin chỉ chọn fallback khi giá trị `null`. Nếu cấu hình có ý nghĩa riêng cho `0` hoặc `false`, phải chuyển theo **ngữ nghĩa mong muốn**.

## 4. Settings: chuyển tên project và cấu trúc multi-project

**Trước – `settings.gradle`:**

```groovy
rootProject.name = 'migration-lab'
include 'core', 'app'
```

**Sau – `settings.gradle.kts`:**

```kotlin
rootProject.name = "migration-lab"
include(":core", ":app")
```

`rootProject.name` và `include` thuộc API của **Settings**, khác với `Project` trong `build.gradle.kts`. `:core` và `:app` là path logic của project, không phải package Java hay tên class.

Nếu build dùng `pluginManagement`:

```groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

thì Kotlin DSL có thể giữ gần như nguyên văn:

```kotlin
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}
```

Khối `pluginManagement.repositories` dùng để tìm **plugin**, còn `repositories` của project hoặc `dependencyResolutionManagement.repositories` trong settings (nếu được cấu hình) dùng cho **module dependency**. Chuyển syntax không phải cơ hội tự ý đổi nguồn repository, policy, nội dung dependency catalog hay cách giải quyết dependency.

## 5. Plugins: thay cú pháp và hiểu thời điểm sinh accessor

**Groovy:**

```groovy
plugins {
    id 'java-library'
    id 'maven-publish'
    id 'com.example.demo-plugin' version '1.0.0' apply false
}
```

**Kotlin:**

```kotlin
plugins {
    id("java-library")
    id("maven-publish")
    id("com.example.demo-plugin") version "1.0.0" apply false
}
```

Plugin `com.example.demo-plugin` là ví dụ cú pháp và không bảo đảm tồn tại trên plugin repository. Với core plugins của Gradle, Kotlin DSL cũng có cú pháp accessor của plugin khi thích hợp. Trong migration, dạng `id("java-library")` thường dễ đối chiếu nguồn Groovy nhất.

**Groovy kiểu cũ:**

```groovy
apply plugin: 'java'
```

Kotlin tương ứng: `apply(plugin = "java")`. Tuy nhiên, **nên sử dụng khối `plugins { id("java") }` khi có thể**. Kotlin DSL sinh nhiều *type-safe model accessors* dựa trên plugin/mô hình đã có trước khi thực thi thân script. Nếu plugin được áp dụng muộn trong thân script bằng `apply(plugin = ...)`, lời gọi như `implementation("...")` hay `java { ... }` có thể không có accessor để compile.

Trong trường hợp apply muộn bắt buộc, dùng API tường minh theo **tên hoặc kiểu** (xem mục 10); không thêm `afterEvaluate` như một mẹo chung để che lỗi. Các plugin cộng đồng có thể có hạn chế riêng đối với Kotlin DSL, cần dựa vào tài liệu của đúng phiên bản plugin.

## 6. Repositories và Dependencies: chuyển method call đúng API

### Repository

**Groovy:**

```groovy
repositories {
    mavenCentral()
    maven {
        url 'https://repo.example.org/releases'
    }
}
```

**Kotlin:**

```kotlin
repositories {
    mavenCentral()
    maven {
        url = uri("https://repo.example.org/releases")
    }
}
```

`mavenCentral()` là method không đối số; `url` là property nhận kiểu URI, nên dạng `url = uri("...")` là cách rõ ràng. URL ở trên chỉ minh họa cú pháp; muốn build thật phải có repository hoạt động, quyền truy cập và artifact thích hợp.

### Dependency từ module ngoài và project trong build

**Groovy (đã áp dụng Java plugin):**

```groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.17.0'
    implementation project(':core')
    testImplementation files('libs/test-utils.jar')
}
```

**Kotlin:**

```kotlin
dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
    implementation(project(":core"))
    testImplementation(files("libs/test-utils.jar"))
}
```

`implementation`, `testImplementation` là các API theo configuration do plugin tạo ra; chúng không phải từ khóa Kotlin toàn cục. `project(":core")` chỉ tồn tại nếu settings khai báo project tương ứng. File `libs/test-utils.jar` là đầu vào ví dụ, muốn chạy cần file đó có thật. Với dependency module từ Maven Central phải khai báo repository, đồng thời kiểm tra tính hợp lệ của phiên bản.

Nếu build dùng version catalog `gradle/libs.versions.toml`:

```groovy
dependencies {
    implementation libs.guava
}
```

chuyển sang:

```kotlin
dependencies {
    implementation(libs.guava)
}
```

Chỉ dùng được `libs.guava` khi catalog thực sự có alias đó. Không tạo thư viện hoặc thay version chỉ vì thay ngôn ngữ build script.

### Exclude dependency

**Groovy:**

```groovy
dependencies {
    implementation('com.example:feature:1.0') {
        exclude group: 'org.slf4j', module: 'slf4j-simple'
    }
}
```

**Kotlin:**

```kotlin
dependencies {
    implementation("com.example:feature:1.0") {
        exclude(group = "org.slf4j", module = "slf4j-simple")
    }
}
```

Đây là minh họa API `exclude` phổ biến; dependency `com.example:feature:1.0` không được khẳng định là có thật. Với method Groovy bất kỳ nhận “named arguments”, không mặc nhiên dịch được thành Kotlin named parameters: có method thật nhận `Map`, khi đó phải dùng `mapOf(...)` hoặc API tương ứng.

## 7. Property, toolchain, nguồn mã và plugin extension

**Groovy:**

```groovy
plugins {
    id 'java'
}

group = 'org.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.named('compileJava') {
    options.encoding = 'UTF-8'
}
```

**Kotlin:**

```kotlin
plugins {
    id("java")
}

group = "org.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.named<JavaCompile>("compileJava") {
    options.encoding = "UTF-8"
}
```

`java` là extension do Java plugin cung cấp; `languageVersion` là một `Property<JavaLanguageVersion>`, có thể cấu hình bằng `set(...)`. Một số phiên bản Gradle hiện đại còn hỗ trợ `languageVersion = JavaLanguageVersion.of(17)` cho lazy property assignment; dạng `set` tiện khi muốn rõ ràng về Provider API và tính tương thích. `JavaCompile` là task type của Gradle; nếu import mặc định không đáp ứng IDE của dự án, thêm `import org.gradle.api.tasks.compile.JavaCompile` ở đầu script.

**Không thay thế việc chọn toolchain bằng cách chỉ đổi đuôi file.** Khi build chạy bằng JDK 21 nhưng Java toolchain yêu cầu 17, môi trường phải có JDK17 tương ứng hoặc cơ chế tải toolchain đã được cấu hình. Gradle Wrapper version, Gradle JVM và Java toolchain là ba thông số cần phân biệt.

Plugin khác có thể tạo extension kiểu riêng. Một khối Groovy như `somePlugin { option = 'x' }` chỉ có thể chuyển đúng khi biết plugin ID, kiểu extension và API của phiên bản đó. Nếu thiếu accessor, cách tiếp cận là cấu hình theo kiểu extension hoặc kiểm tra tài liệu plugin, không đoán tên hàm từ Groovy.

## 8. Task: chuyển closure Groovy thành lambda Kotlin

### Đăng ký task và giữ đúng giai đoạn thực thi

**Groovy:**

```groovy
tasks.register('greet') {
    group = 'learning'
    description = 'In lời chào'
    doLast {
        println 'Hello from Gradle'
    }
}
```

**Kotlin:**

```kotlin
tasks.register("greet") {
    group = "learning"
    description = "In lời chào"
    doLast {
        println("Hello from Gradle")
    }
}
```

`tasks.register` trả về `TaskProvider`, giúp Gradle trì hoãn cấu hình task không được dùng. `group` và `description` được cấu hình khi task được hiện thực hóa; `doLast` là **action** chạy trong giai đoạn execution khi task nằm trong graph và không bị bỏ qua.

**Không trộn hai thời điểm sau:**

```kotlin
println("Đang đánh giá script")

tasks.register("example") {
    println("Đang cấu hình task")
    doLast {
        println("Đang chạy task")
    }
}
```

Dòng đầu chạy khi Gradle đánh giá script; dòng thứ hai chỉ chạy khi task được hiện thực hóa/cấu hình (có thể trì hoãn nhờ `register`); dòng trong `doLast` chạy lúc task action được thực thi. Việc chuyển DSL không biến code ở cấp script thành action của task.

### Task có kiểu cụ thể

**Groovy:**

```groovy
tasks.register('copyAssets', Copy) {
    from 'src/assets'
    into layout.buildDirectory.dir('assets')
}
```

**Kotlin:**

```kotlin
tasks.register<Copy>("copyAssets") {
    from("src/assets")
    into(layout.buildDirectory.dir("assets"))
}
```

`Copy` là task type. `<Copy>` trong Kotlin cung cấp API có kiểu, và `layout.buildDirectory` trả về Provider/Directory tương thích. Đây là ví dụ khai báo; muốn thực sự copy file phải có thư mục `src/assets` và task được yêu cầu chạy. Không cần dùng API `tasks.create` nếu chỉ muốn cấu hình/đăng ký lazy.

### Cấu hình task plugin đã tạo

**Groovy:**

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}
```

**Kotlin:**

```kotlin
import org.gradle.api.tasks.testing.Test

plugins {
    id("java")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

Những task-specific methods như `useJUnitPlatform()` cần đúng kiểu `Test`. Nếu lấy `tasks.named("test")` mà Gradle/Kotlin chỉ biết kiểu chung `Task`, compiler có thể báo `Unresolved reference: useJUnitPlatform`. Có thể dùng accessor `tasks.test { useJUnitPlatform() }` khi plugin đã được áp dụng và accessor sẵn có.

### Task dependency vẫn phải được giữ nguyên

**Groovy:**

```groovy
def prepare = tasks.register('prepare') {
    doLast { println 'prepare' }
}

tasks.register('executeDemo') {
    dependsOn prepare
    doLast { println 'executeDemo' }
}
```

**Kotlin:**

```kotlin
val prepare = tasks.register("prepare") {
    doLast { println("prepare") }
}

tasks.register("executeDemo") {
    dependsOn(prepare)
    doLast { println("executeDemo") }
}
```

Chạy `./gradlew -q executeDemo` sẽ in do hai action này:

```text
prepare
executeDemo
```

`dependsOn` kết nối task graph; nó không thay thế `implementation(project(":core"))` vốn dùng để khai báo dependency phần mềm/classpath. `mustRunAfter` và `shouldRunAfter` quy định thứ tự khi các task cùng được chọn, không tự làm task khác xuất hiện trong graph.

## 9. Provider, biến local và extra property

### Biến local

`def channel = 'dev'` trong Groovy thường chuyển thành `val channel = "dev"` trong Kotlin; dùng `var` nếu biến phải được gán lại. List/map thay bằng `listOf`, `mapOf`, hoặc collection biến đổi được khi cần. Một `val` chứa `MutableList` không khiến chính list trở nên bất biến.

### Extra property

**Groovy:**

```groovy
ext.releaseChannel = 'beta'
println project.ext.releaseChannel
```

**Kotlin:**

```kotlin
extra["releaseChannel"] = "beta"
println(extra["releaseChannel"] as String)
```

`ext` và `extra` là API Gradle của đối tượng có hỗ trợ extra properties; không phải biến local. Trong multi-project build, lưu ý property thuộc root project hay subproject. Không chuyển việc đọc `rootProject.ext` sang `extra` của project con rồi cho rằng chúng tương đương. Với cấu hình được chia sẻ rộng, cân nhắc convention plugin hoặc cấu hình có kiểu trong một đợt refactor riêng.

### Project property và Provider

**Groovy:**

```groovy
def stageProvider = providers.gradleProperty('stage').orElse('dev')
tasks.register('showStage') {
    doLast {
        println "stage=${stageProvider.get()}"
    }
}
```

**Kotlin:**

```kotlin
val stageProvider = providers.gradleProperty("stage").orElse("dev")
tasks.register("showStage") {
    doLast {
        println("stage=${stageProvider.get()}")
    }
}
```

Lệnh `./gradlew -q showStage` in `stage=dev`. Lệnh `./gradlew -q showStage -Pstage=prod` in `stage=prod`. `Provider<String>` là API Gradle về giá trị trì hoãn; đây không phải string Groovy/Kotlin thông thường. Dùng `map`, `flatMap` và `set`/assignment vào Gradle property khi API hỗ trợ, tránh gọi `get()` ở giai đoạn cấu hình chỉ vì thuận tay.

## 10. Bản migration đầy đủ có thể chạy: :core và :app

Bài tập có một thư viện Java `:core` và một ứng dụng `:app`; project dependency giữ nguyên sau migration. Chỉ cần Gradle Wrapper phù hợp và JDK 17 cho Java toolchain (hoặc toolchain resolver đã cấu hình), không cần tải dependency ngoài.

### Cấu trúc

```text
migration-lab/
├── settings.gradle               # Trước migration
├── core/
│   ├── build.gradle              # Trước migration
│   └── src/main/java/demo/core/Greeting.java
└── app/
    ├── build.gradle              # Trước migration
    └── src/main/java/demo/app/Main.java
```

Khi chuyển, đổi từng file `*.gradle` thành `*.gradle.kts` tương ứng. Không để song song hai bản cấu hình trong cùng project như hai file active. Có thể chưa cần root `build.gradle`: root Project vẫn tồn tại nhờ settings. Nếu cần tạo Wrapper cho bài tập mới và máy đã có Gradle, chạy `gradle wrapper` tại root; dự án thực tế nên dùng Wrapper hiện có.

### Ba script Groovy trước migration

**`settings.gradle`:**

```groovy
rootProject.name = 'migration-lab'
include 'core', 'app'
```

**`core/build.gradle`:**

```groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
```

**`app/build.gradle`:**

```groovy
plugins {
    id 'application'
}

application {
    mainClass = 'demo.app.Main'
}

dependencies {
    implementation project(':core')
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

def environment = providers.gradleProperty('environment').orElse('dev')

tasks.register('showEnvironment') {
    group = 'learning'
    doLast {
        println "environment=${environment.get()}"
    }
}
```

### Ba script Kotlin sau migration

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "migration-lab"
include(":core", ":app")
```

**`core/build.gradle.kts`:**

```kotlin
plugins {
    id("java-library")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

**`app/build.gradle.kts`:**

```kotlin
plugins {
    id("application")
}

application {
    mainClass.set("demo.app.Main")
}

dependencies {
    implementation(project(":core"))
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

val environment = providers.gradleProperty("environment").orElse("dev")

tasks.register("showEnvironment") {
    group = "learning"
    doLast {
        println("environment=${environment.get()}")
    }
}
```

### Hai file Java không cần thay đổi

**`core/src/main/java/demo/core/Greeting.java`:**

```java
package demo.core;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from core";
    }
}
```

**`app/src/main/java/demo/app/Main.java`:**

```java
package demo.app;

import demo.core.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Application: " + Greeting.message());
    }
}
```

Để xác nhận source Java độc lập với Gradle, từ root trên macOS/Linux:

```bash
mkdir -p out
javac -d out core/src/main/java/demo/core/Greeting.java app/src/main/java/demo/app/Main.java
java -cp out demo.app.Main
```

`javac -d out` đặt `.class` theo package dưới thư mục `out`, rồi lệnh `java -cp out` chạy main class. Trên Windows, thay `mkdir -p out` bằng `mkdir out` nếu thư mục chưa tồn tại; các lệnh `javac`/`java` còn lại tương tự.

**Stdout chính xác do Java in:**

```text
Application: Hello from core
```

### Chạy Gradle trước và sau chuyển

```bash
./gradlew projects
./gradlew :app:tasks --all
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:run
./gradlew :app:build
./gradlew -q :app:showEnvironment
./gradlew -q :app:showEnvironment -Penvironment=prod
```

Trên Windows, dùng `gradlew.bat` thay `./gradlew`. Chương trình từ `:app:run` in dòng `Application: Hello from core`. Hai lần `showEnvironment` in tương ứng:

```text
environment=dev
```

```text
environment=prod
```

**Vì sao hai DSL tương đương ở ví dụ này?** Cả hai settings khai báo đúng hai Project; `:core` áp dụng `java-library`; `:app` áp dụng `application` và có dependency `implementation(project(":core"))`; Java toolchain là 17; main class là `demo.app.Main`; task `showEnvironment` nhận cùng property và in cùng giá trị. Gradle có thể in log hoặc trạng thái task khác nhau do cache/trạng thái build, nhưng hành vi chương trình và dependency graph thiết yếu phải tương đương.

## 11. Type-safe accessors: khi nào có, khi nào không?

Một ưu điểm của Kotlin DSL là Gradle sinh accessors có kiểu cho nhiều model elements (configuration, extension, task, source set) **đã được tạo ở thời điểm định hình schema trước khi thực thi thân script**. Thông thường, plugin trong khối `plugins { }` cung cấp những phần này.

Ví dụ sau **có** accessor `implementation(...)` nhờ Java plugin:

```kotlin
plugins {
    id("java")
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Khi áp dụng plugin muộn, có thể cần API theo chuỗi:

```kotlin
apply(plugin = "java")

dependencies {
    add("implementation", "org.apache.commons:commons-lang3:3.17.0")
}
```

Tương tự, khi tự tạo configuration trong thân script:

```kotlin
val tooling by configurations.creating

dependencies {
    add("tooling", "org.apache.commons:commons-lang3:3.17.0")
}
```

`tooling("...")` chưa chắc có type-safe accessor, bởi configuration đó được tạo sau điểm Gradle sinh accessors. Đoạn trên minh họa cú pháp khai báo; một custom configuration muốn dùng thực tế còn phải có vai trò resolvable/consumable và cách đưa vào task phù hợp.

Nếu cần cấu hình extension Java sau khi apply muộn, dùng kiểu extension:

```kotlin
import org.gradle.api.plugins.JavaPluginExtension

apply(plugin = "java")

configure<JavaPluginExtension> {
    sourceCompatibility = JavaVersion.VERSION_17
}
```

Nếu không thấy accessor của plugin khác, tìm class extension thật trong tài liệu plugin và cấu hình bằng `configure<ActualExtension>`. Với task có API cụ thể, dùng `tasks.named<Test>("test")` thay vì `tasks.named("test")` nếu cần gọi API thuộc `Test`. Lệnh `./gradlew :app:kotlinDslAccessorsReport` có thể giúp xem accessors Gradle sinh cho project `:app` khi task tồn tại.

## 12. Plugin phụ thuộc Groovy động và môi trường đa script

Một số plugin viết bằng Groovy nhận `groovy.lang.Closure`, dùng named map arguments hoặc dynamic method/property. Kotlin DSL không tự chuyển mọi biểu thức Groovy động thành Kotlin có kiểu. Các lựa chọn:

1. Dùng cú pháp Kotlin DSL chính thức của **đúng phiên bản plugin**, nếu có.
2. Dùng plugin API dạng `Action<T>` hoặc extension có kiểu; Kotlin lambda thường tương tác trực tiếp với API này.
3. Nếu plugin thật sự yêu cầu Groovy Closure, Kotlin DSL có các trợ giúp như `closureOf<T>`, `delegateClosureOf<T>` và `withGroovyBuilder`. Chỉ áp dụng khi đã xác định method/delegate thực, vì không có một adapter chung đúng cho mọi plugin.
4. Tạm giữ một Groovy script riêng cho phần cấu hình rất động, áp dụng bằng `apply(from = "legacy-config.gradle")` trong script Kotlin, rồi chuyển dần khi plugin hỗ trợ.

Ví dụ áp dụng script Groovy từ Kotlin:

```kotlin
plugins {
    id("java")
}

apply(from = "legacy-config.gradle")
```

Ví dụ này **chỉ chạy khi** `legacy-config.gradle` tồn tại và chứa build logic hợp lệ. Trong multi-project build, script con Groovy và Kotlin có thể cùng tồn tại; tuy nhiên việc apply script/plugin sau `plugins { }` không bảo đảm tạo type-safe accessor trong thân script đang biên dịch.

Nếu bản Groovy dùng `allprojects { ... }`, `subprojects { ... }`, `buildSrc` hoặc included build, phân tích từng phần trước khi thay. Chuyển DSL không đồng nghĩa với di chuyển cấu hình từ root xuống module hay đổi chiến lược convention plugins. Nếu thực sự muốn tái cấu trúc, cần một lượt kiểm thử riêng để tránh làm lệch semantics trong cùng migration.

## 13. Lỗi điển hình và cách sửa

| Lỗi/triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `Unexpected tokens`, `Expecting an expression` | Còn cú pháp Groovy `id 'java'`, `def`, map `[key: value]`. | Viết lời gọi Kotlin có ngoặc, `val/var`, `mapOf`. |
| `Too many characters in a character literal` | Giữ `'java'` như String trong Kotlin. | Đổi thành `"java"`. |
| `Unresolved reference: implementation` | Chưa áp dụng plugin có configuration trước khi sinh accessors. | Dùng `plugins { }` đúng plugin hoặc `add("implementation", ...)`. |
| `Unresolved reference: java` | Java extension chưa tồn tại/không có accessor. | Kiểm tra plugin, dùng `configure<JavaPluginExtension>` khi cần. |
| `Unresolved reference: useJUnitPlatform` | Cấu hình `test` với kiểu chung `Task`. | Dùng `tasks.named<Test>("test")`/accessor của `Test`. |
| `Type mismatch` cho repository URL | Dùng `url "..."` hoặc string sai kiểu. | Viết `url = uri("...")`. |
| `Unresolved reference: it` | Closure Groovy và Kotlin lambda có receiver/parameter khác. | Xem API, dùng tham số tường minh hoặc receiver đúng. |
| `Property 'foo' not found` | Biến `def`/`ext` trong ngữ cảnh Groovy động không còn được tra cứu như cũ. | Xác định Project/Settings/extension sở hữu property; dùng `extra`/API có kiểu. |
| Task action chạy khác trước | Vô ý đổi `dependsOn`, cấu hình task, `doLast` hoặc Provider. | So sánh task graph và output thực, giữ ngữ nghĩa cũ. |
| Dependency không resolve | Sai repo, project path, configuration hoặc version. | So sánh `dependencies --configuration ...` trước/sau, xác nhận repository và plugin. |
| IDE báo lỗi nhưng CLI thành công | IDE chưa reload model Kotlin DSL. | Sync lại Gradle project, dùng Wrapper để xác định lỗi thật. |
| CI vẫn tìm `build.gradle` | Đường dẫn script cũ trong CI hoặc `apply(from = ...)`. | Cập nhật tham chiếu và chạy clean checkout. |
| Plugin Groovy không compile trong Kotlin DSL | API dynamic/Closure chưa tương thích. | Tra tài liệu/plugin version; dùng API typed/interop hoặc giữ script Groovy riêng. |

**Ví dụ đặc biệt:** khi Groovy viết `project.version` ở thời điểm cấu hình và sau đó đổi version, một chuỗi đã được nội suy sớm sẽ **không tự cập nhật**. Khi migrate, tránh ngẫu nhiên đọc Provider/property sớm rồi làm thay đổi kết quả. Tương tự, đổi `tasks.create` thành `tasks.register` có thể có lợi cho cấu hình lười, nhưng hãy kiểm tra thứ tự/lúc hiện thực hóa task nếu build cũ có side effect.

## 14. Quy trình QA migration có thể áp dụng cho dự án thật

### 14.1. Kiểm tra mô hình và script compilation

```bash
./gradlew --version
./gradlew help
./gradlew projects
./gradlew tasks --all
./gradlew :app:tasks --all
```

Xem project path, các plugin/task đã có, các unresolved reference hoặc script compilation error. Kotlin DSL có thể mất thêm thời gian biên dịch script trên clean checkout; khác biệt thời gian lần đầu không tự chứng minh chức năng đổi.

### 14.2. Kiểm tra dependency và task graph

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:compileJava --dry-run
./gradlew :app:build --dry-run
```

`--dry-run` cho biết task nào được lên lịch, không thực thi action và **không chứng minh** Java/test thực sự chạy đúng. So sánh dependency, classpath, toolchain, task order cần thiết và artifact producer với baseline.

### 14.3. Chạy build/test/artifact thật

```bash
./gradlew :app:build
./gradlew :app:run
./gradlew -q :app:showEnvironment -Penvironment=prod
```

Với project có test integration, publishing, code generation, signing, Docker/Android... thì cần chạy task liên quan trong môi trường cho phép. So sánh tên/nội dung artifact, báo cáo test, main class, manifest, compiler options và các output có ý nghĩa. Không yêu cầu log giống từng byte, vì cache và version có thể làm thay đổi dòng trạng thái.

### 14.4. Kiểm tra IDE và CI

Reload project bằng Gradle Wrapper trong IDE; kiểm tra type-safe accessors, imports, Kotlin script errors. Chạy pipeline trên clean checkout với JDK/Gradle version đã ghi. Dò các tham chiếu đến `build.gradle`, `settings.gradle`, `gradle/quality.gradle` trong CI, wrapper scripts và các `apply(from = ...)` có liên quan. Nếu một plugin yêu cầu credentials, dịch vụ nội bộ hoặc toolchain chưa sẵn, ghi rõ hạn chế kiểm thử thay vì suy đoán.

**Không nhầm lẫn:** script Kotlin DSL compile thành công là cổng đầu; `:app:build`, test, dependency resolution, artifact và CI hoạt động đúng mới là bằng chứng migration ở phạm vi thực tế.

## 15. Bảng tra nhanh cuối bài

| Groovy DSL | Kotlin DSL |
| --- | --- |
| `plugins { id 'java' }` | `plugins { id("java") }` |
| `id 'x.y' version '1.2'` | `id("x.y") version "1.2"` |
| `apply plugin: 'java'` | `apply(plugin = "java")`, ưu tiên `plugins { }` |
| `implementation 'g:a:v'` | `implementation("g:a:v")` |
| `implementation project(':core')` | `implementation(project(":core"))` |
| `testImplementation files('libs/x.jar')` | `testImplementation(files("libs/x.jar"))` |
| `exclude group: 'g', module: 'm'` | `exclude(group = "g", module = "m")` trong DSL tương ứng |
| `def opts = ['dev', 'prod']` | `val opts = listOf("dev", "prod")` |
| `def flags = [debug: true]` | `val flags = mapOf("debug" to true)` |
| `ext.branch = 'main'` | `extra["branch"] = "main"` |
| `println "Hello, $name"` | `println("Hello, $name")` |
| `tasks.register('hello') { }` | `tasks.register("hello") { }` |
| `tasks.register('copy', Copy) { }` | `tasks.register<Copy>("copy") { }` |
| `tasks.named('test', Test) { }` | `tasks.named<Test>("test") { }` |
| `dependsOn prepare` | `dependsOn(prepare)` |
| `apply from: 'rules.gradle'` | `apply(from = "rules.gradle")` |
| `include 'core', 'app'` | `include(":core", ":app")` |

Cách tư duy khi gặp dòng chưa biết chuyển thế nào: **xác định đó là biểu thức Groovy hay một API Gradle; biết đối tượng đang cấu hình; tra method/property/kiểu thực; chuyển bằng Kotlin có kiểu; kiểm chứng bằng chính Gradle Wrapper của dự án**. Đó là cách giữ nguyên hành vi build thay vì chỉ khiến file mới trông giống Kotlin.

### Tài liệu tham khảo chính thức

- [Gradle — Migrating build logic from Groovy to Kotlin](https://docs.gradle.org/current/userguide/migrating_from_groovy_to_kotlin_dsl.html)
- [Gradle — Kotlin DSL Primer](https://docs.gradle.org/current/userguide/kotlin_dsl.html)
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle — Task Configuration Avoidance](https://docs.gradle.org/current/userguide/task_configuration_avoidance.html)
- [Kotlin — Basic Syntax](https://kotlinlang.org/docs/basic-syntax.html)
