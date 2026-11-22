# buildSrc trong Gradle: cấu trúc, dependencies và ảnh hưởng tới build

## 1. buildSrc là gì và khi nào nên dùng?

Khi repository Gradle có nhiều modules, các build scripts thường lặp cùng cấu hình Java toolchain, compiler options, test tasks, publishing hoặc kiểm tra chất lượng. Nếu copy-paste trong `app/build.gradle.kts`, `lib/build.gradle.kts` và nhiều module khác, mỗi lần nâng cấp sẽ phải sửa nhiều nơi và dễ xuất hiện những module có policy khác nhau mà không ai nhận ra.

**`buildSrc`** là một thư mục đặc biệt tại **root của Gradle build**. Khi nhận diện thư mục `buildSrc/`, Gradle xem nó như một **build độc lập được quản lý ngầm**, biên dịch code và precompiled scripts ở đó trước khi những **project build scripts** của main build cần dùng chúng, rồi đưa output lên build-script classpath. Nhờ vậy bạn có thể:

- Đưa helper Java/Kotlin/Groovy classes dùng bởi Gradle scripts vào một chỗ.
- Tạo custom task types và plugin implementations.
- Định nghĩa **precompiled script convention plugins** để subprojects áp dụng bằng plugin ID ngắn.
- Viết unit tests hoặc Gradle TestKit tests cho build logic như một project Gradle bình thường.
- Giảm việc lặp cấu hình và tránh `subprojects { ... }` tác động ngầm lên tất cả project.

Ví dụ:

```text
workspace/
├── settings.gradle.kts
├── build.gradle.kts
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── java-conventions.gradle.kts
├── app/
│   ├── build.gradle.kts
│   └── src/main/java/...
└── lib/
    ├── build.gradle.kts
    └── src/main/java/...
```

File `buildSrc/src/main/kotlin/java-conventions.gradle.kts`, khi buildSrc áp dụng plugin `kotlin-dsl`, được Gradle biên dịch thành plugin có ID `java-conventions`. Các module có thể dùng:

```kotlin
plugins {
    id("java-conventions")
}
```

mà **không phải thêm `includeBuild("buildSrc")`** trong root Settings. Đây là khác biệt quan trọng với included build có tên thông thường như `build-logic`.

**Giới hạn quan trọng:** buildSrc chứa **logic dùng để xây dự án**, không phải source runtime của ứng dụng. Class từ `buildSrc` được đưa vào classpath của Gradle scripts, **không tự thêm vào Java application's `compileClasspath` hay `runtimeClasspath`**.

### Mục tiêu sau bài học

Bạn sẽ biết cấu trúc `buildSrc`, cơ chế tự phát hiện/biên dịch, Gradle classpaths, repositories/dependencies/version catalogs riêng, cách dùng helper Java 17, cách tạo convention plugins Kotlin và Groovy, ảnh hưởng lên Configuration Cache/incremental build/classloaders, cách test buildSrc, các lỗi phổ biến và khi nào nên chuyển sang included build `build-logic`.

## 2. buildSrc không phải một subproject bình thường

Phân biệt ba loại thành phần:

| Loại | Cách tham gia build | Công dụng |
| --- | --- | --- |
| `:app`, `:lib` | `include(":app", ":lib")` trong root Settings. | Modules tạo application/library artifacts. |
| `buildSrc/` | Được Gradle tự phát hiện tại root. | Tạo các compiled build logic classes/plugins cho project scripts. |
| `build-logic/` | Được khai báo tường minh với `includeBuild(...)`, thường trong `pluginManagement`. | Included build cung cấp versioned/structured plugins với classpath scope rõ hơn. |

Vì là **build riêng**, `buildSrc` có thể chứa:
- `buildSrc/build.gradle.kts` hoặc `buildSrc/build.gradle`.
- `buildSrc/settings.gradle.kts`/`settings.gradle` nếu cần Settings riêng.
- `src/main/java`, `src/main/kotlin`, `src/main/groovy` tùy plugin.
- `src/main/resources` cho resource metadata.
- `src/test/java` hoặc `src/test/kotlin` và tương đương để test build logic.
- Repositories, plugins, dependencies, sourceSets và tasks riêng.

Nó **không** được khai báo `include(":buildSrc")` trong Settings của main build. Nếu bạn đặt `buildSrc` ở một folder không phải root build đang chạy, nó không trở thành build logic dùng chung chỉ nhờ cái tên. Muốn rõ ràng xuyên builds, dùng included build.

### 2.1. Vòng đời giản lược

Khi chạy `./gradlew :app:run`:

1. Gradle khởi chạy bằng Gradle Wrapper/JVM phù hợp và xử lý Settings.
2. Gradle nhận diện `buildSrc`, cấu hình build logic và biên dịch hoặc lấy output/cache khi cần.
3. Những classes/plugins của buildSrc được thêm vào classpath cho root/subproject **build scripts**.
4. Main build scripts được cấu hình; modules có thể import helper hoặc apply plugin từ buildSrc.
5. Gradle lên task graph và chạy những tasks cần để build/test/run app.

Đừng diễn giải là “Gradle luôn compile lại toàn bộ buildSrc mỗi lần chạy”. Incremental compilation, up-to-date checks và caching có thể tránh công việc khi inputs không đổi. Nhưng khi **code hoặc dependency của buildSrc** thay đổi, Gradle phải xem xét lại nhiều tầng vì classpath của project build scripts đã đổi.

### 2.2. buildSrc không tự làm Settings plugin

Trong các Gradle builds hiện đại, buildSrc compiled code được làm sẵn cho **project build scripts**. Không nên dựa vào nó để resolve một plugin dùng ngay ở **root `settings.gradle.kts`** trước khi buildSrc được chuẩn bị. Với Settings plugins, cách rõ hơn là dùng published plugin hoặc một plugin-producing included build được khai báo trong `pluginManagement { includeBuild("...") }`.

## 3. Có thể chia sẻ những loại build logic nào?

**Helper class:** Một Java/Kotlin helper kiểm tra format, đặt conventions, tạo ID hoặc xác định file paths được script gọi. Dễ test, nhưng nếu mỗi module vẫn lặp cấu hình tasks/plugins thì chưa thay thế được convention plugin.

**Precompiled script plugin:** Một `*.gradle.kts` hoặc `*.gradle` nằm trong plugin source set, được Gradle compile thành plugin với ID suy từ filename/package. Nó thích hợp cho Java conventions, test settings, publishing defaults và logic khai báo đơn giản.

**Binary Gradle plugin:** Class implement `Plugin<Project>`, có extensions, task types với `Property<T>`, work actions, validation và tests. Phù hợp với build logic phức tạp, yêu cầu typed API hoặc chia sẻ qua nhiều repositories.

Cả ba có thể nằm trong buildSrc. Với quy mô lớn, **Gradle Best Practices** hiện nay khuyến nghị xem một included build `build-logic` là vị trí ưu tiên cho reusable plugins và conventions vì có ranh giới classloader/dependency tốt hơn.

## 4. Demo A — Java 17 helper class trong buildSrc

Đầu tiên tạo một project **không có dependency bên ngoài**, dùng `buildSrc` để cung cấp class Java cho Gradle script. Demo A độc lập với Demo B ở phần sau; không kết hợp cả hai cấu hình buildSrc trong cùng project mà không chủ động thiết kế lại.

### 4.1. Cấu trúc files

```text
buildsrc-helper-lab/
├── settings.gradle.kts
├── build.gradle.kts
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/java/demo/build/BuildText.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/app/Main.java
```

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "buildsrc-helper-lab"
include(":app")
```

Root `build.gradle.kts` có thể rỗng nếu root không cần plugins/tasks. Không thêm `include(":buildSrc")`: Gradle tự phát hiện special directory.

### 4.2. buildSrc/build.gradle.kts

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

Java Library plugin biên dịch Java code trong `buildSrc/src/main/java`. Vì ví dụ chỉ dùng Java standard library, buildSrc không cần khai báo `repositories`/`dependencies`. Đặt Java toolchain 17 **cho buildSrc** không tự đặt Java 17 cho mọi application module.

### 4.3. buildSrc/src/main/java/demo/build/BuildText.java

```java
package demo.build;

import java.util.Locale;
import java.util.Objects;

public final class BuildText {
    private BuildText() {
    }

    public static String label(String module, int javaVersion) {
        String normalized = Objects.requireNonNull(module)
            .strip()
            .toUpperCase(Locale.ROOT);
        return normalized + ":JAVA" + javaVersion;
    }

    public static void main(String[] args) {
        System.out.println(label(" demo ", 17));
    }
}
```

Đây là Java 17 code hợp lệ, biên dịch/chạy **không cần Gradle**:

```bash
mkdir -p manual-out
javac --release 17 -d manual-out buildSrc/src/main/java/demo/build/BuildText.java
java -cp manual-out demo.build.BuildText
```

Stdout **chính xác**:

```text
DEMO:JAVA17
```

`javac --release 17` bảo đảm Java language/bytecode/API level của class. Nhưng compile bằng `javac` chưa chứng minh Gradle đã phát hiện buildSrc; bước tiếp theo dùng class ngay trong `app/build.gradle.kts`.

### 4.4. app/build.gradle.kts

```kotlin
import demo.build.BuildText

plugins {
    id("application")
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

application {
    mainClass.set("demo.app.Main")
}

tasks.register("printBuildLabel") {
    group = "help"
    description = "Print a label using buildSrc class"
    doLast {
        println(BuildText.label(" app ", 17))
    }
}
```

**`app/src/main/java/demo/app/Main.java`:**

```java
package demo.app;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("APP_RUNTIME=" + Runtime.version().feature());
    }
}
```

Chạy:

```bash
./gradlew -q :app:printBuildLabel
./gradlew -q :app:run
```

Stdout của **`printBuildLabel`**:

```text
APP:JAVA17
```

Stdout của **`:app:run`** khi dùng launcher Java 17:

```text
APP_RUNTIME=17
```

Hai dòng này đến từ hai ngữ cảnh khác nhau:
- `BuildText` thuộc build logic, được Gradle scripts/task sử dụng.
- `demo.app.Main` thuộc application code, chạy trong Java process của task `run`.

Nếu bạn thêm `import demo.build.BuildText;` vào `app/src/main/java/demo/app/Main.java`, JavaCompile của app **không tự thấy class** chỉ vì nó tồn tại trong buildSrc. Muốn dùng chung class runtime, hãy chuyển logic đó thành Java library module và khai báo `implementation(project(":..."))` phù hợp, thay vì phụ thuộc ngược vào buildSrc.

### 4.5. Groovy DSL thay thế cho Demo A

Giữ nguyên các Java classes. Thay `settings.gradle.kts` bằng **`settings.gradle`**:

```groovy
rootProject.name = 'buildsrc-helper-lab'
include 'app'
```

Thay `buildSrc/build.gradle.kts` bằng **`buildSrc/build.gradle`**:

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

**`app/build.gradle`**:

```groovy
import demo.build.BuildText

plugins {
    id 'application'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.app.Main'
}

tasks.register('printBuildLabel') {
    group = 'help'
    description = 'Print a label using buildSrc class'
    doLast {
        println BuildText.label(' app ', 17)
    }
}
```

Stdout vẫn là `APP:JAVA17` và `APP_RUNTIME=17` trong môi trường Java 17 phù hợp. Kotlin DSL và Groovy DSL là **hai lựa chọn build scripts khác nhau**, không phải hai đoạn cùng dán vào một file.

## 5. Demo B — convention plugin để chia sẻ Java 17 configuration

Một helper class tốt để tái sử dụng thuật toán, nhưng vẫn có thể phải copy nhiều block cấu hình tasks/plugins. Convention plugin giải quyết vấn đề này tốt hơn. Demo B có `:lib` và `:app`, cả hai áp dụng chung `java-conventions`.

### 5.1. Cấu trúc

```text
buildsrc-convention-lab/
├── settings.gradle.kts
├── buildSrc/
│   ├── build.gradle.kts
│   └── src/main/kotlin/java-conventions.gradle.kts
├── lib/
│   ├── build.gradle.kts
│   └── src/main/java/demo/Greeting.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/Main.java
```

**`settings.gradle.kts`:**

```kotlin
rootProject.name = "buildsrc-convention-lab"
include(":lib", ":app")
```

### 5.2. buildSrc/build.gradle.kts

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
```

`kotlin-dsl` hỗ trợ phát triển Kotlin-based Gradle build logic, đồng thời xử lý compilation của `*.gradle.kts` precompiled script plugins trong `src/main/kotlin`. Repositories của buildSrc được khai báo cho **build riêng này**; nếu CI hạn chế mạng, dùng approved mirror/cache tương ứng.

### 5.3. buildSrc/src/main/kotlin/java-conventions.gradle.kts

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

Gradle biên dịch precompiled plugin với ID **`java-conventions`** suy từ filename. Plugin áp dụng `java-library` và Java toolchain 17. Không cần khai báo một `gradlePlugin { plugins {...} }` chỉ để tạo ID cho precompiled script plugin.

Có thể bổ sung compiler encoding và target một cách tập trung:

```kotlin
// Phần thêm vào cuối java-conventions.gradle.kts nếu cần.
import org.gradle.api.tasks.compile.JavaCompile

tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
    options.release.set(17)
}
```

Đây là snippet **minh họa bổ sung**: các import trong file script thật nên đặt ở đầu file, trước `plugins`. Với toolchain 17, `--release 17` phù hợp; khi dùng compiler/toolchain version khác, phải kiểm tra mục tiêu compatibility. Không cần đoạn này để chạy lab cơ bản.

### 5.4. lib/build.gradle.kts và Java library

```kotlin
plugins {
    id("java-conventions")
}
```

**`lib/src/main/java/demo/Greeting.java`:**

```java
package demo;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Hello, " + name.strip() + "!";
    }
}
```

Module `lib` nhận `java-library` plugin và Java 17 toolchain từ convention. Không lặp lại cùng cấu hình trong `lib/build.gradle.kts`.

### 5.5. app/build.gradle.kts và Java application

```kotlin
plugins {
    id("application")
    id("java-conventions")
}

dependencies {
    implementation(project(":lib"))
}

application {
    mainClass.set("demo.Main")
}
```

**`app/src/main/java/demo/Main.java`:**

```java
package demo;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println(Greeting.message(" Gradle "));
        System.out.println("runtime.major=" + Runtime.version().feature());
    }
}
```

`implementation(project(":lib"))` đưa production classes từ `:lib` vào app. **BuildSrc không làm việc này**. `application` plugin cung cấp task `run`; convention cung cấp `java-library` và Java toolchain.

### 5.6. Chạy và xác minh

```bash
./gradlew -q javaToolchains
./gradlew :lib:compileJava :app:compileJava
./gradlew -q :app:run
```

Stdout của **application** khi launcher là Java 17:

```text
Hello, Gradle!
runtime.major=17
```

Các Gradle task logs, repository resolution và `javaToolchains` outputs sẽ thay đổi theo môi trường. Không ghi nhớ một output Gradle dài cố định; chỉ hai dòng `System.out.println` trên là output được Java code xác định.

Có thể compile hai classes thủ công với JDK 17 khi đã tạo files:

```bash
mkdir -p out
javac --release 17 -d out \
  lib/src/main/java/demo/Greeting.java \
  app/src/main/java/demo/Main.java
java -cp out demo.Main
```

Nếu lệnh `java` dùng JDK/JRE 17 thì stdout cũng gồm hai dòng trên. Nếu runtime trên PATH là Java 21, dòng thứ hai sẽ là `runtime.major=21`; vì thế **Java toolchain Gradle và PATH runtime không phải một khái niệm**.

### 5.7. Groovy DSL cho convention plugin

Giữ nguyên Java sources. Dùng **`settings.gradle`**:

```groovy
rootProject.name = 'buildsrc-convention-lab'
include 'lib', 'app'
```

Dùng **`buildSrc/build.gradle`**:

```groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
}
```

**`buildSrc/src/main/groovy/java-conventions.gradle`**:

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

**`lib/build.gradle`**:

```groovy
plugins {
    id 'java-conventions'
}
```

**`app/build.gradle`**:

```groovy
plugins {
    id 'application'
    id 'java-conventions'
}

dependencies {
    implementation project(':lib')
}

application {
    mainClass = 'demo.Main'
}
```

`groovy-gradle-plugin` compile `*.gradle` scripts trong `src/main/groovy` thành precompiled plugins; Kotlin dùng `kotlin-dsl` và `*.gradle.kts` trong `src/main/kotlin`. Với cả hai, plugin ID `java-conventions` và hành vi application là như nhau.

## 6. Từ helper sang convention plugin: ưu và nhược điểm

Một helper `BuildText.label` hỗ trợ logic tái sử dụng, nhưng nếu mọi module vẫn lặp `java { toolchain { ... } }` hoặc `tasks.test { ... }` thì duplication vẫn còn.

Convention plugin:
- Đóng gói **cấu hình** có thể áp dụng bằng plugin ID.
- Giúp scripts ngắn, dễ nhận biết một module có tuân thủ policy nào.
- Cho phép quản lý một nơi khi đổi toolchain/test settings.
- Dễ có test riêng và IDE support.
- Giảm nhu cầu block `allprojects { ... }`/`subprojects { ... }` cấu hình tràn lan.

Tuy nhiên cần chia plugin theo vai trò thực. Library và application có thể khác Java target, test suites hoặc artifact packaging. Android/Kotlin/Scala/native builds có settings riêng. Không áp đặt một “super-conventions” plugin cho mọi module nếu scope của nó không phù hợp.

## 7. Dependencies của buildSrc: ranh giới classpath quan trọng nhất

**BuildSrc dependencies thuộc build logic classpath**, không phải production runtime classpath.

Giả sử `buildSrc/build.gradle.kts` có:

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Lúc này Kotlin/Java code trong **buildSrc** có thể gọi Commons Lang3 nếu source/API tương thích. Nhưng Java source trong `app/src/main/java` **không tự có** `org.apache.commons.lang3.StringUtils`.

Để app dùng Commons Lang3 ở runtime, phải khai báo trong **`app/build.gradle.kts`**:

```kotlin
repositories {
    mavenCentral()
}

dependencies {
    implementation("org.apache.commons:commons-lang3:3.17.0")
}
```

Hai dependencies trùng tọa độ nhưng được resolve trong **hai builds/contexts khác nhau**. Một build dùng helper ở configuration phase, một build dùng library trong application. Không nhầm `buildSrc` với `src/main/java` của app.

### 7.1. Ba classpaths cần nhớ

| Classpath | Chứa gì? | Ai dùng? |
| --- | --- | --- |
| BuildSrc compile/runtime classpaths | Gradle API, Kotlin/Groovy runtime theo plugin, external build logic libraries. | Biên dịch và chạy classes/plugins trong buildSrc. |
| Project build-script classpath | Gradle DSL/Plugins, compiled buildSrc outputs/deps được Gradle phơi bày. | Cấu hình app/lib tasks, repositories, plugins. |
| Production app compile/runtime classpaths | `implementation`, `api`, `runtimeOnly` và project dependencies. | `javac`/Java application/test processes. |

Tài liệu Gradle chỉ rõ buildSrc output được đưa lên classpath của project build scripts; **không có nghĩa mọi class đó sẽ nằm trong application JAR**.

### 7.2. Rủi ro classloader và dependency version conflict

Vì buildSrc classes/dependencies xuất hiện rộng trong script classpath, một số version conflicts có thể xuất hiện giữa plugin jars, Gradle API và thư viện mà buildSrc kéo theo. Triệu chứng như `NoSuchMethodError` hoặc `ClassNotFoundException` ở **Gradle configuration phase** không nhất thiết liên quan production dependencies.

Một dependency thêm “cho tiện” vào buildSrc có thể khiến nhiều scripts phải resolve lại classpath hoặc không tương thích với plugin khác. Giữ buildSrc dependencies nhỏ, versioned và tested; đừng copy `implementation` list của app vào buildSrc.

## 8. Repositories của buildSrc không tự kế thừa root

Root `settings.gradle.kts` có thể viết:

```kotlin
dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
```

Nhưng buildSrc là build riêng. Không nên giả định nó luôn có đúng repositories, pluginManagement, credentials hoặc version catalogs của root. Nếu buildSrc cần external plugin/library, cấu hình đúng trong **buildSrc**:

```kotlin
// buildSrc/settings.gradle.kts
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}
```

Ví dụ dùng public repositories vì dễ học; CI enterprise có thể thay bằng internal mirrors và credentials được quản lý. Không đưa token/password vào Git.

**Nhận biết lỗi:** Main `implementation(...)` resolve được nhưng `buildSrc:compileKotlin` fail `Could not resolve...` thì thường cần xem **buildSrc repositories/dependencies**, không sửa app's repositories.

## 9. Root version catalog có tự xuất hiện trong buildSrc không?

**Không.** `gradle/libs.versions.toml` của root được Gradle import theo Settings của main build, còn buildSrc có Settings riêng. Muốn dùng chung catalog, khai báo trong **`buildSrc/settings.gradle.kts`**:

```kotlin
dependencyResolutionManagement {
    versionCatalogs {
        create("libs") {
            from(files("../gradle/libs.versions.toml"))
        }
    }
}
```

Giả sử file TOML có alias thích hợp, `buildSrc/build.gradle.kts` có thể sử dụng catalog để khai báo dependency:

```kotlin
dependencies {
    implementation(libs.commons.lang3)
}
```

Đây là snippet **có điều kiện**, không tự chạy nếu alias `commons-lang3` chưa có trong TOML. Khi buildSrc có own `gradle/libs.versions.toml`, chú ý không tạo duplicate catalog definition.

### 9.1. Plugin aliases trong precompiled scripts

Điểm dễ nhầm: trong `plugins { ... }` của **precompiled script plugin**, việc dùng `alias(libs.plugins.somePlugin)` không giống `plugins` block của root project. Theo Gradle Version Catalog docs, precompiled script plugin không truy cập plugin catalog aliases trực tiếp ở block đó.

Cách được khuyến nghị khi apply external plugin:

1. Khai báo **plugin implementation artifact** làm `implementation` dependency của buildSrc.
2. Apply **plugin ID không kèm version** trong precompiled script plugin.

Ví dụ minh họa lấy từ Gradle docs (không phải một bài thực hành Docker hoàn chỉnh):

```kotlin
// buildSrc/build.gradle.kts
plugins {
    `kotlin-dsl`
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("com.bmuschko:gradle-docker-plugin:6.4.0")
}
```

```kotlin
// buildSrc/src/main/kotlin/docker-conventions.gradle.kts
plugins {
    id("com.bmuschko.docker-remote-api")
}
```

Version của external plugin ở **buildSrc dependency declaration**; `plugins { id(...) }` trong precompiled plugin chỉ áp dụng plugin. `6.4.0` là version ví dụ trong tài liệu, **không phải khẳng định plugin này là bản mới nhất hoặc phù hợp mọi Gradle version**.

## 10. Test buildSrc là một build riêng

Bạn có thể viết unit tests cho helper classes hoặc TestKit tests cho behavior của convention/binary plugins. Một phần cần nhớ: **chạy root `check` không mặc nhiên chạy mọi unit test riêng của buildSrc**. BuildSrc code cần được biên dịch để main build dùng, nhưng team nên có QA gate riêng cho build logic.

### 10.1. Java 17 smoke test độc lập

Dựa trên helper `BuildText.java` của Demo A, tạo một file **`BuildTextCheck.java`** ở root (dùng để thử Java class, không phải tự động JUnit test):

```java
import demo.build.BuildText;

public final class BuildTextCheck {
    private BuildTextCheck() {
    }

    public static void main(String[] args) {
        String actual = BuildText.label(" api ", 17);
        if (!"API:JAVA17".equals(actual)) {
            throw new AssertionError(actual);
        }
        System.out.println("BUILD_LOGIC_TEST_OK");
    }
}
```

Lệnh:

```bash
mkdir -p test-out
javac --release 17 -d test-out \
  buildSrc/src/main/java/demo/build/BuildText.java \
  BuildTextCheck.java
java -cp test-out BuildTextCheck
```

Stdout:

```text
BUILD_LOGIC_TEST_OK
```

Đây là test Java thủ công cho thuật toán, **không có Gradle/JUnit task**. Khi phát triển buildSrc production, hãy đặt JUnit tests dưới `buildSrc/src/test/java` và cấu hình test dependencies của buildSrc:

```kotlin
// Bổ sung vào buildSrc/build.gradle.kts phù hợp plugin test hiện có.
repositories {
    mavenCentral()
}

dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter:5.11.4")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher:1.11.4")
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
```

Khi đã có các test sources hợp lệ, CI có thể chạy:

```bash
./gradlew -p buildSrc test
./gradlew -p buildSrc check
```

Đó là **test của buildSrc build**, không phải `:app:test`. Với included build `build-logic` cũng nên chạy tests của chính included build.

### 10.2. Gradle TestKit cho plugin behavior

Nếu convention plugin cần đảm bảo task configuration, plugin application hoặc generated outputs, JUnit test chỉ kiểm tra helper có thể chưa đủ. Gradle TestKit tạo temporary build và gọi `GradleRunner` để test plugin như consumer sẽ dùng; có thể assert task outcome/output.

TestKit phải được cấu hình trong plugin development project (thường có `java-gradle-plugin`), dùng thư mục tạm và Gradle version/test configuration phù hợp. **Không coi một `BuildText.main` pass là toàn bộ convention plugin functional test đã đạt.**

## 11. Tác động tới configuration phase và build performance

Tài liệu **Gradle Best Practices** khuyên ưu tiên included `build-logic` cho build logic lớn vì buildSrc có scope classpath lớn. Một thay đổi trong buildSrc có thể ảnh hưởng cấu hình của **nhiều modules**, kể cả những modules không trực tiếp dùng helper vừa sửa.

Tuy nhiên cần phân biệt:

| Tầng | BuildSrc thay đổi có thể tác động thế nào? |
| --- | --- |
| BuildSrc compilation | Source/dependency inputs đổi thì tasks buildSrc có thể recompile hoặc lấy từ cache. |
| Kotlin/Groovy build scripts | Compiled script classpath đổi, có thể phải compile/configure lại. |
| Configuration Cache | buildSrc sources/build scripts/intermediate outputs là configuration inputs, có thể invalidate cache entry. |
| Task graph/configuration time | Cache miss khiến project configuration cần chạy lại. |
| `:app:compileJava`/`:lib:test` | Task inputs/up-to-date checks độc lập; **không chắc chắn mọi task rerun** chỉ vì buildSrc đổi. |

**Đừng nói quá:** “Mọi thay đổi buildSrc bắt Gradle biên dịch lại tất cả Java code” là không chính xác. Vấn đề lớn nhất là **script classpath/configuration invalidation scope**. Một build có nhiều modules/plugins có thể mất đáng kể thời gian cấu hình dù task compilation/test outputs vẫn UP-TO-DATE.

### 11.1. Ví dụ ảnh hưởng lan rộng

Một monorepo có 80 modules, nhưng một helper buildSrc chỉ được gọi ở 3 modules. Khi sửa helper:
- BuildSrc compile output thay đổi.
- Các project scripts chia sẻ buildSrc classpath có thể mất cache reuse.
- Nhiều modules có thể phải được cấu hình lại.
- Những JavaCompile tasks có inputs không đổi vẫn có thể UP-TO-DATE.

Nếu helper chuyển vào plugin của included build và chỉ 3 modules apply plugin đó, scope classpath/build invalidation **có thể nhỏ hơn**. Cải thiện không bảo đảm mọi lần; cần đo theo project thực tế.

### 11.2. Configuration Cache khác Build Cache

| Cache | Chức năng |
| --- | --- |
| **Configuration Cache** | Lưu/reuse trạng thái configuration và task graph khi inputs không đổi. |
| **Build Cache** | Lưu/reuse outputs của cacheable tasks khi inputs hash phù hợp. |
| **Incremental compilation** | Compile phần source liên quan thay vì toàn bộ khi compiler có đủ thông tin. |
| **Dependency cache** | Lưu resolved module artifacts/metadata. |

Đừng thấy output `FROM-CACHE` rồi kết luận Configuration Cache reused; hai cache có điều kiện và log riêng. Cũng không nên tắt tất cả caching để “chữa” plugin invalidation khi chưa xác định nguyên nhân.

## 12. Kiểm tra Configuration Cache với buildSrc

Chạy hai lần:

```bash
./gradlew :app:run --configuration-cache
./gradlew :app:run --configuration-cache
```

Nếu build logic đáp ứng requirements và không có input nào thay đổi, lần sau Gradle có thể báo **configuration cache reused**. Sau khi đổi source của `buildSrc`, entry có thể bị invalidated vì Gradle theo dõi buildSrc trong configuration inputs.

Trong Gradle hiện hành, có thể bật qua `org.gradle.configuration-cache=true` trong `gradle.properties`, nhưng lab chỉ cần flag. **Đừng hard-code stdout Gradle**, vì cache state, Gradle version và machine khác nhau.

### 12.1. Custom tasks cần Property/Provider API

Trong build logic tốt, task inputs/outputs nên được khai báo theo Gradle APIs như `@Input`, `@OutputFile`, `Property<String>`, `RegularFileProperty`. Đừng giữ tham chiếu tới `Project` hoặc script instance trong task actions rồi mong Configuration Cache serialize an toàn.

**Ví dụ Java custom task type mang tính khái niệm**:

```java
package demo.build;

import org.gradle.api.DefaultTask;
import org.gradle.api.provider.Property;
import org.gradle.api.tasks.Input;
import org.gradle.api.tasks.TaskAction;

public abstract class PrintLabelTask extends DefaultTask {
    @Input
    public abstract Property<String> getLabel();

    @TaskAction
    public void run() {
        System.out.println(getLabel().get());
    }
}
```

**Đây là code cần Gradle API classpath**, không phải một chương trình có thể compile bằng `javac` chỉ với JDK. Để chứa Java Gradle plugin/task types, buildSrc có thể dùng plugin `java-gradle-plugin` hoặc cấu hình Gradle API dependency phù hợp; Demo A trước đó không cần Gradle API vì chỉ dùng Java standard library.

Khi type đã nằm trên script classpath, có thể đăng ký:

```kotlin
import demo.build.PrintLabelTask

tasks.register<PrintLabelTask>("printGreeting") {
    label.set("HELLO_FROM_BUILDSRC")
}
```

Khi task được đăng ký đúng và chạy:

```text
HELLO_FROM_BUILDSRC
```

`@Input Property` giúp Gradle theo dõi state và serializable task configuration. Trái lại, mã như:

```kotlin
tasks.register("badTask") {
    doLast {
        println(project.name)
    }
}
```

có thể vi phạm Configuration Cache vì task action tham chiếu `Project` ở execution time. Nên gán project name vào task property ở configuration time và chỉ đọc `Property` trong `@TaskAction`.

### 12.2. Đọc environment, external process và files

Nếu build logic đọc environment/version/commit:
- Dùng `providers.gradleProperty("...")`, `providers.environmentVariable("...")` và `providers.fileContents(...)` khi phù hợp.
- Với external process ở configuration phase, cân nhắc `ValueSource` hoặc đưa data từ CI thành build property có input tracking.
- Không chạy shell/network bất ngờ ở configuration time nếu có thể trì hoãn tới task execution.
- Không in credentials/secrets ra task logs hoặc đưa chúng vào output artifacts.

Configuration Cache theo dõi nhiều loại inputs nhưng plugin/task vẫn phải tuân thủ requirements. Khi có report lỗi, sửa chính logic khiến việc serialize hoặc tracking không an toàn; không biến `--configuration-cache-problems=warn` thành policy lâu dài chỉ để build xanh.

## 13. Vì sao Gradle khuyên build-logic included build trong project lớn?

Gradle Best Practices hiện hành nói **included build**, thường tên `build-logic`, là cách nên ưu tiên cho reusable build logic của dự án lớn. `buildSrc` thuận tiện để prototype nhưng có một số đánh đổi:

1. Compiled output/dependencies của buildSrc xuất hiện rộng trên classpath project scripts, làm tăng invalidation.
2. Classloader và dependency resolution của buildSrc có những khác biệt subtle so với included plugin builds.
3. Khó phân chia nhiều convention plugins thành những classpaths được attach theo nhu cầu từng module.
4. Build logic settings/credentials/dependencies có thể bị hiểu nhầm là root build config.
5. Không tự có một versioned plugin artifact để share across repositories.
6. Dùng plugin trong Settings có thể cần cơ chế pluginManagement khác với buildSrc.
7. Code build logic không có tests/ownership rõ sẽ trở thành “thư viện tiện ích ngầm” khó bảo trì.

**Không có nghĩa buildSrc đã bị xóa hoặc bị cấm.** Với một repo nhỏ, một convention plugin, ít thay đổi và CI nhanh, buildSrc có thể là giải pháp đơn giản, hiệu quả. Nên quyết định bằng requirements và profiling thực tế.

### 13.1. Bảng so sánh

| Tiêu chí | buildSrc | Included build `build-logic` |
| --- | --- | --- |
| Đăng ký trong root Settings | Tự nhận diện theo tên ở root. | Cần `includeBuild` hoặc `pluginManagement.includeBuild`. |
| Script classpath | BuildSrc output sẵn cho root/subproject scripts. | Plugin classpath gắn nơi plugin được apply. |
| Scope invalidation | Có thể rộng khi buildSrc đổi. | Có thể nhỏ hơn với plugins/modules chia nhỏ. |
| Dependency/Version Catalog | Của buildSrc riêng. | Của included build riêng. |
| Unit/TestKit tests | Có thể viết trong buildSrc. | Có thể viết trong included build. |
| Chia sẻ ngoài repo | Thường phải copy/refactor/publish. | Dễ tách plugin package để dùng nhiều builds. |
| Prototype đơn giản | Rất tiện. | Setup nhiều hơn. |

## 14. Migration từ buildSrc sang build-logic included build

Giữ convention plugin từ Demo B nhưng di chuyển sang included build rõ ràng:

```text
buildsrc-convention-lab/
├── settings.gradle.kts
├── build-logic/
│   ├── settings.gradle.kts
│   ├── build.gradle.kts
│   └── src/main/kotlin/java-conventions.gradle.kts
├── lib/
│   ├── build.gradle.kts
│   └── src/main/java/demo/Greeting.java
└── app/
    ├── build.gradle.kts
    └── src/main/java/demo/Main.java
```

**Root `settings.gradle.kts`**:

```kotlin
pluginManagement {
    includeBuild("build-logic")

    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = "buildsrc-convention-lab"
include(":lib", ":app")
```

**`build-logic/settings.gradle.kts`**:

```kotlin
rootProject.name = "build-logic"
```

**`build-logic/build.gradle.kts`**:

```kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
}
```

**`build-logic/src/main/kotlin/java-conventions.gradle.kts`**:

```kotlin
plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}
```

`app/build.gradle.kts` và `lib/build.gradle.kts` **giữ nguyên** `id("java-conventions")`. Plugin được resolve thông qua `pluginManagement.includeBuild("build-logic")`.

### 14.1. Tại sao nên dùng pluginManagement.includeBuild?

Included builds có nhiều vai trò (develop libraries together, compose repositories, share plugins). Khi một build **cung cấp plugins dùng trong `plugins { ... }`**, khai báo trong `pluginManagement` của root Settings thể hiện rõ mục đích plugin resolution. Với Settings plugins được áp dụng ngay trong Settings file, điều này đặc biệt quan trọng.

**Không thêm `includeBuild("buildSrc")`** để “tối ưu” buildSrc. Với included build mới, tên và đường dẫn `build-logic` phải khớp file tree thật.

### 14.2. Bẫy migration: helper classes mất khả năng import trực tiếp

Một điểm rất dễ quên: ở buildSrc, project build scripts có thể import `demo.build.BuildText` **trực tiếp**. Khi chuyển class đó sang included build `build-logic`, class **không còn tự ở trên script classpath** của mọi module. Chỉ những plugin outputs được resolve/apply qua plugin mechanism mới hiện diện theo contract.

Do đó, nếu nhiều scripts đang gọi static helpers, cần chuyển behavior đó thành convention plugin/extension/task type API hoặc khai báo plugin classpath phù hợp. Không được di chuyển folder rồi giả định imports vẫn compile.

### 14.3. Lộ trình migration thực tế

1. Liệt kê các convention plugins và helpers trong buildSrc.
2. Phân nhóm theo vai trò: Java library/application/test/publish.
3. Tạo `build-logic` với Settings, plugin build, repositories, dependencies riêng.
4. Chuyển precompiled plugins vào `src/main/kotlin` hoặc `src/main/groovy`.
5. Khai báo `pluginManagement.includeBuild("build-logic")` ở root.
6. Giữ hoặc sửa plugin IDs ở modules để trỏ đúng plugin.
7. Chuyển direct helper imports thành plugin/extension API khi cần.
8. Chạy buildSrc/plugin tests, Java compile/test và CLI smoke tests.
9. Đo performance/configuration-cache reuse trước và sau.
10. Tránh giữ hai plugins cùng ID trong buildSrc và build-logic vì resolution/ownership sẽ mơ hồ.

### 14.4. Groovy included build tương đương

**Root `settings.gradle`**:

```groovy
pluginManagement {
    includeBuild('build-logic')

    repositories {
        gradlePluginPortal()
    }
}

rootProject.name = 'buildsrc-convention-lab'
include 'lib', 'app'
```

**`build-logic/build.gradle`**:

```groovy
plugins {
    id 'groovy-gradle-plugin'
}

repositories {
    gradlePluginPortal()
}
```

**`build-logic/src/main/groovy/java-conventions.gradle`**:

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

Project build scripts Groovy vẫn dùng `plugins { id 'java-conventions' }`. Đây là một cấu trúc khác buildSrc, mặc dù cùng source convention logic.

## 15. Tác động lên CI, Gradle Wrapper và môi trường phát triển

Một team sử dụng buildSrc nên quản lý hai lớp JDK:
- **JVM chạy Gradle**: phải tương thích với Gradle Wrapper/plugins.
- **Toolchain của buildSrc và application tasks**: theo `java.toolchain` của từng build/module.

Không có gì bảo đảm buildSrc và app tự có cùng Java toolchain nếu không cấu hình. Với Kotlin DSL buildSrc, version Kotlin/Gradle APIs do `kotlin-dsl`/Gradle distribution quản lý và nên kiểm tra tương thích plugin/Gradle/JDK trước upgrade.

CI nên:
- Sử dụng Gradle Wrapper của repository.
- Cài hoặc provision JDK toolchains cần thiết.
- Kiểm thử build logic **riêng**: `./gradlew -p buildSrc check` khi dùng buildSrc; hoặc tests của included build.
- Chạy main app/library `check`, integration tests theo policy.
- Chạy `--configuration-cache` trong một test workflow khi dự án muốn tận dụng tính năng này.
- Đảm bảo approved plugin repositories/mirrors và credentials không hard-code.
- Không coi việc compile buildSrc thành công là đủ để chứng minh plugin conventions hoạt động ở consumer project.

### 15.1. Đo performance thay vì đoán

Một kịch bản benchmark:
1. Chạy một clean build (sau khi Gradle caches lạnh nếu muốn đo cold).
2. Chạy lại cùng tasks để đo up-to-date/cache reuse.
3. Sửa một convention script trong buildSrc; đo configuration time và task work.
4. Chuyển convention vào included build; chạy cùng tình huống với cùng Gradle/JDK/dependencies.
5. So sánh median time nhiều runs, số scripts recompiled, number of tasks executed/UP-TO-DATE/FROM-CACHE, configuration cache status.

Không tuyên bố một migration luôn nhanh hơn theo tỷ lệ cố định. Với project nhỏ, lợi ích của included build có thể chủ yếu là code ownership/classpath boundaries.

## 16. Troubleshooting buildSrc

| Triệu chứng | Nguyên nhân khả dĩ | Cách xử lý |
| --- | --- | --- |
| `Unresolved reference: BuildText` trong Gradle Kotlin script | Class/package/import sai, file không nằm `buildSrc/src/main`, hoặc buildSrc compile lỗi. | Kiểm tra paths, `./gradlew -p buildSrc build`, log compiler. |
| `Plugin [id: 'java-conventions'] was not found` | Script plugin sai tên/vị trí/DSL plugin, hoặc migration included build thiếu pluginManagement.includeBuild. | Kiểm tra `src/main/kotlin/*.gradle.kts`, `kotlin-dsl` và Settings. |
| `Could not resolve ...` trong buildSrc | BuildSrc thiếu repositories, network/credentials/mirror. | Kiểm tra buildSrc Settings/build file, không sửa nhầm root app repos. |
| `Unresolved reference: libs` ở buildSrc | Root version catalog không tự được share. | Import catalog trong buildSrc Settings hoặc dùng dependency notation tường minh. |
| `alias(libs.plugins...)` không dùng được trong precompiled script | Plugin alias access limitation của plugin source set. | Thêm plugin implementation dependency và apply ID không version. |
| Build scripts thấy helper nhưng `Main.java` không import được | buildSrc là build script classpath, không phải app compileClasspath. | Tách logic runtime thành library module với `implementation`. |
| Plugin configuration báo `NoSuchMethodError` | Plugin/Gradle API version/classloader dependency conflict. | Kiểm tra buildSrc dependency versions và compatibility matrix. |
| Đổi buildSrc khiến nhiều modules reconfigure | Shared script classpath invalidation. | Đo CC/cache và cân nhắc included build scope nhỏ. |
| `:app:compileJava` không chạy được vì buildSrc lỗi | BuildSrc compile xảy ra trước khi project build scripts dùng nó. | Sửa buildSrc compiler/dependencies trước. |
| Root `check` pass nhưng buildSrc tests chưa chạy | Chỉ compile build logic, không mặc nhiên chạy test suite riêng. | CI chạy `-p buildSrc check`. |
| Configuration Cache fail | Task action capture `Project`, nonserializable state hoặc undeclared inputs. | Đọc report, dùng Property/Provider/ValueSource APIs. |
| `No matching toolchains found` cho buildSrc | JDK version của buildSrc không tìm thấy/provision. | Kiểm tra `javaToolchains` và JDK setup. |
| BuildSrc plugin và build-logic plugin trùng ID | Hai sources plugin có khả năng resolution conflict. | Chỉ giữ một nguồn ID và kiểm tra explicit inclusion. |
| Custom Java task compile lỗi `DefaultTask` không tìm thấy | Chưa có Gradle API compile classpath đúng. | Dùng `java-gradle-plugin` hoặc Gradle API dependency. |
| External plugin đã thêm trong root mà convention plugin không thấy | BuildSrc là build độc lập, external plugin implementation thiếu. | Đưa plugin implementation dependency vào buildSrc. |
| Runtime Java của app khác Gradle Daemon JDK | Java toolchain và daemon JVM là hai context. | Kiểm tra `./gradlew --version`, `javaToolchains`, `:app:run`. |

### 16.1. Những lệnh chẩn đoán hữu ích

```bash
./gradlew --version
./gradlew tasks --all

# Xem tasks và build riêng của buildSrc.
./gradlew -p buildSrc tasks
./gradlew -p buildSrc build
./gradlew -p buildSrc dependencies --configuration runtimeClasspath

# Kiểm tra main project.
./gradlew -q javaToolchains
./gradlew :app:run --info

# Kiểm tra Configuration Cache hai lần.
./gradlew :app:run --configuration-cache
./gradlew :app:run --configuration-cache
```

`--info` chỉ để debug; terminal logs sẽ phụ thuộc Gradle version, environment, cache state và plugins. Nếu buildSrc compiler fail, đừng chữa bằng cách thêm `implementation(...)` vào app khi lỗi xuất phát từ **buildSrc compile classpath**.

## 17. Best practices và tiêu chí ra quyết định

- Đặt `buildSrc` đúng **root build**. Không biến nó thành application source module.
- Giữ buildSrc dependencies/repositories/version catalogs rõ và riêng; tránh leak plugin dependencies.
- Dùng `kotlin-dsl`/`groovy-gradle-plugin` khi tạo precompiled script plugins tương ứng.
- Dùng convention plugins có mục đích để giảm copy-paste và tránh global `subprojects` mutation.
- Chia Java library/application/test conventions theo contract, tránh một plugin áp quá nhiều.
- Đặt custom tasks trong typed classes và dùng `Property/Provider` API, khai báo inputs/outputs.
- Test helpers và convention plugins; build logic quality gate là một phần release pipeline.
- Kiểm tra Gradle Wrapper/JDK/plugin compatibility trước mỗi nâng version.
- Quan sát configuration-cache misses và đo warm/cold build thay vì phỏng đoán.
- Chọn included build `build-logic` khi repository lớn hoặc cần classpath isolation.
- Không chuyển helpers sang included build mà bỏ qua direct import dependencies.
- Không nhúng secrets/tokens vào buildSrc hoặc logs.
- Đừng ép migrate buildSrc nhỏ, ít thay đổi, đang hoạt động tốt nếu không có lợi ích cụ thể.

## 18. Câu hỏi tự kiểm tra

1. **buildSrc có cần `include(":buildSrc")`?** — Không, Gradle tự nhận diện thư mục tại root.
2. **buildSrc `implementation("commons-lang3")` có làm app tự compile với Commons Lang3 không?** — Không, classpath của application là scope khác.
3. **Plugin ID của `src/main/kotlin/java-conventions.gradle.kts` là gì?** — `java-conventions`.
4. **Root `libs.versions.toml` có tự truyền vào buildSrc?** — Không, import/catalog trong Settings của buildSrc riêng.
5. **Vì sao `plugins` block precompiled plugin khác root?** — External plugin implementation cần trên build logic classpath; thường khai báo version qua buildSrc dependencies.
6. **buildSrc có thể được test?** — Có, chạy `./gradlew -p buildSrc test/check` khi đã cấu hình test tasks.
7. **Đổi buildSrc có chắc mọi JavaCompile task chạy lại?** — Không, có nhiều cơ chế up-to-date/cache; nhưng configuration/script classpath invalidation có thể rộng.
8. **Khi nào dùng build-logic included build?** — Khi cần tách plugins/classpaths và thu hẹp scope ảnh hưởng trên build lớn.
9. **Helper class được import trực tiếp từ buildSrc khi chuyển sang included build còn thấy tự động?** — Không; cần plugin/extension hoặc classpath design mới.
10. **Gradle Daemon JDK và Java toolchain của app có phải cùng version?** — Không bắt buộc, chúng có vai trò khác nhau.

## 19. Bảng tra nhanh

| Nội dung | Cấu hình/cách làm |
| --- | --- |
| buildSrc location | `<root>/buildSrc/` |
| Kotlin convention plugin source | `buildSrc/src/main/kotlin/name.gradle.kts` |
| Groovy convention plugin source | `buildSrc/src/main/groovy/name.gradle` |
| Kotlin build logic plugin | `plugins { `kotlin-dsl` }` (cú pháp trong code fence Kotlin). |
| Groovy build logic plugin | `plugins { id 'groovy-gradle-plugin' }` |
| Apply convention plugin | `plugins { id("java-conventions") }` |
| Java helper in buildSrc | `buildSrc/src/main/java/demo/build/BuildText.java` |
| Test buildSrc | `./gradlew -p buildSrc check` |
| Xem buildSrc dependencies | `./gradlew -p buildSrc dependencies --configuration runtimeClasspath` |
| Cấu hình buildSrc repositories | `buildSrc/build.gradle(.kts)`/`buildSrc/settings.gradle(.kts)` |
| Share root version catalog | Import `../gradle/libs.versions.toml` trong buildSrc Settings. |
| Explicit plugin build | `pluginManagement { includeBuild("build-logic") }` |
| Configuration Cache | `./gradlew --configuration-cache <task>` |
| Custom task state | `@Input Property<T>`, `@OutputFile`, `Provider` APIs. |
| Dùng helper ở application runtime | Tạo library dependency thực, không dựa vào buildSrc classpath. |
| Đo tác động buildSrc | So configuration cache reuse, script recompilation và task UP-TO-DATE trước/sau thay đổi. |

**Kết luận:** `buildSrc` là một **Gradle build đặc biệt được biên dịch tự động để cung cấp build logic cho project scripts**. Nó giúp tập trung conventions và helpers, nhưng cũng tạo **classpath coupling**: thay đổi dependencies/sources của buildSrc có thể làm nhiều scripts/configuration caches mất khả năng reuse. Cần phân biệt rõ buildSrc dependencies với runtime dependencies của app, quản lý riêng repositories/catalogs, test build logic và sử dụng typed Gradle APIs. Với build lớn, một **included build `build-logic`** thường dễ bảo trì và có thể giới hạn phạm vi invalidation tốt hơn; với build nhỏ, buildSrc vẫn là lựa chọn đơn giản đáng dùng.

### Tài liệu chính thức

- [Gradle — Sharing Build Logic using buildSrc](https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html): tự nhận diện, compilation và script classpath.
- [Gradle — Structuring and Organizing Gradle Projects](https://docs.gradle.org/current/userguide/organizing_build_logic.html): buildSrc và reusable logic.
- [Gradle — Best Practices for Structuring Builds](https://docs.gradle.org/current/userguide/best_practices_structuring_builds.html): ưu tiên included build và phân tích invalidation.
- [Gradle — Pre-compiled Script Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html): Kotlin/Groovy plugin source, plugin IDs, external dependencies.
- [Gradle — Convention Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins_convention.html): convention plugin patterns.
- [Gradle — Composite Builds](https://docs.gradle.org/current/userguide/composite_builds.html): explicit includeBuild/pluginManagement.
- [Gradle — Version Catalogs](https://docs.gradle.org/current/userguide/version_catalogs.html): catalog import vào buildSrc.
- [Gradle — Configuration Cache](https://docs.gradle.org/current/userguide/configuration_cache.html): tracked inputs và cache invalidation.
- [Gradle — Configuration Cache Requirements](https://docs.gradle.org/current/userguide/configuration_cache_requirements.html): typed task state và Providers.
- [Gradle — Implementing Gradle Plugins](https://docs.gradle.org/current/userguide/implementing_gradle_plugins.html): binary/precompiled plugins và testing.
